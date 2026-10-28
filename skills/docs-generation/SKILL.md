---
name: docs-generation
description: Generate, restructure, update or audit a project's documentation to one strict standard: four live documents (FLOWS = what happens, no technology; TECH = what it is made of and why; OPERATIONS = install, run, update, fix; ROADMAP = status, open items, what is not verified) plus README, CHANGELOG and a history folder, with Mermaid diagrams, a doc-lint that checks the text against the code, and an independent read-only review. Use whenever the user asks to write, generate, rewrite, reorganize, shorten, review or update docs, a README, a runbook, architecture or flow diagrams or a changelog, whenever a code change needs its documents updated, and whenever docs are long, duplicated, stale, or mix "what it does" with "how it is built" - even if the user never says "skill". Kích hoạt khi người dùng yêu cầu viết, gen, làm lại, sắp xếp, rút gọn, review tài liệu, vẽ sơ đồ luồng, tách flow và công nghệ, hoặc cập nhật tài liệu sau khi sửa mã.
---

# Docs generation

Produces documentation that people actually read and that stays true. It was distilled from a real project whose docs had grown to many long files that mixed behaviour with technology and drifted from the code; the rebuilt set is four short documents, each with one job, checked by a linter and a read-only reviewer. Each rule below prevents a specific failure, and the reference files give the reason with the rule so you can judge edge cases.

**Precedence.** The repository's own rules (`AGENTS.md`, `CLAUDE.md`, a documented language or layout) come first, the user's explicit words beat both. This skill fills the gaps. Reply to the user in the language they write; write the documents in the repository's documentation language (read it from `AGENTS.md`; default English) and keep any runtime text the repo wants escaped, escaped.

## The standard in one screen

| File | Answers | Never contains | Budget |
|---|---|---|---|
| `README.md` | what is it, how do I start, where is everything | design, long explanations | 60 lines |
| `docs/FLOWS.md` | what happens, step by step, and what I do | ports, tools, routes, file names, libraries | 200 |
| `docs/TECH.md` | what it is made of, why, how to extend, what is enforced where | step-by-step behaviour (link FLOWS instead) | 300 |
| `docs/OPERATIONS.md` | install, run, update, back up, fix, every command | why the design is so | 200 |
| `docs/ROADMAP.md` | status, open items, decisions for the owner, **not verified** | finished-phase detail (move it to history) | 80 |
| `CHANGELOG.md` | what changed per version (Keep a Changelog, SemVer) | design rationale | - |
| `docs/history/` | evidence: old plans, review logs, measurements | anything still needed to operate | - |

Ten rules, each with its reason:

1. **Four live documents, no more.** Every extra file is another place for a fact to rot and a reader to get lost; sections replace files.
2. **Flows and technology never share a document.** Owners and operators need behaviour; engineers need construction. Mixed text serves neither, and a linter can enforce the split mechanically.
3. **One fact, one home.** State it once, link to it elsewhere. Duplicates drift apart.
4. **Every claim traces to code, a measurement or an explicit "not verified".** Numbers, defaults, limits, commands and ports are copied from the source, never from memory or from older docs.
5. **Diagrams are Mermaid text inside the document**, small (about 15 nodes), one idea each. Text diffs, reviews and renders on GitHub; a picture file does not. A drawing tool file may exist as a twin, never as the source of truth.
6. **Short on purpose.** Tables beat paragraphs; the budgets above are enforced as warnings. If a doc outgrows its budget, move detail to `history/` or cut it.
7. **History is kept, not maintained.** Superseded material goes to `docs/history/` with a note at the top; live documents never depend on it for operation.
8. **Docs are code.** A linter checks commands, links, anchors, paths, markers and the flows/tech split, in the same gate as the tests.
9. **Honest status.** `ROADMAP.md` has a "Not verified" section that says plainly what was never run against the real system. "Optimal", "secure", "done" need evidence or are not written.
10. **Plain words, active voice, one reader.** Say who does what ("the agent downloads", "you press"). Avoid "etc.", "simply", "just", and passive sentences that hide the actor.

## Choose the mode

| The user wants... | Mode | Read |
|---|---|---|
| docs for a project that has none, or a fresh set | **Generate** | the workflow below |
| to tidy, shorten, merge or split existing docs | **Restructure** | `references/restructure-and-update.md` first, then the workflow |
| docs brought up to date with a code change | **Update** | `references/restructure-and-update.md` (change-to-document map) |
| to know whether the docs are good or true | **Audit** | `references/verification.md`; report, do not edit unless asked |

