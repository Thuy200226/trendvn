"""Vietnamese voice-over with Gemini text-to-speech, fitted to the window the original speech occupies.

What the current TTS models (gemini-3.x-flash-tts) do, measured on 2026-10-02 by transcribing the audio back: the `text` is a VERBATIM
transcript. An instruction written before it ("Đọc bằng tiếng Việt tự nhiên... chỉ đọc đoạn sau:") is read ALOUD, which put an extra
10 seconds of spoken instructions in front of every voice-over and made the narration look far too long for its window. Style and pace
travel separately, in the Interactions API's `speech_metadata.style`; the same style words move the pace from 12 to 24 characters a
second with every word still spoken (recall 1.00), so pace is chosen with words, not by squeezing the audio afterwards.
"""

import base64
import re
import wave
from pathlib import Path

from ..domain import voices
from ..domain.settings import TTS_FALLBACKS
from ..media.ffmpeg import ffmpeg
from . import gemini as client
from .errors import VoiceoverUnfit

# A voice that speaks faster than this is not followable (the same limit the subtitles use is 17; spoken Vietnamese is easier to follow).
MAX_CHARS_PER_SECOND = 24
# How much the finished audio may be sped up to fit its window (a natural voice sped up more than this sounds hurried), and the shortest
# it may be compared with the window (a much shorter voice leaves the picture talking without anyone).
MAX_TEMPO = 1.25
MIN_TEMPO = 0.92  # never slowed down: a voice that finishes early simply finishes early
MIN_FILL = 0.5
TRY_AGAIN_ABOVE = 1.15  # longer than the window by more: ask once more with a faster delivery before stretching
INTERACTION_MODEL = re.compile(r"gemini-3\.\d+-flash(-lite)?-tts")


def _interaction_body(model, text, voice, style):
    content = {"type": "text", "text": text}
    if style:
        content["annotations"] = [{"type": "speech_metadata", "style": style}]
    return {
        "model": model,
        "input": [{"type": "user_input", "content": [content]}],
        "response_format": {"type": "audio"},
        "generation_config": {"speech_config": [{"voice": voice}]},
    }


def _legacy_body(text, voice, style):
    spoken = (style + ": " + text) if style else text  # older models take direction as words before the text
    return {
        "contents": [{"parts": [{"text": spoken}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }


def _audio_of_interaction(data):
    audios = [c for s in data.get("steps", []) if s.get("type") == "model_output" for c in s.get("content", []) if c.get("type") == "audio"]
    if not audios:
        raise ValueError("TTS did not return audio")
    return audios[-1].get("mime_type", audios[-1].get("mimeType", "")), audios[-1]["data"]


def _audio_of_candidate(data):
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    found = [p.get("inlineData", p.get("inline_data")) for p in parts if p.get("inlineData") or p.get("inline_data")]
    if not found:
        raise ValueError("TTS did not return audio")
    return found[0].get("mimeType", found[0].get("mime_type", "")), found[0]["data"]


def _write_wav(mime, encoded, out):
    raw = base64.b64decode(encoded, validate=True)
    if "audio/L16" in mime or "audio/pcm" in mime or (not mime and raw[:4] != b"RIFF"):
        rate_match = re.search(r"rate=(\d+)", mime)
        rate = int(rate_match.group(1)) if rate_match else 24000
        with wave.open(str(out), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(raw)
    elif raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        Path(out).write_bytes(raw)  # newer TTS models return a complete WAV file
    elif mime.startswith("audio/"):
        src = Path(str(out) + ".src")
        src.write_bytes(raw)  # mp3, ogg, ...: let ffmpeg normalise it to WAV
        try:
            ffmpeg("-i", str(src), "-ar", "24000", "-ac", "1", str(out))
        finally:
            src.unlink(missing_ok=True)
    else:
        raise ValueError("Unexpected TTS audio format: " + mime[:40])


def tts(store, cfg, text, out, voice=None, style=None):
    """Speak `text` (exactly this text, nothing added) with `voice` in the delivery `style` into the WAV file `out`. Returns its length in
    seconds. The newest models are asked through the Interactions API; if that is refused (HTTP 400/404) the same model gets a plain
    generateContent request WITHOUT any instruction text, and older models get the style as words before the text."""
    if not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise ValueError("Invalid Vietnamese narration")
    voice = voice or cfg["voice"]

    def attempt(model):
        if INTERACTION_MODEL.fullmatch(model):
            try:
                return _audio_of_interaction(
                    client.gemini(store, model, _interaction_body(model, text, voice, style), endpoint="interactions")
                )
            except ValueError as error:
                if "HTTP 400" not in str(error) and "HTTP 404" not in str(error):
                    raise
                return _audio_of_candidate(client.gemini(store, model, _legacy_body(text, voice, None)))
        return _audio_of_candidate(client.gemini(store, model, _legacy_body(text, voice, style)))

    mime, encoded = client.call_with_fallback(store, cfg, "tts_model", TTS_FALLBACKS, attempt)
    _write_wav(mime, encoded, out)
    with wave.open(str(out), "rb") as w:
        return w.getnframes() / w.getframerate()


def make_voice(store, cfg, a, folder):
    """Vietnamese narration audio fitted to the time window the original speech occupies. The voice follows the speaker (a man's speech
    gets a man's voice), the delivery follows the tone, and the pace is asked for in words to land close to the window; whatever
    remains is closed with a small speed change, never a big one. Raises VoiceoverUnfit when it cannot fit (the video then keeps subtitles).
    """
    text = (a.get("narration_vi") or "").strip() or " ".join(s["vi"] for s in a["segments"])
    wav = folder / "voice.wav"
    start, end = a["segments"][0]["start"], a["segments"][-1]["end"]
    span = max(2.0, end - start)
    voice = voices.pick_voice(cfg, a.get("speaker"))
    pace = voices.pace_for(len(text) / span)
    seconds = tts(store, cfg, text, wav, voice, voices.style_for(a.get("speaker"), pace))
    if seconds / span > TRY_AGAIN_ABOVE and pace != voices.FAST:
        pace = voices.FAST  # one more try, delivered faster, before the audio is sped up
        seconds = tts(store, cfg, text, wav, voice, voices.style_for(a.get("speaker"), pace))
    if len(text) / seconds > MAX_CHARS_PER_SECOND:
        raise VoiceoverUnfit("Giọng đọc %.1fs quá ngắn cho %d ký tự: có thể bị bỏ sót chữ" % (seconds, len(text)))
    ratio = seconds / span
    if ratio > MAX_TEMPO or ratio < MIN_FILL:
        raise VoiceoverUnfit("Giọng đọc %.1fs không khớp cửa sổ lời %.1fs" % (seconds, span))
    tempo = min(MAX_TEMPO, max(MIN_TEMPO, ratio))
    return {"wav": wav, "tempo": tempo, "delay": start, "seconds": seconds / tempo, "voice": voice, "pace": pace}
