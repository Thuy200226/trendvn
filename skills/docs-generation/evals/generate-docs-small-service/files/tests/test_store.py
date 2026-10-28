import tempfile
import time
import unittest

from mailq import config, store


class StoreTests(unittest.TestCase):
    def setUp(self):
        config.DB = tempfile.mkstemp()[1]
        self.db = store.connect()

    def test_stale_sending_job_becomes_unknown_never_pending(self):
        job_id = store.enqueue(self.db, "a@b.c", "s", "b")
        store.claim(self.db)
        store.recover(self.db, now=time.time() + config.LEASE_SECONDS + 1)
        self.assertEqual(self.db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()[0], "unknown")

    def test_third_temporary_failure_is_dead(self):
        job_id = store.enqueue(self.db, "a@b.c", "s", "b")
        for _ in range(config.MAX_ATTEMPTS):
            self.db.execute("UPDATE jobs SET state='sending' WHERE id=?", (job_id,))
            store.finish(self.db, job_id, "temporary")
        self.assertEqual(self.db.execute("SELECT state FROM jobs WHERE id=?", (job_id,)).fetchone()[0], "dead")


if __name__ == "__main__":
    unittest.main()
