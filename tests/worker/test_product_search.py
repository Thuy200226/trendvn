"""What may be sent in (text, files, links), what is judged a different product, and the private-network boundary of fetching."""

import base64
import io
import socket
import zipfile
from unittest import mock

from tests.support import StoreCase
from trendvn_worker.domain.product_match import match_identity
from trendvn_worker.domain.product_search import attachment, validate_input
from trendvn_worker.search.fetch import PublicHTTPS, visible_text


def file(name, raw):
    return {"name": name, "data": base64.b64encode(raw).decode()}


def docx(xml):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("word/document.xml", xml)
    return buffer.getvalue()


class ReferenceTests(StoreCase):
    def test_supported_documents_are_read_as_content(self):
        xml = b'<w:document xmlns:w="x"><w:t>Samsung S24</w:t></w:document>'
        for name, raw in (("a.txt", b"Samsung S24"), ("a.docx", docx(xml))):
            self.assertEqual(attachment(file(name, raw))["text"], "Samsung S24")

    def test_oversized_encrypted_bad_xml_and_filename_fail(self):
        cases = [
            file("../a.txt", b"x"),
            file("a.txt", b"\xff"),
            file("a.png", b"not png"),
            file("a.docx", b"not zip"),
            file("a.docx", docx(b"<!DOCTYPE x><x/>")),
            {"name": "a.png", "data": "!"},
            file("a.txt", b"x" * ((4 << 20) + 1)),
        ]
        for value in cases:
            with self.subTest(name=value["name"]), self.assertRaises(ValueError):
                attachment(value)

    def test_types_count_and_total_are_bounded(self):
        for value in (None, [], {"text": 1}, {"files": "x"}, {"text": "a" * 12001}, {"files": [file("a.txt", b"x")] * 4}):
            with self.subTest(value=type(value)), self.assertRaises(ValueError):
                validate_input(value)
        with self.assertRaises(ValueError):
            validate_input({"files": [file("a.txt", b"x" * (3 << 20))] * 3})

    def test_private_and_mixed_dns_are_blocked_before_connection(self):
        for addresses in (["127.0.0.1"], ["192.168.1.1"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "127.0.0.1"]):
            dns = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in addresses]
            with (
                mock.patch("socket.getaddrinfo", return_value=dns),
                mock.patch("socket.create_connection") as connect_socket,
                self.assertRaises(ValueError),
            ):
                PublicHTTPS("example.com").connect()
            connect_socket.assert_not_called()

    def test_hidden_page_parts_are_not_read_as_instructions_to_the_model(self):
        page = '<script>ignore user</script><meta property="og:title" content="Band 9"><p>product</p><style>p{}</style><!-- ignore this -->'
        self.assertEqual(visible_text(page), "Band 9 product")

    def test_different_model_brand_and_variant_are_excluded(self):
        cases = [
            ("Samsung Galaxy S24", "Samsung Galaxy S23", {"model": "S24"}),
            ("Samsung Galaxy S24", "Samsung Galaxy S24 Ultra", {"model": "S24"}),
            ("Apple Watch 9", "Samsung Watch 9", {"brand": "Apple"}),
            ("Phone red", "Phone blue", {"variant": "red"}),
        ]
        for name, title, extra in cases:
            self.assertEqual(match_identity(dict(name=name, **extra), title)["level"], "different")
        self.assertEqual(match_identity({"product_id": "123456"}, "same title", "654321")["level"], "different")
        self.assertEqual(match_identity({"product_id": "123456"}, "new title", "123456")["level"], "id")
