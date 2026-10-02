# The three-review protocol (end of every phase)

## Why three, and why different
One reviewer shares the author's blind spots. Three different *kinds* of review find different bugs:
- **Static** finds what reading finds (shadowed names, wrong constants, doc drift).
- **Dynamic** finds what only real data and the real system reveal (a Gemini answer, a site's behaviour, timing, a migration on a real database).
- **Independent** finds what the author cannot see: an agent with no stake in the code, told to break it, with scratch space and a harness of its own.
In the reference project the independent reviews found every serious bug that survived the first two passes (a duplicate-detection race under parallelism, a starving login-less account, silent-audio NaN, a dead "fix" never wired in).

## 1. Static review (you)
- Re-read the whole diff of the phase as if someone else wrote it. Check every changed function for: names shadowing imports, rare branches, off-by-one, units (ms vs s), mutated shared dicts, new exceptions that a caller classifies wrongly.
- Run formatter, linter, shellcheck, doc-lint, full unit tests. Check docs claims against code constants (numbers in docs must match).
- Look for functions that grew past the size limit and long files; split.
- Fix, commit, note findings in the roadmap.

## 2. Dynamic review (you, on the real system)
- Deploy to the live/staging system with the project's own update command; run the real flows (collect, process, publish rehearsal, UI) and compare with the measurements taken before the phase.
- Use real data: real videos, real titles, a copy of the real database for migrations. Take a "before" number first so "after" means something.
- Exercise failure paths that really happen (API overload, site throttling, a stalled request, a reboot) and check the system recovers (re-queues, retries, does not mark good items broken).
- Do not hammer a third party while testing: repeated probes can get you throttled and confound the very measurement you are making. Space runs out, interleave A/B, and say when a comparison is inconclusive.

## 3. Independent review (a read-only subagent, in the background)
Launch with a self-contained prompt (template: `assets/reviewer-prompt-template.md`). Required ingredients:
- The exact commit range to review and what changed in plain words.
- **Hard limits**: read-only on the repo, scratch dir only, must not touch the live system/ports/data, must not read secrets, must not call paid or external APIs, disk budget.
- **Tasks that run things**, not just read: a randomized model test of the state machine, a fuzz matrix of external-command arguments in the real container, a concurrency stress with injected failures, a migration test on odd data, hostile inputs through every validator, escaping in generated HTML, differential old-vs-new comparison for refactors.
- A report format: findings ranked BUG / RISK / NIT with file:line, minimal reproduction, observed vs expected, and an explicit list of what was tested and found fine (with counts) so silence is informative.
Do not edit files the reviewer is reading while it runs; do harmless work (docs for a different phase, measurements in scratch) or wait. If a reviewer dies (rate limit), reuse its scratch scripts and results instead of starting from zero.

## After the reviews
- Fix every BUG; for each RISK either fix or write down why it is acceptable; NITs when cheap.
- Each fix gets a regression test. Re-run the reviewer's own harness against the fix when it is reusable.
- Record in the roadmap: what the three reviews found, what was fixed, what stays unverified (with the reason). Then commit and, only then, move to the next phase.

## Review prompts that work
- "Try to break X. Write the harness. Report counts." beats "review X".
- Ask for the *minimal* reproduction; refuse findings without one.
- Tell the reviewer what you are unsure about; reviewers are most useful on the author's doubts.
