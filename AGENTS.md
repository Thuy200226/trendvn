# AGENTS.md - rules for all agents working in this repo

Read this file before editing anything. Users write in Vietnamese: reply in Vietnamese, clearly, without showing off.
Common standards for all projects (layout and modules, **security**, **performance and speed**, testing, CI/CD and deployment, 3-round review process) are in the skill
`engineering-standards`: version in repo at [skills/engineering-standards](skills/engineering-standards/SKILL.md), install for all projects using
`cp -r skills/engineering-standards ~/.claude/skills/`. If the skill is installed, use it; This file records only the rules specific to this repo.
AGENTS.md template reused for another project: `skills/engineering-standards/assets/AGENTS-template.md`.

Write all documentation, comments and docstrings in English. Preserve required Vietnamese runtime text with Unicode escapes.

## What is the project
TrendVN collects trending videos (Douyin, Kuaishou; TikTok, Instagram need US IP), adds Vietsub or Vietnamese voiceover using Gemini, then posts to one or more TikTok accounts via real Chrome (not using TikTok API), according to the project's own n8n schedule.
Three blocks: **worker**(Docker: queue, rules, Gemini, ffmpeg, console),**agent**(host: Chrome + Playwright, background service `trendvn-agent`),**n8n** (timer and step only).

## Command (one-stop shop: `./trendvn`)
| Job | Command |
|---|---|
| Quick (lint + unit) / full testing (add real Docker and Chrome) | `./trendvn test` / `./trendvn test all` |
| Code format | `./trendvn fmt` |
| Apply new code to running system | `./trendvn update` |
| Diagnostics | `./trendvn doctor` |
| Packaging | `./trendvn package` |
Full commands: `docs/OPERATIONS.md`. Status, open items and owner decisions: `docs/ROADMAP.md` (read before continuing unfinished work); the evidence and review log of each phase: `docs/history/PHASES-0-K.md`.

## Layout (one responsibility per file, written in the docstring line at the beginning of the file)
- `services/worker/src/trendvn_worker/`: `domain/` (pure rules, no I/O) -> `store/` (SQLite, one concern per mixin) -> `ai/`, `media/` (Gemini, ffmpeg) -> `web/`, `tasks.py`, `pipeline.py` -> `ui/` (one file per tab).
- `services/agent/src/trendvn_agent/`: `collector/` (`sources/<source>.py` + register a line in `sources/__init__.py`), `publisher/`, `browser.py`, `server.py`.
- `tests/{worker,agent,tools,e2e}` mirror code; `tests/support.py` is a common place. `docs/` is document; `data/` and `.env` are stateful and secret (never packaged or committed).
- If the function is longer than about 60 lines, separate the named step. Add new source, tab, topic = add one file and one subscription line, do not edit across five files.

## Documentation (four live documents, flows and technology kept apart)
- `docs/FLOWS.md` says **what happens** (life of a video, schedules, buttons, failures) and contains **no technology**: no tool, port, route, file or lock names. `scripts/doclint.py` fails if it does.
- `docs/TECH.md` says **what it is made of and why** (components, decisions, data, interfaces, AI, performance, security, deployment, extension). It has no step-by-step owner instructions.
- `docs/OPERATIONS.md` is the how-to (install, run, update, fix, every command); `docs/ROADMAP.md` is status, open items and owner decisions. `docs/history/` holds evidence and old logs and is never rewritten; `docs/diagrams/` holds what is not text.
- Add to an existing document before adding a file; a new live document needs a link in `README.md`. Flows and states are Mermaid blocks in the document (they must parse); a draw.io file is only a visual twin of a text section.
- One H1 per document, English, short sentences, tables for facts. A figure says what was measured, on what, and when; an estimate says it is one; what is not verified is said so.
- Change behavior and documents together, and add the entry to `CHANGELOG.md` (the packaging step needs a section for the version).
- The portable form of this standard is the skill `skills/docs-generation` (generate, restructure, update or audit documents; its linter, Mermaid check and self-test are in its `scripts/`): `cp -r skills/docs-generation ~/.claude/skills/`. `scripts/doclint.py` stays this repo's own, stricter linter.

