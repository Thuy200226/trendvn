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
            wrong_account=lambda ctx, expected: None,
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

    def test_expired_login_page_means_signed_out_and_is_not_the_videos_fault(self):
        """A session TikTok ended sends Studio to /login. That is the account's trouble: reported as signed out (the schedule then leaves the
        account alone and the owner is told), never as a failed post that counts against the video and parks it after three strikes."""
        self.page.url = "https://www.tiktok.com/login?redirect=upload"
        outcome, _, reason = self.run_job()
        self.assertEqual(outcome, "signed_out")
        self.assertIn("hết hạn", reason)

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

    def test_a_profile_that_is_not_signed_in_never_posts(self):
        post.logged_in = lambda ctx: False
        outcome, _, reason = self.run_job()
        self.assertEqual(outcome, "signed_out")
        self.assertIn("@u", reason)
        self.ctx.new_page.assert_not_called()

    def test_a_profile_signed_in_as_somebody_else_never_posts(self):
        post.wrong_account = lambda ctx, expected: "Hồ sơ Chrome đang đăng nhập @khac, không phải @%s." % expected
        outcome, _, reason = self.run_job()
        self.assertEqual((outcome, "@khac" in reason), ("signed_out", True))
        self.ctx.new_page.assert_not_called()
        self.assertEqual(self.run_job(dry_run=True)[0], "signed_out")  # a rehearsal does not upload into the wrong account either

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


class AccountProfileTests(unittest.TestCase):
    """One Chrome profile per TikTok account; every publisher job opens the profile of the account it belongs to."""

    def test_profile_names(self):
        from trendvn_agent.publisher.profile import profile_name

        self.assertEqual(profile_name(None), "publisher")  # the signed-in profile of 1.0 - 1.3 is the main account's
        self.assertEqual(profile_name("main"), "publisher")
        self.assertEqual(profile_name("kenh-meo"), "publisher-kenh-meo")
        for bad in ("../x", "A", "a b", "x" * 40, "a/b"):
            with self.assertRaises(ValueError, msg=bad):
                profile_name(bad)

    def test_cli_takes_the_account_flag_anywhere(self):
        from trendvn_agent.publisher import cli

        self.assertEqual(cli._split(["login", "5", "--account", "pets"]), (["login", "5"], "pets"))
        self.assertEqual(cli._split(["--account", "pets", "status"]), (["status"], "pets"))
        self.assertEqual(cli._split(["status"]), (["status"], None))
        with self.assertRaises(SystemExit):
            cli._split(["login", "--account"])

    def test_a_rehearsal_asks_for_the_account_it_was_given(self):
        from trendvn_agent.publisher import cli, jobs

        sent = []

        def worker(path, payload=None, timeout=900):
            sent.append((path, payload))
            return {"status": "idle", "reason": "No rendered video is waiting"}

        with mock.patch.object(jobs, "worker", worker):
            jobs.dry_run_next(account="pets")
            jobs.dry_run_next()
        self.assertEqual(sent[0], ("/api/publish/peek", {"account": "pets"}))
        self.assertEqual(sent[1], ("/api/publish/peek", {}))  # as before when no account is given
        with mock.patch.object(cli, "dry_run_next", lambda job_id=None, account=None: {"asked": account}) as _:
            with mock.patch("builtins.print") as shown:
                cli.main(["dry-run", "--account", "pets"])
        self.assertIn("pets", str(shown.call_args))  # `tiktok dry-run --account pets` no longer ignores the account

    def test_the_login_hint_names_the_account(self):
        from trendvn_agent.publisher import session

        self.assertEqual(session.account_flag(None), "")
        self.assertEqual(session.account_flag("main"), "")
        self.assertEqual(session.account_flag("pets"), " --account pets")


class RecordingChrome:
    """Stands in for chrome(): remembers which profiles were opened and hands out a context that knows which one it is."""

    def __init__(self):
        self.opened = []

    def __call__(self, profile, **kw):
        self.opened.append(profile)

        class Context:
            def __enter__(inner):
                return inner

            def __exit__(inner, *a):
                return False

        return Context()


