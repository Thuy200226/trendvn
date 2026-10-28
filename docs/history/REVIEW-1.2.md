# Review log version 1.2

> Note: this is a historical document of version 1.2; the paths in there (`worker/`, `agent/`, `runtime/`, `agent_data/`, `install.sh`...) are from the old layout. The comparison table to layout 1.3 is located at [CHANGELOG](../../CHANGELOG.md).

Goal: the interface works well on phones, is fast, doesn't cause errors, and the video quality, description, and hashtags are good enough to post. Four rounds of testing, plus tests using real services. All findings below were reproduced in code or in runtime before correction.

## Round 1 — Interface (Real Chrome, Auto)

> **Updated after real-use feedback:** queue separated into separate tabs (6 tabs), status bar into tabs, instructions when Posting tab is empty; This tester runs 6 tabs × 7 sizes and tests the bottom bar separately (labels do not wrap, do not touch each other).

Tool: `tests/ui_e2e.py` builds a real worker with sample data (with video) and a fake agent, opens real Chrome in 7 sizes (320×640, 360×740, 375×812, 414×896, 768×1024, 1280×900, 1440×900) and 6 tab. Each page is checked for: horizontal overflow, overlapping blocks (compare each pair of boxes), tags stuck together, buttons smaller than 44 px, text cut off, font size smaller than 11 px, bottom bar covering the bottom of the page. Then try the whole flow: Start, Collect, Process, Post now, Preview, Edit description, Restore, Skip video, double click, agent busy, agent off.

| # | Error found | Level | How to fix |
|---|---|---|---|
| 1 | **Any form submit button rejected** ("Local form only"): header `Referrer-Policy: no-referrer` causes Chrome to send `Origin: null` for the form on the same page. Has existed since 1.0 (previously only viewed the page, not clicked the form in the browser) | serious | `same-origin` and accepted `Origin: null` only if `Sec-Fetch-Site: same-origin`; CSRF | is still required
| 2 | Page icon blocking security policy (console error) | low | `img-src 'self' data:` |
| 3 | `.wrap` overrides bottom padding of `main`: footer sticks to bottom navbar on phones | medium | separates left/right margin from top/bottom margin |
| 4 | Clicking the menu on a wide screen causes the item title to be covered by the header bar | medium | `scroll-margin-top` |
| 5 | Refresh button 38–41 px; menu top 35 px (bottom 44 px for touch) | low | raised 44 px |
| 6 | Click Post Now to switch to the Posting tab but progress is only shown in the Overview tab: results are not visible | average | progress table is present in related tabs (Posting, Posted) |
| 7 | Posting tab lacks equal spacing between blocks | low | common spacing system `.stack` |

Final result: **58 passed test, 0 errors** (35 layouts + 23 button press threads, including no console errors).

## Round 2 — Performance (30,000 videos, 150,000 events, 100,000 observations)

| Operation | Previous | After index |
|---|---|---|
| Console data | 63 ms | **20 ms** |
| API status (collector and n8n calling continuously) | 13 ms | **8 ms** |
| Full page (data + HTML) | 66 ms | **22 ms** |
| Import 100 videos | 9 ms | 11 ms |
| Outgoing HTML | 134 KB | **16 KB** after gzip |

Other: preview video doesn't load without clicking (`preload=none` + poster image), page only asks for a small piece of HTML to update the progress (instead of reloading the whole page), blurred background built with thumbnail image then zoomed in (about 4 times faster), editing file limited to 4 Mbps (78 second video: 54 MB → 41 MB; 4K video captures 1080×1920). Another real statistic: editing a 78-second vertical video takes 36 seconds, a 36-second vertical video takes 7 seconds.

## Round 3 — Independent review of code reading (a separate, read-only agent)

Get 22 findings. All verified and corrected; Notable items:

