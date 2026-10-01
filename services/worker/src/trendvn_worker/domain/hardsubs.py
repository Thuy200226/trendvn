"""Subtitles burned into the source picture (common on Douyin and Kuaishou): where they are, so our captions can replace them."""

import math

MAX_BAND = 0.30  # a band taller than this is not a line of subtitles, it is Gemini guessing
MARGIN = 0.012  # safety margin added above and below, as a fraction of the picture height


def hard_subtitle_band(analysis):
    """(top, bottom) of the burned-in subtitles as fractions of the picture height, or None when there are none or the answer
    is unusable. A wrong band only blurs a harmless strip of picture, so bad data is ignored instead of failing the video."""
    found = analysis.get("hard_subtitles")
    if not isinstance(found, dict) or found.get("present") is not True:
        return None
    top, bottom = found.get("top"), found.get("bottom")
    for value in (top, bottom):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            return None
    if not 0 < bottom - top <= MAX_BAND:
        return None
    return round(max(0.0, top - MARGIN), 4), round(min(1.0, bottom + MARGIN), 4)
