"""Video geometry, subtitles, voice-over mixing and the quality gates of the render."""

import base64
import shutil
import subprocess
import tempfile
import unittest
import wave
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


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg/ffprobe (runs in the worker image)")
class HardSubtitleRenderTests(unittest.TestCase):
    """Real ffmpeg: the strip of picture that carries the source's own subtitles is blurred, nothing else is touched."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def source(self, name, size, audio=True):
        out = self.dir / name
        cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=%s:d=3:r=25" % size]
        if audio:
            cmd += ["-f", "lavfi", "-i", "sine=frequency=300:duration=3"]
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else []) + [str(out)]
        subprocess.run(cmd, check=True)
        return out

    def render(self, src, tag, route="vietsub", band=None, segments=((0.0, 3.0),), mask="auto"):
        folder = self.dir / tag
        folder.mkdir()
        analysis = {"kind": "dialogue", "segments": [{"start": a, "end": b, "vi": "Xin chào"} for a, b in segments]}
        if band:
            analysis["hard_subtitles"] = {"present": True, "top": band[0], "bottom": band[1]}
        return render_mod.render(src, folder, analysis, route, ffmpeg_mod.probe(src)[0], mask=mask)

    def sharpness(self, video, width, y, height, second=0.0):
        """Mean absolute horizontal gradient of a strip of the frame at `second`: high for detail, low once blurred."""
        raw = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-ss",
                str(second),
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-vf",
                "crop=%d:%d:0:%d" % (width, height, y),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "gray",
                "-",
            ],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        rows = [raw[i * width : (i + 1) * width] for i in range(height)]
        return sum(abs(r[x + 1] - r[x]) for r in rows for x in range(width - 1)) / (height * (width - 1))

    def test_the_band_is_blurred_and_the_rest_of_the_picture_is_not(self):
        src = self.source("p.mp4", "720x1280")
        plain, covered = self.render(src, "plain"), self.render(src, "covered", band=(0.70, 0.78))
        in_band = (int(0.72 * 1280), 60)
        self.assertLess(self.sharpness(covered, 720, *in_band), 0.5 * self.sharpness(plain, 720, *in_band))
        above = (200, 80)
        self.assertAlmostEqual(self.sharpness(covered, 720, *above), self.sharpness(plain, 720, *above), delta=2.0)

    def test_the_strip_is_blurred_only_while_our_own_line_is_on_screen(self):
        """A permanent grey band across the whole video covered the people and the scene (the owner's complaint)."""
        src = self.source("p.mp4", "720x1280")
        plain = self.render(src, "plain", segments=((1.0, 1.5),))
        gated = self.render(src, "gated", band=(0.70, 0.78), segments=((1.0, 1.5),))
        in_band = (int(0.72 * 1280), 60)
        self.assertLess(
            self.sharpness(gated, 720, *in_band, second=1.2), 0.5 * self.sharpness(plain, 720, *in_band, second=1.2)
        )  # line showing: blurred
        for later in (0.1, 2.8):  # before and after the line: the picture is untouched
            self.assertAlmostEqual(
                self.sharpness(gated, 720, *in_band, second=later), self.sharpness(plain, 720, *in_band, second=later), delta=2.0
            )

    def frames_md5(self, video):
        """Checksum of the decoded picture: identical when no filter touched it, different when something (a blur) did."""
        return subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(video), "-map", "0:v", "-f", "md5", "-"], check=True, stdout=subprocess.PIPE
        ).stdout

    def test_auto_blurs_only_what_our_captions_would_cover_and_the_owner_can_force_either_way(self):
        src = self.source("p.mp4", "720x1280")
        plain = self.frames_md5(self.render(src, "plain"))
        low = (0.90, 0.96)  # below our captions: nothing of ours would sit on it
        self.assertEqual(self.frames_md5(self.render(src, "auto_low", band=low)), plain)  # auto: left alone, the very same picture
        self.assertNotEqual(self.frames_md5(self.render(src, "always_low", band=low, mask="always")), plain)  # forced: blurred
        self.assertNotEqual(self.frames_md5(self.render(src, "auto_mid", band=(0.70, 0.78))), plain)  # where our captions go: blurred
        self.assertEqual(self.frames_md5(self.render(src, "off_mid", band=(0.70, 0.78), mask="off")), plain)  # never

    def test_music_that_stays_as_it_is_keeps_the_lyrics_burned_into_it(self):
        src = self.source("p.mp4", "720x1280")
        kept = self.render(src, "kept", route="original", band=(0.70, 0.78))
        plain = self.render(src, "plain", route="original")
        in_band = (int(0.72 * 1280), 60)
        self.assertAlmostEqual(self.sharpness(kept, 720, *in_band), self.sharpness(plain, 720, *in_band), delta=1.0)

    def test_odd_bands_and_wide_pictures_still_render(self):
        wide = self.source("w.mp4", "1920x1080")
        tall = self.source("p.mp4", "720x1280")
        for tag, src, band in (
            ("edge", tall, (0.97, 1.0)),
            ("thin", tall, (0.50, 0.505)),
            ("top", tall, (0.0, 0.03)),
            ("wide", wide, (0.82, 0.92)),
        ):
            info, problems = render_mod.qc(self.render(src, tag, band=band), True)
            self.assertEqual(problems, [], tag)

    def test_a_band_at_the_very_edge_of_a_tiny_picture_still_renders(self):
        for tag, size in (("tiny", "64x128"), ("small", "160x320")):
            info, problems = render_mod.qc(self.render(self.source(tag + ".mp4", size), tag, band=(0.9999, 1.0)), True)
            self.assertEqual(problems, [], tag)

    def test_digital_silence_renders_instead_of_failing_in_loudnorm(self):
        """loudnorm turns an all-zero audio track into NaN and the AAC encoder refuses it; common for clips with an empty track."""
        out = self.dir / "zero.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:d=2:r=25", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
             "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
            check=True,
        )  # fmt: skip
        for kind in ("silent", "music"):  # Gemini says silent: no levelling at all; if it says anything else: one retry without it
            folder = self.dir / ("zero_" + kind)
            folder.mkdir()
            final = render_mod.render(out, folder, {"kind": kind, "segments": []}, "original", 2.0)
            info, problems = render_mod.qc(final, True)
            self.assertEqual(problems, [], kind)
            self.assertTrue(info["audio"], kind)

    def test_faint_hiss_is_not_boosted_to_full_loudness_in_a_silent_video(self):
        hiss = self.dir / "hiss.mp4"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:d=2:r=25", "-f", "lavfi", "-i", "anoisesrc=a=1:d=2,volume=-80dB",
             "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(hiss)],
            check=True,
        )  # fmt: skip
        folder = self.dir / "hiss_out"
        folder.mkdir()
        info, _ = render_mod.qc(render_mod.render(hiss, folder, {"kind": "silent", "segments": []}, "original", 2.0), True)
        self.assertLess(info["lufs"], -35)

    def test_the_quality_report_includes_loudness(self):
        out = self.render(self.source("p.mp4", "720x1280"), "loud")
        info, problems = render_mod.qc(out, True)
        self.assertEqual(problems, [])
        self.assertLess(info["lufs"], 0)
        self.assertGreater(info["lufs"], -40)
        silent = self.render(self.source("s.mp4", "720x1280", audio=False), "silent")
        info, problems = render_mod.qc(silent, False)
        self.assertNotIn("lufs", info)
        self.assertEqual(problems, [])


