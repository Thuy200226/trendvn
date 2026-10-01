"""The platforms we read. Adding a source = one module here with `parse_*` (pure, unit-tested) and `scan_*`, plus one line below."""

from .douyin import scan_douyin
from .instagram import scan_instagram
from .kuaishou import scan_kuaishou
from .tiktok import scan_tiktok

SOURCES = {
    # geo_locked: the feed depends on the viewer's IP, so the exit country must match. Douyin and Kuaishou only serve
    # mainland-China content, so any IP sees the same source.
    "douyin": {"country": "CN", "locale": "zh-CN", "scan": scan_douyin, "geo_locked": False},
    "kuaishou": {"country": "CN", "locale": "zh-CN", "scan": scan_kuaishou, "geo_locked": False},
    "tiktok": {"country": "US", "locale": "en-US", "scan": scan_tiktok, "geo_locked": True},
    "instagram": {"country": "US", "locale": "en-US", "scan": scan_instagram, "geo_locked": True},
}
