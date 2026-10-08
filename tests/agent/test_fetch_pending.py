"""A scan asks the worker which of the videos IT saw may be downloaded, not for the best ones the worker has ever stored."""

import unittest
from unittest import mock

from tests.support import StoreCase
from trendvn_agent.collector import run


class FetchPendingTests(StoreCase):
    def ask(self, seen, status=None):
        asked = []

        def worker(path, payload=None, **kw):
            asked.append((path, payload))
            return (
                {
                    "items": [
                        {"id": "id-" + sid, "platform": "douyin", "source_id": sid, "topic_hint": None}
                        for sid in (payload or {}).get("source_ids", [])
                    ]
                }
                if path == "/api/media/pending"
                else {"state": "queued"}
            )

        with mock.patch.multiple(
            run,
            worker=worker,
            worker_get=lambda path, timeout=30: status or {"counts": {}, "backlog": 0, "thresholds": {"max_backlog": 4}},
            download=lambda ctx, item, platform: "f.mp4",
            free_bytes=lambda: 50 << 30,
        ):
            report = run.fetch_pending(None, "douyin", seen, 3, [])
        return report, [p for path, p in asked if path == "/api/media/pending"]

    def test_the_request_names_the_videos_of_this_scan_so_old_high_scores_cannot_crowd_them_out(self):
        seen = {"s%d" % n: {"source_id": "s%d" % n, "score": n} for n in range(5)}
        report, asked = self.ask(seen)
        self.assertEqual(asked[0]["source_ids"], list(seen))
        self.assertEqual(asked[0]["platform"], "douyin")
        self.assertEqual(report["downloaded"], 3)

    def test_a_very_long_scan_sends_at_most_three_hundred_ids(self):
        seen = {"s%d" % n: {"source_id": "s%d" % n, "score": n} for n in range(450)}
        _, asked = self.ask(seen)
        self.assertEqual(len(asked[0]["source_ids"]), 300)

    def test_a_full_queue_still_asks_for_nothing_and_says_why(self):
        report, asked = self.ask({"s1": {"source_id": "s1", "score": 1}}, {"counts": {}, "backlog": 4, "thresholds": {"max_backlog": 4}})
        self.assertEqual(asked, [])
        self.assertIn("Hàng chờ đã đủ", report["note"])


if __name__ == "__main__":
    unittest.main()
