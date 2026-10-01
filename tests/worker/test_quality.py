"""Decisions that shape the finished video: which route, how long captions stay, where burned-in subtitles are."""

import unittest

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain import route
from trendvn_worker.domain.hardsubs import MARGIN, hard_subtitle_band
from trendvn_worker.domain.readability import MAX_CPS, MAX_EXTENSION, chars_per_second, fit_reading_speed


def seg(start, end, text="x" * 10):
    return {"start": start, "end": end, "vi": text, "original": ""}


class RouteTests(unittest.TestCase):
    def test_every_kind_has_one_route_and_a_reason(self):
        table = {
            ("dialogue", True): "vietsub",
            ("mixed", True): "vietsub",
            ("narration", True): "voiceover",
            ("music", False): "original",
            ("silent", False): "original",
            ("music", True): "vietsub",  # a spoken line inside a music video is subtitled
            ("silent", True): "vietsub",
        }
        for (kind, has_segments), expected in table.items():
            chosen, reason = route.choose_route(kind, has_segments)
            self.assertEqual(chosen, expected, (kind, has_segments))
            self.assertTrue(reason)

    def test_music_keeps_the_original_sound_and_says_why(self):
        chosen, reason = route.choose_route("music", False)
        self.assertEqual(chosen, route.ORIGINAL)
        self.assertIn("giữ nguyên", reason)


class ReadabilityTests(unittest.TestCase):
    def test_a_fast_caption_borrows_the_pause_after_it(self):
        text = "x" * 34  # needs 2 s at 17 characters a second
        fitted, worst = fit_reading_speed([seg(0, 1, text), seg(5, 6)], 10)
        self.assertEqual(fitted[0]["end"], 2.0)
        self.assertEqual(worst, round(34 / 2.0, 1))

    def test_never_runs_into_the_next_caption_or_past_the_video(self):
        fitted, _ = fit_reading_speed([seg(0, 1, "x" * 60), seg(1.5, 2.5)], 2.5)
        self.assertLessEqual(fitted[0]["end"], 1.45)
        fitted, _ = fit_reading_speed([seg(8, 9, "x" * 60)], 9.4)
        self.assertEqual(fitted[0]["end"], 9.4)

    def test_extension_is_capped_and_short_captions_are_left_alone(self):
        fitted, _ = fit_reading_speed([seg(0, 0.5, "x" * 200)], 60)
        self.assertEqual(fitted[0]["end"], 0.5 + MAX_EXTENSION)
        fitted, _ = fit_reading_speed([seg(0, 3, "ngắn")], 10)
        self.assertEqual(fitted[0]["end"], 3)

    def test_input_is_not_modified_and_timing_never_shrinks(self):
        original = [seg(0, 4, "x" * 20), seg(3.99, 6)]
        fit_reading_speed(original, 10)
        self.assertEqual(original[0]["end"], 4)
        fitted, _ = fit_reading_speed(original, 10)
        self.assertGreaterEqual(fitted[0]["end"], 4)

    def test_empty_and_speed_helpers(self):
        self.assertEqual(fit_reading_speed([], 10), ([], 0.0))
        self.assertEqual(chars_per_second(seg(0, 2, "x" * 34)), MAX_CPS)
        self.assertEqual(chars_per_second(seg(1, 1)), float("inf"))


class HardSubtitleTests(unittest.TestCase):
    def band(self, **found):
        return hard_subtitle_band({"hard_subtitles": found})

    def test_a_plausible_band_gets_a_safety_margin(self):
        top, bottom = self.band(present=True, top=0.72, bottom=0.76)
        self.assertAlmostEqual(top, 0.72 - MARGIN, 3)
        self.assertAlmostEqual(bottom, 0.76 + MARGIN, 3)

    def test_the_margin_stays_inside_the_picture(self):
        self.assertEqual(self.band(present=True, top=0.0, bottom=0.05)[0], 0.0)
        self.assertEqual(self.band(present=True, top=0.95, bottom=1.0)[1], 1.0)

    def test_nothing_usable_means_no_band(self):
        for found in (
            dict(present=False, top=0.7, bottom=0.8),
            dict(present=True),  # no position
            dict(present=True, top=0.8, bottom=0.7),  # upside down
            dict(present=True, top=0.2, bottom=0.8),  # far too tall to be a subtitle
            dict(present=True, top="0.7", bottom=0.8),
            dict(present=True, top=True, bottom=0.8),
            dict(present=True, top=-0.1, bottom=0.2),
            dict(present=True, top=0.7, bottom=float("nan")),
            dict(present="yes", top=0.7, bottom=0.8),
        ):
            self.assertIsNone(self.band(**found), found)
        self.assertIsNone(hard_subtitle_band({}))
        self.assertIsNone(hard_subtitle_band({"hard_subtitles": "none"}))
