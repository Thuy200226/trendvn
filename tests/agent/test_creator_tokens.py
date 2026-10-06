"""Creator scope/token boundaries and source fallback without contacting social networks."""

import json
import time
from unittest import mock

from tests.support import StoreCase
from trendvn_agent.search import search
from trendvn_agent.search_douyin import video_items
from trendvn_agent.shop import credentials, tokens
from trendvn_agent.shop.client import Client


class CreatorTokenTests(StoreCase):
    def granted(self, **changes):
        data = dict(
            user_type=1,
            granted_scopes=["creator.affiliate.info", "creator.showcase.read", "creator.affiliate_collaboration.read"],
            access_token="test-access",
            refresh_token="test-refresh",
            open_id="creator-id",
            access_token_expire_in=3600,
        )
        data.update(changes)
        return data

    def test_creator_only_scopes_and_refresh_identity(self):
        app = {"app_key": "test-key", "app_secret": "test-secret"}
        self.assertGreater(tokens.validate(app, self.granted())["expires_at"], time.time())
        scopes = ["creator.affiliate.info", "creator.video.write", "creator.affiliate_collaboration.read"]
        tokens.validate(app, self.granted(granted_scopes=scopes))
        for change in (
            {"user_type": 0},
            {"user_type": True},
            {"granted_scopes": ["creator.video.write"]},
            {"access_token_expire_in": 0},
            {"access_token": "bad token"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                tokens.validate(app, self.granted(**change))
        with self.assertRaises(ValueError):
            tokens.validate(dict(app, open_id="other"), self.granted())

    def test_refresh_is_atomic_and_reuses_only_same_creator(self):
        app = dict(
            app_key="test-key",
            app_secret="test-secret",
            access_token="old-token",
            refresh_token="test-refresh",
            open_id="creator-id",
            expires_at=time.time() - 1,
        )
        renewed = tokens.validate(app, self.granted())
        with mock.patch.object(credentials, "RUNTIME", self.s.root), mock.patch.object(tokens, "request", return_value=renewed) as request:
            credentials.write("main", app)
            client = Client("main")
            self.assertEqual(client.credentials["access_token"], "test-access")
            self.assertEqual(credentials.read("main")["access_token"], "test-access")
        request.assert_called_once_with(app, refresh="test-refresh")

    def test_exchange_sanitizes_third_party_echo(self):
        conn = mock.Mock()
        conn.getresponse.return_value.status = 200
        conn.getresponse.return_value.read.return_value = json.dumps({"code": 100, "message": "private-secret", "data": {}}).encode()
        with mock.patch("trendvn_agent.shop.tokens.http.client.HTTPSConnection", return_value=conn), self.assertRaises(ValueError) as error:
            tokens.request({"app_key": "test-key", "app_secret": "private-secret"}, code="private-code")
        self.assertNotIn("private", str(error.exception))
        self.assertIn("/api/v2/token/get?", conn.request.call_args.args[1])


class SourceFallbackTests(StoreCase):
    def test_one_blocked_source_does_not_discard_other_results(self):
        result = {"items": [{"source_id": "1234567890", "platform": "douyin"}], "note": "Douyin"}
        payload = dict(
            account="main", query="MCHOSE ACE68", queries={"douyin": "迈从 ACE68 磁轴键盘", "tiktok": "MCHOSE ACE68"}, source="auto"
        )
        with (
            mock.patch("trendvn_agent.search._account", return_value={"id": "main", "username": "owner"}),
            mock.patch("trendvn_agent.search_douyin.search", return_value=result) as cn,
            mock.patch("trendvn_agent.search._tiktok_search", side_effect=ValueError("TikTok captcha")),
        ):
            response = search(payload)
        self.assertEqual(response["items"], result["items"])
        self.assertIn("captcha", response["note"])
        self.assertEqual(cn.call_args.args[1], "迈从 ACE68 磁轴键盘")
        with self.assertRaises(ValueError):
            search(payload, human=True)

    def test_douyin_only_accepts_actual_video_with_media_not_suggestions(self):
        item = dict(
            aweme_id="1234567890",
            aweme_type=0,
            desc="迈从 ACE68",
            video={"play_addr": {"url_list": ["https://v.douyinvod.com/video.mp4"]}, "duration": 10000},
            statistics={"digg_count": 1},
        )
        for payload in ({"aweme_list": [item]}, {"data": [{"aweme_info": item}]}):
            self.assertEqual(video_items(payload)[0]["platform"], "douyin")
        self.assertEqual(video_items({"data": [{"suggestion": "ACE68"}]}), [])
        self.assertEqual(video_items({"aweme_list": [dict(item, is_ads=True)]}), [])


class CreatorLoginTests(StoreCase):
    def test_unknown_or_wrong_actual_username_does_not_complete_login(self):
        from trendvn_agent import account_login

        ctx = mock.Mock()
        ctx.new_page.return_value.is_closed.return_value = False
        context = mock.MagicMock()
        context.__enter__.return_value = ctx
        account = {"id": "main", "username": "owner"}
        clock = iter([0, 0, 241])
        with (
            mock.patch.object(account_login, "_account", return_value=account),
            mock.patch.object(account_login, "chrome", return_value=context),
            mock.patch.object(account_login, "logged_in", return_value=True),
            mock.patch.object(account_login, "signed_in_as", return_value=None),
            mock.patch.object(account_login.time, "monotonic", side_effect=lambda: next(clock)),
            mock.patch.object(account_login, "report_login") as report,
            self.assertRaises(ValueError),
        ):
            account_login.login({"account": "main"})
        report.assert_not_called()

    def test_correct_username_is_confirmed_in_exact_profile(self):
        from trendvn_agent import account_login

        ctx = mock.Mock()
        ctx.new_page.return_value.is_closed.return_value = False
        context = mock.MagicMock()
        context.__enter__.return_value = ctx
        with (
            mock.patch.object(account_login, "_account", return_value={"id": "pets", "username": "owner"}),
            mock.patch.object(account_login, "chrome", return_value=context) as browser,
            mock.patch.object(account_login, "logged_in", return_value=True),
            mock.patch.object(account_login, "signed_in_as", return_value="OWNER"),
            mock.patch.object(account_login, "report_login") as report,
        ):
            self.assertTrue(account_login.login({"account": "pets"})["logged_in"])
        self.assertEqual(browser.call_args.args[0], "publisher-pets")
        report.assert_called_once_with("pets", True)
