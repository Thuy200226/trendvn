"""The jobs behind chat answers: every one ends its message in 'done' or 'error', and a failure never leaves one hanging."""

from unittest import mock

from tests.support import StoreCase
from trendvn_worker.search import runner

PID = "1729384756102938475"
LINK = "https://vt.tiktok.com/ZSabc123/"


def found(**fields):
    base = {
        "input": LINK,
        "chain": [LINK],
        "final": LINK,
        "product_id": PID,
        "title": "Bàn phím MCHOSE ACE68",
        "markers": {"share_creator_id": "7"},
        "tracked": True,
        "stopped": "",
        "kind": "product",
        "status": 200,
    }
    return base | fields


class RecogniseTests(StoreCase):
    def test_the_identity_lands_in_the_message_and_the_line_names_the_product(self):
        mid = self.s.chat_add("bot", "product", {}, state="running", account="main")
        ok, line = runner.run(self.s, "identify", str(mid), agent=None, reference={"text": "Xiaomi Band 9", "files": []})
        self.assertTrue(ok)
        message = self.s.chat_get(mid)
        self.assertEqual((message["state"], message["body"]["identity"]["brand"]), ("done", "Xiaomi"))
        self.assertIn("Xiaomi", line)

    def test_a_product_nobody_can_make_out_is_an_error_message_not_a_hanging_one(self):
        mid = self.s.chat_add("bot", "product", {}, state="running", account="main")
        ok, line = runner.run(self.s, "identify", str(mid), agent=None, reference={"text": "https://example.com/x", "files": []})
        self.assertFalse(ok)
        message = self.s.chat_get(mid)
        self.assertEqual((message["state"], message["body"]["error"]), ("error", line))


class LinkTests(StoreCase):
    def pasted(self):
        return self.s.chat_add("bot", "link", {"url": LINK}, state="running", account="main")

    def check(self, mid, **inspected):
        with mock.patch.object(runner.affiliate, "inspect", return_value=found(**inspected)):
            return runner.check_link(self.s, mid)

    def test_the_first_link_of_an_account_waits_for_the_owner_and_makes_the_product_the_chat_is_about(self):
        mid = self.pasted()
        self.check(mid)
        body = self.s.chat_get(mid)["body"]
        self.assertEqual(body["verdict"]["verdict"], "found")
        self.assertTrue(body["verdict"]["needs_confirmation"])
        self.assertNotIn("saved", body)
        product = self.s.chat_product()
        self.assertEqual((product["id"], product["body"]["identity"]["product_id"]), (body["product"], PID))
        self.assertTrue(product["body"]["from_link"])
        self.assertIsNone(self.s.commission_get("main", PID))

    def test_a_link_for_the_chats_product_with_the_marks_of_confirmed_links_is_kept_at_once(self):
        self.s.commission_save("main", found(product_id="999999", input="https://vt.tiktok.com/ZSold/"))
        self.s.chat_add("bot", "product", {"identity": {"name": "MCHOSE ACE68", "product_id": PID}})
        mid = self.pasted()
        self.check(mid)
        body = self.s.chat_get(mid)["body"]
        self.assertEqual((body["verdict"]["verdict"], body["saved"]), ("exact", True))
        self.assertEqual(self.s.commission_get("main", PID)["url"], LINK)

    def test_a_link_of_another_product_is_shown_and_never_kept(self):
        self.s.chat_add("bot", "product", {"identity": {"name": "Samsung S24", "product_id": "5555555555"}})
        mid = self.pasted()
        self.check(mid)
        body = self.s.chat_get(mid)["body"]
        self.assertEqual(body["verdict"]["verdict"], "different")
        self.assertNotIn("saved", body)
        self.assertIsNone(self.s.commission_get("main", PID))

    def test_a_short_link_that_turns_out_to_be_a_video_becomes_a_video_to_look_up_not_an_invalid_product(self):
        mid = self.pasted()
        video = "https://www.tiktok.com/@creator/video/7234567890123456789"
        self.check(mid, final=video, kind="video", product_id=None, title="")
        body = self.s.chat_get(mid)["body"]
        self.assertEqual(body["video"], video)
        self.assertNotIn("verdict", body)
        placeholder = self.s.chat_get(body["product"])
        self.assertEqual(placeholder["body"]["identity"]["links"], [video])
        self.assertTrue(placeholder["body"]["from_video"])

    def test_a_placeholder_for_a_video_is_not_the_product_a_later_link_is_compared_with(self):
        self.s.chat_add("bot", "product", {"identity": {"name": "MCHOSE ACE68", "query": "mchose ace68"}})
        self.s.chat_add(
            "bot",
            "product",
            {"identity": {"name": "", "query": "Video theo đường dẫn", "links": ["https://www.tiktok.com/@a/video/1234567890"]}},
        )
        self.assertEqual(self.s.chat_product()["body"]["identity"]["name"], "MCHOSE ACE68")

    def test_an_unreadable_link_ends_in_an_error_message(self):
        mid = self.pasted()
        with mock.patch.object(runner.affiliate, "inspect", side_effect=ValueError("Chỉ nhận đường dẫn https của TikTok")):
            ok, line = runner.run(self.s, "link", str(mid), agent=None)
        self.assertFalse(ok)
        self.assertEqual(self.s.chat_get(mid)["state"], "error")
        self.assertIn("TikTok", self.s.chat_get(mid)["body"]["error"])


