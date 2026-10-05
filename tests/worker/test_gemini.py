"""Gemini client resilience: retired models, overload, timeouts, budget, audio formats."""

import base64
import io
import json
import unittest
import wave
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.ai import gemini as gemini_api, tts as speech
from trendvn_worker.domain.settings import DEFAULTS, MODEL_FALLBACKS
from trendvn_worker.store import Store

ROOT = Path(__file__).resolve().parents[2]


class GeminiResilienceTests(StoreCase):
    """Regression tests for problems found by calling the real Gemini API."""

    def setUp(self):
        super().setUp()
        (Path(self.tmp.name) / "gemini.key").write_text("x" * 30)
        self.real_gemini, self.real_sleep = gemini_api.gemini, gemini_api.time.sleep
        gemini_api.time.sleep = lambda s: None

    def tearDown(self):
        gemini_api.gemini, gemini_api.time.sleep = self.real_gemini, self.real_sleep
        super().tearDown()

    def test_retired_model_in_settings_is_upgraded(self):
        with self.s.transaction() as db:
            db.execute("UPDATE settings SET value='\"gemini-2.5-flash\"' WHERE key='model'")
            db.execute("UPDATE settings SET value='\"gemini-2.5-flash-preview-tts\"' WHERE key='tts_model'")
        cfg = Store(self.tmp.name).settings()
        self.assertEqual((cfg["model"], cfg["tts_model"]), (DEFAULTS["model"], DEFAULTS["tts_model"]))

    def test_404_falls_back_and_remembers_working_model(self):
        calls = []

        def fake(store, model, body):
            calls.append(model)
            if model != "gemini-flash-latest":
                raise ValueError("Gemini HTTP 404 (%s): no longer available to new users" % model)
            return {"ok": model}

        gemini_api.gemini = fake
        cfg = self.s.settings()
        r = gemini_api.generate(self.s, cfg, [{"text": "x"}])
        self.assertEqual(r, {"ok": "gemini-flash-latest"})
        self.assertEqual(self.s.settings()["model"], "gemini-flash-latest")  # next call goes straight to it
        calls.clear()
        gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])
        self.assertEqual(calls, ["gemini-flash-latest"])

    def test_a_passing_overload_does_not_make_a_weaker_model_the_permanent_choice(self):
        """gemini-3.5-flash was remembered after one 503 on the preferred model and later wrote a runaway answer for good."""
        state = {"n": 0}

        def busy_once(store, model, body):
            state["n"] += 1
            if model == self.s.settings()["model"] and state["n"] == 1:
                raise ValueError("Gemini HTTP 503 (%s): high demand" % model)
            return {"ok": model}

        gemini_api.gemini = busy_once
        before = self.s.settings()["model"]
        result = gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])
        self.assertNotEqual(result["ok"], before)  # this call was answered by a fallback ...
        self.assertEqual(self.s.settings()["model"], before)  # ... and the next call asks the preferred model again

    def error_429(self, quota_id):
        """What `gemini()` makes of a 429 whose details carry this quota id: Google's text is the same for a per-minute and a per-day limit."""
        import urllib.error
        import urllib.request

        body = {
            "error": {
                "code": 429,
                "message": "You exceeded your current quota, please check your plan and billing details.",
                "details": [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [{"quotaId": quota_id}]}],
            }
        }

        def reject(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 429, "x", {}, io.BytesIO(json.dumps(body).encode()))

        real = urllib.request.urlopen
        urllib.request.urlopen = reject
        try:
            with self.assertRaises(ValueError) as caught:
                self.real_gemini(self.s, "gemini-3.8-flash", {})
        finally:
            urllib.request.urlopen = real
        return str(caught.exception)

    def test_only_a_per_day_quota_is_marked_as_used_up_for_the_day(self):
        self.assertIn(gemini_api.DAILY_QUOTA, self.error_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier"))
        self.assertNotIn(gemini_api.DAILY_QUOTA, self.error_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier"))

    def test_a_per_minute_limit_is_still_waited_for(self):
        slept = []
        gemini_api.time.sleep = slept.append
        gemini_api.gemini = lambda store, model, body: (_ for _ in ()).throw(
            ValueError("Gemini HTTP 429 (%s): You exceeded your current quota, please check your plan and billing details." % model)
        )
        with self.assertRaises(gemini_api.Transient) as caught:
            gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])
        self.assertEqual(slept, [10, 30, 60])  # the same words as a day's quota, but nothing marks it as one: it may clear in seconds
        self.assertIn("quá tải", str(caught.exception))

    def test_a_model_that_is_out_of_quota_does_not_stop_the_waiting_for_one_that_is_only_busy(self):
        slept = []
        gemini_api.time.sleep = slept.append

        def mixed(store, model, body):
            if model == MODEL_FALLBACKS[0]:
                raise ValueError("Gemini HTTP 429 (%s): quota [%s]" % (model, gemini_api.DAILY_QUOTA))
            raise ValueError("Gemini HTTP 503 (%s): high demand" % model)

        gemini_api.gemini = mixed
        with self.assertRaises(gemini_api.Transient):
            gemini_api.generate(self.s, dict(self.s.settings(), model=MODEL_FALLBACKS[0]), [{"text": "x"}])
        self.assertEqual(slept, [10, 30, 60])

    def test_a_key_out_of_quota_is_not_waited_for_in_rounds(self):
        import time as time_module

        slept = []
        calls = []

        def out_of_quota(store, model, body):
            calls.append(model)
            raise ValueError(
                "Gemini HTTP 429 (%s): You exceeded your current quota, please check your plan. [%s]" % (model, gemini_api.DAILY_QUOTA)
            )

        gemini_api.gemini = out_of_quota
        real_sleep = time_module.sleep
        time_module.sleep = slept.append
        try:
            with self.assertRaises(gemini_api.Transient) as caught:
                gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])
        finally:
            time_module.sleep = real_sleep
        self.assertEqual(slept, [])  # tomorrow is not 10, 30 and 60 seconds away
        self.assertEqual(len(calls), len(MODEL_FALLBACKS))  # every model tried once
        self.assertIn("Hạn mức", str(caught.exception))

    def test_overload_retries_then_requeues_instead_of_breaking_the_job(self):
        gemini_api.gemini = lambda store, model, body: (_ for _ in ()).throw(ValueError("Gemini HTTP 503 (%s): high demand" % model))
        with self.assertRaises(gemini_api.Transient):
            gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])
        self.assertTrue(issubclass(gemini_api.Transient, gemini_api.RateLimited))  # process_one re-queues RateLimited

    def test_overload_recovers_on_second_round(self):
        state = {"n": 0}

        def flaky(store, model, body):
            state["n"] += 1
            if state["n"] <= len(MODEL_FALLBACKS):
                raise ValueError("Gemini HTTP 503 (%s): high demand" % model)
            return {"ok": True}

        gemini_api.gemini = flaky
        self.assertEqual(gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}]), {"ok": True})

    def test_timeout_is_transient_and_not_counted(self):
        import urllib.request

        real = urllib.request.urlopen

        def hang(req, timeout=0):
            raise TimeoutError("read timed out")

        urllib.request.urlopen = hang
        try:
            gemini_api.gemini = self.real_gemini
            with self.assertRaises(ValueError) as cm:
                gemini_api.gemini(self.s, "gemini-3.8-flash", {})
            self.assertIn("HTTP 504", str(cm.exception))
            with self.s.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM api_calls").fetchone()[0], 0)
        finally:
            urllib.request.urlopen = real

    def test_total_time_budget_is_respected(self):
        real_time = gemini_api.time.time
        clock = {"now": 1000.0}
        gemini_api.time.time = lambda: clock["now"]
        calls = []

        def slow(store, model, body):
            calls.append(model)
            clock["now"] += 100  # every attempt burns 100 s
            raise ValueError("Gemini HTTP 504 (%s): no response in time" % model)

        gemini_api.gemini = slow
        try:
            with self.assertRaises(gemini_api.Transient):
                gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])
        finally:
            gemini_api.time.time = real_time
        self.assertLessEqual(len(calls), 4)  # the 240 s budget stops the retry loop long before rounds x models

    def test_other_errors_are_not_swallowed(self):
        gemini_api.gemini = lambda store, model, body: (_ for _ in ()).throw(ValueError("Gemini HTTP 401 (x): bad key"))
        with self.assertRaises(ValueError):
            gemini_api.generate(self.s, self.s.settings(), [{"text": "x"}])

    def test_rejected_requests_do_not_use_the_daily_allowance(self):
        import urllib.error
        import urllib.request

        real = urllib.request.urlopen

        def reject(req, timeout=0):
            raise urllib.error.HTTPError(req.full_url, 404, "nf", {}, io.BytesIO(b'{"error":{"message":"gone"}}'))

        urllib.request.urlopen = reject
        try:
            gemini_api.gemini = self.real_gemini
            with self.assertRaises(ValueError) as cm:
                gemini_api.gemini(self.s, "gemini-3.8-flash", {})
            self.assertIn("gone", str(cm.exception))
            with self.s.connect() as db:
                self.assertEqual(db.execute("SELECT count(*) FROM api_calls").fetchone()[0], 0)
        finally:
            urllib.request.urlopen = real

    def test_tts_accepts_wav_pcm_and_reports_duration(self):
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 48000)
        wav = buf.getvalue()
        out = Path(self.tmp.name) / "v.wav"

        def shaped(m, p):
            """What the API sends: the Interactions API's steps for the current TTS models, candidates for generateContent."""
            audio = base64.b64encode(p).decode()

            def reply(store, model, body, endpoint=None):
                if endpoint == "interactions":
                    return {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": audio, "mime_type": m}]}]}
                return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": m, "data": audio}}]}}]}

            return reply

        for mime, payload in (("audio/wav", wav), ("audio/L16;codec=pcm;rate=24000", b"\x00\x00" * 48000), ("", wav)):
            gemini_api.gemini = shaped(mime, payload)
            self.assertAlmostEqual(speech.tts(self.s, self.s.settings(), "Xin chào", out), 2.0, places=2)

    def test_audio_with_no_samples_is_an_error_not_a_voice(self):
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
        audio = base64.b64encode(buf.getvalue()).decode()
        gemini_api.gemini = lambda store, model, body, endpoint=None: {
            "steps": [{"type": "model_output", "content": [{"type": "audio", "data": audio, "mime_type": "audio/wav"}]}]
        }
        with self.assertRaisesRegex(ValueError, "empty audio"):
            speech.tts(self.s, self.s.settings(), "Xin chào", Path(self.tmp.name) / "v.wav")

    def test_every_3x_tts_model_is_spoken_to_through_the_interactions_api_and_nothing_else_is(self):
        """A 3.x TTS model on the plain path got its style spoken aloud as words before the text (gemini-3.1-flash-tts-preview, a listed
        fallback, did not match the first pattern)."""
        for model in ("gemini-3.1-flash-tts-preview", "gemini-3.5-flash-tts", "gemini-3.1-flash-lite-tts"):
            self.assertTrue(speech.INTERACTION_MODEL.fullmatch(model), model)
        for model in ("gemini-2.5-flash-preview-tts", "gemini-3.5-flash"):
            self.assertFalse(speech.INTERACTION_MODEL.fullmatch(model), model)

    def test_the_text_is_sent_as_the_transcript_and_the_style_travels_apart(self):
        """gemini-3.x TTS reads the text VERBATIM: an instruction in front of it was spoken aloud (10 s of it, found 2026-10-02)."""
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 24000)
        audio = base64.b64encode(buf.getvalue()).decode()
        sent = []

        def reply(store, model, body, endpoint=None):
            sent.append((model, endpoint, body))
            return {"steps": [{"type": "model_output", "content": [{"type": "audio", "data": audio}]}]}

        gemini_api.gemini = reply
        out = Path(self.tmp.name) / "v.wav"
        speech.tts(self.s, self.s.settings(), "Chào các bạn.", out, voice="Puck", style="chậm rãi")
        model, endpoint, body = sent[0]
        self.assertEqual((model, endpoint), ("gemini-3.8-flash-tts", "interactions"))
        content = body["input"][0]["content"][0]
        self.assertEqual(content["text"], "Chào các bạn.")  # nothing before it, nothing after it
        self.assertEqual(content["annotations"], [{"type": "speech_metadata", "style": "chậm rãi"}])
        self.assertEqual(body["generation_config"]["speech_config"], [{"voice": "Puck"}])
        speech.tts(self.s, self.s.settings(), "Chào.", out)  # no style: no annotation at all
        self.assertNotIn("annotations", sent[1][2]["input"][0]["content"][0])

    def test_when_the_interactions_api_is_refused_the_plain_text_is_sent_without_any_instruction(self):
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 24000)
        audio = base64.b64encode(buf.getvalue()).decode()
        sent = []

        def reply(store, model, body, endpoint=None):
            sent.append((model, endpoint, body))
            if endpoint == "interactions":
                raise ValueError("Gemini HTTP 400 (%s): bad request" % model)
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": audio}}]}}]}

        gemini_api.gemini = reply
        speech.tts(self.s, self.s.settings(), "Chào các bạn.", Path(self.tmp.name) / "v.wav", style="nhanh")
        self.assertEqual([e for _, e, _ in sent], ["interactions", None])
        self.assertEqual(
            sent[1][2]["contents"][0]["parts"][0]["text"], "Chào các bạn."
        )  # the style is NOT put in front of it for this model

    def test_an_older_tts_model_takes_the_style_as_words_before_the_text(self):
        import io

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 24000)
        audio = base64.b64encode(buf.getvalue()).decode()
        sent = []
        gemini_api.gemini = lambda store, model, body, endpoint=None: sent.append((model, endpoint, body)) or {
            "candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/wav", "data": audio}}]}}]
        }
        self.s.update_settings({"tts_model": "gemini-2.5-flash-preview-tts"})
        speech.tts(self.s, self.s.settings(), "Chào.", Path(self.tmp.name) / "v.wav", style="ấm áp")
        self.assertEqual(sent[0][1], None)
        self.assertEqual(sent[0][2]["contents"][0]["parts"][0]["text"], "ấm áp: Chào.")


if __name__ == "__main__":
    unittest.main()
