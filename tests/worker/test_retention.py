"""The disk must never fill: expiry, file removal, history trimming, orphan files, crash recovery and the migrations that came with them."""

import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import StoreCase
from trendvn_worker.store import Store, retention, schema

DAY = 86400


class RetentionTests(StoreCase):
    def media(self, jid, source=True, render=True, folder_extra=()):
        """Real files for a job: inbox source, job-folder render, poster and manifest (and any extra names)."""
        fields = {}
        if source:
            path = self.s.root / "inbox" / ("douyin_%s.mp4" % jid)
            path.write_bytes(b"s" * 1000)
            fields["source_file"] = str(path)
        folder = self.s.root / "jobs" / jid
        folder.mkdir(exist_ok=True)
        for name in ("poster.jpg", "manifest.json", *folder_extra):
            (folder / name).write_bytes(b"k" * 10)
        if render:
            (folder / "final.mp4").write_bytes(b"r" * 2000)
            (folder / "analysis.mp4").write_bytes(b"a" * 500)
            fields["output_file"] = str(folder / "final.mp4")
        return fields

    def old(self, days):
        return time.time() - days * DAY

    def test_a_finished_video_loses_its_files_after_a_week_but_keeps_its_poster_and_its_row(self):
        old = self.old(retention.KEEP_FILES_DAYS + 1)
        self.job("p", "published", updated=old, published_at=old, **self.media("p"))
        self.job("fresh", "published", updated=time.time(), published_at=time.time(), **self.media("fresh"))
        result = self.s.prune()
        folder = self.s.root / "jobs" / "p"
        self.assertEqual(sorted(x.name for x in folder.iterdir()), ["manifest.json", "poster.jpg"])
        self.assertFalse((self.s.root / "inbox" / "douyin_p.mp4").exists())
        self.assertTrue((self.s.root / "inbox" / "douyin_fresh.mp4").exists())  # still inside the grace period
        self.assertTrue((self.s.root / "jobs" / "fresh" / "final.mp4").exists())
        self.assertGreaterEqual(result["files_removed"], 3)
        with self.s.connect() as db:
            row = db.execute("SELECT state,source_file,pruned_at FROM jobs WHERE id='p'").fetchone()
        self.assertEqual((row["state"], row["source_file"]), ("published", None))  # the row still remembers the video (no duplicates)
        self.assertIsNotNone(row["pruned_at"])

    def test_a_second_run_does_nothing_and_no_batch_starves_the_rest(self):
        old = self.old(10)
        for n in range(retention.BATCH + 30):
            self.job("j%03d" % n, "rejected", updated=old, source_file="/data/inbox/x%03d.mp4" % n)
        self.s.prune()
        self.s.prune()
        with self.s.connect() as db:
            left = db.execute("SELECT count(*) FROM jobs WHERE pruned_at IS NULL").fetchone()[0]
        self.assertEqual(left, 0)  # the second call reached the rows past the first batch of 200
        self.assertEqual(self.s.prune()["files_removed"], 0)

    def test_jobs_in_progress_and_ready_videos_keep_their_files(self):
        old = self.old(10)
        self.job("q", "queued", updated=old, **self.media("q", render=False))
        self.job("r", "ready", updated=time.time(), **self.media("r"))
        self.job("rv", "needs_review", updated=time.time(), **self.media("rv", render=False))
        self.s.prune()
        for jid in ("q", "r", "rv"):
            self.assertTrue((self.s.root / "inbox" / ("douyin_%s.mp4" % jid)).exists(), jid)

    def test_candidates_and_undecided_videos_expire_with_a_reason(self):
        self.job("c-old", "candidate", first_seen=self.old(retention.CANDIDATE_EXPIRY_DAYS + 1), updated=time.time())
        self.job("c-new", "candidate", first_seen=self.old(1), updated=time.time())
        self.job("n-old", "needs_review", updated=self.old(retention.UNDECIDED_EXPIRY_DAYS + 1))
        self.job("r-old", "ready", updated=self.old(retention.UNDECIDED_EXPIRY_DAYS + 1))
        self.job("r-new", "ready", updated=time.time())
        self.assertEqual(self.s.prune()["expired"], 3)
        with self.s.connect() as db:
            states = {r["id"]: (r["state"], r["reason"]) for r in db.execute("SELECT id,state,reason FROM jobs")}
        self.assertEqual(states["c-old"][0], "rejected")
        self.assertIn("không được tải", states["c-old"][1])
        self.assertEqual((states["c-new"][0], states["r-new"][0]), ("candidate", "ready"))
        self.assertEqual((states["n-old"][0], states["r-old"][0]), ("rejected", "rejected"))

    def test_history_tables_are_trimmed_but_recent_rows_and_running_tasks_stay(self):
        now = time.time()
        with self.s.transaction() as db:
            db.execute("INSERT INTO observations VALUES ('j','s',?,1,1,'e')", (now - 40 * DAY,))
            db.execute("INSERT INTO observations VALUES ('j','s',?,1,1,'e')", (now - DAY,))
            db.execute("INSERT INTO events(at,job_id,event,detail) VALUES (?,?,?,?)", (now - 70 * DAY, "j", "x", ""))
            db.execute("INSERT INTO events(at,job_id,event,detail) VALUES (?,?,?,?)", (now - DAY, "j", "x", ""))
            db.execute("INSERT INTO api_calls VALUES (?,?,?)", (now - 3 * DAY, "m", "s"))
            db.execute("INSERT INTO api_calls VALUES (?,?,?)", (now - 3600, "m", "s"))
            db.execute(
                "INSERT INTO tasks(id,kind,state,started,finished) VALUES ('t1','process','done',?,?)", (now - 30 * DAY, now - 30 * DAY)
            )
            db.execute("INSERT INTO tasks(id,kind,state,started) VALUES ('t2','process','running',?)", (now - 30 * DAY,))
        self.s.prune()
        with self.s.connect() as db:
            counts = {t: db.execute("SELECT count(*) FROM " + t).fetchone()[0] for t in ("observations", "api_calls", "tasks")}
            events = db.execute("SELECT count(*) FROM events WHERE job_id='j'").fetchone()[0]
        self.assertEqual(counts, {"observations": 1, "api_calls": 1, "tasks": 1})
        self.assertEqual(events, 1)
        self.assertEqual(self.s.settings()["gemini_daily_limit"], 12)  # the daily allowance looks back 24 h: an hour-old call is kept

    def test_orphan_files_go_but_young_files_and_files_in_use_stay(self):
        inbox = self.s.root / "inbox"
        used = inbox / "douyin_used.mp4"
        used.write_bytes(b"u")
        self.job("used", "queued", source_file=str(used))
        orphan, young, part = inbox / "orphan.mp4", inbox / "young.mp4", inbox / "x.part"
        for path in (orphan, young, part):
            path.write_bytes(b"o" * 100)
        os.utime(orphan, (self.old(3), self.old(3)))
        folder = self.s.root / "jobs" / "ghost"
        folder.mkdir()
        (folder / "final.mp4").write_bytes(b"g")
        os.utime(folder, (self.old(3), self.old(3)))
        shots = self.s.root / "exports"
        old_shot, new_shot, sample = shots / "shot_123456789.png", shots / "shot_987654321.png", shots / "voice_sample.wav"
        for path in (old_shot, new_shot, sample):
            path.write_bytes(b"p")
        os.utime(old_shot, (self.old(20), self.old(20)))
        os.utime(sample, (self.old(90), self.old(90)))
        result = self.s.prune()
        self.assertFalse(orphan.exists())
        self.assertFalse(folder.exists())
        self.assertFalse(old_shot.exists())
        self.assertTrue(used.exists())
        self.assertTrue(young.exists() and part.exists())  # maybe being written right now
        self.assertTrue(new_shot.exists())
        self.assertTrue(sample.exists())  # not a screenshot: never pruned
        self.assertEqual(result["orphans"], 3)

    def test_nothing_outside_the_data_folder_is_ever_deleted(self):
        outside = Path(self.tmp.name).parent / ("keep-%d.mp4" % os.getpid())
        outside.write_bytes(b"precious")
        link = self.s.root / "jobs" / "linked"
        link.mkdir()
        os.symlink(outside, link / "final.mp4")  # a symlink out of the data folder
        self.job("linked", "rejected", updated=self.old(10), source_file=str(outside), output_file=str(link / "final.mp4"))
        try:
            self.s.prune()
            self.assertTrue(outside.exists(), "a source_file path outside inbox/ must not be followed")
            self.assertFalse((link / "final.mp4").exists())  # the link itself goes, the target stays
        finally:
            outside.unlink(missing_ok=True)

    def test_a_failing_rule_does_not_stop_the_others(self):
        self.job("c", "candidate", first_seen=self.old(10), updated=time.time())

        def boom(now):
            raise RuntimeError("disk error")

        self.s._trim_history = boom
        result = self.s.prune()
        self.assertEqual(result["expired"], 1)
        self.assertIn("disk error", result["errors"][0])

    def test_housekeeping_reports_what_it_pruned(self):
        self.job("c", "candidate", first_seen=self.old(10), updated=time.time())
        self.assertEqual(self.s.housekeeping()["pruned"]["expired"], 1)


