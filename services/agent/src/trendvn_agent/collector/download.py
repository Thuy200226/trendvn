"""Fetch one video into the shared inbox."""

import json
import subprocess
import sys
from urllib.parse import urlsplit

from ..browser import proxy_for
from ..config import ENV, RUNTIME

MAX_BYTES = 250 * 1024 * 1024


CDN_SUFFIXES = (
    "zjcdn.com",
    "douyinvod.com",
    "douyincdn.com",
    "douyin.com",
    "bytecdn.cn",
    "bytedance.com",
    "ibytedtos.com",
    "tiktok.com",
    "tiktokcdn.com",
    "tiktokcdn-us.com",
    "tiktokv.com",
    "tiktokv.us",
    "kwaicdn.com",
    "yximgs.com",
    "kuaishou.com",
    "gifshow.com",
    "ksapisrv.com",
)


def ytdlp_proxy():
    """Instagram goes through yt-dlp, so it must use the same US exit as the browser (validated by proxy_for)."""
    if proxy_for("us") is None:
        return []
    return ["--proxy", ENV["TRENDVN_US_PROXY"].strip()]


def ytdlp_meta(url):
    try:
        p = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "-j", "--no-warnings", "--no-playlist", "--socket-timeout", "20", *ytdlp_proxy(), url],
            capture_output=True,
            timeout=90,
        )
        return json.loads(p.stdout) if p.returncode == 0 and p.stdout else None
    except Exception:
        return None


def download(ctx, item, platform):
    """Fetch one video into the shared inbox and return its file name. Raises on any doubt."""
    m = item["media"]
    name = "%s_%s.mp4" % (platform, item["source_id"])
    dest = RUNTIME / "inbox" / name
    tmp = dest.with_suffix(".part")
    if m["kind"] == "ytdlp":
        p = subprocess.run(
            [
                sys.executable,
                "-m",
                "yt_dlp",
                "--no-warnings",
                "--no-playlist",
                *ytdlp_proxy(),
                "-f",
                "mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
                "--merge-output-format",
                "mp4",
                "--max-filesize",
                str(MAX_BYTES),
                "-o",
                str(tmp) + ".%(ext)s",
                m["url"],
            ],
            capture_output=True,
            timeout=240,
        )
        produced = list(RUNTIME.glob("inbox/" + tmp.name + ".*"))
        if p.returncode or not produced:
            raise ValueError("yt-dlp could not download this reel")
        produced[0].rename(tmp)
    else:
        host = (urlsplit(m["url"]).hostname or "").lower()
        if not m["url"].startswith("https://") or not any(host == d or host.endswith("." + d) for d in CDN_SUFFIXES):
            raise ValueError("Media host is not a known platform CDN: " + host)
        r = ctx.request.get(m["url"], headers={"Referer": m["referer"]}, timeout=120000)
        if not r.ok:
            raise ValueError("Media HTTP %s" % r.status)
        body = r.body()
        if not 50_000 <= len(body) <= MAX_BYTES:
            raise ValueError("Media size out of range")
        tmp.write_bytes(body)
    head = tmp.read_bytes()[:12]
    if b"ftyp" not in head:
        tmp.unlink(missing_ok=True)
        raise ValueError("Downloaded file is not an MP4 container")
    tmp.replace(dest)
    return name
