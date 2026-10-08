"""Every check between the owner's click and a deletion in the owner's browser, one by one: a grant is good only for the exact post, account
and moment it was made for. Each test below breaks exactly one of the things the grant is bound to."""

import time
import unittest

from tests.worker.test_post_delete_safety import DeletionCase
from trendvn_worker import tasks as tasks_mod
from trendvn_worker.store.post_deletions import DELETING_SECONDS, PENDING_SECONDS, RUNNING_TASK_SECONDS


class BeginGuards(DeletionCase):
    def change(self, **fields):
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET %s WHERE id=?" % ",".join("%s=?" % k for k in fields), [*fields.values(), self.jid])

    def refused(self, url=None, account="main"):
        with self.assertRaises(ValueError):
            self.s.delete_post_begin(self.jid, url or self.url, account)
        self.assertIsNone(self.s.delete_post_state(self.jid))  # and nothing was recorded

    def test_only_a_published_video_can_be_deleted(self):
        for state in ("ready", "queued", "rejected"):
            self.change(state=state)
            self.refused()

    def test_the_address_must_be_the_one_recorded_for_the_video(self):
        self.refused(url="https://www.tiktok.com/@%s/video/9999999999" % self.who)

    def test_the_account_must_be_the_one_the_video_was_posted_with(self):
        self.change(account="other")
        self.refused()

    def test_a_post_of_another_user_is_never_deleted(self):
        other = "https://www.tiktok.com/@someone.else/video/1234567890"
        self.change(publish_url=other)
        self.refused(url=other)

    def test_the_account_the_video_was_aimed_at_must_be_the_logged_in_one(self):
        self.change(target="someone.else")
        self.refused()

    def test_only_a_real_post_address_is_accepted(self):
        for odd in (
            self.url + "?lang=vi",
            self.url + "/x",
            "http://www.tiktok.com/@%s/video/1234567890" % self.who,
            "https://evil.test/" + self.url,
        ):
            self.change(publish_url=odd)
            self.refused(url=odd)

    def test_a_video_whose_account_no_longer_exists_is_refused_in_words(self):
        ghost = "https://www.tiktok.com/@ghost.shop/video/1234567890"
        self.change(account="ghost", target="ghost.shop", publish_url=ghost)
        with self.assertRaises(ValueError):  # a ValueError the page can show, not a crash
            self.s.delete_post_begin(self.jid, ghost, "ghost")

    def test_every_state_but_failed_blocks_a_new_request(self):
        token = self.grant()
        with self.assertRaises(ValueError):  # pending
            self.grant()
        self.s.delete_post_claim(self.jid, token)
        with self.assertRaises(ValueError):  # deleting
            self.grant()
        self.s.delete_post_finish(self.jid, token, "unknown", "x")
        with self.assertRaises(ValueError):  # unknown
            self.grant()
        self.s.delete_post_checked_deleted(self.jid, self.url, "main")
        with self.assertRaises(ValueError):  # deleted
            self.grant()

    def test_a_failed_request_can_be_made_again_and_replaces_the_old_grant(self):
        old = self.grant()
        self.s.delete_post_cancel(self.jid, old)
        new = self.grant()
        self.assertNotEqual(old, new)
        with self.assertRaises(ValueError):
            self.s.delete_post_claim(self.jid, old)  # the old grant is dead
        self.assertEqual(self.s.delete_post_claim(self.jid, new)["id"], self.jid)


class TwinAndCase(DeletionCase):
    def test_the_same_post_written_with_another_letter_case_is_still_the_same_post(self):
        twin = "b" * 32
        shouting = "https://www.tiktok.com/@%s/video/1234567890" % self.who.upper()
        self.job(twin, "published", account="main", target=self.who, publish_url=shouting, published_at=100)
        self.grant()
        with self.assertRaises(ValueError):
            self.s.delete_post_begin(twin, shouting, "main")

    def test_the_username_in_the_address_may_differ_from_the_account_only_in_case(self):
        shouting = "https://www.tiktok.com/@%s/video/1234567890" % self.who.upper()
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET publish_url=? WHERE id=?", (shouting, self.jid))
        self.assertTrue(self.s.delete_post_begin(self.jid, shouting, "main")["grant"])

    def test_only_ascii_digits_make_a_video_id(self):
        arabic = "https://www.tiktok.com/@%s/video/١٢٣٤٥٦٧" % self.who
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET publish_url=? WHERE id=?", (arabic, self.jid))
        with self.assertRaises(ValueError):
            self.s.delete_post_begin(self.jid, arabic, "main")


