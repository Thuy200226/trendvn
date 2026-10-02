"""Subtitles burned into the source picture (common on Douyin and Kuaishou): where they are, so our captions can replace them."""

MAX_BAND = 0.30  # a band taller than this is not a line of subtitles, it is Gemini guessing
MARGIN = 0.012  # safety margin added above and below, as a fraction of the picture height
# The source's own line is on screen while someone speaks, which is when our Vietnamese line is on screen too: the strip is blurred
# only then (plus a little either side: Gemini's times are rounded to whole seconds), not for the whole video, where a permanent grey
# band across the picture covers the people and the scene for no reason.
PAD_BEFORE = 0.5  # seconds before our line appears
PAD_AFTER = 0.6  # seconds after it goes
MERGE_GAP = 1.5  # lines closer together than this share one blurred patch instead of blinking on and off between them


def hard_subtitle_band(analysis):
    """(top, bottom) of the burned-in subtitles as fractions of the picture height, or None when there are none or the answer
    is unusable. A wrong band only blurs a harmless strip of picture, so bad data is ignored instead of failing the video."""
    found = analysis.get("hard_subtitles")
    if not isinstance(found, dict) or found.get("present") is not True:
        return None
    top, bottom = found.get("top"), found.get("bottom")
    for value in (top, bottom):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:  # also false for NaN and infinity
            return None
    if not 0 < bottom - top <= MAX_BAND:
        return None
    return round(max(0.0, top - MARGIN), 4), round(min(1.0, bottom + MARGIN), 4)


def covered_spans(segments, duration):
    """[(start, end)] in seconds when the strip must be blurred: every Vietnamese line's time with its padding, merged when close.
    Empty when there are no lines (then there is nothing to cover the source's subtitles with, and nothing to hide them for)."""
    spans = []
    for segment in sorted(segments, key=lambda item: item["start"]):
        start = max(0.0, segment["start"] - PAD_BEFORE)
        end = min(duration, segment["end"] + PAD_AFTER)
        if end <= start:
            continue
        if spans and start - spans[-1][1] <= MERGE_GAP:
            spans[-1][1] = max(spans[-1][1], end)
        else:
            spans.append([start, end])
    return [(round(a, 2), round(b, 2)) for a, b in spans]
