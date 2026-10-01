"""Small formatting helpers shared by every part of the dashboard."""

import html
import json
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


def windows_text(windows):
    """[[11, 14], [19, 23]] -> '11-14, 19-23'."""
    return ", ".join("%d-%d" % (start, end) for start, end in windows)
