"""Several TikTok accounts: each takes its own topics and obeys its own limits; one account's trouble never blocks the others."""

import json
import time

from tests.support import StoreCase, at


class MultiAccountPublishingTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.s.update_settings({"publisher_enabled": True, "post_windows": [], "min_publish_gap": 0, "daily_limit": 5})
        self.s.update_account("main", {"topics": ["music", "comedy"]})
        self.s.add_account({"username": "meo_channel", "id": "pets", "topics": ["pets", "food"]})

    def video(self, job_id, topic, score=1, **fields):
        meta = json.dumps({"score": score})
        self.ready(job_id, topic=topic, meta=meta, **fields)

    def claim(self, **kw):
        return self.s.publish_claim(**kw)

    def finish(self, claim, outcome="published"):
        url = "https://www.tiktok.com/@%s/video/1" % claim["target"] if outcome == "published" else ""
        self.s.publish_finish(claim["id"], claim["lease"], outcome, url)

    def test_each_video_goes_to_an_account_that_takes_its_topic(self):
        self.video("song", "music")
        self.video("cat", "pets")
        first = self.claim()
        self.finish(first)
        second = self.claim()
        self.finish(second)
        routed = {first["id"]: first["account"], second["id"]: second["account"]}
        self.assertEqual(routed, {"song": "main", "cat": "pets"})
        self.assertEqual((first["target"] if first["id"] == "cat" else second["target"]), "meo_channel")

    def test_a_video_no_enabled_account_takes_is_never_picked_by_the_schedule(self):
        self.video("game", "gaming")
        self.assertEqual(self.claim()["status"], "idle")
        self.s.update_account("pets", {"topics": ["gaming"]})
        self.assertEqual(self.claim()["account"], "pets")

    def test_the_account_that_posted_longest_ago_goes_first(self):
        self.video("a", "music", score=9)
        self.video("b", "comedy", score=8)
        self.video("c", "pets", score=7)
        order = []
        for _ in range(3):
            claim = self.claim()
            order.append((claim["account"], claim["id"]))
            self.finish(claim)
            time.sleep(0.01)
        self.assertEqual({account for account, _ in order}, {"main", "pets"})
        self.assertEqual(order[0][0], "main")  # nobody had posted: the oldest-created account first
        self.assertEqual(order[1][0], "pets")  # then the one that has not posted at all
        self.assertEqual(order[2][0], "main")  # and the one that posted longest ago

    def test_limits_are_per_account(self):
        self.s.update_account("pets", {"daily_limit": 1})
        for i in range(3):
            self.video("cat%d" % i, "pets")
        self.video("song", "music")
        self.finish(self.claim())  # one of the two accounts
        self.finish(self.claim())
        claims = []
        while True:
            claim = self.claim()
            if claim["status"] != "claimed":
                break
            self.finish(claim)
            claims.append(claim["account"])
        today = {account: self.s.published_today(account=self.s.account(account)) for account in ("main", "pets")}
        self.assertEqual(today["pets"], 1)  # pets stops at its own limit of 1 although the global one is 5
        self.assertEqual(self.claim()["status"], "limit")  # pets still has cats waiting but is full; main has room and nothing to post

    def test_spacing_and_windows_are_per_account(self):
        self.s.update_account("main", {"min_gap": 3600})
        self.video("song", "music")
        self.video("song2", "music")
        self.video("cat", "pets")
        first = self.claim()
        self.finish(first)
        # main must now wait an hour, but pets (no gap of its own: the global 0) may post straight away
        second = self.claim()
        self.assertEqual((second["status"], second["account"]), ("claimed", "pets"))
        self.finish(second)
        third = self.claim()
        self.assertEqual(third["status"], "wait")
        self.assertGreater(third["retry_after"], 3000)

    def test_a_window_only_closes_the_account_that_owns_it(self):
        self.s.update_account("main", {"windows": [[19, 23]]})
        self.video("song", "music")
        self.video("cat", "pets")
        noon = self.claim(now=at(12))
        self.assertEqual(noon["account"], "pets")  # main only posts in the evening; pets has no window of its own
        self.finish(noon)
        self.assertEqual(self.claim(now=at(12))["status"], "wait")  # only main's song is left and its window is closed
        self.assertEqual(self.claim(now=at(20))["account"], "main")

    def test_an_unconfirmed_post_stops_only_its_own_account(self):
        self.video("cat", "pets")
        self.video("cat2", "pets")
        self.video("song", "music")
        stuck = self.s.publish_claim()
        self.s.publish_finish(stuck["id"], stuck["lease"], "unknown", reason="no idea")
        blocked_account = stuck["account"]
        other = self.claim()
        self.assertEqual(other["status"], "claimed")
        self.assertNotEqual(other["account"], blocked_account)

    def test_only_one_post_in_flight_at_a_time(self):
        self.video("cat", "pets")
        self.video("song", "music")
        self.claim()
        self.assertEqual(self.claim()["status"], "blocked")

    def test_manual_posting_goes_to_the_fitting_account_or_the_default_and_waives_limits(self):
        self.s.update_account("pets", {"daily_limit": 1})
        self.video("cat", "pets")
        self.video("cat2", "pets")
        self.video("odd", "gaming")
        first = self.claim(job_id="cat")
        self.assertEqual((first["account"], first["manual"]), ("pets", True))
        self.finish(first)
        again = self.claim(job_id="cat2")  # over the account's own limit: the owner's click wins
        self.assertEqual(again["account"], "pets")
        self.finish(again)
        misc = self.claim(job_id="odd")
        self.assertEqual(misc["account"], "main")  # nobody takes gaming: the default account
        self.assertEqual(misc["target"], self.s.default_account()["username"])

    def test_visibility_can_differ_per_account(self):
        self.s.update_account("pets", {"visibility": "friends"})
        self.video("cat", "pets")
        self.assertEqual(self.claim()["visibility"], "friends")
        self.s.publish_finish(
            "cat", self.s.conn_lease("cat") if hasattr(self.s, "conn_lease") else self._lease("cat"), "failed", reason="x"
        )
        self.video("song", "music")
        self.assertEqual(self.claim(job_id="song")["visibility"], self.s.settings()["visibility"])

    def _lease(self, job_id):
        with self.s.connect() as db:
            return db.execute("SELECT publish_lease FROM jobs WHERE id=?", (job_id,)).fetchone()[0]

    def test_videos_made_before_topics_existed_go_to_any_account(self):
        self.video("old", None)
        self.assertEqual(self.claim()["status"], "claimed")

    def test_disabled_accounts_do_not_post_and_the_claim_names_the_account_for_the_agent(self):
        self.video("cat", "pets")
        self.s.update_account("pets", {"enabled": False})
        self.assertEqual(self.claim()["status"], "idle")
        self.s.update_account("pets", {"enabled": True})
        claim = self.claim()
        self.assertEqual((claim["account"], claim["target"]), ("pets", "meo_channel"))
        row = self.s.account("pets")
        self.assertEqual(row["username"], "meo_channel")
        with self.s.connect() as db:
            stored = db.execute("SELECT account,target FROM jobs WHERE id='cat'").fetchone()
        self.assertEqual(tuple(stored), ("pets", "meo_channel"))

    def test_peek_shows_the_account_without_changing_anything(self):
        self.video("cat", "pets")
        peek = self.s.publish_peek()
        self.assertEqual((peek["account"], peek["target"]), ("pets", "meo_channel"))
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='cat'").fetchone()[0], "ready")

    def test_old_published_posts_without_an_account_count_for_the_default_account(self):
        self.job("old", "published", published_at=time.time(), updated=time.time())
        default = self.s.default_account()
        self.assertEqual(self.s.published_today(account=default), 1)
        self.assertEqual(self.s.published_today(account=self.s.account("pets")), 0)
        self.assertEqual(self.s.published_today(), 1)


