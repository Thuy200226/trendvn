"""Vietnamese wording shown in the dashboard: states, sources, components, events, and the plain-language version of internal reasons."""

import re

from ..domain.platforms import REGISTRY

STATE_LABELS = {
    "baseline": "M\u1ed1c ban \u0111\u1ea7u",
    "candidate": "\u1ee8ng vi\u00ean",
    "queued": "Ch\u1edd x\u1eed l\u00fd",
    "processing": "\u0110ang x\u1eed l\u00fd",
    "awaiting_approval": "Ch\u1edd b\u1ea1n duy\u1ec7t",
    "ready": "S\u1eb5n s\u00e0ng \u0111\u0103ng",
    "publishing": "\u0110ang \u0111\u0103ng",
    "published": "\u0110\u00e3 \u0111\u0103ng",
    "needs_review": "C\u1ea7n duy\u1ec7t",
    "publish_unknown": "Ch\u01b0a x\u00e1c nh\u1eadn",
    "duplicate": "Tr\u00f9ng",
    "failed": "L\u1ed7i",
    "rejected": "\u0110\u00e3 b\u1ecf",
}
STATE_TONE = {
    "published": "good",
    "ready": "good",
    "awaiting_approval": "warn",
    "needs_review": "warn",
    "publish_unknown": "bad",
    "failed": "bad",
    "processing": "info",
    "publishing": "info",
    "queued": "info",
    "candidate": "mute",
    "baseline": "mute",
    "duplicate": "mute",
    "rejected": "mute",
}
PLATFORM = {p.id: (p.name, p.country) for p in REGISTRY}
COMPONENT = {
    "connected": ("Ho\u1ea1t \u0111\u1ed9ng", "good"),
    "not_connected": ("Ch\u01b0a k\u1ebft n\u1ed1i", "mute"),
    "stale": ("L\u00e2u ch\u01b0a b\u00e1o c\u00e1o", "warn"),
    "error": ("C\u1ea7n ch\u00fa \u00fd", "bad"),
}
ROUTE_LABEL = {"vietsub": "Vietsub", "voiceover": "L\u1ed3ng ti\u1ebfng + Vietsub", "original": "Gi\u1eef nguy\u00ean"}
VISIBILITY_LABEL = {"public": "C\u00f4ng khai", "friends": "B\u1ea1n b\u00e8", "self": "Ch\u1ec9 m\u00ecnh t\u00f4i"}

EVENT_LABELS = {
    "processing": "B\u1eaft \u0111\u1ea7u x\u1eed l\u00fd",
    "queued": "\u0110\u00e3 t\u1ea3i, ch\u1edd x\u1eed l\u00fd",
    "ready": "\u0110\u00e3 d\u1ef1ng, s\u1eb5n s\u00e0ng \u0111\u0103ng",
    "awaiting_approval": "Ch\u1edd b\u1ea1n duy\u1ec7t",
    "needs_review": "C\u1ea7n b\u1ea1n duy\u1ec7t",
    "publishing": "\u0110ang \u0111\u0103ng",
    "publish_published": "\u0110\u00e3 \u0111\u0103ng th\u00e0nh c\u00f4ng",
    "publish_unknown": "\u0110\u0103ng ch\u01b0a x\u00e1c nh\u1eadn",
    "publish_failed": "\u0110\u0103ng ch\u01b0a th\u00e0nh c\u00f4ng",
    "publish_duplicate": "B\u1ecf v\u00ec tr\u00f9ng b\u00e0i \u0111\u00e3 c\u00f3",
    "candidate": "Ph\u00e1t hi\u1ec7n video m\u1edbi",
    "failed": "L\u1ed7i",
    "duplicate": "Tr\u00f9ng video \u0111\u00e3 c\u00f3",
    "released": "X\u1ebfp l\u1ea1i h\u00e0ng \u0111\u1ee3i",
    "media_failed": "T\u1ea3i video l\u1ed7i",
    "operator_approve": "B\u1ea1n \u0111\u00e3 duy\u1ec7t",
    "operator_reject": "B\u1ea1n \u0111\u00e3 b\u1ecf",
    "resolved_published": "X\u00e1c nh\u1eadn \u0111\u00e3 \u0111\u0103ng",
    "resolved_failed": "X\u00e1c nh\u1eadn ch\u01b0a \u0111\u0103ng",
    "settings": "\u0110\u1ed5i c\u00e0i \u0111\u1eb7t",
    "account_added": "Th\u00eam t\u00e0i kho\u1ea3n TikTok",
    "account_updated": "S\u1eeda t\u00e0i kho\u1ea3n TikTok",
    "account_deleted": "X\u00f3a t\u00e0i kho\u1ea3n TikTok",
    "caption_edited": "B\u1ea1n s\u1eeda m\u00f4 t\u1ea3",
    "challenge_on": "TikTok \u0111\u00f2i x\u00e1c minh: t\u1ea1m d\u1eebng \u0111\u0103ng",
    "challenge_off": "\u0110\u00e3 gi\u1ea3i x\u00e1c minh: \u0111\u0103ng l\u1ea1i b\u00ecnh th\u01b0\u1eddng",
    "expired": "Qu\u00e1 h\u1ea1n, h\u1ec7 th\u1ed1ng b\u1ecf",
    "publish_deferred": "Ho\u00e3n \u0111\u0103ng (kh\u00f4ng ph\u1ea3i l\u1ed7i c\u1ee7a video)",
    "operator_retry": "B\u1ea1n \u0111\u01b0a v\u1ec1 s\u1eb5n s\u00e0ng \u0111\u0103ng",
}

