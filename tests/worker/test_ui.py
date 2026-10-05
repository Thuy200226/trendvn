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
        self.assertIn("giới hạn cứng", ui.vi_reason("Sensitive content (hard stop: sexual) needs review"))
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

    def test_the_verification_card_and_the_post_buttons_give_the_command_for_the_account_that_has_it(self):
        self.s.add_account({"username": "meo_channel", "id": "pets", "topics": ["pets"]})
        self.s.set_challenge(True, "pets")
        html = self.render()
        self.assertIn("./trendvn tiktok trust --account pets", html)
        self.assertIn("@meo_channel", html)
        self.s.set_challenge(False, "pets")
        self.s.set_challenge(True, "main")
        html = self.render()
        self.assertIn("./trendvn tiktok trust", html)
        self.assertNotIn("trust --account", html)

    def confirm_text(self, job_id):
        html = self.render()
        match = re.search(r'data-confirm="([^"]*)"', html[html.index(job_id) :])
        import html as html_lib

        return html_lib.unescape(match.group(1))

    def test_the_post_now_question_uses_the_limit_and_the_golden_hours_of_the_account_that_will_post(self):
        self.s.update_settings({"daily_limit": 5, "post_windows": []})  # the channel as a whole may post a lot, any time
        self.s.update_account("main", {"topics": ["music"]})
        self.s.add_account({"username": "meo_channel", "id": "pets", "topics": ["pets"]})
        self.s.update_account("pets", {"daily_limit": 1})
        self.job("old" + "0" * 29, "published", account="pets", published_at=time.time(), output_file="/d/o.mp4")
        self.ready("c" * 32, topic="pets")
        question = self.confirm_text("c" * 32)
        self.assertIn("@meo_channel", question)
        self.assertIn("đã đăng đủ 1/1", question)  # that account's own 1 a day, not the channel's 5
        self.s.update_account("pets", {"daily_limit": 3})
        hour = self.s.local_now().hour
        start = (hour + 5) % 23
        self.s.update_account("pets", {"windows": [[start, start + 1]]})  # an hour that is not now, for this account only
        question = self.confirm_text("c" * 32)
        self.assertNotIn("đã đăng đủ", question)
        self.assertIn("ngoài giờ vàng", question.lower())

    def test_an_unconfirmed_post_stops_only_the_post_buttons_of_its_own_account(self):
        from trendvn_worker.ui.tabs import publish
        from trendvn_worker.ui.view import View

        self.s.update_account("main", {"topics": ["music"]})
        self.s.add_account({"username": "meo_channel", "id": "pets", "topics": ["pets"]})
        self.job("u" * 32, "publish_unknown", account="pets", target="meo_channel", output_file="/d/u.mp4")
        self.ready("m" * 32, topic="music")
        self.ready("p" * 32, topic="pets")
        d = self.s.dashboard_data()
        d["ready"] = []
        view = View(d, "CSRF")
        self.assertEqual(publish.blocked_reason(view, {"topic": "music"}), "")  # the other account is free to post
        reason = publish.blocked_reason(view, {"topic": "pets"})
        self.assertIn("@meo_channel", reason)
        self.assertIn("chưa xác nhận", reason)

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


