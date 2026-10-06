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
        guest = [cookie(n) for n in ("__ac_nonce", "__ac_referer", "__ac_signature", "s_v_web_id", "ttwid", "odin_tt")]
        self.assertFalse(channels.signed_in("douyin", guest))
        for name in channels.DOUYIN_SESSION:
            self.assertTrue(channels.signed_in("douyin", guest + [cookie(name)]), name)
        self.assertTrue(channels.signed_in("douyin", [cookie("LOGIN_STATUS", value="1")]))

    def test_an_empty_or_foreign_session_cookie_is_not_a_sign_in(self):
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", value="")]))
        self.assertFalse(channels.signed_in("douyin", [cookie("LOGIN_STATUS", value="0")]))
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", domain=".example.com")]))
        self.assertFalse(channels.signed_in("douyin", [cookie("sessionid", domain=".tiktok.com")]))  # TikTok's session is not Douyin's

    def test_tiktok_is_signed_in_by_its_own_session_cookie_only(self):
        self.assertTrue(channels.signed_in("tiktok", [cookie("sessionid", ".tiktok.com")]))
        self.assertFalse(channels.signed_in("tiktok", [cookie("sessionid", ".douyin.com"), cookie("ttwid", ".tiktok.com")]))

    def test_each_account_has_its_own_profile_and_tiktok_shares_the_one_it_posts_with(self):
        self.assertEqual(channels.profile("tiktok", "main"), "publisher")
        self.assertEqual(channels.profile("tiktok", "pets"), "publisher-pets")
        self.assertEqual(channels.profile("douyin", "pets"), "search-cn-pets")
        for channel, account in (("myspace", "main"), ("douyin", "../x"), ("douyin", ""), ("tiktok", "A B")):
            with self.subTest(channel=channel, account=account), self.assertRaises(ValueError):
                channels.profile(channel, account)


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
def fake_chrome(cookies=(), pages=1):
    ctx = mock.Mock()
    ctx.cookies.side_effect = cookies if callable(cookies) else (lambda: list(cookies))
    ctx.pages = [mock.Mock(is_closed=mock.Mock(return_value=False)) for _ in range(pages)]
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

    def test_checking_reads_cookies_in_a_hidden_browser_and_opens_no_page(self):
        result, launched, report = self.check("douyin", [cookie("sessionid")])
        self.assertEqual(result, {"logged_in": True, "channel": "douyin"})
        self.assertEqual(launched.call_args.args[0], "search-cn-main")
        self.assertTrue(launched.call_args.kwargs["headless"])
        report.assert_called_once_with("main", "douyin", "ok", "")

    def test_a_signed_out_profile_is_reported_as_out(self):
        result, _, report = self.check("tiktok", [])
        self.assertFalse(result["logged_in"])
        report.assert_called_once_with("main", "tiktok", "out", "")


class LoginTests(StoreCase):
    def test_without_a_screen_there_is_no_window_to_sign_in_with_and_the_owner_is_told_where_to_go(self):
        with mock.patch.object(channels, "wants_window", return_value=False), self.assertRaises(ValueError) as caught:
            channels.login(ACCOUNT, "douyin")
        self.assertIn("màn hình", str(caught.exception))

    def test_tiktok_uses_the_publishers_own_sign_in_expecting_this_very_account(self):
        with (
            mock.patch.object(channels, "wants_window", return_value=True),
            mock.patch("trendvn_agent.publisher.session.login", return_value=True) as login,
            mock.patch.object(channels, "report") as report,
        ):
            result = channels.login({"id": "pets", "username": "pets_shop"}, "tiktok", minutes=3)
        login.assert_called_once_with(minutes=3, account="pets", expected="pets_shop")
        self.assertEqual((result["ok"], result["who"]), (True, "pets_shop"))
        report.assert_called_once_with("pets", "tiktok", "ok", "pets_shop")

    def douyin(self, jar, minutes=1, pages=1):
        """Run the Douyin window; `jar` is what the browser's cookies are on each poll (a list of lists, the last one repeating)."""
        polls = iter(jar)
        last = [jar[-1]]

        def cookies():
            nonlocal last
            try:
                last = [next(polls)]
            except StopIteration:
                pass
            return last[0]

        with (
            mock.patch.object(channels, "wants_window", return_value=True),
            mock.patch.object(channels, "chrome", return_value=fake_chrome(cookies, pages)) as launched,
            mock.patch.object(channels, "report") as report,
            mock.patch.object(channels, "check", return_value={"logged_in": False}) as final,
        ):
            return channels.login(ACCOUNT, "douyin", minutes=minutes), launched, report, final

    def test_the_douyin_window_waits_until_the_session_cookie_appears_then_closes(self):
        result, launched, report, _ = self.douyin([[], [], [cookie("sessionid")]])
        self.assertTrue(result["ok"])
        self.assertFalse(launched.call_args.kwargs["headless"])
        self.assertEqual(launched.call_args.args[0], "search-cn-main")
        report.assert_called_once_with("main", "douyin", "ok", "")

    def test_a_window_closed_before_the_cookie_showed_is_asked_once_more_through_the_profile(self):
        with mock.patch.object(channels, "chrome") as launched:
            ctx = mock.Mock()
            ctx.pages = [mock.Mock(is_closed=mock.Mock(return_value=True))]
            ctx.cookies.return_value = []
            ctx.new_page.return_value = ctx.pages[0]
            launched.return_value.__enter__ = lambda self_: ctx
            launched.return_value.__exit__ = lambda *a: False
            with (
                mock.patch.object(channels, "wants_window", return_value=True),
                mock.patch.object(channels, "report") as report,
                mock.patch.object(channels, "check", return_value={"logged_in": True}) as final,
            ):
                result = channels.login(ACCOUNT, "douyin")
        final.assert_called_once_with(ACCOUNT, "douyin")
        self.assertTrue(result["ok"])
        report.assert_called_once_with("main", "douyin", "ok", "")

    def test_no_sign_in_in_time_is_reported_as_out_with_what_to_do(self):
        with mock.patch.object(channels.time, "time", side_effect=[0, 0, 1e9, 1e9, 1e9, 1e9]):
            result, _, report, final = self.douyin([[]], minutes=1)
        self.assertFalse(result["ok"])
        self.assertIn("Đăng nhập", result["reason"])
        report.assert_called_once_with("main", "douyin", "out", "")
        final.assert_called_once()

    def test_a_browser_that_dies_under_the_window_ends_the_wait_instead_of_crashing(self):
        def cookies():
            raise RuntimeError("Target closed")

        with (
            mock.patch.object(channels, "wants_window", return_value=True),
            mock.patch.object(channels, "chrome", return_value=fake_chrome(cookies)),
            mock.patch.object(channels, "report"),
            mock.patch.object(channels, "check", return_value={"logged_in": False}),
        ):
            self.assertFalse(channels.login(ACCOUNT, "douyin")["ok"])
