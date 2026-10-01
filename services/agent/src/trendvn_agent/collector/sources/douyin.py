"""Douyin (CN): the "jingxuan" feed."""

import time

from ..capture import Blocked, capture_streams
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


# Douyin's own category tabs on the jingxuan page (measured on the live site: each returns about 40 videos of its own). topic -> tab name.
TABS = {
    "music": "音乐",
    "comedy": "小剧场",
    "pets": "动物",
    "food": "美食",
    "travel": "旅行",
    "family": "亲子",
    "beauty": "美妆穿搭",
    "sports": "体育",
    "gaming": "游戏",
    "anime": "二次元",
    "movies": "影视",
    "lifestyle": "生活vlog",
    "knowledge": "知识",
}
MAX_TABS = 6  # tabs read per scan; with more topics wanted they take turns, so a scan stays about a minute longer, not ten


def tabs_this_scan(topics, now=None):
    """The wanted topics that have a tab, at most MAX_TABS of them, rotating with the clock (every 3 hours) so all get their turn."""
    available = [t for t in topics if t in TABS]
    if len(available) <= MAX_TABS:
        return available
    start = int((now if now is not None else time.time()) // 10800) % len(available)
    return [available[(start + i) % len(available)] for i in range(MAX_TABS)]


def click_tab(label):
    def go(page):
        # a login pop-up usually covers the page and swallows real clicks; the tab's own click handler still works
        page.locator(".semi-tabs-tab", has_text=label).first.dispatch_event("click", timeout=8000)

    return go


def tag_topic(items, topic):
    for item in items:
        item["topic"] = topic
    return items


def scan_douyin(ctx, topics=()):
    """The featured feed, plus one stream per wanted topic that has a tab (all from a single page load)."""
    wanted = tabs_this_scan(topics)
    streams = [("jingxuan", None)] + [("jingxuan_" + t, click_tab(TABS[t])) for t in wanted]
    found = capture_streams(
        ctx,
        "https://www.douyin.com/jingxuan",
        lambda u: "/aweme/v2/web/module/feed" in u or "/aweme/v1/web/tab/feed" in u,
        parse_douyin,
        streams,
    )
    if not found["jingxuan"] and not any(found.values()):
        raise Blocked("no videos returned")
    for t in wanted:
        tag_topic(found["jingxuan_" + t], t)
    return found
