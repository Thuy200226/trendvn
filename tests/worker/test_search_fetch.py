"""Following a link's redirects safely: public addresses only, every hop checked, nothing read but the redirects."""

import unittest
from unittest import mock

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.product_links import tiktok_host
from trendvn_worker.search import fetch as fetch_mod
from trendvn_worker.search.fetch import visible_text


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
                    def getheader(self, name, default=None):
                        return {"Location": location, "Content-Type": "text/html"}.get(name, default)

                    def __init__(self):
                        self.status, self.left = status, body if isinstance(body, bytes) else b""
                        self.script = body if isinstance(body, list) else None

                    def read1(self, n=-1):
                        if self.script is not None:
                            step = self.script.pop(0) if self.script else b""
                            return step() if callable(step) else step
                        piece, self.left = self.left[:n], self.left[n:]
                        return piece

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


class HardeningTests(unittest.TestCase):
    PRODUCT = "https://www.tiktok.com/view/product/1729384756102938475"

    def test_a_title_page_that_redirects_off_tiktok_is_an_error_and_the_other_site_is_never_requested(self):
        servers, patch = patched({self.PRODUCT: (302, "https://evil.example/landing", b"")})
        with patch, self.assertRaises(ValueError):
            fetch_mod.page_title(self.PRODUCT, allow=tiktok_host)
        self.assertEqual(servers.requested, ["https://www.tiktok.com/view/product/1729384756102938475"])

    def test_a_first_address_the_caller_refuses_is_never_requested(self):
        servers, patch = patched({})
        with patch, self.assertRaises(ValueError):
            fetch_mod.fetch("https://evil.example/x", allow=tiktok_host)
        self.assertEqual(servers.requested, [])

    def test_og_title_is_found_whichever_way_round_its_attributes_come_and_entities_are_decoded(self):
        for meta in (
            "<meta property='og:title' content='Bàn phím &amp; chuột'>",
            '<meta content="Bàn phím &amp; chuột" property="og:title" />',
            '<META PROPERTY="og:title" CONTENT="Bàn phím &amp; chuột">',
        ):
            servers, patch = patched({self.PRODUCT: (200, None, ("<head><title>x</title>%s</head>" % meta).encode())})
            with patch:
                self.assertEqual(fetch_mod.page_title(self.PRODUCT)[0], "Bàn phím & chuột", meta)

    def test_a_page_longer_than_its_head_is_cut_not_refused_when_only_the_title_is_wanted(self):
        page = b"<title>Short</title>" + b"x" * (fetch_mod.HEAD_BYTES * 2)
        servers, patch = patched({self.PRODUCT: (200, None, page)})
        with patch:
            self.assertEqual(fetch_mod.page_title(self.PRODUCT)[0], "Short")
        servers, patch = patched({self.PRODUCT: (200, None, page)})
        with patch, self.assertRaises(ValueError):
            fetch_mod.fetch(self.PRODUCT, limit=1000)  # a download that must be whole is refused instead

    def test_a_server_that_drips_bytes_is_given_up_on_at_the_deadline(self):
        clock = [0.0]
        drip = [lambda: clock.__setitem__(0, clock[0] + 10) or b"x" for _ in range(50)]
        servers, patch = patched({self.PRODUCT: (200, None, drip)})
        with patch, mock.patch.object(fetch_mod.time, "monotonic", lambda: clock[0]), self.assertRaises(ValueError) as caught:
            fetch_mod.fetch(self.PRODUCT, limit=1 << 20)
        self.assertIn("quá chậm", str(caught.exception))

    def test_a_server_that_answers_with_garbage_is_a_could_not_read_not_a_crash(self):
        import http.client

        class Broken(FakeServers):
            def __call__(self, host, timeout=0, context=None):
                conn = super().__call__(host, timeout, context)
                conn.getresponse = lambda: (_ for _ in ()).throw(http.client.BadStatusLine("garbage"))
                return conn

        with mock.patch.object(fetch_mod, "PublicHTTPS", Broken({})), self.assertRaises(ValueError):
            fetch_mod.fetch(self.PRODUCT)

    def test_translation_and_multicast_ranges_are_not_public_addresses(self):
        for address in ("64:ff9b::808:808", "224.0.0.1", "ff02::1", "192.88.99.1", "127.0.0.1", "10.0.0.1", "::1", "::ffff:127.0.0.1"):
            self.assertFalse(fetch_mod.is_public(address), address)
        self.assertTrue(fetch_mod.is_public("8.8.8.8"))
        self.assertTrue(fetch_mod.is_public("2606:4700:4700::1111"))


class VisibleTextTests(unittest.TestCase):
    def test_hostile_pages_are_read_in_linear_time(self):
        import time

        for hostile in ("<!--" * 65536, "<" * 262144, "<script" * 40000, "<a " * 80000, "<meta " * 40000, "<" + "x" * 262144):
            started = time.time()
            visible_text(hostile)
            self.assertLess(time.time() - started, 2.0, hostile[:12])

    def test_text_between_tags_is_kept_and_everything_hidden_is_not(self):
        page = "<p>Hello <b>shop</b></p><script>alert(1)</script><style>a{}</style><!-- hidden --><noscript>no</noscript><p>end</p>"
        self.assertEqual(visible_text(page), "Hello shop end")

    def test_an_unterminated_script_or_comment_takes_the_rest_of_the_page_with_it(self):
        self.assertEqual(visible_text("<p>a</p><script>b<p>c</p>"), "a")
        self.assertEqual(visible_text("<p>a</p><!-- b<p>c</p>"), "a")

    def test_valueless_and_odd_meta_attributes_do_not_break_it(self):
        self.assertEqual(visible_text('<meta property="og:title" content><meta name=description content="d"><p>x</p>'), "d x")


if __name__ == "__main__":
    unittest.main()
