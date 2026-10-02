"""The stylesheet and the script, kept as real files (static/app.css, static/app.js) and inlined into the page at start-up."""

import base64
import hashlib
from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
# Content-Security-Policy hash of the inline script, so the page can run exactly this script and no other
JS_SHA256 = base64.b64encode(hashlib.sha256(JS.encode("utf-8")).digest()).decode()