class ClaimGuards(DeletionCase):
    def claim_refused(self, token=None):
        with self.assertRaises(ValueError):
            self.s.delete_post_claim(self.jid, token or self.token)
        self.assertEqual(self.state(), "pending")  # a refused claim never moves the row

    def setUp(self):
        super().setUp()
        self.token = self.grant()

    def change(self, **fields):
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET %s WHERE id=?" % ",".join("%s=?" % k for k in fields), [*fields.values(), self.jid])

    def rename(self):  # behind the store's back: the account form refuses this while a deletion is open (see AccountGuards)
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET username='renamed.account' WHERE id='main'")

    def test_the_claim_hands_the_agent_exactly_what_it_may_delete(self):
        self.assertEqual(
            self.s.delete_post_claim(self.jid, self.token),
            {"id": self.jid, "url": self.url, "account": "main", "username": self.who},
        )
        self.assertEqual(self.state(), "deleting")

    def test_a_wrong_grant_claims_nothing(self):
        self.claim_refused("f" * 32)

    def test_a_grant_is_used_once(self):
        self.s.delete_post_claim(self.jid, self.token)
        with self.assertRaises(ValueError):
            self.s.delete_post_claim(self.jid, self.token)

    def test_a_grant_nobody_claimed_in_time_is_void(self):
        self.age(PENDING_SECONDS - 5)
        self.assertEqual(self.s.delete_post_claim(self.jid, self.token)["id"], self.jid)  # still good just inside the limit

    def test_a_late_claim_is_refused(self):
        self.age(PENDING_SECONDS + 5)
        self.claim_refused()

    def test_the_video_must_still_be_published(self):
        self.change(state="ready")
        self.claim_refused()

    def test_the_account_must_not_have_changed_since_the_click(self):
        self.change(account="other")
        self.claim_refused()

    def test_the_address_must_not_have_changed_since_the_click(self):
        self.change(publish_url="https://www.tiktok.com/@%s/video/9999999999" % self.who)
        self.claim_refused()

    def test_the_account_must_not_have_been_renamed_since_the_click(self):
        self.rename()
        self.claim_refused()

    def test_the_account_the_video_was_aimed_at_must_not_have_changed(self):
        self.change(target="someone.else")
        self.claim_refused()


