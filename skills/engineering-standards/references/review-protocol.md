# The three-review protocol (end of every phase or significant change)

## Why three, and why different
One reviewer shares the author's blind spots. Three different *kinds* of review find different bugs:
- **Static** finds what reading finds (shadowed names, wrong constants, doc drift, missing authorization).
- **Dynamic** finds what only real data and the real system reveal (a third party's actual behaviour, timing, a migration on a copy of real data, an overload).
- **Independent** finds what the author cannot see: an agent with no stake in the code, told to break it, with its own harness. In the reference project this pass found every serious bug that survived the first two (a duplicate-detection race under parallelism, one broken account starving the others, a NaN on silent audio, a "fix" that was never wired in).

## 1. Static review (you)
- Re-read the whole diff of the phase as if someone else wrote it. For each changed function check: names shadowing imports, rare branches, off-by-one, units (ms vs s), mutated shared state, exceptions a caller classifies wrongly, check-then-act races.
- Security pass with `assets/security-checklist.md`; performance pass against the budget (`performance-standard.md`).
- Run formatter, linters, type checks, shellcheck, doc-lint, secret/dependency scans and the full test suite. Verify numbers and commands in the docs against code constants and real CLIs.
- Look for functions/files that grew past the size limits; split. Fix, commit, log findings in the roadmap.

## 2. Dynamic review (you, on the real system)
- Deploy to staging/live using the project's own update command; run the real flows and compare with the measurements taken before the phase (the "before" must exist).
- Use real data: real inputs, a copy of the real database for migrations, real third-party behaviour. Exercise failure paths that really happen (overload, throttling, stalled requests, reboot) and check recovery (re-queue, retry, nothing good marked broken).
- Don't hammer a third party while testing: repeated probes can get you throttled and confound the measurement. Space runs out, interleave A/B, and call an inconclusive comparison inconclusive.

## 3. Independent review (a read-only subagent, in the background)
Launch with a self-contained prompt (`assets/reviewer-prompt-template.md`). Required ingredients:
- The exact commit range and what changed, in plain words.
- **Hard limits**: read-only on the repo; scratch directory only; must not touch live systems, ports or data; must not read secrets; must not call paid or external APIs; disk budget.
- **Tasks that run things, not just read**: a randomized model test of state machines, a fuzz matrix of external-command arguments in the real container, a concurrency stress with injected failures, a migration test on odd data, hostile inputs through every validator, escaping in generated HTML, authorization tests across tenants, old-vs-new differential comparison for refactors, docs-vs-code checks.
- A report format: findings ranked BUG / RISK / NIT with file:line, minimal reproduction, observed vs expected, and an explicit list of what was tested and found fine (with counts) so silence is informative.
Do not edit files the reviewer is reading while it runs; do harmless work (docs for another phase, measurements in scratch) or wait. If a reviewer dies (rate limit), reuse its scratch scripts and results instead of starting from zero.

## After the reviews
- Fix every BUG; for each RISK fix it or write down why it is acceptable (owner, date); NITs when cheap.
- Each fix gets a regression test; re-run the reviewer's own harness against the fix when reusable.
- Record in the roadmap: what the three reviews found, what was fixed, what stays unverified and why. Commit, then move on.

## Prompts that work
- "Try to break X. Write the harness. Report counts." beats "review X".
- Require a **minimal reproduction** for every finding; reject findings without one.
- Tell the reviewer what you are unsure about; reviewers are most useful on the author's doubts.
- Ask for what was **verified fine**, not only what is wrong.