class CopyPathTests(unittest.TestCase):
    """A portrait music video that is already what we would produce keeps its picture bit for bit; everything else is re-encoded."""

    STREAM = {"codec_name": "h264", "pix_fmt": "yuv420p", "width": 1080, "height": 1920, "avg_frame_rate": "30/1", "bit_rate": "2000000"}

    def can(self, route="original", **changes):
        stream = dict(self.STREAM, **changes)
        return render_mod.can_copy_video(stream, geometry.layout(*geometry.display_size(stream)), route)

    def test_only_an_untouched_portrait_h264_at_an_ordinary_bitrate_is_copied(self):
        self.assertTrue(self.can())
        self.assertTrue(self.can(width=720, height=1280, bit_rate="900000"))
        refused = {
            "subtitles or voice-over need the picture re-made": dict(route="vietsub"),
            "landscape goes on the blurred canvas": dict(width=1920, height=1080),
            "square goes on the canvas": dict(width=1080, height=1080),
            "hevc is not what phones expect": dict(codec_name="hevc"),
            "10-bit": dict(pix_fmt="yuv420p10le"),
            "60 fps is brought to 30": dict(avg_frame_rate="60/1"),
            "bigger than the canvas is scaled down": dict(width=2160, height=3840),
            "odd size is made even": dict(width=721, height=1281),
            "rotation flag is applied by re-encoding": dict(tags={"rotate": "90"}, width=1920, height=1080),
            "a 180 degree tag is baked in too": dict(tags={"rotate": "180"}),
            "a display matrix of any angle is baked in": dict(side_data_list=[{"side_data_type": "Display Matrix", "rotation": 180}]),
            "a display matrix without an angle": dict(side_data_list=[{"side_data_type": "Display Matrix"}]),
            "an unreadable rotation tag": dict(tags={"rotate": "sideways"}),
            "unknown bitrate": dict(bit_rate=None),
            "too high a bitrate is brought down to the cap": dict(bit_rate="9000000"),
        }
        for why, changes in refused.items():
            self.assertFalse(self.can(**changes), why)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg/ffprobe (runs in the worker image)")
    def test_a_copied_picture_is_identical_and_the_sound_is_levelled(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "p.mp4"
            subprocess.run(
                ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=720x1280:d=3:r=25", "-f", "lavfi", "-i", "sine=frequency=300:duration=3",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-b:v", "1M", "-c:a", "aac", str(src)],
                check=True,
            )  # fmt: skip

            def picture_hash(path):
                return subprocess.run(
                    ["ffmpeg", "-v", "error", "-i", str(path), "-map", "0:v:0", "-f", "md5", "-"], check=True, stdout=subprocess.PIPE
                ).stdout

            folder = d / "o"
            folder.mkdir()
            out = render_mod.render(src, folder, {"kind": "music", "segments": []}, "original", ffmpeg_mod.probe(src)[0])
            self.assertEqual(picture_hash(out), picture_hash(src))  # not one pixel changed
            info, problems = render_mod.qc(out, True)
            self.assertEqual(problems, [])
            self.assertAlmostEqual(info["lufs"], -14, delta=2.5)  # the sound was still levelled
            vsrc = next(s for s in ffmpeg_mod.probe(src)[1]["streams"] if s["codec_type"] == "video")
            vout = next(s for s in ffmpeg_mod.probe(out)[1]["streams"] if s["codec_type"] == "video")
            self.assertEqual((vsrc["codec_name"], vsrc["width"], vsrc["height"]), (vout["codec_name"], vout["width"], vout["height"]))
            self.assertAlmostEqual(float(ffmpeg_mod.probe(out)[1]["format"]["duration"]), 3.0, delta=0.3)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg/ffprobe (runs in the worker image)")
    def test_a_video_without_sound_and_a_silent_track_also_copy(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, audio in (("none", None), ("zero", "anullsrc=r=44100:cl=stereo")):
                src = d / (name + ".mp4")
                cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=360x640:d=2:r=25"]
                cmd += ["-f", "lavfi", "-i", audio, "-c:a", "aac"] if audio else []
                subprocess.run(cmd + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", "2", str(src)], check=True)
                folder = d / name
                folder.mkdir()
                out = render_mod.render(src, folder, {"kind": "silent", "segments": []}, "original", 2.0)
                info, problems = render_mod.qc(out, audio is not None)
                self.assertEqual((problems, info["audio"]), ([], audio is not None), name)


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
    def test_a_compressed_reply_is_converted_to_wav_even_under_a_part_name(self):
        """The voice is written under "<name>.wav.part" and renamed when finished: ffmpeg cannot choose a container from ".part"."""
        raw = subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=f=440:d=1", "-c:a", "aac", "-f", "adts", "-"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout
        out = Path(self.tmp.name) / "voice-abc.wav.part"
        speech._write_wav("audio/aac", base64.b64encode(raw).decode(), out)
        with wave.open(str(out), "rb") as w:
            self.assertGreater(w.getnframes(), 20000)  # about a second at 24 kHz

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

        def voice_of(seconds):
            def fake_tts(store, cfg, text, out, voice=None, style=None, **limits):
                # the voice is written under a ".part" name first, so the container must be named explicitly
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=600:duration=%s" % seconds, "-f", "wav", str(out)],
                    check=True,
                )
                return seconds

            return fake_tts

        def fresh_voice(seconds):
            # a voice is remembered in the job's folder by text, voice and style: each scenario starts without the previous one's
            for kept in folder.glob("voice-*.wav"):
                kept.unlink()
            return voice_of(seconds)

        real = speech.tts
        speech.tts = fresh_voice(4.4)
        try:
            voice = speech.make_voice(self.s, self.s.settings(), analysis, folder)
            self.assertAlmostEqual(voice["tempo"], 1.1, places=2)
            self.assertEqual(voice["delay"], 1.0)
            out = render_mod.render(src, folder, analysis, "voiceover", 8.0, voice)
            dur, meta = ffmpeg_mod.probe(out)
            self.assertAlmostEqual(dur, 8.0, delta=0.6)
            self.assertTrue(any(s["codec_type"] == "audio" for s in meta["streams"]))
            speech.tts = fresh_voice(20.0)  # voice far longer than the speech window: refuse, subtitles remain
            with self.assertRaises(ai_errors.VoiceoverUnfit):
                speech.make_voice(self.s, self.s.settings(), analysis, folder)
            long_text = dict(analysis, narration_vi="x" * 150, segments=[{"start": 1.0, "end": 14.0, "vi": "Xin chào"}])
            speech.tts = fresh_voice(4.0)  # 37 characters a second: a voice that skipped words to hurry
            with self.assertRaisesRegex(ai_errors.VoiceoverUnfit, "bỏ sót"):
                speech.make_voice(self.s, self.s.settings(), long_text, folder)
            speech.tts = fresh_voice(15.0)  # 10 characters a second is the natural pace and passes
            self.assertEqual(speech.make_voice(self.s, self.s.settings(), long_text, folder)["delay"], 1.0)
        finally:
            speech.tts = real


if __name__ == "__main__":
    unittest.main()
