"""The HTTP request handler: routing, access rules, and turning errors into responses."""

import json
import re
import time
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from .. import ui
from ..ui.labels import vi_error
from ..version import VERSION
from . import api, forms, media_files
from .log import log
from .pages import dashboard_html
from .responses import ResponseMixin
from .security import SESSION_COOKIE, SESSION_SECONDS, same

STALE_PAGE = (
    '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Trang \u0111\u00e3 c\u0169</title>'
    '<body style="font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem">'
    "<h1>Trang \u0111\u00e3 c\u0169</h1><p>Trang n\u00e0y \u0111\u01b0\u1ee3c m\u1edf tr\u01b0\u1edbc khi h\u1ec7 th\u1ed1ng c\u1eadp nh\u1eadt ho\u1eb7c \u0111\u00e3 \u0111\u1ec3 qu\u00e1 l\u00e2u, n\u00ean l\u1ea7n b\u1ea5m v\u1eeba r\u1ed3i "
    "<b>ch\u01b0a \u0111\u01b0\u1ee3c l\u01b0u</b>. T\u1ea3i l\u1ea1i b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n r\u1ed3i l\u00e0m l\u1ea1i thao t\u00e1c.</p>"
    '<p><a href="/">← Quay l\u1ea1i b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n</a></p></body>'
)

MAX_BODY = 2 * 1024 * 1024
LOGIN_FORM_MAX = 4096
# polled by the page or by Docker every few seconds: not worth a log line
QUIET_PATHS = ("/health", "/fragment/", "/media/", "/favicon")
SOCKET_TIMEOUT = 30  # seconds a client may stall mid-request before its connection is dropped (slow-client protection)


class Handler(ResponseMixin, BaseHTTPRequestHandler):
    server_version = "TrendVN/" + VERSION
    timeout = SOCKET_TIMEOUT
    app = None  # bound to the running App by web.server.make_handler

    def version_string(self):  # no Python version in the Server header
        return "TrendVN"

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
        source = " from " + self.client_address[0] if code in ("401", "403") else ""  # who is knocking
        log("%s %s -> %s%s" % (command, path, code, source))

    def log_message(self, fmt, *args):  # malformed requests and other server-level complaints
        log("http: " + (fmt % args))

    # ------------------------------------------------------------------ shortcuts to the app
    @property
    def store(self):
        return self.app.store

    @property
    def access(self):
        return self.app.access

    def body_length(self):
        """Content-Length as a number from 0 up; anything else (negative, signs, spaces, Unicode digits) is a ValueError."""
        raw = self.headers.get("Content-Length", "0")
        if not re.fullmatch(r"[0-9]{1,9}", raw):
            raise ValueError("Bad Content-Length")
        return int(raw)

    def host_ok(self):
        return self.access.host_ok(self.headers)

    def local_ui(self):
        return self.access.local_ui(self.headers, self.client_address[0])

    def wrong_peer(self):
        """The Host header claims localhost but the connection came from somewhere that is not this machine."""
        return (
            self.headers.get("Host", "") in self.app.config.loopback_hosts and self.client_address[0] not in self.app.config.trusted_peers
        )

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
        if path in ("/", "/login") and self.wrong_peer():
            peer = self.client_address[0]
            log(
                "dashboard refused: Host says this machine but the connection came from %s (set TRENDVN_TRUSTED_PEERS if that is you)"
                % peer
            )
            return self.send(
                403,
                {
                    "error": "K\u1ebft n\u1ed1i t\u1eeb %s kh\u00f4ng ph\u1ea3i m\u00e1y n\u00e0y. N\u1ebfu \u0111\u00e2y \u0111\u00fang l\u00e0 m\u00e1y c\u1ee7a b\u1ea1n, th\u00eam \u0111\u1ecba ch\u1ec9 \u0111\u00f3 v\u00e0o TRENDVN_TRUSTED_PEERS trong .env"
                    % peer
                },
            )
        if path == "/login" and self.host_ok() and not self.local_ui():
            if not self.app.config.ui_password:
                return self.send(
                    403,
                    {
                        "error": "\u0110\u1eb7t TRENDVN_UI_PASSWORD trong .env \u0111\u1ec3 m\u1edf b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n t\u1eeb m\u00e1y kh\u00e1c"
                    },
                )
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
        if path == "/logout":
            return self.logout()
        try:
            length = self.body_length()
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
            return self.send(403, STALE_PAGE, "text/html; charset=utf-8")  # (an open page that outlived an update: say what to do)
        try:
            result = forms.FORMS[path](self.app, form)
        except (ValueError, KeyError, TypeError, OSError, OverflowError) as error:
            return self.redirect(err=vi_error(str(error)) or "Kh\u00f4ng th\u1ef1c hi\u1ec7n \u0111\u01b0\u1ee3c")
        return self.redirect(result.key, result.err, result.anchor)

    def api_post(self, path, payload):
        try:
            return self.send(200, api.handle(self.app, path, payload))
        except api.NotFound:
            return self.send(404, {"error": "Not found"})
        except api.Busy as busy:
            return self.send(409, {"error": str(busy)})

    # ------------------------------------------------------------------ password login (only for hosts other than this machine)
    def session_cookie(self, value, max_age):
        secure = "; Secure" if self.app.config.secure_cookie else ""
        return "%s=%s; HttpOnly; SameSite=Strict; Path=/; Max-Age=%d%s" % (SESSION_COOKIE, value, max_age, secure)

    def logout(self):
        """Ends the password session in this browser (a form post from the dashboard itself)."""
        if not self.access.form_origin_ok(self.headers):
            return self.send(403, {"error": "Local form only"})
        self.access.end_session(self.headers)  # the cookie value stops working on the server too, not only in this browser
        return self.redirect_to("/login", self.session_cookie("", 0))

    def login_page(self, message=""):
        return self.send(200, ui.login_page(message), "text/html; charset=utf-8")

    def login_post(self):
        if not self.host_ok() or not self.app.config.ui_password:
            return self.send(403, {"error": "Not available"})
        ip = self.client_address[0]
        if self.access.login_locked(ip):
            return self.login_page(
                "Th\u1eed sai qu\u00e1 nhi\u1ec1u l\u1ea7n. \u0110\u1ee3i m\u1ed9t ph\u00fat r\u1ed3i th\u1eed l\u1ea1i."
            )
        try:
            body = self.rfile.read(min(self.body_length(), LOGIN_FORM_MAX)).decode()
            form = parse_qs(body, keep_blank_values=True)
        except Exception:  # a garbled length or body is just a wrong password
            form = {}
        if same(form.get("password", [""])[0], self.app.config.ui_password):
            self.access.login_succeeded(ip)
            return self.redirect_to("/", self.session_cookie(self.access.new_session(), SESSION_SECONDS))
        self.access.login_failed(ip)
        time.sleep(1)  # slow down guessing
        return self.login_page("M\u1eadt kh\u1ea9u ch\u01b0a \u0111\u00fang.")
