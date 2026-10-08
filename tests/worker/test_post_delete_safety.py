"""Deleting a posted video must never be recorded as more or less than what happened: an attempt that never began is 'failed' (and may be
tried again), one that may have run is 'unknown' (and is never repeated by itself), and every state offers the owner only what works."""

import unittest
from unittest import mock

from tests.support import StoreCase
from trendvn_worker import tasks as tasks_mod
from trendvn_worker.tasks import AgentError


class DeletionCase(StoreCase):
    def setUp(self):
        super().setUp()
        self.jid = "a" * 32
        self.who = self.s.account("main")["username"]
        self.url = "https://www.tiktok.com/@%s/video/1234567890" % self.who
        self.job(self.jid, "published", account="main", target=self.who, publish_url=self.url, published_at=100)

    def grant(self, jid=None, url=None):
        return self.s.delete_post_begin(jid or self.jid, url or self.url, "main")["grant"]

    def state(self, jid=None):
        with self.s.connect() as db:
            return db.execute("SELECT state FROM post_deletions WHERE job_id=?", (jid or self.jid,)).fetchone()[0]

    def age(self, seconds, jid=None):
        with self.s.transaction() as db:
            db.execute("UPDATE post_deletions SET updated=updated-? WHERE job_id=?", (seconds, jid or self.jid))


class AbortTests(DeletionCase):
    def test_an_attempt_the_agent_never_took_up_is_failed_and_may_be_tried_again(self):
        token = self.grant()
        self.s.delete_post_abort(self.jid, token, "Agent bận")
        self.assertEqual(self.state(), "failed")
        self.assertTrue(self.grant())  # a fresh one-use grant: nothing was attempted

    def test_an_attempt_that_was_taken_up_is_unknown_and_blocks_a_second_one(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_abort(self.jid, token, "hết thời gian chờ")
        self.assertEqual(self.state(), "unknown")
        with self.assertRaises(ValueError):
            self.grant()

    def test_a_finished_deletion_is_never_changed_by_a_late_abort(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "deleted", "TikTok xác nhận")
        self.s.delete_post_abort(self.jid, token, "late")
        self.assertEqual(self.state(), "deleted")

    def test_a_wrong_grant_aborts_nothing(self):
        self.grant()
        self.s.delete_post_abort(self.jid, "f" * 32, "x")
        self.assertEqual(self.state(), "pending")


class TaskStepTests(DeletionCase):
    def run_step(self, agent):
        grant = self.s.delete_post_begin(self.jid, self.url, "main")
        tasks = tasks_mod.Tasks.__new__(tasks_mod.Tasks)
        tasks.store, tasks.token, tasks.references = self.s, "t" * 40, {self.jid: grant}
        steps = mock.Mock()
        steps.begin.return_value = 0
        with mock.patch.object(tasks_mod, "call_agent", agent):
            return tasks._delete_post_step(steps, self.jid), steps

    def test_a_busy_agent_means_nothing_was_attempted(self):
        ok, steps = self.run_step(mock.Mock(side_effect=AgentError("Trình duyệt agent đang bận việc khác")))
        self.assertFalse(ok)
        self.assertEqual(self.state(), "failed")
        self.assertIn("chưa", steps.end.call_args.args[2].lower())
        self.assertTrue(self.grant())  # the owner can simply try again

    def test_an_agent_that_took_the_job_and_then_vanished_leaves_it_unknown(self):
        def agent(path, payload, token, timeout=0):
            self.s.delete_post_claim(payload["job_id"], payload["grant"])
            raise AgentError("Không gọi được agent trình duyệt")

        ok, _ = self.run_step(agent)
        self.assertFalse(ok)
        self.assertEqual(self.state(), "unknown")

    def test_the_wait_for_the_agent_is_longer_than_the_agents_own_slowest_path(self):
        self.assertGreaterEqual(tasks_mod.DELETE_TIMEOUT, 300)

    def test_any_kind_of_failure_of_the_call_is_told_apart_the_same_way(self):
        import json

        for error in (RuntimeError("boom"), json.JSONDecodeError("bad", "x", 0), OSError("reset"), ValueError("odd")):
            with self.s.transaction() as db:
                db.execute("DELETE FROM post_deletions WHERE job_id=?", (self.jid,))
            ok, _ = self.run_step(mock.Mock(side_effect=error))
            self.assertFalse(ok)
            self.assertEqual(self.state(), "failed", repr(error))  # never claimed: nothing was attempted

    def test_the_agent_is_really_given_that_long(self):
        agent = mock.Mock(return_value={"status": "deleted", "reason": "ok"})
        self.run_step(agent)
        self.assertEqual(agent.call_args.kwargs["timeout"], tasks_mod.DELETE_TIMEOUT)

    def test_the_owner_is_told_which_of_the_two_it_was(self):
        _, steps = self.run_step(mock.Mock(side_effect=AgentError("Trình duyệt agent đang bận việc khác")))
        self.assertTrue(steps.end.call_args.args[2].startswith("Chưa thử xóa bài"))

        def took_it(path, payload, token, timeout=0):
            self.s.delete_post_claim(payload["job_id"], payload["grant"])
            raise AgentError("hết thời gian chờ")

        with self.s.transaction() as db:  # a second attempt at the same post: forget the first
            db.execute("DELETE FROM post_deletions WHERE job_id=?", (self.jid,))
        _, steps = self.run_step(took_it)
        self.assertTrue(steps.end.call_args.args[2].startswith("Chưa xác nhận kết quả xóa"))


class FinishTests(DeletionCase):
    def test_deleted_can_only_come_from_a_deletion_the_agent_really_started(self):
        token = self.grant()
        with self.assertRaises(ValueError):
            self.s.delete_post_finish(self.jid, token, "deleted", "no one claimed this")
        self.assertEqual(self.state(), "pending")
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "deleted", "TikTok xác nhận")
        self.assertEqual(self.state(), "deleted")

    def test_failed_and_unknown_are_still_accepted_before_the_claim(self):
        for outcome in ("failed", "unknown"):
            jid = ("b" if outcome == "failed" else "c") * 32
            url = "https://www.tiktok.com/@%s/video/%d" % (self.who, 1234567891 if outcome == "failed" else 1234567892)
            self.job(jid, "published", account="main", target=self.who, publish_url=url, published_at=100)
            token = self.grant(jid, url)
            self.s.delete_post_finish(jid, token, outcome, "x")
            self.assertEqual(self.state(jid), outcome)


