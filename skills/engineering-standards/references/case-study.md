# Case study (optional reading): one real project, as worked examples

This file is specific to one project - a video-repost automation (a worker service in Docker, a browser agent on the host driving Chrome, a SQLite queue, a dashboard, a scheduler) built and reviewed over four phases. It exists so the general rules have concrete evidence. Do not apply its details to other projects; apply the lessons.

## Evidence for the layout rules
- Splitting two flat apps into packages (`domain/ store/ ai/ media/ web/ ui/`, `collector/sources/<one file per source>`) with one responsibility per file made later features (topics, accounts) additive. A fully behaviour-preserving restructure was verified by independent reviewers: 81 functions AST-identical, 672 render-argument combinations identical, 595 HTTP requests identical. Even so, the restructure introduced one bug the tests did not see: a local variable `shot = shot(...)` shadowed the imported `shot()` function in the publisher, which would have turned every pre-click failure into an `UnboundLocalError`. Fix: split the 88-line function into named steps and add scripted-browser tests for every branch.
- The two longest functions (98 and 88 lines) were the two places refactor risk concentrated.

## Evidence for measure-first performance
- Stage profile of a 153-second video: remote model call ~65% of time, render ~26%, preview encode, fingerprint and checks the rest. So: process 2 items at once (waiting-dominated), not micro-optimize the CPU part.
- Re-encoding a portrait H.264 clip that was already in the target format took 24 s and enlarged the file (24.8 MB from a 12.6 MB source); copying the stream took 3.3 s with decoded frames bit-identical (md5) and a 13.8 MB file. The shortcut has a strict predicate (codec, pixel format, size, rotation/flip/display matrix, frame rate, bitrate) and an integrity test.
- Encoder choice against a high-quality reference: veryfast/crf 24 gave SSIM 0.992 and was ~40% smaller and ~40% faster than fast/crf 23.
- Things measured and dropped: filter-graph variants, extra filter threads, audio-energy-based subtitle alignment (background music made the signal useless), forcing a speech model to talk faster (it silently skipped sentences: only 79% of words survived a round-trip transcription).
- A "speedup" (adaptive waits instead of fixed sleeps) was **withdrawn for one source**: the A/B was confounded because the site throttled repeated loads (0 to 98 items with either code). Kept for another source where per-category counts were measured equal.
- Concurrency introduced a race the single-thread code did not have: duplicate detection compared against fingerprints written only at the end, so two look-alike items processed together both passed. Fix: check-and-record in one transaction.

## Evidence for the security and safety rules
- Real incident: a clean-room restore test dropped the compose project name from a merged `.env` and ran `down` plus a volume restore against the **live** project. Rules that followed: guard mutating commands by project identity; every destructive test exports a unique project name and checks live container IDs before/after.
- Multi-account publishing: one account that was not signed in was always chosen first (it had never posted), burned the three best items into "needs review" and starved the healthy account. Fixes: skip accounts known to be signed out, classify "signed out" as not-the-item's-fault, put a just-failed account behind the others, and verify the signed-in identity matches the intended account **before** the irreversible step.
- An independent reviewer's randomized model test (2,300 operation sequences, ~175k operations) over the publishing state machine found 0 invariant violations and caught all four deliberately injected bugs; this is what justified trusting the multi-account scheduling.
- Never bypass bot checks: search pages showed a CAPTCHA, so the design used the site's category tabs instead.

## Evidence for the review protocol
Static review found shadowing and doc drift; dynamic review on real data found a model overload pattern (video calls failing for days while text calls worked) and a measurement confound; independent reviews found: all-zero audio making a loudness filter emit NaN (a pre-existing bug), a band at the very edge of a tiny picture producing an invalid filter, an integer too large for float, a race under parallelism, a dead "fix" never wired to its caller, and a summary line wrong when two parallel runs finished out of order. Each got a regression test.

## Operating notes from the same project
- The machine rebooted mid-work and wiped temp scratch space; services came back by themselves; recreating pinned dev tools took one command.
- Disk was nearly full for the whole project (1-2 GB free): scratch media is deleted immediately, the doctor command reports free space, and the user was given the exact command to delete the 1.1 GB old deployment rather than the agent deleting it.
- The container registry was briefly unreachable: container tests were run manually in the already-built image and this was reported.
