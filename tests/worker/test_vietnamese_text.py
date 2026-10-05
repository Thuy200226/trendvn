"""What the owner reads is Vietnamese: every reason and error message that can reach the dashboard has a Vietnamese text."""

import ast
import re
import unittest
from pathlib import Path

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import tasks
from trendvn_worker.ui.labels import vi_error, vi_reason

SRC = Path(__file__).resolve().parents[2] / "services" / "worker" / "src" / "trendvn_worker"
VIETNAMESE = re.compile(r"[àáạảãâăấầẩẫậắằẳẵặèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹđ]", re.I)


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
        self.assertEqual(vi_error("Tên tài khoản TikTok không hợp lệ"), "Tên tài khoản TikTok không hợp lệ")
        self.assertEqual(vi_error("something nobody wrote a text for"), "something nobody wrote a text for")
        self.assertEqual(vi_error(""), "")

    def test_a_message_that_already_has_its_vietnamese_is_never_replaced_by_a_shorter_one(self):
        """The release of a held job says what happened in Vietnamese and quotes Google's English after a colon: the English must not
        win a table lookup and swallow the sentence."""
        for text in (
            "Khóa Gemini bị Google từ chối (sai, đã thu hồi hoặc thiếu quyền). Vào Cài đặt đổi khóa rồi chạy lại: Gemini HTTP 403 (m): API key not valid",
            "Gemini đang quá tải, sẽ thử lại sau: Gemini HTTP 503 (m): high demand",
            "Hạn mức Gemini của khóa đã hết, sẽ thử lại sau: Gemini HTTP 429 (m): quota",
        ):
            self.assertEqual(vi_reason(text), text)
        self.assertIn("Gemini báo lỗi", vi_reason("Gemini HTTP 400 (m): bad"))  # the English alone is still translated

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
        self.assertIn("Giá trị không nằm", vi_error("visibility_x must be one of public, friends"))
        self.assertIn("Công tắc", vi_error("processing_enabled must be true or false"))
        self.assertNotIn("min_views.douyin", vi_error("min_views.douyin must be an integer between 0 and 1000000000"))
        self.assertIn("lượt xem", vi_error("min_views.douyin must be an integer between 0 and 1000000000").lower())

    def test_the_process_summary_has_no_english_status_words(self):
        text = tasks.summarize_process([{"status": s} for s in ("ready", "error", "blocked", "disabled", "rate_limited", "needs_review")])
        for word in ("error", "blocked", "disabled"):
            self.assertNotIn(word, text)
