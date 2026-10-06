"""Small public HTTPS downloads with pinned DNS and checked redirects; never access the host's private network."""

import html
import http.client
import ipaddress
import re
import socket
import ssl
import time
from urllib.parse import urljoin, urlsplit

from ..domain.product_links import classify

NOT_PUBLIC = tuple(ipaddress.ip_network(n) for n in ("64:ff9b::/96", "192.88.99.0/24"))  # translation / relay ranges is_global lets through
FETCH_ERRORS = (ValueError, OSError, http.client.HTTPException)  # what a page that cannot be read can raise: all of it is "could not read"
DEADLINE = 25  # seconds a whole download may take, however slowly the server drips (the socket timeout alone only bounds each wait)
HEAD_BYTES = 256 << 10  # a title lives at the top of a page


def is_public(address):
    ip = ipaddress.ip_address(address)
    return ip.is_global and not ip.is_multicast and not any(ip in net for net in NOT_PUBLIC)


class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not is_public(a[4][0]) for a in addresses):
            raise ValueError("Đường dẫn trỏ vào mạng riêng hoặc địa chỉ không công khai")
        # Pin the checked address: a second DNS lookup could resolve to localhost (DNS rebinding).
        sock = socket.create_connection(addresses[0][4][:2], timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


# TikTok's short-link service refuses a bare Python client; this is what the owner's own browser says it is.
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
REDIRECTS = (301, 302, 303, 307, 308)


def _get(url, timeout=12):
    """One GET of a public https URL: (connection, response). The caller reads what it needs and closes the connection."""
    link = classify(url)
    if link is None:
        raise ValueError("Chỉ nhận đường dẫn HTTPS công khai")
    parts = urlsplit(url)
    conn = PublicHTTPS(parts.hostname, timeout=timeout, context=ssl.create_default_context())
    try:
        conn.request(
            "GET",
            (parts.path or "/") + ("?" + parts.query if parts.query else ""),
            headers={"Accept-Encoding": "identity", "User-Agent": USER_AGENT, "Accept-Language": "vi-VN,vi;q=0.9"},
        )
        return conn, conn.getresponse()
    except http.client.HTTPException:
        conn.close()
        raise ValueError("Máy chủ trả lời không hợp lệ") from None
    except BaseException:
        conn.close()
        raise


def _location(url, response):
    destination = response.getheader("Location")
    if not destination:
        raise ValueError("Chuyển hướng không có địa chỉ")
    return urljoin(url, destination)


def _read(response, limit, end, truncate):
    """The body up to `limit` bytes, within the deadline. read1 returns after one receive, so a server that drips a byte a second cannot
    hold the reader past `end` (a plain read(n) would wait for all n)."""
    chunks, size = [], 0
    while size <= limit:
        if time.monotonic() > end:
            raise ValueError("Trang phản hồi quá chậm")
        try:
            piece = response.read1(min(16384, limit + 1 - size))
        except http.client.HTTPException:
            raise ValueError("Máy chủ trả lời không hợp lệ") from None
        if not piece:
            break
        chunks.append(piece)
        size += len(piece)
    data = b"".join(chunks)
    if len(data) > limit:
        if not truncate:
            raise ValueError("Nội dung đường dẫn quá lớn")
        data = data[:limit]
    return data


def fetch(url, limit=1 << 20, allow=None, truncate=False):
    """(body, content type, final address). `allow(host)` may refuse a host, the first one included: a refused redirect is an error,
    never a request. `truncate` keeps the first `limit` bytes of a longer page instead of refusing it."""
    end = time.monotonic() + DEADLINE
    for _ in range(4):
        host = (classify(url) or {}).get("host", "")
        if allow and not allow(host):
            raise ValueError("Đường dẫn chuyển sang nơi không được phép")
        conn, r = _get(url)
        try:
            if r.status in REDIRECTS:
                url = _location(url, r)
                continue
            if r.status != 200:
                raise ValueError("Không đọc được đường dẫn (HTTP %d)" % r.status)
            return _read(r, limit, end, truncate), r.getheader("Content-Type", "").split(";")[0], url
        finally:
            conn.close()
    raise ValueError("Đường dẫn chuyển hướng quá nhiều lần")


def follow(url, allow=lambda host: True, hops=6):
    """Where a link leads, read from the redirects alone (no page body is read): {'chain': [url, ...], 'status': last HTTP status, 'stopped':
    host that was refused or ''}. A hop to a host `allow` refuses is recorded but never requested, so a share link cannot send the server
    anywhere the owner did not mean; every hop is a public https address with its DNS pinned."""
    chain, status, stopped = [url], 0, ""
    for _ in range(hops):
        host = classify(chain[-1])["host"] if classify(chain[-1]) else ""
        if not allow(host):
            stopped = host
            break
        conn, r = _get(chain[-1])
        try:
            status = r.status
            if r.status not in REDIRECTS:
                break
            chain.append(_location(chain[-1], r))
        finally:
            conn.close()
    else:
        raise ValueError("Đường dẫn chuyển hướng quá nhiều lần")
    return {"chain": chain, "status": status, "stopped": stopped}


HIDDEN = ("script", "style", "noscript", "template")
META_TAG = re.compile(r"<meta\b([^>]{0,600})>", re.I)
META_ATTR = re.compile(r"""([a-zA-Z:-]{1,30})\s*=\s*(?:"([^"]{0,600})"|'([^']{0,600})'|([^\s"'>]{1,200}))""")


def _without(text, start, end):
    """`text` with every start...end block removed; an unterminated block takes the rest. Linear: each search moves forward."""
    low, out, pos = text.lower(), [], 0
    while True:
        i = low.find(start, pos)
        if i < 0:
            out.append(text[pos:])
            return "".join(out)
        out.append(text[pos:i])
        j = low.find(end, i + len(start))
        if j < 0:
            return "".join(out)
        pos = j + len(end)


def _strip_tags(text):
    """The text between tags. A '<' with no '>' after it is just a character; the next '>' is looked up once, never once per '<'."""
    out, pos, gt = [], 0, -1
    while True:
        lt = text.find("<", pos)
        if lt < 0:
            out.append(text[pos:])
            return "".join(out)
        if gt < lt:
            gt = text.find(">", lt)
            if gt < 0:
                out.append(text[pos:])
                return "".join(out)
        out.append(text[pos:lt])
        out.append(" ")
        pos = gt + 1


def visible_text(page):
    """What a reader sees of an HTML page (plus the description tags a shop page puts its name in), without script, style or comments.
    Everything here is linear in the size of the page: the standard HTML parser is quadratic on hostile input."""
    parts = []
    for tag in META_TAG.finditer(page):
        attrs = {k.lower(): (a or b or c) for k, a, b, c in META_ATTR.findall(tag.group(1))}
        if attrs.get("property") in ("og:title", "og:description") or attrs.get("name") == "description":
            parts.append(attrs.get("content", ""))
    body = _without(page, "<!--", "-->")
    for hidden in HIDDEN:
        body = _without(body, "<" + hidden, "</" + hidden + ">")
    parts.append(_strip_tags(body))
    return " ".join(html.unescape(" ".join(parts)).split())


def link_text(url):
    raw, mime, final = fetch(url, limit=HEAD_BYTES, truncate=True)
    if mime not in ("text/html", "text/plain", "application/xhtml+xml"):
        raise ValueError("Đường dẫn cần là trang sản phẩm/văn bản; hãy kéo ảnh hoặc PDF vào ô tệp")
    return visible_text(raw.decode("utf-8", "replace"))[:12000], final


META = r"<meta\b[^>]{0,600}"
OG_TITLE = (
    re.compile(META + r"""property\s*=\s*["']og:title["'][^>]{0,600}?content\s*=\s*["']([^"']{1,500})""", re.I),
    re.compile(META + r"""content\s*=\s*["']([^"']{1,500})["'][^>]{0,600}?property\s*=\s*["']og:title["']""", re.I),
)
TITLE = re.compile(r"<title[^>]{0,200}>([^<]{1,500})", re.I)


def page_title(url, allow=None):
    """(the page's own title, final address): og:title, else <title>, read with plain patterns from the top of the page (linear time, no
    parser to stall). A title is one short line: the long page text is not evidence of which product a page is about, because a store
    page mentions many."""
    raw, mime, final = fetch(url, limit=HEAD_BYTES, allow=allow, truncate=True)
    if mime not in ("text/html", "text/plain", "application/xhtml+xml"):
        raise ValueError("Trang không phải HTML")
    text = raw.decode("utf-8", "replace")
    for pattern in (*OG_TITLE, TITLE):
        found = pattern.search(text)
        if found:
            return " ".join(html.unescape(found.group(1)).split())[:300], final
    return "", final
