# Writing OPERATIONS, ROADMAP, README, CHANGELOG, AGENTS section, history

## OPERATIONS.md (install, run, update, fix)

Reader: whoever has to make it work or make it work again, possibly late at night. Every procedure must work when copied; the linter checks that commands exist.

Sections:

1. **Install.** A prerequisites table (`Need | Detail`: system, runtime versions, disk, accounts, with the reason for any non-obvious one). Then numbered steps. Each step is: a bold one-line goal, **one command per fenced block** (no `$` prompt, no trailing comments that are not part of the command), then one short paragraph saying what it does, what is safe to repeat, and what "good" looks like. End the section with a rehearsal (dry run) before the first real use and, if the product has a switch that makes it act on the world, say who turns it on and when.
2. **Daily use.** A table `Command | Purpose`. How to read the status display (what green means precisely). Settings table `Setting | Default` with the range if validated. Account or tenant management in two lines per task.
3. **Update, back up, move.** Backup first, then update, then a Mermaid flowchart of update and rollback with the check after each step. State plainly which changes cannot be rolled back (database migrations) and how the changelog flags them. Moving to another machine in an order that avoids two machines acting at once. Uninstall with its destructive flag explained and the data-preserving default.
4. **When something is wrong.** Table `Symptom | Likely cause | Do`, in the order people meet them. The "Do" is a command or a click path, never "check the configuration". Include the symptom wording users see (the message text), because they search for it. Add a line on how to stop the system acting at once.
5. **Keeping it healthy.** Cleanup, retention, platform quirks (sleep, linger, permissions), what to do about disk.
6. **Command reference.** Every command the front door has, one row each with arguments. The linter fails if the CLI has a command this table omits.

Rules: destructive or irreversible commands (purge, restore, delete) carry their consequence in the same sentence and the safer alternative. Never tell the reader to run something against the live system "to see what happens". Idempotence is stated ("safe to run again").

## ROADMAP.md (state, open items, decisions, not verified)

Reader: the owner deciding what next, and the next agent session continuing work. Short (80 lines): it is a dashboard, not a diary.

- **Status table** `Phase | Content | Status`. Finished phases are one row each. Their evidence (measurements, review findings, what was fixed) is moved to `docs/history/` and linked once at the top.
- **Open items** `Item | Why it matters | Where it comes from`. Only items still open; closed items leave the table.
- **Decisions for the owner**: numbered, each with the options, the cost of each and your recommendation. These are decisions the code cannot make (replace a component, accept a risk, spend money).
- **Not verified**: plain list of what has never run against the real system, what was measured only with fakes, what the independent review has not yet covered, what only the owner can do. Dates help. A "Not verified" section is never empty because nobody looked.
- **How a phase is done**: three lines (measurable goal; change with a test that fails without it; three reviews: static, dynamic with before/after numbers, independent) so a new session continues in the same discipline. Link `assets/ROADMAP-template.md` of `engineering-standards` if the repo uses it.

## README.md

60 lines. In order: one paragraph (what, for whom, what is automated, what stays manual); **Start**, copyable commands with a one-line comment each and a pointer to OPERATIONS for the reasons; **Documents** table (every `docs/*.md` plus CHANGELOG and AGENTS, one phrase each); **Limits to know** (the five facts that surprise people: single-runner rule, third-party walls, region requirements, legal responsibility, network exposure). No design, no history, no badges unless CI proves them.

## CHANGELOG.md

Keep a Changelog 1.1.0 and SemVer 2.0.0. One H1. `## [Unreleased]` on top, then `## [x.y.z] - YYYY-MM-DD`, newest first. Groups: Added, Changed, Deprecated, Removed, Fixed, Security. Write for the person upgrading: what changed in their experience and what to do. A change that needs a data migration or manual step says **Migration:** and the step, because OPERATIONS' rollback depends on it. Update the changelog in the same commit as the change; the doc-update map in `restructure-and-update.md` says what else.

## The docs section of AGENTS.md

Add a section (about ten lines) so every agent and human follows the standard: the four live documents and their jobs; flows and technology stay apart; new facts have one home; update docs in the same commit as code; run the doc linter; history is evidence not instruction. Link `skills/docs-generation` if the skill is vendored in the repo. Do not paste the whole standard into AGENTS.md.

## history/

Everything that is evidence rather than instruction: old roadmaps, review logs, measurement reports, superseded design documents, migration notes for versions nobody runs. Put a one-line banner at the top of each ("Historical: kept as evidence, not maintained; the current state is in ROADMAP.md"). Move with `git mv` so blame survives. Link every history file from ROADMAP (the linter requires that no document is orphaned). Fix relative links after moving (a file one level deeper needs `../../`).
