"""Signing in to the search channels: how a signed-in session is told apart, the owner's window, and what is reported to the worker."""

from contextlib import contextmanager
from unittest import mock

from tests.support import StoreCase
from trendvn_agent import channels

ACCOUNT = {"id": "main", "username": "creator"}


def cookie(name, domain=".douyin.com", value="x"):
    return {"name": name, "domain": domain, "value": value}


class SessionTests(StoreCase):
    def test_a_douyin_guest_has_none_of_the_sign_in_cookies_and_a_signed_in_visitor_has_one(self):
        guest = [cookie(n) for n in ("__ac_nonce", "__ac_referer", "__ac_signature", "s_v_web_id", "ttwid", "odin_tt", "uid_tt")]
        self.assertFalse(channels.signed_in("douyin", guest))  # uid_tt can belong to a device, not a person: it is no sign-in
        for name in channels.SESSION_COOKIES["douyin"]:
            self.assertTrue(channels.signed_in("douyin", guest + [cookie(name)]), name)
        self.assertTrue(channels.signed_in("douyin", [cookie("LOGIN_STATUS", value="1")]))

    def test_an_empty_or_foreign_session_cookie_is_not_a_sign_in(self):
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", value="")]))
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", value=None)]))
        self.assertFalse(channels.signed_in("douyin", [cookie("LOGIN_STATUS", value="0")]))
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", domain=".example.com")]))
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", domain=".tiktok.com")]))  # TikTok's session is not Douyin's
        self.assertFalse(channels.signed_in("tiktok", [cookie("sessionid", ".tiktok.com", value="")]))

    def test_the_site_must_be_the_channels_own_not_a_look_alike_host(self):
        for domain in ("douyin.com.evil.com", "notdouyin.com", "evil-douyin.com", "iesdouyin.com", "douyin.com.cn", "xdouyin.com"):
            self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", domain)]), domain)
        for domain in ("tiktok.com.evil.com", "nottiktok.com", "tiktok.com.cn", "iestiktok.com"):
            self.assertFalse(channels.signed_in("tiktok", [cookie("sessionid", domain)]), domain)
        for domain in (".douyin.com", "douyin.com", "www.douyin.com", ".WWW.Douyin.com"):
            self.assertTrue(channels.signed_in("douyin", [cookie("sessionid", domain)]), domain)
        self.assertTrue(channels.signed_in("tiktok", [cookie("sessionid", ".tiktok.com")]))

    def test_tiktok_is_signed_in_by_its_own_session_cookie_only(self):
        self.assertFalse(channels.signed_in("tiktok", [cookie("sessionid", ".douyin.com"), cookie("ttwid", ".tiktok.com")]))

    def test_an_unknown_channel_is_an_error_not_douyin(self):
        with self.assertRaises(ValueError):
            channels.signed_in("myspace", [cookie("sessionid")])

    def test_each_account_has_its_own_profile_and_tiktok_shares_the_one_it_posts_with(self):
        self.assertEqual(channels.profile("tiktok", "main"), "publisher")
        self.assertEqual(channels.profile("tiktok", "pets"), "publisher-pets")
        self.assertEqual(channels.profile("douyin", "pets"), "search-cn-pets")
        for channel, account in (("myspace", "main"), ("douyin", "../x"), ("douyin", ""), ("tiktok", "A B")):
            with self.subTest(channel=channel, account=account), self.assertRaises(ValueError):
                channels.profile(channel, account)


