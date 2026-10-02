"""Gemini's analysis of a video: repair timestamps, validate, and decide the route (see route.py)."""

import math

from .route import choose_route
from .text import clean_subtitle
from .voices import GENDERS, TONES
from .topics import OTHER, TOPIC_IDS, label

MAX_LINE_CHARS = 350  # a subtitle line above this is refused outright (see validate_analysis)
RESTART_BACK = 3.0  # a line that starts this many seconds before the latest end seen so far has "restarted the clock"
RUSHED_SECONDS = 0.5  # a line on screen for less than this ...
RUSHED_CHARS = 20  # ... with more characters than this cannot be read: it was invented, not heard (a real one: 50 characters in 0.4 s)


def _invented(line):
    """A line that cannot be real speech: long text squeezed into a fraction of a second."""
    return line["end"] - line["start"] < RUSHED_SECONDS and len(str(line.get("vi", "")).strip()) > RUSHED_CHARS


def _drop_restarted_tail(items):
    """In the model's own order, a late line that starts long before earlier ones ended means the model restarted its clock and went on
    writing; when most of what follows is such inventions (long text in a fraction of a second) the whole tail is dropped. Measured:
    a 53-second skit came back with 11 real lines and 11 more at 1.0-2.1 s, which after sorting cut the first real line short and put an
    invented one on screen at second 1.6."""
    latest = 0.0
    for index, line in enumerate(items):
        if line["start"] < latest - RESTART_BACK:
            tail = items[index:]
            if sum(1 for t in tail if _invented(t)) >= 0.6 * len(tail):
                return items[:index]
            return items
        latest = max(latest, line["end"])
    return items


def clean_segments(segments):
    """Subtitle lines as they may be burned in: no links, handles, contacts, emoji or markup. A line that was only such things is
    dropped (an emoji alone is not worth rejecting the video); an originally empty line is left for the structural check to reject."""
    out = []
    for s in segments:
        if isinstance(s, dict) and isinstance(s.get("vi"), str) and 0 < len(s["vi"].strip()) <= MAX_LINE_CHARS:
            s = dict(s, vi=clean_subtitle(s["vi"]))  # (a longer line is left as it is: the length check below refuses it)
            if not s["vi"]:
                continue
        out.append(s)
    return out


def normalize_segments(segments, duration):
    """Gemini's timestamps vary run to run: it can list unsorted or overlapping lines, and on long videos it sometimes keeps 'transcribing'
    past the end of the video. Repair what is repairable (sort, trim overlaps, cut at the video's length, drop lines that lie outside the
    video or are too short to read) and report how many lines were dropped. Structural garbage still raises."""
    items = []
    for s in segments:
        if not isinstance(s, dict):
            raise ValueError("Invalid segments")
        start, finish = s.get("start"), s.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, finish)):
            raise ValueError("Invalid subtitle time")
        items.append(dict(s, start=float(start), end=float(finish)))
    items = [line for line in _drop_restarted_tail(items) if not _invented(line)]
    items.sort(key=lambda s: (s["start"], s["end"]))
    out, outside = [], 0
    for s in items:
        start, finish = max(0.0, s["start"]), min(s["end"], duration)
        if start >= duration - 0.3:
            outside += 1  # beyond the end of the video: the signature of a model that kept inventing lines
            continue
        if finish - start < 0.25:
            continue  # too short to read; harmless
        if out and start < out[-1]["end"]:
            if start - out[-1]["start"] >= 0.3:
                out[-1]["end"] = round(start, 2)  # trim the earlier line
            else:
                start = out[-1]["end"]  # or start the later one after it
            if finish - start < 0.25:
                continue
        s["start"], s["end"] = round(start, 2), round(finish, 2)
        out.append(s)
    if items and outside > len(items) / 2:
        raise ValueError("Subtitle timestamps unreliable (%d of %d lines outside the video)" % (outside, len(items)))
    return out


