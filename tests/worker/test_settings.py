"""Settings validation, the single version number, prompt contracts."""

import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain import topics
from trendvn_worker.ai import prompts

ROOT = Path(__file__).resolve().parents[2]


class SettingsTests(StoreCase):
    def test_valid_patch_is_saved(self):
        self.s.update_settings({"daily_limit": 3, "post_windows": [[9, 12]], "min_views": {"tiktok": 5}, "target": "@my.account"})
        cfg = self.s.settings()
        self.assertEqual(
            (cfg["daily_limit"], cfg["post_windows"], cfg["min_views"]["tiktok"], cfg["target"]), (3, [[9, 12]], 5, "my.account")
        )
        self.assertEqual(cfg["min_views"]["kuaishou"], 1000000)  # a partial update keeps the other sources' thresholds

    def test_bad_values_rejected(self):
        for bad in (
            {"daily_limit": 0},
            {"daily_limit": 2.5},
            {"daily_limit": True},
            {"post_windows": [[14, 11]]},
            {"post_windows": [[0, 25]]},
            {"min_views": {"evil": 1}},
            {"target": "a b"},
            {"audio_confidence": 2},
            {"timezone": "x"},
            {"hb_discovery": {}},
            {"voice": "../x"},
        ):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.s.update_settings(bad)

    def test_processing_needs_key(self):
        with self.assertRaises(ValueError):
            self.s.update_settings({"processing_enabled": True})
        (Path(self.tmp.name) / "gemini.key").write_text("x" * 30)
        self.s.update_settings({"processing_enabled": True})
        self.assertTrue(self.s.settings()["processing_enabled"])


class VersionTests(unittest.TestCase):
    def test_single_version_everywhere(self):
        from trendvn_worker import version

        self.assertEqual(version.VERSION, (ROOT / "VERSION").read_text().strip())
        self.assertIn("## %s " % version.VERSION, (ROOT / "CHANGELOG.md").read_text())


class PromptTests(unittest.TestCase):
    def test_schema_matches_validator(self):
        props = prompts.ANALYSIS_SCHEMA["properties"]
        self.assertEqual(set(props["kind"]["enum"]), {"music", "dialogue", "narration", "mixed", "silent", "uncertain"})
        self.assertEqual(set(props["topic"]["enum"]), {*topics.TOPIC_IDS, "other"})
        for key in prompts.ANALYSIS_SCHEMA["required"]:
            self.assertIn(key, props)
        for word in ("UNTRUSTED", "segments", "hashtags", "sensitive", "narration_vi", "caption_vi"):
            self.assertIn(word, prompts.ANALYSIS_PROMPT)
        self.assertRegex(prompts.PROMPT_VERSION, r"^\d{4}-\d\d-\d\d\.\d+$")


if __name__ == "__main__":
    unittest.main()


class ParallelSettingTests(unittest.TestCase):
    def test_a_typo_in_the_setting_never_stops_the_worker_starting(self):
        from trendvn_worker import pipeline

        for text, expected in (
            ("2", 2),
            ("1", 1),
            ("4", 4),
            ("99", 4),
            ("0", 1),
            ("-3", 1),
            (" 3 ", 3),
            ("abc", 2),
            ("2.5", 2),
            ("1e1", 2),
            ("", 2),
        ):
            self.assertEqual(pipeline._parallel_setting(text), expected, repr(text))