class CrashRecoveryTests(StoreCase):
    def test_a_restart_puts_abandoned_videos_back_without_the_owner(self):
        self.job("first", "processing", attempts=1, lease="L", updated=time.time())
        self.job("third", "processing", attempts=2, lease="L", updated=time.time())
        self.assertEqual(self.s.recover_after_restart(), 2)
        with self.s.connect() as db:
            rows = {r["id"]: (r["state"], r["lease"]) for r in db.execute("SELECT id,state,lease FROM jobs")}
        self.assertEqual(rows["first"], ("queued", None))  # tried once: simply try again
        self.assertEqual(rows["third"], ("needs_review", None))  # tried twice: it is the video, not the crash
        self.assertIsNotNone(self.s.claim())

    def test_housekeeping_only_frees_work_that_has_been_stuck_for_half_an_hour(self):
        self.job("busy", "processing", attempts=1, lease="L", updated=time.time() - 60)
        self.job("stuck", "processing", attempts=1, lease="L", updated=time.time() - 3600)
        out = self.s.housekeeping()
        self.assertEqual(out["interrupted_processing"], 1)
        with self.s.connect() as db:
            states = dict(db.execute("SELECT id,state FROM jobs").fetchall())
        self.assertEqual(states, {"busy": "processing", "stuck": "queued"})


