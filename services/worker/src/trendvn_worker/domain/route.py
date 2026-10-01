"""What to do with a video: keep it as it is, add Vietnamese subtitles, or replace the speech with a Vietnamese voice-over.

The decision is a pure function of what Gemini heard, so it can be read, tested and tuned in one place (docs/PROMPTS.md has the table).
Every route comes with the reason shown to the owner on the dashboard.
"""

ORIGINAL = "original"
VIETSUB = "vietsub"
VOICEOVER = "voiceover"

REASONS = {
    "music": "Nhạc, không có lời nói: giữ nguyên âm thanh gốc",
    "silent": "Không có tiếng: giữ nguyên",
    "speech": "Có lời nói: giữ giọng gốc và thêm phụ đề tiếng Việt",
    "speech_in_music": "Video nhạc có kèm lời nói: thêm phụ đề cho phần lời nói, giữ nhạc",
    "narration": "Người dẫn kể lại: thay bằng thuyết minh tiếng Việt",
    "narration_no_voice": "Người dẫn kể lại, chưa bật lồng tiếng: dùng phụ đề tiếng Việt",
    "voice_failed": "Không tạo được giọng đọc: dùng phụ đề tiếng Việt",
}


def choose_route(kind, has_segments):
    """(route, reason) for a validated analysis. `kind` is Gemini's classification of the audio; `has_segments` says whether any
    speech was transcribed. Videos that need on-screen text translated but carry no speech are refused before this is called."""
    if kind in ("dialogue", "mixed"):
        return VIETSUB, REASONS["speech"]
    if kind == "narration":
        return VOICEOVER, REASONS["narration"]
    if has_segments:  # music or silence with a spoken line in it
        return VIETSUB, REASONS["speech_in_music"]
    return ORIGINAL, REASONS["music" if kind == "music" else "silent"]
