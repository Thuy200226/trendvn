"""Video geometry, subtitles, voice-over mixing and the quality gates of the render."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.ai import errors as ai_errors, tts as speech
from trendvn_worker.media import ffmpeg as ffmpeg_mod, geometry, render as render_mod, subtitles as subtitle_mod

ROOT = Path(__file__).resolve().parents[2]


class SubtitleTests(unittest.TestCase):
    def test_long_sentence_is_split_not_rejected(self):
        from trendvn_worker.media.subtitles import ass_subtitles

        seg = [{"start": 1.0, "end": 9.0, "vi": "Đây là một câu rất dài " * 8}, {"start": 9.5, "end": 11.0, "vi": "Ngắn thôi"}]
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "a.ass"
            ass_subtitles(seg, out, 720, 1280)
            events = [l for l in out.read_text(encoding="utf-8").splitlines() if l.startswith("Dialogue:")]
        self.assertGreater(len(events), 2)
        stamps = [(l.split(",")[1], l.split(",")[2]) for l in events]
        parse = lambda s: sum(float(x) * m for x, m in zip(s.split(":"), (3600, 60, 1)))
        for (a, b), (c, _) in zip(stamps, stamps[1:]):
            self.assertLessEqual(parse(a), parse(b))
            self.assertLessEqual(parse(b), parse(c) + 0.011)  # no overlap between consecutive captions
        for l in events:
            self.assertLessEqual(l.count("\\N"), 1)  # at most two lines per caption


class GeometryAndQualityTests(unittest.TestCase):
    def test_layout_rules(self):
        self.assertEqual(geometry.layout(1080, 1920), {"reframe": False, "w": 1080, "h": 1920})
        self.assertEqual(geometry.layout(721, 1281), {"reframe": False, "w": 720, "h": 1280})  # odd sizes made even
        wide = geometry.layout(1920, 1080)
        self.assertTrue(wide["reframe"] and (wide["w"], wide["h"]) == (1080, 1920) and wide["fg_h"] == 608 and wide["band_top"] == 1264)
        sq = geometry.layout(1080, 1080)
        self.assertTrue(sq["reframe"] and sq["fg_h"] == 1080)
        self.assertTrue(geometry.layout(1280, 720)["reframe"])
        self.assertFalse(geometry.layout(1080, 1350)["reframe"] is False)  # 4:5 goes on the canvas too

    def test_subtitles_sit_in_the_band_when_reframed(self):
        seg = [{"start": 0.5, "end": 3.0, "vi": "Xin chào các bạn"}]
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a.ass", Path(d) / "b.ass"
            subtitle_mod.ass_subtitles(seg, a, 1080, 1920)
            subtitle_mod.ass_subtitles(seg, b, 1080, 1920, band_top=1264)
            style_a = [l for l in a.read_text().splitlines() if l.startswith("Style:")][0].split(",")
            style_b = [l for l in b.read_text().splitlines() if l.startswith("Style:")][0].split(",")
        self.assertEqual(style_a[18], "2")  # bottom-centre over the picture
        self.assertEqual(style_b[18], "8")  # top-centre inside the free band
        self.assertGreater(int(style_b[21]), 1264)  # margin pushes the text below the picture

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg/ffprobe (runs in the worker image)")
    def test_real_render_portrait_wide_and_silent(self):

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)

            def make(name, size, audio=True, rate=30):
                out = d / name
                cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=%s:d=4:r=%d" % (size, rate)]
                if audio:
                    cmd += ["-f", "lavfi", "-i", "sine=frequency=300:duration=4"]
                cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + [str(out)]
                subprocess.run(cmd, check=True)
                return out

            analysis = {"kind": "dialogue", "segments": [{"start": 0.5, "end": 3.0, "vi": "Xin chào các bạn, đây là bản thử"}]}
            for name, size, audio, rate, expect_wh in (
                ("p.mp4", "720x1280", True, 30, (720, 1280)),
                ("w.mp4", "1920x1080", True, 60, (1080, 1920)),
                ("s.mp4", "1080x1080", False, 25, (1080, 1920)),
            ):
                src = make(name, size, audio, rate)
                folder = d / name.split(".")[0]
                folder.mkdir()
                dur, meta = ffmpeg_mod.probe(src)
                out = render_mod.render(src, folder, analysis, "vietsub", dur)
                info, problems = render_mod.qc(out, audio)
                self.assertEqual((info["w"], info["h"]), expect_wh, name)
                self.assertEqual(problems, [], name)
                self.assertEqual(info["audio"], audio, name)
                self.assertLessEqual(info["fps"], 30, name)
                self.assertAlmostEqual(info["duration"], 4.0, delta=0.5, msg=name)
                render_mod.make_poster(out, folder / "poster.jpg", dur)
                self.assertGreater((folder / "poster.jpg").stat().st_size, 500, name)
            # metadata of the source is not carried over
            tagged = d / "tag.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-i", str(d / "p.mp4"), "-metadata", "comment=SOURCE-SECRET", "-c", "copy", str(tagged)],
                check=True,
            )
            folder = d / "tag"
            folder.mkdir()
            out = render_mod.render(tagged, folder, analysis, "vietsub", ffmpeg_mod.probe(tagged)[0])
            self.assertNotIn(b"SOURCE-SECRET", out.read_bytes())


class RotationZonesAndSizeTests(unittest.TestCase):
    def test_displayed_size_follows_rotation(self):
        self.assertEqual(geometry.display_size({"width": 1280, "height": 720}), (1280, 720))
        self.assertEqual(geometry.display_size({"width": 1280, "height": 720, "tags": {"rotate": "90"}}), (720, 1280))
        self.assertEqual(geometry.display_size({"width": 720, "height": 1280, "side_data_list": [{"rotation": -90}]}), (1280, 720))
        self.assertEqual(geometry.display_size({"width": 720, "height": 1280, "side_data_list": [{"rotation": 180}]}), (720, 1280))
        self.assertEqual(geometry.display_size({"width": 720, "height": 1280, "tags": {"rotate": "x"}}), (720, 1280))

    def test_oversized_portrait_is_scaled_to_fit_and_small_is_left_alone(self):
        big = geometry.layout(2160, 3840)
        self.assertEqual((big["w"], big["h"]), (1080, 1920))
        tall = geometry.layout(1080, 2400)
        self.assertLessEqual(tall["h"], 1920)
        self.assertEqual(tall["w"] % 2 + tall["h"] % 2, 0)
        self.assertEqual((geometry.layout(320, 568)["w"], geometry.layout(320, 568)["h"]), (320, 568))

    def test_captions_stay_clear_of_tiktoks_lower_overlay(self):
        portrait = geometry.caption_zone(geometry.layout(1080, 1920))
        self.assertEqual(portrait["align"], 2)
        self.assertLessEqual(1920 - portrait["margin"], 1440 + 1)  # text bottom edge above the overlay
        wide = geometry.caption_zone(geometry.layout(1920, 1080))
        self.assertEqual((wide["align"], wide["box"]), (8, False))
        self.assertLess(wide["margin"], 1400)
        square = geometry.caption_zone(geometry.layout(1080, 1080))  # its bottom band starts at 1500: too low, so the top band is used
        self.assertEqual(square["align"], 8)
        self.assertLess(square["margin"], 400)
        self.assertGreaterEqual(square["margin"], 140)  # below TikTok's top tabs
        four_five = geometry.caption_zone(geometry.layout(1080, 1350))
        self.assertLess(four_five["margin"] + 130, (1920 - 1350) // 2 + 1)  # two caption lines fit inside the top band
        three_four = geometry.caption_zone(geometry.layout(1080, 1440))
        self.assertTrue(three_four["box"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed (runs inside the worker image)")
class VoiceoverTests(StoreCase):
    def test_mix_and_subtitle_render(self):

        folder = Path(self.tmp.name) / "jobs" / "j"
        folder.mkdir(parents=True)
        src = folder / "src.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=360x640:d=8:r=15",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=300:duration=8",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(src),
            ],
            check=True,
        )
        analysis = {
            "kind": "narration",
            "confidence": 0.95,
            "topic": "entertainment",
            "sensitive": False,
            "narration_vi": "Xin chào các bạn",
            "segments": [{"start": 1.0, "end": 5.0, "vi": "Xin chào các bạn"}],
        }

        def fake_tts(store, cfg, text, out):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=600:duration=4.4", str(out)], check=True)
            return 4.4

        real = speech.tts
        speech.tts = fake_tts
        try:
            voice = speech.make_voice(self.s, self.s.settings(), analysis, folder)
            self.assertAlmostEqual(voice["tempo"], 1.1, places=2)
            self.assertEqual(voice["delay"], 1.0)
            out = render_mod.render(src, folder, analysis, "voiceover", 8.0, voice)
            dur, meta = ffmpeg_mod.probe(out)
            self.assertAlmostEqual(dur, 8.0, delta=0.6)
            self.assertTrue(any(s["codec_type"] == "audio" for s in meta["streams"]))
            speech.tts = lambda *a: 20.0  # voice far longer than the speech window: refuse, subtitles remain
            with self.assertRaises(ai_errors.VoiceoverUnfit):
                speech.make_voice(self.s, self.s.settings(), analysis, folder)
        finally:
            speech.tts = real


if __name__ == "__main__":
    unittest.main()
