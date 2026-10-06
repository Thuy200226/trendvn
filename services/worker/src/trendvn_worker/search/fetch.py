"""Small public HTTPS downloads with pinned DNS and checked redirects; never access the host's private network."""

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ..domain.product_links import classify


class PublicHTTPS(http.client.HTTPSConnection):
    def connect(self):
        addresses = socket.getaddrinfo(self.host, 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
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
    except BaseException:
        conn.close()
        raise


def _location(url, response):
    destination = response.getheader("Location")
    if not destination:
        raise ValueError("Chuyển hướng không có địa chỉ")
    return urljoin(url, destination)


def fetch(url, limit=1 << 20):
    for _ in range(4):
        conn, r = _get(url)
        try:
            if r.status in REDIRECTS:
                url = _location(url, r)
                continue
            if r.status != 200:
                raise ValueError("Không đọc được đường dẫn (HTTP %d)" % r.status)
            data = r.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Nội dung đường dẫn quá lớn")
            return data, r.getheader("Content-Type", "").split(";")[0], url
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


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.in_title = False
        self.parts = []
        self.og_title = ""
        self.title = ""

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            a = dict(attrs)
            if a.get("property") == "og:title" and not self.og_title:
                self.og_title = a.get("content", "")
            if a.get("property") in ("og:title", "og:description") or a.get("name") == "description":
                self.parts.append(a.get("content", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and not self.title:
            self.title = data.strip()
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def _html(url):
    raw, mime, final = fetch(url)
    if mime not in ("text/html", "text/plain", "application/xhtml+xml"):
        raise ValueError("Đường dẫn cần là trang sản phẩm/văn bản; hãy kéo ảnh hoặc PDF vào ô tệp")
    parser = VisibleHTML()
    parser.feed(raw.decode("utf-8", "replace"))
    return parser, final


def link_text(url):
    parser, final = _html(url)
    return " ".join(parser.parts)[:12000], final


def page_title(url):
    """(the page's own title, final address): og:title, else <title>. A title is one short line: the long page text is not evidence of
    which product a page is about, because a store page mentions many."""
    parser, final = _html(url)
    return (parser.og_title or parser.title).strip()[:300], final
