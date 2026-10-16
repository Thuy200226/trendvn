"""Tests for Auto-Pilot Affiliate Pipeline and Deep Clean Deletion (purge_job)."""

import json
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from tests.support import StoreCase  # noqa: F401
from trendvn_worker.store import Store
from trendvn_worker.web.forms import purge_video


class TestAutoAffiliateAndPurge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = Store(self.tmp)
        self.store.update_settings({"target": "bubitueanxinhiu", "publisher_enabled": True, "require_approval": False})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_purge_job_deletes_all_files_and_retains_invariant(self):
        jid = "a" * 32
        inbox_file = self.store.root / "inbox" / "video_source.mp4"
        inbox_file.write_bytes(b"dummy source video content" * 100)
        job_dir = self.store.root / "jobs" / jid
        job_dir.mkdir(parents=True)
        (job_dir / "final.mp4").write_bytes(b"final render video" * 50)
        (job_dir / "poster.jpg").write_bytes(b"poster jpg" * 10)
        (job_dir / "manifest.json").write_text("{}")

        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id, platform, source_id, url, country, title, first_seen, last_seen, state, source_file, output_file, fingerprint, updated) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    "douyin",
                    "dy_123",
                    "https://v.douyin.com/test1234/",
                    "CN",
                    "Test Douyin Product",
                    time.time(),
                    time.time(),
                    "ready",
                    str(inbox_file),
                    str(job_dir / "final.mp4"),
                    json.dumps([[1, 2, 3]]),
                    time.time(),
                ),
            )

        self.assertTrue(inbox_file.exists())
        self.assertTrue((job_dir / "final.mp4").exists())

        res = self.store.purge_job(jid)
        self.assertGreater(res["freed_bytes"], 0)
        self.assertFalse(inbox_file.exists())
        self.assertFalse(job_dir.exists())

        row = self.store.job(jid)
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "purged")
        self.assertIsNone(row["source_file"])
        self.assertIsNone(row["output_file"])
        self.assertIsNotNone(row["pruned_at"])
        self.assertEqual(row["url"], "https://v.douyin.com/test1234/")
        self.assertEqual(row["source_id"], "dy_123")

    def test_delete_post_finish_triggers_purge(self):
        jid = "b" * 32
        url = "https://www.tiktok.com/@bubitueanxinhiu/video/7695350773474921749"
        job_dir = self.store.root / "jobs" / jid
        job_dir.mkdir(parents=True)
        (job_dir / "final.mp4").write_bytes(b"final render" * 20)

        with self.store.transaction() as db:
            db.execute("INSERT OR REPLACE INTO accounts(id, username, topics, enabled) VALUES('main', 'bubitueanxinhiu', '[]', 1)")
            db.execute(
                "INSERT INTO jobs(id, platform, source_id, url, country, title, first_seen, last_seen, state, output_file, target, publish_url, account, updated) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    "douyin",
                    "dy_post",
                    url,
                    "CN",
                    "Post Title",
                    time.time(),
                    time.time(),
                    "published",
                    str(job_dir / "final.mp4"),
                    "bubitueanxinhiu",
                    url,
                    "main",
                    time.time(),
                ),
            )

        grant = self.store.delete_post_begin(jid, url, "main")["grant"]
        self.store.delete_post_claim(jid, grant)
        self.store.delete_post_finish(jid, grant, "deleted", "Đã xóa bài trên TikTok")

        self.assertFalse(job_dir.exists())
        row = self.store.job(jid)
        self.assertEqual(row["state"], "post_deleted")
        self.assertIsNone(row["output_file"])

    def test_purge_video_form_handler(self):
        jid = "c" * 32
        job_dir = self.store.root / "jobs" / jid
        job_dir.mkdir(parents=True)
        (job_dir / "final.mp4").write_bytes(b"temp" * 10)

        with self.store.transaction() as db:
            db.execute(
                "INSERT INTO jobs(id, platform, source_id, url, country, title, first_seen, last_seen, state, output_file, updated) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    "douyin",
                    "dy_c",
                    "https://v.douyin.com/test_c/",
                    "CN",
                    "C Title",
                    time.time(),
                    time.time(),
                    "ready",
                    str(job_dir / "final.mp4"),
                    time.time(),
                ),
            )

        class DummyTasks:
            def __init__(self):
                self.cancelled = []

            def cancel_for_job(self, jid):
                self.cancelled.append(jid)

        class DummyApp:
            def __init__(self, store):
                self.store = store
                self.tasks = DummyTasks()

        app = DummyApp(self.store)
        form = {"id": [jid], "confirmed": ["true"], "next": ["publish"]}
        redir = purge_video(app, form)
        self.assertEqual(redir.key, "purged")
        self.assertEqual(redir.anchor, "#publish")
        self.assertEqual(app.tasks.cancelled, [jid])
        self.assertFalse(job_dir.exists())

    def test_affiliate_strict_binding_in_videos_select(self):
        with self.store.transaction() as db:
            db.execute("INSERT OR REPLACE INTO accounts(id, username, topics, enabled) VALUES('main', 'bubitueanxinhiu', '[]', 1)")
            db.execute(
                "INSERT INTO commission_links(account, url, title, product_id, markers, created, tracked) " "VALUES(?, ?, ?, ?, ?, ?, ?)",
                (
                    "main",
                    "https://vt.tiktok.com/ZSj123/",
                    "Kem chống nắng Anessa Perfect UV",
                    "1731815189062584999",
                    "anessa",
                    time.time(),
                    1,
                ),
            )

        body = {
            "identity": {
                "name": "Kem chống nắng Anessa Perfect UV",
                "brand": "Anessa",
                "model": "Perfect UV",
                "product_id": "1731815189062584999",
            },
            "account_username": "bubitueanxinhiu",
            "results": [
                {
                    "platform": "douyin",
                    "source_id": "dy_anessa_1",
                    "url": "https://v.douyin.com/anessa1/",
                    "title": "Review Anessa Perfect UV",
                }
            ],
        }
        mid = self.store.chat_add("bot", "videos", body, state="done", account="main")

        jid = self.store.videos_select(mid, "dy_anessa_1", confirmed=True, platform="douyin")
        row = self.store.job(jid)
        self.assertIsNotNone(row["product_binding"])
        binding = json.loads(row["product_binding"])
        self.assertEqual(binding["product_id"], "1731815189062584999")
        self.assertEqual(binding["title"], "Kem chống nắng Anessa Perfect UV")


if __name__ == "__main__":
    unittest.main()