class PerAccountJobTests(unittest.TestCase):
    def setUp(self):
        self.chrome = RecordingChrome()
        self.sent = []
        status = {
            "target": "main_user",
            "accounts": [
                {"id": "main", "username": "main_user", "enabled": True},
                {"id": "pets", "username": "meo", "enabled": True},
                {"id": "off", "username": "tat", "enabled": False},
            ],
        }
        self.patches = mock.patch.multiple(
            jobs,
            chrome=self.chrome,
            worker_get=lambda path, timeout=30: status,
            worker=lambda path, payload=None, timeout=900: self.sent.append((path, payload)) or self.answer(path),
            own_descriptions=lambda ctx, target: [
                {
                    "id": "11" if target == "main_user" else "22",
                    "desc": "mô tả " + target,
                    "views": 5,
                    "likes": 1,
                    "comments": 0,
                    "shares": 0,
                }
            ],
        )
        self.patches.start()
        self.addCleanup(self.patches.stop)
        self.unresolved = []

    def answer(self, path):
        if path == "/api/publish/unresolved":
            return {"items": self.unresolved}
        return {"matched": 1}

    def test_stats_are_read_from_every_enabled_account(self):
        result = jobs.run_stats()
        self.assertEqual(self.chrome.opened, ["publisher", "publisher-pets"])  # the disabled account is not visited
        self.assertEqual(result["read"], 2)
        sent = [p for path, p in self.sent if path == "/api/stats"][0]["items"]
        self.assertEqual({i["video_id"] for i in sent}, {"11", "22"})

    def test_one_failing_account_does_not_hide_the_others(self):
        calls = []

        def flaky(profile, **kw):
            calls.append(profile)
            if profile == "publisher":
                raise RuntimeError("Chrome crashed")
            return self.chrome(profile, **kw)

        with mock.patch.object(jobs, "chrome", flaky):
            result = jobs.run_stats()
        self.assertEqual(result["read"], 1)
        self.assertIn("main_user", result["errors"][0])

    def test_unconfirmed_posts_are_looked_for_on_the_account_they_were_posted_to(self):
        self.unresolved = [
            {"id": "a", "caption": "mô tả meo", "account": "pets", "target": "meo"},
            {"id": "b", "caption": "mô tả main_user", "account": None, "target": None},  # made before accounts existed: the default one
        ]
        result = jobs.verify_unresolved()
        self.assertEqual(result, {"resolved": 2, "still_unknown": 0})
        self.assertEqual(sorted(self.chrome.opened), ["publisher", "publisher-pets"])
        urls = {p["id"]: p["url"] for path, p in self.sent if path == "/api/publish/resolve"}
        self.assertEqual(urls, {"a": "https://www.tiktok.com/@meo/video/22", "b": "https://www.tiktok.com/@main_user/video/11"})


class PostUsesTheAccountProfileTests(unittest.TestCase):
    def test_the_claim_decides_the_profile(self):
        opened = RecordingChrome()

        def boom(profile, **kw):
            opened(profile)
            raise RuntimeError("stop here")

        folder = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        (folder / "jobs" / "j1").mkdir(parents=True)
        video = folder / "jobs" / "j1" / "final.mp4"
        video.write_bytes(b"x" * 100)
        job = {"id": "j1", "output_hash": sha256(video), "caption": "c", "target": "meo", "account": "pets"}
        with mock.patch.multiple(post, RUNTIME=folder, chrome=boom):
            self.assertEqual(post.publish_one(job, dry_run=False)[0], "failed")
        self.assertEqual(opened.opened, ["publisher-pets"])


class SignedOutReportingTests(unittest.TestCase):
    def test_a_signed_out_account_is_reported_and_the_video_is_given_back_without_a_strike(self):
        sent = []
        claim = {"status": "claimed", "id": "j1", "lease": "L", "account": "pets", "target": "meo", "output_hash": "h", "caption": "c"}

        def worker(path, payload=None, timeout=900):
            sent.append((path, payload))
            return claim if path.endswith("/claim") else {"ok": True}

        with mock.patch.multiple(jobs, worker=worker, publish_one=lambda c, dry_run: ("signed_out", "", "Chưa đăng nhập")):
            result = jobs.run_publish("j1")
        self.assertEqual(result["status"], "signed_out")
        finish = [p for path, p in sent if path.endswith("/finish")][0]
        self.assertEqual(finish["outcome"], "deferred")  # not counted against the video
        self.assertIn(("/api/accounts/login", {"id": "pets", "ok": False}), sent)

    def test_reporting_never_raises(self):
        def broken(*a, **k):
            raise RuntimeError("worker down")

        with mock.patch.object(jobs, "worker", broken):
            jobs.report_login("pets", True)  # must not raise


