"""Automatic search restores source selection from the selected account's real saved profiles."""

from unittest import mock

from tests.support import StoreCase
from trendvn_agent import search


class SavedSearchSessionsTests(StoreCase):
    def test_only_existing_profiles_of_this_receiver_are_read(self):
        account = {"id": "pets", "username": "pets_shop"}
        with (
            mock.patch.object(search, "DATA", self.s.root),
            mock.patch.object(search, "check", return_value={"logged_in": True, "state": "ok"}) as read,
        ):
            (self.s.root / "profiles" / "search-cn-main").mkdir(parents=True)
            self.assertEqual(search._saved_sources(account, ("douyin",)), [])
            read.assert_not_called()
            (self.s.root / "profiles" / "search-cn-pets").mkdir()
            self.assertEqual(search._saved_sources(account, ("douyin",)), ["douyin"])
            read.assert_called_once_with(account, "douyin", report_result=False)

    def test_locked_profile_is_not_reported_as_signed_out(self):
        (self.s.root / "profiles" / "search-cn-main").mkdir(parents=True)
        with (
            mock.patch.object(search, "DATA", self.s.root),
            mock.patch.object(search, "check", side_effect=RuntimeError("locked")),
            mock.patch.object(search, "report") as report,
        ):
            with self.assertRaisesRegex(ValueError, "không cần đăng nhập lại"):
                search._saved_sources({"id": "main"}, ("douyin",))
            report.assert_not_called()

    def test_fresh_saved_session_can_be_used_when_cached_sources_are_empty(self):
        account = {"id": "pets", "username": "pets_shop"}
        with (
            mock.patch.object(search, "_account", return_value=account),
            mock.patch.object(search, "_saved_sources", return_value=["douyin"]) as restore,
            mock.patch.object(search, "_ask", return_value={"items": [{"source_id": "123456789", "platform": "douyin"}]}) as ask,
            mock.patch.object(search, "report") as report,
        ):
            result = search.search(
                {
                    "account": "pets",
                    "source": "auto",
                    "sources": [],
                    "restore_sessions": True,
                    "query": "ACE68",
                    "queries": {"douyin": "迈从 ACE68"},
                }
            )
            self.assertEqual(len(result["items"]), 1)
            self.assertEqual(restore.call_args.args[0], account)
            self.assertEqual(ask.call_args.args[:2], ("douyin", account))
            report.assert_called_once_with("pets", "douyin", "ok", "", expected_username="pets_shop")

    def test_explicit_source_keeps_its_existing_session_and_does_not_probe_others(self):
        with (
            mock.patch.object(search, "_account", return_value={"id": "main", "username": "creator"}),
            mock.patch.object(search, "_saved_sources") as restore,
            mock.patch.object(search, "_ask", return_value={"items": [{"source_id": "123456789"}]}),
            mock.patch.object(search, "report"),
        ):
            search.search({"account": "main", "source": "douyin", "restore_sessions": True, "query": "ACE68"})
            restore.assert_not_called()

    def test_auto_excludes_a_guest_with_stale_cookies_and_uses_the_other_sources(self):
        (self.s.root / "profiles" / "search-cn-main").mkdir(parents=True)
        (self.s.root / "profiles" / "publisher").mkdir()
        with (
            mock.patch.object(search, "DATA", self.s.root),
            mock.patch.object(search, "check", return_value={"logged_in": False, "state": "out"}),
            mock.patch.object(search, "read", return_value=True) as cookie_read,
            mock.patch.object(search, "report"),
        ):
            self.assertEqual(search._saved_sources({"id": "main", "username": "creator"}, ("douyin", "tiktok")), ["tiktok"])
            cookie_read.assert_called_once_with({"id": "main", "username": "creator"}, "tiktok")
