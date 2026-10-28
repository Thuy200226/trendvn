# Documentation index

Start here. Every document of the project is listed once below, grouped by what the reader wants to do. `./trendvn test lint` fails if a file in `docs/` is missing from this index, so the list cannot rot.

## Find what you need

| I want to... | Read |
|---|---|
| install on a Mac | [MAC.md](MAC.md) |
| install, update, back up, move or uninstall on any machine | [DEPLOY.md](DEPLOY.md) |
| find a command | [COMMANDS.md](COMMANDS.md) (the truth is `./trendvn help`) |
| run it day to day and fix what breaks | [OPERATIONS.md](OPERATIONS.md) |
| see what runs by itself and what the buttons do | [WORKFLOWS.md](WORKFLOWS.md) |
| understand how the parts fit and where each rule lives | [ARCHITECTURE.md](ARCHITECTURE.md) |
| change the n8n schedules | [N8N.md](N8N.md) |
| call the worker from another tool | [API.md](API.md) |
| change what Gemini is asked, or judge the output quality | [PROMPTS.md](PROMPTS.md), [QUALITY.md](QUALITY.md) |
| know the risks, secrets and limits | [SECURITY.md](SECURITY.md) |
| see what is planned, what was reviewed and what is still open | [ROADMAP.md](ROADMAP.md) |
| see what changed in each release | [../CHANGELOG.md](../CHANGELOG.md) |
| work on the code as an agent | [../AGENTS.md](../AGENTS.md) |

History, kept as written and never edited to match today's layout: [history/REVIEW-1.2.md](history/REVIEW-1.2.md), [history/REVIEW-1.3.md](history/REVIEW-1.3.md).
Diagram files: [diagrams/architecture.drawio](diagrams/architecture.drawio) (draw.io, two pages: the three blocks and the life cycle of a video).

## Layout

```
README.md  AGENTS.md  CHANGELOG.md     entry points at the root (what it is, rules for agents, what changed)
docs/README.md                         this index
docs/*.md                              one topic per file, live documents
docs/diagrams/                         diagram sources that are not text (draw.io)
docs/history/                          logs of past reviews, append-only
```

## Conventions

1. **Language.** English. Vietnamese appears only where the product shows it to the owner (quoted as such); runtime strings in code stay escaped.
2. **One topic per file, one H1 per file.** A new topic is a new file plus a row above; do not grow a file past one reader's question.
3. **Text is the source of truth, pictures are companions.** Flows and states are Mermaid blocks inside the document (GitHub draws them and an agent reads them as text). A draw.io file is for layouts that need hand placement and always has a text twin in a document.
4. **Which document decides what.**

   | Subject | Authority |
   |---|---|
   | commands | `./trendvn help`, then [COMMANDS.md](COMMANDS.md) |
   | video states and invariants | [ARCHITECTURE.md](ARCHITECTURE.md) section 2 and the tests |
   | schedules and timeouts | `n8n/build.py`, then [N8N.md](N8N.md) and [WORKFLOWS.md](WORKFLOWS.md) |
   | settings and their limits | `domain/settings.py` |
   | HTTP routes | `web/api.py`, then [API.md](API.md) |
   | what is verified and what is not | the newest section of [ROADMAP.md](ROADMAP.md) |

5. **Code and documents change together.** A change of behavior updates the document it affects and [../CHANGELOG.md](../CHANGELOG.md) in the same commit. New releases put their entry under `## <version>` (the packaging step refuses a version without one).
6. **Numbers carry their source.** A figure says what was measured, on what, and when; an estimate says it is one. Anything not verified is said to be unverified.
7. **Commands in documents are real.** `scripts/doclint.py` checks that every `./trendvn ...` exists, every relative link resolves and every file in `docs/` is in this index.
8. **History is not rewritten.** Past review logs stay as written; corrections go in the newest section of [ROADMAP.md](ROADMAP.md).