class ProfileCheckTests(unittest.TestCase):
    def test_wrong_account_message_and_unreadable_pages(self):
        from trendvn_agent.publisher import profile

        with mock.patch.object(profile, "signed_in_as", lambda ctx: "Someone_Else"):
            self.assertIn("@Someone_Else", profile.wrong_account(None, "meo"))
            self.assertIsNone(profile.wrong_account(None, "someone_else"))  # handles compare without regard to case
        with mock.patch.object(profile, "signed_in_as", lambda ctx: None):
            self.assertIsNone(profile.wrong_account(None, "meo"))  # unreadable: carry on rather than block every post

    def test_signed_in_as_reads_the_page_and_survives_errors(self):
        from trendvn_agent.publisher import profile

        page = mock.MagicMock()
        page.evaluate.return_value = "meo"
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        self.assertEqual(profile.signed_in_as(ctx), "meo")
        page.close.assert_called_once()
        page.goto.side_effect = RuntimeError("offline")
        self.assertIsNone(profile.signed_in_as(ctx))


class SessionCheckTests(unittest.TestCase):
    """The 3-hourly sign-in check: one answer per enabled account, and a profile signed in as somebody else is not signed in."""

    @staticmethod
    def fake_chrome(*args, **kwargs):
        from contextlib import contextmanager

        @contextmanager
        def context():
            yield object()

        return context()

    def test_a_profile_signed_in_as_somebody_else_is_not_signed_in_even_in_the_quick_check(self):
        from trendvn_agent.publisher import session

        def wrong(ctx, expected):
            return "Hồ sơ Chrome đang đăng nhập @khac, không phải @%s." % expected if expected == "me" else None

        with mock.patch.multiple(session, chrome=self.fake_chrome, logged_in=lambda ctx: True, wrong_account=wrong):
            status = session.session_status(expected="me")
            self.assertFalse(status["logged_in"])
            self.assertIn("@khac", status["reason"])
            self.assertTrue(session.session_status(expected="khac")["logged_in"])
            self.assertTrue(session.session_status()["logged_in"])  # nobody to compare with: the cookie is enough

    def test_the_heartbeat_checks_every_enabled_account_against_its_own_name_and_names_the_ones_missing(self):
        from trendvn_agent import publisher, server

        accounts = [
            {"id": "main", "username": "chinh", "enabled": True},
            {"id": "pets", "username": "meo", "enabled": True},
            {"id": "old", "username": "cu", "enabled": False},
        ]
        asked, beats = [], []

        def status(account=None, expected=None, deep=False):
            asked.append((account, expected))
            return {"logged_in": account == "main"}

        with (
            mock.patch.multiple(
                server,
                worker_get=lambda path: {"accounts": accounts},
                worker=lambda path, payload=None, timeout=900: beats.append(payload) or {},
            ),
            mock.patch.object(publisher, "session_status", status),
        ):
            result = server.session({})
        self.assertEqual(
            asked, [("main", "chinh"), ("pets", "meo")]
        )  # the switched-off account is not opened, the others are matched by name
        (beat,) = beats
        self.assertEqual(beat["detail"]["login"], {"main": True, "pets": False})
        self.assertFalse(beat["ok"])
        self.assertIn("@meo", beat["detail"]["text"])
        self.assertNotIn("@chinh", beat["detail"]["text"])
        self.assertEqual(result["accounts"], {"main": True, "pets": False})

    def test_login_is_only_done_when_the_window_is_signed_in_as_the_account_that_was_asked_for(self):
        from types import SimpleNamespace

        from trendvn_agent.publisher import session

        page = SimpleNamespace(goto=lambda *a, **k: None, wait_for_timeout=lambda ms: None)
        ctx = SimpleNamespace(pages=[page], new_page=lambda: page)
        reported = []
        answers = iter(["Đang đăng nhập @khac", "Đang đăng nhập @khac", None])  # the owner signs in wrongly twice, then correctly
        clock = iter(range(0, 10_000))
        fake_time = SimpleNamespace(time=lambda: next(clock))
        with (
            mock.patch.multiple(
                session,
                chrome=lambda *a, **k: self.fake_chrome(),
                logged_in=lambda c: True,
                wrong_account=lambda c, expected: next(answers),
                time=fake_time,
                _report=lambda account, ok: reported.append((account, ok)),
            ),
            mock.patch.object(session, "chrome", lambda *a, **k: _Window(ctx)),
        ):
            self.assertTrue(session.login(10, "pets", expected="meo"))
        self.assertEqual(reported, [("pets", True)])  # reported once, after the right account was in
        self.assertEqual(list(answers), [])  # (it looked three times)

    def test_login_with_the_wrong_account_never_succeeds(self):
        from types import SimpleNamespace

        from trendvn_agent.publisher import session

        page = SimpleNamespace(goto=lambda *a, **k: None, wait_for_timeout=lambda ms: None)
        ctx = SimpleNamespace(pages=[page], new_page=lambda: page)
        reported = []
        clock = iter(range(0, 100_000, 30))
        with (
            mock.patch.multiple(
                session,
                logged_in=lambda c: True,
                wrong_account=lambda c, expected: "Đang đăng nhập @khac",
                time=SimpleNamespace(time=lambda: next(clock)),
                _report=lambda account, ok: reported.append((account, ok)),
            ),
            mock.patch.object(session, "chrome", lambda *a, **k: _Window(ctx)),
        ):
            self.assertFalse(session.login(1, "pets", expected="meo"))
        self.assertEqual(reported, [])  # a wrong sign-in is never reported as signed in


