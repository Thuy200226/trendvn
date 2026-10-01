"""Sending responses: JSON/HTML with the security headers, gzip, and redirects after a form post."""

import gzip
import json
from urllib.parse import quote

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
    "media-src 'self'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'"
)
GZIP_MIN_BYTES = 1500


class ResponseMixin:
    """Mixed into the request handler: `send` and `redirect`."""

    def send(self, code, data, kind="application/json; charset=utf-8", extra=None):
        body = json.dumps(data, ensure_ascii=False) if not isinstance(data, (str, bytes)) else data
        body = body.encode() if isinstance(body, str) else body
        compress = (
            len(body) > GZIP_MIN_BYTES
            and "gzip" in self.headers.get("Accept-Encoding", "")
            and (kind.startswith("text/") or "json" in kind)
        )
        if compress:
            body = gzip.compress(body, 5)
        self.send_response(code)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # 'no-referrer' would make Chrome send `Origin: null` on form posts, which once broke every button
        self.send_header("Referrer-Policy", "same-origin")
        if compress:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        if kind.startswith("text/html"):
            self.send_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, key=None, err=None, anchor=""):
        """303 back to the dashboard with a flash message: `key` names a success text, `err` carries an error text."""
        query = "?ok=" + key if key else "?err=" + quote(err[:200], safe="") if err else ""
        self.send_response(303)
        self.send_header("Location", "/" + query + anchor)
        self.end_headers()

    def redirect_to(self, location, cookie=None):
        self.send_response(303)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Location", location)
        self.end_headers()
