"""Who may see what: the bearer token for the API, loopback or a password session for the dashboard."""

import hashlib
import hmac
import secrets
import threading
import time

SESSION_COOKIE = "tv_session"
SESSION_SECONDS = 7 * 24 * 3600  # a password session lasts a week; /logout ends it earlier
MAX_SESSIONS = 64  # signed-in browsers remembered at once (the oldest is forgotten first)
# a reverse proxy in front of the dashboard adds some of these; a browser on this machine never does
PROXY_HEADERS = ("X-Forwarded-For", "X-Forwarded-Host", "X-Forwarded-Proto", "X-Real-IP", "Forwarded")
MAX_LOGIN_FAILURES = 5
LOCK_SECONDS = 60
MAX_TRACKED_IPS = 1024  # failed-login memory is bounded so a spray of addresses cannot grow it


def same(a, b):
    """Constant-time equality for strings that may contain non-ASCII characters (hmac.compare_digest raises TypeError on those)."""
    return hmac.compare_digest(str(a).encode("utf-8"), str(b).encode("utf-8"))


class Access:
    """Decisions about a request, taken from its headers and the address it came from."""

    def __init__(self, config):
        self.config = config
        # Sessions live on the server: a random token per login, kept as its hash with an expiry. /logout and the expiry really end a
        # session, and a restart (which is also how a new password takes effect) ends them all.
        self.sessions = {}  # sha256(token) -> expires at
        self.sessions_lock = threading.Lock()
        self.login_failures = {}  # ip -> (count, locked_until)

    def authorized(self, headers):
        """The API caller presented the right bearer token."""
        return same(headers.get("Authorization", ""), "Bearer " + self.config.token)

    def host_ok(self, headers):
        return headers.get("Host", "") in self.config.ui_hosts

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode("utf-8", "replace")).hexdigest()

    def new_session(self, now=None):
        """A fresh session token for someone who just gave the right password (send it as the cookie value)."""
        now = time.time() if now is None else now
        token = secrets.token_urlsafe(32)
        with self.sessions_lock:
            for key in [key for key, expires in self.sessions.items() if expires <= now]:
                del self.sessions[key]
            while len(self.sessions) >= MAX_SESSIONS:
                del self.sessions[min(self.sessions, key=self.sessions.get)]
            self.sessions[self._digest(token)] = now + SESSION_SECONDS
        return token

    @staticmethod
    def _cookie_token(headers):
        for part in headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE:
                return value
        return ""

    def session_ok(self, headers, now=None):
        token = self._cookie_token(headers)
        if not token:
            return False
        now = time.time() if now is None else now
        with self.sessions_lock:
            expires = self.sessions.get(self._digest(token))
            if expires is not None and expires <= now:
                del self.sessions[self._digest(token)]
                return False
        return expires is not None

    def end_session(self, headers):
        """/logout: forget the session whose cookie this request carries."""
        with self.sessions_lock:
            self.sessions.pop(self._digest(self._cookie_token(headers)), None)

    def local_ui(self, headers, peer=""):
        """The dashboard is open without a password only on this machine: the Host header says localhost AND the connection itself
        came from this machine (a forged Host header from the network is not enough). Any other host you allow (TRENDVN_UI_HOSTS)
        needs the password from TRENDVN_UI_PASSWORD; without one, such hosts are refused outright."""
        host = headers.get("Host", "")
        proxied = any(name in headers for name in PROXY_HEADERS)  # a proxy on this machine would otherwise make every visitor "local"
        if host in self.config.loopback_hosts and peer in self.config.trusted_peers and not proxied:
            return True
        return host in self.config.ui_hosts and bool(self.config.ui_password) and self.session_ok(headers)

    def form_origin_ok(self, headers):
        """Dashboard forms must come from the dashboard itself (Origin check; `Origin: null` only for same-origin requests)."""
        origin = headers.get("Origin")
        same_site = headers.get("Sec-Fetch-Site") == "same-origin"
        return origin in self.config.ui_origins or (origin in (None, "null") and same_site)

    # ------------------------------------------------------------------ password login
    def login_locked(self, ip):
        _, locked_until = self.login_failures.get(ip, (0, 0))
        return time.time() < locked_until

    def login_succeeded(self, ip):
        self.login_failures.pop(ip, None)

    def login_failed(self, ip):
        if ip not in self.login_failures and len(self.login_failures) >= MAX_TRACKED_IPS:
            self.login_failures.pop(next(iter(self.login_failures)))
        count, _ = self.login_failures.get(ip, (0, 0))
        count += 1
        self.login_failures[ip] = (count, time.time() + LOCK_SECONDS if count >= MAX_LOGIN_FAILURES else 0)
