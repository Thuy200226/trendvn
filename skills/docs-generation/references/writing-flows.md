# Writing FLOWS.md (what happens, and what you do)

Reader: an owner, an operator, a new teammate, a reviewer judging behaviour. They want to know what the system does and what they do, in the product's own words. Technology is a different reader's problem and lives in TECH.md. The linter fails FLOWS.md when it finds technology terms, so the split holds over time.

## Structure (keep this order and these headings' meaning)

1. **Opening and actors.** Two sentences: what this document covers and that it has no technology. Then a table `Actor | Role`: each party that acts (a schedule, a background worker, a person, an outside service seen as a party). Add the constraint of each ("decides nothing", "must ask before posting"). Three to six actors.
2. **The whole system in one flow.** One Mermaid flowchart, left to right: triggers, main steps, decision points, end. About 12 nodes. It is the picture a newcomer keeps.
3. **Life of one `<main entity>`.** A Mermaid `stateDiagram-v2` of the entity the system exists to move (a video, an order, a ticket, a build). Then a table `State | Meaning`, one row per state, same names as the code. Then **guarantees that never change**: a numbered list of invariants phrased as always/never ("only one is processed at a time", "nothing retries after the irreversible step"). Each guarantee should be backed by a test; TECH says where it is enforced.
4. **Automatic flows.** One subsection per trigger (every 3 hours, every 30 minutes, nightly). For multi-step ones, a table `Step | What happens | If it fails`. For ones with real branching, a flowchart `TD` whose decisions are the exact checks in order. End with the plain statement of what a failing step does to the next one.
5. **Manual flows.** First run (flowchart, with a sentence explaining any ordering that is not obvious). Buttons or commands table `Action | What it does | Compared with the automatic flow` (this is where readers learn which safety checks a manual action skips and which it keeps). Decisions the person can make on one entity and what each does.
6. **When something goes wrong.** Table `Situation | What the system does by itself | What you do`. Close with what never runs together (concurrency rules in plain words).

If the project has no automatic flows, replace section 4 with the typical journey; if it has no manual ones, say so in one line. Never delete a heading silently.

## No technology: how to say it

Technology terms (the linter's default list: container, docker, database engines, HTTP, API, endpoint, token, cron, framework and tool names, `/api/` routes, plus anything you add to `extra_tech_terms`) are replaced by what the reader experiences.

| Instead of | Write |
|---|---|
| "the worker POSTs /api/claim" | "the worker decides which video is next" |
| "a lease expires" | "work left half-way by a crash goes back in the queue" |
| "SQLite WAL" | "the system remembers" |
| "cron every 30 min" | "every 30 minutes" |
| "returns 409" | "you are told it is busy and nothing starts" |
| "n8n workflow" | "the schedule" |

State names, button labels and settings names are domain words, not technology: keep them exactly as the product shows them.

## Diagram rules (Mermaid)

- One idea per diagram, about 15 nodes at most; split rather than shrink the font.
- `flowchart LR` for pipelines, `flowchart TD` for decision sequences, `stateDiagram-v2` for lifecycles. Use `sequenceDiagram` only when the order between parties is the point.
- Quote every label that has spaces or punctuation: `A["Collect: find new videos"]`. Line breaks with `<br/>`. Never put `( )`, `[ ]` or `{ }` inside an unquoted label; that is the most common parse error.
- Every decision node has every outgoing edge labeled (`yes`/`no` or the condition). Every path ends in an explicit end node or state.
- Same names in the diagram, the table and the code. A diagram that disagrees with its table is a bug in one of them.
- Do not use colour as the only carrier of meaning; GitHub themes differ.
- After writing, run `scripts/check_mermaid.py`; a diagram that does not parse renders as an error box.

## Completeness check before you finish

1. Every transition the code can make appears in the state diagram (extract them from the code, diff against the diagram: the independent reviewer does this too).
2. Every trigger (schedule, button, command) appears in section 4 or 5.
3. Every place the code alerts the user appears in section 6 with what the user does.
4. Every default quoted (3 hours, 2 per day) equals the constant in the code, found by `file:symbol` in your fact sheet.
5. The linter passes with no technology terms; read the sentences once more as the owner would.

## Common failures

- Describing only the happy path. The failure table is half the value.
- Hiding the actor in passive voice ("the video is posted"): by whom, after what check?
- A manual action described without saying what it skips compared with the schedule.
- "Etc." in a list that is meant to be exhaustive. Either list all or say "the main ones" and link where the full list lives.
- Technology sneaking in through a parenthesis ("(via the API)"). Delete it; it is in TECH.
