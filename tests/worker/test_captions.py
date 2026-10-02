"""Captions and hashtags: building, quality checks, the owner's edits, the ready list."""

import json
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.captions import build_caption, lint_caption

ROOT = Path(__file__).resolve().parents[2]


class CaptionTests(StoreCase):
    def test_edit_validate_reset(self):
        self.ready("a")
        for bad in ("", "   ", "x" * 2201):
            with self.assertRaises(ValueError):
                self.s.set_caption("a", bad)
        self.s.set_caption("a", "Mô tả mới #a #b #c")
        self.assertTrue(self.s.ready_list()[0]["caption_edited"])
        self.s.reset_caption("a")
        self.assertFalse(self.s.ready_list()[0]["caption_edited"])

    def test_unchanged_caption_is_not_an_edit(self):
        self.ready("a")
        same = self.s.ready_list()[0]["caption"]
        self.s.set_caption("a", same)
        self.assertFalse(self.s.ready_list()[0]["caption_edited"])
        self.assertEqual(len([e for e in self.s.recent_events(50) if e["event"] == "caption_edited"]), 0)

    def test_only_unposted_videos_can_be_edited(self):
        self.job("p", "published")
        with self.assertRaises(ValueError):
            self.s.set_caption("p", "x")

    def test_caption_quality_rules(self):
        self.assertTrue(lint_caption("Khoảnh khắc thú vị của bé #vui #haihuoc #giadinh")["ok"])
        self.assertIn("Nên có 3–5 hashtag", lint_caption("Khoảnh khắc thú vị của bé #vui")["issues"])
        self.assertIn("Quá nhiều hashtag (nên tối đa 5)", lint_caption("Mô tả dài đủ dùng #a1 #b2 #c3 #d4 #e5 #f6")["issues"])
        self.assertIn("Có hashtag bị lặp", lint_caption("Mô tả dài đủ dùng #Vui #vui #c3")["issues"])
        self.assertIn("Mô tả quá ngắn", lint_caption("Hi #a1 #b2 #c3")["issues"])
        self.assertTrue(lint_caption("Nhạc #nhac #xuhuong #hay với tiếng Việt có dấu đầy đủ")["tags"] == 3)

    def test_build_caption_properties(self):
        long = "Một mô tả rất dài " * 20
        c = build_caption(
            {"kind": "dialogue", "caption_vi": long, "hashtags": ["Hài", "#vui vẻ", "x", "haihuoc", "haihuoc", "a" * 40]}, "t"
        )
        text = c.split(" #")[0]
        self.assertLessEqual(len(text), 110)
        self.assertFalse(text.endswith((",", ";", ":", "-")))
        tags = [t for t in c.split() if t.startswith("#")]
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(len(tags), 5)
        self.assertIn("#xuhuong", tags)
        self.assertTrue(lint_caption(c)["tags"] <= 5)
        self.assertEqual(build_caption({"kind": "music", "caption_vi": "Hay quá", "hashtags": []}, "t"), "Hay quá #xuhuong #nhac #viral")
        self.assertNotIn("##", build_caption({"caption_vi": "#a #b nội dung", "hashtags": ["#c"]}, "t"))

    def test_platform_names_never_become_hashtags_but_reach_tags_do(self):
        c = build_caption(
            {
                "kind": "dialogue",
                "caption_vi": "Một câu mô tả đầy đủ",
                "hashtags": ["tiktokgiaitri", "douyinvn", "fyp", "viral", "haihuoc", "giadinh"],
            },
            "t",
        )
        tags = [x for x in c.split() if x.startswith("#")]
        # a repost gives itself away with another platform's name; reach tags (fyp, viral) are exactly what we want
        self.assertEqual(tags, ["#fyp", "#viral", "#haihuoc", "#giadinh", "#xuhuong"])

    def test_caption_with_emoji_and_diacritics_survives(self):
        self.ready("a")
        self.s.set_caption("a", "Cười xỉu với cô bé này 😂😂 #hàihước #vui #xuhuong")
        self.assertIn("😂", self.s.ready_list()[0]["caption"])


class ReadyListTests(StoreCase):
    def test_ready_list_orders_by_score_and_reports_quality(self):
        self.ready("low", meta=json.dumps({"score": 1}), output_info=json.dumps({"w": 1080, "h": 1920}))
        self.ready("high", meta=json.dumps({"score": 99}))
        self.job("x", "queued")
        lst = self.s.ready_list()
        self.assertEqual([j["id"] for j in lst], ["high", "low"])
        self.assertEqual(lst[1]["info"]["w"], 1080)
        self.assertIn("ok", lst[0]["lint"])


if __name__ == "__main__":
    unittest.main()
