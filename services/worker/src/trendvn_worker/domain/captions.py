"""Vietnamese TikTok captions and hashtags built from the analysis, and their quality checks."""

import re
import unicodedata

# other platforms and editors give a repost away; reach tags (xuhuong, fyp, viral) are welcome
BANNED_TAG_PARTS = ("tiktok", "douyin", "kuaishou", "instagram", "reels", "capcut")


def _cut_at_word(text, limit):
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return (cut if len(cut) >= limit * 0.5 else text[:limit]).strip()


def build_caption(analysis, title):
    """Vietnamese caption from the analysis; falls back to the source title. Never adds claims that were not in the video."""
    analysis = analysis if isinstance(analysis, dict) else {}
    caption = unicodedata.normalize("NFC", analysis.get("caption_vi").strip()) if isinstance(analysis.get("caption_vi"), str) else ""
    if not caption:
        caption = re.sub(r"\s+", " ", re.sub(r"#\S+", " ", title or "")).strip()
    caption = re.sub(r"[\x00-\x1f]", " ", re.sub(r"#\S+", " ", caption))  # hashtags are added below, never duplicated from the text
    caption = _cut_at_word(re.sub(r"\s+", " ", caption).strip(), 110)
    tags = []
    raw_tags = analysis.get("hashtags") if isinstance(analysis.get("hashtags"), list) else []
    for h in raw_tags:
        if not isinstance(h, str):
            continue
        h = unicodedata.normalize("NFC", h).lstrip("#").strip().lower()
        if not re.fullmatch(r"[\w]{2,30}", h) or h in tags:
            continue
        if any(b in h for b in BANNED_TAG_PARTS):
            continue  # never advertise other platforms or filler, whatever the model says
        tags.append(h)
    tags = tags[:4]
    for d in (["xuhuong", "nhac"] if analysis.get("kind") == "music" else ["xuhuong", "giaitri"]):
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
