"""Which videos are worth taking: freshness, length and engagement gates, and a "newly trending" score."""

import time

MAX_DURATION = 180


def age_hours(item, now=None):
    created = item.get("created")
    return max(0.0, ((now or time.time()) - created) / 3600) if created else None


def qualifies(platform, item, thresholds, now=None):
    """Engagement, length, freshness and structure gates applied before anything reaches the queue."""
    age = age_hours(item, now)
    if age is not None and age > 24 * thresholds.get("max_age_days", 7):
        return False
    duration = item.get("duration")
    if duration is None and platform == "instagram":
        pass  # yt-dlp omits it for some reels; the worker probes the real file and enforces the limit
    elif not 1 <= (duration or 0) <= min(MAX_DURATION, thresholds.get("max_duration", MAX_DURATION)):
        return False
    min_views = (thresholds.get("min_views") or {}).get(platform, 0)
    min_likes = (thresholds.get("min_likes") or {}).get(platform, 0)
    if item.get("views") is not None and item["views"] < min_views:
        return False
    if min_likes and item.get("likes") is not None and item["likes"] < min_likes:
        return False
    if min_views and item.get("views") is None and platform != "instagram":
        return False
    return True


def score(platform, item, weights=None, now=None):
    """Newly-trending score: engagement per (softened) hour of age, nudged by how well this source performed for us.
    Views are used when the site shows them; otherwise likes stand in (about 4% of viewers like a video)."""
    base = item.get("views") or (item.get("likes") or 0) * 25
    age = age_hours(item, now)
    per_hour = base / (max(age, 6.0) ** 0.6) if age is not None else base / 24**0.6
    return round(per_hour * (weights or {}).get(platform, 1.0))
