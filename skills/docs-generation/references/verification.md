# Verifying documentation

Documents are verified three ways: mechanically (linter, Mermaid parse), by claims (specific statements checked against code), and independently (a read-only reviewer who did not write them). Do all three; each catches what the others cannot.

## Contents

1. The linter
2. The Mermaid check
3. The claims ledger
4. Running what OPERATIONS says
5. Independent review
6. Report format

## 1. The linter (`scripts/doclint.py`)

```bash
python3 skills/docs-generation/scripts/doclint.py --root . --final
```

Errors fail the run; warnings print and do not (`--strict` makes them fail). `--final` additionally turns unfilled template markers into errors.

| Rule | Level | Catches |
|---|---|---|
| required | error | a missing README, FLOWS, TECH, OPERATIONS, ROADMAP or CHANGELOG |
| links | error | relative links to files that do not exist, and `#anchors` that match no heading |
| reachable | error | a `docs/*.md` README does not link, or a nested document nothing links to |
| one-h1 | error | a document with zero or several H1 headings (code blocks excluded) |
| fences | error | an unbalanced code fence |
| flows-no-tech | error | technology terms in FLOWS.md (HTML comments excluded; add terms in config) |
| markers | warning, error with `--final` | `FILL:`, `TODO`, `TBD`, `XXX`, `lorem ipsum` left in a document |
| paths | error | a backticked path that matches no file in the repo (ignore runtime paths in config) |
| identifiers | warning | a backticked `symbol()`, `CONSTANT_NAME` or `snake_case` name absent from the source |
| commands | error | a documented `<prefix> <command>` the CLI's help does not list; a CLI command the OPERATIONS reference omits (needs config) |
| sections | warning | missing structural headings: failure table in FLOWS, security in TECH, troubleshooting in OPERATIONS, "Not verified" in ROADMAP |
| budgets | warning | a document over its line budget |
| fence-lang | warning | a code fence with no language tag (Mermaid and shell blocks should be tagged) |

Optional config at the repo root, `.doclint.json` (copy `scripts/doclint.example.json`): docs directory, CLI help command and prefix, extra technology terms, paths to ignore, line budgets, history globs. History (`docs/history/**`, CHANGELOG) is exempt from path, command and identifier rules because it describes the past on purpose.

Wire it into the project's front door so it runs with every test (`<tool> test lint`) and in CI. A project may keep its own stricter linter alongside (repo-specific rules such as "old layout names must not reappear").

## 2. The Mermaid check (`scripts/check_mermaid.py`)

```bash
python3 skills/docs-generation/scripts/check_mermaid.py --root .
```

It parses every ```` ```mermaid ```` block with the real Mermaid parser when Node.js is available. The parser and a DOM shim are installed once into a cache directory (`--install` does it; it downloads packages from npm, so say so to the user first). Without Node it falls back to a structural check (valid first line, balanced brackets and quotes, matched `subgraph`/`end`, no parentheses inside unquoted labels) and says that it is weaker. A passing parse proves syntax, not that GitHub's renderer lays it out readably: open one diagram in a browser when the document has complex ones.

## 3. The claims ledger

Pick the ten riskiest statements across the documents: numbers, defaults, limits, timeouts, ports, command names, "never"/"always" guarantees, security statements. For each, write one line in the scratch ledger: `claim | doc:line | code file:symbol | confirmed/wrong/unclear`. Resolve every wrong or unclear one before you finish. Why ten: it is enough to expose the typical drift, and few enough to do for real rather than skim.

Cheap ways to check: grep the constant; run the CLI's help; read the state-writing function; run the test whose name states the guarantee; query the schema.

## 4. Running what OPERATIONS says

At least once, follow the install and update steps as written, in a throwaway copy, a temporary directory, a container or a scratch project name, never on a running real system and never with the user's real data or accounts. The point is to find the step that assumes something the reader does not have (a tool, a folder, an order). Note anything you could not run, and why, under "Not verified".

## 5. Independent review

A reviewer who did not write the documents finds what you cannot see. `assets/doc-reviewer-prompt.md` is a ready brief with modes: flows vs code, tech vs code, operations vs scripts, information loss. Run one reviewer per document in parallel; each is read-only, works in its own scratch directory, never touches live services or secrets, and returns findings with the document line and the code evidence. Then:

1. Verify each finding yourself against the code before acting; a reviewer can misread, and a false fix is worse than none.
2. Fix the true ones in the documents, add a lint rule or a ledger line where the same class of error could recur.
3. Record in ROADMAP (or the history log) what was reviewed, how many findings, how many fixed, what was left and why.

## 6. Report format

End the work with three lists, in the user's language:

- **Verified**, with numbers: linter result, diagrams parsed, claims checked and how many were wrong, review findings and how many fixed, procedures actually run.
- **Not verified**, with the reason for each (no access, would touch a live system, needs the owner's account, needs a long run), and the same list in ROADMAP.
- **Only you can do**: decisions, runs against the real system, repository settings such as the default branch.

Never write "complete", "optimal" or "up to date" without the evidence next to it.
