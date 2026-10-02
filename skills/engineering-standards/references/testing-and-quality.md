# Testing and quality standard (any stack)

Why: the expensive bugs are rarely in logic the unit tests already cover. They hide in refactors (names, argument order), rare branches (empty input, edge of a range), concurrency (two things processed at once), integration (real tools behave differently from fakes) and environments (different formatter version, rebooted machine, unreachable registry). The gates below target those.

## The ladder (use all levels the stack allows)
1. **Unit tests with fakes** for pure rules and store logic against a temporary database; hundreds run in seconds. Fake slow/external things (APIs, subprocesses, network) with small stand-ins returning realistic data.
2. **Scripted I/O**: a fake browser/page/socket/clock that replays answers at chosen times; use a **fake clock instead of sleep** to test timeouts, retries, adaptive waits and ordering deterministically.
3. **Real dependencies in a container**: run the same suite inside the runtime image or with real services (database, ffmpeg, message broker) via Testcontainers/compose; report skipped-test counts and run the skipped ones here.
4. **End-to-end** against a real browser/process for the critical flows; for UIs assert layout rules (no overlap, no horizontal scroll, tap targets >= 44 px), accessibility basics, and every button flow; wait for the page to be at rest before measuring (a flaky layout check is usually a measurement bug).

Add where invariants matter:
- **Property-based / model-based tests** for state machines (queues, payments, publishing, permissions): drive the real implementation with random operation sequences, recompute the expected result in an independent model, assert invariants after every step (never claimed twice, counters never include another tenant's data, at most one in-flight). **Mutation-check the harness** (inject a bug; confirm it is caught).
- **Fuzz/matrix tests** for anything that builds external commands or parses input: combinations of options x geometry x routes, plus degenerate values (NaN, huge ints, empty lists, range edges, unicode, very long strings).
- **Concurrency stress**: many items, 1..N workers, injected failures; assert exactly-once processing, nothing left half-done, no deadlock (use timeouts).
- **Contract tests** between services and for every plugin/variant interface.
- **Differential tests** old-vs-new for refactors; **golden/snapshot tests** for rendered output with reviewed updates.
- **Security tests** (see `security-standard.md`): authorization, injection payloads, error-path leaks, CSRF/Origin in a real browser.

## Rules
- Every bug fixed gets a **regression test that fails without the fix**, named after the failure ("a profile signed in as somebody else never posts").
- Tests are **isolated**: temp folders, unique ports/project names, no writes to real data or logs (redirect the logger in shared test support); anything that changes shared state gets its own instance.
- Tests are **deterministic**: no real sleeps, no real network (except the explicit integration tier), seeded randomness; a flaky test is a bug to fix or delete, never to retry forever.
- Assertions state **why** (test name or comment), not only expected values. Don't loosen a failing assertion to pass; decide whether the test or the code is wrong.
- Test the **unhappy paths**: timeouts, partial failures, third-party overload, corrupt/empty/huge inputs, permissions denied.
- Keep the **pyramid**: many fast unit tests, fewer integration tests, few e2e tests; the whole fast gate stays within a few minutes.
- **Coverage is a smell detector, not a goal**: look at uncovered branches in risky code; don't chase a percentage.

## Lint, format, static checks
- **Pin formatter and linter versions exactly** (style changes between releases); the check script reads the pin and *skips with a clear message* when a different version is installed instead of failing on style; provide a `fmt` command; use a project-local virtual environment/tool cache, never a system-wide tool of unknown version.
- Enable a small, high-signal lint set (undefined/unused names, syntax errors, mutable defaults, unsafe patterns) rather than a huge noisy one; type-check where the language supports it (mypy/pyright, `tsc --strict`, `go vet`); lint shell (shellcheck) and Dockerfiles (hadolint); if macOS is a target keep bash 3.2 compatibility (no associative arrays; guard empty arrays under `set -u`).
- **Docs as code**: a doc-lint verifies every CLI command is documented, links and paths exist, and old names from earlier layouts are gone (outside history files); generated artifacts have a `--check` mode that fails when the committed file differs from what the generator produces.
- Security scans belong to the same gate (see `security-standard.md` section 5).

## Hygiene when the environment misbehaves
Scratch tools in temp directories can vanish on reboot: make recreating the dev environment one command and record the pinned versions. If the network/registry is down, run container tests manually in the existing image and say so; never skip silently.
