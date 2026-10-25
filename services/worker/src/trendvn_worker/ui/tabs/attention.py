"""Must see: what only the owner can decide (TikTok verification, unconfirmed posts, videos held back)."""

import re

from ..cards import review_card
from ..format import ago, escape as E, shown_of


def _challenge(view):
    return (
        '<div class="card alert stack"><h3>🧩 TikTok \u0111ang y\u00eau c\u1ea7u x\u00e1c minh%s</h3><p>\u0110\u0103ng b\u00e0i \u0111ang <b>t\u1ea1m d\u1eebng</b> \u0111\u1ec3 kh\u00f4ng k\u00edch ho\u1ea1t th\u00eam. '
        "H\u00e3y gi\u1ea3i h\u00ecnh x\u00e1c minh m\u1ed9t l\u1ea7n trong c\u1eeda s\u1ed5 Chrome th\u1eadt:</p>"
        '<p><code>%s</code></p><p class="muted small">Mac: nh\u1ea5p \u0111\u00fap <code>macos/Verify-TikTok.command</code>. '
        "Xong h\u1ec7 th\u1ed1ng t\u1ef1 \u0111\u0103ng ti\u1ebfp.</p></div>"
    ) % (E(view.challenge_who), E(view.challenge_command))


def _key_rejected():
    return (
        '<div class="card alert stack"><h3>🔑 Kh\u00f3a Gemini b\u1ecb Google t\u1eeb ch\u1ed1i</h3><p>Kh\u00f3a sai, \u0111\u00e3 thu h\u1ed3i ho\u1eb7c thi\u1ebfu quy\u1ec1n, n\u00ean <b>kh\u00f4ng video n\u00e0o x\u1eed l\u00fd \u0111\u01b0\u1ee3c</b>. '
        "C\u00e1c video v\u1eabn n\u1eb1m ch\u1edd trong h\u00e0ng \u0111\u1ee3i, kh\u00f4ng b\u1ecb \u0111\u00e1nh d\u1ea5u h\u1ecfng. V\u00e0o <b>Th\u00eam → C\u00e0i \u0111\u1eb7t</b> d\u00e1n kh\u00f3a m\u1edbi "
        "(l\u1ea5y \u1edf <code>https://aistudio.google.com/apikey</code>); xong h\u1ec7 th\u1ed1ng t\u1ef1 ch\u1ea1y l\u1ea1i.</p></div>"
    )


def _unresolved(view, job):
    """A post that may or may not be on TikTok: which account it was meant for, what it said and since when, so the owner knows where to look."""
    caption = re.sub(r"\s+", " ", re.sub(r"#\w+", "", job.get("caption") or "")).strip() or (job.get("title") or "")
    who = "@" + job["target"] if job.get("target") else "t\u00e0i kho\u1ea3n m\u1eb7c \u0111\u1ecbnh"
    return (
        '<form method="post" action="/resolve" class="card alert stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
        "<h3>🚨 Ch\u01b0a x\u00e1c nh\u1eadn \u0111\u00e3 \u0111\u0103ng: %s</h3>"
        '<p class="small"><b>%s</b> · b\u1ea5m \u0110\u0103ng %s</p>'
        '<p>H\u1ec7 th\u1ed1ng \u0111\u00e3 d\u1eebng \u0111\u0103ng \u0111\u1ec3 kh\u00f4ng \u0111\u0103ng tr\u00f9ng. M\u1edf TikTok c\u1ee7a %s ki\u1ec3m tra r\u1ed3i ch\u1ecdn:</p><div class="btns">'
        '<button name="outcome" value="published" class="go">B\u00e0i \u0111\u00e3 l\u00ean TikTok</button>'
        '<button name="outcome" value="failed" class="ghost">Ch\u01b0a c\u00f3, cho ph\u00e9p \u0111\u0103ng l\u1ea1i</button></div></form>'
    ) % (view.csrf, E(job["id"]), E(caption[:100]), E(who), E(ago(job.get("updated"), view.now)), E(who))


def render(view):
    d = view.d
    parts = [_challenge(view)] if view.challenge_on else []
    parts += [_key_rejected()] if view.key_rejected else []
    parts += [_unresolved(view, job) for job in d["unresolved"]]
    held = view.counts.get("needs_review", 0)
    if held > len(d["review"]):
        parts.append(
            '<p class="muted small">\u0110ang hi\u1ec7n %s video b\u1ecb gi\u1eef l\u1ea1i: x\u1eed l\u00fd b\u1edbt r\u1ed3i t\u1ea3i l\u1ea1i trang \u0111\u1ec3 th\u1ea5y ph\u1ea7n c\u00f2n l\u1ea1i.</p>'
            % E(shown_of(len(d["review"]), held))
        )
    parts += [review_card(dict(job), view.csrf) for job in d["review"]]
    if not parts:
        parts = [
            '<div class="card empty stack"><p>Kh\u00f4ng c\u00f3 vi\u1ec7c n\u00e0o c\u1ea7n b\u1ea1n xem. 🎉</p><p class="small">Video \u0111ang ch\u1edd x\u1eed l\u00fd n\u1eb1m \u1edf tab '
            '<a href="#queue">H\u00e0ng \u0111\u1ee3i</a>; video \u0111\u00e3 x\u1eed l\u00fd xong n\u1eb1m \u1edf tab <a href="#publish">\u0110\u0103ng b\u00e0i</a>.</p></div>'
        ]
    return "<h2>C\u1ea7n xem</h2>" + "".join(parts)