## Workflow (Generate; the other modes reuse it)

1. **Read the repo's rules and baseline.** `AGENTS.md`/`CLAUDE.md`, existing docs (as claims to verify, not as truth), the front-door command, and run the project's fast tests so you know what was green before you touched anything.
2. **Discover, into a fact sheet in a scratch directory** (never in the repo). Read the code, not the old docs. Capture: actors and who triggers what; the main entities and their states (read the enum or the transition code); automatic triggers (cron, schedulers, workflows, queues) and manual ones (buttons, CLI, endpoints); components and where they run; data stores and retention; interfaces; configuration with defaults; security boundaries; deployment and update path; the CLI's real commands; known failure paths and what the system does about each; what tests exist (they state intended behaviour). `references/standard.md` lists where to look for each.
3. **Scaffold.** `python3 scripts/scaffold.py <repo> --name <Project>` writes the skeletons from `assets/templates/` without overwriting anything; add `--install-lint` to copy the linter into the repo's `scripts/`. Skeletons carry `<!-- FILL: ... -->` markers; the linter fails a final run while any remain.
4. **Write in this order**, reading the matching guide before each: `FLOWS.md` (`references/writing-flows.md`), `TECH.md` (`references/writing-tech.md`), then `OPERATIONS.md`, `ROADMAP.md`, `README.md`, `CHANGELOG.md` and the docs section of `AGENTS.md` (`references/writing-ops.md`). FLOWS first because it fixes the vocabulary (state and actor names) the others reuse.
5. **Verify.** Run the linter (`python3 scripts/doclint.py --final`), the Mermaid check (`python3 scripts/check_mermaid.py`), and the claims ledger (`references/verification.md`): the ten riskiest claims, each checked against code with `file:symbol`. Fix, rerun until clean. Wire the linter into the project's front door (`<tool> test lint`) so it runs with every change.
6. **Independent review.** Spawn a read-only reviewer from `assets/doc-reviewer-prompt.md` (one per document is best: flows vs code, tech vs code, operations vs scripts, and an information-loss audit when you merged old docs). It works in a scratch directory and edits nothing. Verify each finding against the code yourself before you fix it; reviewers are sometimes wrong.
7. **Report faithfully**: what was verified (with numbers: lint result, diagrams parsed, claims checked, findings fixed), what was **not** verified and why, and what only the user can do (for example decisions, real-system runs). Put the same "not verified" list in `ROADMAP.md`.

## Writing habits that make the standard work

- **Name things exactly as the code and the product do.** State names, button labels and setting names are the shared vocabulary; a doc that renames them forces readers to translate, and the linter's identifier check can then no longer find them.
- **Reference code by path and symbol (`store/queue.py`, `claim()`), never by line number.** Lines move; symbols mostly do not, and the linter can check that they still exist.
- **Put every command in its own fenced block**, no `$` prompt, one command per block, so a tool can offer a Run button and a person can copy it. Mark destructive commands with their consequence and the safer alternative.
- **Give the reason beside the rule** (decision | why | cost). A decision without its cost reads as marketing and cannot be revisited honestly.
- **Cut before you add.** For each paragraph ask which reader needs it and where it already lives. Move, link or delete.
- **Never invent.** If the code does not say, write "not documented in the code" in the fact sheet, ask the user, or list it under Not verified. A confident wrong sentence costs more than a gap.
- **Defects you find while reading are findings, not edits.** Documenting is not the moment to change behaviour. Describe what the code really does in FLOWS and TECH (not what it should do), record each defect under ROADMAP "Open items" with its `file:symbol`, and tell the user. A stale claim in an old README is the same kind of finding: replace it with what the code does and say so.

## Read when

| You need | File |
|---|---|
| the full standard, adaptations by project type, where to look in a repo, sources | `references/standard.md` |
| to write or review `FLOWS.md` | `references/writing-flows.md` |
| to write or review `TECH.md` | `references/writing-tech.md` |
| to write OPERATIONS, ROADMAP, README, CHANGELOG, history | `references/writing-ops.md` |
| to merge, split, shorten or update existing docs | `references/restructure-and-update.md` |
| lint rules, Mermaid check, claims ledger, review prompt, report format | `references/verification.md` |

Scripts (Python 3.8+, standard library only): `scaffold.py`, `doclint.py` (with `doclint.example.json` for the optional config), `check_mermaid.py`.
