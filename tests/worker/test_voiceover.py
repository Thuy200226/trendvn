"""Voice-over quality: which voice, which delivery and pace, how it fits its window, how it is mixed, and when the source's own subtitles
are blurred. Cases come from the measurements in docs/QUALITY.md."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.support import StoreCase
from trendvn_worker.ai import analyzer, tts as speech
from trendvn_worker.ai.errors import VoiceoverUnfit
from trendvn_worker.domain import voices
from trendvn_worker.domain.analysis import clean_speaker, validate_analysis
from trendvn_worker.domain.route import choose_route
from trendvn_worker.media import ffmpeg as ffmpeg_mod, render as render_mod
from trendvn_worker.media.subtitles import caption_extent

CFG = {"voice": "Kore", "voice_mode": "auto"}


class VoiceChoiceTests(unittest.TestCase):
    def test_the_voice_follows_the_speaker_and_the_tone(self):
        self.assertEqual(voices.GENDER[voices.pick_voice(CFG, {"gender": "female", "tone": "energetic"})], "female")
        self.assertEqual(voices.GENDER[voices.pick_voice(CFG, {"gender": "male", "tone": "serious"})], "male")
        self.assertNotEqual(
            voices.pick_voice(CFG, {"gender": "female", "tone": "energetic"}),
            voices.pick_voice(CFG, {"gender": "female", "tone": "serious"}),
        )  # (men have one confirmed voice so far: the tone then shows in the delivery words, not in the voice)
        self.assertNotEqual(voices.style_for({"tone": "energetic"}, voices.NORMAL), voices.style_for({"tone": "serious"}, voices.NORMAL))
        self.assertEqual(voices.GENDER[voices.pick_voice(CFG, {"gender": "child", "tone": "playful"})], "female")  # a young bright voice

    def test_unknown_speakers_odd_input_and_the_fixed_mode_use_the_owners_voice(self):
        for speaker in (None, {}, "x", {"gender": "unknown"}, {"gender": "mixed", "tone": "calm"}, {"gender": "robot"}):
            self.assertEqual(voices.pick_voice(CFG, speaker), "Kore", speaker)
        self.assertEqual(voices.pick_voice(dict(CFG, voice_mode="fixed", voice="Puck"), {"gender": "female", "tone": "calm"}), "Puck")
        self.assertEqual(
            voices.pick_voice({"voice": "Orus"}, {"gender": "female"}), voices.pick_voice({"voice": "Orus"}, {"gender": "female"})
        )

    def test_every_pool_voice_is_a_known_voice_of_the_right_gender_and_every_tone_has_one(self):
        for gender, pool in voices.POOLS.items():
            self.assertEqual(set(pool), set(voices.TONES))
            for name in pool.values():
                self.assertEqual(voices.GENDER[name], gender, name)

    def test_pace_is_chosen_from_the_characters_the_window_needs_per_second(self):
        self.assertEqual(voices.pace_for(8), voices.SLOW)
        self.assertEqual(voices.pace_for(14), voices.NORMAL)
        self.assertEqual(voices.pace_for(21), voices.FAST)

    def test_the_style_text_names_the_tone_and_the_pace_and_is_none_when_empty(self):
        self.assertIn("hào hứng", voices.style_for({"tone": "energetic"}, voices.NORMAL))
        self.assertIn("chậm rãi", voices.style_for({"tone": "calm"}, voices.SLOW))
        self.assertIn("nhanh", voices.style_for({}, voices.FAST))
        self.assertIsNone(voices.style_for({}, voices.NORMAL))
        self.assertIsNone(voices.style_for(None, voices.NORMAL))


class RouteTests(unittest.TestCase):
    def analysis(self, **speaker):
        base = {"kind": "dialogue", "confidence": 0.99, "topic": "knowledge", "sensitive": False, "caption_vi": "Mẹo hay",
                "segments": [{"start": 1.0, "end": 5.0, "vi": "Xin chào các bạn"}], "narration_vi": "Xin chào các bạn"}  # fmt: skip
        base["speaker"] = dict({"gender": "female", "tone": "warm", "count": 1, "dub_ok": True}, **speaker)
        return base

    def test_one_person_whose_voice_is_replaceable_is_dubbed_when_the_owner_allows_it(self):
        self.assertEqual(validate_analysis(self.analysis(), 10, strict=True, voiceover_scope="monologue"), "voiceover")
        self.assertEqual(validate_analysis(self.analysis(), 10, strict=True, voiceover_scope="narration"), "vietsub")
        self.assertEqual(validate_analysis(self.analysis(), 10, strict=True), "vietsub")  # the old behaviour is the default of the function

    def test_performances_and_several_speakers_keep_their_own_voices(self):
        for odd in ({"dub_ok": False}, {"count": 2}, {"count": 0}, {"count": None}, {"count": "1"}):
            self.assertEqual(validate_analysis(self.analysis(**odd), 10, strict=True, voiceover_scope="monologue"), "vietsub", odd)

    def test_narration_is_dubbed_as_before_and_music_is_never_touched(self):
        self.assertEqual(choose_route("narration", True)[0], "voiceover")
        self.assertEqual(choose_route("dialogue", True, monologue=True)[0], "voiceover")
        self.assertEqual(choose_route("dialogue", True, monologue=False)[0], "vietsub")
        self.assertEqual(choose_route("music", False, monologue=True)[0], "original")
        self.assertEqual(choose_route("silent", False)[0], "original")

    def test_a_damaged_speaker_block_never_fails_a_video(self):
        for raw in (
            None,
            "x",
            [],
            {"gender": 5, "tone": [], "count": True, "dub_ok": "yes"},
            {"gender": "male", "tone": "furious", "count": -3},
        ):
            clean = clean_speaker({"speaker": raw})
            self.assertIn(clean["gender"], voices.GENDERS)
            self.assertIn(clean["tone"], voices.TONES)
            self.assertIs(clean["dub_ok"], False)
            self.assertIsNone(clean["count"])
        analysis = self.analysis()
        analysis["speaker"] = "loud"
        self.assertEqual(validate_analysis(analysis, 10, strict=True, voiceover_scope="monologue"), "vietsub")
        self.assertEqual(analysis["speaker"]["gender"], "unknown")


class MakeVoiceTests(StoreCase):
    """The voice is fitted to its window with words first (pace), a little speed second, and refused when it cannot fit."""

    def analysis(self, text="x" * 160):
        return {
            "segments": [{"start": 2.0, "end": 12.0, "vi": "a"}],
            "narration_vi": text,
            "speaker": {"gender": "male", "tone": "serious"},
        }

    def make(self, lengths, text="x" * 160):
        calls = []
        spoken = iter(lengths)

        def fake(store, cfg, text, out, voice=None, style=None):
            calls.append((voice, style))
            return next(spoken)

        with mock.patch.object(speech, "tts", fake):
            result = speech.make_voice(self.s, self.s.settings(), self.analysis(text), Path(self.tmp.name))
        return result, calls

    def test_a_voice_that_nearly_fits_is_used_as_it_is(self):
        result, calls = self.make([10.0])
        self.assertAlmostEqual(result["tempo"], 1.0)
        self.assertEqual(result["delay"], 2.0)
        self.assertAlmostEqual(result["seconds"], 10.0)
        self.assertEqual(len(calls), 1)  # one TTS call
        self.assertEqual(voices.GENDER[calls[0][0]], "male")  # a man's speech gets a man's voice
        self.assertIn("nghiêm túc", calls[0][1])

    def test_a_voice_that_is_too_long_is_asked_for_again_faster_before_it_is_sped_up(self):
        result, calls = self.make([13.0, 10.5])
        self.assertEqual(len(calls), 2)
        self.assertIn("nhanh", calls[1][1])
        self.assertAlmostEqual(result["tempo"], 1.05)  # only a small speed change closes the rest

    def test_a_small_overrun_is_closed_by_speed_not_by_another_call(self):
        result, calls = self.make([11.0])
        self.assertEqual(len(calls), 1)
        self.assertAlmostEqual(result["tempo"], 1.1)

    def test_a_voice_much_longer_or_much_shorter_than_its_window_is_refused(self):
        with self.assertRaises(VoiceoverUnfit):
            self.make([15.0, 14.5])  # still far too long after the faster try
        with self.assertRaises(VoiceoverUnfit):
            self.make([3.0])  # the picture would talk without anyone

    def test_a_voice_that_speaks_too_fast_to_follow_is_refused(self):
        with self.assertRaises(VoiceoverUnfit):
            self.make([5.0, 5.0], text="x" * 140)  # 28 characters a second

    def test_a_short_voice_is_slowed_only_a_little(self):
        result, _ = self.make([7.0])
        self.assertAlmostEqual(result["tempo"], 0.92)  # never more than 8% slower: it simply ends early


class AnalysisMemoryTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.video = Path(self.tmp.name) / "v.mp4"
        self.video.write_bytes(b"x" * 1000)
        self.folder = Path(self.tmp.name) / "job"
        self.folder.mkdir()
        self.answer = {"kind": "music", "confidence": 0.99, "topic": "music", "sensitive": False, "caption_vi": "Hay", "segments": []}

    def run_analyze(self, asked, lenient=False, cfg=None):
        def ask(store, path, duration, cfg, folder):
            asked.append(1)
            return json.loads(json.dumps(self.answer))

        with mock.patch.object(analyzer, "_ask", ask):
            return analyzer.analyze(self.s, self.video, 10.0, dict({"audio_confidence": 0.9}, **(cfg or {})), self.folder, lenient=lenient)

    def test_the_video_call_is_paid_once_per_job_even_when_the_run_is_repeated_or_approved(self):
        asked = []
        a, route = self.run_analyze(asked)
        self.assertEqual((route, len(asked)), ("original", 1))
        self.run_analyze(asked)  # a later step failed and the job came back: no second video call
        self.run_analyze(asked, lenient=True)  # the owner approved it: validated again with the checks waived, still no call
        self.assertEqual(len(asked), 1)
        self.assertEqual(a["caption_vi"], "Hay")

    def test_the_remembered_answer_is_raw_so_new_settings_apply_to_it(self):
        asked = []
        self.run_analyze(asked)
        self.answer["kind"] = "dialogue"  # (not consulted: the answer is remembered)
        a, _ = self.run_analyze(asked, cfg={"audio_confidence": 0.99})
        self.assertEqual(a["kind"], "music")
        saved = json.loads((self.folder / "analysis.json").read_text())["answer"]
        self.assertNotIn("route_reason", saved)  # what validation adds is not stored

    def test_a_different_file_or_prompt_asks_again(self):
        asked = []
        self.run_analyze(asked)
        self.video.write_bytes(b"y" * 2000)  # the job's video changed
        self.run_analyze(asked)
        self.assertEqual(len(asked), 2)
        with mock.patch.object(analyzer, "PROMPT_VERSION", "other"):
            self.run_analyze(asked)
        self.assertEqual(len(asked), 3)

    def test_a_damaged_memory_is_ignored(self):
        asked = []
        (self.folder / "analysis.json").write_text("{broken")
        self.run_analyze(asked)
        self.assertEqual(len(asked), 1)


class CondenseTests(StoreCase):
    """Rushed subtitle lines are rewritten shorter, checked line by line; any doubt keeps the original wording."""

    def lines(self):
        return [
            {"start": 0.0, "end": 2.0, "vi": "Xin chào các bạn"},  # 8 characters a second: fine
            {"start": 2.0, "end": 3.0, "vi": "Đây là mục tiêu cần xử lý trong nhiệm vụ lần này đấy"},  # 53 characters in a second
        ]

    def run_condense(self, reply):
        from trendvn_worker.ai import condense as condense_mod

        calls = []

        def fake_generate(store, cfg, parts, schema):
            calls.append(parts[0]["text"])
            if isinstance(reply, Exception):
                raise reply
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(reply)}]}}]}

        with mock.patch.object(condense_mod, "generate", fake_generate):
            return condense_mod.condense(self.s, {}, self.lines()), calls

    def test_only_the_rushed_line_is_sent_with_the_length_it_may_have(self):
        from trendvn_worker.ai import condense as condense_mod

        self.assertEqual(condense_mod.too_fast(self.lines()), [(1, 17)])  # 17 characters a second for one second
        out, calls = self.run_condense({"lines": [{"i": 1, "vi": "Mục tiêu lần này"}]})
        self.assertEqual(out[1]["vi"], "Mục tiêu lần này")
        self.assertEqual(out[0]["vi"], "Xin chào các bạn")  # untouched
        self.assertIn('"max_chars": 17', calls[0])
        self.assertNotIn("Xin chào", calls[0])  # lines that read fine are not even sent

    def test_nothing_rushed_means_no_call(self):
        from trendvn_worker.ai import condense as condense_mod

        with mock.patch.object(condense_mod, "generate", side_effect=AssertionError("no call expected")):
            same = [{"start": 0.0, "end": 4.0, "vi": "Một câu bình thường"}]
            self.assertEqual(condense_mod.condense(self.s, {}, same), same)

    def test_a_bad_rewrite_keeps_the_original_wording(self):
        original = self.lines()[1]["vi"]
        for bad in (
            {"lines": [{"i": 1, "vi": ""}]},  # empty
            {"lines": [{"i": 1, "vi": original + " nữa"}]},  # longer than the original
            {"lines": [{"i": 1, "vi": "x" * 40}]},  # longer than allowed
            {"lines": [{"i": 0, "vi": "a"}]},  # a line that was not asked about
            {"lines": [{"i": "1", "vi": "a"}]},  # wrong type
            {"lines": "no"},
            {"nothing": 1},
            [],
        ):
            out, _ = self.run_condense(bad)
            self.assertEqual(out[1]["vi"], original, bad)

    def test_a_busy_or_failing_model_never_holds_the_video_back(self):
        from trendvn_worker.ai.errors import RateLimited

        original = self.lines()
        for error in (RateLimited("busy"), ValueError("Gemini HTTP 400"), KeyError("x")):
            try:
                out, _ = self.run_condense(error)
            except KeyError:
                continue  # an unexpected exception type is the pipeline's safety net (process_one) to answer, not condense's
            self.assertEqual(out, original)

    def test_the_rewrite_is_cleaned_like_every_other_subtitle(self):
        out, _ = self.run_condense({"lines": [{"i": 1, "vi": "Xem tại evil.com 😂 {x}"}]})
        self.assertNotIn("evil", out[1]["vi"])
        self.assertNotIn("😂", out[1]["vi"])


class AudioMixTests(unittest.TestCase):
    def test_the_voice_is_levelled_delayed_and_the_original_is_turned_down_only_while_it_speaks(self):
        chain, maps = render_mod._audio_chain(True, {"delay": 2.0, "tempo": 1.1, "seconds": 8.0}, True)
        text = ";".join(chain)
        self.assertIn("atempo=1.100", text)
        self.assertIn("loudnorm=I=-16", text)  # the voice on its own first
        self.assertIn("adelay=2000|2000", text)
        self.assertIn("amix=inputs=2:duration=first:normalize=0", text)
        self.assertIn("eval=frame", text)
        self.assertIn(
            "clip((t-1.70)/0.3,0,1)*clip((10.50-t)/0.5,0,1)", text
        )  # eased in before the voice, out after it, untouched elsewhere
        self.assertIn("0.86", text)  # 1 - BED_UNDER_VOICE
        self.assertEqual(maps, ["-map", "[a]"])

    def test_without_levelling_or_without_original_sound_the_chain_stays_valid(self):
        plain, _ = render_mod._audio_chain(True, {"delay": 0.0, "tempo": 1.0}, False)
        self.assertNotIn("loudnorm", ";".join(plain))  # the retry for digital silence must not level either
        only_voice, _ = render_mod._audio_chain(False, {"delay": 1.0, "tempo": 1.0, "seconds": 4.0}, True)
        self.assertNotIn("amix", ";".join(only_voice))
        self.assertEqual(render_mod._audio_chain(False, None, True), ([], []))


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "needs ffmpeg/ffprobe (runs in the worker image)")
class RealMixTests(unittest.TestCase):
    """Real ffmpeg: the original sound drops while the voice speaks and comes back after it."""

    def band_level(self, video, start, length):
        """Level (dB) of the 300 Hz original tone only, in a stretch of the render (the voice is a 1000 Hz tone)."""
        out = subprocess.run(
            [
                "ffmpeg",
                "-v",
                "info",
                "-ss",
                str(start),
                "-t",
                str(length),
                "-i",
                str(video),
                "-af",
                "bandpass=f=300:width_type=h:w=60,volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
        ).stderr.decode()
        return float(out.split("mean_volume:")[1].split("dB")[0])

    def test_the_bed_is_lower_under_the_voice_than_outside_it(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        src, wav = tmp / "s.mp4", tmp / "v.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=s=360x640:d=12:r=25",
                "-f",
                "lavfi",
                "-i",
                "sine=f=300:d=12",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(src),
            ],
            check=True,
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=f=1000:d=4:sample_rate=24000", "-ac", "1", str(wav)], check=True
        )
        folder = tmp / "out"
        folder.mkdir()
        analysis = {"kind": "narration", "segments": [{"start": 4.0, "end": 8.0, "vi": "Xin chào"}]}
        voice = {"wav": wav, "tempo": 1.0, "delay": 4.0, "seconds": 4.0}
        out = render_mod.render(src, folder, analysis, "voiceover", ffmpeg_mod.probe(src)[0], voice)
        before, under, after = self.band_level(out, 0.5, 2.5), self.band_level(out, 4.8, 2.4), self.band_level(out, 9.5, 2.0)
        self.assertLess(under, before - 8)  # at least 8 dB down under the voice
        self.assertLess(under, after - 8)
        self.assertAlmostEqual(
            before, after, delta=6
        )  # roughly the same before and after (the final levelling eases back over a few seconds)


class MaskDecisionTests(unittest.TestCase):
    PORTRAIT = {"reframe": False, "w": 1080, "h": 1920}
    WIDE = {"reframe": True, "w": 1080, "h": 1920, "fg_h": 608, "band_top": 1264}

    def analysis(self, top, bottom):
        return {"hard_subtitles": {"present": True, "top": top, "bottom": bottom}}

    def covered(self, a, geo, mask="auto", route="vietsub"):
        return render_mod.covered_hard_subtitles(a, route, geo, mask)

    def test_a_strip_under_our_captions_is_blurred_and_one_that_is_not_is_left_alone(self):
        self.assertIsNotNone(self.covered(self.analysis(0.70, 0.76), self.PORTRAIT))  # exactly where our captions go
        self.assertIsNone(self.covered(self.analysis(0.88, 0.93), self.PORTRAIT))  # low: under TikTok's own text anyway
        self.assertIsNone(self.covered(self.analysis(0.30, 0.35), self.PORTRAIT))  # high: nothing of ours near it

    def test_on_a_wide_video_our_captions_sit_below_the_picture_so_nothing_is_hidden(self):
        self.assertIsNone(self.covered(self.analysis(0.85, 0.92), self.WIDE))  # the source's text stays, ours is under the picture
        self.assertIsNone(self.covered(self.analysis(0.93, 0.99), self.WIDE))

    def test_the_owners_choice_overrides_the_geometry(self):
        self.assertIsNotNone(self.covered(self.analysis(0.88, 0.93), self.PORTRAIT, "always"))
        self.assertIsNotNone(self.covered(self.analysis(0.85, 0.92), self.WIDE, "always"))
        self.assertIsNone(self.covered(self.analysis(0.70, 0.76), self.PORTRAIT, "off"))

    def test_music_that_stays_as_it_is_and_unusable_bands_are_never_touched(self):
        self.assertIsNone(self.covered(self.analysis(0.70, 0.76), self.PORTRAIT, "always", route="original"))
        self.assertIsNone(self.covered({"hard_subtitles": {"present": True, "top": 0.63}}, self.PORTRAIT, "always"))  # no bottom: ignored
        self.assertIsNone(self.covered({}, self.PORTRAIT))

    def test_the_caption_extent_uses_the_geometry_of_the_drawn_captions(self):
        top, bottom = caption_extent(1080, 1920, {"align": 2, "margin": 518, "box": True})
        self.assertTrue(1200 < top < 1300 and 1380 < bottom < 1440, (top, bottom))  # a two-line box just above the TikTok overlay
        top, bottom = caption_extent(1080, 1920, {"align": 8, "margin": 1312, "box": False})
        self.assertTrue(top >= 1300 and bottom < 1480, (top, bottom))  # under the picture of a wide video


if __name__ == "__main__":
    unittest.main()