class RecoveryTests(DeletionCase):
    def test_a_restart_of_the_worker_settles_what_was_left_open(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        tasks_mod.Tasks(self.s, "t" * 40, lambda *a, **k: None, mock.MagicMock())
        self.assertEqual(self.state(), "unknown")

    def test_after_a_restart_what_never_started_is_failed_and_what_may_have_run_is_unknown(self):
        pending = self.grant()
        other = "b" * 32
        other_url = "https://www.tiktok.com/@%s/video/1234567891" % self.who
        self.job(other, "published", account="main", target=self.who, publish_url=other_url, published_at=100)
        running = self.grant(other, other_url)
        self.s.delete_post_claim(other, running)
        self.s.delete_post_recover()
        self.assertEqual((self.state(), self.state(other)), ("failed", "unknown"))
        self.assertTrue(self.s.delete_post_begin(self.jid, self.url, "main"))
        del pending

    def test_housekeeping_frees_rows_that_stayed_unfinished_while_no_deletion_runs(self):
        token = self.grant()
        self.age(400)
        other = "b" * 32
        other_url = "https://www.tiktok.com/@%s/video/1234567891" % self.who
        self.job(other, "published", account="main", target=self.who, publish_url=other_url, published_at=100)
        running = self.grant(other, other_url)
        self.s.delete_post_claim(other, running)
        self.age(700, other)
        young = "c" * 32
        young_url = "https://www.tiktok.com/@%s/video/1234567892" % self.who
        self.job(young, "published", account="main", target=self.who, publish_url=young_url, published_at=100)
        self.grant(young, young_url)
        self.s.housekeeping()
        self.assertEqual((self.state(), self.state(other), self.state(young)), ("failed", "unknown", "pending"))
        del token

    def test_a_deletion_that_is_really_running_is_left_alone_however_old(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.age(2000)
        self.s.task_create("delete_post", self.jid)
        self.s.housekeeping()
        self.assertEqual(self.state(), "deleting")


class IdentityTests(DeletionCase):
    def test_two_jobs_pointing_at_one_post_cannot_both_be_deleted(self):
        twin = "b" * 32
        self.job(twin, "published", account="main", target=self.who, publish_url=self.url, published_at=100)
        token = self.grant()
        with self.assertRaises(ValueError):
            self.grant(twin)
        self.s.delete_post_abort(self.jid, token, "x")
        self.assertTrue(self.grant(twin))  # once the first attempt never began, the post is free again

    def test_a_username_that_differs_only_in_case_is_the_same_account_at_every_step(self):
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET target=? WHERE id=?", (self.who.upper(), self.jid))
        token = self.grant()
        self.assertEqual(self.s.delete_post_claim(self.jid, token)["id"], self.jid)
        self.s.delete_post_finish(self.jid, token, "unknown", "x")
        self.s.delete_post_checked_present(self.jid, self.url, "main")


class PostedTabTests(DeletionCase):
    def buttons(self, state):
        from trendvn_worker.ui.tabs.posted import _delete_action

        view = mock.Mock(csrf="CSRF", busy_browser=False)
        post = {
            "id": self.jid,
            "publish_url": self.url,
            "account": "main",
            "title": "t",
            "target": self.who,
            "delete_state": state,
            "delete_reason": "",
        }
        html = _delete_action(view, post)
        import re

        return sorted(re.findall(r'action="(/post-delete[a-z-]*)"[^>]*>.*?<button[^>]*>([^<]*)', html, re.S)) or sorted(
            re.findall(r"(/post-delete[a-z-]*)", html)
        )

    def test_each_state_offers_only_what_the_store_will_accept(self):
        actions = lambda state: {a for a, *_ in self.buttons(state)}  # noqa: E731
        self.assertEqual(actions(None), {"/post-delete"})
        self.assertEqual(actions("failed"), {"/post-delete", "/post-delete-checked"})  # try again, or say the post was removed by hand
        self.assertEqual(actions("unknown"), {"/post-delete-checked"})
        for state in ("pending", "deleting", "deleted"):
            self.assertEqual(actions(state), set(), state)

    def render(self, state, reason="", busy=False):
        from trendvn_worker.ui.tabs.posted import _delete_action

        view = mock.Mock(csrf="CSRF", busy_browser=busy)
        post = {
            "id": self.jid, "publish_url": self.url, "account": "main", "title": "t", "target": self.who,
            "delete_state": state, "delete_reason": reason,
        }  # fmt: skip
        return _delete_action(view, post)

    def test_every_form_that_changes_something_asks_the_owner_first(self):
        import re

        for state in (None, "failed", "unknown"):
            html = self.render(state)
            forms = re.findall(r"<form.*?</form>", html, re.S)
            self.assertTrue(forms, state)
            for form in forms:
                self.assertIn("data-confirm=", form, state)

    def test_the_retry_button_waits_while_the_browser_is_busy_the_checks_do_not(self):
        import re

        failed = self.render("failed", busy=True)
        form_of = lambda label: next(f for f in re.findall(r"<form.*?</form>", failed, re.S) if label in f)  # noqa: E731
        self.assertIn("disabled", form_of("Thử xóa lại"))
        self.assertNotIn("disabled", form_of("Đã kiểm tra"))

    def test_a_reason_is_shown_as_text_never_as_markup(self):
        for state in ("failed", "unknown", "deleted"):
            html = self.render(state, '<img src=x onerror=alert(1)> "quoted" <script>x</script>')
            self.assertNotIn("<img", html)
            self.assertNotIn("<script", html)

    def test_a_result_nobody_knows_is_never_worded_as_wait_and_retry(self):
        for reason in ("Connection refused (urlopen error)", "Trình duyệt agent đang bận việc khác", "HTTP 500 busy"):
            unknown = self.render("unknown", reason)
            self.assertNotIn("Video được giữ", unknown, reason)
            self.assertNotIn("thử lại", unknown.split("<form")[0], reason)
        self.assertIn("Chưa kết nối được agent", self.render("failed", "Connection refused (urlopen error)"))  # a failed one may be retried

    def test_an_unknown_result_offers_both_owner_checks_and_never_a_new_deletion(self):
        from trendvn_worker.ui.tabs.posted import _delete_action

        view = mock.Mock(csrf="CSRF", busy_browser=False)
        post = {
            "id": self.jid,
            "publish_url": self.url,
            "account": "main",
            "title": "t",
            "target": self.who,
            "delete_state": "unknown",
            "delete_reason": "",
        }
        html = _delete_action(view, post)
        self.assertIn('value="deleted"', html)
        self.assertIn('value="present"', html)
        self.assertNotIn('action="/post-delete"', html)


if __name__ == "__main__":
    unittest.main()
