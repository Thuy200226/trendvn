# Output quality: what to measure, what to see, what to choose (version 1.6, 2026-10-02)

All numbers below are real measurements (real Douyin video, real Gemini API, real ffmpeg) on 2026-10-02; Any areas that cannot be measured must be clearly stated. Principle: **measure first, only change when there is evidence, keep speed**.

## 1. Biggest error found: the voice always read the instructions

New TTS models (`gemini-3.x-flash-tts`) treat field `text` as **verbatimcopy**. The old version places an instruction sentence in front of the text ("Read in natural Vietnamese... only read the next paragraph"), so **'s voice reads the whole sentence out loud** before reading the narration. Measure by listening again (copy the sound with another model):

| Calling method | Audio length | Speed | Words spoken correctly / words heard |
|---|---|---|---|
| Old version: instructions + text (`generateContent`) | 18.2 s | 7.3 characters/s | 1.00 / **0.50** (half of the words are instructions) |
| Text only (`generateContent`) | 8.2 s | 16.2 characters/s | 1.00 / 1.00 |
| Text only (Interactions API) | 8.0 s | 16.5 chars/s | 1.00 / 1.00 |

Old consequences: the voiceover looks "too long" compared to the speech window, is sped up or rejected (video falls to Vietsub), and the belief "Gemini reads Vietnamese at about 9.5 characters/second, if you force it to read quickly, you miss sentences" **sai**: natural speed is 16–19 characters/second and doesn't miss any words.

Edit: sent text **is just voiceover**; voice, tone, and pacing in `speech_metadata.style` of the Interactions API (`ai/tts.py`). Older models still receive instructions in front text. There is a test that locks this (`test_the_text_is_sent_as_the_transcript...`).

## 2. Reading speed is controlled verbally, not by forcing sound

Same sentence, 134 characters, Kore accent, every word is read (recall 1.00):

| Style included | Length | Speed |
|---|---|---|
| no | 6.9 s (other times 8.2 s) | 16–19 characters/s |
| "slow, warm, clear accent" | 11.0 s | 12.0 |
| "serious as news" | 8.3 s | 15.9 |
| "fast, exciting, full of energy" | 5.6 s | 23.6 |

Therefore, `make_voice` selects the rhythm according to the number of characters to say per second in the speech window (under 14.5: slow; over 19: fast), calls TTS, if longer than the window by more than 15%, calls **again, one step faster** (slow → normal → fast; jumping straight from slow to fast exceeds window so the second version is never closer than the first). The second call only improves the existing version, so just wait for Google to be busy for a round (maximum 25 seconds) and if there are any errors, keep the first version; Whichever version is closer to the window is used. Then only adjust the maximum speed to +25% (never slower than 8%). Reject and videos keep subtitles when: longer than 25% of the window, shorter than half the window, faster than 24 characters/second, the voice lasts more than 0.3 seconds past the end of the video (only happens with a speech window shorter than 2 seconds at the end of the video), or the voice is silent (under -50 LUFS; the file is deleted so that the next playback creates a new voice instead of rereading the exact silence). Created voices are stored in the folder according to (words, voice, rhythm): videos returned to the queue or approved manually do not have to be created, there is no charge again. Text given to filtered voice as captions (no links, phone numbers, emojis, tags `{an8}`, line breaks `\N`). Natural rhythm keeps voice quality better than stretching the sound.

## 3. Select the voice according to the speaker

Gemini now reports `speaker` (gender, nuance, number of speakers) and `dub_ok` (is there any loss in changing the voice). Male voices are not dubbed with female voices. Verified by letting another model listen to each voice read the same sentence:

| Voice | Output | For |
|---|---|---|
| Kore | female, mature, medium | female: calm, serious, dramatic |
| Aoede | female, young, friendly | female: warm, gentle |
| Leda | female, young, friendly | female: lively, mischievous (and childish) |
| Zephyr | female, young | (unused) |
| Orus | **nam**, mature | male: all shades |

