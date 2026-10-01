"""Odd inputs and failures must never wedge the queue."""

import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.captions import build_caption

ROOT = Path(__file__).resolve().parents[2]


class RobustnessTests(StoreCase):
    def test_malformed_model_output_cannot_break_captions_or_the_list(self):
        for bad in (5, True, "haihuoc", {"a": 1}, [None, 7, ["x"], "ok1"]):
            c = build_caption({"kind": "dialogue", "caption_vi": "Một câu mô tả đầy đủ", "hashtags": bad}, "t")
            self.assertIn("#xuhuong", c)
        self.job("a", "ready", output_file="/d/a.mp4", output_hash="h", analysis="{not json")
        self.assertEqual(len(self.s.ready_list()), 1)

    def test_caption_line_breaks_and_unicode_are_normalised(self):
        self.ready("a")
        self.s.set_caption("a", "Dòng một  \r\nDòng hai\r\n#a1 #b2 #c3")
        self.assertEqual(self.s.ready_list()[0]["caption"], "Dòng một\nDòng hai\n#a1 #b2 #c3")
        again = self.s.ready_list()[0]["caption"]
        self.s.set_caption("a", again.replace("\n", "\r\n"))
        self.assertEqual(
            len([e for e in self.s.recent_events(50) if e["event"] == "caption_edited"]), 1
        )  # re-saving the same text is not an edit
        self.s.set_caption("a", "Vie\u0302\u0323t Nam #vie\u0302\u0323t #a2 #b3")
        self.assertIn("Việt Nam", self.s.ready_list()[0]["caption"])  # decomposed accents become normal letters

    def test_partial_settings_update_never_erases_other_thresholds(self):
        self.s.update_settings({"min_views": {"tiktok": 7}})
        self.s.update_settings({"min_likes": {"douyin": 9}})
        cfg = self.s.settings()
        self.assertEqual((cfg["min_views"]["tiktok"], cfg["min_views"]["kuaishou"], cfg["min_likes"]["douyin"]), (7, 1000000, 9))


if __name__ == "__main__":
    unittest.main()
