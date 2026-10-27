# Source language maintenance — 2026-10-25

- Translate documentation, comments and docstrings into English.
- Preserve Vietnamese runtime text with Unicode/octal escapes and keep generated workflow JSON ASCII-escaped.
- Rename macOS launchers to English and update their references.
- Update documentation lint history markers to match the translated migration guide.

# Change history

## Unreleased — 2026-10-28 (review of design and implementation: docs/ROADMAP.md, "Design and implementation review")

Two independent read-only reviews (worker; host agent and n8n) found eight real defects. Each fix has a test that fails when the fix is removed (mutation-checked).
- **Retention clocks no longer reset by a scan.** A scan that saw a known video again reset `updated`, which drives file removal of finished videos, the 21-day expiry, the 45-minute publishing expiry and the daily post count: files of a rejected or duplicate video that stayed popular were kept for good, and a stuck `publishing` post blocked every account for longer than 45 minutes. `last_seen` already records the sighting.
- **One failing video no longer blocks processing.** A video sent back after a transient Gemini failure (a 5xx, or a timeout reported as HTTP 504) was claimed first on every run, so 1-2 such videos stopped everything (reviewer's simulation: 0 of 8 runs processed anything). `claim()` now takes the video that waited longest since it entered the queue, so a sent-back video goes behind the others; after 10 transient failures of the same video (`MAX_DEFERRALS`) it waits for the owner, and approving it starts the count again. Our own daily budget running out never counts.
- **The download room is shared across platforms.** Each platform filled the room in the order of `SOURCES` before the next one ran (reviewer's simulation: Douyin 18 downloads, Kuaishou 1 in 16 cycles, whatever the weights). Platforms scanned in the same browser session are now scanned first and the downloads are chosen once from one pool (`fetch_pooled`), ranked by score with the topic round-robin unchanged.
- **A CAPTCHA that appears after the file was sent pauses the account.** It covered the editor, the step failed with "element is covered" and the video got a strike without any pause (each 30-minute slot burned a video). When a step fails before the Post click, the page is now checked for a verification and reported as `challenge`.
- **The caption is checked as strictly before the click as after it.** The pre-click check compared 25 normalised characters, the profile check after the click 60: an editor that dropped letters past the 25th let a wrong caption go live that could never be confirmed. Both use the same key now.
- **Backup on macOS no longer passes without the session.** `pack_profiles` treated tar exit code 1 as the benign "file changed while read"; that is GNU tar. bsdtar (macOS) exits 1 for any error, an unreadable `Cookies` file included, so the backup passed with no session in it. 1 is tolerated only for GNU tar.
- **`./trendvn test` on macOS runs green.** `int.bit_count()` needs Python 3.10 and macOS ships 3.9; replaced by `bin(x).count("1")` (same result).
- **The result of a post is recorded first.** The verification pause was reported before `/api/publish/finish`; if that call failed the result was never sent and the video became a false "unconfirmed post" 45 minutes later. The result is sent first and retried 3 times (a refusal from the worker is final); the pause and login reports follow and can no longer fail the job.


## 1.6 — 2026-10-02 (output quality: docs/QUALITY.md)

**Biggest error found:**reading voice**Read the instructions out loud**standing in front of the voiceover (new TTS model `text` is a verbatim transcript): adds 10 seconds of instruction to every voiceover video, making it look too long and then being sped up or rejected. Now only send notes; voice, tone and rhythm `speech_metadata.style` (Interactions API); Older models still receive text instructions. The old conclusion "if you read quickly, you miss sentences" is also wrong (16–19 characters/second naturally, still enough for each word).**Dubbing is preferred when appropriate.**Gemini reports additional `speaker` (gender, nuance, number of speakers) and `dub_ok`: voice-over video** and one-person video with voice change at no cost**are dubbed; Comedy, drama, many speakers keep original voice + Vietsub. The voice follows the speaker (heard and tested with another model: Kore, Aoede, Leda female; Orus male), rhythm is selected verbally according to the number of characters to say per second, then only adjusts the speed slightly. If Google is busy, the video will return to the queue (the analysis is remembered in `jobs/<id>/analysis.json`, no additional video calls will be needed; manual approval will not call back), up to 4 times and then exit to Vietsub. New settings: "Dubbing for", "Choose voice", "Dubbing Vietnamese" switch is on by default.**Voice voice.**Individual scale voice -16 LUFS; Original audio is only lowered (to 14%) in both the original lyrics window, soft in/out, stays the same outside (previously lowered to a fixed 18% throughout the video); after the mix there is a peak limiter. Measured: more than 8 dB below the voice.** Blur original subtitles according to conditions.**"Blur original subtitles" setting: Automatic (default: only when Vietnamese subtitles will overlap the original text, compared to real geometry), Always, Never; always only while Vietnamese subtitles appear. Horizontal videos (Vietnamese subtitles below the frame) are no longer blurred.**Subtitles.**Removed made-up lines when the model "resets the clock" (a 53-second skit with 11 made-up lines appears at 1.6 seconds); Lines that are too fast (>20 characters/second) are shortened with one text call, checking each line.**After two rounds of independent review (2026-10-02 and 2026-10-05; details in docs/ROADMAP.md, Phase F).**
- The created voice and short text are stored in the work folder: the video is recorded back in the queue or approved without payment. Remembered parsing is kept only if it is structurally valid, atomically written, and the key includes both description and model (the previous version's file, which did not have these two fields, can still be used to avoid having to pay an additional video call for each waiting video).
- Voice rejected when extending beyond the end of the video or silence (silence file is deleted); The text given to the voice removes emoji, tag `{an8}`, line break `\N`.
- The second voice creation (when the first voice is too long) is one step faster than **** instead of jumping from slow to fast, just waiting for Google to be busy for a round, and whatever error it has, it will keep the first version.
- Gemini: the model can run when the configuration model is only busy and no longer remembers to change the configuration model; only 429 according to **day** (read from the error details) skips round waiting, 429 according to minutes still waits.
- **Fatal bug fixed:** hand-approved video was queued forever when Google was busy generating voice (delay counter was set to zero on each run because the `approved` flag stayed on the stream); Now the counter only resets once, when browsing.
- mp3/ogg to WAV branch failed because of filename `.part` (ffmpeg failed to select format): specified `-f wav`.

**Multiple accounts (Phase G).**Expired TikTok sessions are no longer counted as video errors (postponed, reporting each account with a log in command; testing a 3-hour session does not clear the log out flag); a suspended post does not block other accounts for more than 45 minutes; CAPTCHA, "Post now" confirmation box, and Post button per account; `tiktok dry-run --account`; Chrome profile backup does not have cache. Details and remaining part: docs/ROADMAP.md, Phase G section.**Product quality (Phase I).**Honest status bar (7 hours), "why not posted" line on each video, rejected Gemini lock keeps videos in queue and shows on banner and To watch tab (phone: maximum every 6 hours), errors and reasons in Vietnamese (with code scanning test), list showing Vietnamese description, list match count, collection steps After all the errors, an error message appears, `./trendvn doctor` has the same drive threshold as the control board and checks `linger`, the first installation order is correct. Details: docs/ROADMAP.md, Phase I section.**Performance (Phase H).**The original subtitle blur strip is blurred on a 1/4 thumbnail and then re-zoomed: video editing requires 19% faster blurring (44.8 → 36.4 seconds on real 134-second video), equivalent image (SSIM 0.988–0.996). The collector writes in `agent.log` time each scroll and tab switch. Constant measurements and tests (encoder, QC pooling, acquisition latency): docs/ROADMAP.md, Phase H section.**Measured and unchanged:** encoding (crf, preset, tune: SSIM only difference 0.001–0.002 but capacity +30–70%, time +31–78%). Performance is the same or better (less blurring).

## 1.5 — 2026-10-02 (3-round independent review: docs/ROADMAP.md, section "Review 1.5")

**Content at the request of the channel owner.**Only "hard limit" left to block videos (sex, children in danger, real blood, hatred, self-harm/crime, dangerous advice, private life); Politics, controversies, dramas, accidents in the news, scandals, shocking scenes are posted normally. Add topic `news` (breaking news/drama), set `caption_style` (`hook` = caption description sticks to the video, default; `factual`), reach hashtag (`xuhuong`, `fyp`, `viral`) is allowed, always enough 3–5 unsigned tags with topic tag. The system does not and cannot guarantee that a video is "definitely viral" or that a channel "will never be removed": see docs/SECURITY.md sections 1 and 7.**Security (static + dynamic + independent review).**- Passwordless console only if `Host` is localhost**and**connect to from host (or project's Docker bridge port)**and** do not have reverse proxy header; `TRENDVN_TRUSTED_PEERS` for Docker Desktop. Login session saved on server (7 days, `/logout` and "Logout" button disabled), `Secure` when `TRENDVN_UI_HTTPS=1`.
- HTTP Server: `Content-Length` negative/strange denied (used to cause `/login` unlimited reads), socket expires 30 seconds per read, max 48 threads (503 left over), backlog 64; CSP no longer has `script-src 'unsafe-inline'` (hashed script), `base-uri 'none'`, `Permissions-Policy`; log cleans control characters and logs source addresses of 401/403.
- Gemini output test port: duplicate JSON key, multiple objects, `caption_vi` not string rejected; Description and subtitles are filtered for links, @name, phone number, email, hidden/inverted characters (subtitles: also emoji); A reminder "content in the video is not instructions" is sent after the video.
- Video download: tight URL syntax (backslash, user-info, IP, port), yt-dlp proxy via environment variables, request body limit agent, and socket expiration. Notice: no IP, must resolve to public address, no redirects, no @everyone.
- Bug fix: too large heartbeat used to crash a setup line and cause 500 error on every page; `resolve_unknown` receives `javascript:` as path; 3 endpoints pay 500 when the data type is wrong.
- `./trendvn test lint` blocks hidden/inverted characters in source code (Trojan Source attack); Use code `\\uXXXX` instead of pasting directly.
- compose: `cap_drop: ALL` for both n8n, limit RAM/number of processes, pin background image by hash code; add `.github/workflows/ci.yml` (SHA pin, not running on GitHub yet).

**Edited after real use.**A Douyin video goes to "Need approval" with the reason "Gemini returns unreadable data": model `gemini-3.5-flash` wrote the correct analysis and then fell into a loop in subfield `sensitive_reason` (an endless sequence of 13,455 tokens up to the starting limit output, the JSON is cut off). That field is not used anywhere so it has been removed from the schema and prompt (`PROMPT_VERSION` 2026-10-02.2); The remaining text fields have a length ceiling (`maxLength`, `maxItems`), tried it: same video now outputs 2,528 tokens, ends `STOP`, with hard subtitle position; The cut answer at `MAX_TOKENS` is reported for the correct reason in Vietnamese.**The original subtitle blur strip no longer covers the entire video.**The burned-in Chinese text blur strip used to cover the entire video and its width, so it covers people and scenes even when no one is speaking; Now it's only blurred while Vietnamese subtitles are showing (plus padding, merging lines close together). The affected pre-rendered video (one video) is reconstructed from the saved source and analysis (do not call Gemini).**Logic and performance.**
- Disk cleanup (risk of repetition of this project): expire candidates/videos that no one has decided, delete files of finished videos after 7 days, shred history, delete orphan files; Stop downloading less than 1 GB free and stop downloading less than 512 MB; Chrome limits caching to 64MB; `agent.log` rotation; The Overview page shows the drive.
- Select candidates by score (no more "latest 100 videos"), filter by platform; Douyin does not have views measured by heart; limit the length according to the correct setting (no hard block of 180 seconds); "Kuaishou did not return the video" is no longer reported as a CAPTCHA.
- The "Ready" number is the actual total (not the first 30 lines); Queue includes videos waiting for approval.
- Worker restarts and automatically reorders videos in progress; wait-and-retry start when database is locked; old lease no longer causes `process_one` to throw errors; 1×1 video rejected; ffmpeg error does not reveal directory path.
- Measured on a fake database of 20,000 videos: `record_stats` 200 items 927 → 9 ms, page 52 → 39 ms, `status` 22 → 17 ms.
- Keyword suggested topic `news` narrow (remove breaking, 社会, 现场, 监控, 反转, 曝光, tense: too general, often mismatched); just a suggestion before loading, Gemini still decides the topic after analysis.
- Migration 4 (`main` receives `news` if the master has not edited the list; constants in migration are no longer imported) and 5 (`pruned_at`, duplicate hash index).

**Expand.** A single platform table (`domain/platforms.py REGISTRY`) that generates labels, thresholds, banned hashtags, names in notifications; Each collection source declares its own CDN; tab list in one place (`ui/page.py TABS`, output HTML is identical). Added new sources: 2 files instead of 9–11.

## 1.4 — 2026-10-02 (phase log and review: docs/ROADMAP.md)

**Phase A — layout and module division (no change in behavior).** Two applications are separated into Python packages with job directories, one file per responsibility (no file should be more than about 300 lines):

- `services/worker/src/trendvn_worker/`: `domain/` (pure rules: scoring, calendar, observations, captions), `store/` (SQLite: versioned schema, ingest, queue, publishing, reporting…), `ai/` (Gemini: analysis, TTS, client), `media/` (ffmpeg, fingerprint, sub theme, build), `web/` (HTTP: handler, security, form, API), `ui/` (interface: tags, each tab, static CSS/JS), `tasks.py`, `pipeline.py`.
- `services/agent/src/trendvn_agent/`: `collector/` (+ `sources/` one file per platform, add platform = add one file and one registration line), `publisher/`, `browser.py`, `server.py`.
- Runs by module (`python -m trendvn_worker`, `python -m trendvn_agent`); systemd/launchd model and `agent.sh` updated accordingly; `./trendvn update` reinstalls the agent's background service so the version running with the old layout can still be migrated.
- Versioned database (`PRAGMA user_version` + migration list); Database 1.0–1.3 is received as is.
- `tests/` divided by `worker/ agent/ tools/ e2e/`; add `./trendvn fmt` (black + ruff, pin in `requirements-dev.txt`), doclint checks every command has documentation.
**Phase B — analytics and video quality (measured on real Douyin videos).**
- The decision to maintain / Vietsub / explanation is a separate function (`domain/route.py`) with a decision table, with reasons in Vietnamese displayed on the video card.
- The hard subtitles of the original video (Chinese characters burned-in) are blurred at that strip before burning the Vietnamese subtitles (Gemini reports the location); The subtitle line is too fast to be extended into the interval after it (21 → 17 characters/second on measured video).
- `veryfast/crf 24` encoding: SSIM 0.992 compared to reference, about 40% smaller and faster. Measure the volume right during the decoding test.
- Fix bug since 1.3: absolute silent audio line caused AAC encoder to reject; Gemini voice reading unusually fast (missing sentences) is rejected.

**Phase C — topic and multiple accounts.**
- Menu 14 themes; Gemini categorizes, collects and searches by topic (Douyin: tab of each topic; TikTok: chip), chooses to download and divide between topics.
- Multiple TikTok accounts, each account gets several themes, separate day/spacing/prime time limits, separate Chrome profile (`./trendvn tiktok login --account ID`). The old version's account becomes `main`; The old database migrated automatically (tested on a real database copy of 1.2).
- Interface: "TikTok accounts and themes" section in the More tab; The video tag states the subject and account that will receive it.

**Phase D — performance.**
- Process 2 videos at the same time (`TRENDVN_PROCESS_PARALLEL`); Checking the duplicate video is atomic, so two identical copies processed at the same time are still caught.
- Vertical music video without lyrics reproduced in full image (3.3 seconds instead of 24 seconds, no quality loss, every pixel is the same as the original); wait for adaptation when scanning Douyin's topic tabs.

- Fix error found when splitting: `sys` was not imported in collector's Instagram load path; The e2e test layout flickered because the page was not at the top.

## 1.3 — 2026-09-30

Repackaged for delivery and deployment on multiple Mac/Linux machines. **Unchanged system behavior** (automatic flow, rules, interface keep original 1.2); Change folder layout and add operating tools.

- **Standard folder layout: ** `services/worker` (Docker image), `services/agent` (Chrome on device), `n8n/` (workflow generator + management tool), `scripts/`, `macos/`, `tests/`, `docs/`; All data and secrets of the device are in `data/` and `.env` (not in the packaging).
- **One command for everything: ** `./trendvn` (and `Makefile` as shortcut): `install`, `up`, `down`, `restart`, `update`, `status`, `doctor`, `logs`, `build`, `backup`, `restore`, `package`, `test`, `agent ...`, `tiktok ...`, `n8n ...`.
- **Build tool n8n:** `n8n/build.py` generates 6 workflows from code (node id is fixed so regenerating gives identical results; `--check` detects JSON file with miscode); `n8n/manage.py` loads, turns on/off schedule, exports workflow from n8n; Reloading does not turn off the active calendar.
- **Docker:** version-labeled worker image, `HEALTHCHECK`, runs read-only root filesystem, all capabilities removed, `no-new-privileges`; self-rotating container log (5 × 10 MB); n8n has healthcheck; `up --wait` wait until you are well.
- **Log:** `./trendvn logs [worker|n8n|agent|all] [-f] [-n]` collects the logs of all three components.
- **Packaging:** `./trendvn package` (Pure Python, same on Linux/macOS) checked then packaged; restore the backup keeping the correct network key/uid of the new machine.
- **`./trendvn migrate <old-directory-1.2>`**: move the running system from the 1.2 folder to the new folder with one command (backup, stop the old version, copy data and TikTok sessions, install, compare), keep the calendar and switch status intact, have a backtrack.
- Backups created by 1.2 are still recoverable. `restore` merges `.env` safely (the value of the current device always wins), check the backup before deleting anything, `backup` stops for a few seconds to copy data consistently.
- **Protect other systems on the same machine:** all change commands refuse to run if the Docker project is running from another directory (`TRENDVN_ALLOW_TAKEOVER=1` to ignore); `install` refuses to create a new n8n key when the old n8n volume is present; The background service only controls the agent of this directory.
- **Stronger settings:** check `docker compose` ≥ 2.20, Google Chrome in place Playwright finds, rejects paths with spaces/special characters and (macOS) Documents/Desktop/Downloads folders; `doctor` try opening Chrome via Playwright; The background service is generated in Python (`scripts/render_service.py`) so it does not break when there is Wayland or strange characters; Reinstall on Linux and restart the agent.
- **Python for agent must be from 3.10** (playwright and yt-dlp required; macOS only comes with 3.9): `install` manually select the latest version on your device or instruct `brew install python@3.12`; This error has existed since version 1.2 and only appears when installing on a new Mac.
- **A generic `.env` reader** (`scripts/envfile.py`, according to Compose rules: endnote, caret, empty line) for all tools; Copying `.env.example` to `.env` still generates the real secret key.
- Bug fix: password/header with Vietnamese accents caused `hmac.compare_digest` to throw error (unable to log in, 500); request log is in wrong format; N8n credential loading is no longer via root-0600 file (broken on Mac).
- **Log:** worker logs useful (startup, each API call, errors with traceback; does not log tokens, cookies or query strings); `./trendvn logs agent` collects agent.log, launchd.log, agent.out or systemd's journal, so it also shows errors when starting up.
- **Automated testing:** `./trendvn test lint` checks the generated code matching workflow, Python/shell syntax, macOS bash 3.2, shellcheck (if present), background service pattern, and `scripts/doclint.py` ensures code matching documents (commands, links, paths).

Old → new path: `worker/` → `services/worker/src/trendvn_worker/`, `agent/` → `services/agent/src/trendvn_agent/`, `runtime/` → `data/worker/`, `agent_data/` → `data/agent/`, `backups/` → `data/backups/`, `workflows/` → `n8n/workflows/`, `install.sh`/`backup.sh`/... → `./trendvn install`/`backup`/...

## 1.2 — 2026-09-30

This version adds manual buttons to the control panel (automatic scheduled flow remains completely intact) and goes through three rounds of review (look and feel, performance, bugs), one of which is conducted by an independent party.

**Adjust the interface according to feedback when using it for real (same version 1.2)**- Separate**Queue**into separate tab (lower bar has 6 items, with number of waiting videos): order to be processed, button**Process N waiting videos**, button to enable processing while off, candidate list not loaded.
- Rename tab **Needs processing**to**Needs to watch** so it doesn't get confused with "pending" videos.
- Tab **Post** when empty explain the reason (processing is off / there are N videos waiting / nothing yet) and have the correct button to continue; If you don't have a Gemini key, go to Settings.
- The status bar is no longer a horizontal scrolling row with text cut out but a three-line card; Clickable Processing Flow steps; bottom bar labels do not wrap/stick together at 320–414 px (checked with real Chrome); The results of jobs that have been completed for more than 15 minutes are no longer displayed in another tab; Each background button takes you to the correct tab where the button is located.

**Operation button on the control panel**-**▶ Getting Started:**collects new videos and processes them, ready to post. Include button**Collect new videos**, **Process waiting videos**and**Read views**. Progress is displayed directly, runs in the background, and shares the same key with the n8n schedule so there is no collision.
- **Tab Post:**list of processed videos, each video has preview, box to edit description and hashtag (count characters, check quality), button**Post now**, **Preview without posting**(with photo capture),**Save description**, **Browse for self-posting schedule**, **Skip video**. Clicking Post Now is your consent for that exact video: skip the switch, prime time, day limit; The account protection pins (one post is being posted, unconfirmed post, TikTok requires verification) still remain.

**Fix critical error found during review**
- All console form submit buttons are rejected since 1.0 (header `Referrer-Policy: no-referrer` causes Chrome to send `Origin: null`).
- Long Douyin video was rejected because Gemini added subtitles after the last minute: now standardize timelines (arrange, cut, remove redundancy) and only reject when more than half of the lines are unreliable.
- Error before clicking Post (Chrome cannot open...) used to be mistakenly counted as "clicked Post without confirmation" and blocked all posting attempts; Any errors after clicking are always "unclear" (never reposted).
- Manual post failure no longer accidentally browses videos for self-posting schedule; Videos that fail 3 times are moved to Must Watch, errors 1–2 times take a break of 1 hour to avoid blocking the queue.
- The empty box in Settings used to be ignored (deleting golden hour has no effect, deleting a threshold turns that threshold off); Too large number causes error 500.
- Post suspension threshold increased from 15 to 45 minutes (posting late is not considered broken midway).

**Security**- Open the control panel outside the machine now** requires password**(`TRENDVN_UI_PASSWORD`, prevent wrong guess after 5 times); on this machine itself there is still no need. Turn on the Auto-publish or One-touch processing with confirmation switch.**Video quality, description, hashtag**
- Horizontal and square videos are brought into a 1080×1920 vertical frame on a blurred background (4x faster); rotated video is received correctly; videos that are too large yield a maximum of 1080×1920; standard volume −14 LUFS; remove source metadata; 30 fps limit; Measure the output quality and create a preview image.
- Captions avoid TikTok's text area (the blurred strip below or above the image, or above for vertical videos).
- Prompt requires a description of a natural sentence of 40–90 characters, 3–4 hashtags without diacritics; The code filters out hashtags with platform names or clich\u00e9s, standardizes Unicode, cuts descriptions at word boundaries; If the description is short or missing, the video will be Must Watch.

**Performance (measured with 30,000 videos, 150,000 events)**- New index: console data 63 → 20 ms, whole page 22 ms, 16 KB after gzip compression; Pages no longer fully reload when just viewing progress; preview images instead of downloading the whole video.**After round 4 review: **"Return ready to post" button for the video was transferred Need to watch after 3 errors; logging never crashes a task; Collected summaries do not cut between words.**Tests:** from 82 to 150+ tests, added real browser test suite (`tests/e2e/ui_e2e.py`: layout in 7 sizes × 6 tabs and full button click flow) and HTTP server test suite.

## 1.1 — 2026-09-30

This release fixes bugs that were only exposed when running with real services (Gemini, TikTok) and is packaged for installation on other devices, including macOS.

**Fix real test detection error**
- Gemini: the default model `gemini-2.5-flash` has been discontinued by Google for new users (HTTP 404). The default is now `gemini-3.8-flash`, the old installation is automatically upgraded, when encountering 404, automatically switch to the next model and remember the model that can be used.
- Gemini overloaded (429/5xx) or timed out: try again and change model; If the error persists, re-queue the video without marking it as broken. Rejected requests do not count toward the daily limit. The error message shows Google's real reason.
- Voice: new model returns WAV file, old model returns raw PCM; now reads both and all other formats via ffmpeg.
- TikTok Studio takes 20–30 seconds to complete the upload page (previously it only took 7 seconds); Child frames destroyed while the page is being built no longer throw errors.
- TikTok sometimes shows CAPTCHA: recognized by the publisher, **does not solve or bypass CAPTCHA**, pauses posting, reports on console and phone; command `publisher.py trust` (or double click `Verify-TikTok.command`) so you can solve it yourself once and then continue automatically.

**Verified with real service in this version**
- Gemini: analyze a real Kuaishou video (classify, transcribe and translate 7 dialogues, description, hashtags, edit Vietsub) and read the voice in 15.6 seconds.
- TikTok Studio: log in, dry-run, then **post a real private test video** and confirm the post on the profile (the channel owner clearly agrees, the remaining test post is for the channel owner to delete).
- Clean install, n8n call agent, backup and restore on a separate second install.

**Honest to site**
- Remove automation hiding settings (flag `AutomationControlled`, edit User-Agent to remove "Headless"). The four sources are still readable.
- The default uploader uses **the real Chrome window** when the device has a screen (TikTok displays a verification image for hidden Chrome much thicker); `TRENDVN_PUBLISH_HEADED=0/1` to exchange. The verification image is still up to you to solve.
- Adjustable post display mode (Everyone, Friends, Only Me) for safe testing.

**Phone interface**- Navigation bar below the screen, one page per screen; table into cards; quick switch (processing, self-posting) right on the main screen; folding installation group; floating save button; 16px font size input box prevents zooming on iPhone; safe zone support (rabbit ears); Link n8n according to the address you are using.**Packaging for other machines**
- `install.sh` runs on Linux and macOS (Chrome in /Applications, launchd, `caffeinate`, `host-gateway` of Docker Desktop).
- User rights to match machine (`TRENDVN_UID/GID`), port, network range, project name can all be changed in `.env`; Load, backup, and restore workflows no longer depend on fixed container names.
- `yt-dlp` installs in a separate environment (no system installation required); `package.sh` comes in clean packaging without secrets; `CAI-DAT-MAC.md` 5-step instructions; two double-click shortcuts `Sign-in-TikTok.command`, `Verify-TikTok.command`.
- Verified clean install, n8n call agent, backup and restore on a separate second install.

## 1.0 — 2026-09-30

**Collect**
- Four real running sources: Douyin, Kuaishou (any IP), TikTok and Instagram (only if exit IP is US; refuse mislabeling).
- Select videos according to "newness": score = interaction level ÷ (age in hours)^0.6, filter videos that are too old, prioritize previously effective sources.
- Retry when site disconnects; US proxy also applies to Instagram via yt-dlp.

**Handle**
- Separate prompt (`worker/prompts.py`), has JSON forced schema, checks subject, sensitivity, hashtag, prompt version in manifest.
- Vietnamese subtitles automatically divide long sentences, with a blurred background covering the original text; Vietnamese dubbing for voice-over videos (original language reduced to 18%).
- When Gemini limit expires, re-queue instead of marking failed; Adjustable limit.

**Post**
- TikTok poster via Chrome private profile, auto-login with your own actions; `dry-run` does not click Post; confirm posts on profile; Never repost an article with unknown results.
- Happy hour, limited days, spacing, choose the highest score; Optional manual browsing.
- Read views after posting and manually adjust source weight (requires ≥ 8 posts).

**Operation**
- Rewrite dashboard: to-do, browse with video preview, performance, power, full settings, notifications, log, light/dark, available on phone.
- Notice Telegram, Discord/Slack, ntfy, with anti-spam by type.
- Six n8n workflows: 01 collect and process (3 hours), 02 post (30 minutes), 03 finalize date (23:30), 00, 10, 20.

**Packaging**
- `install.sh` one command, `uninstall.sh`, `backup.sh`, `restore.sh`, `scripts/doctor.py`, `.env.example`, fully parameterize `compose.yaml`, self-select empty Docker network range.
- Documents: README, ARCHITECTURE, DEPLOY, OPERATIONS, PROMPTS, SECURITY, API.
- 69 test.

## 0.1 — 2026-09-29

Platform: SQLite queue, deduplication, Vietsub processing, three basic n8n workflows.