| # | Detection | Level | Treatment |
|---|---|---|---|
| 1 | Error before clicking Post (Chrome doesn't open...) leaves post `publishing`, after 15 minutes it becomes "clicked Post not confirmed" and blocks all postings | high | `publish_one` never throws error: before clicking = `failed`, after pressing = `unknown` (with test) |
| 2 | Post failed on video waiting for approval quietly browse it for self-posting schedule | average | remember `prev_state`, restore on failure |
| 3 | One video error forever blocks the whole channel (schedule re-selects it every 30 minutes, every time opening Chrome) | average | rests for 1 hour after error, 3 times then comes in Need to watch |
| 4 | There is no button to browse videos for self-posting schedule when "hand review" is enabled | medium | add "Browse for self-posting schedule" button |
| 5 | Empty cells are ignored: deleting golden hours has no effect, deleting a threshold turns that threshold off again | average | reads all blank cells, aggregates thresholds by source |
| 6 | Open the control panel to the machine without authentication | medium | mandatory `TRENDVN_UI_PASSWORD` (HttpOnly cookie, locked after 5 failures), doctor warns |
| 7 | "Auto Post" switch turns on with one touch | medium | asks for confirmation when turned on |
| 8 | Subtitles fall into the text area of TikTok with square, 4:5, 3:4 and vertical videos | average | `caption_zone`: blurred band below or above, or above, always avoid y > 1440 |
| 10 | Video with 90° rotation flag is distorted | low | read display size |
| 11–12 | Slow background blur, video too large to zoom out, `-level` wrong | low | correct as above |
| 13 | Revisiting "possible duplicate" videos has no effect | low | skips duplicate checking when you've already browsed |
| 14 | `hashtags` crashes crashing both dashboard and posting schedule | low | protects data type, one broken line doesn't drag down entire page |
| 15–16 | Line break CRLF, Unicode combination, hashtag counter; number too large causes error 500 | low | standardize NFC/CRLF, Unicode regex, block number |
| 17 | 15-minute threshold can interrupt a slow posting | low | raised to 45 minutes (theoretical maximum of a posting is about 20 minutes) |
| 18 | If you post the same description, you will lose the video | is low | returns to you, edit the description |
| 19–20 | Empty description still posted; error creating directory for job stuck `processing` | low | on Need to see; `mkdir` in `try`, clean up suspended tasks before processing |
| 21–22 | macOS: restart services, Downloads folder, backup via file share; package missing `.env.example` | low | fix, instruction `~/trendvn`, backup in container |

The reviewer also confirmed that it is fine: atomic posting allocation (30 concurrent attempts with only 1 success), cannot post the wrong video (hash), path access protection, escapes all displayed values, parameterized SQL, ffmpeg is fine with 12 input types.

## Round 4 — Main attack fixes

I assigned a second independent agent to review the fixes, but it was interrupted midway because of the service's session limit and **did not return the report**, so this round was done by me and does not count as an independent review. Content:

| Test | Result |
|---|---|
| Upgraded from the real database of version 1.1 (backup created by `backup.sh`) | 55 intact videos, added 5 columns and table `tasks`, reopened many times without error |
| Password bypass: 14 paths (`//`, `/./`, `/%2e/`, `/login/../`, `/api/dashboard`...), `Host` wrong case/period/space/missing, title `X-Forwarded-For`/`Forwarded`, fake cookie, POST without CSRF, API without token | No entry (automatic test) |
| Error I found myself when re-reading the edit: the video was changed to "Need to watch" after 3 postings, there was no way to return to posting, and the error counter was not cleared when reviewing again | Edit: "↩ Bring back ready to post" button, counter to 0 (with test) |
| Error found when running test on read-only drive: agent logging throws error, breaking "poster never throws error" promise | Fix: logging never crashes task (with test) |
| All tests | 153 tests passed on computer, 97 tests passed in image with ffmpeg, 58 tests passed in real browser |

Recommendation: run an additional independent review when the service is ready.

## Test with real service (not emulator)

| Test | Result |
|---|---|
| Gemini: analysis of 4 real videos | Detected that Gemini made up subtitles at the end of a long video (11 lines in addition to 138 seconds) causing the video to be rejected: fixed with timestamp normalizer; 3/4 of the following runs passed; The remaining is Gemini overload (503/504), the system requeues according to the design |
| Description quality | Before: catchphrase ("...and the ending") and platform name hashtag ("tiktokgiaitri"). After editing the prompt and filter: "After taking a whole month off from work, my son still calculates for his father to pay him." #haihuoc #tieuphim #congso |
| Collect button on running console | Real run via agent: "Douyin: read 48, reached threshold 2, new 2 / Kuaishou: read 20..." |
| Preview button | Real run: Chrome opens TikTok Studio, loads test video, fills in description and 5 hashtags (TikTok recognizes, counter 97/4000), stops before Post button, photo can be opened from the panel; No posts posted |
| Video Skip Button | Real run, video changes to "rejected" |
| Button **🚀 Post now**on real channel | Get approval from the channel owner for a private test: press the button on the interface, the confirmation box correctly states "ONLY ME", Chrome posts and** confirms on the profile profile** (`.../video/7691237769196080404`), video disappeared from the list, count "Today 1/2". Then restore Public mode and delete the test record from the system; post on TikTok so the channel owner can delete |

## Remaining limit (straight talk)

- macOS: proven clean install on Linux; launchd and `host-gateway` do not run on real Macs yet.
- TikTok sometimes requires verification (CAPTCHA); The system stops and warns, but does not solve the problem for you. Frequency at 2 articles/day has not been measured long term.
- Gemini is sometimes overloaded or slow (saw 503/504 several times during testing day); The system tries again, changes models, and requeues, but processing time may be longer than usual.
- Video rotation flag is processed according to ffprobe data and has unit tests; Haven't tried with videos shot from a real phone.
- Description quality measured on 4 videos (mainly Chinese, comedy); Not measured on music videos or voiceovers.
