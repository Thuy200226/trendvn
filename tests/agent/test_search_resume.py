"""Owner verification can restore one exact query without navigating while a wall is active."""

from unittest import TestCase, mock

from trendvn_agent.search_capture import Capture, wait_for_results
from trendvn_agent.search_douyin import resume_query


class ResumeQueryTests(TestCase):
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
