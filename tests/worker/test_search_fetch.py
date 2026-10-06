"""Following a link's redirects safely: public addresses only, every hop checked, nothing read but the redirects."""

import unittest
from unittest import mock

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.search import fetch as fetch_mod


class FakeServers:
    """Stands in for PublicHTTPS: {url: (status, Location or None, body)}; remembers every URL that was really requested."""

    def __init__(self, pages):
        self.pages, self.requested, self.headers = pages, [], []

    def __call__(self, host, timeout=0, context=None):
        servers = self

        class Conn:
            def request(self, method, path, headers=None):
                self.url = "https://" + host + path
                servers.requested.append(self.url)
                servers.headers.append(headers or {})

            def getresponse(self):
                status, location, body = servers.pages[self.url]

                class Response:
                    def __init__(self):
                        self.status = status

                    def getheader(self, name, default=None):
                        return {"Location": location, "Content-Type": "text/html"}.get(name, default)

                    def read(self, n=-1):
                        return body

                return Response()

            def close(self):
                pass

        return Conn()


def patched(pages):
    servers = FakeServers(pages)
    return servers, mock.patch.object(fetch_mod, "PublicHTTPS", servers)


class FollowTests(unittest.TestCase):
    def test_the_hops_of_a_short_link_are_returned_in_order_and_no_body_is_read(self):
        servers, patch = patched(
            {
                "https://vt.tiktok.com/ZSabc/": (302, "https://www.tiktok.com/t/ZTabc/", b""),
                "https://www.tiktok.com/t/ZTabc/": (301, "/view/product/1729384756102938475?share_creator_id=7000000000000000001", b""),
                "https://www.tiktok.com/view/product/1729384756102938475?share_creator_id=7000000000000000001": (200, None, b"<html>"),
            }
        )
        with patch:
            result = fetch_mod.follow("https://vt.tiktok.com/ZSabc/")
        self.assertEqual(
            result["chain"],
            [
                "https://vt.tiktok.com/ZSabc/",
                "https://www.tiktok.com/t/ZTabc/",
                "https://www.tiktok.com/view/product/1729384756102938475?share_creator_id=7000000000000000001",
            ],
        )
        self.assertEqual((result["status"], result["stopped"]), (200, ""))
        self.assertIn("Mozilla", servers.headers[0]["User-Agent"])  # a bare Python client is refused by the short-link service

    def test_a_hop_to_a_host_that_is_not_allowed_is_recorded_but_never_requested(self):
        servers, patch = patched({"https://vt.tiktok.com/ZSabc/": (302, "https://evil.example/steal", b"")})
        with patch:
            result = fetch_mod.follow("https://vt.tiktok.com/ZSabc/", allow=lambda host: host.endswith("tiktok.com"))
        self.assertEqual(result["chain"][-1], "https://evil.example/steal")
        self.assertEqual(result["stopped"], "evil.example")
        self.assertEqual(servers.requested, ["https://vt.tiktok.com/ZSabc/"])

    def test_a_redirect_loop_and_a_redirect_without_a_target_are_errors(self):
        servers, patch = patched({"https://vt.tiktok.com/a/": (302, "https://vt.tiktok.com/a/", b"")})
        with patch, self.assertRaises(ValueError):
            fetch_mod.follow("https://vt.tiktok.com/a/", hops=4)
        servers, patch = patched({"https://vt.tiktok.com/b/": (302, None, b"")})
        with patch, self.assertRaises(ValueError):
            fetch_mod.follow("https://vt.tiktok.com/b/")

    def test_http_and_private_looking_links_are_refused_before_any_connection(self):
        servers, patch = patched({})
        with patch:
            for url in ("http://vt.tiktok.com/a/", "https://user:pw@vt.tiktok.com/a/", "https://vt.tiktok.com:8443/a/"):
                with self.assertRaises(ValueError, msg=url):
                    fetch_mod.follow(url)
        self.assertEqual(servers.requested, [])


class FetchTests(unittest.TestCase):
    def test_a_page_is_read_after_its_redirects_and_returns_its_final_address(self):
        servers, patch = patched(
            {
                "https://vt.tiktok.com/ZSabc/": (302, "https://www.tiktok.com/view/product/1729384756102938475", b""),
                "https://www.tiktok.com/view/product/1729384756102938475": (200, None, "<title>Bàn phím</title>".encode()),
            }
        )
        with patch:
            data, mime, final = fetch_mod.fetch("https://vt.tiktok.com/ZSabc/")
        self.assertEqual(
            (data, mime, final),
            ("<title>Bàn phím</title>".encode(), "text/html", "https://www.tiktok.com/view/product/1729384756102938475"),
        )

    def test_an_error_status_is_an_error_not_a_page(self):
        servers, patch = patched({"https://vt.tiktok.com/a/": (403, None, b"blocked")})
        with patch, self.assertRaises(ValueError):
            fetch_mod.fetch("https://vt.tiktok.com/a/")

    def test_the_page_title_is_the_og_title_before_the_html_title_and_is_kept_short(self):
        page = "<html><head><title>TikTok</title><meta property='og:title' content='Bàn phím MCHOSE ACE68'></head><body>x</body></html>"
        servers, patch = patched({"https://www.tiktok.com/view/product/1729384756102938475": (200, None, page.encode())})
        with patch:
            title, final = fetch_mod.page_title("https://www.tiktok.com/view/product/1729384756102938475")
        self.assertEqual((title, final), ("Bàn phím MCHOSE ACE68", "https://www.tiktok.com/view/product/1729384756102938475"))

    def test_without_og_title_the_html_title_is_used_and_cut_at_300_characters(self):
        page = "<title>%s</title>" % ("a" * 500)
        servers, patch = patched({"https://www.tiktok.com/view/product/1729384756102938475": (200, None, page.encode())})
        with patch:
            title, _ = fetch_mod.page_title("https://www.tiktok.com/view/product/1729384756102938475")
        self.assertEqual(title, "a" * 300)


if __name__ == "__main__":
    unittest.main()
