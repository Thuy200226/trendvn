"""What Gemini says about a video: validation, timestamp repair, topic and sensitivity gates."""

import tempfile
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain import topics
from trendvn_worker.domain.analysis import normalize_segments, validate_analysis
from trendvn_worker.domain.captions import build_caption
from trendvn_worker.media.fingerprint import similar
from trendvn_worker.media.subtitles import subtitles

ROOT = Path(__file__).resolve().parents[2]


class AudioTests(unittest.TestCase):
    def a(self, kind="dialogue"):
        return {"kind": kind, "confidence": 0.99, "segments": [{"start": 0, "end": 2, "vi": "Xin chào Việt Nam!"}]}

    def test_music_route(self):
        self.assertEqual(validate_analysis({"kind": "music", "confidence": 0.99, "segments": []}, 10), "original")

    def test_mixed_route(self):
        self.assertEqual(validate_analysis(self.a("mixed"), 10), "vietsub")

    def test_music_with_speech_rejected(self):
        with self.assertRaises(ValueError):
            validate_analysis(self.a("music"), 10)

    def test_low_confidence_held(self):
        a = self.a()
        a["confidence"] = 0.5
        with self.assertRaises(ValueError):
            validate_analysis(a, 10)

    def test_segment_running_past_the_video_is_cut_not_rejected(self):
        a = self.a()
        validate_analysis(a, 1)
        self.assertEqual(a["segments"][0]["end"], 1)

    def test_mostly_outside_video_is_held(self):
        a = self.a()
        a["segments"] = [{"start": 50, "end": 60, "vi": "x"}, {"start": 60, "end": 70, "vi": "y"}]
        with self.assertRaises(ValueError):
            validate_analysis(a, 10)

    def test_nan_held(self):
        a = self.a()
        a["confidence"] = float("nan")
        with self.assertRaises(ValueError):
            validate_analysis(a, 10)

    def test_visual_duplicate(self):
        self.assertTrue(similar(["0" * 16] * 5, ["0" * 15 + "1"] * 5))
        self.assertFalse(similar(["0" * 16] * 5, ["f" * 16] * 5))

    def test_subtitle_injection_sanitized(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "vi.srt"
            a = self.a()
            a["segments"][0]["vi"] = "<b>Xin</b> {\\pos(0,0)}\nchào"
            subtitles(a["segments"], p)
            s = p.read_text()
            self.assertNotIn("<b>", s)
            self.assertNotIn("{", s)


class SegmentNormalisationTests(unittest.TestCase):
    """Regression for a real Gemini failure: on a 138 s video it listed 11 lines after the end and the whole video was rejected."""

    def norm(self, segs, dur=10.0):
        return normalize_segments([dict(s, vi="x") for s in segs], dur)

    def test_hallucinated_lines_past_the_end_are_dropped_and_the_rest_kept(self):
        segs = [{"start": i * 3.0, "end": i * 3.0 + 3.0} for i in range(40)]  # a real 120 s video, but Gemini kept going to 120
        out = normalize_segments([dict(s, vi="x") for s in segs], 100.0)
        self.assertEqual(len(out), 34)
        self.assertLessEqual(out[-1]["end"], 100.0)

    def test_overlaps_are_trimmed_and_order_fixed(self):
        out = self.norm([{"start": 4.0, "end": 7.0}, {"start": 0.0, "end": 4.5}])
        self.assertEqual([(s["start"], s["end"]) for s in out], [(0.0, 4.0), (4.0, 7.0)])

    def test_zero_length_and_tiny_lines_are_dropped(self):
        out = self.norm([{"start": 1.0, "end": 1.0}, {"start": 2.0, "end": 2.1}, {"start": 3.0, "end": 5.0}])
        self.assertEqual(len(out), 1)

    def test_last_line_is_cut_at_the_video_end(self):
        out = self.norm([{"start": 8.0, "end": 14.0}])
        self.assertEqual(out[0]["end"], 10.0)

    def test_unreliable_output_is_still_rejected(self):
        with self.assertRaises(ValueError):
            self.norm([{"start": 20.0, "end": 25.0}, {"start": 25.0, "end": 30.0}, {"start": 1.0, "end": 2.0}])
        for bad in ([{"start": True, "end": 2.0}], [{"start": 0, "end": float("nan")}], ["x"]):
            with self.assertRaises(ValueError):
                self.norm(bad)

    def test_validate_analysis_persists_the_repaired_segments(self):
        a = {
            "kind": "dialogue",
            "confidence": 0.99,
            "topic": "entertainment",
            "sensitive": False,
            "caption_vi": "Mô tả đủ dài",
            "segments": [
                {"start": 0.0, "end": 4.0, "vi": "a"},
                {"start": 3.5, "end": 7.0, "vi": "b"},
                {"start": 12.0, "end": 15.0, "vi": "c"},
            ],
        }
        self.assertEqual(validate_analysis(a, 10.0, strict=True), "vietsub")
        self.assertEqual([(s["start"], s["end"]) for s in a["segments"]], [(0.0, 3.5), (3.5, 7.0)])


class InventedLinesTests(unittest.TestCase):
    """From a real analysis (2026-10-02, a 53-second skit): after 11 real lines the model restarted its clock and wrote 11 more at
    1.0-2.1 seconds; sorted in, they cut the first real line short and put an invented line on screen at second 1.6."""

    REAL = [
        (0.0, 2.0, "Lời khuyên cho mọi người:"), (2.0, 4.0, "Đừng cho bạn thân biết mật khẩu nhà."), (4.0, 5.0, "Nếu không thì..."),
        (19.0, 21.0, "Lão Tất, cậu dán bao nhiêu cái rồi?"), (21.0, 24.0, "Một tờ có 18 cái, tôi dán hết đống này."),
        (25.0, 29.0, "1, 2, 3, 4... 14, 15, 16, 17, 18, 19, 22."), (30.0, 31.0, "18 nhân 22 là bao nhiêu?"),
    ]  # fmt: skip
    INVENTED = [
        (1.0, 1.0, "Tôi chịu thua luôn rồi đó."), (1.1, 1.1, "Suốt ngày lướt mạng, toàn học mấy trò này."),
        (1.2, 1.2, "Bức tranh này của tôi trông có gì đó lạ lạ?"), (1.4, 1.4, "Cứ tưởng trong tủ lạnh không còn gì nữa."),
        (1.6, 2.0, "Nó vừa nhắn bảo trong phòng vẫn còn 50-60 cái nữa."), (2.0, 2.0, "Cậu rốt cuộc đã dán bao nhiêu cái hả?"),
    ]  # fmt: skip

    def lines(self, rows):
        return [{"start": a, "end": b, "vi": text} for a, b, text in rows]

    def test_a_restarted_clock_and_its_invented_lines_are_dropped_and_the_real_ones_keep_their_time(self):
        out = normalize_segments(self.lines(self.REAL + self.INVENTED), 53.0)
        self.assertEqual([(s["start"], s["end"]) for s in out], [(a, b) for a, b, _ in self.REAL])
        self.assertEqual(out[0]["vi"], "Lời khuyên cho mọi người:")  # not cut short, nothing invented in front of or inside it

    def test_one_unreadable_line_is_dropped_even_without_a_restart(self):
        rows = [(0.0, 2.0, "Xin chào các bạn"), (3.0, 3.4, "Một câu rất dài bị nhét vào chưa đầy nửa giây"), (5.0, 7.0, "Tạm biệt nhé")]
        self.assertEqual([s["vi"] for s in normalize_segments(self.lines(rows), 10.0)], ["Xin chào các bạn", "Tạm biệt nhé"])

    def test_a_legitimate_later_group_of_lines_is_kept(self):
        """Lines grouped by speaker (each group in time order) restart the clock too, but they are real: not a degenerate tail."""
        rows = [
            (0.0, 3.0, "Người A nói câu một"),
            (10.0, 14.0, "Người A nói câu hai"),
            (2.0, 5.0, "Người B trả lời câu một"),
            (11.0, 13.0, "Người B trả lời câu hai"),
        ]
        self.assertEqual(len(normalize_segments(self.lines(rows), 20.0)), 4)

    def test_short_real_lines_are_not_mistaken_for_inventions(self):
        rows = [(0.0, 0.4, "Ừ"), (1.0, 1.4, "Được thôi"), (2.0, 2.4, "Đi nào")]  # short text in short time
        self.assertEqual(len(normalize_segments(self.lines(rows), 10.0)), 3)


class TopicTests(unittest.TestCase):
    def a(self, **kw):
        base = {"kind": "music", "confidence": 0.99, "segments": [], "topic": "music", "sensitive": False, "caption_vi": "Giai điệu hay"}
        return dict(base, **kw)

    def test_strict_requires_topic_fields(self):
        with self.assertRaises(ValueError):
            validate_analysis({"kind": "music", "confidence": 0.99, "segments": []}, 10, strict=True)
        self.assertEqual(validate_analysis(self.a(), 10, strict=True), "original")

    def test_off_topic_and_sensitive_held(self):
        with self.assertRaises(ValueError):
            validate_analysis(self.a(topic="other"), 10, strict=True)
        with self.assertRaises(ValueError):
            validate_analysis(self.a(sensitive=True), 10, strict=True)

    def test_a_topic_no_account_takes_needs_the_owner(self):
        with self.assertRaisesRegex(ValueError, "chưa có tài khoản nào nhận"):
            validate_analysis(self.a(topic="food"), 10, strict=True, accepted_topics=["music", "pets"])
        self.assertEqual(validate_analysis(self.a(topic="pets"), 10, strict=True, accepted_topics=["music", "pets"]), "original")
        self.assertEqual(validate_analysis(self.a(topic="food"), 10, strict=True), "original")  # no account list given: not checked
        self.assertEqual(validate_analysis(self.a(topic="food"), 10, strict=True, lenient=True, accepted_topics=["pets"]), "original")

    def test_the_topic_must_come_from_the_menu(self):
        with self.assertRaisesRegex(ValueError, "Topic/sensitivity"):
            validate_analysis(self.a(topic="cooking"), 10, strict=True)
        for topic in topics.TOPIC_IDS:
            self.assertEqual(validate_analysis(self.a(topic=topic), 10, strict=True), "original")

    def test_caption_never_empty_and_bounded(self):
        cap = build_caption({"kind": "dialogue", "caption_vi": "x" * 400}, "t")
        self.assertLessEqual(len(cap.split(" #")[0]), 150)
        self.assertTrue(build_caption({}, "#tag Tiêu đề gốc").startswith("Tiêu đề gốc #"))  # source hashtags are dropped, ours are appended


if __name__ == "__main__":
    unittest.main()
