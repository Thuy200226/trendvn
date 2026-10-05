"""Which voice reads the Vietnamese voice-over, and how: pure choices from what Gemini heard in the original.

The voice follows the speaker (a man's speech is not dubbed by a woman), the delivery follows the tone, and the pace follows how much
text has to fit in how many seconds. docs/QUALITY.md has the measurements behind the table (gender and age as heard by a second model
listening to each voice, pace per style).
"""

SLOW, NORMAL, FAST = "slow", "normal", "fast"

# name -> gender as heard in the listening test of 2026-10-02 (docs/QUALITY.md): each voice read the same Vietnamese sentence and a second
# model, listening to the audio, said who it heard. Only confirmed voices are in the pools below. Google documents Puck, Charon, Fenrir,
# Achird, Sadaltager and others as male voices, but the test could not finish: the day's quota of the API key ran out after Orus (docs/QUALITY.md
# lists what is still to be heard; add a voice here and to POOLS only after it has been).
GENDER = {
    "Kore": "female", "Leda": "female", "Aoede": "female", "Zephyr": "female",
    "Orus": "male",
}  # fmt: skip

# tone -> voice, per gender. The tones are the ones the analysis may report (ai/prompts.py): calm, warm, energetic, serious, playful,
# dramatic, gentle. A tone without an entry uses "calm". The delivery (style words) differs by tone even when the voice is the same.
POOLS = {
    "female": {"calm": "Kore", "warm": "Aoede", "energetic": "Leda", "serious": "Kore", "playful": "Leda", "dramatic": "Kore", "gentle": "Aoede"},
    "male": {tone: "Orus" for tone in ("calm", "warm", "energetic", "serious", "playful", "dramatic", "gentle")},
}  # fmt: skip
TONES = ("calm", "warm", "energetic", "serious", "playful", "dramatic", "gentle")
GENDERS = ("male", "female", "child", "mixed", "unknown")

# Vietnamese words for the delivery (the style text of the TTS request): what the speaker sounds like, and how fast.
TONE_WORDS = {
    "calm": "điềm tĩnh, rõ ràng",
    "warm": "ấm áp, thân thiện",
    "energetic": "hào hứng, đầy năng lượng",
    "serious": "nghiêm túc như bản tin",
    "playful": "vui tươi, tinh nghịch",
    "dramatic": "kịch tính, nhấn nhá",
    "gentle": "nhẹ nhàng, dịu dàng",
}
PACE_WORDS = {SLOW: "chậm rãi, nhấn nhá rõ ràng", NORMAL: "", FAST: "nhanh, gọn, dứt khoát"}
# characters per second the narration needs to fit its window: below SLOW_BELOW a slow delivery fills the window (the analysis asks for
# about 13 a second, which a plain delivery at 16-19 would finish early), above FAST_ABOVE a fast one is needed (measured with Kore:
# plain 16-19, slow 12, fast 24)
SLOW_BELOW = 14.5
FAST_ABOVE = 19.0


def pick_voice(cfg, speaker):
    """The voice for this speaker. `voice_mode` "fixed" (or an unknown speaker) uses the owner's chosen voice."""
    speaker = speaker if isinstance(speaker, dict) else {}
    gender = "female" if speaker.get("gender") == "child" else speaker.get("gender")
    if cfg.get("voice_mode", "auto") == "fixed" or gender not in POOLS:
        return cfg["voice"]
    pool = POOLS[gender]
    return pool.get(speaker.get("tone"), pool["calm"])


def pace_for(chars_per_second):
    """The delivery pace that lands nearest a window needing this many characters a second."""
    if chars_per_second < SLOW_BELOW:
        return SLOW
    return FAST if chars_per_second > FAST_ABOVE else NORMAL


def faster(pace):
    """The next quicker delivery, one step at a time (slow to fast overshoots a window that needed about 14 characters a second), or None
    when the delivery is already the fastest."""
    return {SLOW: NORMAL, NORMAL: FAST}.get(pace)


def style_for(speaker, pace):
    """The style text for the TTS request: tone words and pace words, or None when there is nothing to say."""
    speaker = speaker if isinstance(speaker, dict) else {}
    tone = TONE_WORDS.get(speaker.get("tone"))
    pace_words = PACE_WORDS.get(pace, "")
    words = ", ".join(w for w in (tone, pace_words) if w)
    return words or None
