"""Background tasks started from dashboard buttons, against a fake browser agent."""

import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import tasks as tasks_mod

ROOT = Path(__file__).resolve().parents[2]


class FakeAgentHandler(BaseHTTPRequestHandler):
    hits = []
    code = 200
    body = {
        "report": {
            "douyin": {
                "status": "ok",
                "summary": {"jingxuan": {"seen": 5, "qualified": 2, "baseline": False, "new": 1}, "media": {"downloaded": 1}},
            }
        }
    }
    delay = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        FakeAgentHandler.hits.append((self.path, json.loads(self.rfile.read(n) or b"{}"), self.headers.get("Authorization")))
        time.sleep(FakeAgentHandler.delay)
        body = json.dumps(FakeAgentHandler.body).encode()
        self.send_response(FakeAgentHandler.code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


DEFAULT_BODY = dict(FakeAgentHandler.body)


class TaskCase(StoreCase):
    """A task runner whose browser agent is a fake HTTP server."""

    def setUp(self):
        super().setUp()
        FakeAgentHandler.hits.clear()
        FakeAgentHandler.body = dict(DEFAULT_BODY)
        FakeAgentHandler.code, FakeAgentHandler.delay = 200, 0
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeAgentHandler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.real_url = tasks_mod.agent_url
        tasks_mod.agent_url = lambda: "http://127.0.0.1:%d" % self.srv.server_address[1]
        self.lock = threading.Lock()
        self.processed = []
        self.t = tasks_mod.Tasks(self.s, "t" * 40, lambda store: self.processed.append(1) or {"status": "idle"}, self.lock)

    def tearDown(self):
        tasks_mod.agent_url = self.real_url
        self.srv.shutdown()
        super().tearDown()

    def wait(self, tid, seconds=10):
        end = time.time() + seconds
        while time.time() < end:
            row = [x for x in self.s.tasks_recent(20) if x["id"] == tid][0]
            if row["state"] != "running":
                return row
            time.sleep(0.05)
        self.fail("task still running")


class TaskTests(TaskCase):
    def test_collect_task_summarises_each_source_in_vietnamese(self):
        row = self.wait(self.t.start("collect"))
        self.assertEqual(row["state"], "done")
        self.assertIn("Douyin", row["result"])
        self.assertEqual(FakeAgentHandler.hits[0][0], "/api/collect")
        self.assertEqual(FakeAgentHandler.hits[0][2], "Bearer " + "t" * 40)

    def test_update_runs_collect_then_process_and_survives_a_failed_step(self):
        FakeAgentHandler.code = 500
        row = self.wait(self.t.start("update"))
        self.assertEqual(len(row["steps"]), 2)
        self.assertEqual(row["steps"][0]["state"], "error")
        self.assertEqual(row["state"], "done")  # processing still ran, so the round is not a total failure
        self.assertTrue(self.processed)

    def test_a_collect_where_every_source_failed_is_not_reported_as_done(self):
        """A green 'Xong' over 'lỗi, lỗi' made the owner believe the scan had worked."""
        FakeAgentHandler.body = {
            "report": {"douyin": {"status": "error", "reason": "mạng"}, "kuaishou": {"status": "skipped", "reason": "x"}}
        }
        try:
            row = self.wait(self.t.start("collect"))
        finally:
            FakeAgentHandler.body = {
                "report": {
                    "douyin": {
                        "status": "ok",
                        "summary": {"jingxuan": {"seen": 5, "qualified": 2, "baseline": False, "new": 1}, "media": {"downloaded": 1}},
                    }
                }
            }
        self.assertEqual(row["state"], "error")
        self.assertEqual(row["steps"][0]["state"], "error")
        self.assertIn("lỗi", row["result"])

    def test_one_source_working_is_enough_for_the_scan_to_count(self):
        FakeAgentHandler.body = {
            "report": {
                "douyin": {"status": "ok", "summary": {"jingxuan": {"seen": 5, "qualified": 2, "baseline": False, "new": 1}, "media": {}}},
                "kuaishou": {"status": "error", "reason": "mạng"},
            }
        }
        try:
            row = self.wait(self.t.start("collect"))
        finally:
            FakeAgentHandler.body = {
                "report": {
                    "douyin": {
                        "status": "ok",
                        "summary": {"jingxuan": {"seen": 5, "qualified": 2, "baseline": False, "new": 1}, "media": {"downloaded": 1}},
                    }
                }
            }
        self.assertEqual(row["state"], "done")

    def test_a_challenge_found_while_posting_tells_the_owner_the_exact_command_of_that_account(self):
        self.assertIn(
            "trust --account pets",
            tasks_mod.summarize_publish({"status": "challenge", "reason": "TikTok đòi xác minh. ./trendvn tiktok trust --account pets"}),
        )
        self.assertIn("tiktok trust", tasks_mod.summarize_publish({"status": "challenge"}))  # an older agent: the plain command

    def test_agent_busy_and_agent_down_give_owner_readable_errors(self):
        FakeAgentHandler.code = 409
        row = self.wait(self.t.start("collect"))
        self.assertEqual(row["state"], "error")
        self.assertIn("bận", row["error"] + row["result"])
        self.srv.shutdown()
        self.srv.server_close()
        row = self.wait(self.t.start("collect"))
        self.assertIn("agent", (row["error"] + row["result"]).lower())

    def test_a_second_browser_task_is_refused_while_one_runs(self):
        FakeAgentHandler.delay = 1.0
        first = self.t.start("collect")
        with self.assertRaises(tasks_mod.TaskBusy):
            self.t.start("publish", "a" * 32)
        with self.assertRaises(tasks_mod.TaskBusy):
            self.t.start("update")
        self.t.start("process")  # processing does not need the browser, so it may run alongside
        self.wait(first)

    def test_process_shares_the_schedules_lock(self):
        self.lock.acquire()
        try:
            row = self.wait(self.t.start("process"))
            self.assertIn("lịch tự động", (row["error"] + row["result"]))
            self.assertFalse(self.processed)
        finally:
            self.lock.release()

    def test_publish_and_dryrun_pass_the_chosen_video_to_the_agent(self):
        FakeAgentHandler.body = {"status": "published", "url": "https://www.tiktok.com/@u/video/1"}
        row = self.wait(self.t.start("publish", "b" * 32))
        self.assertEqual(FakeAgentHandler.hits[-1][:2], ("/api/publish", {"job_id": "b" * 32}))
        self.assertIn("Đã đăng", row["result"])
        FakeAgentHandler.body = {"status": "dry_run", "screenshot": "/x.png"}
        row = self.wait(self.t.start("dryrun", "b" * 32))
        self.assertEqual(FakeAgentHandler.hits[-1][0], "/api/dry-run")
        self.assertEqual(row["state"], "done")
        FakeAgentHandler.body = {"status": "challenge"}
        row = self.wait(self.t.start("publish", "b" * 32))
        self.assertEqual(row["state"], "error")
        self.assertIn("xác minh", row["result"])

    def test_bad_requests_are_rejected(self):
        for kind, job in (("nope", None), ("publish", None), ("dryrun", "")):
            with self.assertRaises(ValueError):
                self.t.start(kind, job)

    def test_leftover_running_tasks_are_reaped_after_a_restart(self):
        tid = self.s.task_create("collect")
        tasks_mod.Tasks(self.s, "t" * 40, lambda s: {}, self.lock)
        row = [x for x in self.s.tasks_recent(5) if x["id"] == tid][0]
        self.assertEqual(row["state"], "error")
        self.assertFalse(self.s.tasks_running())

    def test_unexpected_exception_never_leaves_a_task_running(self):
        def boom(store):
            raise RuntimeError("kaboom")

        t = tasks_mod.Tasks(self.s, "t" * 40, boom, self.lock)
        row = self.wait(t.start("process"))
        self.assertNotEqual(row["state"], "running")


class ChatTaskTests(TaskCase):
    """The jobs behind the product chat run through the same task system: the browser ones never overlap, the others never wait for it."""

    def videos(self):
        body = {"identity": {"name": "MCHOSE ACE68", "model": "ACE68", "query": "mchose ace68", "queries": {}, "links": []}, "source": "tiktok",
                "account_username": self.s.account("main")["username"], "results": []}  # fmt: skip
        return self.s.chat_add("bot", "videos", body, state="running", account="main")

    def test_a_search_reaches_the_agent_with_the_account_and_ends_its_message(self):
        FakeAgentHandler.body = {"items": [], "note": "không có"}
        mid = self.videos()
        row = self.wait(self.t.start("search", str(mid)))
        self.assertEqual(row["state"], "done")
        path, payload, _ = FakeAgentHandler.hits[0]
        self.assertEqual((path, payload["account"], payload["source"]), ("/api/search", "main", "tiktok"))
        self.assertEqual(self.s.chat_get(mid)["state"], "done")

    def test_a_search_the_agent_refuses_is_an_error_task_and_an_error_message(self):
        FakeAgentHandler.code, FakeAgentHandler.body = 409, {"error": "bận"}
        mid = self.videos()
        row = self.wait(self.t.start("search", str(mid)))
        self.assertEqual(row["state"], "error")
        self.assertEqual(self.s.chat_get(mid)["state"], "error")
        self.assertIn("bận", self.s.chat_get(mid)["body"]["error"])

    def test_recognising_a_product_needs_no_browser_and_hands_its_reference_over_once(self):
        mid = self.s.chat_add("bot", "product", {}, state="running", account="main")
        busy = self.s.task_create("collect")  # a browser job is running: recognition must not care
        row = self.wait(self.t.start("identify", str(mid), {"text": "Xiaomi Band 9", "files": []}))
        self.assertEqual(row["state"], "done")
        self.assertEqual(self.s.chat_get(mid)["body"]["identity"]["brand"], "Xiaomi")
        self.assertNotIn(str(mid), self.t.references)
        self.s.task_update(busy, state="done")

    def test_two_browser_searches_cannot_run_at_once_but_the_second_leaves_no_hanging_message(self):
        FakeAgentHandler.delay = 0.6
        FakeAgentHandler.body = {"items": []}
        first = self.t.start("search", str(self.videos()))
        with self.assertRaises(tasks_mod.TaskBusy):
            self.t.start("search", str(self.videos()))
        self.wait(first)

    def test_ids_are_checked_per_kind(self):
        for kind, key in (("search", "abc"), ("search", None), ("identify", "1; DROP"), ("link", "x" * 20), ("search_download", "12")):
            with self.subTest(kind=kind, key=key), self.assertRaises(ValueError):
                self.t.start(kind, key)

    def test_a_thread_that_cannot_start_leaves_no_running_task_and_no_files_in_memory(self):
        from unittest import mock

        mid = self.s.chat_add("bot", "product", {}, state="running", account="main")
        with mock.patch.object(tasks_mod.threading.Thread, "start", side_effect=RuntimeError("can't start new thread")):
            with self.assertRaises(RuntimeError):
                self.t.start("identify", str(mid), {"text": "x", "files": [{"name": "a.png"}]})
        self.assertFalse(self.s.tasks_running())
        self.assertEqual(self.t.references, {})
        self.t.start("collect")  # the browser is not blocked afterwards

    def test_a_restart_turns_every_unfinished_answer_into_an_error(self):
        mid = self.videos()
        tasks_mod.Tasks(self.s, "t" * 40, lambda s: {}, self.lock)
        self.assertEqual(self.s.chat_get(mid)["state"], "error")


if __name__ == "__main__":
    unittest.main()
