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
        self.s.set_caption("a", "M\u00f4 t\u1ea3 m\u1edbi #a #b #c")
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
        self.assertTrue(lint_caption("Kho\u1ea3nh kh\u1eafc th\u00fa v\u1ecb c\u1ee7a b\u00e9 #vui #haihuoc #giadinh")["ok"])
        self.assertIn(
            "N\u00ean c\u00f3 3–5 hashtag", lint_caption("Kho\u1ea3nh kh\u1eafc th\u00fa v\u1ecb c\u1ee7a b\u00e9 #vui")["issues"]
        )
        self.assertIn(
            "Qu\u00e1 nhi\u1ec1u hashtag (n\u00ean t\u1ed1i \u0111a 5)",
            lint_caption("M\u00f4 t\u1ea3 d\u00e0i \u0111\u1ee7 d\u00f9ng #a1 #b2 #c3 #d4 #e5 #f6")["issues"],
        )
        self.assertIn(
            "C\u00f3 hashtag b\u1ecb l\u1eb7p", lint_caption("M\u00f4 t\u1ea3 d\u00e0i \u0111\u1ee7 d\u00f9ng #Vui #vui #c3")["issues"]
        )
        self.assertIn("M\u00f4 t\u1ea3 qu\u00e1 ng\u1eafn", lint_caption("Hi #a1 #b2 #c3")["issues"])
        self.assertTrue(
            lint_caption("Nh\u1ea1c #nhac #xuhuong #hay v\u1edbi ti\u1ebfng Vi\u1ec7t c\u00f3 d\u1ea5u \u0111\u1ea7y \u0111\u1ee7")["tags"]
            == 3
        )

    def test_build_caption_properties(self):
        long = "M\u1ed9t m\u00f4 t\u1ea3 r\u1ea5t d\u00e0i " * 20
        c = build_caption(
            {"kind": "dialogue", "caption_vi": long, "hashtags": ["H\u00e0i", "#vui v\u1ebb", "x", "haihuoc", "haihuoc", "a" * 40]}, "t"
        )
        text = c.split(" #")[0]
        self.assertLessEqual(len(text), 110)
        self.assertFalse(text.endswith((",", ";", ":", "-")))
        tags = [t for t in c.split() if t.startswith("#")]
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(len(tags), 5)
        self.assertIn("#xuhuong", tags)
        self.assertTrue(lint_caption(c)["tags"] <= 5)
        self.assertEqual(
            build_caption({"kind": "music", "caption_vi": "Hay qu\u00e1", "hashtags": []}, "t"), "Hay qu\u00e1 #xuhuong #nhac #viral"
        )
        self.assertNotIn("##", build_caption({"caption_vi": "#a #b n\u1ed9i dung", "hashtags": ["#c"]}, "t"))

    def test_platform_names_never_become_hashtags_but_reach_tags_do(self):
        c = build_caption(
            {
                "kind": "dialogue",
                "caption_vi": "M\u1ed9t c\u00e2u m\u00f4 t\u1ea3 \u0111\u1ea7y \u0111\u1ee7",
                "hashtags": ["tiktokgiaitri", "douyinvn", "fyp", "viral", "haihuoc", "giadinh"],
            },
            "t",
        )
        tags = [x for x in c.split() if x.startswith("#")]
        # a repost gives itself away with another platform's name; reach tags (fyp, viral) are exactly what we want
        self.assertEqual(tags, ["#fyp", "#viral", "#haihuoc", "#giadinh", "#xuhuong"])

    def test_caption_with_emoji_and_diacritics_survives(self):
        self.ready("a")
        self.s.set_caption("a", "C\u01b0\u1eddi x\u1ec9u v\u1edbi c\u00f4 b\u00e9 n\u00e0y 😂😂 #h\u00e0ih\u01b0\u1edbc #vui #xuhuong")
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
