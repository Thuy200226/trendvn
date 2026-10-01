"""Vietnamese voice-over with Gemini text-to-speech, fitted to the window the original speech occupies."""

import base64
import re
import wave
from pathlib import Path

from ..domain.settings import TTS_FALLBACKS
from ..media.ffmpeg import ffmpeg
from .errors import VoiceoverUnfit
from . import gemini as client
from .prompts import TTS_PROMPT

# Gemini reads Vietnamese at about 9.5 characters a second. Told to hurry it jumps to 16 and silently skips whole sentences (measured by
# transcribing the audio back: 79% of the words survived), so anything much faster than natural speech is refused instead of posted.
MAX_CHARS_PER_SECOND = 14


def tts(store, cfg, text, out):
    if not isinstance(text, str) or not text.strip() or len(text) > 6000:
        raise ValueError("Invalid Vietnamese narration")
    body = {
        "contents": [{"parts": [{"text": TTS_PROMPT + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": cfg["voice"]}}},
        },
    }
    data = client.call_with_fallback(store, cfg, "tts_model", TTS_FALLBACKS, lambda model: client.gemini(store, model, body))
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    audios = [p.get("inlineData", p.get("inline_data")) for p in parts if p.get("inlineData") or p.get("inline_data")]
    if not audios:
        raise ValueError("TTS did not return audio")
    audio = audios[0]
    mime = audio.get("mimeType", audio.get("mime_type", ""))
    raw = base64.b64decode(audio["data"], validate=True)
    if "audio/L16" in mime or "audio/pcm" in mime:
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
    with wave.open(str(out), "rb") as w:
        return w.getnframes() / w.getframerate()


def make_voice(store, cfg, a, folder):
    """Vietnamese narration audio fitted to the time window the original speech occupies."""
    text = (a.get("narration_vi") or "").strip() or " ".join(s["vi"] for s in a["segments"])
    wav = folder / "voice.wav"
    seconds = tts(store, cfg, text, wav)
    if len(text) / seconds > MAX_CHARS_PER_SECOND:
        raise VoiceoverUnfit("Giọng đọc %.1fs quá ngắn cho %d ký tự: có thể bị bỏ sót chữ" % (seconds, len(text)))
    start = a["segments"][0]["start"]
    end = a["segments"][-1]["end"]
    span = max(2.0, end - start)
    ratio = seconds / span
    if not 0.7 <= ratio <= 1.4:
        raise VoiceoverUnfit("Giọng đọc %.1fs không khớp cửa sổ lời %.1fs" % (seconds, span))
    return {"wav": wav, "tempo": min(1.4, max(0.85, ratio)), "delay": start}
