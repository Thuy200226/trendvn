"""Fetch one video into the shared inbox."""

import json
import os
import re
import subprocess
import sys

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


# https, a plain DNS name (the last label starts with a letter: no IP literals, no 0x7f.1 tricks), no user-info, no port, and a path
# without whitespace, control characters or backslash (a browser reads a backslash as a slash, Python does not, so
# `https://evil.test<backslash>@v.douyin.com/` would pass a Python host check and fetch evil.test)
MEDIA_URL = re.compile(r"https://((?:[A-Za-z0-9-]+\.)+[A-Za-z][A-Za-z0-9-]*)(?:/[^\s\\\x00-\x1f\x7f]*)?")


def cdn_host(url):
    """The host of a media URL if it is a plain https URL on a known platform CDN; otherwise ValueError."""
    match = MEDIA_URL.fullmatch(url or "")
    host = match.group(1).lower() if match else ""
    if not host or not any(host == d or host.endswith("." + d) for d in CDN_SUFFIXES):
        raise ValueError("Media host is not a known platform CDN: " + (host or "unparseable URL")[:80])
    return host


def ytdlp_env():
    """Instagram goes through yt-dlp, so it must use the same US exit as the browser (validated by proxy_for). The proxy goes in the
    environment, not on the command line, where any local user could read its password with `ps`."""
    env = dict(os.environ)
    if proxy_for("us") is not None:
        proxy = ENV["TRENDVN_US_PROXY"].strip()
        env.update(HTTP_PROXY=proxy, HTTPS_PROXY=proxy, ALL_PROXY=proxy)
    return env


def ytdlp_meta(url):
    try:
        p = subprocess.run(
            [sys.executable, "-m", "yt_dlp", "-j", "--no-warnings", "--no-playlist", "--socket-timeout", "20", url],
            capture_output=True,
            timeout=90,
            env=ytdlp_env(),
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
            env=ytdlp_env(),
        )
        produced = list(RUNTIME.glob("inbox/" + tmp.name + ".*"))
        if p.returncode or not produced:
            raise ValueError("yt-dlp could not download this reel")
        produced[0].rename(tmp)
    else:
        cdn_host(m["url"])
        r = ctx.request.get(m["url"], headers={"Referer": m["referer"]}, timeout=120000)
        if not r.ok:
            raise ValueError("Media HTTP %s" % r.status)
        body = r.body()
        if not 50_000 <= len(body) <= MAX_BYTES:
            raise ValueError("Media size out of range")
        tmp.write_bytes(body)
    with open(tmp, "rb") as produced_file:
        head = produced_file.read(12)  # only the container signature; the file can be 250 MB
    if b"ftyp" not in head:
        tmp.unlink(missing_ok=True)
        raise ValueError("Downloaded file is not an MP4 container")
    tmp.replace(dest)
    return name