**Unheard**: Puck, Charon, Fenrir, Achird, Sadaltager, Algieba, Gacrux, Sulafat, Callirrhoe, Despina (Google lists Puck, Charon, Fenrir, Orus... as male voices; no evidence of our own). At that time, the Gemini key's daily quota expired (HTTP 429 "exceeded your current quota"), so only one male voice was confirmed and the `POOLS` (`domain/voices.py`) board only used the voice heard. Want to add: call the TTS with the same voice, ask the model to listen and ask for gender/age (see `docs/PROMPTS.md`, TTS section), then add `GENDER` and `POOLS` with the same test.

## 4. Voice acting is preferred when appropriate

- `narration` (narrator): same voiceover.
- A speaker and Gemini for `dub_ok = true` (explanation, tutorial, news reading, product review, storytelling vlog): voiceover. Adjustment range is at "Dub for" (`voiceover_scope`: default `monologue` or `narration`).
- Comedy, drama, controversy, emotional scenes, singing, many people talking: keep the original voice and Vietsub. True measurement: 2-person skit video (53 seconds) ranked by Gemini `dub_ok = false`, `count = 2`, "mischievous" nuance → Vietsub, correct.
- "Vietnamese dubbing" master switch now **enabled by default**. Google was busy while creating the voice, so the video went back to the queue (analysis remembered in `jobs/<id>/analysis.json`, wait without wasting additional video calls), maximum 4 times before joining Vietsub.

## 5. Sound when dubbing

Old version: dubbed voice mixed with original voice lowered to 18% **throughout the entire video**. Now: voices are weighted separately (-16 LUFS) and then mixed; The original sound is only lowered to 14% (about -17 dB) **in the original lyrics window**(from 0.3 s before the voice to the end of the window or the end of the voice, whichever is later, then soft out 0.5 s; a voice shorter than the original speech does not return the original voice to full volume while the original speaker is still speaking) and remains the same at the beginning, rest and end; The whole mix still returns -14 LUFS like every video. Measured with real ffmpeg: original sound (300 Hz) is lower**above 8 dB**subvocal compared to pre- and post-vocal (`test_the_bed_is_lower_under_the_voice_than_outside_it`). After the mix there is an additional peak limiter (`alimiter`, -1.5 dBFS) because the reviewer measured a peak exceeding 0 dBTP after AAC on pulsed music (+3.9 dBTP without, +0.3 with).**Limits of measurement:**On the 7 tracks I built myself (sparse/thick pulse, square, kick drum, hard cut, loud then soft) the limiter shifted peaks no more than 0.3 dB in either direction and all peaks were below -2.7 dBTP, so**There is no test to distinguish between its presence and absence** (only test to make sure it's connected to the right place); and it is not guaranteed not to exceed 0 dBTP (the reviewer's background is still +0.3).

## 6. Blur original subtitles: only when needed, only when needed

The original blurs a horizontal strip **throughout the video** should cover people and scenes even when no one is speaking. Now decided by condition (setting "Blur original subtitles"):

| Mode | What does | do
|---|---|
| Automatic (default) | Blur only when **Vietnamese subtitles will overlap the original text strip** (compare the actual geometry of the subtitle box with the Gemini strip, with 1.5% height padding), and only while Vietnamese subtitles are visible (+0.5 s before, +0.6 s after, merge lines less than 1.5 s apart) |
| Always | Blur when knowing the original text range, still only while Vietnamese subtitles appear |
| Never | No dimming |

Geometric consequences (with test): video **ngang**is put into a vertical frame with Vietnamese subtitles** under the frame ** so never override the original text → the original text remains the same, the image is not obscured. Vertical video has the original text in the right place with Vietnamese subtitles (about 70–76% of the height) → blurred at the right time; The original text is close to the bottom (under the TikTok cover area) or high → leave it as is. The music video stays intact and is never blurred (keeping the lyrics). The Gemini band that says it cannot be used (`bottom` missing, 30% too high) is ignored. The video card on the control panel indicates whether it has been dimmed or left intact.

