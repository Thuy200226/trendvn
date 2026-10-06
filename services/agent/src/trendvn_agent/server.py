"""Host-side TrendVN agent API: n8n and the dashboard call it, it drives Chrome. Listens only on the project's private Docker bridge."""

import hmac
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import ENV, TOKEN
from .log import log
from .worker_client import worker, worker_get

BIND = ENV.get("TRENDVN_AGENT_BIND", "172.20.0.1")
PORT = int(ENV.get("TRENDVN_AGENT_PORT", "5682"))
browser_lock = threading.Lock()  # one Chrome job at a time: profiles cannot be shared and sites throttle parallel scans
MAX_BODY = 1024 * 1024  # a job request is a few small fields; anything bigger is refused before it is read
SOCKET_TIMEOUT = 30  # seconds a caller may stall mid-request


# ------------------------------------------------------------------ jobs (imports are lazy: Playwright loads only when a job runs)
def collect(payload):
    from . import collector

    platforms = payload.get("platforms") if isinstance(payload.get("platforms"), list) else None
    if platforms and any(p not in collector.SOURCES for p in platforms):
        raise ValueError("Unknown platform")
    return {"report": collector.collect(platforms, download_media=payload.get("download", True))}


def publish(payload):
    from . import publisher

    return publisher.run_publish(payload.get("job_id"))


def dry_run(payload):
    from . import publisher

    return publisher.dry_run_next(payload.get("job_id"))


def session(payload):
    """Is the browser signed in to each enabled account? One heartbeat for the publisher, with the answer per account."""
    from . import publisher

    accounts = [(a["id"], a["username"]) for a in worker_get("/api/status").get("accounts", []) if a["enabled"]]
    results = {}
    for account, username in accounts or [("main", "")]:
        results[account] = (username, publisher.session_status(account=account, expected=username or None))
    logins = {account: bool(status.get("logged_in")) for account, (_, status) in results.items()}
    missing = ["@%s" % (username or account) for account, (username, _) in results.items() if not logins[account]]
    ok = not missing
    detail = {
        "login": logins,
        "text": "Đã đăng nhập TikTok, sẵn sàng" if ok else "Chưa đăng nhập: " + ", ".join(missing),
    }
    worker("/api/heartbeat", {"component": "publisher", "ok": ok, "detail": detail})
    first = next(iter(results.values()))[1]
    return dict(first, accounts=logins) if len(results) > 1 else first


def stats(payload):
    from . import publisher

    return publisher.run_stats()


def verify(payload):
    from . import publisher

    return publisher.verify_unresolved()


def search_videos(payload):
    from .search import search

    return search(payload)


def search_download(payload):
    from .search import download_selected

    return download_selected(payload)


def search_open(payload):
    from .search import search

    return search(payload, human=True)


def _channel_args(payload):
    from . import channels
    from .search import _account

    channel = payload.get("channel")
    if channel not in channels.NAMES:
        raise ValueError("Kênh không hợp lệ")
    return channels, _account(payload), channel


def channel_login(payload):
    channels, account, channel = _channel_args(payload)
    return channels.login(account, channel)


def channel_check(payload):
    channels, account, channel = _channel_args(payload)
    return channels.check(account, channel)


ROUTES = {
    "/api/channel/login": channel_login,
    "/api/channel/check": channel_check,
    "/api/search/open": search_open,
    "/api/search": search_videos,
    "/api/search/download": search_download,
    "/api/collect": collect,
    "/api/publish": publish,
    "/api/session": session,
    "/api/verify": verify,
    "/api/dry-run": dry_run,
    "/api/stats": stats,
}


class Handler(BaseHTTPRequestHandler):
    server_version = "TrendVNAgent/1.0"
    timeout = SOCKET_TIMEOUT

    def version_string(self):
        return "TrendVNAgent"

    def log_message(self, fmt, *args):
        pass

    def send(self, code, data):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self):
        presented = self.headers.get("Authorization", "").encode("utf-8")  # bytes: str with non-ASCII raises in compare_digest
        return hmac.compare_digest(presented, ("Bearer " + TOKEN).encode("utf-8"))

    def do_GET(self):
        if self.path == "/health":
            return self.send(200, {"ok": True, "service": "trendvn-agent", "busy": browser_lock.locked()})
        self.send(404, {"error": "Not found"})

    def do_POST(self):
        if not self.authorized():
            return self.send(401, {"error": "Authentication required"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= MAX_BODY:
                return self.send(413, {"error": "Request too large"})
            payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
            if not isinstance(payload, dict):
                raise ValueError("payload must be an object")
        except Exception:
            return self.send(400, {"error": "Invalid JSON"})
        job = ROUTES.get(self.path)
        if not job:
            return self.send(404, {"error": "Not found"})
        if not browser_lock.acquire(blocking=False):
            return self.send(409, {"error": "Agent busy with another browser job"})
        try:
            self.send(200, job(payload))
        except Exception as error:
            log("ERROR %s: %s" % (self.path, traceback.format_exc()[-600:]))
            self.send(500, {"error": str(error)[:300]})
        finally:
            browser_lock.release()


def main():
    if len(TOKEN) < 32:
        raise SystemExit("TRENDVN_TOKEN missing; run ./trendvn install first")
    log("agent listening on %s:%s" % (BIND, PORT))
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
