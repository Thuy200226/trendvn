"""Serving files from the data folder to the dashboard (videos, posters, screenshots) with HTTP Range support for seeking."""

import re
from pathlib import Path
from urllib.parse import unquote

CHUNK = 1 << 16
SERVED_TYPES = {
    ".mp4": "video/mp4",
    ".jpg": "image/jpeg",
    ".png": "image/png",
    ".wav": "audio/wav",
}  # nothing else is ever sent to a browser
SHOT_NAME = re.compile(r"shot_\d{9,12}\.png")
JOB_ID = re.compile(r"[0-9a-f]{32}")


def resolve(store, path):
    """Map a /media/... URL path to a file inside the data folder, or None."""
    parts = unquote(path).split("/")[2:]
    if parts == ["voice-sample"]:
        return store.root / "exports" / "voice_sample.wav"
    if len(parts) == 2 and parts[0] == "shot" and SHOT_NAME.fullmatch(parts[1]):
        return store.root / "exports" / parts[1]
    if len(parts) == 2 and JOB_ID.fullmatch(parts[0]) and parts[1] in ("final", "source", "poster"):
        with store.connect() as db:
            row = db.execute("SELECT output_file, source_file FROM jobs WHERE id=?", (parts[0],)).fetchone()
        if not row:
            return None
        if parts[1] == "poster":
            return Path(row["output_file"]).with_name("poster.jpg") if row["output_file"] else None
        return Path((row["output_file"] if parts[1] == "final" else row["source_file"]) or "")
    return None


def byte_range(header, size):
    """(start, end, is_partial) for a Range header, or None when it cannot be satisfied."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header or "")
    if not (match and (match.group(1) or match.group(2))):
        return 0, size - 1, False
    if match.group(1):
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else size - 1
    else:
        start, end = max(0, size - int(match.group(2))), size - 1
    if start > end or start >= size:
        return None
    return start, min(end, size - 1), True


def serve(handler, store, path):
    """Send the file for `path`, or a 404/416. Only files that live under the data folder are ever served."""
    try:
        file = resolve(store, path)
        file = file.resolve() if file else None
        if not file or not file.is_file() or store.root not in file.parents:
            return handler.send(404, {"error": "Not found"})
    except OSError:
        return handler.send(404, {"error": "Not found"})
    size = file.stat().st_size
    span = byte_range(handler.headers.get("Range", ""), size)
    if span is None:
        return handler.send(416, {"error": "Bad range"}, extra={"Content-Range": "bytes */%d" % size})
    start, end, partial = span
    handler.send_response(206 if partial else 200)
    handler.send_header("Content-Type", SERVED_TYPES.get(file.suffix.lower(), "application/octet-stream"))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    if partial:
        handler.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "private, max-age=60")
    handler.end_headers()
    with open(file, "rb") as source:
        source.seek(start)
        left = end - start + 1
        while left > 0:
            chunk = source.read(min(CHUNK, left))
            if not chunk:
                break
            try:
                handler.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            left -= len(chunk)
