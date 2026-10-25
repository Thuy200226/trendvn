"""What to do with a video: keep it as it is, add Vietnamese subtitles, or replace the speech with a Vietnamese voice-over.

The decision is a pure function of what Gemini heard, so it can be read, tested and tuned in one place (docs/PROMPTS.md has the table).
Every route comes with the reason shown to the owner on the dashboard.
"""

ORIGINAL = "original"
VIETSUB = "vietsub"
VOICEOVER = "voiceover"

REASONS = {
    "music": "Nh\u1ea1c, kh\u00f4ng c\u00f3 l\u1eddi n\u00f3i: gi\u1eef nguy\u00ean \u00e2m thanh g\u1ed1c",
    "silent": "Kh\u00f4ng c\u00f3 ti\u1ebfng: gi\u1eef nguy\u00ean",
    "speech": "C\u00f3 l\u1eddi n\u00f3i: gi\u1eef gi\u1ecdng g\u1ed1c v\u00e0 th\u00eam ph\u1ee5 \u0111\u1ec1 ti\u1ebfng Vi\u1ec7t",
    "speech_in_music": "Video nh\u1ea1c c\u00f3 k\u00e8m l\u1eddi n\u00f3i: th\u00eam ph\u1ee5 \u0111\u1ec1 cho ph\u1ea7n l\u1eddi n\u00f3i, gi\u1eef nh\u1ea1c",
    "narration": "Ng\u01b0\u1eddi d\u1eabn k\u1ec3 l\u1ea1i: thay b\u1eb1ng thuy\u1ebft minh ti\u1ebfng Vi\u1ec7t",
    "monologue": "M\u1ed9t ng\u01b0\u1eddi n\u00f3i, gi\u1ecdng \u0111\u1ecdc ti\u1ebfng Vi\u1ec7t thay \u0111\u01b0\u1ee3c: l\u1ed3ng ti\u1ebfng",
    "narration_no_voice": "Video h\u1ee3p l\u1ed3ng ti\u1ebfng nh\u01b0ng ch\u01b0a b\u1eadt l\u1ed3ng ti\u1ebfng: d\u00f9ng ph\u1ee5 \u0111\u1ec1 ti\u1ebfng Vi\u1ec7t",
    "voice_failed": "Kh\u00f4ng t\u1ea1o \u0111\u01b0\u1ee3c gi\u1ecdng \u0111\u1ecdc: d\u00f9ng ph\u1ee5 \u0111\u1ec1 ti\u1ebfng Vi\u1ec7t",
}


def choose_route(kind, has_segments, monologue=False):
    """(route, reason) for a validated analysis. `kind` is Gemini's classification of the audio; `has_segments` says whether any
    speech was transcribed; `monologue` says one person speaks and replacing the voice loses nothing (the analysis' dub_ok with a
    speaker count of 1, and the owner allows voice-over for such videos). Videos that need on-screen text translated but carry no
    speech are refused before this is called."""
    if kind in ("dialogue", "mixed"):
        return (VOICEOVER, REASONS["monologue"]) if monologue and has_segments else (VIETSUB, REASONS["speech"])
    if kind == "narration":
        return VOICEOVER, REASONS["narration"]
    if has_segments:  # music or silence with a spoken line in it
        return VIETSUB, REASONS["speech_in_music"]
    return ORIGINAL, REASONS["music" if kind == "music" else "silent"]
