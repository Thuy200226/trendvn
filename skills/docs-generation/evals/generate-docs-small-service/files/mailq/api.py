"""HTTP API: enqueue a job, read it, resolve an unknown one. Every route but /health needs the bearer token."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, store


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorised(self):
        return bool(config.TOKEN) and self.headers.get("Authorization") == "Bearer " + config.TOKEN

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"ok": True})
        if not self._authorised():
            return self._send(401, {"error": "token"})
        if self.path.startswith("/api/jobs/"):
            row = store.connect().execute("SELECT id, state, attempts FROM jobs WHERE id=?", (self.path.rsplit("/", 1)[1],)).fetchone()
            return self._send(200 if row else 404, dict(row) if row else {"error": "no such job"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authorised():
            return self._send(401, {"error": "token"})
        body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 1 << 20)) or b"{}")
        if self.path == "/api/jobs":
            return self._send(201, {"id": store.enqueue(store.connect(), body["to"], body["subject"], body["body"])})
        if self.path.endswith("/resolve"):
            ok = store.resolve(store.connect(), self.path.split("/")[-2], body.get("answer"))
            return self._send(200 if ok else 409, {"ok": ok})
        self._send(404, {"error": "not found"})


def serve():
    ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler).serve_forever()
