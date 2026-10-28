"""Phase K, worker side: a failed workflow step reaches the owner (once per 6 hours), and housekeeping leaves a video that is being processed alone."""

import threading
import time
from types import SimpleNamespace
from unittest import mock

from tests.support import StoreCase
from trendvn_worker import notify
from trendvn_worker.web import api


class AlertRouteTests(StoreCase):
    def app(self):
        return SimpleNamespace(store=self.s, process_lock=threading.Lock(), log=lambda *_: None)

    def sent(self):
        messages = []
        self.s.notifier = lambda kind, text, key="": messages.append((kind, text, key))
        return messages

    def test_a_failed_step_is_an_urgent_message_keyed_by_the_step(self):
        messages = self.sent()
        self.assertEqual(api.alert(self.app(), {"step": "01 collect", "detail": "500 - boom"}), {"ok": True})
        kind, text, key = messages[0]
        self.assertEqual((kind, key), ("urgent", "workflow:01 collect"))
        self.assertIn("01 collect", text)
        self.assertIn("500 - boom", text)

    def test_the_message_never_carries_a_bearer_token_markup_or_more_than_300_characters(self):
        messages = self.sent()
        api.alert(self.app(), {"step": "<b>x</b> 02 publish", "detail": "failed with Bearer abc123secret and " + "z" * 500})
        text = messages[0][1]
        self.assertNotIn("abc123secret", text)
        self.assertIn("Bearer ***", text)
        self.assertNotIn("<", messages[0][2])
        self.assertLess(len(text), 520)

    def test_an_empty_step_still_gives_a_message(self):
        messages = self.sent()
        api.alert(self.app(), {})
        self.assertEqual(messages[0][2], "workflow:unknown")

    def test_the_same_step_failing_every_cycle_is_one_phone_message_not_eight_a_day(self):
        sent = []
        with (
            mock.patch.object(notify, "send", lambda cfg, text: sent.append(text) or {"x": True}),
            mock.patch.object(notify, "load_config", lambda root: {"ntfy": "https://ntfy.sh/t"}),
        ):
            self.s.notifier = notify.Notifier(self.s)
            for _ in range(3):
                api.alert(self.app(), {"step": "01 collect", "detail": "boom"})
            api.alert(self.app(), {"step": "01 process", "detail": "boom"})  # another step is another message
        self.assertEqual(len(sent), 2)


class HousekeepingLockTests(StoreCase):
    def test_a_video_that_is_being_processed_is_not_put_back_while_the_processing_lock_is_held(self):
        """A slow video can look stuck for over 30 minutes; recovering it under a live run made two runs work on the same file."""
        self.job("slow", "processing", attempts=1, lease="L", updated=time.time() - 3600)
        app = SimpleNamespace(store=self.s, process_lock=threading.Lock(), log=lambda *_: None)
        app.process_lock.acquire()
        self.assertEqual(api.housekeeping(app, {})["interrupted_processing"], 0)
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='slow'").fetchone()[0], "processing")
        app.process_lock.release()
        self.assertEqual(api.housekeeping(app, {})["interrupted_processing"], 1)  # nobody is processing: it really is stuck
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='slow'").fetchone()[0], "queued")

    def test_the_other_housekeeping_still_runs_while_processing_is_busy(self):
        self.job("old", "publishing", updated=time.time() - 3000, publish_lease="P")
        app = SimpleNamespace(store=self.s, process_lock=threading.Lock(), log=lambda *_: None)
        app.process_lock.acquire()
        self.assertEqual(api.housekeeping(app, {})["uncertain_publishing"], 1)
