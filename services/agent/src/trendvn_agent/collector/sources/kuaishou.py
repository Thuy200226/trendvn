"""Kuaishou (CN): the "brilliant" feed."""

import re

from ..capture import capture
from ..normalize import to_int


def parse_kuaishou(payload):
    items = []
    feeds = (((payload.get("data") or {}).get("brilliantTypeData") or {}).get("feeds")) or []
    for f in feeds:
        p = f.get("photo") if isinstance(f, dict) else None
        if not p or not p.get("id") or not p.get("photoUrl"):
            continue
        vid = str(p["id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", vid):
            continue
        items.append(
            {
                "source_id": vid,
                "url": "https://www.kuaishou.com/short-video/" + vid,
                "title": str(p.get("caption") or "")[:500],
                "likes": to_int(p.get("realLikeCount")),
                "views": to_int(p.get("viewCount")),
                "duration": (p.get("duration") or 0) / 1000,
                "created": (to_int(p.get("timestamp")) or 0) // 1000 or None,
                "media": {"kind": "direct", "url": p["photoUrl"], "referer": "https://www.kuaishou.com/"},
            }
        )
    return items


def scan_kuaishou(ctx):
    return {
        "brilliant": capture(ctx, "https://www.kuaishou.com/brilliant", lambda u: u.endswith("/graphql"), parse_kuaishou, wait_ms=14000)
    }
