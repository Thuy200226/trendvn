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


class ShotTests(StoreCase):
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
