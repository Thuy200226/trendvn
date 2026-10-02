"""Supported source platforms and what makes a source video URL canonical."""

import re
from urllib.parse import urlsplit, urlunsplit

PLATFORMS = {"douyin": ("douyin.com",), "kuaishou": ("kuaishou.com",), "tiktok": ("tiktok.com",), "instagram": ("instagram.com",)}


COUNTRIES = {"douyin": "CN", "kuaishou": "CN", "tiktok": "US", "instagram": "US"}


def canonical_url(platform, value):
    if platform not in PLATFORMS:
        raise ValueError("Unsupported platform")
    u = urlsplit(value)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or u.username or u.password or u.port not in (None, 443):
        raise ValueError("HTTPS source URL required")
    if not any(host == d or host.endswith("." + d) for d in PLATFORMS[platform]):
        raise ValueError("Source domain does not match platform")
    if not u.path or u.path == "/":
        raise ValueError("A video URL is required")
    # Share redirects are not stable IDs; resolve in the collector before ingest.
    if host in ("vm.tiktok.com", "vt.tiktok.com", "v.douyin.com", "v.kuaishou.com"):
        raise ValueError("Resolve short share link to canonical video URL first")
    return urlunsplit(("https", host, u.path.rstrip("/"), "", ""))


POST_URL = re.compile(r'https://[A-Za-z0-9.-]+\.tiktok\.com/[^\s"<>\\]{1,300}')


def valid_post_url(url):
    """A link to a published TikTok post as the owner's browser would show it (stored and later rendered as a link)."""
    return bool(POST_URL.fullmatch(url or ""))
