# Roadmap

Where the project stands, what is still open, and what only the owner can decide. The evidence behind each phase (measurements, review findings, what was fixed) is in [history/PHASES-0-K.md](history/PHASES-0-K.md); older logs are [history/REVIEW-1.2.md](history/REVIEW-1.2.md), [history/REVIEW-1.3.md](history/REVIEW-1.3.md) and the measurements of the output quality, [history/QUALITY-1.6.md](history/QUALITY-1.6.md). Read this before continuing unfinished work.

## Status

| Phase | Content | Status |
|---|---|---|
| 0 to I | move to the new folder, module layout, analysis and video quality, topics and several accounts, performance, content policy, security and logic reviews, output quality (1.6), several TikTok accounts, an honest dashboard | done, each with three review rounds |
| J | review of design and implementation; eight defects fixed (retention clocks, queue starvation, shared download room, CAPTCHA pause, caption check, macOS backup, Python 3.9 tests, post result recorded first) | done |
| K | workflow reliability: failed steps reported, agent job limits and overdue alert, housekeeping respects the processing lock, collector survives odd data, n8n stops phoning home | done except the open items below |
| L | documentation: four live documents with flows and technology kept apart, a rule that enforces it | done (this change) |

## Open items

| Item | Why it matters | Where it comes from |
|---|---|---|
| Lock for the `tiktok` commands (K4 d) | they open the agent's Chrome profile without its browser lock; a clash counts as a failure of the video | phase K |
| Session check in the manual Update (K5) | only the schedule notices an expired TikTok session; a product choice (it costs a Chrome launch per account) | phase K |
| "Post now" refuses when the account with the fewest posts has an unconfirmed post, even if another account takes the topic and is free | blocks a legitimate manual post | phase J |
| A video that needed 3 download tries is parked by its first interrupted processing (one `attempts` counter for both) | needless owner work after an update | phase J |
| A fresh video cannot be downloaded when the worker's best-100 list holds older candidates with higher frozen scores | good videos wait | phase J (frequency on a live database unknown) |
| The analysis preview and fingerprint are rebuilt on every transient retry; a claim reads the whole jobs table per account | 3 to 7.5 s of CPU per retry; 82 ms per claim at 100k videos | phase J |
| `capture()` sleeps 18 s after its last failed attempt; posting confirmation sleeps 45 s after its last check | wasted time | phase J |
| Dead code: the `observations` table is written and never read; `status()["jobs"]`; `domain/states.py` and a few unused helpers | noise | phase J |
| No image vulnerability scan, SBOM or signing; the CI file has not been seen running on GitHub; no metrics endpoint | supply-chain and observability gaps | this review |

## Decisions for the owner

1. **Keep n8n or replace it** with a scheduler inside the worker (an estimated 60 to 100 lines that reuse the dashboard task runner). n8n costs about 2 GB of image, ~380 MiB RAM idle and a second secret store, and gives a timer and a run history. With failed steps now reported, its worst weakness is gone; decide after a few weeks of use.
2. **Score scale across platforms.** Downloads are ranked in one pool, so Douyin (likes standing in for views) and Kuaishou (views) compete directly; a review saw best scores of 1.8M against 17.1M. Watch the downloads per platform in the agent log; a per-platform scale factor is the fix if one platform starves.

## Not verified

Nothing has run against a live system for phases J to L: no alert has been seen from a real failing schedule; agent job durations (verify and session with several accounts, a full collect) are unmeasured, so the job limits may be too tight or too loose; that n8n no longer contacts `api.n8n.io` was checked in its settings only, not by a network trace; the stricter caption check has not met TikTok's real editor; the independent read-only review of phase K and L is still to do.

## How a phase is done

A measurable goal first. Then the change, with a test that fails when the change is removed. Then three reviews: static (read it again, lint, documents match the code), dynamic (run it on real data with before and after numbers), independent (a read-only reviewer tries to break it). Findings are fixed and recorded in the history file; nothing is called done without saying what was and was not verified.