class BrokenAccountTests(StoreCase):
    """An account that cannot post (not signed in, failing) must not starve the others or burn the videos."""

    def setUp(self):
        super().setUp()
        self.s.update_settings({"publisher_enabled": True, "post_windows": [], "min_publish_gap": 0, "daily_limit": 5})
        self.s.update_account("main", {"topics": ["pets"]})
        self.s.add_account({"username": "newch", "id": "newch", "topics": ["pets"]})

    def video(self, job_id, score=1, topic="pets"):
        self.ready(job_id, topic=topic, meta=json.dumps({"score": score}))

    def test_an_account_known_to_be_signed_out_is_skipped_until_it_is_signed_in(self):
        for i in range(4):
            self.video("v%d" % i, score=10 - i)
        self.s.set_account_login("newch", False)
        for _ in range(3):
            claim = self.s.publish_claim()
            self.assertEqual(claim["account"], "main")
            self.s.publish_finish(claim["id"], claim["lease"], "published", "https://www.tiktok.com/@u/video/1")
        self.s.set_account_login("newch", True)
        self.video("late")
        self.assertEqual(self.s.publish_claim()["account"], "newch")  # signed in now, and it has not posted yet: its turn

    def test_when_every_account_is_signed_out_the_answer_says_which(self):
        self.video("v")
        self.s.set_account_login("main", False)
        self.s.set_account_login("newch", False)
        claim = self.s.publish_claim()
        self.assertEqual(claim["status"], "blocked")
        self.assertIn("tiktok login", claim["reason"])

    def test_unknown_login_state_does_not_block(self):
        self.video("v")
        self.assertEqual(self.s.publish_claim()["status"], "claimed")  # the agent has never reported: try, it will find out

    def test_an_account_that_just_failed_waits_behind_the_others(self):
        for i in range(3):
            self.video("v%d" % i, score=10 - i)
        first = self.s.publish_claim()
        self.s.publish_finish(first["id"], first["lease"], "failed", reason="Studio changed")
        second = self.s.publish_claim()
        self.assertNotEqual(second["account"], first["account"])  # the other account is tried before the one that failed
        self.s.publish_finish(second["id"], second["lease"], "published", "https://www.tiktok.com/@u/video/1")
        third = self.s.publish_claim()  # the other account still has room, so it still goes first
        self.assertEqual(third["account"], second["account"])
        self.s.publish_finish(third["id"], third["lease"], "published", "https://www.tiktok.com/@u/video/2")
        self.s.update_account(second["account"], {"daily_limit": 2})
        self.video("again")
        self.assertEqual(self.s.publish_claim()["account"], first["account"])  # now it is full: back to the one that failed

    def test_login_reports_merge_instead_of_replacing(self):
        self.s.set_account_login("main", True)
        self.s.set_account_login("newch", False)
        self.s.heartbeat("publisher", False, {"login": {"main": False}, "text": "x"})
        login = self.s.status()["accounts"]
        self.assertEqual({a["id"]: a["logged_in"] for a in login}, {"main": False, "newch": False})
        self.s.heartbeat("publisher", True, {"login": {"newch": True}})
        self.assertEqual({a["id"]: a["logged_in"] for a in self.s.status()["accounts"]}, {"main": False, "newch": True})
        with self.assertRaises(ValueError):
            self.s.set_account_login("ghost", True)

    def test_an_account_deleted_a_moment_ago_never_gets_a_post(self):
        self.video("v", topic="pets")
        stale = self.s.accounts(enabled_only=True)
        self.s.delete_account("newch")
        self.s.accounts = lambda enabled_only=False: stale  # a copy read before the deletion
        claim = self.s.publish_claim()
        self.assertEqual(claim["account"], "main")

    def test_videos_deep_in_the_queue_are_still_found_for_an_account(self):
        for i in range(120):
            self.ready("other%d" % i, topic="gaming", meta=json.dumps({"score": 100 + i}))
        self.video("mine", score=1)
        self.assertEqual(self.s.publish_claim()["id"], "mine")


