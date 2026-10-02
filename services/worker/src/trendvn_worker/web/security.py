"""Who may see what: the bearer token for the API, loopback or a password session for the dashboard."""

import hmac
import time

SESSION_COOKIE = "tv_session"
SESSION_SECONDS = 7 * 24 * 3600  # a password session lasts a week; /logout ends it earlier
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
        # only someone who knew the password ever receives this value; changing the password invalidates every session
        key = config.token.encode()
        self.session_value = hmac.new(key, b"dashboard-session\0" + config.ui_password.encode(), "sha256").hexdigest()
        self.login_failures = {}  # ip -> (count, locked_until)

    def authorized(self, headers):
        """The API caller presented the right bearer token."""
        return same(headers.get("Authorization", ""), "Bearer " + self.config.token)

    def host_ok(self, headers):
        return headers.get("Host", "") in self.config.ui_hosts

    def session_ok(self, headers):
        for part in headers.get("Cookie", "").split(";"):
            name, _, value = part.strip().partition("=")
            if name == SESSION_COOKIE and same(value, self.session_value):
                return True
        return False

    def local_ui(self, headers, peer=""):
        """The dashboard is open without a password only on this machine: the Host header says localhost AND the connection itself
        came from this machine (a forged Host header from the network is not enough). Any other host you allow (TRENDVN_UI_HOSTS)
        needs the password from TRENDVN_UI_PASSWORD; without one, such hosts are refused outright."""
        host = headers.get("Host", "")
        if host in self.config.loopback_hosts and peer in self.config.trusted_peers:
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