# (fragment of the internal English reason, what to tell the owner)
REASONS = (
    ("Audio needs review", "Gemini ch\u01b0a \u0111\u1ee7 ch\u1eafc ch\u1eafn v\u1ec1 lo\u1ea1i \u00e2m thanh"),
    (
        "Sensitive content",
        "Ch\u1ea1m gi\u1edbi h\u1ea1n c\u1ee9ng (t\u00ecnh d\u1ee5c, tr\u1ebb em g\u1eb7p nguy, m\u00e1u me th\u1eadt, th\u00f9 gh\u00e9t, t\u1ef1 h\u1ea1i/t\u1ed9i ph\u1ea1m, l\u1eddi khuy\u00ean nguy hi\u1ec3m, \u0111\u1eddi t\u01b0): c\u1ea7n b\u1ea1n quy\u1ebft \u0111\u1ecbnh",
    ),
    ("Off-topic", "N\u1ed9i dung kh\u00f4ng thu\u1ed9c lo\u1ea1i gi\u1ea3i tr\u00ed"),
    ("Possible visual duplicate", "C\u00f3 th\u1ec3 tr\u00f9ng v\u1edbi m\u1ed9t video \u0111\u00e3 x\u1eed l\u00fd"),
    ("Video duration outside", "Th\u1eddi l\u01b0\u1ee3ng ngo\u00e0i gi\u1edbi h\u1ea1n cho ph\u00e9p"),
    ("Speech detected without transcript", "C\u00f3 l\u1eddi n\u00f3i nh\u01b0ng kh\u00f4ng ch\u00e9p \u0111\u01b0\u1ee3c l\u1eddi"),
    ("Subtitle timestamps", "M\u1ed1c th\u1eddi gian ph\u1ee5 \u0111\u1ec1 kh\u00f4ng h\u1ee3p l\u1ec7"),
    ("Topic/sensitivity missing", "Gemini kh\u00f4ng tr\u1ea3 \u0111\u1ee7 th\u00f4ng tin ch\u1ee7 \u0111\u1ec1"),
    (
        "Gemini output truncated",
        "M\u00f4 h\u00ecnh Gemini vi\u1ebft lan man qu\u00e1 d\u00e0i n\u00ean c\u00e2u tr\u1ea3 l\u1eddi b\u1ecb c\u1eaft d\u1edf (l\u1ed7i c\u1ee7a m\u00f4 h\u00ecnh, kh\u00f4ng ph\u1ea3i c\u1ee7a video); b\u1ea5m Duy\u1ec7t \u0111\u1ec3 ph\u00e2n t\u00edch l\u1ea1i",
    ),
    ("Gemini did not return valid", "Gemini tr\u1ea3 d\u1eef li\u1ec7u kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c"),
    ("Gemini returned no analysis", "Gemini t\u1eeb ch\u1ed1i ho\u1eb7c kh\u00f4ng tr\u1ea3 l\u1eddi video n\u00e0y"),
    ("Invalid caption", "Gemini kh\u00f4ng vi\u1ebft \u0111\u01b0\u1ee3c m\u00f4 t\u1ea3 cho video"),
    ("Processing interrupted", "X\u1eed l\u00fd b\u1ecb gi\u00e1n \u0111o\u1ea1n"),
    ("Local rolling 24-hour limit", "H\u1ebft h\u1ea1n m\u1ee9c Gemini trong 24 gi\u1edd; s\u1ebd t\u1ef1 x\u1eed l\u00fd l\u1ea1i"),
    ("Initial observation only", "Ch\u1ec9 ghi m\u1ed1c ban \u0111\u1ea7u"),
    ("Rejected by operator", "B\u1ea1n \u0111\u00e3 b\u1ecf video n\u00e0y"),
    ("Approved by operator", "B\u1ea1n \u0111\u00e3 duy\u1ec7t"),
    ("Invalid audio classification", "Gemini tr\u1ea3 lo\u1ea1i \u00e2m thanh kh\u00f4ng h\u1ee3p l\u1ec7"),
    ("Invalid confidence", "Gemini tr\u1ea3 \u0111\u1ed9 ch\u1eafc ch\u1eafn kh\u00f4ng h\u1ee3p l\u1ec7"),
    ("Invalid segments", "Gemini tr\u1ea3 ph\u1ee5 \u0111\u1ec1 kh\u00f4ng h\u1ee3p l\u1ec7"),
    ("Invalid subtitle time", "Gemini tr\u1ea3 m\u1ed1c th\u1eddi gian ph\u1ee5 \u0111\u1ec1 kh\u00f4ng h\u1ee3p l\u1ec7"),
    ("Invalid translated segment", "Gemini tr\u1ea3 b\u1ea3n d\u1ecbch ph\u1ee5 \u0111\u1ec1 kh\u00f4ng h\u1ee3p l\u1ec7"),
    (
        "Music-only classification conflicts with speech",
        "Gemini x\u1ebfp l\u00e0 ch\u1ec9 c\u00f3 nh\u1ea1c nh\u01b0ng video l\u1ea1i c\u00f3 l\u1eddi n\u00f3i: c\u1ea7n b\u1ea1n xem",
    ),
    (
        "On-screen information requires translation",
        "Video c\u00f3 ch\u1eef quan tr\u1ecdng tr\u00ean m\u00e0n h\u00ecnh m\u00e0 ch\u01b0a c\u00f3 b\u1ea3n d\u1ecbch: c\u1ea7n b\u1ea1n xem",
    ),
    ("duplicate key", "Gemini tr\u1ea3 d\u1eef li\u1ec7u b\u1ecb l\u1eb7p kh\u00f3a n\u00ean kh\u00f4ng \u0111\u1ecdc \u0111\u01b0\u1ee3c"),
    (
        "Analysis proxy exceeds",
        "B\u1ea3n xem tr\u01b0\u1edbc g\u1eedi Gemini qu\u00e1 n\u1eb7ng (h\u01a1n 12 MB): video qu\u00e1 d\u00e0i ho\u1eb7c qu\u00e1 n\u1eb7ng",
    ),
    ("Source file changed after attachment", "File video b\u1ecb \u0111\u1ed5i sau khi t\u1ea3i v\u1ec1: c\u1ea7n b\u1ea1n xem"),
    (
        "Gemini HTTP",
        "Gemini b\u00e1o l\u1ed7i khi ph\u00e2n t\u00edch video n\u00e0y (c\u00f3 th\u1ec3 th\u1eed l\u1ea1i b\u1eb1ng n\u00fat Duy\u1ec7t)",
    ),
)