class BacklogAndLegacyTests(StoreCase):
    def test_rendered_videos_nobody_takes_do_not_count_against_the_collector(self):
        self.s.update_account("main", {"topics": ["pets"]})
        self.ready("ok", topic="pets")
        self.ready("old", topic=None)
        for i in range(3):
            self.ready("stuck%d" % i, topic="gaming")
        self.job("q", "queued")
        status = self.s.status()
        self.assertEqual(status["counts"]["ready"], 5)
        self.assertEqual(status["backlog"], 3)  # q + ok + old; the three gaming videos have nowhere to go

    def test_posts_from_before_accounts_belong_to_main_even_after_the_default_changes(self):
        import sqlite3

        self.job("old", "published", published_at=time.time(), updated=time.time())
        with self.s.connect() as db:
            db.execute("UPDATE jobs SET account=NULL,target=NULL")
            db.execute("PRAGMA user_version = 2")
            db.commit()
        from trendvn_worker.store import schema

        db = sqlite3.connect(self.s.db)
        schema.migrate(db)
        db.commit()
        db.close()
        with self.s.connect() as db:
            self.assertEqual(
                tuple(db.execute("SELECT account,target FROM jobs WHERE id='old'").fetchone()), ("main", self.s.account("main")["username"])
            )
        self.s.add_account({"username": "second", "topics": ["food"]})
        self.s.update_account("main", {"enabled": False})
        self.assertEqual(self.s.published_today(account=self.s.account("second")), 0)
        self.assertEqual(self.s.published_today(account=self.s.account("main")), 1)

    def test_a_clashing_default_name_leaves_the_other_settings_untouched(self):
        self.s.add_account({"username": "taken", "topics": ["food"]})
        before = self.s.settings()["daily_limit"]
        with self.assertRaisesRegex(ValueError, "đã có"):
            self.s.update_settings({"daily_limit": before + 1, "target": "taken"})
        self.assertEqual(self.s.settings()["daily_limit"], before)


