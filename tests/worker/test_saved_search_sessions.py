"""Login results are durable per receiving account even when the agent callback is unavailable."""

from unittest import mock

from tests.support import StoreCase
from trendvn_worker.search import runner
from trendvn_worker.store import Store


class SavedSearchSessionsTests(StoreCase):
    def asked(self, account="main", channel="douyin"):
        return self.s.chat_add(
            "bot", "login", {"channel": channel, "account_username": self.s.account(account)["username"]}, state="running", account=account
        )

    def test_successful_return_is_persisted_without_any_agent_callback(self):
        mid = self.asked()
        runner.sign_in(self.s, mid, mock.Mock(return_value={"ok": True}))
        reopened = Store(self.s.root)
        self.assertEqual(reopened.channel_states()["main"]["douyin"]["state"], "ok")
        self.assertEqual(reopened.chat_get(mid)["state"], "done")

    def test_each_receiving_account_and_source_keep_their_own_state(self):
        self.s.add_account({"id": "pets", "username": "pets_shop", "topics": ["pets"]})
        for account, channel, result in (("main", "douyin", True), ("pets", "douyin", False), ("pets", "instagram", True)):
            runner.sign_in(self.s, self.asked(account, channel), mock.Mock(return_value={"logged_in": result}), check=True)
        states = Store(self.s.root).channel_states()
        self.assertEqual(states["main"]["douyin"]["state"], "ok")
        self.assertEqual(states["pets"]["douyin"]["state"], "out")
        self.assertEqual(states["pets"]["instagram"]["state"], "ok")
        self.assertNotIn("instagram", states["main"])

    def test_network_failure_does_not_erase_a_saved_session(self):
        self.s.channel_report("main", "douyin", "ok", "source-user")
        ok, _ = runner.run(self.s, "channel_check", str(self.asked()), mock.Mock(side_effect=TimeoutError("unavailable")))
        self.assertFalse(ok)
        self.assertEqual(self.s.channel_states()["main"]["douyin"]["state"], "ok")

    def test_cookie_check_preserves_known_identity_and_wall_is_not_logout(self):
        self.s.channel_report("main", "douyin", "ok", "source-user")
        runner.sign_in(self.s, self.asked(), mock.Mock(return_value={"logged_in": True}), check=True)
        self.s.channel_report("main", "douyin", "wall")
        state = self.s.channel_states()["main"]["douyin"]
        self.assertEqual((state["state"], state["who"]), ("wall", "source-user"))
        self.s.channel_report("main", "douyin", "out")
        self.assertEqual(self.s.channel_states()["main"]["douyin"]["who"], "")

    def test_renamed_receiver_does_not_accept_a_previous_login_result(self):
        mid = self.asked()

        def response(*args):
            self.s.update_account("main", {"username": "changed_user"})
            return {"ok": True}

        ok, _ = runner.run(self.s, "channel_login", str(mid), response)
        self.assertFalse(ok)
        self.assertNotIn("douyin", self.s.channel_states().get("main", {}))

    def test_tiktok_result_for_another_identity_is_rejected(self):
        ok, _ = runner.run(
            self.s, "channel_login", str(self.asked(channel="tiktok")), mock.Mock(return_value={"ok": True, "who": "someone_else"})
        )
        self.assertFalse(ok)
        self.assertNotIn("tiktok", self.s.channel_states().get("main", {}))

    def test_callback_arriving_after_rename_cannot_write_or_enable_the_new_identity(self):
        from types import SimpleNamespace
        from trendvn_worker.web import api

        previous = self.s.account("main")["username"]
        mid = self.asked(channel="tiktok")

        def response(*args):
            self.s.update_account("main", {"username": "changed_user"})
            with self.assertRaises(ValueError):
                api.handle(
                    SimpleNamespace(store=self.s),
                    "/api/channel/report",
                    {
                        "account": "main",
                        "channel": "tiktok",
                        "state": "ok",
                        "who": previous,
                        "expected_username": previous,
                    },
                )
            return {"ok": True, "who": previous}

        ok, _ = runner.run(self.s, "channel_login", str(mid), response)
        self.assertFalse(ok)
        self.assertNotIn("tiktok", self.s.channel_states().get("main", {}))
        self.assertIsNot(self.s.login_map(self.s.settings()).get("main"), True)

    def test_wrong_tiktok_callback_is_rejected_before_it_can_write(self):
        from types import SimpleNamespace
        from trendvn_worker.web import api

        with self.assertRaises(ValueError):
            api.handle(
                SimpleNamespace(store=self.s),
                "/api/channel/report",
                {
                    "account": "main",
                    "channel": "tiktok",
                    "state": "ok",
                    "who": "someone_else",
                    "expected_username": self.s.account("main")["username"],
                },
            )
        self.assertNotIn("tiktok", self.s.channel_states().get("main", {}))
        self.assertIsNot(self.s.login_map(self.s.settings()).get("main"), True)

    def test_failure_updating_heartbeat_rolls_back_the_channel_report_too(self):
        with mock.patch.object(self.s, "_set_account_login", side_effect=RuntimeError("injected failure")):
            with self.assertRaises(RuntimeError):
                self.s.channel_report("main", "tiktok", "ok", self.s.account("main")["username"])
        self.assertNotIn("tiktok", self.s.channel_states().get("main", {}))

    def test_wall_and_unknown_are_persisted_without_claiming_logout_or_success(self):
        self.s.channel_report("main", "douyin", "ok", "owner-name")
        for state in ("wall", "unknown"):
            mid = self.asked()
            runner.sign_in(self.s, mid, mock.Mock(return_value={"logged_in": False, "state": state}), check=True)
            entry = self.s.channel_states()["main"]["douyin"]
            self.assertEqual((entry["state"], entry["who"]), (state, "owner-name"))
            self.assertEqual(self.s.chat_get(mid)["body"]["session_state"], state)