class MigrationTests(unittest.TestCase):
    def migrated_main_topics(self, topics):
        """An installation at version 3 whose `main` account has these topics, brought to the latest version."""
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            with store.transaction() as db:
                db.execute("UPDATE accounts SET topics=? WHERE id='main'", (json.dumps(topics),))
                db.execute("PRAGMA user_version = 3")
            Store(folder)  # opening it again runs the missing migrations
            return store.account("main")["topics"]

    def test_the_account_of_a_release_before_news_gets_news(self):
        self.assertEqual(self.migrated_main_topics(list(schema.V2_MAIN_TOPICS)), [*schema.V2_MAIN_TOPICS, "news"])

    def test_an_account_the_owner_edited_is_left_alone(self):
        self.assertEqual(self.migrated_main_topics(["music", "gaming"]), ["music", "gaming"])
        self.assertEqual(self.migrated_main_topics([*schema.V2_MAIN_TOPICS, "news", "food"]), [*schema.V2_MAIN_TOPICS, "news", "food"])

    def test_a_fresh_installation_takes_news_too_and_has_the_cleanup_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            store = Store(folder)
            self.assertIn("news", store.account("main")["topics"])
            with store.connect() as db:
                self.assertIn("pruned_at", {r[1] for r in db.execute("PRAGMA table_info(jobs)")})
                self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], len(schema.MIGRATIONS))


