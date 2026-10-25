"""Vietnamese TikTok captions and hashtags built from the analysis, and their quality checks."""

import re
import unicodedata

from .platforms import PLATFORMS
from .text import clean_caption
from .topics import TOPIC_TAGS

# other platforms and editors give a repost away; reach tags (xuhuong, fyp, viral) are welcome
BANNED_TAG_PARTS = (*PLATFORMS, "reels", "capcut")


def _cut_at_word(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return (cut if len(cut) >= limit * 0.5 else text[:limit]).rstrip("\u200d\ufe0f").strip()  # never end on half an emoji sequence


def ascii_tag(raw):
    """A hashtag the way viewers type it: lowercase, no accents ('Funny' -> 'haihuoc'), letters and digits only."""
    text = unicodedata.normalize("NFD", unicodedata.normalize("NFC", raw).lstrip("#").strip().lower().replace("\u0111", "d"))
    return "".join(c for c in text if not unicodedata.combining(c))


def build_caption(analysis, title):
    """Vietnamese caption from the analysis; falls back to the source title. Never adds claims that were not in the video."""
    analysis = analysis if isinstance(analysis, dict) else {}
    caption = analysis.get("caption_vi") if isinstance(analysis.get("caption_vi"), str) else ""
    # hashtags are added below, never duplicated from the text; links, handles and invisible characters never reach the post
    caption = clean_caption(re.sub(r"#\S+", " ", caption)) or clean_caption(re.sub(r"#\S+", " ", title or ""))
    caption = _cut_at_word(caption, 110)
    tags = []
    raw_tags = analysis.get("hashtags") if isinstance(analysis.get("hashtags"), list) else []
    for h in raw_tags:
        if not isinstance(h, str):
            continue
        h = ascii_tag(h)
        if not re.fullmatch(r"[a-z0-9_]{2,30}", h) or h in tags:
            continue
        if any(b in h for b in BANNED_TAG_PARTS):
            continue  # never advertise other platforms or filler, whatever the model says
        tags.append(h)
    tags = tags[:4]
    topic_tag = TOPIC_TAGS["music"] if analysis.get("kind") == "music" else TOPIC_TAGS.get(analysis.get("topic"), "giaitri")
    for d in ("xuhuong", topic_tag, "viral"):  # reach first; always 3 or more tags, never more than 5
        if d not in tags and len(tags) < 5:
            tags.append(d)
    return (caption + " " + " ".join("#" + h for h in tags)).strip()


def lint_caption(caption):
    """Quality checks shown next to every caption. Returns {'ok': bool, 'tags': n, 'length': n, 'issues': [...]}."""
    issues = []
    text = re.sub(r"#\w+", "", caption).strip()
    tags = re.findall(r"#(\w+)", caption)
    if len(text) < 8:
        issues.append("M\u00f4 t\u1ea3 qu\u00e1 ng\u1eafn")
    if len(text) > 150:
        issues.append("M\u00f4 t\u1ea3 h\u01a1i d\u00e0i (tr\u00ean 150 k\u00fd t\u1ef1 d\u1ec5 b\u1ecb c\u1eaft khi xem)")
    if len(tags) < 3:
        issues.append("N\u00ean c\u00f3 3–5 hashtag")
    if len(tags) > 5:
        issues.append("Qu\u00e1 nhi\u1ec1u hashtag (n\u00ean t\u1ed1i \u0111a 5)")
    if len({t.lower() for t in tags}) != len(tags):
        issues.append("C\u00f3 hashtag b\u1ecb l\u1eb7p")
    if len(caption) > 2200:
        issues.append("V\u01b0\u1ee3t gi\u1edbi h\u1ea1n 2200 k\u00fd t\u1ef1")
    return {"ok": not issues, "tags": len(tags), "length": len(text), "issues": issues}
