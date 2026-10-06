"""What a TikTok or Douyin link points at, judged from its text alone. No network: following a short link is search/fetch.py's job."""

import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

MAX_LINKS = 3
ID = r"(\d{6,25})"
SHORT_HOSTS = {"vt.tiktok.com", "vm.tiktok.com"}
PRODUCT_PATHS = tuple(
    re.compile(pattern)
    for pattern in (
        r"/view/product/%s/?" % ID,
        r"/shop/pdp/(?:[^/]+/)?%s/?" % ID,
        r"/product/%s/?" % ID,
        r"/@[A-Za-z0-9._-]{1,50}/product/%s/?" % ID,
    )
)
TIKTOK_VIDEO = re.compile(r"/@([A-Za-z0-9._-]{1,50})/video/%s/?" % ID)
DOUYIN_VIDEO = re.compile(r"/video/%s/?" % ID)
SHORT_PATH = re.compile(r"/t/[A-Za-z0-9]{3,40}/?")
# Parameters that tie a link to a person (the creator who shared it) rather than to the product or the page.
MARKER = re.compile(r"(?<![a-z0-9])(?:creator|affiliate|partner|sec_?user|sec_?uid|share_?user|u_code|ug)(?![a-z0-9])", re.I)
# Of those, the ones that name WHO shared (a campaign tag such as ug_btm says nothing about the sharer).
WHO = re.compile(r"(?<![a-z0-9])(?:creator|affiliate|partner|sec_?user|sec_?uid|share_?user|u_code)(?![a-z0-9])", re.I)
VALUE_LIMIT = 80


def tiktok_host(host):
    return host == "tiktok.com" or host.endswith(".tiktok.com")


def _parts(value):
    """The URL's parts when it is a clean public https link (no credentials, no port, no whitespace), else None."""
    if not isinstance(value, str) or not value or len(value) > 2000 or not value.isascii() or re.search(r"[\s\\\x00-\x1f\x7f]", value):
        return None
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        return None
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or port not in (None, 443):
        return None
    if re.fullmatch(r"(?:0x[0-9a-f]+|\d+)", parts.hostname.lower().rsplit(".", 1)[-1]):
        return None  # 2130706433, 0x7f.1, 127.1: a number where the top-level name should be
    try:
        ipaddress.ip_address(parts.hostname)
    except ValueError:
        return parts
    return None  # a share link names a site, never a bare address


def _query_product(query):
    return next((v for k, v in parse_qsl(query) if k == "product_id" and re.fullmatch(ID, v)), None)


def classify(value):
    """{'url','host','kind','platform','product_id','video_id','canonical','conflict'} or None for text that is not a clean https link.
    kind: product | video | short (a link that has to be followed to know where it goes) | tiktok (any other TikTok page) | other.
    A video address is a video whatever its query says; an address that names two different products is no product (`conflict`)."""
    parts = _parts(value)
    if parts is None:
        return None
    host, path = parts.hostname.lower(), parts.path or "/"
    link = {
        "url": value, "host": host, "kind": "other", "platform": None, "product_id": None, "video_id": None, "canonical": None, "conflict": False,
    }  # fmt: skip
    if tiktok_host(host):
        link.update(kind="tiktok", platform="tiktok")
        video = TIKTOK_VIDEO.fullmatch(path)
        if video:
            link.update(
                kind="video", video_id=video.group(2), canonical="https://www.tiktok.com/@%s/video/%s" % (video.group(1), video.group(2))
            )
        elif host in SHORT_HOSTS or (host == "www.tiktok.com" and SHORT_PATH.fullmatch(path)):
            link["kind"] = "short"
        else:
            named = next((m.fullmatch(path) for m in PRODUCT_PATHS if m.fullmatch(path)), None)
            ids = {i for i in (named.group(1) if named else None, _query_product(parts.query)) if i}
            link["conflict"] = len(ids) > 1
            if len(ids) == 1:
                pid = ids.pop()
                link.update(kind="product", product_id=pid, canonical="https://www.tiktok.com/view/product/" + pid)
    elif host in ("douyin.com", "www.douyin.com"):
        link.update(platform="douyin")
        video = DOUYIN_VIDEO.fullmatch(path)
        if video:
            link.update(kind="video", video_id=video.group(1), canonical="https://www.douyin.com/video/" + video.group(1))
    return link


def from_text(text, limit=MAX_LINKS):
    """The distinct clean https links in a piece of prose, in order, cut where a sentence's punctuation ends them."""
    found, seen = [], set()
    for raw in re.findall(r"https://[^\s<>\"']+", str(text)):
        url = raw.rstrip(").,;:!?]}»”")
        link = classify(url)
        if link and url not in seen:
            seen.add(url)
            found.append(link)
        if len(found) == limit:
            break
    return found


def product_link(text):
    """The TikTok product page or short link a message carries (the one to check as a share link), or None. A link the app shares comes
    with a line of words around it, so the words are not a reason to read it as anything else."""
    return next((link for link in from_text(text) if link["kind"] in ("product", "short")), None)


def sharer(markers):
    """The part of a link's marks that names the sharer: {name: value}."""
    return {name: value for name, value in markers.items() if WHO.search(name)}


def attribution(value):
    """The parameters of a link that name a person, not a page: {'markers': {name: value}, 'tracked': bool}. A plain product link has none.
    Which of these is the owner's own creator code is learned from the links the owner confirms (search/affiliate.py), never assumed."""
    parts = _parts(value)
    markers = {}
    if parts is not None:
        for name, content in parse_qsl(parts.query):
            if MARKER.search(name) and name not in markers:
                markers[name] = content[:VALUE_LIMIT]
    return {"markers": markers, "tracked": bool(markers)}
