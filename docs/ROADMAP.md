# Roadmap

Where the project stands, what is still open, and what only the owner can decide. The evidence behind each phase (measurements, review findings, what was fixed) is in [history/PHASES-0-K.md](history/PHASES-0-K.md); older logs are [history/REVIEW-1.2.md](history/REVIEW-1.2.md), [history/REVIEW-1.3.md](history/REVIEW-1.3.md) and the measurements of the output quality, [history/QUALITY-1.6.md](history/QUALITY-1.6.md). Read this before continuing unfinished work. Detail of the retired documents that was not carried over (the voice listening-test method, the caption and tag rules, the old API notes) stays readable in git: `git show 1e911e2:docs/PROMPTS.md`, with the old API and security notes beside it in that commit's docs folder.

## Status

| Phase | Content | Status |
|---|---|---|
| 0 to I | move to the new folder, module layout, analysis and video quality, topics and several accounts, performance, content policy, security and logic reviews, output quality (1.6), several TikTok accounts, an honest dashboard | done, each with three review rounds |
| J | review of design and implementation; eight defects fixed (retention clocks, queue starvation, shared download room, CAPTCHA pause, caption check, macOS backup, Python 3.9 tests, post result recorded first) | done |
| K | workflow reliability: failed steps reported, agent job limits and overdue alert, housekeeping respects the processing lock, collector survives odd data, n8n stops phoning home | done except the open items below |
| L | documentation: four live documents with flows and technology kept apart, a rule that enforces it, and four independent read-only reviews (flows against code, technology against code, operations against scripts, information lost in the merge); every false statement they found was corrected and the lost operating knowledge restored | done |

## Open items

| Item | Why it matters | Where it comes from |
|---|---|---|
| Lock for the `tiktok` commands (K4 d) | they open the agent's Chrome profile without its browser lock; a clash counts as a failure of the video | phase K |
| Session check in the manual Update (K5) | only the schedule notices an expired TikTok session; a product choice (it costs a Chrome launch per account) | phase K |
| `macos/Install.command` runs `install` without `--no-activate`, so the schedule turns on, unlike the documented first run; `Verify-TikTok.command` passes a verification but does not settle unclear posts | a double-click install differs from the written steps | phase L review |
| Golden hours and the daily count always use Vietnam time; `TRENDVN_TZ` only moves the n8n schedule and the container clock | an owner in another time zone cannot change it | phase L review |
| Alerts are dropped silently when no notification channel is configured | "failures are reported" holds only with a channel | phase L review |
| "Post now" refuses when the account with the fewest posts has an unconfirmed post, even if another account takes the topic and is free | blocks a legitimate manual post | phase J |
| A video that needed 3 download tries is parked by its first interrupted processing (one `attempts` counter for both) | needless owner work after an update | phase J |
| A fresh video cannot be downloaded when the worker's best-100 list holds older candidates with higher frozen scores | good videos wait | phase J (frequency on a live database unknown) |
| The analysis preview and fingerprint are rebuilt on every transient retry; a claim reads the whole jobs table per account | 3 to 7.5 s of CPU per retry; 82 ms per claim at 100k videos | phase J |
| `capture()` sleeps 18 s after its last failed attempt; posting confirmation sleeps 45 s after its last check | wasted time | phase J |
| Dead code: the `observations` table is written and never read; `status()["jobs"]`; `domain/states.py` and a few unused helpers | noise | phase J |
| Several accounts (phase G, unconfirmed since): an account with many topics takes videos from specialised ones; the download backlog is global; one claim per 30-minute check caps posting (5 accounts of 4 posts want 20, post 14); all accounts share one IP and fingerprint | fairness and throughput with many accounts | phase G |
| No image vulnerability scan, SBOM or signing; the CI file has not been seen running on GitHub; no metrics endpoint | supply-chain and observability gaps | phase L review |

## Decisions for the owner

1. **Keep n8n or replace it** with a scheduler inside the worker (an estimated 60 to 100 lines that reuse the dashboard task runner). n8n costs about 2 GB of image, ~380 MiB RAM idle and a second secret store, and gives a timer and a run history. With failed steps now reported, its worst weakness is gone; decide after a few weeks of use. While jobs hang, one workflow can hold the n8n queue for about 78 minutes and delay a posting slot.
2. **Score scale across platforms.** Downloads are ranked in one pool, so Douyin (likes standing in for views) and Kuaishou (views) compete directly; a review saw best scores of 1.8M against 17.1M. Watch the downloads per platform in the agent log; a per-platform scale factor is the fix if one platform starves.

## Not verified

Nothing has run against a live system for phases J to L: no alert has been seen from a real failing schedule; agent job durations (verify and session with several accounts, a full collect) are unmeasured, so the job limits may be too tight or too loose; that n8n no longer contacts `api.n8n.io` was checked in its settings only, not by a network trace; the stricter caption check has not met TikTok's real editor. The documentation was compared with the code by four read-only reviewers, with scripts on temporary data; the install and update steps were read against the scripts, not run on a clean machine.

Standing since earlier phases (as recorded then): the AI reporting hard-subtitle boxes on real video; US sources with a real US IP and proxy; real posting from several accounts; the whole macOS path (launchd, `host-gateway`, Python through Homebrew, the quarantine flag); long runs on a live schedule. On Linux a clean install, the n8n-to-agent calls, backup and restore ran for real; the systemd and launchd units were checked statically only.

## How a phase is done

A measurable goal first. Then the change, with a test that fails when the change is removed. Then three reviews: static (read it again, lint, documents match the code), dynamic (run it on real data with before and after numbers), independent (a read-only reviewer tries to break it). Status and open items go here; the evidence goes to the history file. Nothing is called done without saying what was and was not verified.
