"""Owner waits preserve the window and validate deletion authority before doing anything irreversible."""

import unittest
from unittest.mock import Mock, patch

from tests import support  # noqa: F401
from trendvn_agent.owner_wait import OwnerClosed, wait
from trendvn_agent.publisher.delete import _perform, _same_post, _studio_link, delete_post
from trendvn_agent import channels


class WaitTests(unittest.TestCase):
    def test_waits_without_a_deadline_or_navigation_until_owner_finishes(self):
        page = Mock()
        page.is_closed.return_value = False
        ready = Mock(side_effect=[False] * 400 + [True])
        pulse = Mock()
        wait(page, ready, pulse)
        self.assertEqual(pulse.call_count, 401)
        page.goto.assert_not_called()
        page.close.assert_not_called()

    def test_owner_close_is_explicit_cancellation(self):
        page = Mock()
        page.is_closed.side_effect = [False, True]
        with self.assertRaises(OwnerClosed):
            wait(page, Mock(return_value=False))
        page.close.assert_not_called()

    def test_revoked_authority_stops_before_ready_or_click(self):
        page = Mock()
        page.is_closed.return_value = False
        ready = Mock()
        with self.assertRaisesRegex(ValueError, "revoked"):
            wait(page, ready, Mock(side_effect=ValueError("revoked")))
        ready.assert_not_called()

    def test_studio_navigation_interruption_waits_for_exact_post_to_appear(self):
        page = Mock(url="https://www.tiktok.com/tiktokstudio/content")
        page.is_closed.return_value = False
        page.goto.side_effect = RuntimeError("Navigation interrupted")
        link = page.locator.return_value
        link.count.side_effect = [0] * 300 + [1, 1]
        link.first.is_visible.return_value = True
        with patch("trendvn_agent.publisher.delete._blocked"):
            self.assertIs(_studio_link(page, {"url": "https://www.tiktok.com/@owner/video/1234567890"}, None), link)
        self.assertGreater(page.wait_for_timeout.call_count, 120)
        page.close.assert_not_called()
        page.goto.assert_called_once()  # no automatic refresh while the owner works

    def test_cookie_does_not_close_a_douyin_verification_window(self):
        ctx = Mock()
        ctx.cookies.return_value = [{"name": "sessionid", "value": "present", "domain": ".douyin.com"}]
        with patch("trendvn_agent.search_douyin.blocked", return_value=True):
            self.assertFalse(channels._session_ready("douyin", Mock(url="https://www.douyin.com/"), ctx))

    def test_changed_post_during_authorization_never_clicks_delete(self):
        page = Mock(url="https://www.tiktok.com/@owner/video/1234567890")
        page.is_closed.return_value = False
        remove = page.get_by_role.return_value
        remove.count.return_value = 1
        mark = Mock(side_effect=lambda: setattr(page, "url", "https://www.tiktok.com/@owner/video/9999999999"))
        with (
            patch("trendvn_agent.publisher.delete._blocked"),
            patch(
                "trendvn_agent.publisher.delete._open_menu",
                return_value=lambda: _same_post(page, {"url": "https://www.tiktok.com/@owner/video/1234567890", "username": "owner"}),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "đúng bài"):
                _perform(page, {"url": "https://www.tiktok.com/@owner/video/1234567890", "username": "owner"}, mark)
        remove.click.assert_not_called()

    def test_revoked_grant_never_reaches_a_delete_click(self):
        post = {"url": "https://www.tiktok.com/@owner/video/1234567890", "account": "main", "username": "owner"}
        click = Mock()
        calls = []

        def worker(path, payload, **kwargs):
            calls.append(path)
            if path.endswith("authorize"):
                raise ValueError("revoked")
            return post if path.endswith("claim") else {}

        def perform(page, post, mark, pulse):
            mark()
            click()

        with (
            patch("trendvn_agent.publisher.delete.worker", side_effect=worker),
            patch("trendvn_agent.publisher.delete.chrome") as chrome,
            patch("trendvn_agent.publisher.delete._verify"),
            patch("trendvn_agent.publisher.delete._perform", side_effect=perform),
            patch("trendvn_agent.publisher.delete.shot", return_value=None),
        ):
            chrome.return_value.__enter__.return_value.new_page.return_value.is_closed.return_value = False
            result = delete_post({"job_id": "a" * 32, "grant": "b" * 32})
        self.assertEqual(result["status"], "failed")
        click.assert_not_called()
        self.assertEqual(calls[-1], "/api/post-delete/finish")


class MidStepGuards(unittest.TestCase):
    def test_cookie_on_a_browser_error_or_foreign_page_is_not_a_completed_login(self):
        ctx = Mock()
        ctx.cookies.return_value = [{"name": "sessionid", "value": "present", "domain": ".instagram.com"}]
        for url in ("chrome-error://chromewebdata/", "about:blank", "https://instagram.com.evil.com/", "https://example.com/"):
            self.assertFalse(channels._session_ready("instagram", Mock(url=url), ctx))

    def test_mid_step_captcha_waits_and_never_runs_the_ready_action_while_blocked(self):
        from trendvn_agent.channels import Wall
        from trendvn_agent.publisher.delete import _wait_action

        page = Mock()
        page.is_closed.return_value = False
        ready = Mock(return_value=True)
        with patch("trendvn_agent.publisher.delete._blocked", side_effect=[Wall("verify")] * 400 + [None]):
            _wait_action(page, ready)
        self.assertEqual(page.wait_for_timeout.call_count, 400)
        ready.assert_called_once()
        page.goto.assert_not_called()

    def test_captcha_after_final_identity_check_blocks_delete_even_if_url_is_unchanged(self):
        from trendvn_agent.channels import Wall
        from trendvn_agent.publisher.delete import _open_menu

        page = Mock(url="https://www.tiktok.com/@owner/video/1234567890")
        page.locator.return_value.count.return_value = 1
        with patch("trendvn_agent.publisher.delete._blocked") as blocked:
            same = _open_menu(page, {"url": page.url, "username": "owner"})
            blocked.side_effect = Wall("verify appeared")
            with self.assertRaises(Wall):
                same()


class UnlimitedSignInTests(unittest.TestCase):
    def test_dashboard_login_waits_past_ten_minutes_and_suppresses_inner_callback(self):
        from trendvn_agent.publisher import session

        page = Mock(url="https://www.tiktok.com/login/")
        page.is_closed.return_value = False
        ctx = Mock(pages=[page])
        with (
            patch.object(session, "chrome") as chrome,
            patch.object(session, "logged_in", return_value=True),
            patch.object(session, "wrong_account", return_value=None),
            patch.object(session, "has_challenge", side_effect=[True] * 400 + [False]),
            patch.object(session, "_report") as report,
        ):
            chrome.return_value.__enter__.return_value = ctx
            self.assertTrue(session.login(None, "main", "owner", report_result=False))
        self.assertGreaterEqual(page.wait_for_timeout.call_count, 400)
        report.assert_not_called()

    def test_dashboard_channel_route_requests_no_login_deadline(self):
        from trendvn_agent import server

        account = {"id": "main", "username": "owner"}
        with (
            patch.object(server, "_channel_args", return_value=(channels, account, "tiktok")),
            patch.object(channels, "login", return_value={}) as login,
        ):
            server.channel_login({"account": "main", "channel": "tiktok"})
        login.assert_called_once_with(account, "tiktok", minutes=None, report_result=False)


class DelayedAuthorizationTests(unittest.TestCase):
    def test_revocation_during_identity_navigation_is_rechecked_before_click(self):
        post = {"url": "https://www.tiktok.com/@owner/video/1234567890", "account": "main", "username": "owner"}
        authorized, revoked = [], []
        click = Mock()
        checks = []

        def worker(path, payload, **kwargs):
            if path.endswith("authorize"):
                authorized.append(True)
                if revoked:
                    raise ValueError("revoked while verifying")
            return post if path.endswith("claim") else {}

        def verify(ctx, account):
            checks.append(True)
            if len(checks) == 2:
                revoked.append(True)  # the account lookup's page took time, while the worker invalidated the grant

        def perform(page, post, mark, pulse):
            mark()
            click()

        with (
            patch("trendvn_agent.publisher.delete.worker", side_effect=worker),
            patch("trendvn_agent.publisher.delete.chrome"),
            patch("trendvn_agent.publisher.delete._verify", side_effect=verify),
            patch("trendvn_agent.publisher.delete._perform", side_effect=perform),
            patch("trendvn_agent.publisher.delete.shot", return_value=None),
        ):
            result = delete_post({"job_id": "a" * 32, "grant": "b" * 32})
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(authorized), 2)
        click.assert_not_called()

    def test_transient_error_in_wait_itself_keeps_the_owner_window(self):
        class Error(Exception):
            __module__ = "playwright._impl._errors"

        page = Mock()
        page.is_closed.return_value = False
        page.wait_for_timeout.side_effect = [Error("navigation context changed"), None]
        ready = Mock(side_effect=[False, False, True])
        pulse = Mock()
        wait(page, ready, pulse)
        self.assertEqual(pulse.call_count, 3)
        page.close.assert_not_called()
