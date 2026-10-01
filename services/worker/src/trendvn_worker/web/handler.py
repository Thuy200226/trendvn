"""The HTTP request handler: routing, access rules, and turning errors into responses."""

import json
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from .. import ui
from ..version import VERSION
from . import api, forms, media_files
from .log import log
from .pages import dashboard_html
from .responses import ResponseMixin
from .security import SESSION_COOKIE, same

MAX_BODY = 2 * 1024 * 1024
LOGIN_FORM_MAX = 4096
# polled by the page or by Docker every few seconds: not worth a log line
QUIET_PATHS = ("/health", "/fragment/", "/media/", "/favicon")


class Handler(ResponseMixin, BaseHTTPRequestHandler):
    server_version = "TrendVN/" + VERSION
    app = None  # bound to the running App by web.server.make_handler

    # ------------------------------------------------------------------ logging
    def log_request(self, code="-", size="-"):
        # path only: the query string can carry flash text and is never logged. `path`/`command` are unset for malformed requests.
        path = urlsplit(getattr(self, "path", "") or "").path
        command = getattr(self, "command", None) or "-"
        code = str(code)
        if command == "GET" and code.startswith("2") and (path == "/" or path.startswith(QUIET_PATHS)):
            return
        if path.startswith(QUIET_PATHS) and not code.startswith(("4", "5")):
            return
        log("%s %s -> %s" % (command, path, code))

    def log_message(self, fmt, *args):  # malformed requests and other server-level complaints
        log("http: " + (fmt % args))

    # ------------------------------------------------------------------ shortcuts to the app
    @property
    def store(self):
        return self.app.store

    @property
    def access(self):
        return self.app.access

    def host_ok(self):
        return self.access.host_ok(self.headers)

    def local_ui(self):
        return self.access.local_ui(self.headers)

    def api_allowed(self):
        return self.access.authorized(self.headers) or self.local_ui()

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        try:
            return self._get()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            log("ERROR GET %s\n%s" % (urlsplit(self.path).path, traceback.format_exc().rstrip()))
            try:
                return self.send(500, {"error": "Internal failure; inspect local service"})
            except Exception:
                return

    def _get(self):
        url = urlsplit(self.path)
        path = url.path
        if path == "/health":
            return self.send(200, {"ok": True, "project": "trendvn", "version": VERSION})
        if path == "/login" and self.host_ok() and not self.local_ui():
            if not self.app.config.ui_password:
                return self.send(403, {"error": "Đặt TRENDVN_UI_PASSWORD trong .env để mở bảng điều khiển từ máy khác"})
            return self.login_page()
        if path == "/" and self.host_ok() and not self.local_ui():
            return self.redirect_to("/login")
        if path.startswith("/media/") and self.local_ui():
            return media_files.serve(self, self.store, path)
        if path == "/" and self.local_ui():
            query = parse_qs(url.query)
            ok_key = query.get("ok", [""])[0]
            flash = ("ok", forms.FLASH[ok_key]) if ok_key in forms.FLASH else (("err", query["err"][0]) if query.get("err") else None)
            return self.send(200, dashboard_html(self.app, flash, self.headers.get("Host", "")), "text/html; charset=utf-8")
        if path == "/api/status" and self.api_allowed():
            return self.send(200, self.store.status())
        if path == "/api/dashboard" and self.api_allowed():
            return self.send(200, self.store.dashboard_data())
        if path == "/fragment/tasks" and self.local_ui():
            return self.send(200, ui.task_panel(self.store.tasks_recent(6)), "text/html; charset=utf-8")
        if path == "/api/tasks" and self.api_allowed():
            return self.send(200, {"running": self.store.tasks_running(), "tasks": self.store.tasks_recent(6)})
        return self.send(404, {"error": "Not found"})

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        path = urlsplit(self.path).path
        if path == "/login":
            return self.login_post()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_BODY:
                return self.send(413, {"error": "Request too large or empty"})
            if path in forms.FORMS:
                return self.form_post(path, length)
            if not self.access.authorized(self.headers):
                return self.send(401, {"error": "Authentication required"})
            payload = json.loads(self.rfile.read(length))
            return self.api_post(path, payload)
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            return self.send(400, {"error": str(error)[:700]})
        except Exception:
            log("ERROR POST %s\n%s" % (path, traceback.format_exc().rstrip()))
            return self.send(500, {"error": "Internal failure; inspect local service"})

    def form_post(self, path, length):
        if not self.local_ui() or not self.access.form_origin_ok(self.headers):
            return self.send(403, {"error": "Local form only"})
        form = parse_qs(self.rfile.read(length).decode(), keep_blank_values=True)
        if not same(form.get("csrf", [""])[0], self.app.csrf):
            return self.send(403, {"error": "Refresh the page and retry"})
        try:
            result = forms.FORMS[path](self.app, form)
        except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
            return self.redirect(err=str(error) or "Không thực hiện được")
        return self.redirect(result.key, result.err, result.anchor)

    def api_post(self, path, payload):
        try:
            return self.send(200, api.handle(self.app, path, payload))
        except api.NotFound:
            return self.send(404, {"error": "Not found"})
        except api.Busy as busy:
            return self.send(409, {"error": str(busy)})

    # ------------------------------------------------------------------ password login (only for hosts other than this machine)
    def login_page(self, message=""):
        return self.send(200, ui.login_page(message), "text/html; charset=utf-8")

    def login_post(self):
        if not self.host_ok() or not self.app.config.ui_password:
            return self.send(403, {"error": "Not available"})
        ip = self.client_address[0]
        if self.access.login_locked(ip):
            return self.login_page("Thử sai quá nhiều lần. Đợi một phút rồi thử lại.")
        try:
            body = self.rfile.read(min(int(self.headers.get("Content-Length", "0")), LOGIN_FORM_MAX)).decode()
            form = parse_qs(body, keep_blank_values=True)
        except Exception:
            form = {}
        if same(form.get("password", [""])[0], self.app.config.ui_password):
            self.access.login_succeeded(ip)
            cookie = "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=2592000" % (SESSION_COOKIE, self.access.session_value)
            return self.redirect_to("/", cookie)
        self.access.login_failed(ip)
        time.sleep(1)  # slow down guessing
        return self.login_page("Mật khẩu chưa đúng.")