VIETNAMESE_LETTER = re.compile(
    "[\xe0\xe1\u1ea1\u1ea3\xe3\xe2\u0103\u1ea5\u1ea7\u1ea9\u1eab\u1ead\u1eaf\u1eb1\u1eb3\u1eb5\u1eb7\xe8\xe9\u1eb9\u1ebb\u1ebd\xea\u1ebf\u1ec1\u1ec3\u1ec5\u1ec7\xec\xed\u1ecb\u1ec9\u0129\xf2\xf3\u1ecd\u1ecf\xf5\xf4\u1ed1\u1ed3\u1ed5\u1ed7\u1ed9\u01a1\u1edb\u1edd\u1edf\u1ee1\u1ee3\xf9\xfa\u1ee5\u1ee7\u0169\u01b0\u1ee9\u1eeb\u1eed\u1eef\u1ef1\u1ef3\xfd\u1ef5\u1ef7\u1ef9\u0111]",
    re.I,
)


def vi_reason(text):
    """Plain-language version of an internal reason (unknown reasons, and ones already written in Vietnamese, are shown as they are:
    a Vietnamese sentence that quotes Google's English after a colon must not lose itself to the table entry for that English)."""
    if text and VIETNAMESE_LETTER.search(text):
        return text
    for fragment, vietnamese in REASONS:
        if text and fragment in text:
            return vietnamese
    return text or ""


