"""Which videos are worth taking: freshness, length and engagement gates, and a "newly trending" score."""

import time

MAX_DURATION = 180
# A topic tab (music, pets, food...) is a smaller pond than the general feed: measured on 520 live Douyin videos, only 12% of a tab's
# videos reach the general feed's 150k-like bar, while the tab's median is 10-70k. Topic streams use this share of the thresholds.
TOPIC_FACTOR = 0.15
# Their videos are also older: the median age is 39 days (p25: 17), and a 7-day freshness limit lets 10% through. Topic streams may be
# this many times older than the general limit (28 days at the default); the score still prefers the fresher ones.
TOPIC_AGE_FACTOR = 4


def rotate(available, limit, now=None):
    """At most `limit` of `available`, rotating with the clock (every 3 hours) so that, scan after scan, every one gets its turn."""
    if len(available) <= limit:
        return list(available)
    start = int((now if now is not None else time.time()) // 10800) % len(available)
    return [available[(start + i) % len(available)] for i in range(limit)]


def age_hours(item, now=None):
    created = item.get("created")
    return max(0.0, ((now or time.time()) - created) / 3600) if created else None


def qualifies(platform, item, thresholds, now=None, topic_stream=False):
    """Engagement, length, freshness and structure gates applied before anything reaches the queue.
    topic_stream: the video comes from a category tab, which gets the lower engagement bar described at TOPIC_FACTOR."""
    age = age_hours(item, now)
    if age is not None and age > 24 * thresholds.get("max_age_days", 7) * (TOPIC_AGE_FACTOR if topic_stream else 1):
        return False
    duration = item.get("duration")
    if duration is None and platform == "instagram":
        pass  # yt-dlp omits it for some reels; the worker probes the real file and enforces the limit
    elif not 1 <= (duration or 0) <= min(MAX_DURATION, thresholds.get("max_duration", MAX_DURATION)):
        return False
    share = TOPIC_FACTOR if topic_stream else 1
    min_views = int((thresholds.get("min_views") or {}).get(platform, 0) * share)
    min_likes = int((thresholds.get("min_likes") or {}).get(platform, 0) * share)
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


def choose_downloads(pending, scores, wanted, limit):
    """Which candidates to download now. Videos whose topic hint is a topic no account takes are skipped (no hint = unknown, kept);
    the rest are taken round-robin across hints, best score first within each, so one busy topic cannot crowd out the others.
    `pending` are the worker's candidates (with `topic_hint`), `scores` maps source_id -> score."""
    groups = {}
    for job in pending:
        hint = job.get("topic_hint")
        if wanted and hint is not None and hint not in wanted:
            continue
        groups.setdefault(hint, []).append(job)
    best_first = lambda job: -scores.get(job["source_id"], 0)  # noqa: E731
    queues = [sorted(group, key=best_first) for group in groups.values()]
    queues.sort(key=lambda queue: best_first(queue[0]))  # the group with the best video goes first in each round
    chosen = []
    while queues and len(chosen) < limit:
        for queue in list(queues):
            if len(chosen) >= limit:
                break
            chosen.append(queue.pop(0))
            if not queue:
                queues.remove(queue)
    return chosen
