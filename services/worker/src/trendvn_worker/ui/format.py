"""Small formatting helpers shared by every part of the dashboard."""

import html
import json
import re
import time

escape = html.escape


def ago(timestamp, now=None):
    """'3 giờ trước' for a Unix time; '—' when unknown."""
    if not timestamp:
        return "—"
    seconds = int((now or time.time()) - timestamp)
    if seconds < 60:
        return "vừa xong"
    for divisor, unit in ((86400, "ngày"), (3600, "giờ"), (60, "phút")):
        if seconds >= divisor:
            return "%d %s trước" % (seconds // divisor, unit)
    return "—"


def num(value):
    """1234567 -> '1.234.567' (Vietnamese thousands separator); '—' for anything that is not a number."""
    return format(int(value), ",").replace(",", ".") if isinstance(value, (int, float)) else "—"


def meta_of(job):
    """The collector's numbers for a job (score, likes, views, age) as a dict, tolerating a missing or damaged column."""
    try:
        return json.loads(job.get("meta") or "{}")
    except Exception:
        return {}


def left_text(seconds):
    """'2 giờ 50 phút', '35 phút', 'dưới 1 phút': how long a wait still has to run."""
    minutes = max(0, int(seconds)) // 60
    if minutes < 1:
        return "dưới 1 phút"
    hours, minutes = divmod(minutes, 60)
    return ("%d giờ %d phút" % (hours, minutes)) if hours and minutes else ("%d giờ" % hours if hours else "%d phút" % minutes)


def shown_of(shown, total):
    """'30 trong 45' when a list was cut short, the plain number when it was not: a heading must not promise more rows than the table has."""
    return "%d trong %d" % (shown, total) if total > shown else str(total)


def windows_text(windows):
    """[[11, 14], [19, 23]] -> '11-14, 19-23'."""
    return ", ".join("%d-%d" % (start, end) for start, end in windows)


def headline(row, limit=90):
    """HTML naming a video on a list: its Vietnamese caption (hashtags left out) when it has one, with the source title in small grey
    type under it; just the title otherwise. The source title is Chinese for most videos, so alone it tells the owner nothing."""
    title = str(row.get("title") or "")
    caption = re.sub(r"\s+", " ", re.sub(r"#\w+", "", str(row.get("caption_vi") or ""))).strip()
    if not caption:
        return escape(title[:limit])
    return '%s<div class="muted small">%s</div>' % (escape(caption[:limit]), escape(title[:limit]))
