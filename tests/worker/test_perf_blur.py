"""The blur over the source's own burned-in subtitles runs on a quarter-size copy of the strip (render time, Phase H)."""

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.media import geometry, render as render_mod

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
BANDS = [(0.70, 0.76), (0.90, 0.97), (0.05, 0.10), (0.0, 0.03), (0.97, 1.0), (0.50, 0.52), (0.30, 0.31)]
SIZES = [(360, 640), (720, 1280), (1080, 1920), (1920, 1080), (1280, 720), (1080, 1350)]


def graph(width, height, band, spans=((0.5, 2.5),)):
    """(filter graph text, final label) of the picture chain for a video of this size whose source has subtitles in `band`."""
    geo = geometry.layout(width, height)
    chain, last = render_mod._picture_chain(
        geo, 25, {"hard_subtitles": {"present": True, "top": band[0], "bottom": band[1]}, "segments": [{"start": 1.0, "end": 2.0, "vi": "x"}]},
        "vietsub", Path(tempfile.mkdtemp()), 4.0, "always",
    )  # fmt: skip
    return chain, last, geo


class BlurGraphShapeTests(unittest.TestCase):
    def blur_step(self, band):
        chain, _, geo = graph(1080, 1920, band)
        (step,) = [s for s in chain if "boxblur" in s and "hsb" in s]
        return step, geo

    def test_a_tall_strip_is_blurred_at_a_quarter_of_its_size_and_enlarged_back(self):
        step, geo = self.blur_step((0.70, 0.76))
        (small_w, small_h), (back_w, back_h) = [tuple(map(int, m)) for m in re.findall(r"scale=(\d+):(\d+):flags=bilinear", step)]
        self.assertEqual((back_w, small_w), (geo["w"], geo["w"] // 8 * 2))
        self.assertEqual(small_h % 2, 0)
        self.assertTrue(small_w * 4 <= back_w and small_h * 4 <= back_h and small_w * 4 > back_w - 8)  # a quarter in each direction
        self.assertLess(step.index("scale=%d:%d" % (small_w, small_h)), step.index("boxblur"))  # shrink, blur ...
        self.assertLess(step.index("boxblur"), step.rindex("scale="))  # ... then enlarge
        self.assertIn("enable='between(t,0.50,2.60)'", step)  # the time gate is unchanged

    def strip_of(self, width, height, band):
        geo = geometry.layout(width, height)
        found = render_mod.covered_hard_subtitles(
            {"hard_subtitles": {"present": True, "top": band[0], "bottom": band[1]}}, "vietsub", geo, "always"
        )
        return render_mod._band_pixels(geo, found)[1]

    def test_a_strip_too_thin_to_scale_down_is_blurred_as_it_is_and_one_at_the_limit_is_not(self):
        thin = [(w, h, b) for w, h in SIZES for b in BANDS if self.strip_of(w, h, b) < render_mod.BLUR_SMALL_MIN_HEIGHT]
        tall = [(w, h, b) for w, h in SIZES for b in BANDS if self.strip_of(w, h, b) >= render_mod.BLUR_SMALL_MIN_HEIGHT]
        self.assertTrue(thin and tall, "the sizes and bands of this test must cover both paths")
        for w, h, band in thin:
            chain, _, _ = graph(w, h, band)
            (step,) = [s for s in chain if "hsb" in s and "boxblur" in s]
            self.assertNotIn("scale=", step.split("[hsb]")[1].split("[hsc]")[0], (w, h, band))  # blurred at full size
        for w, h, band in tall:
            chain, _, _ = graph(w, h, band)
            (step,) = [s for s in chain if "hsb" in s and "boxblur" in s]
            self.assertEqual(step.count("scale="), 2, (w, h, band))  # shrunk and enlarged
        self.assertEqual(render_mod.BLUR_SMALL_MIN_HEIGHT, 48)

    def test_the_radius_at_a_quarter_size_is_a_quarter_of_the_radius_at_full_size(self):
        """A blur of radius r on the full strip looks like one of r/4 on a strip a quarter the size: not dividing it blurs four times too much."""
        for w, h in SIZES:
            for band in BANDS:
                strip = self.strip_of(w, h, band)
                if strip < render_mod.BLUR_SMALL_MIN_HEIGHT:
                    continue
                chain, _, _ = graph(w, h, band)
                (step,) = [s for s in chain if "hsb" in s and "boxblur" in s]
                full = max(1, min(render_mod.BLUR_MAX_RADIUS, strip // 4 - 1))
                small_h = strip // 8 * 2
                self.assertEqual(int(re.search(r"boxblur=(\d+):3", step).group(1)), max(1, min(full // 4, small_h // 4 - 1)), (w, h, band))

    def test_the_blur_radius_never_exceeds_what_the_scaled_strip_allows(self):
        for width, height in SIZES:
            for band in BANDS:
                chain, _, _ = graph(width, height, band)
                for step in chain:
                    if "hsb" not in step or "boxblur" not in step:
                        continue
                    radius = int(re.search(r"boxblur=(\d+):3", step).group(1))
                    rows = [int(m) for m in re.findall(r"scale=\d+:(\d+):flags=bilinear", step)]
                    strip = int(re.search(r"crop=\d+:(\d+):0:\d+", step).group(1))
                    seen = rows[0] if rows else strip
                    self.assertGreaterEqual(radius, 1, (width, height, band))
                    self.assertLessEqual(radius, max(1, seen // 4 - 1), (width, height, band))  # the half-height chroma planes cap it


@unittest.skipUnless(HAS_FFMPEG, "needs ffmpeg/ffprobe (runs in the worker image)")
class BlurRunsInFfmpegTests(unittest.TestCase):
    def run_graph(self, width, height, chain, last, out, frames=25):
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=%dx%d:d=4:r=25" % (width, height), "-filter_complex", ";".join(chain),
             "-map", "[%s]" % last, "-frames:v", str(frames), "-c:v", "ffv1", "-f", "nut", str(out)],
            check=True, capture_output=True,
        )  # fmt: skip

    def test_every_strip_size_is_accepted_by_ffmpeg(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        for width, height in SIZES:
            for band in BANDS:
                chain, last, geo = graph(width, height, band)
                try:
                    self.run_graph(geo["w"], geo["h"] if not geo["reframe"] else geo["h"], chain, last, tmp / "o.nut", frames=3)
                except subprocess.CalledProcessError as error:
                    self.fail("%sx%s band %s: %s" % (width, height, band, error.stderr.decode()[-300:]))

    def test_the_quarter_size_blur_looks_like_the_full_size_one(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        width, height, band = 1080, 1920, (0.70, 0.76)
        chain, last, geo = graph(width, height, band)
        quarter = [s for s in chain]
        step = next(s for s in quarter if "hsb" in s)
        y, strip = render_mod._band_pixels(
            geo,
            render_mod.covered_hard_subtitles(
                {"hard_subtitles": {"present": True, "top": band[0], "bottom": band[1]}}, "vietsub", geo, "always"
            ),
        )
        radius = max(1, min(render_mod.BLUR_MAX_RADIUS, strip // 4 - 1))
        full = [
            s if "hsb" not in s else (
                "[v0]split=2[hsa][hsb];[hsb]crop=%d:%d:0:%d,boxblur=%d:3,eq=brightness=-0.12[hsc];[hsa][hsc]overlay=0:%d:enable='between(t,0.50,2.60)'[v1]"
                % (geo["w"], strip, y, radius, y)
            )
            for s in quarter
        ]  # fmt: skip
        self.assertNotEqual(step, full[quarter.index(step)])
        self.run_graph(geo["w"], geo["h"], quarter, last, tmp / "q.nut", frames=40)
        self.run_graph(geo["w"], geo["h"], full, last, tmp / "f.nut", frames=40)
        crop = "crop=%d:%d:0:%d" % (geo["w"], strip, y)
        report = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(tmp / "q.nut"), "-i", str(tmp / "f.nut"), "-lavfi",
             "[0:v]%s[a];[1:v]%s[b];[a][b]ssim" % (crop, crop), "-f", "null", "-"],
            capture_output=True, text=True, check=True,
        ).stderr  # fmt: skip
        ssim = float(re.search(r"All:([\d.]+)", report).group(1))
        self.assertGreater(ssim, 0.95, report[-300:])  # (0.99 on the real video; this test picture is far busier than any footage)


if __name__ == "__main__":
    unittest.main()
