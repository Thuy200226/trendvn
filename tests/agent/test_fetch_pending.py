"""A scan asks the worker which of the videos IT saw may be downloaded, not for the best ones the worker has ever stored."""

import unittest
from unittest import mock

from tests.support import StoreCase
from trendvn_agent.collector import run


class FetchPendingTests(StoreCase):
    def ask(self, seen, status=None, topics=(), hints=None):
        asked = []

        def worker(path, payload=None, **kw):
            asked.append((path, payload))
            return (
                {
                    "items": [
                        {"id": "id-" + sid, "platform": "douyin", "source_id": sid, "topic_hint": (hints or {}).get(sid)}
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
            download=lambda ctx, item, platform: self.downloaded.append(item["source_id"]) or "f.mp4",
            free_bytes=lambda: 50 << 30,
        ):
            self.downloaded = []
            report = run.fetch_pending(None, "douyin", seen, 3, list(topics))
        return report, [p for path, p in asked if path == "/api/media/pending"]

    def test_the_request_names_the_videos_of_this_scan_so_old_high_scores_cannot_crowd_them_out(self):
        seen = {"s%d" % n: {"source_id": "s%d" % n, "score": n} for n in range(5)}
        report, asked = self.ask(seen)
        self.assertEqual(asked[0]["source_ids"], ["s4", "s3", "s2", "s1", "s0"])  # best score first
        self.assertEqual(asked[0]["platform"], "douyin")
        self.assertEqual(report["downloaded"], 3)

    def test_a_video_the_scan_did_not_see_is_never_downloaded_even_if_the_worker_lists_it(self):
        downloaded = []
        seen = {"s1": {"source_id": "s1", "score": 1}}
        items = [{"id": "x" + sid, "platform": "douyin", "source_id": sid, "topic_hint": None} for sid in ("s1", "other")]
        with mock.patch.multiple(
            run,
            worker=lambda path, payload=None, **kw: {"items": items} if path == "/api/media/pending" else {"state": "queued"},
            worker_get=lambda path, timeout=30: {"counts": {}, "backlog": 0, "thresholds": {"max_backlog": 4}},
            download=lambda ctx, item, platform: downloaded.append(item["source_id"]) or "f.mp4",
            free_bytes=lambda: 50 << 30,
        ):
            run.fetch_pending(None, "douyin", seen, 3, [])
        self.assertEqual(downloaded, ["s1"])

    def test_the_topics_the_accounts_take_still_decide_what_is_downloaded(self):
        """The ids of the scan and the topics of the accounts are two different lists: asking by id must not replace the topics."""
        seen = {"s%d" % n: {"source_id": "s%d" % n, "score": 10 - n} for n in range(4)}
        hints = {"s0": "pets", "s1": "comedy", "s2": None, "s3": "food"}
        report, asked = self.ask(seen, topics=["comedy", "music"], hints=hints)
        self.assertEqual(sorted(self.downloaded), ["s1", "s2"])  # comedy and the unhinted one; pets and food are for nobody
        self.assertEqual(report["downloaded"], 2)

    def test_every_hinted_video_is_kept_when_an_account_takes_its_topic(self):
        seen = {"s%d" % n: {"source_id": "s%d" % n, "score": n} for n in range(3)}
        report, _ = self.ask(seen, topics=["comedy"], hints={"s0": "comedy", "s1": "comedy", "s2": "comedy"})
        self.assertEqual(report["downloaded"], 3)

    def test_when_more_than_three_hundred_were_seen_the_best_scores_are_asked_about(self):
        seen = {"s%d" % n: {"source_id": "s%d" % n, "score": n} for n in range(450)}  # the best ones were read last
        _, asked = self.ask(seen)
        self.assertEqual(len(asked[0]["source_ids"]), 300)
        self.assertIn("s449", asked[0]["source_ids"])
        self.assertNotIn("s0", asked[0]["source_ids"])

    def test_an_id_the_worker_would_refuse_never_spoils_the_request(self):
        """A source id is 1-100 letters, digits, - and _ (what the worker takes in): the rest is left out, not allowed to fail the scan."""
        seen = {sid: {"source_id": sid, "score": 1} for sid in ("ok1", "k" * 100, "k" * 101, "bad id", "a/b", "")}
        _, asked = self.ask(seen)
        self.assertEqual(sorted(asked[0]["source_ids"]), sorted(["ok1", "k" * 100]))

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
