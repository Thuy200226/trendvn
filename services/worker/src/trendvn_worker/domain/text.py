"""Cleaning text that came from a model or a website before it is shown, burned into a video or posted under the owner's name."""

import re
import unicodedata

# a link, a handle, an e-mail address or a phone number inside a caption or a subtitle is advertising or an injection: never posted
URL = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|org|vn|cn|io|me|ly|tv|co|app|link|xyz|top|site|shop|club|info|biz|cc|gg)\b(?:/\S*)?",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
HANDLE = re.compile(r"(?<![\w])@[\w.]{2,}")
PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[ .\-]?\d|0\d)[\d .\-]{7,11}\d(?![\w])")
EMOJI = re.compile("[\U0001f000-\U0001faff⌀-⏿☀-➿⬀-⯿︎️‍⃣]")
ZWJ = "‍"  # kept in captions: it joins the parts of one emoji (family, profession)


def _strip_invisible(text):
    """Control characters and invisible formatting (zero-width spaces, bidi overrides, BOM) go; line breaks become spaces."""
    out = []
    for ch in text:
        category = unicodedata.category(ch)
        if ch in "\r\n\t  ":
            out.append(" ")
        elif category == "Cc" or (category in ("Cf", "Zl", "Zp") and ch != ZWJ):
            continue
        else:
            out.append(ch)
    return "".join(out)


def strip_contacts(text):
    """Remove links, e-mail addresses, @handles and phone numbers."""
    for pattern in (EMAIL, URL, HANDLE, PHONE):
        text = pattern.sub(" ", text)
    return text


def clean_caption(text):
    """A caption/title line: NFC, no invisible or control characters, no links/handles/contacts, single spaces."""
    text = unicodedata.normalize("NFC", _strip_invisible(str(text)))
    return re.sub(r"\s+", " ", strip_contacts(text)).strip()


def clean_subtitle(text):
    """A subtitle line burned into the picture: like a caption, plus no emoji (the subtitle font cannot draw them), no markup."""
    text = re.sub(r"<[^>]*>", "", str(text))
    text = clean_caption(EMOJI.sub("", text))
    return text.replace("\\", "").replace("{", "(").replace("}", ")")
