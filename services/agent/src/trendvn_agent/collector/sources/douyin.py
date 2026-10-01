"""Douyin (CN): the "jingxuan" feed."""

from ..capture import capture
from ..normalize import to_int


def parse_douyin(payload):
    items = []
    for a in payload.get("aweme_list") or []:
        if not isinstance(a, dict) or a.get("aweme_type") != 0 or a.get("is_ads") or not a.get("video"):
            continue
        stats = a.get("statistics") or {}
        vid = str(a.get("aweme_id") or "")
        urls = ((a["video"].get("play_addr") or {}).get("url_list")) or []
        urls = [u for u in urls if isinstance(u, str) and u.startswith("http")]
        if not vid or not urls or not stats:
            continue
        urls = [u.replace("http://", "https://", 1) for u in urls]
        duration = (a.get("duration") or a["video"].get("duration") or 0) / 1000
        items.append(
            {
                "source_id": vid,
                "url": "https://www.douyin.com/video/" + vid,
                "title": str(a.get("desc") or "")[:500],
                "likes": to_int(stats.get("digg_count")),
                "views": None,
                "duration": duration,
                "created": to_int(a.get("create_time")),
                "media": {"kind": "direct", "url": urls[0], "referer": "https://www.douyin.com/"},
            }
        )
    return items


def scan_douyin(ctx):
    return {
        "jingxuan": capture(
            ctx,
            "https://www.douyin.com/jingxuan",
            lambda u: "/aweme/v2/web/module/feed" in u or "/aweme/v1/web/tab/feed" in u,
            parse_douyin,
        )
    }
