"""The chat log, picking a video out of an answer, and the commission links the owner confirmed."""

import json

from tests.support import StoreCase


def result(source_id="1234567890", platform="tiktok", url=None, level="candidate"):
    return {
        "source_id": source_id, "platform": platform, "title": "Samsung S24", "media": {"kind": "direct"},
        "url": url or "https://www.tiktok.com/@a/video/" + source_id, "match": {"level": level, "score": 100, "reason": "keywords"},
    }  # fmt: skip


class ChatLogTests(StoreCase):
    def test_a_message_keeps_its_body_and_the_thread_reads_oldest_first(self):
        first = self.s.chat_add("user", "say", {"text": "Samsung S24"}, account="main")
        second = self.s.chat_add("bot", "product", {"identity": {"name": "Samsung S24"}}, state="running")
        thread = self.s.chat_thread()
        self.assertEqual([m["id"] for m in thread], [first, second])
        self.assertEqual((thread[0]["role"], thread[0]["account"], thread[0]["body"]), ("user", "main", {"text": "Samsung S24"}))
        self.assertEqual(thread[1]["state"], "running")

    def test_set_changes_the_state_and_merges_fields_without_losing_the_rest(self):
        mid = self.s.chat_add("bot", "videos", {"identity": {"name": "S24"}, "note": "x"}, state="running")
        self.s.chat_set(mid, "done", results=[1])
        message = self.s.chat_get(mid)
        self.assertEqual((message["state"], message["body"]), ("done", {"identity": {"name": "S24"}, "note": "x", "results": [1]}))
        self.s.chat_set(mid, note="y")
        self.assertEqual((self.s.chat_get(mid)["state"], self.s.chat_get(mid)["body"]["note"]), ("done", "y"))

    def test_unknown_roles_kinds_states_and_messages_are_refused(self):
        for args in (("owner", "say", {}), ("user", "poem", {}), ("user", "say", {}, "stuck")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.s.chat_add(*args)
        with self.assertRaises(ValueError):
            self.s.chat_get(999)
        with self.assertRaises(ValueError):
            self.s.chat_set(999, "done")

    def test_the_product_in_question_is_the_latest_finished_product_answer(self):
        self.assertIsNone(self.s.chat_product())
        self.s.chat_add("bot", "product", {"identity": {"name": "old"}})
        newest = self.s.chat_add("bot", "product", {"identity": {"name": "new"}})
        self.s.chat_add("bot", "product", {"identity": {"name": "unfinished"}}, state="running")
        self.s.chat_add("bot", "videos", {})
        self.assertEqual(self.s.chat_product()["id"], newest)

    def test_only_a_few_answers_may_be_unfinished_at_once(self):
        for _ in range(3):
            self.s.chat_add("bot", "videos", {}, state="running")
        with self.assertRaises(ValueError):
            self.s.chat_add("bot", "videos", {}, state="pending")
        self.s.chat_add("bot", "note", {"text": "finished messages are not limited"})

    def test_a_message_and_its_answer_are_kept_together_or_not_at_all(self):
        mid = self.s.chat_ask("main", {"text": "S24"}, "product", {})
        thread = self.s.chat_thread()
        self.assertEqual([(m["role"], m["kind"], m["state"]) for m in thread], [("user", "say", "done"), ("bot", "product", "running")])
        self.assertEqual(thread[1]["id"], mid)
        for _ in range(2):
            self.s.chat_ask("main", {"text": "more"}, "product", {})
        with self.assertRaises(ValueError):
            self.s.chat_ask("main", {"text": "one too many"}, "product", {})
        self.assertNotIn("one too many", [m["body"].get("text") for m in self.s.chat_thread()])

    def test_old_messages_are_dropped_beyond_the_limit(self):
        from trendvn_worker.store import chat

        ids = [self.s.chat_add("user", "say", {"text": str(i)}) for i in range(chat.KEEP + 5)]
        thread = self.s.chat_thread(limit=1000)
        self.assertEqual(len(thread), chat.KEEP)
        self.assertEqual(thread[0]["id"], ids[5])

    def test_after_a_restart_unfinished_answers_become_errors_and_downloads_wait_to_be_picked_again(self):
        mid = self.s.chat_add("bot", "videos", {"results": []}, state="running")
        done = self.s.chat_add("bot", "note", {"text": "ok"})
        self.job("a1", "candidate", search_id=str(mid), search_account="main", source_file=None)
        self.s.chat_recover()
        self.assertEqual(self.s.chat_get(mid)["state"], "error")
        self.assertIn("gián đoạn", self.s.chat_get(mid)["body"]["error"])
        self.assertEqual(self.s.chat_get(done)["state"], "done")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='a1'").fetchone()[0], "search_selected")


class VideoPickTests(StoreCase):
    def answer(self, results=None, account="main"):
        name = (self.s.account(account) or {}).get("username")
        body = {"identity": {"name": "Samsung S24"}, "account_username": name, "results": results if results is not None else [result()]}
        return self.s.chat_add("bot", "videos", body, state="done", account=account)

    def test_the_pick_needs_the_owners_confirmation_and_is_idempotent(self):
        mid = self.answer()
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890")
        jid = self.s.videos_select(mid, "1234567890", True)
        self.assertEqual(jid, self.s.videos_select(mid, "1234567890", True))
        with self.s.connect() as db:
            row = db.execute("SELECT state,search_id,search_account,country FROM jobs WHERE id=?", (jid,)).fetchone()
        self.assertEqual(tuple(row), ("search_selected", str(mid), "main", "US"))

    def test_a_video_already_picked_by_another_answer_is_not_taken_again(self):
        self.s.videos_select(self.answer(), "1234567890", True)
        with self.assertRaises(ValueError):
            self.s.videos_select(self.answer(), "1234567890", True)

    def test_a_video_of_another_product_cannot_be_picked(self):
        mid = self.answer([result(level="different")])
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890", True)

    def test_an_unfinished_or_foreign_message_cannot_be_picked_from(self):
        name = self.s.account("main")["username"]
        running = self.s.chat_add("bot", "videos", {"results": [result()], "account_username": name}, state="running", account="main")
        said = self.s.chat_add("user", "say", {"results": [result()], "account_username": name}, account="main")
        for mid in (running, said):
            with self.assertRaises(ValueError):
                self.s.videos_select(mid, "1234567890", True)

    def test_the_pick_does_not_follow_a_changed_account(self):
        mid = self.answer()
        jid = self.s.videos_select(mid, "1234567890", True)
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET username='replacement' WHERE id='main'")
            db.execute("UPDATE jobs SET state='ready',output_file='/d/a.mp4' WHERE id=?", (jid,))
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890", True)
        with self.assertRaises(ValueError):
            self.s.publish_peek(jid)

    def test_download_is_claimed_once_and_kept_from_the_regular_collector(self):
        jid = self.s.videos_select(self.answer(), "1234567890", True)
        claimed = self.s.videos_media_ready(jid)
        self.assertEqual((claimed["account"], claimed["item"]["source_id"]), ("main", "1234567890"))
        self.assertEqual(self.s.candidates_without_media(), [])
        with self.assertRaises(ValueError):
            self.s.videos_media_ready(jid)

    def test_the_same_id_on_two_sources_needs_the_platform_and_gets_the_right_country(self):
        items = [
            result(platform="douyin", url="https://www.douyin.com/video/1234567890"),
            result(platform="tiktok"),
        ]
        mid = self.answer(items)
        with self.assertRaises(ValueError):
            self.s.videos_select(mid, "1234567890", True)
        jid = self.s.videos_select(mid, "1234567890", True, "douyin")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT country FROM jobs WHERE id=?", (jid,)).fetchone()[0], "CN")
        self.assertEqual(self.s.videos_media_ready(jid)["item"]["platform"], "douyin")

    def test_a_regular_collection_cannot_move_a_picked_video_to_another_account(self):
        jid = self.s.videos_select(self.answer(), "1234567890", True)
        report = {
            "platform": "tiktok", "stream": "test", "observed_at": 100,
            "items": [{
                "source_id": "1234567890", "url": "https://www.tiktok.com/@a/video/1234567890", "country": "US", "title": "Samsung S24",
                "rank": 1, "views": 1000, "evidence_url": "https://www.tiktok.com/search?q=S24", "meta": {"score": 900},
            }],
        }  # fmt: skip
        self.s.ingest(report, now=100)
        with self.s.connect() as db:
            meta = json.loads(db.execute("SELECT meta FROM jobs WHERE id=?", (jid,)).fetchone()[0])
        self.assertEqual(meta["search_username"], self.s.account("main")["username"])


class RankTests(StoreCase):
    def test_candidates_are_ordered_by_match_with_other_products_last_and_bad_ids_dropped(self):
        mid = self.s.chat_add(
            "bot", "videos", {"identity": {"name": "Samsung Galaxy S24", "model": "S24"}}, state="running", account="main"
        )
        items = [
            {
                "source_id": "2222222222",
                "platform": "tiktok",
                "url": "https://www.tiktok.com/@a/video/2222222222",
                "title": "Samsung Galaxy S23",
            },
            {
                "source_id": "1111111111",
                "platform": "tiktok",
                "url": "https://www.tiktok.com/@a/video/1111111111",
                "title": "Samsung Galaxy S24 review",
            },
            {"source_id": "../x", "platform": "tiktok", "url": "https://www.tiktok.com/@a/video/3333333333", "title": "Samsung Galaxy S24"},
        ]
        ranked = self.s.videos_rank(mid, items)
        self.assertEqual([r["source_id"] for r in ranked], ["1111111111", "2222222222"])
        self.assertEqual(ranked[1]["match"]["level"], "different")


class CommissionTests(StoreCase):
    FOUND = {
        "input": "https://vt.tiktok.com/ZSabc/",
        "product_id": "1729384756102938475",
        "title": "Bàn phím",
        "markers": {"share_creator_id": "7"},
        "tracked": True,
    }

    def test_a_confirmed_link_is_kept_per_account_and_product_and_its_marks_become_the_reference(self):
        self.assertEqual(self.s.commission_known("main"), [])
        self.s.commission_save("main", self.FOUND)
        self.assertEqual(self.s.commission_known("main"), [{"share_creator_id": "7"}])
        saved = self.s.commission_get("main", self.FOUND["product_id"])
        self.assertEqual((saved["url"], saved["title"]), (self.FOUND["input"], "Bàn phím"))
        self.assertIsNone(self.s.commission_get("main", "999999"))

    def test_a_second_confirmation_for_the_same_product_replaces_the_first(self):
        self.s.commission_save("main", self.FOUND)
        self.s.commission_save("main", dict(self.FOUND, input="https://vt.tiktok.com/ZSnew/"))
        self.assertEqual([l["url"] for l in self.s.commission_list("main")], ["https://vt.tiktok.com/ZSnew/"])

    def test_a_plain_link_confirmed_by_the_owner_teaches_no_marks(self):
        self.s.commission_save("main", dict(self.FOUND, markers={}, tracked=False))
        self.assertEqual(self.s.commission_known("main"), [])

    def test_a_link_needs_an_existing_account_and_a_product(self):
        for account, found in (("nobody", self.FOUND), ("main", dict(self.FOUND, product_id=None))):
            with self.assertRaises(ValueError):
                self.s.commission_save(account, found)
