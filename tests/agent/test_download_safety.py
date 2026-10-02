"""The agent fetches what a website tells it to: media URLs, yt-dlp, and requests from the worker. Regression tests from the security review."""

import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_agent import server
from trendvn_agent.collector import download


class MediaUrlTests(unittest.TestCase):
    def test_only_plain_https_urls_on_a_platform_cdn_pass(self):
        for good in (
            "https://v3-web.douyinvod.com/a/b.mp4?x=1&y=2",
            "https://v16m.tiktokcdn.com/path/video/tos/x/?a=1",
            "https://js2.a.yximgs.com/x",
            "https://DOUYIN.com/video/1",
        ):
            self.assertIn(".", download.cdn_host(good))
        for bad in (
            "https://evil.test\\@v3.douyinvod.com/x",  # a browser reads the backslash as a slash: it would fetch evil.test
            "https://v3.douyinvod.com@evil.test/x",
            "https://evil.test/https://v3.douyinvod.com/x",
            "https://v3.douyinvod.com:8443/x",
            "https://127.0.0.1/x",
            "https://2130706433/x",
            "https://0x7f.1/x",
            "https://[::1]/x",
            "http://v3.douyinvod.com/x",
            "https://v3.douyinvod.com/x y",
            "https://v3.douyinvod.com/x\r\nHost: evil",
            "https://douyinvod.com.evil.test/x",
            "https://evildouyinvod.com/x",
            "//v3.douyinvod.com/x",
            "",
            None,
        ):
            with self.assertRaises(ValueError, msg=repr(bad)):
                download.cdn_host(bad)


class FakeResponse:
    def __init__(self, status, location=None):
        self.status = status
        self.headers = {"location": location} if location else {}
        self.ok = 200 <= status < 300


class RedirectTests(unittest.TestCase):
    """Playwright follows 20 redirects on its own and the allowlist holds the platforms' main sites: every hop must be checked."""

    def ctx(self, answers):
        asked = []

        def get(url, **kwargs):
            asked.append((url, kwargs))
            return answers[len(asked) - 1]

        return mock.Mock(request=mock.Mock(get=get)), asked

    def test_a_redirect_to_another_host_is_never_requested(self):
        ctx, asked = self.ctx([FakeResponse(302, "https://evil.test/steal"), FakeResponse(200)])
        with self.assertRaises(ValueError):
            download.fetch_media(ctx, "https://v3.douyinvod.com/a.mp4", "https://www.douyin.com/")
        self.assertEqual([url for url, _ in asked], ["https://v3.douyinvod.com/a.mp4"])  # the second request never went out
        self.assertEqual(asked[0][1]["max_redirects"], 0)  # the browser stack is told not to follow by itself

    def test_a_redirect_between_platform_hosts_is_followed_and_relative_ones_resolve(self):
        ctx, asked = self.ctx([FakeResponse(302, "https://v26.douyinvod.com/b.mp4"), FakeResponse(301, "/c.mp4"), FakeResponse(200)])
        response = download.fetch_media(ctx, "https://v3.douyinvod.com/a.mp4", "https://www.douyin.com/")
        self.assertTrue(response.ok)
        self.assertEqual([url for url, _ in asked][-1], "https://v26.douyinvod.com/c.mp4")

    def test_loops_and_missing_destinations_stop(self):
        ctx, _ = self.ctx([FakeResponse(302, "https://v3.douyinvod.com/a.mp4")] * 10)
        with self.assertRaisesRegex(ValueError, "Too many"):
            download.fetch_media(ctx, "https://v3.douyinvod.com/a.mp4", "https://www.douyin.com/")
        ctx, _ = self.ctx([FakeResponse(302)])
        with self.assertRaisesRegex(ValueError, "without a destination"):
            download.fetch_media(ctx, "https://v3.douyinvod.com/a.mp4", "https://www.douyin.com/")

    def test_yt_dlp_does_not_copy_the_servers_date_onto_the_file(self):
        calls = []
        with mock.patch.object(download.subprocess, "run", lambda argv, **k: calls.append(argv) or mock.Mock(returncode=1)):
            with self.assertRaises(ValueError):
                download.download(
                    None, {"source_id": "x", "media": {"kind": "ytdlp", "url": "https://www.instagram.com/reel/x/"}}, "instagram"
                )
        self.assertIn("--no-mtime", calls[0])


class YtDlpTests(StoreCase):
    def test_the_proxy_goes_in_the_environment_never_on_the_command_line(self):
        secret = "socks5://user:hunter2@proxy.example:1080"
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            return mock.Mock(returncode=0, stdout=b"{}")

        with (
            mock.patch.object(download, "proxy_for", return_value={"server": "x"}),
            mock.patch.dict(download.ENV, {"TRENDVN_US_PROXY": secret}),
            mock.patch.object(download.subprocess, "run", fake_run),
        ):
            download.ytdlp_meta("https://www.instagram.com/reel/abc/")
        argv, kwargs = calls[0]
        self.assertNotIn("hunter2", " ".join(argv))
        self.assertNotIn("--proxy", argv)
        self.assertEqual(kwargs["env"]["HTTPS_PROXY"], secret)

    def test_without_a_us_proxy_the_environment_is_left_alone(self):
        with mock.patch.object(download, "proxy_for", return_value=None):
            self.assertEqual(download.ytdlp_env(), dict(os.environ))


class AgentRequestLimitsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = "t" * 40
        cls.patch = mock.patch.object(server, "TOKEN", cls.token)  # never the real installation's token
        cls.patch.start()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def post(self, path, body, length=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        if length is not None:
            headers["Content-Length"] = str(length)
        conn.request("POST", path, body=body, headers=headers)
        response = conn.getresponse()
        out = (response.status, response.read(), dict(response.getheaders()))
        conn.close()
        return out

    def test_a_huge_content_length_is_refused_before_it_is_read(self):
        self.assertEqual(self.post("/api/collect", b"{}", length=server.MAX_BODY + 1)[0], 413)

    def test_a_payload_that_is_not_an_object_is_a_400(self):
        self.assertEqual(self.post("/api/collect", json.dumps([1, 2]))[0], 400)

    def test_the_server_header_does_not_advertise_python(self):
        _, _, headers = self.post("/api/collect", json.dumps([1]))
        self.assertEqual(headers.get("Server", "").split()[0], "TrendVNAgent")
        self.assertTrue(0 < server.Handler.timeout <= 60)


if __name__ == "__main__":
    unittest.main()