class ChallengeWiringTests(unittest.TestCase):
    """The account the CAPTCHA belongs to travels from the agent to the worker (a mutation of any of these links survived the suite)."""

    def test_the_default_account_names_itself_when_it_clears_the_pause(self):
        from types import SimpleNamespace

        from trendvn_agent.publisher import session

        page = SimpleNamespace(
            goto=lambda *a, **k: None,
            wait_for_timeout=lambda ms: None,
            locator=lambda selector: SimpleNamespace(count=lambda: 1),
        )
        ctx = SimpleNamespace(pages=[page], new_page=lambda: page)
        sent = []
        with (
            mock.patch.multiple(
                session, has_challenge=lambda p: False, worker=lambda path, payload=None, timeout=900: sent.append((path, payload)) or {}
            ),
            mock.patch.object(session, "chrome", lambda *a, **k: _Window(ctx)),
        ):
            self.assertTrue(session.trust(1, None))
            self.assertTrue(session.trust(1, "pets"))
        # None would clear a pause held for ANY account (the macOS launcher always runs it for the main one): it says "main"
        self.assertEqual(sent[0], ("/api/publisher/challenge", {"active": False, "account": "main"}))
        self.assertEqual(sent[1], ("/api/publisher/challenge", {"active": False, "account": "pets"}))

    def test_a_challenge_found_while_posting_names_the_account(self):
        sent = []
        claim = {"status": "claimed", "id": "j1", "lease": "L", "account": "pets", "target": "meo", "output_hash": "h", "caption": "c"}

        def worker(path, payload=None, timeout=900):
            sent.append((path, payload))
            return claim if path.endswith("/claim") else {"ok": True}

        with mock.patch.multiple(jobs, worker=worker, publish_one=lambda c, dry_run: ("challenge", "", "TikTok đòi xác minh")):
            jobs.run_publish("j1")
        self.assertIn(("/api/publisher/challenge", {"active": True, "account": "pets"}), sent)


class _Window:
    """A stand-in for the chrome() context manager that hands out a prepared context."""

    def __init__(self, ctx):
        self.ctx = ctx

    def __enter__(self):
        return self.ctx

    def __exit__(self, *exc):
        return False
