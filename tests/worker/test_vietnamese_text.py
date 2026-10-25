"""What the owner reads is Vietnamese: every reason and error message that can reach the dashboard has a Vietnamese text."""

import ast
import re
import unittest
from pathlib import Path

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import tasks
from trendvn_worker.ui.labels import vi_error, vi_reason

SRC = Path(__file__).resolve().parents[2] / "services" / "worker" / "src" / "trendvn_worker"
VIETNAMESE = re.compile(
    "[\xe0\xe1\u1ea1\u1ea3\xe3\xe2\u0103\u1ea5\u1ea7\u1ea9\u1eab\u1ead\u1eaf\u1eb1\u1eb3\u1eb5\u1eb7\xe8\xe9\u1eb9\u1ebb\u1ebd\xea\u1ebf\u1ec1\u1ec3\u1ec5\u1ec7\xec\xed\u1ecb\u1ec9\u0129\xf2\xf3\u1ecd\u1ecf\xf5\xf4\u1ed1\u1ed3\u1ed5\u1ed7\u1ed9\u01a1\u1edb\u1edd\u1edf\u1ee1\u1ee3\xf9\xfa\u1ee5\u1ee7\u0169\u01b0\u1ee9\u1eeb\u1eed\u1eef\u1ef1\u1ef3\xfd\u1ef5\u1ef7\u1ef9\u0111]",
    re.I,
)


def literals(path, call="ValueError"):
    """The text of every `raise ValueError("...")` in a source file (the part before a % formatting)."""
    found = []
    for node in ast.walk(ast.parse((SRC / path).read_text())):
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and getattr(node.exc.func, "id", "") == call and node.exc.args:
            arg = node.exc.args[0]
            if isinstance(arg, ast.BinOp) and isinstance(arg.op, ast.Mod):
                arg = arg.left
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                found.append(arg.value)
    return found


class ReasonTextTests(unittest.TestCase):
    def test_every_reason_a_video_can_be_held_for_has_a_vietnamese_text(self):
        """Reasons come from the analysis checks and the processing steps; the review card shows vi_reason() of them."""
        missing = []
        for path in ("domain/analysis.py", "ai/analyzer.py", "pipeline.py"):
            for text in literals(path):
                if not VIETNAMESE.search(text) and vi_reason(text) == text:
                    missing.append((path, text))
        self.assertEqual(missing, [])

    def test_every_error_the_owner_can_get_back_from_a_form_has_a_vietnamese_text(self):
        missing = []
        for path in (
            "domain/settings.py", "domain/accounts.py", "store/queue.py", "store/base.py", "store/feedback.py", "store/accounts.py",
            "store/publishing.py", "store/health.py", "web/forms.py", "tasks.py",
        ):  # fmt: skip
            for text in literals(path):
                if not VIETNAMESE.search(text) and vi_error(text) == text:
                    missing.append((path, text))
        self.assertEqual(missing, [])

    def test_a_message_that_is_already_vietnamese_or_unknown_is_left_alone(self):
        self.assertEqual(
            vi_error("T\u00ean t\u00e0i kho\u1ea3n TikTok kh\u00f4ng h\u1ee3p l\u1ec7"),
            "T\u00ean t\u00e0i kho\u1ea3n TikTok kh\u00f4ng h\u1ee3p l\u1ec7",
        )
        self.assertEqual(vi_error("something nobody wrote a text for"), "something nobody wrote a text for")
        self.assertEqual(vi_error(""), "")

    def test_a_message_that_already_has_its_vietnamese_is_never_replaced_by_a_shorter_one(self):
        """The release of a held job says what happened in Vietnamese and quotes Google's English after a colon: the English must not
        win a table lookup and swallow the sentence."""
        for text in (
            "Kh\u00f3a Gemini b\u1ecb Google t\u1eeb ch\u1ed1i (sai, \u0111\u00e3 thu h\u1ed3i ho\u1eb7c thi\u1ebfu quy\u1ec1n). V\u00e0o C\u00e0i \u0111\u1eb7t \u0111\u1ed5i kh\u00f3a r\u1ed3i ch\u1ea1y l\u1ea1i: Gemini HTTP 403 (m): API key not valid",
            "Gemini \u0111ang qu\u00e1 t\u1ea3i, s\u1ebd th\u1eed l\u1ea1i sau: Gemini HTTP 503 (m): high demand",
            "H\u1ea1n m\u1ee9c Gemini c\u1ee7a kh\u00f3a \u0111\u00e3 h\u1ebft, s\u1ebd th\u1eed l\u1ea1i sau: Gemini HTTP 429 (m): quota",
        ):
            self.assertEqual(vi_reason(text), text)
        self.assertIn("Gemini b\u00e1o l\u1ed7i", vi_reason("Gemini HTTP 400 (m): bad"))  # the English alone is still translated

    def test_an_english_check_is_not_mistaken_for_a_setting_error(self):
        self.assertEqual(
            vi_error("Gemini HTTP 400 (m): voice must be one of the prebuilt names"),
            "Gemini HTTP 400 (m): voice must be one of the prebuilt names",
        )
        self.assertEqual(
            vi_error("The voice value must be one of the prebuilt names"), "The voice value must be one of the prebuilt names"
        )  # (anchored)
        self.assertEqual(
            vi_error("Gemini HTTP 404 (gemini-x): Invalid model name"), "Gemini HTTP 404 (gemini-x): Invalid model name"
        )  # an outside service's words
        self.assertIn("Gi\u00e1 tr\u1ecb kh\u00f4ng n\u1eb1m", vi_error("visibility_x must be one of public, friends"))
        self.assertIn("C\u00f4ng t\u1eafc", vi_error("processing_enabled must be true or false"))
        self.assertNotIn("min_views.douyin", vi_error("min_views.douyin must be an integer between 0 and 1000000000"))
        self.assertIn("l\u01b0\u1ee3t xem", vi_error("min_views.douyin must be an integer between 0 and 1000000000").lower())

    def test_the_process_summary_has_no_english_status_words(self):
        text = tasks.summarize_process([{"status": s} for s in ("ready", "error", "blocked", "disabled", "rate_limited", "needs_review")])
        for word in ("error", "blocked", "disabled"):
            self.assertNotIn(word, text)
