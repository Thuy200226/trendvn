"""Publisher outcomes (never raises, unknown after the Post click) and logging that never breaks a job."""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_agent.publisher import jobs, post
from trendvn_agent.publisher.text import sha256

ROOT = Path(__file__).resolve().parents[2]


class PublisherOutcomeTests(unittest.TestCase):
    """publish_one must never raise and must never turn a pre-click error into 'unknown' or a post-click error into 'failed'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.real = (post.RUNTIME, post.chrome)
        post.RUNTIME = Path(self.tmp.name)
        folder = Path(self.tmp.name) / "jobs" / "j1"
        folder.mkdir(parents=True)
        (folder / "final.mp4").write_bytes(b"x" * 100)
        self.job = {
            "id": "j1",
            "output_hash": sha256(folder / "final.mp4"),
            "caption": "Mô tả #a1 #b2 #c3",
            "target": "u",
            "visibility": "public",
        }

    def tearDown(self):
        post.RUNTIME, post.chrome = self.real
        self.tmp.cleanup()

    def test_chrome_failing_to_start_is_a_plain_failure(self):
        def boom(*a, **k):
            raise RuntimeError("Chrome crashed")

        post.chrome = boom
        outcome, url, reason = post.publish_one(self.job, dry_run=False)
        self.assertEqual(outcome, "failed")
        self.assertIn("Chrome crashed", reason)

    def test_missing_or_changed_file_is_refused_before_any_browser(self):
        post.chrome = lambda *a, **k: (_ for _ in ()).throw(AssertionError("browser must not start"))
        self.assertEqual(post.publish_one(dict(self.job, output_hash="other"), False)[0], "failed")
        self.assertEqual(post.publish_one(dict(self.job, id="nope"), False)[0], "failed")

    def test_error_after_the_post_click_is_unknown_never_failed(self):
        orig = post._publish_one

        def clicked_then_boom(job, dry_run, st):
            st["clicked"] = True
            raise RuntimeError("network died while verifying")

        post._publish_one = clicked_then_boom
        try:
            outcome, _, reason = post.publish_one(self.job, dry_run=False)
        finally:
            post._publish_one = orig
        self.assertEqual(outcome, "unknown")
        self.assertIn("network died", reason)

    def test_run_publish_always_reports_back_to_the_worker(self):
        calls = []
        real_worker = jobs.worker
        jobs.worker = lambda path, payload=None, timeout=900: calls.append((path, payload)) or (
            {"status": "claimed", "id": "j1", "lease": "L", **{k: self.job[k] for k in ("output_hash", "caption", "target", "visibility")}}
            if path.endswith("/claim")
            else {"ok": True}
        )
        post.chrome = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no display"))
        try:
            res = jobs.run_publish("j1")
        finally:
            jobs.worker = real_worker
        self.assertEqual(res["status"], "failed")
        finish = [c for c in calls if c[0].endswith("/finish")]
        self.assertEqual(len(finish), 1)
        self.assertEqual((finish[0][1]["outcome"], finish[0][1]["lease"]), ("failed", "L"))
        self.assertEqual(calls[0][1], {"job_id": "j1"})


class ScriptedStudioTests(unittest.TestCase):
    """The whole of publish_one against a scripted browser: every branch must give the right outcome and never raise."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name) / "jobs" / "j1"
        folder.mkdir(parents=True)
        (folder / "final.mp4").write_bytes(b"x" * 100)
        self.job = {
            "id": "j1",
            "output_hash": sha256(folder / "final.mp4"),
            "caption": "Mô tả #a1 #b2 #c3",
            "target": "u",
            "visibility": "public",
        }
        self.page = mock.MagicMock()
        self.page.url = "https://www.tiktok.com/tiktokstudio/upload"
        self.target = mock.MagicMock()
        self.ctx = mock.MagicMock()
        self.ctx.new_page.return_value = self.page
        self.shots = []
        self.descriptions = []  # what the public profile shows; each call of own_descriptions returns the list as it is then

        class Chrome:
            def __init__(inner, *a, **k):
                pass

            def __enter__(inner):
                return self.ctx

            def __exit__(inner, *a):
                return False

        def take(page, name):
            self.shots.append(name)
            return "/shots/%s.png" % name

        patches = mock.patch.multiple(
            post,
            RUNTIME=Path(self.tmp.name),
            chrome=Chrome,
            logged_in=lambda ctx: True,
            own_descriptions=lambda ctx, target: list(self.descriptions),
            wait_for_upload_ui=lambda page: (self.target, mock.MagicMock()),
            wait_uploaded=lambda page: True,
            dismiss_popups=lambda page: None,
            set_caption=lambda page, editor, caption: True,
            set_visibility=lambda page, wanted: True,
            studio_shows=lambda ctx, caption: False,
            shot=take,
            export_shot=lambda page, name: "/shots/%s.png" % name,
        )
        patches.start()
        self.addCleanup(patches.stop)
        sleeps = mock.patch.object(post.time, "sleep", lambda s: None)
        sleeps.start()
        self.addCleanup(sleeps.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_job(self, dry_run=False, **changes):
        return post.publish_one(dict(self.job, **changes), dry_run=dry_run)

    def test_dry_run_stops_before_the_post_button(self):
        outcome, url, _ = self.run_job(dry_run=True)
        self.assertEqual((outcome, url), ("dry_run", "/shots/dry_run.png"))
        self.assertFalse(self.target.locator.return_value.first.click.called)
        self.page.close.assert_called_once()

    def test_no_file_input_is_a_failure_with_a_screenshot(self):
        """Regression: a local variable called `shot` once hid the shot() function and turned this into an UnboundLocalError."""
        post.wait_for_upload_ui = lambda page: (self.target, None)
        outcome, picture, reason = self.run_job()
        self.assertEqual((outcome, picture), ("failed", "/shots/no_file_input.png"))
        self.assertIn("TikTok Studio", reason)

    def test_every_failure_step_names_its_screenshot(self):
        cases = {
            "upload_slow": dict(wait_uploaded=lambda page: False),
            "caption": dict(set_caption=lambda page, editor, caption: False),
            "visibility": dict(set_visibility=lambda page, wanted: False),
        }
        for name, patch in cases.items():
            with self.subTest(name), mock.patch.multiple(post, **patch):
                self.shots.clear()
                outcome, picture, _ = self.run_job()
                self.assertEqual((outcome, picture), ("failed", "/shots/%s.png" % name))

    def test_expired_login_page_is_a_failure(self):
        self.page.url = "https://www.tiktok.com/login?redirect=upload"
        self.assertEqual(self.run_job()[0], "failed")

    def test_challenge_before_the_click_pauses_publishing(self):
        def blocked(page):
            raise post.Challenge("TikTok đòi xác minh")

        post.wait_for_upload_ui = blocked
        outcome, picture, reason = self.run_job()
        self.assertEqual((outcome, picture), ("challenge", "/shots/challenge.png"))
        self.assertIn("trust", reason)

    def test_challenge_after_the_click_is_unknown(self):
        def blocked(page):
            raise post.Challenge("TikTok đòi xác minh")

        with mock.patch.object(post, "_confirm_post", blocked):
            outcome, _, _ = self.run_job()
        self.assertEqual(outcome, "unknown")

    def test_error_after_the_click_is_unknown_and_before_it_is_failed(self):
        def broken(page):
            raise RuntimeError("page crashed")

        with mock.patch.object(post, "_confirm_post", broken):
            self.assertEqual(self.run_job()[0], "unknown")
        self.shots.clear()
        post.set_caption = lambda page, editor, caption: (_ for _ in ()).throw(RuntimeError("editor crashed"))
        outcome, picture, _ = self.run_job()
        self.assertEqual((outcome, picture), ("failed", "/shots/error.png"))

    def test_post_is_confirmed_only_by_a_new_id_with_the_same_caption(self):
        self.descriptions = [{"id": "1", "desc": "bài cũ"}]
        self.assertEqual(self.run_job()[0], "unknown")  # clicked, nothing new appeared on the profile
        calls = []

        def profile(ctx, target):
            calls.append(1)
            return list(self.descriptions) + ([{"id": "2", "desc": "mô tả #a1 #b2 #c3"}] if len(calls) > 1 else [])

        post.own_descriptions = profile
        outcome, url, _ = self.run_job()
        self.assertEqual((outcome, url), ("published", "https://www.tiktok.com/@u/video/2"))

    def test_private_post_is_confirmed_in_studio_instead_of_the_profile(self):
        post.studio_shows = lambda ctx, caption: True
        outcome, url, _ = self.run_job(visibility="private")
        self.assertEqual((outcome, url), ("published", ""))

    def test_same_caption_already_on_the_account_is_refused_before_uploading(self):
        self.descriptions = [{"id": "1", "desc": "Mô tả #a1 #b2 #c3"}]
        self.assertEqual(self.run_job()[0], "duplicate")
        self.assertEqual(self.run_job(manual=True)[0], "deferred")
        self.ctx.new_page.assert_not_called()


class LoggingNeverBreaksJobsTests(unittest.TestCase):
    def test_log_survives_an_unwritable_log_file(self):
        from trendvn_agent import log as log_module

        real = log_module.DATA
        try:
            log_module.DATA = Path("/proc/nonexistent-dir")  # cannot be created or written
            log_module.log("still fine")
        finally:
            log_module.DATA = real


if __name__ == "__main__":
    unittest.main()