class BannerTests(StoreCase):
    """The green banner may only say everything runs by itself when it does: set up, heartbeats fresh, nothing waiting for the owner."""

    def render(self):
        d = self.s.dashboard_data()
        d["notify_channels"] = []
        d["voice_sample"] = False
        return ui.render(d, "CSRFTOKEN", None)

    def set_up(self):
        (self.s.root / "gemini.key").write_text("k" * 30)
        self.s.update_settings({"processing_enabled": True, "publisher_enabled": True})
        self.s.heartbeat("discovery", True, {"text": "ok"})
        self.s.heartbeat("publisher", True, {"text": "ok"})

    def age_heartbeat(self, component, seconds):
        with self.s.transaction() as db:
            raw = json.loads(db.execute("SELECT value FROM settings WHERE key=?", ("hb_" + component,)).fetchone()[0])
            raw["at"] = time.time() - seconds
            db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(raw), "hb_" + component))

    def test_both_switches_on_is_not_enough_when_nothing_has_reported_yet(self):
        self.s.update_settings({"processing_enabled": False})
        (self.s.root / "gemini.key").write_text("k" * 30)
        self.s.update_settings({"processing_enabled": True, "publisher_enabled": True})
        html = self.render()
        self.assertNotIn("Đang tự động hoàn toàn", html)  # collector and publisher read "chưa kết nối"
        self.assertIn("Chưa tự động hoàn toàn", html)

    def test_a_complete_setup_with_fresh_heartbeats_and_nothing_waiting_is_green(self):
        self.set_up()
        self.assertIn("Đang tự động hoàn toàn", self.render())

    def test_a_video_waiting_for_the_owners_approval_keeps_it_from_being_green(self):
        self.set_up()
        self.s.update_settings({"require_approval": True})
        self.job("w", "awaiting_approval", route="vietsub", output_file="/d/w.mp4")
        html = self.render()
        self.assertNotIn("Đang tự động hoàn toàn", html)
        self.assertIn("chờ bạn duyệt", html)

    def test_a_collector_that_stopped_reporting_says_the_schedule_may_be_off(self):
        self.set_up()
        self.age_heartbeat("discovery", 8 * 3600)  # three scheduled runs missed
        html = self.render()
        self.assertNotIn("Đang tự động hoàn toàn", html)
        self.assertIn("./trendvn n8n activate", html)
        self.age_heartbeat("discovery", 5 * 3600)  # one run late is still fine
        self.assertIn("Đang tự động hoàn toàn", self.render())

    def test_a_publisher_that_reports_trouble_is_not_called_silent(self):
        """Fresh heartbeat saying 'not signed in' is not 'the schedule may be off': the owner has to sign in, not look at n8n."""
        self.set_up()
        self.s.add_account({"username": "meo_channel", "id": "pets", "topics": ["pets"]})
        self.s.heartbeat("publisher", False, {"login": {"main": True, "pets": False}, "text": "Chưa đăng nhập: @meo_channel"})
        html = self.render()
        banner = re.search(r'<div class="banner warn">(.*?)</div>', html).group(1)
        self.assertIn("Trình đăng TikTok", banner)
        self.assertIn("báo lỗi", banner)
        self.assertNotIn("n8n", banner)  # (not the scheduler's fault)

    def test_a_video_still_waiting_for_approval_keeps_it_amber_even_after_the_approval_switch_was_turned_off(self):
        self.set_up()
        self.s.update_settings({"require_approval": True})
        self.job("w", "awaiting_approval", route="vietsub", output_file="/d/w.mp4")
        self.s.update_settings({"require_approval": False})  # the scheduler only posts 'ready' videos: this one still waits for a click
        self.assertNotIn("Đang tự động hoàn toàn", self.render())


class WhyNotPostedTests(StoreCase):
    """A ready video says why the schedule has not posted it yet, in words, from the same numbers the scheduler uses."""

    def render(self):
        d = self.s.dashboard_data()
        d.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=[])
        return ui.render(d, "CSRFX")

    def wait(self):
        """The text of the 'why not posted yet' line of the one ready card."""
        found = re.findall(r'<div class="note small wait">(.*?)</div>', self.render())
        self.assertEqual(len(found), 1, found)
        return found[0]

    def hour(self):
        return self.s.local_now().hour

    def setUp(self):
        super().setUp()
        self.s.update_settings({"publisher_enabled": True, "post_windows": [], "daily_limit": 2, "min_publish_gap": 0})
        self.s.update_account("main", {"topics": ["comedy"]})
        self.ready("a" * 32, topic="comedy")

    def test_the_switch_being_off_is_the_first_thing_said(self):
        self.s.update_settings({"publisher_enabled": False})
        self.assertIn("Công tắc Tự đăng đang tắt", self.wait())

    def test_a_video_waiting_for_the_owner_says_so(self):
        self.s.update_settings({"require_approval": True})
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET state='awaiting_approval' WHERE id=?", ("a" * 32,))
        self.assertIn("Chờ bạn duyệt", self.wait())

    def test_an_account_that_has_posted_enough_today_is_named_with_its_numbers(self):
        for n in range(2):
            self.job("p%d" % n, "published", account="main", target="user5706026522362", published_at=time.time(), topic="comedy")
        text = self.wait()
        self.assertIn("Chưa đăng vì", text)
        self.assertIn("đã đăng đủ 2/2 bài hôm nay", text)

    def test_the_minimum_gap_since_the_last_post_is_said_with_the_time_left(self):
        """The most common reason between two posts: the card used to promise 'the next check will post it' while the scheduler said wait."""
        self.s.update_settings({"min_publish_gap": 3 * 3600})
        self.job("last", "published", account="main", target="user5706026522362", published_at=time.time() - 600, topic="comedy")
        text = self.wait()
        self.assertIn("Chưa đăng vì", text)
        self.assertIn("giãn cách", text)
        self.assertRegex(text, r"2 giờ 5\d phút|3 giờ|2 giờ")  # about 2 h 50 min left of the 3 h
        self.assertNotIn("sẽ đăng ở lần kiểm tra", text)

    def test_a_video_that_failed_to_post_recently_is_not_promised_to_the_next_check(self):
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET last_publish_fail=?,publish_fails=1 WHERE id=?", (time.time() - 600, "a" * 32))
        text = self.wait()
        self.assertIn("lần đăng trước lỗi", text)
        self.assertNotIn("sẽ đăng ở lần kiểm tra", text)

    def test_another_post_being_sent_or_unconfirmed_or_a_verification_pause_is_said(self):
        self.job("busy", "publishing", account="main", target="user5706026522362", topic="comedy", output_file="/d/b.mp4")
        self.assertIn("đang được đăng", self.wait())
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET state='publish_unknown' WHERE id='busy'")
        self.assertIn("chưa xác nhận", self.wait())
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET state='published',published_at=? WHERE id='busy'", (time.time() - 99999,))
        self.s.set_challenge(True)
        self.assertIn("xác minh", self.wait())

    def test_outside_the_golden_hours_says_when_they_open(self):
        start = (self.hour() + 3) % 24
        self.s.update_settings({"post_windows": [[start, start + 1]]})
        text = self.wait()
        self.assertIn("ngoài giờ vàng", text)
        self.assertIn("%02d" % start, text)

    def test_a_signed_out_account_is_named(self):
        self.s.set_account_login("main", False)
        self.assertIn("chưa đăng nhập TikTok", self.wait())

    def test_when_nothing_holds_it_back_it_says_the_next_check_will_post_it(self):
        self.assertIn("lần kiểm tra lịch kế tiếp", self.wait())


