"""Host-side TrendVN agent API: n8n and the dashboard call it, it drives Chrome. Listens only on the project's private Docker bridge."""

import hmac
import json
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import ENV, TOKEN
from .limits import JOB_SECONDS
from .log import log
from .worker_client import worker, worker_get

BIND = ENV.get("TRENDVN_AGENT_BIND", "172.20.0.1")
PORT = int(ENV.get("TRENDVN_AGENT_PORT", "5682"))
browser_lock = threading.Lock()  # one Chrome job at a time: profiles cannot be shared and sites throttle parallel scans
current = {"job": None, "since": 0.0}  # what holds the lock and since when (shown by /health)
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
        "text": (
            "\u0110\u00e3 \u0111\u0103ng nh\u1eadp TikTok, s\u1eb5n s\u00e0ng"
            if ok
            else "Ch\u01b0a \u0111\u0103ng nh\u1eadp: " + ", ".join(missing)
        ),
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


def overdue(path):
    """A job has run longer than its limit (limits.py). It is not stopped; the owner is told, because the browser stays busy and every
    later call gets 409 until it ends or the agent restarts. Never raises: this runs on a timer thread."""
    minutes = int(JOB_SECONDS.get(path, 1800) // 60)
    log("job %s still running after %d minutes" % (path, minutes))
    try:
        worker(
            "/api/alert",
            {"step": "agent " + path, "detail": "still running after %d minutes; the browser is busy until it ends" % minutes},
            timeout=30,
        )
    except Exception as error:
        log("could not send the overdue alert: " + str(error)[:120])


ROUTES = {
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
            busy = browser_lock.locked()
            job = current["job"] if busy else None
            return self.send(
                200,
                {
                    "ok": True,
                    "service": "trendvn-agent",
                    "busy": busy,
                    "job": job,
                    "busy_for": int(time.monotonic() - current["since"]) if job else 0,
                },
            )
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
        current.update(job=self.path, since=time.monotonic())
        timer = threading.Timer(JOB_SECONDS.get(self.path, 1800), overdue, args=(self.path,))
        timer.daemon = True
        timer.start()
        try:
            self.send(200, job(payload))
        except Exception as error:
            log("ERROR %s: %s" % (self.path, traceback.format_exc()[-600:]))
            self.send(500, {"error": str(error)[:300]})
        finally:
            timer.cancel()
            current.update(job=None, since=0.0)
            browser_lock.release()


def main():
    if len(TOKEN) < 32:
        raise SystemExit("TRENDVN_TOKEN missing; run ./trendvn install first")
    log("agent listening on %s:%s" % (BIND, PORT))
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
