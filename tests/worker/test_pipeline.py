"""The processing pipeline end to end with ffmpeg and Gemini replaced by scripted stand-ins."""

import json
from pathlib import Path
from unittest import mock

from tests.support import StoreCase
from trendvn_worker import pipeline
from trendvn_worker.ai.errors import RateLimited
from trendvn_worker.files import file_hash

ANALYSIS = {"kind": "dialogue", "caption_vi": "Mô tả tiếng Việt", "hashtags": ["a", "b", "c"], "segments": []}


class PipelineTests(StoreCase):
    def setUp(self):
        super().setUp()
        self.source = Path(self.tmp.name) / "source.mp4"
        self.source.write_bytes(b"video")
        (self.s.root / "gemini.key").write_text("key")
        self.s.update_settings({"processing_enabled": True, "require_approval": False})
        self.job("j1", "queued", source_file=str(self.source), content_hash=file_hash(self.source))
        self.calls = []

        def render(path, folder, analysis, route, duration, voice=None):
            self.calls.append(("render", route, bool(voice)))
            out = folder / "final.mp4"
            out.write_bytes(b"rendered")
            return out

        patches = mock.patch.multiple(
            pipeline,
            probe=lambda path: (30.0, {"streams": [{"codec_type": "video", "width": 720, "height": 1280}, {"codec_type": "audio"}]}),
            fingerprint=lambda path, duration: [1, 2, 3],
            similar=lambda a, b: a == b,
            analyze=lambda store, path, duration, cfg, folder, lenient=False: (dict(ANALYSIS), "vietsub"),
            make_voice=lambda store, cfg, analysis, folder: {"wav": "v.wav", "delay": 0, "tempo": 1.0},
            render=render,
            qc=lambda out, audio: ({"w": 720, "h": 1280, "duration": 30.0}, []),
            make_poster=lambda out, poster, duration: None,
        )
        patches.start()
        self.addCleanup(patches.stop)

    def row(self, job_id="j1"):
        with self.s.connect() as db:
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def test_a_good_video_becomes_ready_with_a_manifest(self):
        result = pipeline.process_one(self.s)
        self.assertEqual(result, {"id": "j1", "status": "ready", "route": "vietsub"})
        row = self.row()
        self.assertEqual((row["state"], row["route"], row["output_hash"]), ("ready", "vietsub", file_hash(Path(row["output_file"]))))
        manifest = json.loads((self.s.root / "jobs" / "j1" / "manifest.json").read_text())
        self.assertEqual((manifest["route"], manifest["output_hash"], manifest["published"]), ("vietsub", row["output_hash"], False))
        self.assertTrue(json.loads(row["output_info"])["reframed"] is False and json.loads(row["output_info"])["poster"])

    def test_owner_approval_setting_parks_the_video_for_a_decision(self):
        self.s.update_settings({"require_approval": True})
        self.assertEqual(pipeline.process_one(self.s)["status"], "awaiting_approval")
        self.assertEqual(self.row()["state"], "awaiting_approval")

    def test_gates_refuse_before_claiming_anything(self):
        self.s.update_settings({"processing_enabled": False})
        self.assertEqual(pipeline.process_one(self.s)["status"], "disabled")
        self.s.update_settings({"processing_enabled": True})
        (self.s.root / "gemini.key").unlink()
        self.assertEqual(pipeline.process_one(self.s)["status"], "blocked")
        self.assertEqual(self.row()["state"], "queued")
        (self.s.root / "gemini.key").write_text("key")
        pipeline.process_one(self.s)
        self.assertEqual(pipeline.process_one(self.s)["status"], "idle")

    def test_changed_source_or_wrong_length_goes_to_review(self):
        self.source.write_bytes(b"tampered")
        result = pipeline.process_one(self.s)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("changed", result["reason"])
        self.job("j2", "queued", source_file=str(self.source), content_hash=file_hash(self.source))
        with mock.patch.object(pipeline, "probe", lambda path: (9999.0, {"streams": []})):
            self.assertIn("duration", pipeline.process_one(self.s)["reason"])

    def test_visual_duplicate_is_parked_unless_the_owner_approved(self):
        self.job("old", "published", fingerprint=json.dumps([1, 2, 3]), duration=30.0)
        result = pipeline.process_one(self.s)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("old", self.row()["reason"])
        self.job("j2", "queued", source_file=str(self.source), content_hash=file_hash(self.source), approved=1)
        self.assertEqual(pipeline.process_one(self.s)["status"], "ready")

    def test_missing_vietnamese_caption_needs_the_owner(self):
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS, caption_vi="  "), "vietsub")):
            result = pipeline.process_one(self.s)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("mô tả", result["reason"])

    def test_voice_over_route_falls_back_to_subtitles_when_the_voice_fails(self):
        self.s.update_settings({"voiceover_enabled": True})
        analyzer = mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS), "voiceover"))
        with analyzer:
            self.assertEqual(pipeline.process_one(self.s)["route"], "voiceover")
            self.assertEqual(self.calls[-1], ("render", "voiceover", True))
            # the first video's fingerprint is now on file, so the second one needs the owner's approval to skip the look-alike check
            self.job("j2", "queued", source_file=str(self.source), content_hash=file_hash(self.source), approved=1)

            def broken(*a, **k):
                raise ValueError("TTS quota")

            with mock.patch.object(pipeline, "make_voice", broken):
                result = pipeline.process_one(self.s)
        self.assertEqual((result["route"], self.calls[-1]), ("vietsub", ("render", "vietsub", False)))
        self.assertIn("TTS quota", self.row("j2")["reason"])

    def test_voice_over_disabled_in_settings_means_subtitles(self):
        self.s.update_settings({"voiceover_enabled": False})
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS), "voiceover")):
            self.assertEqual(pipeline.process_one(self.s)["route"], "vietsub")

    def test_original_route_renders_without_voice(self):
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS), "original")):
            self.assertEqual(pipeline.process_one(self.s)["route"], "original")
        self.assertEqual(self.calls[-1], ("render", "original", False))

    def test_rate_limit_puts_the_job_back_without_using_an_attempt(self):
        def limited(*a, **k):
            raise RateLimited("Gemini hết hạn mức")

        with mock.patch.object(pipeline, "analyze", limited):
            result = pipeline.process_one(self.s)
        row = self.row()
        self.assertEqual((result["status"], row["state"], row["attempts"]), ("rate_limited", "queued", 0))

    def test_failed_quality_check_blocks_the_video(self):
        with mock.patch.object(pipeline, "qc", lambda out, audio: ({}, ["Bản dựng mất tiếng"])):
            result = pipeline.process_one(self.s)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("Bản dựng mất tiếng", self.row()["reason"])

    def test_a_poster_failure_does_not_fail_the_video(self):
        def no_poster(out, poster, duration):
            raise ValueError("ffmpeg")

        with mock.patch.object(pipeline, "make_poster", no_poster):
            self.assertEqual(pipeline.process_one(self.s)["status"], "ready")
        self.assertFalse(json.loads(self.row()["output_info"])["poster"])

    def info(self, job_id="j1"):
        return json.loads(self.row(job_id)["output_info"])

    def test_the_dashboard_gets_the_reason_for_the_route(self):
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS, route_reason="Có lời nói: thêm phụ đề"), "vietsub")):
            pipeline.process_one(self.s)
        self.assertEqual(self.info()["why"], "Có lời nói: thêm phụ đề")

    def test_a_voice_over_that_falls_back_explains_itself(self):
        analyzer = mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS, route_reason="Người dẫn kể lại"), "voiceover"))
        with analyzer:
            pipeline.process_one(self.s)  # voice-over is off in the default settings
        self.assertIn("chưa bật lồng tiếng", self.info()["why"])

    def test_burned_in_subtitles_are_blurred_only_when_ours_replace_them(self):
        found = dict(ANALYSIS, hard_subtitles={"present": True, "top": 0.72, "bottom": 0.77})
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(found), "vietsub")):
            pipeline.process_one(self.s)
        self.assertTrue(self.info()["hard_subs"])
        self.job("j2", "queued", source_file=str(self.source), content_hash=file_hash(self.source), approved=1)
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(found), "original")):
            pipeline.process_one(self.s)
        self.assertNotIn("hard_subs", self.info("j2"))

    def test_captions_are_given_time_to_be_read_and_a_remaining_rush_is_flagged(self):
        talk = [{"start": 0.0, "end": 1.0, "vi": "x" * 34, "original": ""}, {"start": 1.2, "end": 2.0, "vi": "y" * 60, "original": ""}]
        with mock.patch.object(pipeline, "analyze", lambda *a, **k: (dict(ANALYSIS, segments=talk), "vietsub")):
            pipeline.process_one(self.s)
        analysis = json.loads(self.row()["analysis"])
        self.assertGreater(analysis["segments"][0]["end"], 1.0)  # borrowed from the pause
        self.assertLessEqual(analysis["segments"][0]["end"], 1.15)  # but never over the next caption
        info = self.info()
        self.assertGreater(info["max_cps"], 24)
        self.assertIn("nhanh", info["warning"])
