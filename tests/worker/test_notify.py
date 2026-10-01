"""Phone notifications: channel validation, secrets handling, throttling."""

import json
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import notify

ROOT = Path(__file__).resolve().parents[2]


class NotifyTests(StoreCase):
    def test_validation(self):
        for bad in (
            {"webhook": "http://example.com/x"},
            {"webhook": "https://127.0.0.1/x"},
            {"ntfy": "https://192.168.1.5/t"},
            {"webhook": "https://localhost/x"},
            {"telegram_token": "abc", "telegram_chat": "123456"},
            {"telegram_token": "123456789:" + "A" * 35, "telegram_chat": "x y"},
        ):
            with self.assertRaises(ValueError, msg=str(bad)):
                notify.validate(bad)
        ok = notify.validate(
            {"webhook": "https://discord.com/api/webhooks/1/a", "telegram_token": "123456789:" + "A" * 35, "telegram_chat": "-100123456"}
        )
        self.assertEqual(notify.channels(ok), ["Telegram", "Webhook (Discord/Slack)"])

    def test_config_file_is_private_and_never_returned(self):
        notify.save_config(self.tmp.name, {"ntfy": "https://ntfy.sh/private-topic-xyz"})
        f = Path(self.tmp.name) / "notify.json"
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("private-topic-xyz", json.dumps(self.s.status()))

    def test_throttle_and_emit_hooks(self):
        sent = []
        real_send, real_load = notify.send, notify.load_config
        notify.send = lambda cfg, text: sent.append(text) or {"x": True}
        notify.load_config = lambda root: {"ntfy": "https://ntfy.sh/t"}
        try:
            self.s.notifier = notify.Notifier(self.s)
            self.s.emit("component", "a", "discovery")
            self.s.emit("component", "a", "discovery")  # throttled
            self.s.emit("review", "r1", "j1")
            self.s.emit("review", "r1", "j1")  # review is never throttled
            self.assertEqual(len(sent), 3)
            self.job("q", "queued", source_file="/x", title="Video X")
            job = self.s.claim()
            self.s.finish("q", job["lease"], "needs_review", reason="Off-topic")
            self.assertTrue(any("Cần bạn duyệt" in m and "Video X" in m for m in sent))
        finally:
            notify.send, notify.load_config = real_send, real_load

    def test_notifier_failure_never_breaks_queue(self):
        def boom(kind, text, key):
            raise RuntimeError("network down")

        self.s.notifier = boom
        self.s.heartbeat("publisher", False, "x")  # must not raise


if __name__ == "__main__":
    unittest.main()
