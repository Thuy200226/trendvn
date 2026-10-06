"""What the product chat accepts from the page, and how it routes a message: words describe a product, a TikTok product link is checked."""

from types import SimpleNamespace
from unittest import mock

from tests.support import StoreCase
from tests.worker.test_product_search import file
from trendvn_worker.tasks import TaskBusy
from trendvn_worker.web import chat_forms

SHARE = "https://vt.tiktok.com/ZSabc123/"


class FormCase(StoreCase):
    def setUp(self):
        super().setUp()
        self.tasks = mock.Mock()
        self.app = SimpleNamespace(store=self.s, tasks=self.tasks)

    def say(self, text, files=(), account="main"):
        return chat_forms.send(self.app, {"account": account, "text": text, "files": list(files)})

    def product(self, **identity):
        return self.s.chat_add("bot", "product", {"identity": {"name": "MCHOSE ACE68", "query": "mchose ace68"} | identity}, account="main")


class SendTests(FormCase):
    def test_words_start_a_recognition_and_the_log_keeps_the_words_but_not_the_files(self):
        mid = self.say("bàn phím mchose ace68", [file("a.png", b"\x89PNG\r\n\x1a\nphoto")])["id"]
        kind, key = self.tasks.start.call_args.args[:2]
        self.assertEqual((kind, key), ("identify", str(mid)))
        reference = self.tasks.start.call_args.args[2]
        self.assertEqual(reference["files"][0]["name"], "a.png")
        user, bot = self.s.chat_thread()
        self.assertEqual(user["body"], {"text": "bàn phím mchose ace68", "files": [{"name": "a.png", "kind": "image"}], "link": False})
        self.assertEqual((bot["kind"], bot["state"], bot["account"]), ("product", "running", "main"))
        self.assertNotIn("data", str(user["body"]))

    def test_a_share_link_is_checked_not_described_even_with_words_around_it(self):
        mid = self.say("Xem sản phẩm này nhé " + SHARE + " cảm ơn")["id"]
        self.assertEqual(self.tasks.start.call_args.args[:2], ("link", str(mid)))
        self.assertEqual(self.s.chat_get(mid)["kind"], "link")
        self.assertEqual(self.s.chat_get(mid)["body"], {"url": SHARE})

    def test_a_link_with_a_file_is_a_description_of_what_the_files_show(self):
        self.say(SHARE, [file("a.txt", b"Samsung S24")])
        self.assertEqual(self.tasks.start.call_args.args[0], "identify")

    def test_an_empty_message_an_unknown_account_and_bad_files_are_refused_without_a_trace(self):
        for args in (("",), ("   ",), ("S24", (), "nobody"), ("S24", [file("bad.png", b"x")])):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.say(*args)
        self.assertEqual(self.s.chat_thread(), [])
        self.tasks.start.assert_not_called()

    def test_a_job_that_cannot_start_leaves_an_error_answer_not_a_hanging_one(self):
        self.tasks.start.side_effect = TaskBusy("Đang bận")
        with self.assertRaises(ValueError):
            self.say("Samsung S24")
        self.assertEqual([(m["kind"], m["state"]) for m in self.s.chat_thread()], [("say", "done"), ("product", "error")])


