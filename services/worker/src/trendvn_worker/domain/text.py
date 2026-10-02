"""Cleaning text that came from a model or a website before it is shown, burned into a video or posted under the owner's name."""

import re
import unicodedata

MAX_CAPTION_CHARS = (
    5000  # longer input is cut BEFORE any pattern runs: the patterns are linear, but a repetition loop of a model is not worth reading
)
MAX_SUBTITLE_CHARS = 1000

TLDS = "com|net|org|vn|cn|io|me|ly|tv|co|app|link|xyz|top|site|shop|club|info|biz|cc|gg|be|ee|dev|ai|page|live|store|online|vip|pro|one|tech|fun|ws|to|sh"
# A link, a handle, an e-mail address or a phone number inside a caption or a subtitle is advertising or an injection: never posted.
# Every pattern starts only where a token starts (lookbehind) and has bounded or single-pass repetition, so a hostile string cannot make
# them quadratic (a 32,000-character "a-a-a-..." took 19 s with the first version). A bare domain must be plain ASCII with a lowercase
# TLD, so "quá.Top" and "Mr.Co" (a missing space after a full stop) are left alone.
URL = re.compile(
    r"(?i:https?://)\S+|(?<![\w@.-])(?:(?i:www\.)\S+|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.(?:%s)\b(?:/\S*)?)" % TLDS,
)
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]{1,64}@[\w-]{1,63}(?:\.[\w-]{1,63}){1,5}")
HANDLE = re.compile(r"(?<![\w])@[\w.]{2,}")
PHONE_CANDIDATE = re.compile(r"(?<![\w.])\+?\(?\d[\d .\-()]{7,18}\d(?![\w])")
HTML_TAG = re.compile(r"</?[A-Za-z][^<>]{0,80}>")
EMOJI = re.compile(
    "[\U0001f000-\U0001faff\u00a9\u00ae\u203c\u2049\u2122\u2139\u2190-\u21ff\u2300-\u23ff\u25a0-\u25ff\u2600-\u27bf\u2b00-\u2bff\ufe0e-\ufe0f\u200d\u20e3]"
)
ZWJ = "\u200d"  # kept in captions: it joins the parts of one emoji (family, profession)
# look empty but are not "blank": filler and joiner characters that survive .strip()
BLANKS = "\u3164\u2800\u115f\u1160\u034f\u17b4\u17b5\u180e\uffa0"


def _strip_invisible(text):
    """Control characters and invisible formatting (zero-width spaces, bidi overrides, BOM, filler characters) go; line breaks become
    spaces; lone surrogates (invalid text) are dropped."""
    out = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch in "\r\n\t\u2028\u2029":
            out.append(" ")
        elif ch in BLANKS or category in ("Cc", "Cs") or (category in ("Cf", "Zl", "Zp") and ch != ZWJ):
            continue
        else:
            out.append(ch)
    return "".join(out)


def _is_phone(match):
    """A candidate is a phone number when its digits look like one (Vietnamese 0xxxxxxxxx / +84..., or any +country number) and its groups
    are the size phone numbers come in: so dates (01.10.2026), opening hours (07.00-22.00), scores and lists of numbers are kept."""
    text = match.group(0)
    digits = re.sub(r"\D", "", text)
    groups = re.split(r"[ .\-()]+", text.lstrip("+("))
    if any(len(g) < 3 for g in groups[1:]):
        return False
    if text.startswith("+"):
        return 9 <= len(digits) <= 15
    hotline = re.fullmatch(r"1[89]00\d{4,6}", digits) is not None  # 1900 xxxx, 1800 xxxx: paid and free business lines
    return hotline or (digits.startswith("0") and len(digits) in (10, 11)) or (digits.startswith("84") and len(digits) in (11, 12))


def strip_contacts(text):
    """Remove links, e-mail addresses, @handles and phone numbers. Repeated until nothing more is found, so a link glued to another
    ("evil.comhttp://x") cannot survive as what is left over."""
    for _ in range(4):
        before = text
        for pattern in (EMAIL, URL, HANDLE):
            text = pattern.sub(" ", text)
        text = PHONE_CANDIDATE.sub(lambda m: " " if _is_phone(m) else m.group(0), text)
        if text == before:
            break
    return text


def clean_caption(text):
    """A caption/title line: NFC, no invisible or control characters, no links/handles/contacts, single spaces."""
    text = unicodedata.normalize("NFC", _strip_invisible(str(text)[:MAX_CAPTION_CHARS]))
    return re.sub(r"\s+", " ", strip_contacts(text)).strip()


def clean_subtitle(text):
    """A subtitle line burned into the picture: like a caption, plus no emoji (the subtitle font cannot draw them), no markup, no ASS
    override characters. Backslashes go first, so "evil.c\\om" cannot turn into a link after the check."""
    text = str(text)[:MAX_SUBTITLE_CHARS].replace("\\", "")
    text = HTML_TAG.sub("", text)
    text = clean_caption(EMOJI.sub("", text))
    return text.replace("{", "(").replace("}", ")").strip()
