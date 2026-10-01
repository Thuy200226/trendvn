"""Reading speed of the Vietnamese subtitles: nobody reads what flashes past faster than about 17 characters a second."""

MAX_CPS = 17.0  # comfortable reading speed, characters per second
MIN_SHOWN = 1.0  # a caption stays at least this long unless the next one starts first
MAX_EXTENSION = 1.0  # a caption may outlast the speech it translates by at most this long
GAP = 0.05  # kept clear between two captions
TOO_FAST = 24.0  # still faster than this after fitting: flagged on the dashboard, not blocked


def chars_per_second(segment):
    shown = segment["end"] - segment["start"]
    return len(segment["vi"].strip()) / shown if shown > 0 else float("inf")


def fit_reading_speed(segments, duration):
    """Give every caption the time it needs to be read by extending its end into the pause that follows it: never over the next
    caption, never past the end of the video, never by more than MAX_EXTENSION. Returns (fitted copies, worst characters per second)."""
    fitted = []
    for i, segment in enumerate(segments):
        segment = dict(segment)
        need = max(MIN_SHOWN, len(segment["vi"].strip()) / MAX_CPS)
        room = (segments[i + 1]["start"] - GAP) if i + 1 < len(segments) else duration
        end = min(segment["start"] + need, segment["end"] + MAX_EXTENSION, room)
        segment["end"] = round(max(segment["end"], end), 2)
        fitted.append(segment)
    return fitted, round(max((chars_per_second(s) for s in fitted), default=0.0), 1)