class FinishGuards(DeletionCase):
    def test_only_the_three_known_outcomes_are_accepted(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        for bad in ("success", "ok", "", None, "DELETED"):
            with self.assertRaises(ValueError):
                self.s.delete_post_finish(self.jid, token, bad, "x")
        self.assertEqual(self.state(), "deleting")

    def test_the_wrong_grant_finishes_nothing(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        with self.assertRaises(ValueError):
            self.s.delete_post_finish(self.jid, "f" * 32, "deleted", "x")
        self.assertEqual(self.state(), "deleting")

    def test_an_answer_is_taken_once(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "failed", "x")
        with self.assertRaises(ValueError):
            self.s.delete_post_finish(self.jid, token, "deleted", "late")
        self.assertEqual(self.state(), "failed")

    def test_the_reason_is_kept_but_bounded(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "failed", "x" * 5000)
        with self.s.connect() as db:
            reason = db.execute("SELECT reason FROM post_deletions WHERE job_id=?", (self.jid,)).fetchone()[0]
        self.assertEqual(len(reason), 700)


class CancelGuards(DeletionCase):
    def test_only_a_request_nobody_took_up_can_be_cancelled(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_cancel(self.jid, token)
        self.assertEqual(self.state(), "deleting")  # the agent is already at work: never pretend it did not start

    def test_the_wrong_grant_cancels_nothing(self):
        self.grant()
        self.s.delete_post_cancel(self.jid, "f" * 32)
        self.assertEqual(self.state(), "pending")

    def test_a_cancelled_request_says_so(self):
        token = self.grant()
        self.s.delete_post_cancel(self.jid, token)
        self.assertEqual(self.state(), "failed")


class OwnerCheckGuards(DeletionCase):
    def unknown(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "unknown", "x")

    def change(self, **fields):
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET %s WHERE id=?" % ",".join("%s=?" % k for k in fields), [*fields.values(), self.jid])

    def rename(self):
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET username='renamed.account' WHERE id='main'")

    def both_refused(self, url=None, account="main"):
        for check in (self.s.delete_post_checked_present, self.s.delete_post_checked_deleted):
            with self.assertRaises(ValueError):
                check(self.jid, url or self.url, account)
        self.assertEqual(self.state(), "unknown")

    def test_a_check_settles_nothing_while_the_deletion_is_still_open_or_already_settled(self):
        token = self.grant()  # pending
        self.both_refused_in("pending")
        self.s.delete_post_claim(self.jid, token)  # deleting
        self.both_refused_in("deleting")
        self.s.delete_post_finish(self.jid, token, "deleted", "TikTok xác nhận")
        self.both_refused_in("deleted")  # and nothing leaves 'deleted'

    def both_refused_in(self, state):
        for check in (self.s.delete_post_checked_present, self.s.delete_post_checked_deleted):
            with self.assertRaises(ValueError):
                check(self.jid, self.url, "main")
        self.assertEqual(self.state(), state)

    def test_a_video_without_any_deletion_has_nothing_to_check(self):
        for check in (self.s.delete_post_checked_present, self.s.delete_post_checked_deleted):
            with self.assertRaises(ValueError):
                check(self.jid, self.url, "main")

    def test_the_video_must_still_be_published(self):
        self.unknown()
        self.change(state="ready")
        self.both_refused()

    def test_the_address_must_match_the_one_asked_about(self):
        self.unknown()
        self.both_refused(url="https://www.tiktok.com/@%s/video/9999999999" % self.who)

    def test_the_address_recorded_for_the_video_must_not_have_changed(self):
        self.unknown()
        self.change(publish_url="https://www.tiktok.com/@%s/video/9999999999" % self.who)
        self.both_refused()

    def test_the_account_must_match(self):
        self.unknown()
        self.both_refused(account="other")

    def test_the_account_asked_about_must_be_the_one_the_deletion_was_made_for(self):
        self.unknown()
        self.s.add_account({"username": "second.shop", "id": "second", "topics": ["food"]})
        self.change(account="second")  # the video and the question agree with each other, but not with the deletion
        self.both_refused(account="second")

    def test_the_address_asked_about_must_be_the_one_the_deletion_was_made_for(self):
        self.unknown()
        moved = "https://www.tiktok.com/@%s/video/9999999999" % self.who
        self.change(publish_url=moved)  # the video and the question agree with each other, but not with the deletion
        self.both_refused(url=moved)

    def test_the_video_must_still_belong_to_that_account(self):
        self.unknown()
        self.change(account="other")
        self.both_refused()

    def test_a_renamed_account_is_not_the_one_that_was_asked_about(self):
        self.unknown()
        self.rename()
        self.both_refused()

    def test_the_target_must_still_be_the_account(self):
        self.unknown()
        self.change(target="someone.else")
        self.both_refused()

    def test_the_owner_saying_present_means_failed_and_may_ask_again(self):
        self.unknown()
        self.s.delete_post_checked_present(self.jid, self.url, "main")
        self.assertEqual(self.state(), "failed")
        self.assertTrue(self.grant())  # the post is still there: a new request is allowed

    def test_the_owner_saying_deleted_means_deleted(self):
        self.unknown()
        self.s.delete_post_checked_deleted(self.jid, self.url, "main")
        self.assertEqual(self.state(), "deleted")

    def test_each_check_leaves_its_own_trace(self):
        self.unknown()
        self.s.delete_post_checked_deleted(self.jid, self.url, "main")
        with self.s.connect() as db:
            events = [r[0] for r in db.execute("SELECT event FROM events WHERE job_id=? ORDER BY at, rowid", (self.jid,))]
        self.assertIn("delete_checked_deleted", events)
        self.assertNotIn("delete_checked_present", events)


class AccountGuards(DeletionCase):
    """An account with a deletion that is not settled can neither be renamed nor removed: the grant names a username."""

    def setUp(self):
        super().setUp()
        self.s.add_account({"username": "second.shop", "id": "second", "topics": ["food"]})

    def refused(self):
        with self.assertRaises(ValueError):
            self.s.update_account("main", {"username": "renamed.account"})
        with self.assertRaises(ValueError):
            self.s.delete_account("main")
        self.assertEqual(self.s.account("main")["username"], self.who)

    def test_an_open_request_pins_the_account(self):
        token = self.grant()
        self.refused()  # pending
        self.s.delete_post_claim(self.jid, token)
        self.refused()  # deleting
        self.s.delete_post_finish(self.jid, token, "unknown", "x")
        self.refused()  # unknown

    def test_a_settled_request_frees_the_account(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "failed", "x")
        self.assertEqual(self.s.update_account("main", {"username": "renamed.account"})["username"], "renamed.account")

    def test_other_changes_to_the_account_are_never_blocked(self):
        self.grant()
        self.assertEqual(self.s.update_account("main", {"label": "Kênh chính"})["label"], "Kênh chính")


class ExpiryLimits(DeletionCase):
    def freed(self):
        return self.s.delete_post_expire(time.time())

    def test_a_deletion_the_agent_is_still_working_on_is_not_freed_early(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.age(DELETING_SECONDS - 5)
        self.assertEqual(self.freed(), 0)
        self.assertEqual(self.state(), "deleting")
        self.age(10)
        self.assertEqual(self.freed(), 1)
        self.assertEqual(self.state(), "unknown")  # it may have run: never offered again by itself

    def test_a_request_nobody_took_up_is_freed_only_after_its_time(self):
        self.grant()
        self.age(PENDING_SECONDS - 5)
        self.assertEqual(self.freed(), 0)
        self.age(10)
        self.assertEqual(self.freed(), 1)
        self.assertEqual(self.state(), "failed")


class OwnerRemovedItByHand(DeletionCase):
    """A deletion that failed because the post was already gone: the owner can say so, and only that."""

    def failed(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "failed", "Không thấy bài trong Studio")

    def test_a_failed_deletion_can_be_settled_as_deleted_by_the_owner(self):
        self.failed()
        self.s.delete_post_checked_deleted(self.jid, self.url, "main")
        self.assertEqual(self.state(), "deleted")
        with self.assertRaises(ValueError):
            self.grant()

    def test_a_failed_deletion_cannot_be_settled_as_still_there(self):
        self.failed()
        with self.assertRaises(ValueError):
            self.s.delete_post_checked_present(self.jid, self.url, "main")
        self.assertEqual(self.state(), "failed")

    def test_the_same_guards_hold_for_a_failed_deletion(self):
        self.failed()
        for kwargs in ({"url": "https://www.tiktok.com/@%s/video/9999999999" % self.who}, {"account": "other"}):
            with self.assertRaises(ValueError):
                self.s.delete_post_checked_deleted(self.jid, kwargs.get("url", self.url), kwargs.get("account", "main"))
        self.assertEqual(self.state(), "failed")


class EventsAndTimes(DeletionCase):
    def events(self):
        with self.s.connect() as db:
            return [r[0] for r in db.execute("SELECT event FROM events WHERE job_id=? ORDER BY rowid", (self.jid,))]

    def test_begin_and_abort_leave_a_trace(self):
        token = self.grant()
        self.s.delete_post_abort(self.jid, token, "x" * 3000)
        self.assertEqual(self.events(), ["delete_requested", "post_failed"])
        with self.s.connect() as db:
            self.assertLessEqual(len(db.execute("SELECT reason FROM post_deletions WHERE job_id=?", (self.jid,)).fetchone()[0]), 700)

    def test_the_time_a_deletion_may_take_counts_from_the_claim_not_from_the_click(self):
        token = self.grant()
        self.age(PENDING_SECONDS - 10)
        self.s.delete_post_claim(self.jid, token)
        self.age(DELETING_SECONDS - PENDING_SECONDS)  # long after the click, but not long after the claim
        self.assertEqual(self.s.delete_post_expire(time.time()), 0)
        self.assertEqual(self.state(), "deleting")

    def test_the_cleanup_waits_longer_than_the_worker_waits_for_the_agent(self):
        self.assertGreaterEqual(DELETING_SECONDS, tasks_mod.DELETE_TIMEOUT + 120)


class RunningTaskGuard(DeletionCase):
    def stuck(self, kind, age):
        tid = self.s.task_create(kind, self.jid)
        with self.s.transaction() as db:
            db.execute("UPDATE tasks SET started=started-? WHERE id=?", (age, tid))

    def deleting(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.age(DELETING_SECONDS + 5)

    def test_a_deletion_task_that_is_really_running_holds_the_cleanup_back(self):
        self.deleting()
        self.stuck("delete_post", 5)
        self.assertEqual(self.s.delete_post_expire(time.time()), 0)

    def test_a_deletion_task_stuck_for_longer_than_any_deletion_can_take_no_longer_does(self):
        self.deleting()
        self.stuck("delete_post", RUNNING_TASK_SECONDS + 60)
        self.assertEqual(self.s.delete_post_expire(time.time()), 1)
        self.assertEqual(self.state(), "unknown")

    def test_the_time_after_which_a_running_task_is_taken_for_dead_is_sensible(self):
        self.assertGreater(RUNNING_TASK_SECONDS, tasks_mod.DELETE_TIMEOUT + 60)  # a slow but live deletion is never given up on
        self.deleting()
        self.stuck("delete_post", 3600)  # an hour: dead whatever the exact limit
        self.assertEqual(self.s.delete_post_expire(time.time()), 1)

    def test_a_running_task_of_another_kind_never_holds_it_back(self):
        self.deleting()
        self.stuck("publish", 5)
        self.assertEqual(self.s.delete_post_expire(time.time()), 1)


class RecoverGuards(DeletionCase):
    def test_recovery_leaves_finished_rows_alone(self):
        token = self.grant()
        self.s.delete_post_claim(self.jid, token)
        self.s.delete_post_finish(self.jid, token, "deleted", "xác nhận")
        self.s.delete_post_recover()
        self.assertEqual(self.state(), "deleted")


if __name__ == "__main__":
    unittest.main()
