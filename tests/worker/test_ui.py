"""The dashboard HTML: tabs, empty states, escaping, confirmations."""

import json
import re
import time
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import ui
from trendvn_worker.web.forms import parse_windows, settings_patch

ROOT = Path(__file__).resolve().parents[2]


class UiTests(StoreCase):
    def render(self):
        d = self.s.dashboard_data()
        d["notify_channels"] = []
        d["voice_sample"] = False
        return ui.render(d, "CSRFTOKEN", ("ok", "Đã lưu"))

    def test_empty_dashboard_renders(self):
        html = self.render()
        self.assertIn("TrendVN", html)
        self.assertIn("CSRFTOKEN", html)

    def test_html_is_escaped(self):
        evil = "<script>alert(1)</script>"
        self.job("e", "awaiting_approval", title=evil, reason=evil, route="vietsub")
        self.job("f", "published", title=evil, publish_url="https://www.tiktok.com/@u/video/7690000000000000009", published_at=time.time())
        self.job("g", "needs_review", title=evil, reason="<img src=x onerror=1>", source_file="/x")
        html = self.render()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertNotIn("<img src=x", html)

    def test_reason_translation_and_labels(self):
        self.assertIn("nhạy cảm", ui.vi_reason("Sensitive content (politics) needs review"))
        self.assertEqual(ui.vi_reason("unknown reason"), "unknown reason")
        self.assertEqual(ui.ago(None), "—")
        self.assertEqual(ui.num(1234567), "1.234.567")

    def test_server_settings_patch_roundtrip(self):
        patch = settings_patch(
            {
                "daily_limit": ["3"],
                "gap_hours": ["2.5"],
                "post_windows": ["11-14, 19-23"],
                "views_tiktok": ["2000000"],
                "views_douyin": ["0"],
                "views_kuaishou": ["5"],
                "views_instagram": ["0"],
                "likes_douyin": ["100"],
                "processing_enabled": ["false"],
                "require_approval": ["true"],
            }
        )
        self.assertEqual(patch["min_publish_gap"], 9000)
        self.assertEqual(patch["post_windows"], [[11, 14], [19, 23]])
        self.s.update_settings(patch)
        with self.assertRaises(ValueError):
            parse_windows("abc")