class CandidateAndCountTests(StoreCase):
    def meta(self, score):
        return json.dumps({"score": score})

    def page(self, **extra):
        """The whole dashboard page as the web layer builds it (dashboard_data plus what pages.py adds)."""
        from trendvn_worker import ui

        data = self.s.dashboard_data()
        data.update(notify_channels=[], voice_sample=False, ready=self.s.ready_list(), tasks=self.s.tasks_recent(6))
        data.update(extra)
        return ui.render(data, "CSRF"), data

    def test_the_best_candidates_come_first_whatever_arrived_last(self):
        for n, score in enumerate((10, 900, 50, 700)):
            self.job("d%d" % n, "candidate", first_seen=100 + n, meta=self.meta(score))
        self.job(
            "k",
            "candidate",
            platform="kuaishou",
            source_id="k",
            url="https://www.kuaishou.com/short-video/k",
            first_seen=999,
            meta=self.meta(5),
        )
        ids = [c["id"] for c in self.s.candidates_without_media(3, "douyin")]
        self.assertEqual(ids, ["d1", "d3", "d2"])  # best score first; the newer weak ones and the other platform cannot crowd them out
        self.assertEqual(len(self.s.candidates_without_media(100)), 5)
        self.assertEqual(len(self.s.candidates_without_media(10**9)), 5)  # absurd limits are clamped, not an error

    def test_rendered_videos_waiting_for_approval_count_toward_the_backlog(self):
        self.s.update_settings({"require_approval": True})
        for n in range(3):
            self.job("a%d" % n, "awaiting_approval", topic="comedy")
        self.job("stuck", "awaiting_approval", topic="gaming")  # no account takes gaming: it has nowhere to go, so it does not count
        self.job("q", "queued")
        status = self.s.status()
        self.assertEqual(status["backlog"], 4)

    def test_the_ready_count_is_the_real_total_not_the_length_of_the_first_page(self):
        for n in range(35):
            self.ready("r%02d" % n)
        html, data = self.page()
        self.assertEqual(len(data["ready"]), 30)
        self.assertIn("<b>35</b><small>Sẵn sàng</small>", html)  # the funnel
        self.assertIn(">35</i>", html)  # the navigation badge
        self.assertNotIn("<b>30</b><small>Sẵn sàng</small>", html)

    def test_the_posted_views_label_says_it_covers_the_latest_30(self):
        html, _ = self.page()
        self.assertIn("Lượt xem (30 bài gần nhất)", html)
        self.assertNotIn("Lượt xem bài đã đăng", html)

    def test_the_front_page_shows_free_disk_space(self):
        from trendvn_worker.ui.tabs import home

        self.assertIn("Ổ đĩa", self.page()[0])
        self.assertIn("good", home._disk_chip(5000))
        self.assertIn("warn", home._disk_chip(1500))
        self.assertIn("bad", home._disk_chip(300))
        self.assertIn("mute", home._disk_chip(None))

    def test_stats_are_matched_to_posts_by_video_id(self):
        self.job("pub", "published", publish_url="https://www.tiktok.com/@a/video/7600000000000000001", published_at=time.time())
        self.job("other", "ready", publish_url="https://www.tiktok.com/@a/video/7600000000000000002")  # not published: ignored
        out = self.s.record_stats(
            [
                {"video_id": "7600000000000000001", "views": 12, "likes": 3},
                {"video_id": "7600000000000000002", "views": 99},
                {"video_id": "7600000000000000003", "views": 1},
                {"video_id": "abc"},
            ]
        )
        self.assertEqual(out, {"matched": 1})
        self.assertEqual(self.s.performance(5)[0]["views"], 12)

    def test_posts_today_counts_each_account_in_one_pass(self):
        self.s.add_account({"username": "second", "topics": ["food"]})
        now = time.time()
        self.job("a", "published", account="main", published_at=now)
        self.job("b", "publishing", account="second", published_at=None, updated=now)
        self.job("c", "published", account=None, published_at=now)  # from before accounts: belongs to the default account
        self.job("d", "published", account="main", published_at=now - 3 * DAY)
        counts = self.s.posts_today(self.s.day_start())
        self.assertEqual(counts, {"main": 2, "second": 1})
        status = self.s.status()
        self.assertEqual(status["published_today"], 3)
        self.assertEqual({a["id"]: a["published_today"] for a in status["accounts"]}, {"main": 2, "second": 1})


