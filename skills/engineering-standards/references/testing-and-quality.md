# Testing and quality gates

## Why
Most expensive bugs in the reference project were not in logic the tests covered. They were in refactors (names, argument order), rare branches (silent audio, a band at the edge of a picture), concurrency (two duplicates processed at once) and environments (a different formatter version, a rebooted machine, an unreachable registry). The gates below target those.

## The ladder (use all four where the stack allows)
1. **Unit tests with fakes**: pure rules and store logic against a temporary database. Fast (seconds for hundreds of tests). Fake slow or external things (LLM, ffmpeg, network) with small stand-ins that return realistic data.
2. **Scripted I/O**: a fake browser/page/clock that replays answers at chosen times. This is how adaptive-wait logic, late responses, failing tabs and retry behaviour were tested deterministically. Prefer a fake clock over `sleep`.
3. **Real tools in a container**: run the same suite inside the runtime image so real ffmpeg / database / OS behaviour is exercised (a host without ffmpeg silently skipped 11 tests; the container run had 0 skipped). Include a small "real render" check on synthetic media.
4. **End-to-end in a real browser/process**: drive the real UI at several viewport sizes; assert layout rules (no overlap, no horizontal scroll, tap targets >= 44 px), and every button flow. Wait for the page to be at rest before measuring (a flaky layout check was a measurement bug, not a UI bug).

## Add on top where invariants matter
- **Model-based / randomized tests** for state machines (publishing, queues, accounts): drive the real store with random operations, recompute the expected outcome independently in a model, check invariants after every step (at most one in-flight job; a job is never claimed twice; an account's counters never include another account's posts). Mutation-check the harness (inject a bug, see it caught).
- **Fuzz the matrix** for anything that builds external commands: combinations of input geometry x options x routes (486 combinations found 3 real bugs). Include degenerate values (NaN, huge ints, empty lists, the edge of a range).
- **Concurrency stress**: many jobs, 1..N threads, injected failures; assert each job is processed once and nothing is left half-done.
- **Differential tests** for refactors: old commit vs new commit on the same inputs.

## Rules for tests
- Every bug fixed gets a regression test that fails without the fix (name it after the failure: "a profile signed in as somebody else never posts").
- Tests are isolated: temp folders, unique ports/project names, no writes to real data or logs (redirect the logger in the shared support module). A test that changes shared state (accounts, settings) gets its own server/instance.
- Assertions say why: put the reason in the test name or a comment, not only the expected value.
- Don't loosen a failing assertion to pass; find out whether the test or the code is wrong (several first-draft tests were wrong about *correct* behaviour; the diagnosis mattered).
- Skipped tests are visible: report counts, and run the skipped ones somewhere (container).

## Lint, format, docs
- **Pin tool versions exactly** (e.g. `black==X`, `ruff==Y`) in the dev requirements; the check script reads the pin and *skips with a clear message* when the installed version differs, instead of failing on style differences. Provide a `fmt` command.
- Enable a small, high-signal lint set (undefined names, unused imports, mutable defaults, syntax) rather than a huge noisy one. Add shellcheck for shell scripts and check bash 3.2 compatibility if macOS is a target (no associative arrays; guard empty arrays under `set -u`).
- **Doc-lint**: every CLI command appears in the docs; every link and path in the docs exists; old names/paths from previous layouts are rejected outside history files. This caught stale names the day after a refactor.
- Generated artifacts (workflows, configs) have a `--check` mode that fails when the committed file differs from what the generator produces.

## Test hygiene when the machine misbehaves
- Scratch tools in `/tmp` can vanish on reboot: make creating the dev venv a one-liner and note the pinned versions in the roadmap/memory.
- If the registry/network is down, run the container tests manually in the existing image rather than skipping them silently; say that you did.