class DashboardAgreesWithTheWorkerTests(StoreCase):
    """The account the card names must be the account the button really uses."""

    def test_destination_matches_the_manual_claim_for_every_case(self):
        from trendvn_worker.ui.view import View

        self.s.update_settings({"publisher_enabled": True, "post_windows": [], "min_publish_gap": 0, "daily_limit": 9})
        self.s.update_account("main", {"topics": ["music"]})
        self.s.add_account({"username": "meo", "id": "pets", "topics": ["pets"]})
        self.s.add_account({"username": "both", "id": "both", "topics": ["pets", "music"]})
        for topic in ("music", "pets", "gaming", "other", None):
            for already in (0, 1):
                self.ready("job-%s-%d" % (topic, already), topic=topic, meta="{}")
        # make one account busier today so "the fewest posts" matters
        busy = self.s.publish_claim(job_id="job-pets-1")
        self.s.publish_finish(busy["id"], busy["lease"], "published", "https://www.tiktok.com/@u/video/1")
        for topic in ("music", "pets", "gaming", "other", None):
            view = View(dict(self.s.dashboard_data(), ready=[]), "csrf")
            shown = view.destination(topic)
            claim = self.s.publish_claim(job_id="job-%s-0" % topic)
            self.assertEqual(shown["id"], claim["account"], topic)
            self.s.publish_finish(claim["id"], claim["lease"], "failed", reason="x")  # leave the posts-today counts as they were

    def test_a_topic_nobody_takes_is_called_out_on_the_card_and_goes_to_the_default_account(self):
        from trendvn_worker.ui.cards import _destination_line
        from trendvn_worker.ui.view import View

        self.s.update_account("main", {"topics": ["music"]})
        self.s.add_account({"username": "meo", "id": "pets", "topics": ["pets"]})
        view = View(dict(self.s.dashboard_data(), ready=[]), "csrf")
        line = _destination_line(view, {"topic": "gaming"})
        self.assertIn("chưa có tài khoản nào nhận", line)
        self.assertIn("@" + self.s.default_account()["username"], line)
        self.assertIn("lịch tự động đăng lên", _destination_line(view, {"topic": "pets"}))
        both = View(dict(self.s.dashboard_data(), ready=[]), "csrf")
        self.s.update_account("main", {"topics": ["pets"]})
        shared = _destination_line(View(dict(self.s.dashboard_data(), ready=[]), "csrf"), {"topic": "pets"})
        self.assertIn("chọn một trong", shared)
        self.assertIn("@meo", shared)
        del both


class LoginFlagTests(StoreCase):
    def test_a_disabled_or_deleted_accounts_old_flag_does_not_make_the_publisher_look_broken(self):
        self.s.add_account({"username": "second", "id": "second", "topics": ["food"]})
        self.s.set_account_login("main", True)
        self.s.set_account_login("second", False)
        self.assertEqual(self.s.status()["publisher"], "error")
        self.s.update_account("second", {"enabled": False})
        self.s.set_account_login("main", True)
        self.assertEqual(self.s.status()["publisher"], "connected")
        self.s.update_account("second", {"enabled": True})
        self.s.delete_account("second")
        self.s.set_account_login("main", True)
        self.assertEqual(self.s.status()["publisher"], "connected")

    def test_manual_posting_avoids_an_account_known_to_be_signed_out(self):
        self.s.update_settings({"publisher_enabled": True})
        self.s.update_account("main", {"topics": ["pets"]})
        self.s.add_account({"username": "second", "id": "second", "topics": ["pets"]})
        self.s.set_account_login("main", False)
        self.ready("v", topic="pets", meta="{}")
        self.assertEqual(self.s.publish_claim(job_id="v")["account"], "second")

    def test_the_backlog_is_never_negative(self):
        self.s.update_account("main", {"topics": ["pets"]})
        self.ready("g1", topic="gaming")
        self.ready("g2", topic="gaming")
        self.assertEqual(self.s._backlog({"ready": 0}, ["pets"]), 0)  # counts read a moment earlier than the query can disagree
        self.assertEqual(self.s._backlog({"ready": 2}, ["pets"]), 0)
        self.assertEqual(self.s._backlog({"ready": 3, "queued": 1}, ["pets"]), 2)
