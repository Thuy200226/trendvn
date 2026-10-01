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

    def test_route_preview_for_the_dashboard(self):
        self.assertEqual(self.s.route_preview("pets")["id"], "pets")
        self.assertIsNone(self.s.route_preview("gaming"))
        self.assertEqual(self.s.route_preview(None)["id"], "main")  # no topic recorded: the first account
