"""Post performance, source weights and the daily summary."""

import time
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import tasks as tasks_mod
from trendvn_worker.domain.platforms import PLATFORMS

ROOT = Path(__file__).resolve().parents[2]


class FeedbackTests(StoreCase):
    def published(self, jid, platform, vid, views, age_days=3):
        self.job(
            jid,
            "published",
            platform=platform,
            publish_url="https://www.tiktok.com/@u/video/%s" % vid,
            published_at=time.time() - age_days * 86400,
        )
        self.s.record_stats([{"video_id": vid, "views": views, "likes": views // 10}])

    def test_stats_matched_by_video_id(self):
        self.published("a", "douyin", "7690000000000000001", 500)
        r = self.s.record_stats(
            [
                {"video_id": "7690000000000000001", "views": 900},
                {"video_id": "7699999999999999999", "views": 1},
                {"video_id": "zz", "views": 1},
            ]
        )
        self.assertEqual(r["matched"], 1)
        self.assertEqual(self.s.performance()[0]["views"], 900)

    def test_weights_need_evidence_then_move(self):
        self.assertEqual(self.s.platform_weights(), {p: 1.0 for p in PLATFORMS})
        for i in range(4):
            self.published("d%d" % i, "douyin", "76900000000000%05d" % i, 10000)
        for i in range(4):
            self.published("k%d" % i, "kuaishou", "76910000000000%05d" % i, 1000)
        w = self.s.platform_weights()
        self.assertGreater(w["douyin"], 1.0)
        self.assertLess(w["kuaishou"], 1.0)
        self.assertEqual(w["tiktok"], 1.0)
        self.assertTrue(0.6 <= w["kuaishou"] <= w["douyin"] <= 1.5)


class SummaryTests(unittest.TestCase):
    def test_process_summaries(self):
        self.assertIn("TẮT", tasks_mod.summarize_process([{"status": "disabled"}]))
        self.assertIn("Không có video", tasks_mod.summarize_process([{"status": "idle"}]))
        self.assertIn("2 sẵn sàng đăng", tasks_mod.summarize_process([{"status": "ready"}, {"status": "ready"}, {"status": "idle"}]))
        # two runs at once finish in any order: an idle one first must not hide the video the other processed
        self.assertIn("1 sẵn sàng đăng", tasks_mod.summarize_process([{"status": "idle"}, {"status": "ready"}]))
        self.assertIn(
            "Gemini",
            tasks_mod.summarize_process(
                [{"status": "blocked", "reason": "Gemini API key missing"}, {"status": "blocked", "reason": "Gemini API key missing"}]
            ),
        )

    def test_collect_summary_handles_skipped_and_first_scan(self):
        text = tasks_mod.summarize_collect(
            {
                "tiktok": {"status": "skipped", "reason": "Cần IP US"},
                "douyin": {"status": "ok", "summary": {"s": {"seen": 10, "qualified": 3, "baseline": True, "new": 3}}},
                "kuaishou": {"status": "error", "reason": "hết thời gian"},
            }
        )
        self.assertIn("bỏ qua", text)
        self.assertIn("lần đầu", text)
        self.assertIn("lỗi", text)


if __name__ == "__main__":
    unittest.main()
