"""Deletion reports success only after positive proof and preserves uncertainty after a click."""

import unittest
from unittest.mock import MagicMock, patch

from trendvn_agent.publisher.delete import _perform, _studio_menu, _studio_query, delete_post


class PostDeleteTests(unittest.TestCase):
    def test_studio_query_uses_one_caption_word_without_hashtags_or_invented_ids(self):
        self.assertEqual(_studio_query("Video kiểm thử TrendVN ngày 07/10/2026. #thishashtagislonger"), "TrendVN")
        self.assertLessEqual(len(_studio_query("中" * 300)), 64)

    def test_studio_menu_is_bound_to_exact_link_and_rechecks_navigation(self):
        page = MagicMock()
        page.url = "https://www.tiktok.com/tiktokstudio/content"
        post = {"url": "https://www.tiktok.com/@owner/video/1234567890", "username": "owner"}
        link = page.locator.return_value
        videos = MagicMock()
        videos.count.return_value = 1
        page.locator.side_effect = [link, videos]
        link.inner_text.return_value = "my unique caption"
        page.get_by_placeholder.return_value.input_value.return_value = "caption"
        link.count.return_value = 1
        link.is_visible.return_value = True
        row = link.locator.return_value
        row.count.return_value = 1
        row.get_by_role.return_value.count.return_value = 1
        with patch("trendvn_agent.publisher.delete._blocked"):
            same = _studio_menu(page, post)
            self.assertIn("/@owner/video/1234567890", page.locator.call_args_list[0].args[0])
            row.get_by_role.assert_called_once_with("button", name="", exact=True)
            row.get_by_role.return_value.click.assert_called_once()
            page.get_by_placeholder.return_value.press.assert_called_once_with("Enter")
            videos.count.return_value = 2  # another post/menu becomes available on the same Studio URL
            with self.assertRaisesRegex(ValueError, "đã thay đổi"):
                same()
            videos.count.return_value = 1
            page.get_by_placeholder.return_value.input_value.return_value = "different post"
            with self.assertRaisesRegex(ValueError, "đã thay đổi"):
                same()
            page.get_by_placeholder.return_value.input_value.return_value = "my unique caption"
            page.url = "https://www.tiktok.com/tiktokstudio/upload"
            with self.assertRaisesRegex(ValueError, "đã thay đổi"):
                same()

    def test_studio_ambiguous_post_link_never_opens_menu(self):
        page = MagicMock()
        page.url = "https://www.tiktok.com/tiktokstudio/content"
        page.locator.return_value.count.return_value = 2
        with patch("trendvn_agent.publisher.delete._blocked"), self.assertRaisesRegex(ValueError, "đã thay đổi"):
            _studio_menu(page, {"url": "https://www.tiktok.com/@owner/video/1234567890", "username": "owner"})
        page.locator.return_value.locator.return_value.get_by_role.assert_not_called()

    def test_navigation_during_hydration_cannot_delete_another_post(self):
        page = MagicMock()
        url = "https://www.tiktok.com/@owner/video/1234567890"
        page.url = url
        settings = page.locator.return_value
        settings.count.return_value = 1
        settings.first.wait_for.side_effect = lambda **kwargs: setattr(page, "url", "https://www.tiktok.com/@owner/video/9999999999")
        with patch("trendvn_agent.publisher.delete._blocked"), self.assertRaisesRegex(ValueError, "đúng bài"):
            _perform(page, {"url": url, "username": "owner"}, MagicMock())
        settings.click.assert_not_called()

    def test_waits_for_owned_menu_after_page_hydration(self):
        page = MagicMock()
        page.url = "https://www.tiktok.com/@owner/video/1234567890"
        settings = MagicMock()
        hydrated = []
        settings.first.wait_for.side_effect = lambda **kwargs: hydrated.append(True)
        settings.count.side_effect = lambda: 1 if hydrated else 0
        page.locator.return_value = settings
        page.get_by_role.return_value.count.return_value = 1
        page.get_by_role.return_value.get_by_role.return_value.count.return_value = 1
        with (
            patch("trendvn_agent.publisher.delete._blocked"),
            patch("trendvn_agent.publisher.delete.arm_notice") as arm,
            patch("trendvn_agent.publisher.delete.wait_notice") as wait,
        ):
            result = _perform(page, {"url": page.url, "username": "owner"}, MagicMock())
        self.assertIn("1234567890", result)
        settings.first.wait_for.assert_called_once_with(state="visible", timeout=15000)
        arm.assert_called_once_with(page)
        wait.assert_called_once_with(page)

    def run_deletion(self, behavior):
        post = {"url": "https://www.tiktok.com/@owner/video/1234567890", "account": "main", "username": "owner"}
        calls = []

        def worker(path, payload):
            calls.append((path, payload))
            return post if path.endswith("claim") else {}

        with (
            patch("trendvn_agent.publisher.delete.worker", side_effect=worker),
            patch("trendvn_agent.publisher.delete.chrome", return_value=MagicMock()),
            patch("trendvn_agent.publisher.delete._verify"),
            patch("trendvn_agent.publisher.delete.shot"),
            patch("trendvn_agent.publisher.delete._perform", side_effect=behavior),
        ):
            result = delete_post({"job_id": "a" * 32, "grant": "b" * 32})
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[-1][0], "/api/post-delete/finish")
        self.assertEqual(calls[-1][1]["outcome"], result["status"])
        return result

    def test_failure_before_any_delete_click_is_retryable(self):
        def perform(page, post, mark):
            raise ValueError("No owned menu")

        self.assertEqual(self.run_deletion(perform)["status"], "failed")

    def test_lost_confirmation_after_click_is_unknown_never_success(self):
        def perform(page, post, mark):
            mark()
            raise TimeoutError("No positive notice")

        self.assertEqual(self.run_deletion(perform)["status"], "unknown")

    def test_positive_proof_is_reported_to_worker(self):
        def perform(page, post, mark):
            mark()
            return "TikTok xác nhận đã xóa bài 1234567890"

        self.assertEqual(self.run_deletion(perform)["status"], "deleted")
