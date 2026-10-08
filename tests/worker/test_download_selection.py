"""Which videos a scan may download: the ones that scan saw, not the best ones ever stored; and when none can be, the owner is told why."""

import json
import time
import unittest
from types import SimpleNamespace

from tests.support import StoreCase
from trendvn_worker import tasks as tasks_mod
from trendvn_worker.store.retention import CANDIDATE_EXPIRY_DAYS
from trendvn_worker.web import api


def add(case, jid, score, **fields):
    case.job(
        jid,
        fields.pop("state", "candidate"),
        platform="douyin",
        source_id=jid,
        topic_hint="comedy",
        meta=json.dumps({"score": score}),
        **fields,
    )


class StarvationTests(StoreCase):
    def test_a_pool_of_old_high_scores_cannot_hide_the_videos_the_scan_just_saw(self):
        for number in range(120):
            add(self, "old%03d" % number, 100000 + number)
        for number in range(5):
            add(self, "new%d" % number, 1000 + number)
        everything = [j["source_id"] for j in self.s.candidates_without_media(100, "douyin")]
        self.assertEqual(len(everything), 100)
        self.assertFalse(any(sid.startswith("new") for sid in everything))  # this is how the scan used to starve
        seen = ["new%d" % n for n in range(5)]
        chosen = self.s.candidates_without_media(100, "douyin", source_ids=seen)
        self.assertEqual(sorted(j["source_id"] for j in chosen), sorted(seen))

    def test_an_empty_list_of_wanted_videos_returns_nothing_not_everything(self):
        add(self, "a1", 5)
        self.assertEqual(self.s.candidates_without_media(10, "douyin", source_ids=[]), [])

    def test_the_best_of_the_wanted_ones_come_first(self):
        for jid, score in (("a1", 10), ("a2", 900), ("a3", 50)):
            add(self, jid, score)
        self.assertEqual(
            [j["source_id"] for j in self.s.candidates_without_media(2, "douyin", source_ids=["a1", "a2", "a3"])], ["a2", "a3"]
        )

    def test_the_api_accepts_a_bounded_list_of_plain_ids_only(self):
        app = SimpleNamespace(store=self.s)
        add(self, "a1", 5)
        self.assertEqual(len(api.handle(app, "/api/media/pending", {"platform": "douyin", "source_ids": ["a1"]})["items"]), 1)
        longest = "x" * 100  # the longest id the worker itself takes in (ingest and Kuaishou allow 100)
        self.assertEqual(api.handle(app, "/api/media/pending", {"platform": "douyin", "source_ids": [longest]})["items"], [])
        for bad in ("a1", [1], ["a b"], ["x" * 101], ["ok"] * 301, {"a1": 1}, [None]):
            with self.subTest(bad=str(bad)[:30]), self.assertRaises(ValueError):
                api.handle(app, "/api/media/pending", {"platform": "douyin", "source_ids": bad})

    def test_scores_that_tie_come_out_in_one_fixed_order(self):
        for jid in ("b", "a", "c"):
            add(self, jid, 5)
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET first_seen=1")
        first = [j["source_id"] for j in self.s.candidates_without_media(2, "douyin")]
        self.assertEqual(first, [j["source_id"] for j in self.s.candidates_without_media(2, "douyin")])
        self.assertEqual(first, ["a", "b"])


class ReSightingTests(StoreCase):
    def test_seeing_a_video_again_does_not_make_its_state_look_newer(self):
        add(self, "a1", 5, state="rejected", updated=1000)
        with self.s.connect() as db:
            before = db.execute("SELECT updated,last_seen FROM jobs WHERE id='a1'").fetchone()
        self.s.ingest(
            {
                "platform": "douyin",
                "stream": "jingxuan",
                "observed_at": time.time(),
                "items": [
                    {
                        "source_id": "a1",
                        "url": "https://www.douyin.com/video/a1",
                        "country": "CN",
                        "title": "t",
                        "rank": 1,
                        "views": 9,
                        "evidence_url": "https://www.douyin.com/jingxuan",
                        "meta": {"score": 9},
                    }
                ],
            }
        )
        with self.s.connect() as db:
            after = db.execute("SELECT updated,last_seen FROM jobs WHERE id='a1'").fetchone()
        self.assertEqual(after["updated"], before["updated"])
        self.assertGreater(after["last_seen"], before["last_seen"])


class VisibleReasonTests(StoreCase):
    def test_a_scan_that_downloaded_nothing_because_the_queue_is_full_says_so(self):
        line = tasks_mod.summarize_collect(
            {
                "douyin": {
                    "status": "ok",
                    "summary": {
                        "jingxuan": {"seen": 50, "qualified": 4, "new": 2},
                        "media": {"downloaded": 0, "note": "Hàng chờ đã đủ; chưa tải thêm"},
                    },
                }
            }
        )
        self.assertIn("tải 0", line)
        self.assertIn("Hàng chờ đã đủ", line)

    def test_an_ordinary_scan_has_no_extra_words(self):
        line = tasks_mod.summarize_collect(
            {"douyin": {"status": "ok", "summary": {"jingxuan": {"seen": 5, "qualified": 2, "new": 1}, "media": {"downloaded": 1}}}}
        )
        self.assertTrue(line.endswith("tải 1"))


class FullQueueNoticeTests(StoreCase):
    def home(self):
        from trendvn_worker import ui

        data = self.s.dashboard_data()
        data.update(notify_channels=[], voice_sample=False, ready=[], tasks=[])
        return ui.render(data, "CSRF")

    def test_home_says_why_nothing_new_arrives_when_the_waiting_line_is_at_its_limit(self):
        for number in range(4):
            self.job("q%d" % number, "queued")
        html = self.home()
        self.assertIn("Hàng chờ đang đầy (4/4)", html)
        self.assertIn("hết hạn sau %d ngày" % CANDIDATE_EXPIRY_DAYS, html)  # the figure the retention rule really uses

    def test_it_stays_quiet_while_there_is_room(self):
        self.job("q0", "queued")
        self.assertNotIn("Hàng chờ đang đầy", self.home())


if __name__ == "__main__":
    unittest.main()
