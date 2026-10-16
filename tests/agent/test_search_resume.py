"""Owner verification can restore one exact query without navigating while a wall is active."""

from unittest import TestCase, mock

from trendvn_agent.search_capture import Capture, wait_for_results
from trendvn_agent.search_douyin import resume_query, check
from trendvn_agent.channels import Wall


class ResumeQueryTests(TestCase):
    def test_verification_does_not_instruct_the_owner_to_sign_in_again(self):
        with mock.patch("trendvn_agent.search_douyin.blocked", return_value=True):
            with self.assertRaises(Wall) as caught:
                check(mock.Mock())
        self.assertIn("không có nghĩa là mất phiên", str(caught.exception))
        self.assertNotIn("Bấm Đăng nhập", str(caught.exception))
        self.assertEqual(caught.exception.state, "wall")

    def test_restores_exact_query_once_only_after_a_wall(self):
        query = "https://www.douyin.com/search/ACE68?type=video"
        page = mock.Mock(url="https://www.douyin.com/jingxuan")
        capture = Capture((), None)
        resume = resume_query(query, capture)
        self.assertFalse(resume(page, False))
        page.goto.assert_not_called()
        self.assertTrue(resume(page, True))
        self.assertFalse(resume(page, True))
        page.goto.assert_called_once_with(query, wait_until="domcontentloaded", timeout=45000)

    def test_does_not_reload_an_unchanged_query(self):
        url = "https://www.douyin.com/search/ACE68?type=video"
        page = mock.Mock(url=url)
        self.assertFalse(resume_query(url, Capture((), None))(page, True))
        page.goto.assert_not_called()

    def test_a_user_search_must_return_to_video_search_but_tracking_is_ignored(self):
        url = "https://www.douyin.com/search/ACE68?type=video"
        page = mock.Mock(url="https://www.douyin.com/search/ACE68?type=user")
        self.assertTrue(resume_query(url, Capture((), None))(page, True))
        page.goto.assert_called_once_with(url, wait_until="domcontentloaded", timeout=45000)
        page = mock.Mock(url=url + "&tracking=x")
        self.assertFalse(resume_query(url, Capture((), None))(page, True))
        page.goto.assert_not_called()

    def test_wait_never_calls_resume_during_captcha(self):
        page = mock.Mock()
        page.is_closed.return_value = False
        capture = Capture((), None)
        capture.seen["123"] = {"source_id": "123"}
        resume = mock.Mock(return_value=False)
        check = mock.Mock(side_effect=[ValueError("wall"), None])
        wait_for_results(page, capture, True, check, rounds=1, resume=resume)
        self.assertEqual(check.call_count, 2)
        resume.assert_called_once_with(page, True)


class LongOwnerWaitTests(TestCase):
    def test_wall_beyond_the_old_deadline_waits_for_owner_then_returns_results(self):
        page = mock.Mock()
        page.is_closed.return_value = False
        capture = Capture((), None)
        ticks = []

        def check(_page):
            ticks.append(1)
            if len(ticks) <= 400:
                raise Wall("Chờ chủ")
            capture.seen["123"] = {"source_id": "123"}

        wait_for_results(page, capture, True, check, rounds=120)
        self.assertEqual(len(ticks), 401)  # more than 13 simulated minutes, with no navigation
        page.goto.assert_not_called()

    def test_owner_closing_the_window_ends_the_wait_without_clearing_its_profile(self):
        page = mock.Mock()
        page.is_closed.side_effect = [False, False, True]
        capture = Capture((), None)
        wait_for_results(page, capture, True, mock.Mock(side_effect=Wall("wall")), rounds=1)
        self.assertEqual(page.wait_for_timeout.call_count, 2)
        page.goto.assert_not_called()

    def test_navigation_error_does_not_close_the_owners_window(self):
        from trendvn_agent.search_capture import navigate

        page = mock.Mock()
        page.goto.side_effect = RuntimeError("net::ERR_HTTP_RESPONSE_CODE_FAILURE")
        navigate(page, "https://www.douyin.com/search/ACE68", True)
        page.close.assert_not_called()
        with self.assertRaises(RuntimeError):
            navigate(page, "https://www.douyin.com/search/ACE68", False)


class AutomaticVisibleWaitTests(TestCase):
    def test_regular_visible_search_waits_through_verification_without_expiring(self):
        page = mock.Mock()
        page.is_closed.return_value = False
        capture = Capture((), None)
        checks = mock.Mock(side_effect=[Wall("wall")] * 400 + [None] * 6)
        wait_for_results(page, capture, False, checks, rounds=6, owner_window=True)
        self.assertEqual(checks.call_count, 406)
        page.goto.assert_not_called()

    def test_transient_navigation_during_owner_verification_keeps_the_window(self):
        class Error(Exception):
            __module__ = "playwright._impl._errors"

        page = mock.Mock()
        page.is_closed.return_value = False
        capture = Capture((), None)
        capture.seen["123"] = {"source_id": "123"}
        checks = mock.Mock(side_effect=[Error("navigation")] * 150 + [None])
        wait_for_results(page, capture, False, checks, rounds=1, owner_window=True)
        self.assertEqual(checks.call_count, 151)


class TransientWaitTickTests(TestCase):
    def test_navigation_error_during_the_tick_does_not_end_an_owner_search(self):
        class Error(Exception):
            __module__ = "playwright._impl._errors"

        page = mock.Mock()
        page.is_closed.return_value = False
        page.wait_for_timeout.side_effect = [Error("navigation context changed"), None]
        capture = Capture((), None)
        capture.seen["123"] = {"source_id": "123"}
        checks = mock.Mock()
        wait_for_results(page, capture, False, checks, rounds=1, owner_window=True)
        checks.assert_called_once()
        self.assertEqual(page.wait_for_timeout.call_count, 2)
        page.close.assert_not_called()
