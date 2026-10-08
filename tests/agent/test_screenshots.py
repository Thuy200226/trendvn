"""Failure screenshots (and the page text saved beside them) are kept in a small number: the disk is nearly full."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support import StoreCase
from trendvn_agent.publisher import screenshots


def make(folder, count, text=True):
    for number in range(count):
        picture = folder / ("delete_%d.png" % (1000 + number))
        picture.write_bytes(b"png")
        os.utime(picture, (1000 + number, 1000 + number))
        if text:
            picture.with_suffix(".txt").write_text("page text with a caption and a username")


class PruneTests(unittest.TestCase):
    def test_only_the_newest_screenshots_stay_and_their_text_goes_with_the_old_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make(folder, 25)
            screenshots.prune_shots(folder)
            names = sorted(p.name for p in folder.iterdir())
            self.assertEqual(len([n for n in names if n.endswith(".png")]), 20)
            self.assertEqual(len([n for n in names if n.endswith(".txt")]), 20)
            self.assertNotIn("delete_1000.png", names)
            self.assertNotIn("delete_1000.txt", names)
            self.assertIn("delete_1024.png", names)

    def test_a_text_file_whose_picture_is_gone_does_not_stay_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "delete_1.txt").write_text("orphan")
            make(folder, 2)
            screenshots.prune_shots(folder)
            self.assertFalse((folder / "delete_1.txt").exists())
            self.assertEqual(len(list(folder.glob("*.png"))), 2)

    def test_an_empty_or_small_folder_is_left_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            screenshots.prune_shots(Path(tmp))
            make(Path(tmp), 3)
            screenshots.prune_shots(Path(tmp))
            self.assertEqual(len(list(Path(tmp).glob("*.png"))), 3)

    def test_with_equal_times_the_name_decides_which_are_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            names = ["shot_%02d" % n for n in (7, 3, 11, 0, 9, 5, 1, 10, 4, 8, 2, 6)]  # created in no particular order
            for name in names:
                picture = folder / (name + ".png")
                picture.write_bytes(b"png")
                os.utime(picture, (500, 500))
            screenshots.prune_shots(folder, keep=4)
            self.assertEqual(sorted(p.name for p in folder.iterdir()), ["shot_%02d.png" % n for n in (8, 9, 10, 11)])

    def test_keeping_none_removes_every_screenshot_and_its_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            make(Path(tmp), 3)
            screenshots.prune_shots(Path(tmp), keep=0)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_nothing_but_screenshots_and_their_text_is_ever_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            make(folder, 30)
            for name in ("notes.json", "keep.jpg", "x.png.bak"):
                (folder / name).write_text("mine")
            (folder / "sub").mkdir()
            (folder / "sub" / "old.png").write_bytes(b"png")
            screenshots.prune_shots(folder)
            self.assertTrue({"notes.json", "keep.jpg", "x.png.bak", "sub"} <= {p.name for p in folder.iterdir()})
            self.assertTrue((folder / "sub" / "old.png").exists())


class ShotTests(StoreCase):
    def test_a_file_that_cannot_be_pruned_never_costs_the_screenshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            shots = Path(tmp) / "shots"
            shots.mkdir()
            (shots / "dangling.png").symlink_to(Path(tmp) / "missing")  # its time cannot be read
            page = mock.Mock()
            page.screenshot.side_effect = lambda path, full_page: Path(path).write_bytes(b"png")
            with mock.patch.object(screenshots, "DATA", Path(tmp)), mock.patch.object(screenshots.time, "time", return_value=9999):
                path = screenshots.shot(page, "delete")
            self.assertTrue(path and Path(path).exists())

    def test_a_failed_screenshot_is_none(self):
        page = mock.Mock()
        page.screenshot.side_effect = RuntimeError("closed")
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(screenshots, "DATA", Path(tmp)):
            self.assertIsNone(screenshots.shot(page, "delete"))

    def test_taking_a_screenshot_prunes_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            shots = Path(tmp) / "shots"
            shots.mkdir()
            make(shots, 22)
            page = mock.Mock()
            page.screenshot.side_effect = lambda path, full_page: Path(path).write_bytes(b"png")
            with mock.patch.object(screenshots, "DATA", Path(tmp)), mock.patch.object(screenshots.time, "time", return_value=9999):
                path = screenshots.shot(page, "delete")
            self.assertTrue(path and Path(path).exists())
            self.assertLessEqual(len(list(shots.glob("*.png"))), 20)


if __name__ == "__main__":
    unittest.main()
