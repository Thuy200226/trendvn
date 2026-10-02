"""Supported source platforms and what makes a source video URL canonical."""

import re
from collections import namedtuple
from urllib.parse import urlsplit, urlunsplit

Platform = namedtuple("Platform", "id name country domains min_views")

# THE list of source platforms. Everything else that needs a platform's name, country, domains or default views bar is derived from
# here (the dashboard labels, the settings defaults and form fields, banned hashtags, task texts). Adding a source = one line here
# + one module and one line in the agent's collector/sources/__init__.py.
REGISTRY = (
    Platform("douyin", "Douyin", "CN", ("douyin.com",), 0),
    Platform("kuaishou", "Kuaishou", "CN", ("kuaishou.com",), 1_000_000),
    Platform("tiktok", "TikTok", "US", ("tiktok.com",), 1_000_000),
    Platform("instagram", "Instagram", "US", ("instagram.com",), 0),
)
PLATFORMS = {p.id: p.domains for p in REGISTRY}
COUNTRIES = {p.id: p.country for p in REGISTRY}
NAMES = {p.id: p.name for p in REGISTRY}
DEFAULT_MIN_VIEWS = {p.id: p.min_views for p in REGISTRY}


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
