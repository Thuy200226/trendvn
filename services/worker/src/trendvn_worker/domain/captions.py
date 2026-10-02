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
    """A hashtag the way viewers type it: lowercase, no accents ('Hài hước' -> 'haihuoc'), letters and digits only."""
    text = unicodedata.normalize("NFD", unicodedata.normalize("NFC", raw).lstrip("#").strip().lower().replace("đ", "d"))
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
        issues.append("Mô tả quá ngắn")
    if len(text) > 150:
        issues.append("Mô tả hơi dài (trên 150 ký tự dễ bị cắt khi xem)")
    if len(tags) < 3:
        issues.append("Nên có 3–5 hashtag")
    if len(tags) > 5:
        issues.append("Quá nhiều hashtag (nên tối đa 5)")
    if len({t.lower() for t in tags}) != len(tags):
        issues.append("Có hashtag bị lặp")
    if len(caption) > 2200:
        issues.append("Vượt giới hạn 2200 ký tự")
    return {"ok": not issues, "tags": len(tags), "length": len(text), "issues": issues}