class ProcessingSafetyTests(StoreCase):
    def setUp(self):
        super().setUp()
        (self.s.root / "gemini.key").write_text("key")
        self.s.update_settings({"processing_enabled": True})

    def test_a_job_taken_away_meanwhile_is_reported_not_raised(self):
        from unittest import mock

        from trendvn_worker import pipeline

        self.job("j", "queued", source_file="/x", content_hash="h")
        with (
            mock.patch.object(pipeline, "_process", side_effect=ValueError("boom")),
            mock.patch.object(self.s, "finish", side_effect=ValueError("Stale lease")),
        ):
            result = pipeline.process_one(self.s)
        self.assertEqual(result["status"], "error")
        self.assertIn("Stale lease", result["reason"])
        self.assertIn("boom", result["reason"])

    def test_a_rate_limit_with_a_stale_lease_is_reported_too(self):
        from unittest import mock

        from trendvn_worker import pipeline
        from trendvn_worker.ai.errors import RateLimited

        self.job("j", "queued", source_file="/x", content_hash="h")
        with (
            mock.patch.object(pipeline, "_process", side_effect=RateLimited("limit")),
            mock.patch.object(self.s, "release", side_effect=ValueError("Stale lease")),
        ):
            self.assertEqual(pipeline.process_one(self.s)["status"], "error")

    def test_a_nearly_full_disk_blocks_processing_without_claiming_anything(self):
        from unittest import mock

        from trendvn_worker import pipeline

        self.job("j", "queued", source_file="/x", content_hash="h")
        with mock.patch.object(pipeline, "free_bytes", return_value=100 << 20):
            result = pipeline.process_one(self.s)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("100 MB", result["reason"])
        self.assertEqual(self.s.status()["counts"], {"queued": 1})  # still waiting: nothing was claimed, nothing lost

    def test_a_one_pixel_video_is_refused_before_any_work(self):
        from unittest import mock

        from trendvn_worker import pipeline

        tiny = {"streams": [{"codec_type": "video", "width": 1, "height": 1}]}
        with mock.patch.object(pipeline, "probe", return_value=(5.0, tiny)), mock.patch.object(pipeline, "file_hash", return_value="h"):
            with self.assertRaisesRegex(ValueError, "quá nhỏ"):
                pipeline._source({"source_file": "/x.mp4", "content_hash": "h"}, {"max_duration": 180})

    def test_error_text_from_ffmpeg_does_not_reveal_server_folders(self):
        from trendvn_worker.media import ffmpeg

        text = "/data/inbox/douyin_1.mp4: Invalid data found when processing input; also /app/trendvn_worker/x.py and 16/9 stay"
        cleaned = ffmpeg.tidy(text)
        self.assertNotIn("/data/", cleaned)
        self.assertNotIn("/app/", cleaned)
        self.assertIn("douyin_1.mp4", cleaned)
        self.assertIn("16/9", cleaned)


class StartupTests(unittest.TestCase):
    def test_a_locked_database_at_start_up_is_retried(self):
        from unittest import mock

        calls = []

        def flaky(db):
            calls.append(1)
            if len(calls) < 3:
                raise sqlite3.OperationalError("database is locked")

        with tempfile.TemporaryDirectory() as folder, mock.patch("trendvn_worker.store.base.initialise", flaky):
            with mock.patch("trendvn_worker.store.base.time.sleep", lambda s: None):
                Store(folder)
        self.assertEqual(len(calls), 3)

    def test_other_database_errors_are_not_swallowed(self):
        from unittest import mock

        def broken(db):
            raise sqlite3.OperationalError("disk I/O error")

        with tempfile.TemporaryDirectory() as folder, mock.patch("trendvn_worker.store.base.initialise", broken):
            with self.assertRaises(sqlite3.OperationalError):
                Store(folder)


if __name__ == "__main__":
    unittest.main()
