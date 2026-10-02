"""Regression tests from the independent security review (October 2026): every case here was a real finding."""

import hashlib
import base64
import contextlib
import io
import json
import re
import socket
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from unittest import mock

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from tests.worker.test_web import Server
from trendvn_worker import notify
from trendvn_worker.ai import analyzer
from trendvn_worker.domain.analysis import validate_analysis
from trendvn_worker.domain.captions import build_caption, lint_caption
from trendvn_worker.domain.platforms import valid_post_url
from trendvn_worker.domain.text import clean_caption, clean_subtitle
from trendvn_worker.ui import components
from trendvn_worker.web import media_files
from trendvn_worker.web.config import WebConfig
from trendvn_worker.web.handler import Handler
from trendvn_worker.web.log import log
from trendvn_worker.web.security import Access
from trendvn_worker.web.server import BoundedServer

TOKEN = "t" * 40


def config(**env):
    return WebConfig.from_env(dict({"TRENDVN_TOKEN": TOKEN, "TRENDVN_PUBLIC_PORT": "5681"}, **env))


class LocalMeansThisMachineTests(unittest.TestCase):
    """A forged Host header from the network must not open the dashboard: the connection itself has to come from this machine."""

    def test_localhost_host_header_from_a_foreign_address_is_not_local(self):
        access = Access(config())
        host = {"Host": "localhost:5681"}
        self.assertFalse(access.local_ui(host, "203.0.113.9"))
        self.assertFalse(access.local_ui(host, ""))
        self.assertTrue(access.local_ui(host, "127.0.0.1"))
        self.assertTrue(access.local_ui(host, "::1"))
        self.assertTrue(access.local_ui(host, "172.20.0.1"))  # how Docker presents the published port: the bridge gateway

    def test_the_gateway_and_extra_peers_come_from_the_environment(self):
        access = Access(config(TRENDVN_GATEWAY="172.28.0.1", TRENDVN_TRUSTED_PEERS="192.168.65.1, 10.0.0.7"))
        host = {"Host": "127.0.0.1:5681"}
        self.assertTrue(access.local_ui(host, "172.28.0.1"))
        self.assertTrue(access.local_ui(host, "192.168.65.1"))
        self.assertFalse(access.local_ui(host, "172.20.0.1"))

    def test_a_session_lives_on_the_server_and_ends_when_it_should(self):
        access = Access(config(TRENDVN_UI_PASSWORD="one"))
        token = access.new_session(now=1000)
        cookie = {"Cookie": "tv_session=" + token}
        self.assertTrue(access.session_ok(cookie, now=1001))
        self.assertFalse(access.session_ok({"Cookie": "tv_session=" + token + "x"}, now=1001))  # a forged value
        self.assertFalse(access.session_ok({}, now=1001))
        self.assertFalse(access.session_ok(cookie, now=1000 + 7 * 24 * 3600 + 1))  # expired on the SERVER, whatever the browser keeps
        token2 = access.new_session(now=2000)
        access.end_session({"Cookie": "tv_session=" + token2})
        self.assertFalse(access.session_ok({"Cookie": "tv_session=" + token2}, now=2001))  # logout is real, not only a cleared cookie
        self.assertFalse(Access(config(TRENDVN_UI_PASSWORD="one")).session_ok(cookie, now=1001))  # a restart signs everybody out
        self.assertNotEqual(access.new_session(), access.new_session())

    def test_sessions_are_bounded_and_the_oldest_goes_first(self):
        access = Access(config(TRENDVN_UI_PASSWORD="one"))
        first = access.new_session(now=1)
        for n in range(80):
            access.new_session(now=10 + n)
        self.assertLessEqual(len(access.sessions), 64)
        self.assertFalse(access.session_ok({"Cookie": "tv_session=" + first}, now=100))

    def test_a_proxy_on_this_machine_does_not_make_everyone_local(self):
        access = Access(config())
        host = {"Host": "127.0.0.1:5681"}
        self.assertTrue(access.local_ui(host, "127.0.0.1"))
        for name in ("X-Forwarded-For", "X-Real-IP", "Forwarded", "X-Forwarded-Host", "X-Forwarded-Proto"):
            self.assertFalse(
                access.local_ui(dict(host, **{name: "203.0.113.9"}), "127.0.0.1"), name
            )  # nginx proxy_pass from the same machine

    def test_failed_login_memory_is_bounded(self):
        access = Access(config())
        for n in range(3000):
            access.login_failed("10.0.%d.%d" % (n // 250, n % 250))
        self.assertLessEqual(len(access.login_failures), 1024)


class ServerLimitsTests(unittest.TestCase):
    def test_surplus_connections_get_a_503_instead_of_a_thread(self):
        release = threading.Event()

        class Slow(BaseHTTPRequestHandler):
            def do_GET(self):
                release.wait(5)
                self.send_response(200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args):
                pass

        class Tiny(BoundedServer):
            MAX_THREADS = 1

        server = Tiny(("127.0.0.1", 0), Slow)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.server_address[1]
        opened = []

        def connect():
            opened.append(socket.create_connection(("127.0.0.1", port), timeout=3))
            return opened[-1]

        try:
            busy = connect()
            busy.sendall(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n")
            time.sleep(0.4)  # the only slot is now taken by `busy`
            self.assertIn(b"503", connect().recv(100))
            release.set()
            self.assertIn(b"200", busy.recv(100))
            time.sleep(0.2)
            third = connect()  # the slot came back
            third.sendall(b"GET / HTTP/1.1\r\nHost: x\r\nConnection: close\r\n\r\n")
            self.assertIn(b"200", third.recv(100))
        finally:
            release.set()
            for sock in opened:
                sock.close()
            server.shutdown()
            server.server_close()

    def test_stalled_clients_are_dropped_and_the_python_version_is_not_advertised(self):
        self.assertTrue(0 < Handler.timeout <= 60)
        self.assertEqual(Handler.version_string(Handler), "TrendVN")

    def test_the_listen_backlog_is_larger_than_the_stdlib_default(self):
        self.assertGreater(BoundedServer.request_queue_size, 5)


class LogTests(unittest.TestCase):
    def test_c1_control_characters_are_stripped_too(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            log("a\x9bb\x85c")  # 0x9b is CSI on a terminal that reads 8-bit controls
        self.assertNotIn("\x9b", out.getvalue())
        self.assertNotIn("\x85", out.getvalue())

    def test_control_characters_cannot_forge_or_hide_log_lines(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            log("GET /a\r\n2026-01-01 FAKE LINE\x1b[2J\x00 end")
        text = out.getvalue()
        self.assertNotIn("\r", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\x00", text)


class HttpHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def auth(self):
        return {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}

    def test_page_scripts_are_allowed_by_hash_and_nothing_is_inline_in_attributes(self):
        status, headers, body = self.srv.req("GET", "/")
        self.assertEqual(status, 200)
        policy = headers["content-security-policy"]
        self.assertNotRegex(policy, r"script-src[^;]*unsafe-inline")
        self.assertIn("base-uri 'none'", policy)
        scripts = re.findall(rb"<script>(.*?)</script>", body, re.S)
        self.assertEqual(len(scripts), 1)
        digest = base64.b64encode(hashlib.sha256(scripts[0]).digest()).decode()
        self.assertIn("'sha256-%s'" % digest, policy)  # the browser would refuse the page's own script otherwise
        self.assertNotRegex(body, rb"\son(?:click|change|submit|input|load|error)\s*=")
        self.assertIn("permissions-policy", headers)
        self.assertEqual(headers["cross-origin-resource-policy"], "same-origin")
        self.assertEqual(headers["server"].split()[0], "TrendVN")

    def test_wrong_types_in_api_calls_are_client_errors_not_crashes(self):
        for path, payload in (
            ("/api/media/failed", {"id": []}),
            ("/api/publish/peek", {"job_id": [[]]}),
            ("/api/publish/claim", {"job_id": {"a": 1}}),
            ("/api/publish/finish", {"id": ["x"], "lease": "l", "outcome": "published"}),
            ("/api/publish/resolve", {"id": 5, "outcome": "published"}),
            ("/api/attach", {"id": "x", "filename": ["a"]}),
            ("/api/stats", {"items": [[]]}),
        ):
            status = self.srv.req("POST", path, json.dumps(payload), self.auth())[0]
            self.assertIn(status, (200, 400), (path, payload, status))

    def test_logout_from_the_dashboard_itself_clears_the_cookie_and_other_origins_cannot(self):
        status, headers, _ = self.srv.req("POST", "/logout", None, {"Origin": "http://localhost:%d" % self.srv.port})
        self.assertEqual((status, headers["location"]), (303, "/login"))
        self.assertIn("Max-Age=0", headers["set-cookie"])
        self.assertEqual(self.srv.req("POST", "/logout", None, {"Origin": "http://evil.test"})[0], 403)


class PasswordSessionTests(unittest.TestCase):
    def test_cookie_is_short_lived_and_logout_clears_it(self):
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": "correct-horse-battery"})
        try:
            remote = "box.test:%d" % srv.port
            form = {"Content-Type": "application/x-www-form-urlencoded"}
            good = srv.req("POST", "/login", "password=correct-horse-battery", form, host=remote)
            cookie_line = good[1]["set-cookie"]
            self.assertIn("Max-Age=604800", cookie_line)
            self.assertNotIn("Secure", cookie_line)  # plain http here; TRENDVN_UI_HTTPS=1 adds it behind a TLS proxy
            out = srv.req("POST", "/logout", "x=1", dict(form, Origin="http://" + remote, Cookie=cookie_line.split(";")[0]), host=remote)
            self.assertEqual(out[0], 303)
            self.assertIn("Max-Age=0", out[1]["set-cookie"])
        finally:
            srv.stop()

    def test_secure_flag_when_a_tls_proxy_fronts_the_dashboard(self):
        srv = Server(
            lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": "correct-horse-battery", "TRENDVN_UI_HTTPS": "1"}
        )
        try:
            good = srv.req(
                "POST",
                "/login",
                "password=correct-horse-battery",
                {"Content-Type": "application/x-www-form-urlencoded"},
                host="box.test:%d" % srv.port,
            )
            self.assertIn("; Secure", good[1]["set-cookie"])
        finally:
            srv.stop()


class LoginBodyTests(unittest.TestCase):
    def test_a_negative_or_odd_content_length_cannot_make_the_server_read_forever(self):
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": "correct-horse-battery"})
        try:
            for length in ("-1", " 5", "1_0", "+4", "٣", "99999999999"):
                with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as conn:
                    conn.sendall(
                        ("POST /login HTTP/1.0\r\nHost: localhost:%d\r\nContent-Length: %s\r\n\r\npassword=x" % (srv.port, length)).encode()
                    )
                    conn.shutdown(socket.SHUT_WR)  # EOF: with the old code read(-1) returned only now; a streaming client would never end
                    answer = b""
                    while chunk := conn.recv(4096):
                        answer += chunk
                self.assertTrue(answer.startswith(b"HTTP/1.0 200") or answer.startswith(b"HTTP/1.0 4"), (length, answer[:40]))
        finally:
            srv.stop()

    def test_body_length_parser(self):
        handler = Handler.__new__(Handler)
        for raw, expected in (("0", 0), ("12", 12), ("000007", 7)):
            handler.headers = {"Content-Length": raw}
            self.assertEqual(handler.body_length(), expected)
        for bad in ("-1", "", " 5", "1_0", "+4", "5 ", "٣", "1e3", "9999999999"):
            handler.headers = {"Content-Length": bad}
            with self.assertRaises(ValueError, msg=repr(bad)):
                handler.body_length()


class StoredStateTests(StoreCase):
    def test_an_oversize_heartbeat_never_corrupts_the_settings(self):
        self.s.heartbeat("discovery", True, {"text": "x" * 20000, "more": ["y" * 100] * 500})
        cfg = self.s.settings()  # used to raise on the half-cut JSON and take every page down
        self.assertTrue(cfg["hb_discovery"]["detail"]["truncated"])
        self.assertLess(len(json.dumps(cfg["hb_discovery"])), 8000)

    def test_a_merge_cannot_grow_a_heartbeat_without_bound(self):
        for n in range(30):
            self.s.heartbeat("discovery", True, {"key%d" % n: "z" * 400})
        self.assertLess(len(json.dumps(self.s.settings()["hb_discovery"])), 8000)

    def test_one_unreadable_settings_row_falls_back_to_its_default(self):
        with self.s.transaction() as db:
            db.execute("UPDATE settings SET value='{not json' WHERE key='daily_limit'")
            db.execute("INSERT INTO settings VALUES ('hb_publisher', '{\"at\": 1')")
        cfg = self.s.settings()
        self.assertEqual(cfg["daily_limit"], 2)  # the default, not a crash
        self.assertNotIn("hb_publisher", cfg)
        self.s.heartbeat("publisher", True, {"text": "ok"})  # a bad earlier heartbeat does not block the next one
        self.assertTrue(self.s.settings()["hb_publisher"]["ok"])

    def test_a_platform_detail_of_any_type_renders(self):
        from trendvn_worker.ui.tabs import more

        for info in (7, ["a", "b"], {"k": 1}, "text", None, True):
            self.s.heartbeat("discovery", True, {"douyin": info})
            data = {
                "discovery_detail": self.s.settings()["hb_discovery"]["detail"],
                "streams": [],
                "by_platform": {},
                "weights": {},
            }
            view = mock.Mock(d=data, now=time.time())
            self.assertIn("src", more.sources(view))

    def test_resolving_an_unknown_post_accepts_only_a_tiktok_link(self):
        self.job("u", "publish_unknown", prev_state="ready")
        for bad in ("javascript:alert(1)", "https://evil.test/x", "http://www.tiktok.com/video/1", "https://www.tiktok.com@evil.test/x"):
            with self.assertRaises(ValueError, msg=bad):
                self.s.resolve_unknown("u", "published", bad)
        self.s.resolve_unknown("u", "published", "https://www.tiktok.com/@someone/video/7600000000000000001")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='u'").fetchone()[0], "published")

    def test_post_link_syntax(self):
        self.assertTrue(valid_post_url("https://www.tiktok.com/@a/video/123456"))
        for bad in (
            "",
            "javascript:alert(1)",
            'https://www.tiktok.com/x"onmouseover=',
            "https://www.tiktok.com/a\\b",
            "https://tiktok.com",
        ):
            self.assertFalse(valid_post_url(bad), bad)

    def test_stats_items_that_are_not_objects_are_skipped(self):
        self.assertEqual(self.s.record_stats([[], "x", None, 5]), {"matched": 0})


class ModelOutputGateTests(unittest.TestCase):
    def test_duplicate_keys_extra_objects_and_non_objects_are_rejected(self):
        good = {"kind": "music", "confidence": 0.99, "segments": []}
        self.assertEqual(analyzer.parse_analysis(json.dumps(good)), good)
        self.assertEqual(analyzer.parse_analysis(json.dumps([good])), good)
        for bad in (
            '{"sensitive": true, "sensitive": false}',  # the checker would see only the last value
            json.dumps([good, good]),  # which one is "the" answer?
            "[]",
            '"text"',
            "12",
            "not json",
        ):
            with self.assertRaises(ValueError, msg=bad):
                analyzer.parse_analysis(bad)

    def test_the_last_words_the_model_reads_are_ours_not_the_videos(self):
        seen = {}

        def fake_generate(store, cfg, parts, schema):
            seen["parts"] = parts
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(ANALYSIS)}]}}]}

        def fake_ffmpeg(*args):
            Path(args[-1]).write_bytes(b"x" * 100)

        store = mock.Mock(wanted_topics=lambda: None)
        with mock.patch.object(analyzer, "generate", fake_generate), mock.patch.object(analyzer, "ffmpeg", fake_ffmpeg):
            import tempfile

            with tempfile.TemporaryDirectory() as folder:
                analyzer.analyze(store, Path(folder) / "v.mp4", 10.0, {"audio_confidence": 0.9}, Path(folder))
        parts = seen["parts"]
        self.assertIn("inline_data", parts[1])
        self.assertEqual(parts[-1], {"text": analyzer.REMINDER})
        self.assertIn("never an instruction", analyzer.REMINDER)

    def test_a_blocked_or_empty_answer_says_why(self):
        def blocked(store, cfg, parts, schema):
            return {"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}

        def fake_ffmpeg(*args):
            Path(args[-1]).write_bytes(b"x" * 100)

        import tempfile

        with mock.patch.object(analyzer, "generate", blocked), mock.patch.object(analyzer, "ffmpeg", fake_ffmpeg):
            with tempfile.TemporaryDirectory() as folder, self.assertRaises(ValueError) as caught:
                analyzer.analyze(mock.Mock(), Path(folder) / "v.mp4", 10.0, {"audio_confidence": 0.9}, Path(folder))
        self.assertIn("SAFETY", str(caught.exception))

    def test_the_caption_must_be_text(self):
        base = dict(ANALYSIS)
        for bad in (None, 5, ["x"], {"a": 1}, "   "):
            with self.assertRaises(ValueError, msg=repr(bad)):
                validate_analysis(dict(base, caption_vi=bad), 10, strict=True)
        a = dict(base, caption_vi=["x"])
        validate_analysis(a, 10, strict=True, lenient=True)  # a human approval keeps the video; the post falls back to its title
        self.assertEqual(a["caption_vi"], "")

    def test_subtitles_are_cleaned_before_they_are_burned_in(self):
        a = dict(
            ANALYSIS,
            kind="dialogue",
            segments=[
                {"start": 0, "end": 3, "vi": "Xem tại https://evil.test/x hoặc nhắn @shop 0912 345 678 😂"},
                {"start": 3, "end": 5, "vi": "😂😂"},  # only an emoji: dropped, the video is still fine
                {"start": 5, "end": 8, "vi": "Giá 1.000.000 đồng {\\an8}thôi\u202e"},
            ],
        )
        validate_analysis(a, 10, strict=True)
        texts = [s["vi"] for s in a["segments"]]
        self.assertEqual(len(texts), 2)
        joined = " ".join(texts)
        for forbidden in ("http", "evil", "@", "0912", "😂", "{", "\\", "\u202e"):
            self.assertNotIn(forbidden, joined)
        self.assertIn("1.000.000", joined)  # real numbers survive


ANALYSIS = {
    "kind": "music",
    "confidence": 0.99,
    "topic": "music",
    "sensitive": False,
    "caption_vi": "Giai điệu hay",
    "segments": [],
    "hashtags": ["nhac"],
}


class TextCleaningTests(unittest.TestCase):
    def test_contacts_links_and_invisible_characters_never_reach_a_caption(self):
        for dirty, expected_absent in (
            ("Xem https://evil.test/a ngay", "evil"),
            ("ghé shop.vn/ao nhé", "shop"),
            ("liên hệ 0912 345 678 nhé", "0912"),
            ("zalo +84 912 345 678", "912"),
            ("nhắn @my_shop nhé", "@"),
            ("mail a.b@example.com nha", "example"),
            ("ẩn\u200b chữ\u202e xấu\ufeff", "\u200b"),
            ("dòng 1\r\ndòng 2\x00", "\x00"),
        ):
            cleaned = clean_caption(dirty)
            self.assertNotIn(expected_absent, cleaned, dirty)
            self.assertNotIn("  ", cleaned)
        self.assertEqual(clean_caption("Hơn 1.000.000 lượt xem"), "Hơn 1.000.000 lượt xem")
        self.assertEqual(clean_caption("Gia đình 👨\u200d👩\u200d👧"), "Gia đình 👨\u200d👩\u200d👧")  # emoji sequences keep their joiners

    def test_subtitle_lines_get_no_emoji_and_no_ass_markup(self):
        self.assertEqual(clean_subtitle("Hay quá 😍 {\\an8}ơi <b>nè</b>"), "Hay quá (an8)ơi nè")

    def test_a_caption_from_the_model_is_cleaned_and_always_has_enough_tags(self):
        c = build_caption(
            {
                "kind": "dialogue",
                "topic": "news",
                "caption_vi": "SỐC! Xem https://x.test và @abc",
                "hashtags": ["Hài Hước", "Hài hước", "#Đời Sống"],
            },
            "t",
        )
        self.assertNotIn("http", c)
        self.assertNotIn("@", c)
        tags = re.findall(r"#(\w+)", c)
        self.assertGreaterEqual(len(tags), 3)
        self.assertLessEqual(len(tags), 5)
        self.assertEqual(len(tags), len(set(tags)))
        self.assertTrue(all(t == t.lower() and t.isascii() for t in tags), tags)  # "Đời Sống" can never stay accented
        self.assertTrue(lint_caption(c)["ok"], lint_caption(c))

    def test_no_model_tags_still_gives_three_including_the_topic(self):
        c = build_caption({"kind": "dialogue", "topic": "news", "caption_vi": "Một câu mô tả đầy đủ", "hashtags": []}, "t")
        self.assertEqual(re.findall(r"#(\w+)", c), ["xuhuong", "tinnong", "viral"])

    def test_a_cut_caption_does_not_end_in_half_an_emoji(self):
        c = build_caption({"caption_vi": "a" * 108 + "👨\u200d👩\u200d👧", "hashtags": []}, "t")
        text = c.split(" #")[0]
        self.assertFalse(text.endswith("\u200d"))


class TextGateReviewTests(unittest.TestCase):
    """Cases from the independent review: what the text gate must keep, what it must remove, and how fast."""

    def test_ordinary_numbers_and_missing_spaces_are_not_mistaken_for_contacts(self):
        for keep in (
            "Ngày 01.10.2026",
            "01-10-2026",
            "Mở cửa 07.00-22.00",
            "Điểm 09.5 10.0 08.5",
            "05 06 07 08 09 10",
            "Hay quá.Top 1",  # a missing space after a full stop is not a web address
            "Mr.Co nói",
            "Anh ấy nói.Co",
            "Tập (1) 2.5",
            "năm (2026) tháng 10",
            "Giá 20.000.000đ",
            "2 < 3 > 1",
        ):
            self.assertEqual(clean_caption(keep), keep, keep)
        self.assertEqual(clean_subtitle("2 < 3 > 1"), "2 < 3 > 1")  # only real tags are markup

    def test_phone_numbers_in_their_usual_shapes_go(self):
        for number in (
            "0912 345 678",
            "0912.345.678",
            "091-234-5678",
            "+84 912 345 678",
            "(028) 3822 1234",
            "(028)38221234",
            "1900 1234",
            "+1 555 123 4567",
        ):
            self.assertEqual(clean_caption("gọi " + number + " nhé"), "gọi nhé", number)

    def test_links_in_every_disguise_go_including_glued_and_split_ones(self):
        for link in ("youtu.be/abc", "linktr.ee/x", "foo.dev", "foo.ai", "evil.com", "www.evil.com/x", "HTTPS://EVIL.TEST/x"):
            self.assertEqual(clean_caption("xem " + link + " nha"), "xem nha", link)
        self.assertNotIn("evil", clean_caption("Xem tại evil.comhttp://x hay"))  # glued: what is left of one link must not become another
        self.assertNotIn("evil", clean_subtitle("xem evil.c\\om nha"))  # a backslash used to be removed only after the check

    def test_filler_characters_do_not_make_an_empty_caption_look_filled(self):
        for blank in ("\u3164", "\u2800", "\u034f", "\u115f\u1160", "\u200b\u200c\ufeff", "\x85\x9b"):
            self.assertEqual(clean_caption(blank * 5), "", repr(blank))
        self.assertEqual(clean_caption("a\ud800b"), "ab")  # a lone surrogate is invalid text: dropped, never a later UnicodeEncodeError
        caption = build_caption({"kind": "dialogue", "caption_vi": "\u3164\u3164", "hashtags": []}, "Tiêu đề nguồn")
        self.assertTrue(caption.startswith("Tiêu đề nguồn"))  # a "blank" caption falls back to the source title

    def test_subtitles_lose_symbols_their_font_cannot_draw_and_never_end_in_a_space(self):
        self.assertEqual(clean_subtitle("Hay (c) (r)\u00a9\u00ae\u2122 ▶ ◽ → 😂 quá {"), "Hay (c) (r) quá (")
        self.assertEqual(clean_subtitle("quá 😂"), "quá")
        self.assertEqual(clean_subtitle("Giá 1.000.000đ, 50%"), "Giá 1.000.000đ, 50%")  # ordinary characters are kept

    def test_hostile_long_strings_are_cleaned_in_milliseconds(self):
        for evil in (
            "a" * 32000,
            "a-" * 16000,
            "a." * 16000,
            "x@" * 16000,
            "1 " * 16000,
            "http://" * 8000,
            "😂" * 30000,
            "0" * 32000,
            "(" * 30000,
        ):
            started = time.perf_counter()
            clean_caption(evil)
            clean_subtitle(evil)
            self.assertLess(time.perf_counter() - started, 0.5, evil[:12])  # the first version took 19-31 s on some of these

    def test_a_huge_subtitle_is_refused_without_running_the_cleaner_on_it(self):
        a = dict(ANALYSIS, kind="dialogue", segments=[{"start": 0, "end": 3, "vi": "x" * 30000}])
        started = time.perf_counter()
        with self.assertRaises(ValueError):
            validate_analysis(a, 10, strict=True)
        self.assertLess(time.perf_counter() - started, 0.5)


class NotifySafetyTests(unittest.TestCase):
    def test_only_public_dns_names_are_accepted(self):
        for bad in (
            "https://2130706433/x",  # 127.0.0.1 as one number
            "https://0x7f.0.0.1/x",
            "https://017700000001/x",
            "https://[::1]/x",
            "https://10.0.0.5/x",
            "https://localhost/x",
            "https://printer.local/x",
            "https://db.internal/x",
            "https://nas.lan/x",
            "https://example.com\\@evil.test/x",
            "https://user:pw@example.com/x",
            "http://example.com/x",
            "https://example/x",
        ):
            with self.assertRaises(ValueError, msg=bad):
                notify._safe_https(bad)
        self.assertEqual(notify._safe_https("https://discord.com/api/webhooks/1/a"), "https://discord.com/api/webhooks/1/a")

    def test_odd_ports_and_odd_dns_answers_are_refused(self):
        for bad in ("https://example.com:99999/x", "https://example.com:abc/x"):
            with self.assertRaises(ValueError, msg=bad):
                notify._safe_https(bad)
        self.assertEqual(notify._safe_https("https://ntfy.example.com:8443/t"), "https://ntfy.example.com:8443/t")
        with mock.patch.object(notify.socket, "getaddrinfo", return_value=[]):
            with self.assertRaises(ValueError):
                notify._public_only("https://example.com/hook")  # no answer at all is not "nothing internal"

    def test_ipv6_forms_that_hide_an_internal_ipv4_are_internal(self):
        for hidden in ("64:ff9b::7f00:1", "::127.0.0.1", "::ffff:10.0.0.1", "fec0::1", "64:ff9b::a9fe:a9fe", "::1", "fd00::1"):
            self.assertFalse(notify._is_public(hidden), hidden)
        for public in ("93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946", "64:ff9b::5db8:d822"):
            self.assertTrue(notify._is_public(public), public)

    def test_a_name_that_resolves_to_an_internal_address_is_refused_at_send_time(self):
        for address in ("127.0.0.1", "169.254.169.254", "10.1.2.3", "::1", "fe80::1%eth0"):
            fake = [(0, 0, 0, "", (address, 443))]
            with mock.patch.object(notify.socket, "getaddrinfo", return_value=fake):
                with self.assertRaises(ValueError, msg=address):
                    notify._public_only("https://sneaky.example.com/hook")
        with mock.patch.object(notify.socket, "getaddrinfo", return_value=[(0, 0, 0, "", ("93.184.216.34", 443))]):
            notify._public_only("https://example.com/hook")

    def test_redirects_are_not_followed(self):
        handler = notify._NoRedirect()
        self.assertIsNone(handler.redirect_request(mock.Mock(), None, 302, "Found", {}, "http://169.254.169.254/"))
        self.assertTrue(any(isinstance(h, notify._NoRedirect) for h in notify._OPENER.handlers))

    def test_a_message_can_never_ping_everyone(self):
        sent = {}

        def capture(url, data, headers, check_host=False):
            sent[url] = json.loads(data)
            return True

        with mock.patch.object(notify, "_post", capture):
            notify.send({"webhook": "https://discord.com/api/webhooks/1/a"}, "@everyone look")
        body = sent["https://discord.com/api/webhooks/1/a"]
        self.assertEqual(body["allowed_mentions"], {"parse": []})


class MediaServingTests(unittest.TestCase):
    def test_only_known_media_types_are_ever_named(self):
        self.assertEqual(set(media_files.SERVED_TYPES), {".mp4", ".jpg", ".png", ".wav"})


class MarkupEscapingTests(unittest.TestCase):
    def test_a_task_state_cannot_break_out_of_its_attribute(self):
        task = {
            "state": 'x"><script>alert(1)</script>',
            "kind": "k",
            "steps": [{"state": 'a"><script>alert(2)</script>', "name": "n", "detail": ""}],
            "started": 1,
            "finished": 2,
        }
        html = components.task_panel([task])
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)


if __name__ == "__main__":
    unittest.main()