def clean_speaker(a):
    """The analysis' `speaker` as {gender, tone, count, dub_ok} with safe values; anything unusable becomes "unknown"/"calm"/None/False.
    Never raises: a voice choice is a nicety, not a reason to refuse a video."""
    found = a.get("speaker") if isinstance(a.get("speaker"), dict) else {}
    count = found.get("count")
    return {
        "gender": found.get("gender") if found.get("gender") in GENDERS else "unknown",
        "tone": found.get("tone") if found.get("tone") in TONES else "calm",
        "count": count if type(count) is int and 0 <= count <= 99 else None,
        "dub_ok": found.get("dub_ok") is True,
    }


def validate_analysis(a, duration, confidence=0.90, strict=False, lenient=False, accepted_topics=None, voiceover_scope="narration"):
    """lenient=True is a human approval: it waives confidence/topic/sensitivity, never the structural checks.
    accepted_topics: the topics some account takes; a video about anything else needs the owner (None skips that check)."""
    allowed = ("music", "dialogue", "narration", "mixed", "silent", "uncertain")
    if not isinstance(a, dict) or a.get("kind") not in allowed:
        raise ValueError("Invalid audio classification")
    c = a.get("confidence")
    if isinstance(c, bool) or not isinstance(c, (float, int)) or not math.isfinite(c) or not 0 <= c <= 1:
        raise ValueError("Invalid confidence")
    if not lenient and (c < confidence or a["kind"] == "uncertain"):
        raise ValueError("Audio needs review")
    if strict and not lenient and (a.get("topic") not in (*TOPIC_IDS, OTHER) or not isinstance(a.get("sensitive"), bool)):
        raise ValueError("Topic/sensitivity missing from analysis")
    if not lenient and a.get("sensitive") is True:
        raise ValueError(
            "Sensitive content (hard stop: sexual, minors at risk, gore, hate, self-harm or crime, harmful advice, private persons) needs review"
        )
    if not lenient and a.get("topic") == OTHER:
        raise ValueError("Off-topic: not entertaining content")
    if not lenient and accepted_topics is not None and a.get("topic") in TOPIC_IDS and a["topic"] not in accepted_topics:
        raise ValueError("Chủ đề «%s» chưa có tài khoản nào nhận" % label(a["topic"]))
    segments = a.get("segments", [])
    if not isinstance(segments, list) or len(segments) > 500:
        raise ValueError("Invalid segments")
    if strict and not lenient and not (isinstance(a.get("caption_vi"), str) and a["caption_vi"].strip()):
        raise ValueError("Invalid caption")
    if not isinstance(a.get("caption_vi"), str):
        a["caption_vi"] = ""  # a human approval keeps the video; the post then falls back to the source title
    segments = a["segments"] = normalize_segments(clean_segments(segments), duration) if segments else []
    end = 0
    for s in segments:
        start, finish = s.get("start"), s.get("end")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (start, finish)):
            raise ValueError("Invalid subtitle time")
        if not end <= start < finish <= duration + 0.1:
            raise ValueError("Subtitle timestamps outside video or overlap")
        if not isinstance(s.get("vi"), str) or not s["vi"].strip() or len(s["vi"]) > 350:
            raise ValueError("Invalid translated segment")
        end = finish
    if a["kind"] in ("dialogue", "narration", "mixed") and not segments:
        raise ValueError("Speech detected without transcript")
    if a["kind"] == "music" and segments:
        raise ValueError("Music-only classification conflicts with speech")
    kind = a["kind"]
    if kind == "uncertain":  # only reachable with lenient=True (a human approval): decide by what was actually heard
        kind = "silent" if not segments else "mixed"
    if kind in ("music", "silent") and a.get("requires_text_translation") and not segments:
        raise ValueError("On-screen information requires translation")
    a["speaker"] = speaker = clean_speaker(a)
    # one person talking whose voice a neutral Vietnamese one replaces without loss: dubbed when the owner allows it for such videos
    monologue = voiceover_scope == "monologue" and speaker["dub_ok"] and speaker["count"] == 1
    chosen, a["route_reason"] = choose_route(kind, bool(segments), monologue)
    return chosen