# the settings the owner types a number for, named as on the dashboard
FIELD_NAMES = {
    "daily_limit": "S\u1ed1 b\u00e0i t\u1ed1i \u0111a m\u1ed7i ng\u00e0y",
    "gemini_daily_limit": "H\u1ea1n m\u1ee9c g\u1ecdi Gemini m\u1ed7i 24 gi\u1edd",
    "min_publish_gap": "Gi\u00e3n c\u00e1ch gi\u1eefa hai b\u00e0i (gi\u00e2y)",
    "max_age_days": "S\u1ed1 ng\u00e0y t\u1ed1i \u0111a c\u1ee7a video",
    "max_duration": "\u0110\u1ed9 d\u00e0i t\u1ed1i \u0111a c\u1ee7a video (gi\u00e2y)",
    "max_candidates_per_scan": "S\u1ed1 video t\u1ea3i m\u1ed7i l\u1ea7n qu\u00e9t",
    "max_backlog": "S\u1ed1 video ch\u1edd t\u1ed1i \u0111a",
    "window start": "Gi\u1edd b\u1eaft \u0111\u1ea7u c\u1ee7a gi\u1edd v\u00e0ng",
    "window end": "Gi\u1edd k\u1ebft th\u00fac c\u1ee7a gi\u1edd v\u00e0ng",
}


def _integer(match):
    name = match.group(1)
    threshold = re.fullmatch(r"(min_views|min_likes)\.(\w+)", name)
    label = FIELD_NAMES.get(name) or (
        "%s (%s)"
        % (
            "L\u01b0\u1ee3t xem t\u1ed1i thi\u1ec3u" if threshold.group(1) == "min_views" else "S\u1ed1 tim t\u1ed1i thi\u1ec3u",
            threshold.group(2),
        )
        if threshold
        else name
    )
    return "%s ph\u1ea3i l\u00e0 s\u1ed1 nguy\u00ean t\u1eeb %s \u0111\u1ebfn %s" % (label, match.group(2), match.group(3))


