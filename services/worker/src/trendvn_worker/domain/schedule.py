"""Posting windows ("golden hours") and local-day arithmetic. Pure functions: time and timezone are arguments."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo


def local_now(timezone, now=None):
    """The current moment as a timezone-aware datetime."""
    return datetime.fromtimestamp(now or time.time(), ZoneInfo(timezone))


def day_start(timezone, now=None):
    """Start of the local day containing `now`, as Unix seconds."""
    return local_now(timezone, now).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def window_state(windows, timezone, now=None):
    """(inside_window, human text of the next opening). No windows configured means any time."""
    if not windows:
        return True, ""
    moment = local_now(timezone, now)
    hour = moment.hour + moment.minute / 60
    if any(start <= hour < end for start, end in windows):
        return True, ""
    later = sorted(start for start, _ in windows if start > hour)
    opening = later[0] if later else sorted(start for start, _ in windows)[0]
    return False, "%02d:00 %s" % (opening, "hôm nay" if later else "ngày mai")