class UiHtmlTests(StoreCase):
    def render(self, **extra):
        d = self.s.dashboard_data()
        d.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=self.s.tasks_recent(6))
        d.update(extra)
        return ui.render(d, "CSRFX")

    def test_publish_tab_has_the_four_buttons_and_the_confirm_text(self):
        self.ready("a" * 32)
        html = self.render()
        for needle in (
            "Đăng ngay",
            "Xem thử, không đăng",
            "Lưu mô tả",
            "Bỏ video",
            "data-confirm=",
            "Chế độ hiển thị".replace("Chế độ hiển thị", "CHỈ MÌNH TÔI" if False else "CÔNG KHAI"),
        ):
            self.assertIn(needle, html)

    def test_buttons_are_disabled_while_a_task_runs_or_tiktok_asks_for_verification(self):
        self.ready("a" * 32)
        self.s.task_create("collect")
        html = self.render()
        self.assertIn("Đang có việc khác chạy", html)
        self.assertRegex(html, r'<button class="go big"[^>]*disabled')
        self.s.tasks_reap()
        self.s.set_challenge(True)
        html = self.render()
        self.assertIn("TikTok đang đòi xác minh", html)

    def test_user_text_is_escaped_in_the_caption_box_and_task_output(self):
        self.ready("a" * 32)
        self.s.set_caption("a" * 32, "</textarea><script>alert(1)</script> #a1 #b2 #c3")
        tid = self.s.task_create("publish", "a" * 32)
        self.s.task_update(
            tid,
            steps=[{"name": "<b>x</b>", "state": "error", "detail": "<img src=x onerror=alert(2)>"}],
            state="error",
            error="<script>3</script>",
        )
        html = self.render()
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<script>3", html)

    def test_approve_button_only_for_unapproved_videos_and_quick_switches_ask_first(self):
        (Path(self.tmp.name) / "gemini.key").write_text("x" * 30)
        self.ready("a" * 32)
        self.job(
            "w" * 32,
            "awaiting_approval",
            output_file="/d/w.mp4",
            output_hash="h",
            analysis=json.dumps({"caption_vi": "Mô tả đủ dài để qua kiểm tra", "hashtags": ["a1", "b2", "c3"]}),
        )
        html = self.render()
        self.assertEqual(html.count("Duyệt cho lịch tự đăng"), 1)
        self.assertEqual(len(re.findall(r'data-confirm="Bật tự đăng\?', html)), 1)
        self.assertEqual(
            len(re.findall(r'data-confirm="Bật xử lý video\?', html)), 2
        )  # the home switch and the Hàng đợi tab card; both ask first
        self.assertNotRegex(html, r'<button class="go big">\s*✔ Bật xử lý video')
        self.s.update_settings({"publisher_enabled": True})
        self.assertNotIn('data-confirm="Bật tự đăng', self.render())  # turning it OFF stays one tap

    def test_screenshot_name_becomes_a_link_but_arbitrary_paths_do_not(self):
        tid = self.s.task_create("dryrun", "a" * 32)
        self.s.task_update(
            tid,
            steps=[
                {
                    "name": "x",
                    "state": "done",
                    "detail": "Xong. Xem ảnh chụp: /media/shot/shot_1790000000.png và /media/shot/../../etc/passwd",
                }
            ],
            state="done",
        )
        html = ui.task_panel(self.s.tasks_recent(3))
        self.assertIn('href="/media/shot/shot_1790000000.png"', html)
        self.assertNotIn('href="/media/shot/../', html)

    def queued(self, jid, state="queued", n=1):
        self.job(jid, state, url="https://x/" + jid, title="Video chờ " + jid[:4], first_seen=time.time() - n)

    def test_publish_tab_explains_why_it_is_empty(self):
        html = self.render()
        self.assertIn("Chưa có video nào xử lý xong", html)
        self.assertIn("Chưa có video nào để xử lý", html)  # nothing anywhere: tells you to update
        self.queued("q" * 32)
        html = self.render()
        self.assertIn("1 video đang chờ xử lý</b> nhưng công tắc", html)  # waiting but processing OFF: says so
        self.assertIn("Chưa có khóa Gemini", html)  # no key yet: points at the settings instead of a button that would fail
        (Path(self.tmp.name) / "gemini.key").write_text("x" * 30)
        html = self.render()
        self.assertRegex(
            html, r'name="next" value="publish"><input type="hidden" name="processing_enabled" value="true"'
        )  # key present: the switch is one tap
        self.s.update_settings({"processing_enabled": True})
        html = self.render()
        self.assertIn("Xử lý ngay (1)", html)  # waiting and ON: one button to process now
        self.assertNotIn("nhưng công tắc", html)

    def test_queue_tab_lists_what_waits_in_processing_order_and_has_its_own_nav_entry(self):
        self.queued("a" * 32, n=30)
        self.queued("b" * 32, n=10)
        self.queued("c" * 32, "processing", n=5)
        self.queued("d" * 32, "candidate", n=1)
        html = self.render()
        self.assertIn('<section data-tab="queue" id="queue"', html)
        body = html.split('<section data-tab="queue" id="queue"')[1].split("</section>")[0]
        self.assertLess(body.index("Video chờ cccc"), body.index("Video chờ aaaa"))  # being processed first
        self.assertLess(body.index("Video chờ aaaa"), body.index("Video chờ bbbb"))  # then oldest first, as claim() takes them
        self.assertIn("Ứng viên chưa tải về (1)", body)
        self.assertEqual(html.count('data-go="queue"'), 2)  # top nav and bottom nav
        self.assertNotIn("Hàng đợi (đang chờ xử lý)", html)  # no longer buried under Thêm
        d = self.s.dashboard_data()
        self.assertEqual([j["state"] for j in d["queue"]], ["processing", "queued", "queued"])

    def test_status_pills_are_one_card_not_a_scrolling_row(self):
        html = self.render()
        self.assertIn('class="card pills"', html)
        self.assertNotIn("overflow-x:auto;scroll-snap", html)
        self.assertNotIn("white-space:nowrap}.chip", html)

    def test_old_finished_task_panels_are_hidden_on_other_tabs_but_running_ones_stay(self):
        tid = self.s.task_create("process")
        self.s.task_update(tid, steps=[{"name": "x", "state": "done", "detail": "ok"}], state="done")
        tasks = self.s.tasks_recent(3)
        now = tasks[0]["started"]
        self.assertIn("taskpanel", ui.task_panel(tasks, now + 60, ("process",)))
        self.assertEqual(ui.task_panel(tasks, now + 3 * 3600, ("process",)), "")
        self.assertIn("taskpanel", ui.task_panel(tasks, now + 3 * 3600))  # the home panel always shows the latest
        self.s.task_create("collect")
        self.assertIn('data-running="1"', ui.task_panel(self.s.tasks_recent(3), now + 3 * 3600, ("collect",)))

    def test_no_element_ids_are_duplicated(self):
        import re

        self.ready("a" * 32)
        ids = re.findall(r'\sid="([^"]+)"', self.render())
        self.assertEqual(len(ids), len(set(ids)), [i for i in ids if ids.count(i) > 1])


if __name__ == "__main__":
    unittest.main()
