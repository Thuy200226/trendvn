"""Dashboard-changeable settings: defaults, model fallbacks and strict validation."""

import math
import re

from .platforms import DEFAULT_MIN_VIEWS, PLATFORMS

DEFAULT_TARGET = "user5706026522362"  # the account of a fresh install; real accounts live in the `accounts` table

DEFAULTS = {
    "daily_limit": 2,
    "timezone": "Asia/Ho_Chi_Minh",
    "max_duration": 180,
    "model": "gemini-3.8-flash",
    "tts_model": "gemini-3.8-flash-tts",
    "voice": "Kore",
    "caption_style": "hook",  # "hook": written to stop the scroll; "factual": the calm descriptive style
    "audio_confidence": 0.90,
    "processing_enabled": False,
    "discovery_connected": False,
    "publisher_connected": False,
    "publisher_enabled": False,
    "min_publish_gap": 3 * 3600,
    "max_candidates_per_scan": 3,
    "max_backlog": 4,
    "min_views": dict(DEFAULT_MIN_VIEWS),
    "min_likes": {"douyin": 150000},
    "post_windows": [[11, 14], [19, 23]],
    "max_age_days": 7,
    "require_approval": False,
    "voiceover_enabled": True,  # voice-over is preferred wherever it fits (narration, and one person talking whose voice is replaceable)
    "voiceover_scope": "monologue",  # "narration": only narrated videos; "monologue": also one person talking when dub_ok
    "voice_mode": "auto",  # "auto": the voice follows the speaker (gender, tone); "fixed": always the chosen voice
    "hard_sub_mask": "auto",  # blur the source's burned-in subtitles: "auto" only where our captions would overlap them, "always", "off"
    "gemini_daily_limit": 12,
    "publisher_challenge": False,
    "visibility": "public",
}


# Google retires Gemini models on a rolling basis ("no longer available to new users"). Stored settings that name a retired
# model are upgraded automatically, and media.py falls back through these chains when a call returns 404.
RETIRED_MODELS = {"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"}


RETIRED_TTS = {"gemini-2.5-flash-preview-tts", "gemini-2.5-pro-preview-tts"}


MODEL_FALLBACKS = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.7-flash"]


TTS_FALLBACKS = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]


def _int(v, lo, hi, name):
    if (
        isinstance(v, bool)
        or not isinstance(v, (int, float))
        or (isinstance(v, float) and not math.isfinite(v))
        or v != int(v)
        or not lo <= v <= hi
    ):
        raise ValueError("%s must be an integer between %s and %s" % (name, lo, hi))
    return int(v)


CHOICES = {
    "voiceover_scope": ("narration", "monologue"),
    "voice_mode": ("auto", "fixed"),
    "hard_sub_mask": ("auto", "always", "off"),
}


def validate_settings(patch):
    """Only these keys can be changed from the dashboard, each with a strict range."""
    if not isinstance(patch, dict):
        raise ValueError("Settings must be an object")
    out = {}
    for k, v in patch.items():
        if k in ("processing_enabled", "publisher_enabled", "require_approval", "voiceover_enabled"):
            if not isinstance(v, bool):
                raise ValueError(k + " must be true or false")
            out[k] = v
        elif k == "daily_limit":
            out[k] = _int(v, 1, 10, k)
        elif k == "gemini_daily_limit":
            out[k] = _int(v, 1, 500, k)
        elif k == "min_publish_gap":
            out[k] = _int(v, 0, 24 * 3600, k)
        elif k == "max_age_days":
            out[k] = _int(v, 1, 60, k)
        elif k == "max_duration":
            out[k] = _int(v, 10, 600, k)
        elif k == "max_candidates_per_scan":
            out[k] = _int(v, 1, 10, k)
        elif k == "max_backlog":
            out[k] = _int(v, 1, 20, k)
        elif k == "audio_confidence":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.5 <= v <= 0.99:
                raise ValueError("audio_confidence must be 0.5-0.99")
            out[k] = float(v)
        elif k in ("min_views", "min_likes"):
            if not isinstance(v, dict) or set(v) - set(PLATFORMS):
                raise ValueError(k + " needs per-platform numbers")
            out[k] = {p: _int(n, 0, 10**10, k + "." + p) for p, n in v.items()}
        elif k == "post_windows":
            if not isinstance(v, list) or len(v) > 6:
                raise ValueError("post_windows: at most 6 windows")
            wins = []
            for w in v:
                if not isinstance(w, (list, tuple)) or len(w) != 2:
                    raise ValueError("post_windows entries are [start, end]")
                s, e = _int(w[0], 0, 23, "window start"), _int(w[1], 1, 24, "window end")
                if s >= e:
                    raise ValueError("window start must be before end")
                wins.append([s, e])
            out[k] = wins
        elif k == "target":
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9._]{2,40}", v.lstrip("@")):
                raise ValueError("Invalid TikTok username")
            out[k] = v.lstrip("@")
        elif k == "visibility":
            if v not in ("public", "friends", "self"):
                raise ValueError("visibility must be public, friends or self")
            out[k] = v
        elif k in ("model", "tts_model"):
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z0-9._-]{3,60}", v):
                raise ValueError("Invalid model name")
            out[k] = v
        elif k == "caption_style":
            if v not in ("hook", "factual"):
                raise ValueError("caption_style must be hook or factual")
            out[k] = v
        elif k in CHOICES:
            if v not in CHOICES[k]:
                raise ValueError("%s must be one of: %s" % (k, ", ".join(CHOICES[k])))
            out[k] = v
        elif k == "voice":
            if not isinstance(v, str) or not re.fullmatch(r"[A-Za-z]{3,20}", v):
                raise ValueError("Invalid voice name")
            out[k] = v
        else:
            raise ValueError("Setting cannot be changed here: " + str(k))
    return out
