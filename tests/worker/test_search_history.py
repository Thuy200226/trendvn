"""Repeated clicks, verification and legacy history keep one search without losing selected video references."""

from concurrent.futures import ThreadPoolExecutor

from tests.worker.test_chat_forms import FormCase
from tests.support import StoreCase
from tests.worker.test_chat_store import result
from trendvn_worker.domain.chat_history import search_messages
from trendvn_worker.ui.tabs.search import chat_thread, chat_side, EMPTY
from trendvn_worker.web import chat_forms
from trendvn_worker.search.runner import find_videos
from unittest import mock


class SearchHistoryTests(FormCase):
    def find(self, pid, source="douyin", **extra):
        return chat_forms.find(self.app, {"id": pid, "source": source, **extra})["id"]

    def test_parallel_clicks_start_one_task_and_keep_one_answer(self):
        pid = self.product()
        with ThreadPoolExecutor(max_workers=6) as pool:
            ids = list(pool.map(lambda _: self.find(pid), range(12)))
        self.assertEqual(len(set(ids)), 1)
        self.tasks.start.assert_called_once_with("search", str(ids[0]))
        self.assertEqual(len(self.s.chat_thread()), 2)

    def test_verification_reuses_the_error_and_clears_its_stale_message(self):
        pid = self.product()
        mid = self.find(pid)
        self.s.chat_set(mid, "error", error="captcha")
        self.assertEqual(self.find(pid, human=True), mid)
        self.assertNotIn("error", self.s.chat_get(mid)["body"])
        self.tasks.start.assert_called_with("search_human", str(mid))
        self.assertEqual(len(self.s.chat_thread()), 2)

    def test_done_search_is_reused_without_erasing_candidates_or_starting_again(self):
        pid = self.product()
        mid = self.find(pid)
        self.s.chat_set(mid, "done", results=[{"source_id": "123"}])
        self.tasks.start.reset_mock()
        self.assertEqual(self.find(pid), mid)
        self.tasks.start.assert_not_called()
        self.assertEqual(self.s.chat_get(mid)["body"]["results"], [{"source_id": "123"}])

    def test_refused_retry_restores_the_original_answer(self):
        pid = self.product()
        mid = self.find(pid)
        self.s.chat_set(mid, "error", error="captcha", note="old")
        previous = self.s.chat_get(mid)
        self.tasks.start.side_effect = ValueError("busy")
        with self.assertRaisesRegex(ValueError, "busy"):
            self.find(pid, human=True)
        self.assertEqual(self.s.chat_get(mid), previous)

    def test_other_sources_and_receivers_get_their_own_answer(self):
        pid = self.product()
        first = self.find(pid)
        other = self.find(pid, "tiktok")
        self.s.chat_set(first, "done")
        self.s.chat_set(other, "done")
        self.s.add_account({"id": "pets", "username": "pets_shop", "topics": ["pets"]})
        self.assertNotEqual(self.find(pid, account="pets"), first)
        self.assertNotEqual(other, first)

    def test_retry_keeps_the_three_pending_task_limit(self):
        mid = self.find(self.product())
        self.s.chat_set(mid, "error", error="captcha")
        for _ in range(3):
            self.s.chat_add("bot", "login", {}, state="running", account="main")
        with self.assertRaisesRegex(ValueError, "Đang có việc"):
            self.find(self.s.chat_get(mid)["body"]["product"])
        self.assertEqual(self.s.chat_get(mid)["state"], "error")

    def test_legacy_duplicate_errors_are_collapsed_without_deleting_selected_answers(self):
        pid = self.product()
        first = self.find(pid)
        self.s.chat_set(first, "error", error="captcha")
        duplicate = self.s.chat_add("bot", "videos", self.s.chat_get(first)["body"], state="error", account="main")
        rows = self.s.chat_thread()
        self.assertEqual([m["id"] for m in search_messages(rows, {})], [pid, duplicate])
        self.assertEqual([m["id"] for m in search_messages(rows, {str(first): [{"state": "queued"}]})], [pid, first, duplicate])
        self.assertEqual(len(self.s.chat_thread()), 3)

    def test_session_checks_are_shown_in_the_channel_row_and_still_polled(self):
        self.s.chat_add("bot", "login", {"channel": "douyin", "mode": "check"}, state="running", account="main")
        data = EMPTY | {"messages": self.s.chat_thread(), "roster": [self.s.account("main")]}
        thread = chat_thread(data)
        self.assertNotIn("Đang đọc phiên", thread)
        self.assertIn('data-busy="1"', thread)
        self.assertIn("Đang đọc phiên", chat_side(data))

    def test_retry_and_fresh_results_preserve_selected_media_even_if_source_omits_it(self):
        pid = self.product()
        mid = self.find(pid, "tiktok")
        selected = result() | {"title": "MCHOSE ACE68", "media": {"kind": "direct", "url": "https://example.com/video.mp4"}}
        self.s.chat_set(mid, "done", results=[selected])
        jid = self.s.videos_select(mid, selected["source_id"], True)
        self.s.chat_set(mid, "error", error="interrupted")
        self.assertEqual(self.find(pid, "tiktok", human=True), mid)
        self.assertEqual(self.s.chat_get(mid)["body"]["results"], [selected])
        find_videos(self.s, mid, mock.Mock(return_value={"items": []}))
        self.assertEqual(self.s.videos_media_ready(jid)["item"], selected)

    def test_new_successful_channel_report_hides_old_login_error(self):
        self.s.chat_add("bot", "login", {"channel": "douyin", "error": "old login failed"}, state="error", account="main")
        self.s.channel_report("main", "douyin", "ok")
        data = EMPTY | {"messages": self.s.chat_thread(), "roster": [self.s.account("main")], "channels": self.s.channel_states()}
        self.assertNotIn("old login failed", chat_side(data))


class WholeSearchTurnTests(StoreCase):
    def test_hiding_product_with_running_child_hides_whole_component_and_late_results(self):
        root = self.s.chat_ask("main", {"text": "ACE68"}, "product", {})
        self.s.chat_set(root, "done", identity={"name": "ACE68"})
        child = self.s.chat_add("bot", "videos", {"product": root, "turn_id": root}, "running", "main")
        other = self.s.chat_add("bot", "product", {"identity": {"name": "S24"}}, account="main")
        self.s.chat_forget(root)
        self.assertEqual([m["id"] for m in self.s.chat_thread()], [other])
        self.assertEqual([m["id"] for m in self.s.chat_waiting()], [child])
        self.s.chat_set(child, "done", results=[])
        late = self.s.chat_add("bot", "videos", {"turn_id": root, "product": root}, account="main")
        self.assertTrue(self.s.chat_get(late)["hidden"])
        self.assertEqual([m["id"] for m in self.s.chat_thread()], [other])

    def test_hidden_parent_is_checked_atomically_at_claim_not_only_by_web(self):
        root = self.s.chat_add("bot", "product", {"identity": {"name": "ACE68"}}, account="main")
        self.s.chat_forget(root)
        with self.assertRaisesRegex(ValueError, "đã xóa"):
            self.s.chat_find("main", {"product": root, "source": "douyin", "account_username": "creator"})
        self.assertEqual(self.s.chat_thread(), [])