class ScreenTests(StoreCase):
    def test_a_name_with_nothing_behind_it_is_no_screen(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as runtime, mock.patch.object(channels.sys, "platform", "linux"):
            (Path(runtime) / "wayland-0").touch()
            for env, alive in (
                ({"DISPLAY": ":77"}, False),  # no /tmp/.X11-unix/X77
                ({"DISPLAY": "garbage"}, False),
                ({}, False),
                ({"WAYLAND_DISPLAY": "wayland-0", "XDG_RUNTIME_DIR": runtime}, True),
                ({"WAYLAND_DISPLAY": "wayland-9", "XDG_RUNTIME_DIR": runtime}, False),
                ({"WAYLAND_DISPLAY": "wayland-0"}, False),
            ):
                with mock.patch.dict(channels.os.environ, env, clear=True):
                    self.assertEqual(channels.display_alive(), alive, env)

    def test_the_window_needs_the_owners_wish_and_a_screen_that_exists(self):
        for wants, alive, expected in ((True, True, True), (True, False, False), (False, True, False)):
            with (
                mock.patch.object(channels, "wants_window", return_value=wants),
                mock.patch.object(channels, "display_alive", return_value=alive),
            ):
                self.assertEqual(channels.window_ok(), expected)


class ReportTests(StoreCase):
    def test_the_state_goes_to_the_worker_and_a_worker_that_is_down_never_fails_the_caller(self):
        with mock.patch.object(channels, "worker") as worker:
            channels.report("main", "douyin", "wall")
        worker.assert_called_once()
        self.assertEqual(
            worker.call_args.args[:2], ("/api/channel/report", {"account": "main", "channel": "douyin", "state": "wall", "who": ""})
        )
        with mock.patch.object(channels, "worker", side_effect=RuntimeError("down")):
            channels.report("main", "douyin", "ok")


@contextmanager
def fake_chrome(cookies=(), pages=1, closed=False):
    ctx = mock.Mock()
    ctx.cookies.side_effect = cookies if callable(cookies) else (lambda: list(cookies))
    ctx.pages = [mock.Mock(is_closed=mock.Mock(return_value=closed)) for _ in range(pages)]
    ctx.new_page.return_value = ctx.pages[0]
    yield ctx


class CheckTests(StoreCase):
    def check(self, channel, cookies):
        with (
            mock.patch.object(channels, "chrome", return_value=fake_chrome(cookies)) as launched,
            mock.patch.object(channels, "report") as report,
        ):
            result = channels.check(ACCOUNT, channel)
        return result, launched, report

    def test_checking_reads_cookies_in_a_hidden_browser_opens_no_page_and_reports_once(self):
        result, launched, report = self.check("douyin", [cookie("sessionid")])
        self.assertEqual(result, {"logged_in": True, "channel": "douyin"})
        self.assertEqual(launched.call_args.args[0], "search-cn-main")
        self.assertTrue(launched.call_args.kwargs["headless"])
        report.assert_called_once_with("main", "douyin", "ok")

    def test_a_cookie_check_never_claims_whose_session_it_is(self):
        result, _, report = self.check("tiktok", [cookie("sessionid", ".tiktok.com")])
        self.assertTrue(result["logged_in"])
        report.assert_called_once_with("main", "tiktok", "ok")  # no handle: only the sign-in itself reads that

    def test_a_signed_out_profile_is_reported_as_out(self):
        result, _, report = self.check("tiktok", [])
        self.assertFalse(result["logged_in"])
        report.assert_called_once_with("main", "tiktok", "out")


class LoginTests(StoreCase):
    def run_login(self, channel, window=None, tiktok=None, profile_signed_in=True, **kwargs):
        """login() with the owner's window, the TikTok sign-in and the final read of the profile replaced."""
        with (
            mock.patch.object(channels, "window_ok", return_value=True),
            mock.patch.object(channels, "_douyin_window", **(window or {"return_value": None})) as douyin_window,
            mock.patch("trendvn_agent.publisher.session.login", **(tiktok or {"return_value": True})) as tiktok_login,
            mock.patch.object(channels, "read", return_value=profile_signed_in) as read,
            mock.patch.object(channels, "report") as report,
        ):
            result = channels.login(kwargs.pop("account", ACCOUNT), channel, **kwargs)
        return result, douyin_window, tiktok_login, read, report

    def test_without_a_screen_there_is_no_window_to_sign_in_with_and_each_owner_is_told_where_to_go(self):
        for channel, words in (("douyin", "Hãy chạy TrendVN trên máy có màn hình"), ("tiktok", "./trendvn tiktok login")):
            with mock.patch.object(channels, "window_ok", return_value=False), self.assertRaises(ValueError) as caught:
                channels.login(ACCOUNT, channel)
            self.assertIn(words, str(caught.exception))

    def test_tiktok_uses_the_publishers_own_sign_in_expecting_this_very_account_and_then_reads_the_profile_back(self):
        result, _, login, read, report = self.run_login("tiktok", account={"id": "pets", "username": "pets_shop"}, minutes=3)
        login.assert_called_once_with(minutes=3, account="pets", expected="pets_shop")
        read.assert_called_once_with({"id": "pets", "username": "pets_shop"}, "tiktok")
        self.assertEqual((result["ok"], result["who"]), (True, "pets_shop"))
        report.assert_called_once_with("pets", "tiktok", "ok", "pets_shop")

    def test_a_tiktok_window_that_never_showed_the_right_account_says_which_account_it_wanted(self):
        result, _, _, read, report = self.run_login("tiktok", tiktok={"return_value": False})
        self.assertFalse(result["ok"])
        self.assertIn("@creator", result["reason"])
        read.assert_not_called()
        report.assert_called_once_with("main", "tiktok", "out", "")

    def test_the_douyin_window_runs_and_the_answer_is_what_the_profile_holds_afterwards(self):
        result, window, _, read, report = self.run_login("douyin")
        window.assert_called_once_with(ACCOUNT, channels.LOGIN_MINUTES)
        read.assert_called_once_with(ACCOUNT, "douyin")
        self.assertTrue(result["ok"])
        report.assert_called_once_with("main", "douyin", "ok", "")

    def test_a_session_that_did_not_survive_the_window_closing_is_not_a_sign_in(self):
        for channel in ("douyin", "tiktok"):
            result, _, _, _, report = self.run_login(channel, profile_signed_in=False)
            self.assertFalse(result["ok"], channel)
            self.assertIn("Đăng nhập", result["reason"])
            self.assertEqual(report.call_args.args[2], "out")

    def test_a_window_that_dies_or_a_page_that_will_not_load_is_a_friendly_failure_and_is_reported(self):
        for channel, kwargs in (
            ("douyin", {"window": {"side_effect": RuntimeError("Page.goto: Timeout 30000ms exceeded")}}),
            ("tiktok", {"tiktok": {"side_effect": RuntimeError("Browser.getCookies: Target closed")}}),
        ):
            result, _, _, _, report = self.run_login(channel, **kwargs)
            self.assertFalse(result["ok"], channel)
            self.assertIn("đã bị đóng hoặc không mở được trang", result["reason"])
            self.assertNotIn("Playwright", result["reason"])
            report.assert_called_once_with("main", channel, "out", "")

    def window(self, cookies, pages=1, closed=False, minutes=1):
        with (
            mock.patch.object(channels, "chrome", return_value=fake_chrome(cookies, pages, closed)) as launched,
            mock.patch.object(channels.time, "time", side_effect=lambda: next(self.clock)),
        ):
            channels._douyin_window(ACCOUNT, minutes)
        return launched

    def test_the_douyin_window_waits_until_the_session_cookie_appears_then_stops(self):
        polls = iter([[], [], [cookie("sessionid")]])
        self.clock = iter(range(0, 1000))
        launched = self.window(lambda: next(polls))
        self.assertFalse(launched.call_args.kwargs["headless"])
        self.assertEqual(launched.call_args.args[0], "search-cn-main")
        self.assertEqual(next(polls, "spent"), "spent")  # it did not keep polling after the sign-in

    def test_a_window_the_owner_closed_ends_the_wait(self):
        self.clock = iter(range(0, 1000))
        self.window([], closed=True)  # returns instead of waiting out the ten minutes

    def test_a_browser_that_dies_under_the_window_ends_the_wait_instead_of_crashing(self):
        def cookies():
            raise RuntimeError("Target closed")

        self.clock = iter(range(0, 1000))
        self.window(cookies)

    def test_with_several_tabs_closing_the_first_does_not_stop_the_wait(self):
        ctx = mock.Mock()
        first, second = mock.Mock(), mock.Mock()
        first.is_closed.return_value, second.is_closed.return_value = True, False
        ctx.pages = [first, second]
        ctx.new_page.return_value = first
        jar = iter([[], [cookie("sessionid")]])
        ctx.cookies.side_effect = lambda: next(jar)
        self.clock = iter(range(0, 1000))

        @contextmanager
        def launched(*args, **kwargs):
            yield ctx

        with (
            mock.patch.object(channels, "chrome", launched),
            mock.patch.object(channels.time, "time", side_effect=lambda: next(self.clock)),
        ):
            channels._douyin_window(ACCOUNT, 1)
        second.wait_for_timeout.assert_called()  # waited on the tab that is still open
        first.wait_for_timeout.assert_called()  # (the first one only for the page load before)
