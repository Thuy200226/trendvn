"""Regression checks for exact video actions, discovery queries, request retries and confirmed remote deletions."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest import mock

from tests.support import StoreCase
from trendvn_worker.domain import discovery
from trendvn_worker.domain.search_queries import explicit, query_plan
from trendvn_worker.web import chat_forms


class DiscoveryTests(StoreCase):
    def test_genre_and_sales_are_in_real_queries_and_model_survives(self):
        identity = explicit("bàn phím mchose ace68")
        identity["queries"] = query_plan(identity)
        chosen = discovery.options({"topic": "knowledge", "sales": True, "category": "electronics"})
        queries = discovery.queries(identity, chosen)
        self.assertEqual(set(queries), {"tiktok", "douyin", "kuaishou", "instagram"})
        for source, query in queries.items():
            self.assertIn("ace68", query.casefold())
            self.assertIn("科普" if source in ("douyin", "kuaishou") else "Kiến thức", query)
            self.assertIn("数码配件" if source in ("douyin", "kuaishou") else "Điện tử", query)

    def test_invalid_discovery_choices_never_reach_a_browser(self):
        for payload in ({"topic": []}, {"sales": "true"}, {"sales": True}, {"category": "unknown"}, {"source": "evil"}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                discovery.options(payload)

    def test_parallel_retry_of_same_send_creates_one_question_one_job(self):
        app = SimpleNamespace(store=self.s, tasks=mock.Mock())
        payload = {"account": "main", "text": "mchose ace68", "files": [], "request_key": "a" * 32, "source": "tiktok"}
        with ThreadPoolExecutor(max_workers=8) as pool:
            answers = list(pool.map(lambda _: chat_forms.send(app, payload), range(16)))
        self.assertEqual(len({a["id"] for a in answers}), 1)
        self.assertEqual(len(self.s.chat_thread()), 2)
        app.tasks.start.assert_called_once()

    def test_same_words_with_new_request_are_a_new_search(self):
        app = SimpleNamespace(store=self.s, tasks=mock.Mock())
        for key in ("a" * 32, "b" * 32):
            chat_forms.send(app, {"account": "main", "text": "mchose ace68", "files": [], "request_key": key})
        self.assertEqual(len(self.s.chat_thread()), 4)

    def test_individual_history_delete_hides_its_question_only_and_keeps_internal_answer(self):
        first = self.s.chat_ask("main", {"text": "a"}, "product", {})
        self.s.chat_set(first, "done")
        other = self.s.chat_ask("main", {"text": "b"}, "product", {})
        self.s.chat_forget(first)
        self.assertEqual([m["id"] for m in self.s.chat_thread()], [other - 1, other])
        self.assertEqual(self.s.chat_get(first)["state"], "done")
        with self.assertRaises(ValueError):
            self.s.chat_forget(other)

    def test_deleting_search_child_hides_whole_turn_and_preserves_download_reference(self):
        root = self.s.chat_ask("main", {"text": "model"}, "product", {})
        self.s.chat_set(root, "done")
        child = self.s.chat_add("bot", "videos", {"product": root, "turn_id": root}, account="main", state="running")
        with self.assertRaises(ValueError):
            self.s.chat_forget(root)
        self.s.chat_set(child, "done")
        self.s.chat_forget(child)
        self.assertEqual(self.s.chat_thread(), [])
        self.assertEqual(self.s.chat_get(child)["body"]["product"], root)

    def test_link_dependency_is_not_a_history_turn(self):
        product = self.s.chat_ask("main", {"text": "model"}, "product", {})
        self.s.chat_set(product, "done")
        link = self.s.chat_ask("main", {"text": "link"}, "link", {"product": product})
        self.s.chat_set(link, "done")
        self.s.chat_forget(link)
        self.assertEqual([m["id"] for m in self.s.chat_thread()], [product - 1, product])

    def test_renamed_account_during_recognition_never_starts_search(self):
        from trendvn_worker.search import runner

        who = self.s.account("main")["username"]
        mid = self.s.chat_ask("main", {"text": "mchose ace68"}, "product", {"discovery": discovery.options({}), "account_username": who})

        def recognise(*args):
            self.s.update_account("main", {"username": "replacement_creator"})
            return explicit("mchose ace68")

        agent = mock.Mock()
        with mock.patch.object(runner, "identify", side_effect=recognise), self.assertRaises(ValueError):
            runner.recognise_product(self.s, mid, {"text": "mchose ace68"}, agent)
        agent.assert_not_called()


class ExactQueueTests(StoreCase):
    def test_claim_specific_video_never_falls_back_to_first_video(self):
        self.job("a" * 32, "queued")
        self.job("b" * 32, "queued")
        self.assertEqual(self.s.claim("b" * 32)["id"], "b" * 32)
        self.assertIsNone(self.s.claim("b" * 32))
        self.assertIsNone(self.s.claim("c" * 32))
        self.assertEqual(self.s.claim()["id"], "a" * 32)

    def test_candidate_download_is_claimed_once_and_cannot_be_rejected_in_flight(self):
        jid = "a" * 32
        self.job(jid, "candidate")
        self.assertEqual(self.s.candidate_download(jid)["job_id"], jid)
        with self.assertRaises(ValueError):
            self.s.candidate_download(jid)
        with self.assertRaises(ValueError):
            self.s.decide(jid, "reject")
        self.s.candidate_download_failed(jid, "network")
        self.s.decide(jid, "reject")
        with self.assertRaises(ValueError):
            self.s.candidate_download(jid)


class PostDeletionTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.jid = "a" * 32
        self.who = self.s.account("main")["username"]
        self.url = "https://www.tiktok.com/@%s/video/1234567890" % self.who
        self.job(self.jid, "published", account="main", target=self.who, publish_url=self.url, published_at=100)

    def grant(self):
        return self.s.delete_post_begin(self.jid, self.url, "main")["grant"]

    def test_wrong_url_or_account_cannot_get_a_deletion_grant(self):
        for url, account in ((self.url + "1", "main"), (self.url, "unknown")):
            with self.subTest(url=url, account=account), self.assertRaises(ValueError):
                self.s.delete_post_begin(self.jid, url, account)

    def test_one_use_grant_and_confirmed_deletion_preserve_publishing_history(self):
        token = self.grant()
        before = self.s.published_today(now=101)
        self.assertEqual(self.s.delete_post_claim(self.jid, token)["url"], self.url)
        with self.assertRaises(ValueError):
            self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "deleted", "TikTok confirmed")
        self.assertEqual(self.s.performance()[0]["delete_state"], "deleted")
        self.assertEqual(self.s.published_today(now=101), before)
        with self.assertRaises(ValueError):
            self.grant()

    def test_unknown_result_and_restart_never_allow_automatic_second_deletion(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_recover()
        with self.assertRaises(ValueError):
            self.grant()
        with self.assertRaises(ValueError):
            self.s.delete_post_finish(self.jid, token, "deleted")

    def test_changed_account_after_confirmation_invalidates_claim(self):
        token = self.grant()
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET username='another' WHERE id='main'")
        with self.assertRaises(ValueError):
            self.s.delete_post_claim(self.jid, token)

    def test_owner_checked_present_can_reset_only_exact_unknown_post(self):
        token = self.grant()
        with self.assertRaises(ValueError):
            self.s.delete_post_checked_present(self.jid, self.url, "main")
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "unknown")
        for url, account in ((self.url + "1", "main"), (self.url, "other")):
            with self.assertRaises(ValueError):
                self.s.delete_post_checked_present(self.jid, url, account)
        self.s.delete_post_checked_present(self.jid, self.url, "main")
        self.assertEqual(self.s.performance()[0]["delete_state"], "failed")
        fresh = self.grant()
        self.assertNotEqual(fresh, token)
        with self.assertRaises(ValueError):
            self.s.delete_post_claim(self.jid, token)

    def test_checked_present_form_requires_explicit_confirmation(self):
        from trendvn_worker.web.forms import delete_post_checked

        app = SimpleNamespace(store=mock.Mock())
        with self.assertRaises(ValueError):
            delete_post_checked(app, {"id": [self.jid], "url": [self.url], "account": ["main"]})
        app.store.delete_post_checked_present.assert_not_called()

    def test_owner_verified_deletion_preserves_history_and_blocks_another_attempt(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "unknown")
        before = self.s.published_today(now=101)
        for url, account in ((self.url + "1", "main"), (self.url, "other")):
            with self.assertRaises(ValueError):
                self.s.delete_post_checked_deleted(self.jid, url, account)
        self.s.delete_post_checked_deleted(self.jid, self.url, "main")
        post = self.s.performance()[0]
        self.assertEqual(post["delete_state"], "deleted")
        self.assertIn("Chủ đã kiểm tra", post["delete_reason"])
        self.assertEqual(self.s.published_today(now=101), before)
        with self.assertRaises(ValueError):
            self.grant()
        with self.assertRaises(ValueError):
            self.s.delete_post_checked_deleted(self.jid, self.url, "main")
        with self.assertRaises(ValueError):
            self.s.delete_post_finish(self.jid, token, "deleted")

    def test_checked_deletion_form_requires_explicit_confirmation_and_known_outcome(self):
        from trendvn_worker.web.forms import delete_post_checked

        app = SimpleNamespace(store=mock.Mock())
        form = {"id": [self.jid], "url": [self.url], "account": ["main"], "outcome": ["deleted"]}
        with self.assertRaises(ValueError):
            delete_post_checked(app, form)
        app.store.delete_post_checked_deleted.assert_not_called()
        with self.assertRaises(ValueError):
            delete_post_checked(app, form | {"confirmed": ["true"], "outcome": ["maybe"]})
        delete_post_checked(app, form | {"confirmed": ["true"]})
        app.store.delete_post_checked_deleted.assert_called_once_with(self.jid, self.url, "main")

    def test_owner_checked_deletion_refuses_changed_job_account_or_state(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "unknown")
        for column, value in (("account", "other"), ("state", "ready")):
            with self.s.transaction() as db:
                old = db.execute("SELECT " + column + " FROM jobs WHERE id=?", (self.jid,)).fetchone()[0]
                db.execute("UPDATE jobs SET " + column + "=? WHERE id=?", (value, self.jid))
            with self.assertRaises(ValueError):
                self.s.delete_post_checked_deleted(self.jid, self.url, "main")
            with self.s.transaction() as db:
                db.execute("UPDATE jobs SET " + column + "=? WHERE id=?", (old, self.jid))

    def test_account_cannot_be_deleted_or_renamed_with_unresolved_deletion(self):
        self.s.add_account({"username": "second_creator", "topics": ["music"]})
        self.s.delete_post_begin(self.jid, self.url, "main")
        with self.assertRaises(ValueError):
            self.s.delete_account("main")
        with self.assertRaises(ValueError):
            self.s.update_account("main", {"username": "replacement_creator"})