## 7. Subtitles: less lies and less too fast

- **Fictional lines**: a 53-second skit video that returns 11 real lines then 11 more at 1.0–2.1 seconds (the "reset the clock" and continue writing model); sorted by time, the first real line is truncated and a made-up line appears at 1.6 seconds. Now I find that the clock has been reset and the last part of the line is less than half a second long, so the whole line is removed; The odd line "more than 20 characters in less than 0.5 seconds" was also removed, and a tail of 4 or more lines packed into a short space that added up to more than 30 characters/second was also removed (checked with reviewer data: 11 made-up lines 0.6 seconds long were still eliminated) (`domain/analysis.py`). Line grouping by speaker (valid) is retained.
- **Too fast**: Gemini likes to write 25 characters/second for quick back-and-forth sentences (goal 16). After borrowing time from the break, the line faster than 20 characters/second is shortened with **one call to the text** (works even when the video API is overloaded), each line is tested separately, any line that fails keeps the original text (`ai/condense.py`).

## 8. Encoding and rendering speed: measured, unchanged

30-second clip of 1080p landscape video (1.9 Mb/s source) rendered to a 1080×1920 frame with blurred background; SSIM compared to reference `crf 12 slow`:

| Setup | Time | Capacity | SSIM |
|---|---|---|---|
| **current**veryfast, crf 24, max 4 Mb/s |**7,6 s**|**8,5 MB** | 0.9927 |
| veryfast, crf 22, 4 Mb/s | 7,9 s | 10,9 MB (+29%) | 0,9940 |
| veryfast, crf 20, 6 Mb/s | 8,0 s | 14,4 MB (+69%) | 0,9951 |
| faster, crf 22, 6 Mb/s | 11,2 s (+48%) | 13,1 MB | 0,9948 |
| fast, crf 22, 6 Mb/s | 13,5 s (+78%) | 13,5 MB | 0,9952 |
| veryfast, crf 24, `-tune film` | 10,0 s (+31%) | 8,5 MB | 0,9927 |

SSIM difference is only 0.001–0.002 (the eye cannot distinguish) while capacity increases by 30–70% and time increases by up to 78%; Douyin source is only 1–2 Mb/s, so adding bits cannot restore lost details. **Stay the same.**Recommended TikTok specifications (1080×1920, H.264, 30 fps, minimum 720×1280) achieved; The build runs about 4 times faster than real time. Measured again with real ffmpeg (reviewer, 60 second video, median 3 times): Vietsub editing 21.5 s → 20.5 s, dubbing editing 21.9 s → 22.0 s; +1 s audio branch alone (add `loudnorm` for voice and peak limiter). Fade still runs the blur filter every frame (only the pasted part is toggled on/off over time), so the savings are in the horizontal and low-range video no longer having any pasting, not in the filtering time.**Phase H (2026-10-05):** blur strips are now blurred on a scaled 1/4 scale and then scaled again (same way as blur background), only if the strip is 48 or more pixels high; Thinner strip do the same. Measured on real video that needs blurring (134 seconds, 43% of duration has blurred bands): edit 44.8 seconds → 36.4 seconds (−19%, median of 3 interlaced times, same capacity 43.2 MB); Just attaching `enable=` to `boxblur` gives −5%, which is within the noise threshold and should be removed. The range is different from the old version SSIM 0.988–0.996 (average PSNR 47.7 dB, lowest 36.8 dB), with the naked eye there is no difference (see frames side by side).

## 9. Limits of these measurements

- No human ears: "good sounding voice" is checked by having another model listen and transcribe (word-by-word accuracy, gender, age, rhythm), not by aesthetics. Click "Audio reading" in More → Settings and listen to some real videos before believing.
- The Gemini course's day limit expired halfway, so the male voice set, and the complete playback of a dubbing video from start to finish on the real API (analysis → voice → editing), was not possible. Vocal pairing, mixing and editing were run in real time using ffmpeg with fake audio; The TTS calling part is actually running at each call level.
