"""The worker's HTTP surface, exercised over real sockets: host/origin/CSRF rules, the password gate for other machines,
blank and oversized form fields, media paths, compression, and that nothing crashes the server."""

import gzip
import http.client
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "worker" / "src"))
from trendvn_worker.store import Store


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Server:
    def __init__(self, extra_env=None, capture=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.port = free_port()
        Store(self.tmp.name)
        env = dict(
            os.environ,
            TRENDVN_DATA=self.tmp.name,
            TRENDVN_TOKEN="t" * 40,
            TRENDVN_PORT=str(self.port),
            TRENDVN_PUBLIC_PORT=str(self.port),
            TRENDVN_AGENT_URL="http://127.0.0.1:1",
        )
        env.update(extra_env(self.port) if callable(extra_env) else (extra_env or {}))
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "trendvn_worker"],
            cwd=str(ROOT / "services" / "worker" / "src"),
            env=env,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.STDOUT if capture else subprocess.DEVNULL,
        )
        for _ in range(60):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.3).close()
                return
            except OSError:
                time.sleep(0.2)
        raise RuntimeError("server did not start")

    def req(self, method, path, body=None, headers=None, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = {"Host": host or "localhost:%d" % self.port}
        h.update(headers or {})
        conn.request(method, path, body=body, headers=h)
        r = conn.getresponse()
        data = r.read()
        out = (r.status, dict((k.lower(), v) for k, v in r.getheaders()), data)
        conn.close()
        return out

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(5)
        except Exception:
            self.proc.kill()
        self.tmp.cleanup()


class LocalServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server()
        s, h, body = cls.srv.req("GET", "/")
        cls.csrf = re.search(rb'name="csrf" value="([^"]+)"', body).group(1).decode()

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def post(self, path, fields, origin=True, fetch_site=None, csrf=True):
        f = dict(fields)
        if csrf:
            f["csrf"] = self.csrf
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if origin == "null":
            headers["Origin"] = "null"
        elif origin:
            headers["Origin"] = "http://localhost:%d" % self.srv.port
        if fetch_site:
            headers["Sec-Fetch-Site"] = fetch_site
        return self.srv.req("POST", path, urlencode(f), headers)

    def test_unknown_host_and_paths(self):
        self.assertEqual(self.srv.req("GET", "/", host="evil.test")[0], 404)
        self.assertEqual(self.srv.req("GET", "/nope")[0], 404)
        self.assertEqual(self.srv.req("GET", "/health", host="anything")[0], 200)
        self.assertEqual(self.srv.req("GET", "/api/status", host="evil.test")[0], 404)  # needs token or local dashboard

    def test_api_needs_the_token(self):
        self.assertEqual(
            self.srv.req("POST", "/api/settings", '{"daily_limit": 3}', {"Content-Type": "application/json"}, host="evil.test")[0], 401
        )
        ok = self.srv.req("POST", "/api/settings", '{"daily_limit": 3}', {"Authorization": "Bearer " + "t" * 40})
        self.assertEqual(ok[0], 200)
        self.assertEqual(self.srv.req("POST", "/api/settings", '{"daily_limit": 3}', {"Authorization": "Bearer wrong"})[0], 401)

    def test_form_needs_origin_and_csrf(self):
        self.assertEqual(self.post("/settings", {"daily_limit": "2"}, origin=False)[0], 403)
        self.assertEqual(self.post("/settings", {"daily_limit": "2"}, origin="null")[0], 403)  # null origin alone is not enough
        self.assertEqual(self.post("/settings", {"daily_limit": "2"}, csrf=False)[0], 403)
        self.assertEqual(self.post("/settings", {"daily_limit": "2"}, origin="null", fetch_site="same-origin")[0], 303)  # what Chrome sends
        self.assertEqual(self.post("/settings", {"daily_limit": "2"}, origin="null", fetch_site="cross-site")[0], 403)
        evil = self.srv.req(
            "POST",
            "/settings",
            urlencode({"csrf": self.csrf, "daily_limit": "2"}),
            {"Content-Type": "application/x-www-form-urlencoded", "Origin": "http://evil.test"},
        )
        self.assertEqual(evil[0], 403)

    def test_blank_fields_mean_what_they_say(self):
        store = Store(self.srv.tmp.name)
        self.post("/settings", {"post_windows": "9-12", "views_tiktok": "5"}, fetch_site="same-origin")
        self.assertEqual(store.settings()["post_windows"], [[9, 12]])
        self.post("/settings", {"post_windows": "", "views_tiktok": "", "views_kuaishou": "7"}, fetch_site="same-origin")
        cfg = store.settings()
        self.assertEqual(cfg["post_windows"], [])  # blank window box = publish any time
        self.assertEqual(cfg["min_views"]["tiktok"], 5)  # blank number = unchanged, not "no threshold"
        self.assertEqual(cfg["min_views"]["kuaishou"], 7)

    def test_absurd_numbers_get_a_message_not_a_crash(self):
        for field, value in (
            ("gap_hours", "1e400"),
            ("gap_hours", "inf"),
            ("daily_limit", "9" * 400),
            ("audio_confidence", "nan"),
            ("max_age_days", "-5"),
        ):
            status, headers, _ = self.post("/settings", {field: value}, fetch_site="same-origin")
            self.assertEqual(status, 303, (field, value))
            self.assertIn("err=", headers.get("location", ""), (field, value))
        self.assertEqual(self.srv.req("GET", "/health")[0], 200)

    def test_task_form_validates_input(self):
        status, headers, _ = self.post("/task", {"kind": "nope"}, fetch_site="same-origin")
        self.assertEqual(status, 303)
        self.assertIn("err=", headers["location"])
        status, headers, _ = self.post("/task", {"kind": "publish", "id": "../../etc"}, fetch_site="same-origin")
        self.assertIn("err=", headers["location"])
        status, headers, _ = self.post("/task", {"kind": "publish"}, fetch_site="same-origin")  # no video chosen
        self.assertIn("err=", headers["location"])

    def test_media_paths_cannot_escape(self):
        for p in (
            "/media/../../etc/passwd",
            "/media/shot/../../../etc/passwd",
            "/media/shot/shot_1.png",
            "/media/%2e%2e/x/final",
            "/media/" + "a" * 32 + "/final",
            "/media/" + "a" * 32 + "/../final",
            "/media/shot/shot_123456789.png",
            "/media/x",
        ):
            self.assertEqual(self.srv.req("GET", p)[0], 404, p)

    def test_fragment_and_dashboard_are_compressed(self):
        status, headers, body = self.srv.req("GET", "/", headers={"Accept-Encoding": "gzip"})
        self.assertEqual(status, 200)
        self.assertEqual(headers.get("content-encoding"), "gzip")
        html = gzip.decompress(body).decode()
        self.assertIn("TrendVN", html)
        self.assertIn("img-src 'self' data:", headers["content-security-policy"])
        self.assertEqual(headers["referrer-policy"], "same-origin")
        status, headers, body = self.srv.req("GET", "/fragment/tasks")
        self.assertEqual(status, 200)
        self.assertIn(b"taskpanel", body)

    def test_malformed_requests_do_not_kill_the_server(self):
        for raw in (
            b"GARBAGE\r\n\r\n",
            b"GET / HTTP/1.1\r\nHost: localhost\r\nContent-Length: abc\r\n\r\n",
            b"POST /settings HTTP/1.1\r\nHost: localhost:%d\r\nContent-Length: 99999999\r\n\r\n" % self.srv.port,
        ):
            s = socket.create_connection(("127.0.0.1", self.srv.port), timeout=3)
            s.sendall(raw)
            try:
                s.recv(200)
            except OSError:
                pass
            s.close()
        self.assertEqual(self.srv.req("GET", "/health")[0], 200)


class RemoteAccessTests(unittest.TestCase):
    def test_other_hosts_need_the_password(self):
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": "correct-horse-battery"})
        port = srv.port
        try:
            remote = "box.test:%d" % port
            status, headers, _ = srv.req("GET", "/", host=remote)
            self.assertEqual((status, headers.get("location")), (303, "/login"))  # no dashboard without logging in
            self.assertEqual(srv.req("GET", "/fragment/tasks", host=remote)[0], 404)
            self.assertEqual(srv.req("GET", "/media/shot/shot_123456789.png", host=remote)[0], 404)
            self.assertEqual(srv.req("GET", "/login", host=remote)[0], 200)
            bad = srv.req(
                "POST", "/login", urlencode({"password": "nope"}), {"Content-Type": "application/x-www-form-urlencoded"}, host=remote
            )
            self.assertEqual(bad[0], 200)
            self.assertIn("chưa đúng".encode(), bad[2])
            self.assertNotIn("set-cookie", bad[1])
            good = srv.req(
                "POST",
                "/login",
                urlencode({"password": "correct-horse-battery"}),
                {"Content-Type": "application/x-www-form-urlencoded"},
                host=remote,
            )
            self.assertEqual(good[0], 303)
            cookie = good[1]["set-cookie"].split(";")[0]
            self.assertIn("HttpOnly", good[1]["set-cookie"])
            self.assertIn("SameSite=Strict", good[1]["set-cookie"])
            self.assertEqual(srv.req("GET", "/", headers={"Cookie": cookie}, host=remote)[0], 200)
            self.assertEqual(srv.req("GET", "/", headers={"Cookie": "tv_session=forged"}, host=remote)[0], 303)
            self.assertEqual(srv.req("GET", "/", host="localhost:%d" % port)[0], 200)  # this machine never needs the password
        finally:
            srv.stop()

    def test_gate_cannot_be_bypassed_with_path_or_header_tricks(self):
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": "correct-horse-battery"})
        try:
            remote = "box.test:%d" % srv.port
            protected = [
                "/",
                "//",
                "/?x=1",
                "/index",
                "/fragment/tasks",
                "/api/tasks",
                "/api/dashboard",
                "/api/status",
                "/media/shot/shot_123456789.png",
                "/media/" + "a" * 32 + "/final",
                "/./",
                "/%2e/",
                "/login/../",
                "//login/../",
            ]
            for path in protected:
                status = srv.req("GET", path, host=remote)[0]
                self.assertIn(status, (303, 404), (path, status))  # never 200 without the password
            for host in (
                "BOX.TEST:%d" % srv.port,
                "box.test.:%d" % srv.port,
                "box.test:%d " % srv.port,
                "localhost:%d.evil.test" % srv.port,
                "localhost",
            ):
                self.assertEqual(srv.req("GET", "/", host=host)[0], 404, host)  # only exact allowed hosts are answered
            for raw in (b"GET / HTTP/1.0\r\n\r\n", b"GET / HTTP/1.1\r\nHost:\r\n\r\n"):  # no usable Host header at all
                s = socket.create_connection(("127.0.0.1", srv.port), timeout=3)
                s.sendall(raw)
                first = s.recv(200).split(b"\r\n")[0]
                s.close()
                self.assertIn(b" 404 ", first, raw)
            spoof = {
                "X-Forwarded-For": "127.0.0.1",
                "X-Real-IP": "127.0.0.1",
                "Forwarded": "for=127.0.0.1",
                "X-Forwarded-Host": "localhost:%d" % srv.port,
            }
            self.assertEqual(srv.req("GET", "/", headers=spoof, host=remote)[0], 303)  # forwarded-for headers grant nothing
            for cookie in ("tv_session=", "tv_session=x", "tv_session=" + "a" * 64, "tv_session=1; tv_session=2"):
                self.assertEqual(srv.req("GET", "/", headers={"Cookie": cookie}, host=remote)[0], 303, cookie)
            post = srv.req(
                "POST",
                "/settings",
                urlencode({"daily_limit": "9", "csrf": "x"}),
                {"Content-Type": "application/x-www-form-urlencoded", "Origin": "http://" + remote},
                host=remote,
            )
            self.assertEqual(post[0], 403)
            api = srv.req("POST", "/api/settings", '{"daily_limit": 9}', {"Content-Type": "application/json"}, host=remote)
            self.assertEqual(api[0], 401)
            self.assertNotEqual(Store(srv.tmp.name).settings()["daily_limit"], 9)
        finally:
            srv.stop()

    def test_other_hosts_are_refused_when_no_password_is_set(self):
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": ""})
        port = srv.port
        try:
            remote = "box.test:%d" % port
            self.assertEqual(srv.req("GET", "/login", host=remote)[0], 403)
            self.assertEqual(
                srv.req("POST", "/login", "password=", {"Content-Type": "application/x-www-form-urlencoded"}, host=remote)[0], 403
            )
            self.assertEqual(srv.req("GET", "/", host="localhost:%d" % port)[0], 200)
        finally:
            srv.stop()

    def test_five_wrong_passwords_lock_the_door_for_a_minute(self):
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": "correct-horse-battery"})
        port = srv.port
        try:
            remote = "box.test:%d" % port
            for _ in range(5):
                srv.req("POST", "/login", "password=x", {"Content-Type": "application/x-www-form-urlencoded"}, host=remote)
            locked = srv.req(
                "POST", "/login", "password=correct-horse-battery", {"Content-Type": "application/x-www-form-urlencoded"}, host=remote
            )
            self.assertEqual(locked[0], 200)
            self.assertNotIn("set-cookie", locked[1])
            self.assertIn("quá nhiều".encode(), locked[2])
        finally:
            srv.stop()


if __name__ == "__main__":
    unittest.main()


class LogTests(unittest.TestCase):
    """`./trendvn logs worker` must show what happened, and must never show secrets."""

    def test_worker_logs_start_up_and_api_calls_but_no_secrets_or_noise(self):
        srv = Server(capture=True)
        try:
            srv.req("GET", "/health")
            srv.req("GET", "/")
            srv.req("GET", "/fragment/tasks")
            srv.req(
                "POST",
                "/api/process",
                body=b'{"max":1}',
                headers={"Authorization": "Bearer " + "t" * 40, "Content-Type": "application/json"},
            )
            srv.req("POST", "/api/process", body=b"{}", headers={"Content-Type": "application/json"})  # unauthenticated -> 401
            srv.req("GET", "/api/nothing?token=" + "x" * 30)
            time.sleep(0.5)
        finally:
            srv.proc.terminate()
            out = srv.proc.communicate(timeout=10)[0].decode()
            srv.tmp.cleanup()
        self.assertIn("worker ", out)
        self.assertIn("listening on :%d" % srv.port, out)
        self.assertIn("POST /api/process -> 401", out)
        self.assertIn("process: ", out)
        self.assertNotIn("/health", out)  # polled by Docker every 30 s
        self.assertNotIn("/fragment/", out)  # polled by the open page
        self.assertNotIn("t" * 40, out)  # the bearer token
        self.assertNotIn("x" * 30, out)  # query strings are never logged


class NonAsciiTests(unittest.TestCase):
    """hmac.compare_digest raises TypeError for non-ASCII str: a Vietnamese password must log in, and odd headers must not crash a request."""

    def test_vietnamese_password_logs_in_and_odd_headers_are_rejected_cleanly(self):
        password = "mật-khẩu-rất-dài-123"
        srv = Server(lambda p: {"TRENDVN_UI_HOSTS": "box.test:%d" % p, "TRENDVN_UI_PASSWORD": password})
        try:
            remote = "box.test:%d" % srv.port
            form = {"Content-Type": "application/x-www-form-urlencoded"}
            self.assertEqual(srv.req("POST", "/login", urlencode({"password": "sai-mật-khẩu"}), form, host=remote)[0], 200)
            good = srv.req("POST", "/login", urlencode({"password": password}), form, host=remote)
            self.assertEqual(good[0], 303)
            cookie = good[1]["set-cookie"].split(";")[0]
            self.assertEqual(srv.req("GET", "/", headers={"Cookie": cookie}, host=remote)[0], 200)
            for headers in ({"Authorization": "Bearer " + "é" * 40}, {"Cookie": "tv_session=" + "é" * 20}):
                status = srv.req("GET", "/api/status", headers=headers, host=remote)[0]
                self.assertIn(status, (401, 403, 404, 303), (headers, status))  # answered, not a 500 or a dropped connection
            self.assertEqual(srv.req("GET", "/health")[0], 200)
        finally:
            srv.stop()

    def test_malformed_request_line_is_logged_without_crashing_the_logger(self):
        srv = Server(capture=True)
        try:
            for raw in (b"GET / HTTP/9.9\r\n\r\n", b"\x80\x81\x82 nonsense\r\n\r\n", b"GET /" + b"a" * 70000 + b" HTTP/1.1\r\n\r\n"):
                s = socket.create_connection(("127.0.0.1", srv.port), timeout=3)
                s.sendall(raw)
                try:
                    s.recv(300)
                except OSError:
                    pass
                s.close()
            self.assertEqual(srv.req("GET", "/health")[0], 200)
        finally:
            srv.proc.terminate()
            out = srv.proc.communicate(timeout=10)[0].decode(errors="replace")
            srv.tmp.cleanup()
        self.assertNotIn("AttributeError", out)
        self.assertNotIn("Traceback", out)
