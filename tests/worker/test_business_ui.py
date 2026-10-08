"""Business state presentation: active work, resolved evidence and scoped refresh snapshots."""

import time
from types import SimpleNamespace

from tests.support import StoreCase
from trendvn_worker.ui.components import task_panel
from trendvn_worker.ui.messages import user_message
from trendvn_worker.ui.tabs import attention, home
from trendvn_worker.ui.view import View
from trendvn_worker.web.pages import live_data


class BusinessUiTests(StoreCase):
    def app(self):
        return SimpleNamespace(store=self.s, csrf="csrf-test")

    def view(self):
        data = self.s.dashboard_data()
        data.update(tasks=self.s.tasks_for_ui(), notify_channels=[])
        return View(data, "csrf-test")

    def test_active_task_cannot_be_evicted_by_new_finished_commands(self):
        running = self.s.task_create("process_one")
        for _ in range(15):
            other = self.s.task_create("stats")
            self.s.task_update(other, state="done")
        self.assertNotIn(running, [t["id"] for t in self.s.tasks_recent(6)])
        view = self.view()
        self.assertTrue(view.busy_process)
        self.assertIn('data-running="1"', task_panel(view.tasks, kinds=("process_one",)))
        self.assertNotIn("Đọc lượt xem", task_panel(view.tasks, kinds=("process_one",)))

    def test_automatic_processing_blocks_processing_even_without_a_button_task(self):
        self.job("a" * 32, "processing")
        view = self.view()
        self.assertTrue(view.busy_process)
        self.assertTrue(live_data(self.app(), "queue")["running"])

    def test_reconciled_delete_is_history_but_not_a_current_error(self):
        jid = "d" * 32
        self.job(jid, "published", account="main", target="me", publish_url="https://www.tiktok.com/@me/video/123456789")
        tid = self.s.task_create("delete_post", jid)
        self.s.task_update(tid, state="error", error="Locator.wait_for: Timeout 15000ms exceeded. Call log: secret selector")
        with self.s.transaction() as db:
            db.execute(
                "INSERT INTO post_deletions VALUES(?,?,?,?,?,?,?,?)",
                (
                    jid,
                    "test-grant",
                    "unknown",
                    "main",
                    "me",
                    "https://www.tiktok.com/@me/video/123456789",
                    "Chưa biết kết quả",
                    time.time(),
                ),
            )
        view = self.view()
        self.assertEqual(view.attention, 1)
        self.assertIn("Cần kiểm tra kết quả xóa", attention.render(view))
        with self.s.transaction() as db:
            db.execute("UPDATE post_deletions SET state='deleted',reason='Chủ đã kiểm tra: bài đã xóa trên TikTok' WHERE job_id=?", (jid,))
        self.assertEqual(self.view().attention, 0)
        self.assertNotIn(tid, [t["id"] for t in self.s.tasks_for_ui()])
        self.assertIn("Locator.wait_for", self.s.tasks_recent(1)[0]["error"])

    def test_scoped_refresh_never_includes_search_or_settings_composer(self):
        for tab in ("home", "queue", "publish", "attention", "posted", "more"):
            data = live_data(self.app(), tab)
            self.assertEqual(data["tab"], tab)
            self.assertNotIn("data-chat-form", data["html"] or "")
            self.assertNotIn('action="/settings" class="settings', data["html"] or "")
        self.assertIsNone(live_data(self.app(), "more")["html"])
        with self.assertRaises(ValueError):
            live_data(self.app(), "../settings")

    def test_error_copy_preserves_next_step_without_browser_trace(self):
        raw = "Đã mở thao tác xóa nhưng chưa biết TikTok xóa thành công; hãy kiểm tra bài, không tự thử lại. Locator.wait_for: Timeout 15000ms exceeded. Call log: waiting for locator('secret')"
        shown = user_message(raw, True)
        self.assertIn("hãy kiểm tra bài", shown)
        self.assertNotIn("Locator", shown)
        self.assertNotIn("secret", shown)
        self.assertIn("hàng chờ", user_message("Gemini HTTP 504 timed out", True))
        self.assertIn("Nhật ký", user_message("Unexpected internal failure", True))

    def test_manual_mode_is_not_reported_as_broken_automation(self):
        banner = home.banner(self.view())
        self.assertIn("Chế độ thủ công", banner)
        self.assertNotIn("warn", banner)
        self.assertNotIn("&amp;amp;", home.control(self.view()))

    def test_verification_counts_only_latest_channel_reports_for_enabled_accounts(self):
        self.s.channel_report("main", "douyin", "wall")
        data = live_data(self.app(), "attention")
        self.assertEqual(data["badges"]["attention"], 1)
        self.assertIn("Douyin cần bạn xác minh", data["html"])
        self.s.channel_report("main", "douyin", "ok")
        self.assertEqual(live_data(self.app(), "attention")["badges"]["attention"], 0)
