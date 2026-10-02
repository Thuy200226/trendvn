"""TikTok (US): the explore page, one category chip at a time."""

import re

from ...log import log
from ..capture import Blocked, NotThere, capture
from ..normalize import to_int
from ..rules import rotate


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
        chip = page.locator('[data-e2e="explore-category-chip"]', has_text=re.compile("^" + re.escape(text) + "$")).first
        try:
            chip.wait_for(
                timeout=6000
            )  # the chips appear a moment after the first answer; only a chip still missing after that is "not there"
        except Exception:
            raise NotThere(text) from None
        chip.click(timeout=8000)

    return go


# The explore page's category chips (US site). topic -> chip name; chips we cannot find are skipped without retries.
CHIPS = {
    "music": "Singing & Dancing",
    "comedy": "Comedy",
    "pets": "Animals",
    "food": "Food",
    "family": "Family",
    "beauty": "Beauty Care",
    "sports": "Sports",
    "gaming": "Games",
    "anime": "Anime & Comics",
    "movies": "Shows",
    "lifestyle": "Daily Life",
    "knowledge": "Education",
}
DEFAULT_TOPICS = ("music", "comedy", "movies")
MAX_CHIPS = 5


def scan_tiktok(ctx, topics=()):
    """One stream per wanted topic that has a chip (the default few when no account has wishes), each from a fresh page load."""
    wanted = rotate([t for t in topics if t in CHIPS], MAX_CHIPS) or list(DEFAULT_TOPICS)
    out = {}
    for topic in wanted:
        try:
            items = capture(
                ctx,
                "https://www.tiktok.com/explore",
                lambda u: "/api/explore/item_list/" in u,
                parse_tiktok,
                scrolls=2,
                wait_ms=9000,
                before_scroll=click_chip(CHIPS[topic]),
            )
            out["explore_" + topic] = [dict(item, topic=topic) for item in items]
        except Blocked:
            raise
        except NotThere as e:
            log("tiktok chip %s not found; skipped" % e)
            out["explore_" + topic] = []
        except Exception as e:
            log("tiktok chip %s failed: %s" % (CHIPS[topic], str(e)[:120]))
            out["explore_" + topic] = []
    return out
