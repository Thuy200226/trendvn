"""One odd item, one failing platform or a pile of screenshots must not cost the rest of a scan."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support import StoreCase  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_agent.collector import normalize, run
from trendvn_agent.collector.sources import SOURCES, douyin, kuaishou, tiktok
from trendvn_agent.publisher import screenshots


def douyin_item(vid, **changes):
    item = {
        "aweme_id": vid,
        "aweme_type": 0,
        "duration": 30000,
        "desc": "t",
        "create_time": 1_790_000_000,
        "statistics": {"digg_count": 1000},
        "video": {"play_addr": {"url_list": ["http://v.zjcdn.com/x.mp4"]}},
    }
    item.update(changes)
    return item


class ParseEachTests(unittest.TestCase):
    def test_one_odd_douyin_item_drops_only_itself(self):
        payload = {
            "aweme_list": [douyin_item("1"), douyin_item("2", video="not a dict"), douyin_item("3", duration="soon"), douyin_item("4")]
        }
        with mock.patch.object(normalize, "log") as log:
            items = douyin.parse_douyin(payload)
        self.assertEqual([i["source_id"] for i in items], ["1", "4"])
        self.assertTrue(log.called)  # a changed format must not look like "no videos"

    def test_a_douyin_id_the_worker_would_reject_is_dropped_here_not_the_whole_batch(self):
        payload = {"aweme_list": [douyin_item("1"), douyin_item("bad id!"), douyin_item("2")]}
        self.assertEqual([i["source_id"] for i in douyin.parse_douyin(payload)], ["1", "2"])

    def test_one_odd_kuaishou_item_drops_only_itself(self):
        good = {"photo": {"id": "abc123", "photoUrl": "https://x.kwaicdn.com/v.mp4", "duration": 30000, "realLikeCount": 5}}
        odd = {"photo": {"id": "def456", "photoUrl": "https://x.kwaicdn.com/w.mp4", "duration": "long"}}
        payload = {"data": {"brilliantTypeData": {"feeds": [odd, good]}}}
        with mock.patch.object(normalize, "log"):
            self.assertEqual([i["source_id"] for i in kuaishou.parse_kuaishou(payload)], ["abc123"])

    def test_one_odd_tiktok_item_drops_only_itself(self):
        def item(vid, **video):
            return {
                "id": vid,
                "author": {"uniqueId": "u"},
                "video": dict({"downloadAddr": "https://x/v.mp4", "duration": 20}, **video),
                "stats": {},
            }

        odd = item("2345678")
        odd["stats"] = "not a dict"
        payload = {"itemList": [item("1234567"), odd, item("3456789")]}
        with mock.patch.object(normalize, "log") as log:
            items = tiktok.parse_tiktok(payload)
        self.assertEqual([i["source_id"] for i in items], ["1234567", "3456789"])
        self.assertTrue(log.called)

    def test_a_huge_number_is_an_item_problem_not_a_scan_problem(self):
        payload = {"aweme_list": [douyin_item("1", duration=10**400), douyin_item("2")]}
        with mock.patch.object(normalize, "log"):
            self.assertEqual([i["source_id"] for i in douyin.parse_douyin(payload)], ["2"])


class ScoringTests(unittest.TestCase):
    def test_an_item_whose_numbers_cannot_be_compared_is_dropped_on_its_own(self):
        items = [
            {"source_id": "a", "duration": "long", "views": 10**6, "created": None},
            {"source_id": "b", "duration": 30, "views": 10**6, "created": None},
        ]
        with mock.patch.object(run, "log"):
            kept = [i for i in items if run._qualified_and_scored("kuaishou", i, {"min_views": {}, "max_age_days": 7}, {})]
        self.assertEqual([i["source_id"] for i in kept], ["b"])
        self.assertIn("score", kept[0])


class CollectIsolationTests(unittest.TestCase):
    def collect(self, scan):
        class Window:
            def __enter__(self):
                return None

            def __exit__(self, *exc):
                return False

        fake = {p: {"country": "CN", "locale": "zh-CN", "scan": None, "geo_locked": False} for p in ("douyin", "kuaishou")}
        status = {"counts": {}, "backlog": 0, "thresholds": {"max_backlog": 4, "max_candidates_per_scan": 6}}
        asked = []

        def exit_country(ctx):
            asked.append(1)
            return "CN"

        with (
            mock.patch.dict(SOURCES, fake, clear=True),
            mock.patch.multiple(
                run,
                chrome=lambda *a, **k: Window(),
                exit_country=exit_country,
                scan_platform=scan,
                worker=lambda path, payload=None, **k: {},
                worker_get=lambda path, timeout=30: status,
                log=lambda *a: None,
            ),
        ):
            return run.collect(["douyin", "kuaishou"], download_media=False), asked

    def test_a_platform_that_raises_does_not_end_the_session_for_the_next_one(self):
        scanned = []

        def scan(ctx, platform, thresholds, ingest, topics=()):
            scanned.append(platform)
            if platform == "douyin":
                raise RuntimeError("the page changed")
            return {"status": "ok", "summary": {"s": {"seen": 3}}}, {}

        report, _ = self.collect(scan)
        self.assertEqual(scanned, ["douyin", "kuaishou"])
        self.assertEqual((report["douyin"]["status"], report["kuaishou"]["status"]), ("error", "ok"))
        self.assertIn("the page changed", report["douyin"]["reason"])

    def test_the_exit_country_is_not_looked_up_for_sources_that_do_not_depend_on_it(self):
        _, asked = self.collect(lambda *a, **k: ({"status": "ok", "summary": {}}, {}))
        self.assertEqual(asked, [])


class ScreenshotFolderTests(unittest.TestCase):
    def test_only_the_latest_pictures_are_kept(self):
        with tempfile.TemporaryDirectory() as folder:
            shots = Path(folder) / "shots"
            shots.mkdir()
            for n in range(25):
                old = shots / ("old_%d.png" % n)
                old.write_bytes(b"x")
                os.utime(old, (1000 + n, 1000 + n))

            class Page:
                def screenshot(self, path, full_page):
                    Path(path).write_bytes(b"new")

            with mock.patch.object(screenshots, "DATA", Path(folder)):
                path = screenshots.shot(Page(), "error")
            names = sorted(p.name for p in shots.glob("*.png"))
            self.assertEqual(len(names), 20)  # the latest twenty, like the screenshots of the dry run
            self.assertIn(Path(path).name, names)  # the new one is never the one removed
            self.assertNotIn("old_0.png", names)

    def test_a_folder_that_cannot_be_pruned_does_not_turn_a_picture_into_a_failure(self):
        class Page:
            def screenshot(self, path, full_page):
                Path(path).write_bytes(b"new")

        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "shots").mkdir()
            with mock.patch.object(screenshots, "DATA", Path(folder)), mock.patch.object(Path, "glob", side_effect=OSError("denied")):
                self.assertTrue(screenshots.shot(Page(), "error"))


if __name__ == "__main__":
    unittest.main()
