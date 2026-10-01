"""TikTok (US): the explore page, one category chip at a time."""

import re

from ...log import log
from ..capture import Blocked, capture
from ..normalize import to_int


def parse_tiktok(payload):
    items = []
    for it in payload.get("itemList") or []:
        if not isinstance(it, dict) or it.get("isAd") or not it.get("video") or not it.get("id"):
            continue
        vid = str(it["id"])
        user = (it.get("author") or {}).get("uniqueId") or ""
        if not re.fullmatch(r"\d{6,25}", vid) or not re.fullmatch(r"[A-Za-z0-9._-]{1,50}", user):
            continue
        v = it["video"]
        media = v.get("downloadAddr") or v.get("playAddr")
        if not media:
            continue
        stats = it.get("stats") or {}
        items.append(
            {
                "source_id": vid,
                "url": f"https://www.tiktok.com/@{user}/video/{vid}",
                "title": str(it.get("desc") or "")[:500],
                "likes": to_int(stats.get("diggCount")),
                "views": to_int(stats.get("playCount")),
                "duration": v.get("duration") or 0,
                "created": to_int(it.get("createTime")),
                "media": {"kind": "direct", "url": media, "referer": "https://www.tiktok.com/"},
                "origin_country": it.get("locationCreated"),
            }
        )
    return items


def click_chip(text):
    def go(page):
        page.locator('[data-e2e="explore-category-chip"]', has_text=re.compile("^" + re.escape(text) + "$")).first.click(timeout=8000)

    return go


TIKTOK_CHIPS = [("singing_dancing", "Singing & Dancing"), ("comedy", "Comedy"), ("lipsync", "Lipsync"), ("shows", "Shows")]


def scan_tiktok(ctx):
    out = {}
    for stream, chip in TIKTOK_CHIPS:
        try:
            out[stream] = capture(
                ctx,
                "https://www.tiktok.com/explore",
                lambda u: "/api/explore/item_list/" in u,
                parse_tiktok,
                scrolls=2,
                wait_ms=9000,
                before_scroll=click_chip(chip),
            )
        except Blocked:
            raise
        except Exception as e:
            log("tiktok chip %s failed: %s" % (chip, str(e)[:120]))
            out[stream] = []
    return out
