"""The stylesheet and the script, kept as real files (static/app.css, static/app.js) and inlined into the page at start-up."""

from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"
CSS = (STATIC / "app.css").read_text(encoding="utf-8")
JS = (STATIC / "app.js").read_text(encoding="utf-8")