## How it works
1. Read `docs/ROADMAP.md` (status and open items) and run `./trendvn test` to establish a baseline before making changes.
2. Each phase has a measurable goal, and ends with **3 review rounds**: static (self-readback + tools), dynamic (runs on real data and system, with before/after measurements), independent (read-only agent assigned to break code; sample prompt in skill). Correct all detections, add blocking tests, record them (status and open items in `docs/ROADMAP.md`, evidence in `docs/history/PHASES-0-K.md`) and then move on to another phase.
3. **Measure before optimizing**; change only what the measurements support and record experiments that did not help. Don't repeatedly compare with the site that is limiting you (Kuaishou): the results are noisy, keep the proven behavior.
4. Separate the "refactoring without changing behavior" commit from the commit that changes the behavior. Refactorings must be tested independently (comparing old to new), because existing tests do not catch all.
5. For each bug that is fixed, the test will fail if the fix is abandoned. Update `CHANGELOG.md` and documentation at the same time as the code; `scripts/doclint.py` (running in `./trendvn test lint`) catches miscoded documents.
6. Honest report: what has been verified (with numbers), what **has not** verified and why, what can only be done by the user.

## Quality
- Formatting and lint tools are **pinned to exact versions** in `requirements-dev.txt` (black, ruff): different versions produce different formatting. If the correct version is not available, `./trendvn test lint` will automatically ignore it with a notification; Build your own development venv (in a temporary directory, for example) with `pip install -r requirements-dev.txt` and place it at the top of `PATH`. Don't use anaconda/system black: it formats the file differently.
- Test is not logged to the real `data/` or `agent.log` (`tests/support.py` redirected log); Test changing general status (account, settings) using a separate server/database.
- Full test suite runs in Docker image (with real ffmpeg); Hosts without ffmpeg will skip some tests. If Docker Hub is not accessible, run the container step manually in an existing image and specify it.
- e2e layout measured after the page has come to rest; After adding the theme, run `./trendvn test e2e` (Real Chrome, 7 screen sizes, touch panel >= 44 px).

## Safety (required)
- The real system is running in this directory: container `trendvn-*`, background service `trendvn-agent`, ports 5680-5682, `data/`. **Never** test destructive commands (down, restore, uninstall, volume deletion) on default project; Such a test must export `COMPOSE_PROJECT_NAME` separately and check the container ID before/after. `guard_project` blocks change commands when the project is in another directory (`TRENDVN_ALLOW_TAKEOVER=1` is reserved for the owner).
- **Do not actually post to TikTok** if the user has not given explicit consent at that time; Do not delete posted articles; Never solve or avoid CAPTCHA (the system only detects, pauses, and alerts the owner). The "Auto Post" switch and turning on the n8n calendar are up to the user.
- Do not permanently delete user data or old folders: give correct command and warning (do not `docker compose down -v` in old folder because volume `trendvn_n8n_data` now belongs to this system).
- Secret (`.env`, `data/worker/gemini.key`, Chrome session in `data/agent/profiles`) does not enter git, package, log, API, or temporary directory; If you have to copy it to test it, delete it immediately.
- Database has version (`PRAGMA user_version`); The new migration runs in a transaction with the version upgraded and tested on the actual database copy.
- The review subagent must be read-only, use a temporary folder, do not touch the real system, do not call Gemini, do not open TikTok/Douyin. Don't edit the file they're reading.

## Trap encountered (do not repeat)
- Drive is always nearly full (~1-2 GB free): don't create large files, delete test videos immediately after use; `./trendvn doctor` reports.
- Gemini often returns prolonged HTTP 503 errors for video (text works): considered "re-queue", not broken video; Don't adjust `thinkingConfig`/resolution without measurement (wrong parameters ruin every call).
- `loudnorm` on all-zero audio for NaN: `silent` video no volume adjustment. Getting Gemini TTS to read quickly makes it miss sentences: keep default speed and set `MAX_CHARS_PER_SECOND`.
- Douyin search triggers CAPTCHA; Use the topic tabs of page `jingxuan` (click with `dispatch_event` because the login window blocks the mouse). Kuaishou only has one client stream and limited loop loading; waiting for adaptation is only used for Douyin.
- When changing the run entity source code (`./trendvn update`), don't forget that the agent's background services are also reinstalled; check `./trendvn doctor` afterwards. The machine can reboot and delete `/tmp`: rebuild the development tools from the pinned version.
- Multiple accounts: one Chrome profile per account (`publisher` for `main`, `publisher-<id>` for others); Must check real username before posting; Accounts that are not logged in are ignored and are not counted as video errors.

## Unverified (updated when changed)
Gemini reports hard subtitle location (video API is often overloaded), US source (needs US IP), real posting to multiple accounts, real macOS, running for a long time according to a real schedule. The full, current list is "Not verified" in `docs/ROADMAP.md`.
