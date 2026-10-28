# Writing TECH.md (what it is made of, and why)

Reader: an engineer who will change, extend or review the system. They need the map, the reasons, the places where behaviour lives, and the limits. They do not need the step-by-step behaviour (FLOWS.md has it; link to it).

## Structure

| Section | Content | Form |
|---|---|---|
| 1 Components and topology | C4 container view: parts, where each runs, how they talk, trust boundaries, ports | Mermaid `flowchart LR` (about 12 nodes) + table `Component \| Runs \| Technology \| Responsibility` |
| 2 Design decisions | each decision that a newcomer might question | table `Decision \| Why \| Cost` (add "Rejected" when that is what people will propose) |
| 3 Code layout and extension points | directory tree with one line per directory; "To change X, do Y" table; "Where each rule lives" table | tree in a code block, two tables |
| 4 Data, state and concurrency | stores, schemas and migration policy, retention, locks and leases, idempotency, ordering | tables + short paragraphs |
| 5 Interfaces | every interface other parts or users call: HTTP routes, CLI, events, files, external services | one table per interface: `Method/Command \| Path \| Auth \| Purpose` |
| 6 Domain-specific | what makes this product different (AI usage and quality, rendering, payments, ...) | free but short; rename the heading to the domain |
| 7 Performance | budgets, measured numbers with date and conditions, caches, concurrency settings | table `Measure \| Value \| How measured` |
| 8 Security and privacy | assets, entry points, controls, secrets handling, what is out of scope | table `Risk \| Control \| Where enforced` |
| 9 Deployment and configuration | build, pinning, run modes, environment variables with defaults, remote access, multiple instances | table `Variable \| Default \| Meaning` |
| 10 Quality gates | test ladder and what each level catches, lint, CI, review process | list with commands |

Drop a section's content only by saying "none" and why; keep the heading so readers find the same shape everywhere.

## Rules and their reasons

- **Reason and cost beside every decision.** "Standard library only: no install step, small attack surface | hand-written helpers" lets a reader judge whether the decision still holds. A decision with no cost is advertising.
- **Code is referenced by path and symbol** (`store/queue.py`, `claim()`), never by line number or by pasted code over about 10 lines. Symbols survive edits; the linter checks that referenced paths exist and that identifiers still appear in the source.
- **Numbers have a source.** A default, limit or timeout is copied from the constant (note `file:symbol` in the fact sheet) or from a dated measurement. "About 2 GB image" is acceptable if it is measured; "fast" is not.
- **"Where each rule lives" is the most useful and the most perishable table.** It answers "where do I change when posting rules change?" with a file and function. Keep it short (the ten questions people ask) and let the linter's identifier check police it.
- **Show where each guarantee from FLOWS is enforced** (for example "one video at a time: `publish_claim` takes the lock before the state change"). This is the bridge between the two documents and the thing reviewers look for.
- **Interfaces are tables, not prose.** One row per route/command, auth stated, purpose in a phrase. Link to an OpenAPI file if one exists instead of duplicating it.
- **Security is a table of controls and where they are enforced**, plus an explicit "not covered" list (for example "no image scan yet"). Silence reads as "covered".
- **Do not narrate flows.** If you catch yourself writing "first the agent..., then the worker...", write one sentence and link `FLOWS.md` section N.
- **Pin, don't float.** Versions appear once (section 9), others refer to it.
- **One diagram of topology is enough.** Add a second only for a genuinely different view (data flow, deployment), and keep each under about 15 nodes.

## Fitting the project

- Library: section 1 is a module map; section 5 the public API with stability promises; section 9 packaging, supported versions and compatibility policy.
- Frontend: section 1 splits shell/pages/state/api layers; section 7 holds the web-vitals budgets; section 5 lists the backend contracts it depends on.
- Data pipeline: section 4 holds schemas, partitions, backfill and exactly-once rules; section 7 holds cost and throughput.
- Several services: one TECH at the root for the whole; each service README points at the section it implements.

## Checks before finishing

1. Every path in backticks exists (linter), every `symbol()` is found (linter warning to resolve or justify).
2. Every table of defaults equals the code's defaults; spot-check at least five.
3. Every guarantee in FLOWS section 3 has an enforcement note here.
4. Every extension recipe in section 3 was followed once on paper: are the named files really the only ones to touch? (The independent reviewer should try one.)
5. No sentence in TECH would still be true if the product's behaviour changed but its implementation did not (that is FLOWS' sentence).
