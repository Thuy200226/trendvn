"""Validation of what the collector reports: a batch of videos seen on one platform stream. Pure functions, no I/O."""

import json
import math
import re
from collections import namedtuple
from urllib.parse import urlsplit

from .platforms import COUNTRIES, PLATFORMS, canonical_url
from .topics import TOPIC_IDS

MAX_ITEMS = 100
META_KEYS = ("score", "likes", "views", "age_h", "created")

Batch = namedtuple("Batch", "platform stream observed items topic")
Item = namedtuple("Item", "source_id url rank views evidence title meta")


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def clean_item(platform, raw):
    """One reported video, checked against the platform's rules. Raises ValueError on anything out of line."""
    source_id = str(raw.get("source_id", ""))
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", source_id):
        raise ValueError("Invalid source_id")
    url = canonical_url(platform, raw.get("url", ""))
    if source_id not in urlsplit(url).path.split("/"):
        raise ValueError("source_id must match canonical video URL")
    if raw.get("country") != COUNTRIES[platform]:
        raise ValueError("Wrong source country")
    rank = raw.get("rank")
    if rank is not None and (type(rank) is not int or rank < 1):
        raise ValueError("Invalid rank")
    views = raw.get("views")
    if views is not None and (type(views) is not int or views < 0):
        raise ValueError("Invalid views")
    evidence = raw.get("evidence_url", "")
    if not isinstance(evidence, str) or not evidence.startswith("https://"):
        raise ValueError("Evidence URL required")
    reported = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    meta = {key: reported[key] for key in META_KEYS if _is_number(reported.get(key))}
    return Item(source_id, url, rank, views, evidence, str(raw.get("title", ""))[:500], json.dumps(meta) if meta else None)


def validate_batch(batch, now):
    """A whole report from the collector -> Batch. Nothing is stored unless every item passes."""
    if not isinstance(batch, dict) or not isinstance(batch.get("items"), list) or len(batch["items"]) > MAX_ITEMS:
        raise ValueError("Batch must have at most %d items" % MAX_ITEMS)
    platform = batch.get("platform")
    if platform not in PLATFORMS:
        raise ValueError("Unknown platform")
    stream = batch.get("stream", "")
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", stream):
        raise ValueError("Invalid stream")
    observed = batch.get("observed_at")
    if not _is_number(observed):
        raise ValueError("observed_at must be Unix timestamp")
    if not now - 86400 <= observed <= now + 60:
        raise ValueError("Stale/future batch")
    topic = batch.get("topic")  # the source's own category for this stream (a Douyin tab, a TikTok chip), if it has one
    if topic is not None and topic not in TOPIC_IDS:
        raise ValueError("Unknown topic")
    return Batch(platform, platform + ":" + stream, observed, [clean_item(platform, raw) for raw in batch["items"]], topic)
