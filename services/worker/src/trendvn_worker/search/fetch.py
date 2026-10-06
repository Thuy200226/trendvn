"""Small public HTTPS downloads with pinned DNS and checked redirects; never access the host's private network."""

import http.client
import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from ..domain.product_search import public_url


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


def fetch(url, limit=1 << 20):
    for _ in range(4):
        public_url(url)
        u = urlsplit(url)
        conn = PublicHTTPS(u.hostname, timeout=12, context=ssl.create_default_context())
        try:
            conn.request("GET", (u.path or "/") + ("?" + u.query if u.query else ""), headers={"Accept-Encoding": "identity"})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                dest = r.getheader("Location")
                if not dest:
                    raise ValueError("Chuyển hướng không có địa chỉ")
                url = urljoin(url, dest)
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


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.hidden += 1
        if tag == "meta":
            a = dict(attrs)
            if a.get("property") in ("og:title", "og:description") or a.get("name") == "description":
                self.parts.append(a.get("content", ""))

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(data.strip())


def link_text(url):
    raw, mime, final = fetch(url)
    if mime not in ("text/html", "text/plain", "application/xhtml+xml"):
        raise ValueError("Đường dẫn cần là trang sản phẩm/văn bản; hãy kéo ảnh hoặc PDF vào ô tệp")
    parser = VisibleHTML()
    parser.feed(raw.decode("utf-8", "replace"))
    return " ".join(parser.parts)[:12000], final
