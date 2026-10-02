---
name: engineering-standards
description: Engineering rules for building, restructuring, reviewing or optimizing any software project - folder layout, module split, tests, review passes, performance work, safe releases and honest reporting. Use this skill whenever you start a new project or feature, restructure or refactor code, add or review tests, run a multi-phase plan, optimize speed or quality, prepare a release or deployment, or are told to "organize the code properly", "split into modules", "review it 3 times", "make it production ready" or "follow best practice" - even when the user does not name this skill. Also use it when entering an unfamiliar repository to decide how to work in it.
---

# Engineering standards

These rules were distilled from a real multi-phase project (an automation system with a worker service, a browser agent, a database and a dashboard) where each rule exists because skipping it cost something measurable: a refactor-introduced bug that no test caught, an optimization that lost data on a flaky site, a "fix" that was not needed once measured. They are strong defaults, not laws: when the repository already has a convention, follow the repository and say so; when a rule does not fit the stack, keep its intent and adapt the mechanics.

State of the art moves. Tool versions and idioms named here (black/ruff pinning, `src` layout, `PRAGMA user_version`, pytest vs unittest) are a snapshot from 2026-10. Before relying on a specific tool or flag in a new project, check that it is still current; do not copy a version number blindly.

## How to work (the loop)

1. **Read before you change.** Find the entry points, the test command, the lint command, the docs and any `AGENTS.md`/`CLAUDE.md`. Run the existing tests first so you know the baseline. If the project is live (a running service, real accounts, a real database), read `references/safety-and-operations.md` before touching anything.
2. **Plan in phases with a measurable exit.** Each phase has an objective ("render time per video", "no function over 70 lines", "N accounts post independently"), not a task list. Write it into a `docs/ROADMAP.md` (template: `assets/ROADMAP-template.md`) and keep it current: the next session or agent must be able to continue from the file alone.
3. **Measure before you optimize or "improve".** Get numbers on real data first (`references/performance-and-measurement.md`). Change only what the numbers support, and record the experiments that did not help, because the next person will otherwise repeat them.
4. **Make the change in small, verified steps.** Behaviour-preserving refactors and behaviour changes go in separate commits. Every bug you find gets a regression test that fails without the fix.
5. **Finish each phase with three reviews** (`references/review-protocol.md`): static (read it again with fresh eyes plus tooling), dynamic (run it on real data and the real system), independent (a read-only agent that is told to break it). Fix every finding or write down why not, then log the review in the roadmap. Do not start the next phase before this is done.
6. **Release honestly.** Bump the version, update the changelog and docs, build the package, and report what was *not* verified as plainly as what was.

## Layout and modules (summary; details in `references/layout-and-modules.md`)

- One responsibility per file, stated in the file's first docstring line. If you cannot say it in one sentence, split it.
- Layers that depend in one direction only: **domain** (pure rules, no I/O) -> **store/adapters** (database, files, network) -> **services/entry points** (HTTP, CLI, jobs) -> **ui**. Pure rules never import I/O; that is what makes them testable in milliseconds.
- Functions stay short (target <= 60 lines, investigate anything > 80). A long function is usually several named steps; name them.
- Adding a variant (a new source, a new platform, a new tab) is one new file plus one registry line, never an edit through five files.
- Tests mirror the code layout and live outside the shipped package; shared test helpers live in one `support` module.
- One command is the front door (`./tool`, `make`, or a CLI entry point) for install, run, test, lint, format, release. Docs list exactly those commands and a doc-lint check keeps them true.

## Quality gates (details in `references/testing-and-quality.md`)

- Formatter and linter pinned to exact versions; the check refuses to judge with a different version (formatters change style between releases).
- Tests at four levels: unit with fakes, scripted I/O (fake browser/network), real tools in a container (ffmpeg, database), real end-to-end (browser). Add randomized/model-based tests where invariants matter (money, publishing, state machines).
- Tests never write to the real data directory or the real log; anything that changes shared state gets its own isolated instance.
- Docs are code: a doc-lint step checks commands, links and paths against the repository.

## Hard rules that prevent the expensive mistakes

- Never run a destructive or state-changing test against the live system. Give tests their own project name, ports and data folder, and verify the live system's containers/processes are untouched before and after.
- Never delete the user's data or old deployments yourself; give them the exact command and the warning about shared volumes. Never perform real-world side effects (posting, paying, emailing) without consent for that exact action.
- Do not edit files that a running reviewer is reading; do not argue with a failing test by loosening it.
- A "refactor" must preserve behaviour: prove it with an independent old-vs-new comparison, not by trusting that the tests you already had are enough (they were not, once).
- If a measurement is confounded (rate limiting, a flaky third party, a loaded machine), say so and keep the proven behaviour instead of shipping the optimization.
- Report outcomes faithfully: what passed, what failed, what you could not verify and why.

## When you finish a task

Give the user: what changed and why (short), the measured effect, the commands to run, what was not verified, and the actions only they can take. Keep it plain; no victory laps.
