"""Instagram Reels (US): reel codes from the public Reels page, details through yt-dlp."""

import re

from ...log import log
from ..capture import Blocked, looks_blocked
from ..download import ytdlp_meta
from ..normalize import to_int


def parse_instagram_codes(text):
    """Reel shortcodes visible on the public Reels page (order preserved, de-duplicated)."""
    seen, codes = set(), []
    for m in re.finditer(r"/reels?/([A-Za-z0-9_-]{6,20})/", text):
        c = m.group(1)
        if c not in seen and c != "audio":
            seen.add(c)
            codes.append(c)
    for m in re.finditer(r'"code":"([A-Za-z0-9_-]{8,14})"', text):
        c = m.group(1)
        if c not in seen:
            seen.add(c)
            codes.append(c)
    return codes


def scan_instagram(ctx):
    page = ctx.new_page()
    try:
        try:
            page.goto("https://www.instagram.com/reels/", wait_until="commit", timeout=60000)
        except Exception as e:
            log("instagram goto warning: " + str(e)[:100])
        page.wait_for_timeout(9000)
        codes = []
        for _ in range(4):
            codes = parse_instagram_codes(page.content())
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(2500)
        codes = parse_instagram_codes(page.url + " " + page.content()) or codes
        if not codes and looks_blocked(page):
            raise Blocked("login wall shown")
    finally:
        page.close()
    items = []
    for n, code in enumerate(codes[:14], 1):
        meta = ytdlp_meta("https://www.instagram.com/reel/%s/" % code)
        if not meta:
            continue
        items.append(
            {
                "source_id": code,
                "url": "https://www.instagram.com/reel/%s/" % code,
                "title": str(meta.get("description") or meta.get("title") or "")[:500],
                "likes": to_int(meta.get("like_count")),
                "views": to_int(meta.get("view_count")),
                "duration": meta.get("duration"),
                "created": to_int(meta.get("timestamp")),
                "rank": n,
                "media": {"kind": "ytdlp", "url": "https://www.instagram.com/reel/%s/" % code},
            }
        )
    return {"reels": items}
