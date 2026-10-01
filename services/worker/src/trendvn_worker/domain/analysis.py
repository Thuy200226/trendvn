"""Gemini's analysis of a video: repair timestamps, validate, and decide the route (original / vietsub / voiceover)."""

import math


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


def validate_analysis(a, duration, confidence=0.90, strict=False, lenient=False):
    """lenient=True is a human approval: it waives confidence/topic/sensitivity, never the structural checks."""
    allowed = ("music", "dialogue", "narration", "mixed", "silent", "uncertain")
    if not isinstance(a, dict) or a.get("kind") not in allowed:
        raise ValueError("Invalid audio classification")
    c = a.get("confidence")
    if isinstance(c, bool) or not isinstance(c, (float, int)) or not math.isfinite(c) or not 0 <= c <= 1:
        raise ValueError("Invalid confidence")
    if not lenient and (c < confidence or a["kind"] == "uncertain"):
        raise ValueError("Audio needs review")
    if strict and not lenient and (a.get("topic") not in ("entertainment", "music", "other") or not isinstance(a.get("sensitive"), bool)):
        raise ValueError("Topic/sensitivity missing from analysis")
    if not lenient and a.get("sensitive") is True:
        raise ValueError("Sensitive content (politics, violence, tragedy, adult or medical claims) needs review")
    if not lenient and a.get("topic") == "other":
        raise ValueError("Off-topic for an entertainment and music channel")
    segments = a.get("segments", [])
    if not isinstance(segments, list) or len(segments) > 500:
        raise ValueError("Invalid segments")
    segments = a["segments"] = normalize_segments(segments, duration) if segments else []
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
    if a["kind"] == "uncertain":
        a = dict(a, kind="silent" if not segments else "mixed")
    if a["kind"] in ("dialogue", "mixed"):
        return "vietsub"
    if a["kind"] == "narration":
        return "voiceover"
    if a.get("requires_text_translation") and not segments:
        raise ValueError("On-screen information requires translation")
    return "vietsub" if segments else "original"
