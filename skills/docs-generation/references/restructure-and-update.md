# Restructuring existing docs, and keeping them current

## Contents

1. Restructure: merge, split, shorten
2. The information-loss audit
3. Update: change-to-document map
4. Audit mode

## 1. Restructure: merge, split, shorten

The risk when you restructure is losing a fact that mattered (a warning, a number, a command's caveat) or breaking a link that something outside the docs depends on. The steps below make both visible.

1. **Inventory.** List every document (`git ls-files '*.md' '*.drawio'` plus any in other formats), with line count, audience and what links to it (`grep -rn "<name>" .` over code strings, CI files, scripts and other docs: an installer may print a path to a doc). Note the commit you start from; you will diff against it.
2. **Map every section to a home.** In the scratch directory write a table `Old file#section | New home | Action` where action is keep, merge, move to history, or drop (with the reason). Group by the standard's four jobs: what happens (FLOWS), what it is made of (TECH), how to run it (OPERATIONS), where it stands (ROADMAP). A section doing two jobs is split along those lines. Evidence (review logs, measurements, old phase plans) goes to history whole, not summarised.
3. **Take truth from the code.** When old docs disagree with each other, neither wins: check the code. Fix the number or command in the new text and write the discrepancy down; it may be a bug in the old doc or a bug in the code.
4. **Write the new set** (workflow steps 3 and 4 of SKILL.md), then move the old files with `git mv` into `docs/history/` where they are evidence, or delete where the map says drop. Do not rename a file that is linked from outside the docs without updating those links.
5. **Repair links.** Files moved one level deeper need `../../`; run the linter's link and anchor check. Add the history files to the ROADMAP intro so they are not orphaned.
6. **Leave a note about old names** inside the history file that used to be the main document (for example "phases were called X, now Y"), so a reader of old commits can translate.
7. **Run the loss audit** (section 2) before declaring it done.
8. **Separate the commit** that only restructures docs from commits that change behaviour or code, and say in the message that no behaviour changed.

Shortening without restructuring: remove adjectives, convert prose to tables, move finished-phase detail to history, delete sections that explain the code line by line (the code is the source for that), merge near-duplicate sections and keep the better sentence. Keep every warning and every number that a reader would otherwise have to rediscover.

## 2. The information-loss audit

A reviewer who is not you compares old and new. Brief them with `assets/doc-reviewer-prompt.md`, mode "information loss": they read the old documents from git (`git show <commit>:<path>`), list every concrete fact in them (numbers, defaults, commands, caveats, warnings, decisions with their reasons, links to evidence), and for each say where it is now (new document and section, or history) or that it is gone. For every gone fact decide: restore it where it belongs, or confirm the drop and note the reason in the commit message. Typical misses: a warning attached to a command, the "why" of a decision, a known limitation, a platform-specific step, an experiment that did not help.

## 3. Update: change-to-document map

Documents change in the same commit as the code, because a later "docs pass" is the one that never happens. Use this map to find every document a change touches.

| The change | Update |
|---|---|
| a state added, removed or renamed; a transition changed | FLOWS section 3 (diagram, table, guarantees) and TECH (where enforced) |
| a new automatic trigger or a changed schedule | FLOWS section 4; OPERATIONS if the owner must turn it on or off; TECH if workflow definitions are generated |
| a new button, command or manual action | FLOWS section 5 (and what it skips); OPERATIONS command reference and, if daily, daily use; the CLI help text (the linter reads it) |
| a new or changed setting, default or environment variable | OPERATIONS settings table; TECH section 9; example env file; CHANGELOG |
| a new source, tab, plugin, extension point | TECH section 3 recipe table; FLOWS only if the owner sees it |
| a new or changed interface (route, event, file format) | TECH section 5; CHANGELOG (Changed or Removed if breaking) |
| a new failure mode or alert | FLOWS section 6; OPERATIONS troubleshooting row with the message text |
| a data migration or irreversible step | CHANGELOG with a **Migration:** line; OPERATIONS update/rollback; TECH section 4 |
| a security control added or a gap found | TECH section 8 (control, or the "not covered" list) |
| a measured performance change | TECH section 7 with date and conditions; history if it is an experiment log |
| a phase finished or a decision made | ROADMAP status/open items/decisions; evidence into history |
| something was run, or could not be run | ROADMAP "Not verified" (add or remove the line) |
| install or update steps changed | OPERATIONS sections 1 and 3 and the README Start block |

After the edits: run the linter, then re-read the changed sentences as the reader of each document would. If one fact now lives in two places, delete one and link.

## 4. Audit mode

The user wants a verdict, not edits. Run the linter and the Mermaid check, run the reviewer prompt for each document (read-only, scratch directory, parallel), verify each finding yourself, and return a report: findings ranked BUG (doc says something false), GAP (code has behaviour no document mentions), RISK (doc misleads), NIT, each with the document line and the code `file:symbol` that contradicts it; what you checked with counts; what you could not check. Offer the fixes; apply them only if asked.