class FindTests(FormCase):
    def test_a_search_is_pinned_to_the_chosen_account_and_carries_the_identity(self):
        pid = self.product(links=["https://www.tiktok.com/@a/video/1234567890"])
        mid = chat_forms.act(self.app, {"action": "find", "id": pid, "source": "tiktok", "account": "main"})["id"]
        message = self.s.chat_get(mid)
        self.assertEqual((message["kind"], message["state"], message["account"]), ("videos", "running", "main"))
        self.assertEqual(
            (message["body"]["product"], message["body"]["source"], message["body"]["account_username"]),
            (pid, "tiktok", self.s.account("main")["username"]),
        )
        self.assertEqual(message["body"]["identity"]["name"], "MCHOSE ACE68")
        self.assertEqual(self.tasks.start.call_args.args[:2], ("search", str(mid)))

    def test_the_human_window_needs_a_single_source(self):
        pid = self.product()
        chat_forms.act(self.app, {"action": "find", "id": pid, "source": "douyin", "human": True})
        self.assertEqual(self.tasks.start.call_args.args[0], "search_human")
        with self.assertRaises(ValueError):
            chat_forms.act(self.app, {"action": "find", "id": pid, "source": "auto", "human": True})

    def test_only_a_recognised_product_can_be_searched_and_only_from_known_sources(self):
        running = self.s.chat_add("bot", "product", {}, state="running", account="main")
        said = self.s.chat_add("user", "say", {"text": "x"}, account="main")
        for mid in (running, said, 999):
            with self.subTest(mid=mid), self.assertRaises(ValueError):
                chat_forms.act(self.app, {"action": "find", "id": mid, "source": "tiktok"})
        with self.assertRaises(ValueError):
            chat_forms.act(self.app, {"action": "find", "id": self.product(), "source": "instagram"})
        with self.assertRaises(ValueError):
            chat_forms.act(self.app, {"action": "find", "id": self.product(), "source": "tiktok", "account": "nobody"})


class PickAndConfirmTests(FormCase):
    ITEM = {
        "source_id": "1234567890", "platform": "tiktok", "title": "S24", "url": "https://www.tiktok.com/@a/video/1234567890",
        "match": {"level": "candidate", "score": 90, "reason": "x"},
    }  # fmt: skip

    def videos(self):
        body = {"results": [self.ITEM], "account_username": self.s.account("main")["username"], "identity": {}}
        return self.s.chat_add("bot", "videos", body, account="main")

    def test_a_pick_without_the_owners_confirmation_changes_nothing(self):
        mid = self.videos()
        for confirmed in (None, False, "yes", 1):
            with self.subTest(confirmed=confirmed), self.assertRaises(ValueError):
                chat_forms.act(self.app, {"action": "pick", "id": mid, "source_id": "1234567890", "confirmed": confirmed})
        self.tasks.start.assert_not_called()

    def test_a_confirmed_pick_is_downloaded_for_the_same_account(self):
        mid = self.videos()
        jid = chat_forms.act(self.app, {"action": "pick", "id": mid, "source_id": "1234567890", "confirmed": True, "platform": "tiktok"})[
            "job"
        ]
        self.tasks.start.assert_called_once_with("search_download", jid)

    def link(self, verdict="exact", state="done"):
        found = {"input": SHARE, "product_id": "1729384756102938475", "title": "t", "markers": {"creator_id": "7"}, "tracked": True}
        return self.s.chat_add("bot", "link", {"url": SHARE, "found": found, "verdict": {"verdict": verdict}}, state=state, account="main")

    def test_the_owner_can_confirm_a_link_that_matches_or_might_and_it_is_kept(self):
        for verdict in ("exact", "found", "likely", "unknown"):
            mid = self.link(verdict)
            chat_forms.act(self.app, {"action": "confirm", "id": mid})
            self.assertTrue(self.s.chat_get(mid)["body"]["saved"])
        self.assertEqual(self.s.commission_get("main", "1729384756102938475")["url"], SHARE)
        self.assertEqual(self.s.commission_known("main"), [{"creator_id": "7"}])

    def test_a_link_of_another_product_an_invalid_one_or_an_unfinished_check_cannot_be_confirmed(self):
        for mid in (
            self.link("different"),
            self.link("invalid"),
            self.link("exact", "running"),
            self.s.chat_add("bot", "note", {}, account="main"),
        ):
            with self.subTest(mid=mid), self.assertRaises(ValueError):
                chat_forms.act(self.app, {"action": "confirm", "id": mid})
        self.assertIsNone(self.s.commission_get("main", "1729384756102938475"))

    def test_message_ids_and_actions_are_validated(self):
        for payload in ({"action": "nope"}, {"action": "find", "id": "1"}, {"action": "find", "id": True}, {"action": "find", "id": 0}, {}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                chat_forms.act(self.app, payload)