class VideoTests(StoreCase):
    def asked(self, **identity):
        body = {"identity": {"name": "MCHOSE ACE68", "model": "ACE68", "query": "mchose ace68", "queries": {"tiktok": "mchose ace68", "douyin": "迈从 ACE68"}, "links": []} | identity,
                "source": "tiktok", "account_username": self.s.account("main")["username"], "results": []}  # fmt: skip
        return self.s.chat_add("bot", "videos", body, state="running", account="main")

    ITEM = {
        "source_id": "1234567890",
        "platform": "tiktok",
        "url": "https://www.tiktok.com/@a/video/1234567890",
        "title": "MCHOSE ACE68 review",
    }

    def test_the_agent_gets_the_account_and_the_queries_and_the_answer_is_ranked_and_kept(self):
        mid = self.asked()
        agent = mock.Mock(return_value={"items": [self.ITEM], "note": "Ứng viên từ TikTok"})
        ok, line = runner.run(self.s, "search", str(mid), agent)
        self.assertTrue(ok)
        path, payload, timeout = agent.call_args.args
        self.assertEqual((path, payload["account"], payload["source"], timeout), ("/api/search", "main", "tiktok", runner.SEARCH_TIMEOUT))
        self.assertEqual(payload["queries"]["douyin"], "迈从 ACE68")
        message = self.s.chat_get(mid)
        self.assertEqual((message["state"], len(message["body"]["results"]), message["body"]["note"]), ("done", 1, "Ứng viên từ TikTok"))
        self.assertIn("1 ứng viên", line)

    def test_the_human_window_uses_its_own_route_and_the_long_wait(self):
        agent = mock.Mock(return_value={"items": []})
        runner.run(self.s, "search_human", str(self.asked()), agent)
        self.assertEqual(agent.call_args.args[0::2], ("/api/search/open", runner.HUMAN_TIMEOUT))

    def test_an_agent_failure_is_an_error_message_with_the_reason(self):
        mid = self.asked()
        ok, line = runner.run(self.s, "search", str(mid), mock.Mock(side_effect=ValueError("TikTok yêu cầu xác minh")))
        self.assertFalse(ok)
        self.assertEqual((self.s.chat_get(mid)["state"], self.s.chat_get(mid)["body"]["error"]), ("error", "TikTok yêu cầu xác minh"))

    def test_a_failed_download_puts_the_pick_back_to_waiting_with_the_reason(self):
        mid = self.asked()
        self.s.chat_set(mid, "done", results=[self.ITEM | {"match": {"level": "candidate", "score": 90, "reason": "x"}}])
        jid = self.s.videos_select(mid, "1234567890", True)
        ok, line = runner.run(self.s, "search_download", jid, mock.Mock(side_effect=ValueError("hết hạn")))
        self.assertFalse(ok)
        with self.s.connect() as db:
            self.assertEqual(
                tuple(db.execute("SELECT state,reason FROM jobs WHERE id=?", (jid,)).fetchone()), ("search_selected", "hết hạn")
            )

    def test_a_download_that_is_already_in_the_system_says_so(self):
        mid = self.asked()
        self.s.chat_set(mid, "done", results=[self.ITEM | {"match": {"level": "candidate", "score": 90, "reason": "x"}}])
        jid = self.s.videos_select(mid, "1234567890", True)
        ok, line = runner.run(self.s, "search_download", jid, mock.Mock(return_value={"state": "duplicate"}))
        self.assertTrue(ok)
        self.assertIn("trùng", line)