class ReadableTitlesTests(StoreCase):
    """The source title is Chinese for most videos: lists show the Vietnamese caption first so the owner can tell what each one is."""

    CHINESE = "咪进城啦🐈可以在魔都街头偶遇吗"
    CAPTION = "Chú mèo lạc vào thành phố và cái kết bất ngờ"

    def render(self):
        d = self.s.dashboard_data()
        d.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=[])
        return ui.render(d, "CSRFX")

    def analysis(self):
        return json.dumps({"caption_vi": self.CAPTION + " #meo #viral", "hashtags": ["meo", "viral", "cute"], "kind": "dialogue"})

    def test_a_waiting_video_is_listed_by_its_vietnamese_caption_with_the_source_title_beside_it(self):
        self.job("q" * 32, "queued", title=self.CHINESE, analysis=self.analysis())
        html = self.render()
        self.assertIn(self.CAPTION, html)
        self.assertNotIn("#meo", html.split(self.CAPTION)[1][:40])  # the hashtags are not part of a title
        self.assertIn(self.CHINESE, html)

    def test_a_held_video_card_and_a_posted_row_show_it_too(self):
        self.job("r" * 32, "needs_review", title=self.CHINESE, analysis=self.analysis(), reason="Audio needs review")
        self.job(
            "p" * 32,
            "published",
            title=self.CHINESE,
            analysis=self.analysis(),
            published_at=time.time(),
            publish_url="https://www.tiktok.com/@a/video/1",
        )
        html = self.render()
        self.assertGreaterEqual(html.count(self.CAPTION), 2)

    def test_a_video_without_a_caption_yet_keeps_its_title_and_a_damaged_analysis_breaks_nothing(self):
        self.job("n" * 32, "queued", title=self.CHINESE)
        self.job("b" * 32, "queued", title="hỏng", analysis="{not json")
        html = self.render()
        self.assertIn(self.CHINESE, html)
        self.assertIn("hỏng", html)

    def test_the_unconfirmed_post_card_names_the_account_and_the_caption(self):
        self.s.add_account({"username": "meo_channel", "id": "pets", "topics": ["pets"]})
        self.job(
            "u" * 32,
            "publish_unknown",
            title=self.CHINESE,
            caption="Mô tả đã đăng #a #b #c",
            account="pets",
            target="meo_channel",
            updated=time.time() - 3600,
        )
        html = self.render()
        card = html[html.index("Chưa xác nhận đã đăng") :]
        self.assertIn("@meo_channel", card[:900])
        self.assertIn("Mô tả đã đăng", card[:900])
        self.assertIn("1 giờ", card[:900])


if __name__ == "__main__":
    unittest.main()
