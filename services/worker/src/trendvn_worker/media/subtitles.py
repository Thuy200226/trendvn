"""Subtitle files: SRT for the record, ASS for burning in."""

import re
import textwrap


def timestamp(t):
    ms = round(t * 1000)
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"


def subtitles(segments, path):
    lines = []
    for i, s in enumerate(segments, 1):
        text = re.sub(r"<[^>]*>", "", s["vi"]).replace("\r", " ").replace("\n", " ").replace("-->", "→").replace("{", "(").replace("}", ")")
        lines.append(f"{i}\n{timestamp(s['start'])} --> {timestamp(s['end'])}\n{text.strip()}\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def caption_extent(width, height, zone, lines=2):
    """(top, bottom) in pixels of the output that a caption of up to `lines` lines occupies in `zone`; the numbers are those of
    ass_subtitles() below (font size, padding, margin), so a decision about overlap is made on the same geometry that gets drawn."""
    font = max(14, round(width * 0.047))
    pad = max(4, round(font * 0.28)) if zone["box"] else max(3, round(font * 0.09))
    box = lines * round(font * 1.2) + 2 * pad
    if zone["align"] == 8:
        return zone["margin"] - pad, zone["margin"] + box
    return height - zone["margin"] - box, height - zone["margin"] + pad


def ass_subtitles(segments, path, width, height, band_top=None, zone=None):
    """zone (from caption_zone) says where captions go; band_top is the older shortcut for a free band below the picture."""

    def ass_time(t):
        cs = round(t * 100)
        secs, cs = divmod(cs, 100)
        mins, secs = divmod(secs, 60)
        hours, mins = divmod(mins, 60)
        return f"{hours}:{mins:02}:{secs:02}.{cs:02}"

    font = max(14, round(width * 0.047))
    left = max(12, round(width * 0.045))
    right = max(30, round(width * 0.12))
    margin = max(30, round(height * 0.18))
    if zone is None and band_top is not None:
        zone = {"align": 8, "margin": band_top + round(height * 0.025), "box": False}
    if zone is None:
        zone = {"align": 2, "margin": round(height * 0.27), "box": True}
    align, margin = zone["align"], zone["margin"]
    border, outline = (
        (3, max(4, round(font * 0.28))) if zone["box"] else (1, max(3, round(font * 0.09)))
    )  # a box over the picture, plain outline on the blurred band
    chars = max(20, int((width - left - right) / (font * 0.52)))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,{font},&H00FFFFFF,&H000000FF,&H30000000,&H30000000,-1,0,0,0,100,100,0,0,{border},{outline},0,{align},{left},{right},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for s in segments:
        txt = re.sub(r"<[^>]*>", "", s["vi"]).replace("\\", "＼").replace("{", "(").replace("}", ")")
        txt = " ".join(txt.split())
        lines = textwrap.wrap(txt, width=chars, break_long_words=True, break_on_hyphens=False)
        # Long sentences become consecutive two-line captions sharing the segment's time in proportion to their text.
        chunks = [lines[i : i + 2] for i in range(0, len(lines), 2)]
        weights = [sum(len(x) for x in c) for c in chunks]
        start = s["start"]
        span = s["end"] - s["start"]
        for c, w in zip(chunks, weights):
            end = start + span * w / sum(weights)
            text = "\\N".join(c)
            events.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}")
            start = end
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
