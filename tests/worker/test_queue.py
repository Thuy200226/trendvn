"""The processing queue: discovery, baseline, claim, finish, duplicates, housekeeping."""

import concurrent.futures
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.platforms import canonical_url
from trendvn_worker.store import Store

ROOT = Path(__file__).resolve().parents[2]


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)
        self.now = time.time()

    def tearDown(self):
        self.tmp.cleanup()

    def batch(self, ids, ts=None):
        return {
            "platform": "douyin",
            "stream": "hot_music",
            "observed_at": ts or self.now,
            "items": [
                {
                    "source_id": i,
                    "url": "https://www.douyin.com/video/" + i,
                    "country": "CN",
                    "title": "Video " + i,
                    "rank": n + 1,
                    "views": 1000,
                    "evidence_url": "https://www.douyin.com/hot",
                }
                for n, i in enumerate(ids)
            ],
        }

    def candidate(self, ids=("123",)):
        self.s.ingest(self.batch([]), now=self.now)
        return self.s.ingest(self.batch(ids, self.now + 1), now=self.now + 1)["candidate_ids"]

    def test_baseline_not_new(self):
        result = self.s.ingest(self.batch(["123"]), now=self.now)
        self.assertTrue(result["baseline"])
        self.assertEqual(result["candidate_ids"], [])

    def test_subsequent_new_only(self):
        self.s.ingest(self.batch(["123"]), now=self.now)
        r = self.s.ingest(self.batch(["123", "456"], self.now + 1), now=self.now + 1)
        self.assertEqual(r["existing"], 1)
        self.assertEqual(len(r["candidate_ids"]), 1)

    def test_stale_scan_rejected(self):
        self.s.ingest(self.batch(["123"]), now=self.now)
        with self.assertRaises(ValueError):
            self.s.ingest(self.batch(["456"]), now=self.now)

    def test_batch_transaction_no_partial(self):
        b = self.batch(["123", "456"])
        b["items"][1]["country"] = "US"
        with self.assertRaises(ValueError):
            self.s.ingest(b, now=self.now)
        self.assertEqual(self.s.status()["counts"], {})

    def test_fake_domain_blocked(self):
        for u in ["https://douyin.com.evil.test/video/123", "https://x@douyin.com/video/123", "http://douyin.com/video/123"]:
            with self.assertRaises(ValueError):
                canonical_url("douyin", u)

    def test_encoded_short_link_blocked(self):
        with self.assertRaises(ValueError):
            canonical_url("tiktok", "https://vm.tiktok.com/123")

    def test_file_hash_dedup(self):
        ids = self.candidate(("123", "456"))
        p = Path(self.tmp.name) / "inbox" / "test.mp4"
        p.write_bytes(b"fixture only")
        self.assertEqual(self.s.attach(ids[0], "test.mp4")["state"], "queued")
        self.assertEqual(self.s.attach(ids[1], "test.mp4")["state"], "duplicate")

    def test_traversal_rejected(self):
        jid = self.candidate()[0]
        with self.assertRaises(ValueError):
            self.s.attach(jid, "../../secret")

    def test_atomic_claim(self):
        jid = self.candidate()[0]
        (Path(self.tmp.name) / "inbox" / "x.mp4").write_bytes(b"fixture")
        self.s.attach(jid, "x.mp4")
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
            res = list(ex.map(lambda _: self.s.claim(), range(5)))
        self.assertEqual(sum(x is not None for x in res), 1)

    def test_stale_lease_cannot_finish(self):
        jid = self.candidate()[0]
        (Path(self.tmp.name) / "inbox" / "x.mp4").write_bytes(b"fixture")
        self.s.attach(jid, "x.mp4")
        j = self.s.claim()
        with self.assertRaises(ValueError):
            self.s.finish(jid, "wrong", "ready")
        self.s.finish(jid, j["lease"], "needs_review", reason="test")

    def test_crash_publish_does_not_requeue(self):
        jid = self.candidate()[0]
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET state='publishing',updated=? WHERE id=?", (time.time() - 3000, jid))
        self.s.housekeeping()
        self.assertEqual(self.s.status()["jobs"][0]["state"], "publish_unknown")
        self.assertIsNone(self.s.claim())


if __name__ == "__main__":
    unittest.main()
