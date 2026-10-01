"""Topics (menu, hints) and TikTok accounts (rules, store, migration from the single-account database)."""

import json
import time
import sqlite3
import tempfile
import unittest
from pathlib import Path

from tests.support import StoreCase
from trendvn_worker.domain import topics
from trendvn_worker.domain.accounts import accepts, effective, slug, validate_account
from trendvn_worker.store import schema


class TopicMenuTests(unittest.TestCase):
    def test_every_topic_is_complete_and_unique(self):
        self.assertEqual(len(set(topics.TOPIC_IDS)), len(topics.TOPICS))
        for t in topics.TOPICS:
            self.assertTrue(t.vi and t.gemini, t.id)
        self.assertNotIn(topics.OTHER, topics.TOPIC_IDS)  # "other" is the rejection bucket, never a topic an account can take
        self.assertTrue(set(topics.LEGACY_TOPICS) <= set(topics.TOPIC_IDS))

    def test_valid_topics_cleans_orders_and_refuses(self):
        self.assertEqual(topics.valid_topics(["pets", "music", "pets"]), ["music", "pets"])  # menu order, no duplicates
        for bad in ([], None, "music", ["music", "nope"], ["other"], list(topics.TOPIC_IDS) + ["x"]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                topics.valid_topics(bad)

    def test_keywords_find_the_obvious_topic(self):
        cases = {
            "甘肃兰州牛肉面探店 #美食": "food",
            "My cat and my dog play #pets": "pets",
            "王者荣耀新英雄实测 #游戏": "gaming",
            "上海一日游攻略 #旅游": "travel",
            "樊振东德甲首秀 #乒乓球": "sports",
            "新手妈妈带娃日常 #宝宝": "family",
            "日常妆容分享 #化妆": "beauty",
        }
        for text, expected in cases.items():
            self.assertEqual(topics.guess_topics(text)[0], expected, text)
        self.assertEqual(topics.guess_topics("哈哈哈"), [])
        self.assertEqual(topics.guess_topics(None), [])

    def test_short_latin_keywords_match_whole_words_only(self):
        for text in (
            "Best location ever",
            "the competition",
            "Chăn nuôi gà",
            "Tăng cân nhanh",
            "deliver the parcel",
            "Discover my strong voice",
        ):
            self.assertEqual(topics.guess_topics(text), [], text)
        self.assertEqual(topics.guess_topics("My cat sleeps")[:1], ["pets"])
        self.assertEqual(topics.guess_topics("Nấu ăn ngon")[:1], ["food"])
        self.assertIn("lifestyle", topics.guess_topics("#vlog日常 下班后"))  # a hashtag glued to Chinese text still counts
        self.assertEqual(topics.guess_topics("LIVE concert")[:1], ["music"])

    def test_the_sources_own_category_wins_unless_the_title_clearly_disagrees(self):
        self.assertEqual(topics.topic_hint("music", "今天的生活"), "music")
        self.assertEqual(topics.topic_hint("music", "猫猫狗狗宠物日常"), "pets")  # two hits for pets
        self.assertEqual(topics.topic_hint("music", "一只猫"), "music")  # one hit is not enough to overrule the category
        self.assertEqual(topics.topic_hint(None, "牛肉面探店"), "food")
        self.assertIsNone(topics.topic_hint(None, "hello"))

    def test_the_prompt_menu_lists_every_topic(self):
        menu = topics.prompt_lines()
        for topic_id in topics.TOPIC_IDS:
            self.assertIn('"%s"' % topic_id, menu)

    def test_labels_never_fail(self):
        self.assertEqual(topics.label("pets"), "Thú cưng, động vật")
        self.assertEqual(topics.label("other"), "Ngoài chủ đề")
        self.assertEqual(topics.label(None), "chưa rõ")
        self.assertEqual(topics.label("zzz"), "zzz")


class AccountRuleTests(unittest.TestCase):
    def test_creating_needs_a_username_and_topics(self):
        ok = validate_account({"username": "@Kenh.Meo", "topics": ["pets", "pets"]}, creating=True)
        self.assertEqual((ok["username"], ok["topics"]), ("Kenh.Meo", ["pets"]))
        for bad in ({}, {"username": "a"}, {"username": "x y", "topics": ["pets"]}, {"username": "ok1", "topics": []}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate_account(bad, creating=True)

    def test_overrides_use_the_same_ranges_as_the_global_settings(self):
        ok = validate_account(
            {"daily_limit": 3, "min_gap": 0, "windows": [[8, 10]], "visibility": "friends", "enabled": False, "label": "  Mèo "}
        )
        self.assertEqual(
            (ok["daily_limit"], ok["min_gap"], ok["windows"], ok["visibility"], ok["enabled"], ok["label"]),
            (3, 0, [[8, 10]], "friends", False, "Mèo"),
        )
        self.assertIsNone(validate_account({"daily_limit": None})["daily_limit"])  # None means "use the global setting"
        for bad in ({"daily_limit": 0}, {"daily_limit": True}, {"windows": [[10, 8]]}, {"visibility": "all"}, {"enabled": "yes"}, "x"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate_account(bad)

    def test_effective_limits_fall_back_to_the_global_ones(self):
        cfg = {"daily_limit": 2, "min_publish_gap": 3600, "post_windows": [[11, 14]], "visibility": "public"}
        bare = {"daily_limit": None, "min_gap": None, "windows": None, "visibility": None}
        self.assertEqual(effective(bare, cfg), {"daily_limit": 2, "min_gap": 3600, "windows": [[11, 14]], "visibility": "public"})
        mine = {"daily_limit": 5, "min_gap": 0, "windows": [], "visibility": "self"}
        self.assertEqual(
            effective(mine, cfg), {"daily_limit": 5, "min_gap": 0, "windows": [], "visibility": "self"}
        )  # 0 and [] are real values

    def test_accepts_and_slug(self):
        account = {"topics": ["pets"]}
        self.assertTrue(accepts(account, "pets") and accepts(account, None))
        self.assertFalse(accepts(account, "food"))
        self.assertEqual(slug("Kênh Mèo!"), "k-nh-m-o")
        with self.assertRaises(ValueError):
            slug("!!!")


class AccountStoreTests(StoreCase):
    def test_a_fresh_database_has_the_main_account_with_the_legacy_topics(self):
        accounts = self.s.accounts()
        self.assertEqual([a["id"] for a in accounts], ["main"])
        self.assertEqual(set(accounts[0]["topics"]), set(topics.LEGACY_TOPICS))
        self.assertEqual(self.s.settings()["target"], accounts[0]["username"])
        self.assertEqual(self.s.wanted_topics(), [t for t in topics.TOPIC_IDS if t in topics.LEGACY_TOPICS])

    def test_add_update_and_delete(self):
        pets = self.s.add_account({"username": "kenh_meo", "topics": ["pets"], "daily_limit": 4})
        self.assertEqual((pets["id"], pets["daily_limit"], pets["label"], pets["enabled"]), ("kenh_meo", 4, "kenh_meo", True))
        self.assertIn("food", self.s.update_account("kenh_meo", {"topics": ["pets", "food"]})["topics"])
        self.assertEqual([a["id"] for a in self.s.accounts_for_topic("food")], ["kenh_meo"])
        self.assertEqual({a["id"] for a in self.s.accounts_for_topic("pets")}, {"main", "kenh_meo"})
        self.s.delete_account("kenh_meo")
        self.assertEqual([a["id"] for a in self.s.accounts()], ["main"])

    def test_uniqueness_and_the_last_account_rules(self):
        self.s.add_account({"username": "second", "topics": ["food"]})
        with self.assertRaisesRegex(ValueError, "đã có"):
            self.s.add_account({"username": "second", "topics": ["food"], "id": "other"})
        with self.assertRaisesRegex(ValueError, "Mã"):
            self.s.add_account({"username": "third", "topics": ["food"], "id": "second"})
        self.s.update_account("main", {"enabled": False})
        with self.assertRaisesRegex(ValueError, "ít nhất một"):
            self.s.update_account("second", {"enabled": False})
        with self.assertRaisesRegex(ValueError, "ít nhất một"):
            self.s.delete_account("second")  # the only one still enabled
        self.s.update_account("main", {"enabled": True})
        self.s.delete_account("second")
        with self.assertRaisesRegex(ValueError, "ít nhất một"):
            self.s.delete_account("main")  # the last one
        with self.assertRaises(ValueError):
            self.s.update_account("ghost", {"label": "x"})
        with self.assertRaises(ValueError):
            self.s.update_account("main", {})

    def test_at_most_ten_accounts(self):
        for i in range(9):
            self.s.add_account({"username": "acc%d" % i, "topics": ["food"]})
        with self.assertRaisesRegex(ValueError, "Tối đa"):
            self.s.add_account({"username": "one_too_many", "topics": ["food"]})

    def test_an_account_with_an_unconfirmed_post_cannot_be_deleted(self):
        self.s.add_account({"username": "second", "topics": ["food"]})
        self.job("j1", "publish_unknown", account="second")
        with self.assertRaisesRegex(ValueError, "chưa xác nhận"):
            self.s.delete_account("second")

    def test_the_target_setting_is_the_default_accounts_username(self):
        self.s.update_settings({"target": "@new_name"})
        self.assertEqual(self.s.account("main")["username"], "new_name")
        self.assertEqual(self.s.settings()["target"], "new_name")
        self.s.add_account({"username": "second", "topics": ["food"]})
        self.s.update_account("main", {"enabled": False})
        self.assertEqual(self.s.settings()["target"], "second")  # the first enabled account is the default

    def test_disabled_accounts_are_not_searched_for(self):
        self.s.add_account({"username": "gamer", "topics": ["gaming"], "enabled": False})
        self.assertNotIn("gaming", self.s.wanted_topics())
        self.s.update_account("gamer", {"enabled": True})
        self.assertIn("gaming", self.s.wanted_topics())


class AccountMigrationTests(unittest.TestCase):
    def test_a_database_of_version_one_gets_main_from_the_target_setting_and_topics_on_old_videos(self):
        with tempfile.TemporaryDirectory() as folder:
            db = sqlite3.connect(Path(folder) / "old.sqlite3")
            db.executescript(schema.BASELINE_TABLES)
            for column in schema.JOB_COLUMNS:
                db.execute("ALTER TABLE jobs ADD COLUMN " + column)
            db.execute("PRAGMA user_version = 1")
            db.execute("INSERT INTO settings VALUES ('target', ?)", (json.dumps("my_channel"),))
            db.execute(
                "INSERT INTO jobs(id,platform,source_id,url,state,analysis) VALUES ('a','douyin','1','u1','ready',?)",
                (json.dumps({"topic": "music"}),),
            )
            db.execute("INSERT INTO jobs(id,platform,source_id,url,state,analysis) VALUES ('b','douyin','2','u2','ready','not json')")
            db.commit()
            schema.migrate(db)
            self.assertEqual(db.execute("SELECT id,username FROM accounts").fetchall(), [("main", "my_channel")])
            self.assertEqual(dict(db.execute("SELECT id,topic FROM jobs").fetchall()), {"a": "music", "b": None})
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], len(schema.MIGRATIONS))
            schema.migrate(db)  # idempotent
            self.assertEqual(db.execute("SELECT count(*) FROM accounts").fetchone()[0], 1)
            db.close()


class IngestTopicTests(StoreCase):
    def batch(self, observed, items, topic=None, stream="jingxuan"):
        body = {"platform": "douyin", "stream": stream, "observed_at": observed, "items": items}
        if topic is not None:
            body["topic"] = topic
        return body

    def item(self, source_id, title="t"):
        return {
            "source_id": source_id,
            "url": "https://www.douyin.com/video/" + source_id,
            "country": "CN",
            "title": title,
            "evidence_url": "https://www.douyin.com/",
        }

    def hints(self):
        with self.s.connect() as db:
            return {r["source_id"]: r["topic_hint"] for r in db.execute("SELECT source_id,topic_hint FROM jobs")}

    def test_the_stream_topic_becomes_the_videos_hint_and_unknown_topics_are_refused(self):
        now = time.time()
        self.s.ingest(self.batch(now - 10, [], topic="pets", stream="pets_tab"), now=now)  # first scan of the stream: baseline
        result = self.s.ingest(self.batch(now - 5, [self.item("1", "一只可爱的猫")], topic="pets", stream="pets_tab"), now=now)
        self.assertEqual(result["new"], 1)
        self.assertEqual(self.hints(), {"1": "pets"})
        with self.assertRaisesRegex(ValueError, "Unknown topic"):
            self.s.ingest(self.batch(now - 4, [], topic="cooking", stream="bad_tab"), now=now)

    def test_without_a_stream_topic_the_keywords_guess_and_a_tab_later_overrides_the_guess(self):
        now = time.time()
        self.s.ingest(self.batch(now - 20, []), now=now)
        self.s.ingest(self.batch(now - 19, [self.item("2", "牛肉面探店"), self.item("3", "哈哈哈")]), now=now)
        self.assertEqual(self.hints(), {"2": "food", "3": None})  # keywords guess; nothing to go on for the other
        self.s.ingest(self.batch(now - 18, [], topic="comedy", stream="comedy_tab"), now=now)
        self.s.ingest(self.batch(now - 5, [self.item("3", "哈哈哈")], topic="comedy", stream="comedy_tab"), now=now)
        self.assertEqual(self.hints()["3"], "comedy")  # the tab's own category fills the gap
        self.s.ingest(self.batch(now - 4, [self.item("3", "哈哈哈")]), now=now)
        self.assertEqual(self.hints()["3"], "comedy")  # and the general feed seeing it again does not erase it

    def test_candidates_come_back_with_their_hint(self):
        now = time.time()
        self.s.ingest(self.batch(now - 20, [], topic="food", stream="food_tab"), now=now)
        self.s.ingest(self.batch(now - 5, [self.item("9", "x")], topic="food", stream="food_tab"), now=now)
        self.assertEqual([c["topic_hint"] for c in self.s.candidates_without_media()], ["food"])
