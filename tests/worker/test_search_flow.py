"""Search history, duplicate filtering and download references survive retries independently."""

from types import SimpleNamespace
from unittest import mock

from tests.support import StoreCase
from trendvn_worker.domain.search_queries import explicit
from trendvn_worker.domain.states import STATES
from trendvn_worker.search.runner import find_videos
from trendvn_worker.web import chat_forms


class SearchFlowTests(StoreCase):
    def test_legacy_manual_search_children_disappear_with_their_product_turn(self):
        root = self.s.chat_ask("main", {"text": "ACE68"}, "product", {})
        self.s.chat_set(root, "done")
        child = self.s.chat_add("bot", "videos", {"product": root}, state="error", account="main")
        unrelated = self.s.chat_add("bot", "link", {"product": root}, account="main")
        self.s.chat_forget(child)
        self.assertEqual([r["id"] for r in self.s.chat_thread()], [unrelated])
        self.assertEqual(self.s.chat_get(root)["state"], "done")

    def test_clear_then_retry_same_request_does_not_run_recognition_again(self):
        app = SimpleNamespace(store=self.s, tasks=mock.Mock())
        payload = {"account": "main", "text": "mchose ace68", "files": [], "request_key": "a" * 32}
        first = chat_forms.send(app, payload)
        self.s.chat_set(first["id"], "done")
        self.s.chat_clear()
        self.assertEqual(self.s.chat_thread(), [])
        self.assertEqual(chat_forms.send(app, payload), first)
        app.tasks.start.assert_called_once()
        for _ in range(310):
            self.s.chat_add("bot", "note", {"text": "later"})
        self.assertEqual(chat_forms.send(app, payload), first)
        app.tasks.start.assert_called_once()

    def test_every_existing_state_is_excluded_without_modifying_jobs(self):
        items = []
        for index, state in enumerate(STATES):
            source_id = str(1000000000 + index)
            url = "https://www.douyin.com/video/" + source_id
            self.job(str(index).zfill(32), state, source_id=source_id, url=url)
            items.append({"platform": "douyin", "source_id": source_id, "url": url})
        new, excluded = self.s.videos_new(items)
        self.assertEqual(new, [])
        self.assertEqual(excluded, len(STATES))
        with self.s.connect() as db:
            self.assertEqual({r[0] for r in db.execute("SELECT state FROM jobs")}, set(STATES))

    def test_new_results_after_twenty_existing_videos_are_not_cut_off(self):
        identity = explicit("mchose ace68")
        mid = self.s.chat_add("bot", "videos", {"identity": identity, "source": "douyin"}, state="running", account="main")
        items = []
        for index in range(21):
            source_id = str(1000000000 + index)
            url = "https://www.douyin.com/video/" + source_id
            items.append({"platform": "douyin", "source_id": source_id, "url": url, "title": "MCHOSE ACE68"})
            if index < 20:
                self.job(str(index).zfill(32), "rejected", source_id=source_id, url=url)
        find_videos(self.s, mid, mock.Mock(return_value={"items": items}))
        body = self.s.chat_get(mid)["body"]
        self.assertEqual([r["source_id"] for r in body["results"]], ["1000000020"])
        self.assertEqual(body["existing"], 20)
