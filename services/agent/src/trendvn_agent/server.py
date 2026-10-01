"""Host-side TrendVN agent API: n8n and the dashboard call it, it drives Chrome. Listens only on the project's private Docker bridge."""

import hmac
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .config import ENV, TOKEN
from .log import log
from .worker_client import worker

BIND = ENV.get("TRENDVN_AGENT_BIND", "172.20.0.1")
PORT = int(ENV.get("TRENDVN_AGENT_PORT", "5682"))
browser_lock = threading.Lock()  # one Chrome job at a time: profiles cannot be shared and sites throttle parallel scans


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
    from . import publisher

    status = publisher.session_status()
    logged_in = status.get("logged_in", False)
    worker(
        "/api/heartbeat",
        {"component": "publisher", "ok": logged_in, "detail": "Đã đăng nhập TikTok, sẵn sàng" if logged_in else status.get("reason")},
    )
    return status


def stats(payload):
    from . import publisher

    return publisher.run_stats()


def verify(payload):
    from . import publisher

    return publisher.verify_unresolved()


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
            payload = json.loads(self.rfile.read(length) or b"{}") if length else {}
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
