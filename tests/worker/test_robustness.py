"""Odd inputs and failures must never wedge the queue."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.captions import build_caption
from trendvn_worker.store import schema

ROOT = Path(__file__).resolve().parents[2]


class RobustnessTests(StoreCase):
    def test_malformed_model_output_cannot_break_captions_or_the_list(self):
        for bad in (5, True, "haihuoc", {"a": 1}, [None, 7, ["x"], "ok1"]):
            c = build_caption({"kind": "dialogue", "caption_vi": "Một câu mô tả đầy đủ", "hashtags": bad}, "t")
            self.assertIn("#xuhuong", c)
        self.job("a", "ready", output_file="/d/a.mp4", output_hash="h", analysis="{not json")
        self.assertEqual(len(self.s.ready_list()), 1)

    def test_caption_line_breaks_and_unicode_are_normalised(self):
        self.ready("a")
        self.s.set_caption("a", "Dòng một  \r\nDòng hai\r\n#a1 #b2 #c3")
        self.assertEqual(self.s.ready_list()[0]["caption"], "Dòng một\nDòng hai\n#a1 #b2 #c3")
        again = self.s.ready_list()[0]["caption"]
        self.s.set_caption("a", again.replace("\n", "\r\n"))
        self.assertEqual(
            len([e for e in self.s.recent_events(50) if e["event"] == "caption_edited"]), 1
        )  # re-saving the same text is not an edit
        self.s.set_caption("a", "Vie\u0302\u0323t Nam #vie\u0302\u0323t #a2 #b3")
        self.assertIn("Việt Nam", self.s.ready_list()[0]["caption"])  # decomposed accents become normal letters

    def test_partial_settings_update_never_erases_other_thresholds(self):
        self.s.update_settings({"min_views": {"tiktok": 7}})
        self.s.update_settings({"min_likes": {"douyin": 9}})
        cfg = self.s.settings()
        self.assertEqual((cfg["min_views"]["tiktok"], cfg["min_views"]["kuaishou"], cfg["min_likes"]["douyin"]), (7, 1000000, 9))


if __name__ == "__main__":
    unittest.main()


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "m.sqlite3"

    def open(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        return db

    def test_a_migration_that_crashes_leaves_no_trace_and_no_version(self):
        def second(db):
            db.execute("CREATE TABLE half_done (x)")
            raise RuntimeError("crash in the middle of a migration")

        db = self.open()
        schema.migrate(db)
        with mock.patch.object(schema, "MIGRATIONS", schema.MIGRATIONS + [second]):
            with self.assertRaises(RuntimeError):
                schema.migrate(db)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], len(schema.MIGRATIONS))
        self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='half_done'").fetchone())

    def test_each_migration_runs_once_and_a_database_without_version_is_adopted(self):
        db = self.open()
        db.executescript(schema.BASELINE_TABLES)  # a 1.0 database: the tables, none of the later columns, no version number
        db.execute("INSERT INTO jobs(id,title) VALUES ('a','kept')")
        db.commit()
        schema.migrate(db)
        self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], len(schema.MIGRATIONS))
        self.assertEqual(db.execute("SELECT title FROM jobs").fetchone()[0], "kept")
        self.assertIn("output_info", {row[1] for row in db.execute("PRAGMA table_info(jobs)")})
        ran = []
        with mock.patch.object(schema, "MIGRATIONS", [lambda d: ran.append(1)] * len(schema.MIGRATIONS)):
            schema.migrate(db)
        self.assertEqual(ran, [])