# (regex of the internal English error, the Vietnamese text or a function of the match): messages of forms and buttons
ERRORS = (
    (re.compile(r"(\S[\w. ]*?) must be an integer between (\S+) and (\S+)"), _integer),
    (re.compile(r"Settings must be an object"), "D\u1eef li\u1ec7u c\u00e0i \u0111\u1eb7t kh\u00f4ng h\u1ee3p l\u1ec7"),
    (
        re.compile(r"audio_confidence must be"),
        "\u0110\u1ed9 ch\u1eafc ch\u1eafn t\u1ed1i thi\u1ec3u c\u1ee7a Gemini ph\u1ea3i t\u1eeb 0,5 \u0111\u1ebfn 0,99",
    ),
    (re.compile(r"post_windows: at most"), "T\u1ed1i \u0111a 6 khung gi\u1edd v\u00e0ng"),
    (
        re.compile(r"post_windows entries"),
        "M\u1ed7i gi\u1edd v\u00e0ng g\u1ed3m gi\u1edd b\u1eaft \u0111\u1ea7u v\u00e0 gi\u1edd k\u1ebft th\u00fac",
    ),
    (
        re.compile(r"window start must be before end"),
        "Gi\u1edd b\u1eaft \u0111\u1ea7u ph\u1ea3i nh\u1ecf h\u01a1n gi\u1edd k\u1ebft th\u00fac",
    ),
    (
        re.compile(r"Invalid TikTok username"),
        "T\u00ean t\u00e0i kho\u1ea3n TikTok kh\u00f4ng h\u1ee3p l\u1ec7 (ch\u1ec9 g\u1ed3m ch\u1eef, s\u1ed1, d\u1ea5u ch\u1ea5m v\u00e0 g\u1ea1ch d\u01b0\u1edbi)",
    ),
    (
        re.compile(r"visibility must be"),
        "Ch\u1ebf \u0111\u1ed9 hi\u1ec3n th\u1ecb ph\u1ea3i l\u00e0 c\u00f4ng khai, b\u1ea1n b\u00e8 ho\u1eb7c ch\u1ec9 m\u00ecnh t\u00f4i",
    ),
    (re.compile(r"Invalid model name"), "T\u00ean model kh\u00f4ng h\u1ee3p l\u1ec7"),
    (
        re.compile(r"caption_style must be"),
        "Ki\u1ec3u m\u00f4 t\u1ea3 ph\u1ea3i l\u00e0 gi\u1eadt t\u00edt ho\u1eb7c \u0111i\u1ec1m \u0111\u1ea1m",
    ),
    (re.compile(r"^\S+ must be one of"), "Gi\u00e1 tr\u1ecb kh\u00f4ng n\u1eb1m trong c\u00e1c l\u1ef1a ch\u1ecdn cho ph\u00e9p"),
    (re.compile(r"Invalid voice name"), "T\u00ean gi\u1ecdng \u0111\u1ecdc kh\u00f4ng h\u1ee3p l\u1ec7"),
    (re.compile(r"^\S+ must be true or false"), "C\u00f4ng t\u1eafc ch\u1ec9 nh\u1eadn b\u1eadt ho\u1eb7c t\u1eaft"),
    (re.compile(r"needs per-platform numbers"), "Ng\u01b0\u1ee1ng c\u1ea7n l\u00e0 s\u1ed1 cho t\u1eebng n\u1ec1n t\u1ea3ng"),
    (
        re.compile(r"Setting cannot be changed here"),
        "C\u00e0i \u0111\u1eb7t n\u00e0y kh\u00f4ng \u0111\u1ed5i \u0111\u01b0\u1ee3c \u1edf \u0111\u00e2y",
    ),
    (re.compile(r"Invalid processing terminal state|Invalid fields|Invalid action"), "Thao t\u00e1c kh\u00f4ng h\u1ee3p l\u1ec7"),
    (
        re.compile(r"Stale (publish )?lease"),
        "Vi\u1ec7c n\u00e0y \u0111\u00e3 \u0111\u01b0\u1ee3c nh\u1eadn l\u1ea1i \u1edf n\u01a1i kh\u00e1c; h\u00e3y t\u1ea3i l\u1ea1i trang r\u1ed3i th\u1eed l\u1ea1i",
    ),
    (
        re.compile(r"Job is not awaiting confirmation"),
        "B\u00e0i n\u00e0y kh\u00f4ng c\u00f2n \u1edf tr\u1ea1ng th\u00e1i ch\u1edd x\u00e1c nh\u1eadn (\u0111\u00e3 \u0111\u01b0\u1ee3c x\u1eed l\u00fd \u1edf n\u01a1i kh\u00e1c); t\u1ea3i l\u1ea1i trang",
    ),
    (re.compile(r"Invalid (publish )?(outcome|URL)|Unknown component"), "D\u1eef li\u1ec7u kh\u00f4ng h\u1ee3p l\u1ec7"),
    (re.compile(r"Job not found"), "Kh\u00f4ng t\u00ecm th\u1ea5y video n\u00e0y (c\u00f3 th\u1ec3 \u0111\u00e3 b\u1ecb d\u1ecdn)"),
    (
        re.compile(r"Job cannot be rejected in this state"),
        "Video \u0111ang \u1edf tr\u1ea1ng th\u00e1i kh\u00f4ng b\u1ecf \u0111\u01b0\u1ee3c",
    ),
    (
        re.compile(r"Nothing to approve in this state"),
        "Video n\u00e0y kh\u00f4ng c\u00f3 g\u00ec \u0111\u1ec3 duy\u1ec7t \u1edf tr\u1ea1ng th\u00e1i hi\u1ec7n t\u1ea1i",
    ),
    (
        re.compile(r"Source file is gone; cannot reprocess"),
        "File video g\u1ed1c \u0111\u00e3 b\u1ecb d\u1ecdn n\u00ean kh\u00f4ng x\u1eed l\u00fd l\u1ea1i \u0111\u01b0\u1ee3c",
    ),
    (
        re.compile(r"Gemini key is required to enable processing"),
        "C\u1ea7n nh\u1eadp kh\u00f3a Gemini tr\u01b0\u1edbc khi b\u1eadt x\u1eed l\u00fd video",
    ),
    (re.compile(r"items must be a list"), "D\u1eef li\u1ec7u th\u1ed1ng k\u00ea kh\u00f4ng h\u1ee3p l\u1ec7"),
)


def vi_error(text):
    """Plain-language version of an error message from a form or a button (Vietnamese and unknown messages are returned as they are)."""
    if re.match(r"Gemini HTTP|Media operation failed", text or ""):
        return text  # an error of an outside service: its own words, not a guess about which setting it was
    for pattern, vietnamese in ERRORS:
        match = pattern.search(text or "")
        if match:
            return vietnamese(match) if callable(vietnamese) else vietnamese
    return text or ""
