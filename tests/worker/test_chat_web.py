"""The chat over real sockets: only this machine's page may post, the CSRF token and the size limits hold, and a message makes its way
from the composer to an answer in the thread."""

import json
import re
import time
import unittest

from tests.worker.test_product_search import file
from tests.worker.test_web import Server


class ChatHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server()
        _, _, page = cls.srv.req("GET", "/")
        cls.csrf = re.search(rb'name="csrf" value="([^"]+)"', page).group(1).decode()
        cls.origin = "http://localhost:%d" % cls.srv.port

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def post(self, path, payload, origin=None, raw=None):
        body = raw if raw is not None else json.dumps(payload)
        headers = {"Content-Type": "application/json", "Origin": origin or self.origin}
        code, _, data = self.srv.req("POST", path, body, headers)
        return code, json.loads(data) if data[:1] == b"{" else data

    def thread(self):
        return self.srv.req("GET", "/fragment/chat")[2].decode()

    def wait_idle(self):
        for _ in range(100):
            html = self.thread()
            if 'data-busy="0"' in html:
                return html
            time.sleep(0.1)
        self.fail("the chat stayed busy")

    def test_a_post_from_another_site_or_without_the_page_token_is_refused(self):
        code, _ = self.post("/chat/send", {"csrf": self.csrf, "account": "main", "text": "S24"}, origin="https://evil.example")
        self.assertEqual(code, 403)
        for path in ("/chat/send", "/chat/act"):
            code, _ = self.post(path, {"csrf": "wrong", "account": "main", "text": "S24"})
            self.assertEqual(code, 403, path)

    def test_bad_input_is_a_clean_400_and_the_limits_are_per_route(self):
        code, data = self.post("/chat/send", {"csrf": self.csrf, "account": "main", "files": [file("bad.png", b"x")]})
        self.assertEqual(code, 400)
        self.assertIn("error", data)
        code, data = self.post("/chat/send", {"csrf": self.csrf, "account": "main", "text": ""})
        self.assertEqual(code, 400)
        code, _ = self.post("/chat/act", {"csrf": self.csrf, "action": "nope"})
        self.assertEqual(code, 400)
        code, _ = self.post("/chat/send", None, raw="not json")
        self.assertEqual(code, 400)
        code, _, _ = self.srv.req("POST", "/chat/send", "x", {"Content-Length": str((12 << 20) + 1), "Origin": self.origin})
        self.assertEqual(code, 413)
        code, _, _ = self.srv.req("POST", "/chat/act", "x", {"Content-Length": str((16 << 10) + 1), "Origin": self.origin})
        self.assertEqual(code, 413)

    def test_deeply_nested_json_is_a_clean_refusal_not_a_crash(self):
        code, _ = self.post("/chat/send", None, raw="[" * 5000 + "]" * 5000)
        self.assertEqual(code, 403)  # valid JSON, but not an object carrying the page's token
        code, data = self.post("/chat/send", None, raw='{"csrf":' + "[" * 20000)
        self.assertEqual(code, 400)
        code, _ = self.post("/chat/send", None, raw='{"csrf":' + "[" * 900 + "]" * 900 + "}")
        self.assertEqual(code, 403)

    def test_the_fragment_is_only_for_this_machines_page(self):
        code, _, _ = self.srv.req("GET", "/fragment/chat", host="example.com")
        self.assertNotEqual(code, 200)

    def test_a_message_becomes_a_recognised_product_and_a_failed_search_leaves_a_retry(self):
        code, data = self.post("/chat/send", {"csrf": self.csrf, "account": "main", "text": "bàn phím mchose ace68"})
        self.assertEqual(code, 200)
        html = self.wait_idle()
        self.assertIn("bàn phím mchose ace68", html)
        self.assertIn("MCHOSE", html)
        product = int(re.search(r'data-chat-act="find" data-id="(\d+)" data-source="tiktok"', html).group(1))
        code, data = self.post("/chat/act", {"csrf": self.csrf, "action": "find", "id": product, "source": "tiktok", "account": "main"})
        self.assertEqual(code, 200)
        html = self.wait_idle()  # the test agent address refuses connections: the answer is an error with a way to go on
        self.assertIn("Không gọi được agent", html)
        self.assertIn('data-human="true"', html)


if __name__ == "__main__":
    unittest.main()
