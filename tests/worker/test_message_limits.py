"""Text from outside (an error in the address, a journal entry, a failed task) is bounded before any pattern looks at it: a long line must
never be able to keep the server busy."""

import time
import unittest
from urllib.parse import quote

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.ui.labels import TEXT_LIMIT, vi_error
from trendvn_worker.ui.messages import FALLBACK, user_message
from trendvn_worker.web.handler import ERR_SHOWN

HOSTILE = (
    "x" * 60000,
    "select " * 9000,
    "update " * 14000,
    "a " * 30000,
    "{ " * 20000,
    "must be an integer between " * 3000,
    "w" * 100 + " must be an integer" * 4000,
)


def took(function, *args):
    started = time.perf_counter()
    result = function(*args)
    return time.perf_counter() - started, result


class BoundedTextTests(unittest.TestCase):
    def test_a_huge_line_is_answered_in_milliseconds_not_seconds(self):
        for text in HOSTILE:
            for failed in (False, True):
                seconds, result = took(user_message, text, failed)
                self.assertLess(seconds, 0.2, text[:20])
                self.assertLessEqual(len(result), 450)
            self.assertLess(took(vi_error, text)[0], 0.2, text[:20])

    def test_ordinary_messages_are_unchanged_by_the_bound(self):
        for text, failed, expected in (
            ("Gemini HTTP 503 (gemini-2.5-flash): busy", True, "Gemini đang bận. Video được giữ trong hàng chờ để thử lại."),
            ("Không xác nhận được: HTTPError 500 từ Studio. Bài chưa bị xóa.", True, "Không xác nhận được"),
            ("", False, ""),
            ("", True, FALLBACK),
        ):
            self.assertEqual(user_message(text, failed), expected)
        self.assertEqual(
            vi_error("daily_limit must be an integer between 1 and 10"), "Số bài tối đa mỗi ngày phải là số nguyên từ 1 đến 10"
        )

    def test_the_part_of_a_long_line_that_matters_is_still_read_when_it_comes_first(self):
        text = "Gemini 503 hết thời gian " + "x" * 50000
        self.assertEqual(user_message(text), "Gemini đang bận. Video được giữ trong hàng chờ để thử lại.")


class EachBoundHoldsOnItsOwn(unittest.TestCase):
    """The layers back each other up, so a test of the whole (milliseconds) would still pass if one of them were lost."""

    def test_a_line_is_read_only_up_to_the_limit(self):
        self.assertEqual(len(vi_error("x" * 5000)), TEXT_LIMIT)
        self.assertEqual(user_message("x" * 1500 + " Gemini 503 hết thời gian"), ("x" * 450))  # the words past the limit are never read

    def test_a_field_name_is_read_at_most_sixty_characters_long(self):
        near, far = "daily_limit must be an integer between 1 and 10", "d" * 80 + " must be an integer between 1 and 10"
        self.assertNotEqual(vi_error(near), near)
        self.assertNotIn("d" * 70, vi_error(far))  # only the last sixty characters can be taken for the field's name

    def test_a_query_is_recognised_only_when_its_words_are_close_together(self):
        self.assertEqual(user_message("SELECT a FROM t"), FALLBACK)
        far = "SELECT " + "a" * 300 + " FROM t"
        self.assertTrue(user_message(far).startswith("SELECT aaa"))

    def test_the_error_of_the_address_is_read_up_to_its_own_limit(self):
        from tests.worker.test_web import Server

        server = Server()
        try:
            for filler, shown in ((ERR_SHOWN - 40, True), (ERR_SHOWN + 40, False)):
                _, _, body = server.req("GET", "/?err=" + "d" * filler + "+Gemini+503+timeout")
                self.assertEqual("Gemini đang bận" in body.decode(), shown, filler)
        finally:
            server.stop()


class AddressErrorTests(unittest.TestCase):
    def test_a_long_error_in_the_address_cannot_hold_the_server_up(self):
        from tests.worker.test_web import Server

        server = Server()
        try:
            for size in (12000, 60000):
                started = time.perf_counter()
                code, _, body = server.req("GET", "/?err=" + "select+" * (size // 7))
                self.assertEqual(code, 200)
                self.assertLess(time.perf_counter() - started, 0.6, size)
            started = time.perf_counter()
            self.assertEqual(server.req("GET", "/health")[0], 200)
            self.assertLess(time.perf_counter() - started, 0.3)
        finally:
            server.stop()

    def test_the_flash_shows_at_most_a_short_piece_of_the_error(self):
        from tests.worker.test_web import Server

        server = Server()
        try:
            _, _, body = server.req("GET", "/?err=" + quote("Lỗi ") + "d" * 5000)
            html = body.decode()
            flash = html[html.index('class="flash') :]
            flash = flash[: flash.index("</div>")]
            self.assertLess(len(flash), 1000)
        finally:
            server.stop()


if __name__ == "__main__":
    unittest.main()
