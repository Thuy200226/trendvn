# The documentation standard

Why this exists: documentation fails in four predictable ways. It grows (twenty files, nobody knows which is current). It mixes audiences (an owner wading through ports to learn what a button does). It drifts (the number in the text stopped matching the constant). It flatters (everything "done", nothing said about what never ran). The set below answers each: few files, one audience each, mechanical checks, a mandatory "not verified" section.

## Contents

1. The document set in detail
2. Where each document's facts come from (where to look in a repo)
3. Adapting to the kind of project
4. Size budgets
5. Mapping to public standards
6. Anti-patterns

## 1. The document set in detail

| Document | Reader | Job | Fixed sections |
|---|---|---|---|
| README | someone who just found the repo | get them running and point them to the right document | what it is, Start (copyable commands), Documents table, Limits to know |
| FLOWS | owner, operator, new teammate, a reviewer judging behaviour | explain what happens and what the person does, with no technology | actors; whole system flow; life of the main entity; automatic flows; manual flows; when something goes wrong |
| TECH | engineer changing or reviewing the system | explain construction, reasons and extension points | components; decisions; code layout and extension points; data and concurrency; interfaces; domain-specific section; performance; security; deployment and configuration; quality gates |
| OPERATIONS | whoever installs, runs, updates, fixes | procedures that work when copied | install; daily use; update, back up, move; when something is wrong; keeping it healthy; command reference |
| ROADMAP | owner and the next agent session | state of the work, what remains, what only the owner can decide, what is unproven | status; open items; decisions for the owner; not verified; how a phase is done |
| CHANGELOG | users upgrading | what changed, what to do about it | Unreleased on top; Added / Changed / Deprecated / Removed / Fixed / Security |
| history/ | auditors | evidence behind decisions | free form, each file starts with "historical, not maintained" |

Cross-links, not copies: FLOWS names TECH for "how", TECH names FLOWS for "what", OPERATIONS names both. Section references ("TECH section 9") are fine; anchors are checked by the linter.

## 2. Where each document's facts come from

Read the code and the running tools, not old docs. The old docs are claims to verify.

| Need | Look at |
|---|---|
| actors, triggers (automatic) | scheduler or workflow definitions, cron files, queue consumers, service units, CI schedules |
| triggers (manual) | CLI help output and argument parsers, route tables, UI buttons and forms, Makefile targets |
| entity states and transitions | enums, state tables, the functions that write the status column, model/property tests |
| components and topology | compose/Kubernetes files, Dockerfiles, process entry points, port numbers in config, service templates |
| data and retention | schema and migrations, cleanup jobs, storage paths, backup scripts |
| interfaces | route registration, handler decorators, OpenAPI files, message schemas, public module exports |
| configuration | example env file, settings defaults and validators, config loaders |
| security | auth middleware, token handling, bind addresses, file permissions, CORS/Origin checks, secret scanning in CI, hardening in the image |
| performance | benchmarks, budgets in tests, recorded measurements, caches, concurrency settings |
| install and update | install scripts, package manifests, CI/CD files, release scripts, doctor/health commands |
| failures | error handling branches, alert/notification calls, retry and lease code, "unclear means stop" rules |
| intended behaviour | test names and assertions: they state what the authors meant to guarantee |

Record each fact in the scratch fact sheet as `fact | file:symbol`. A fact with no source does not go into a document.

## 3. Adapting to the kind of project

The four documents always exist; their content shifts.

| Project | FLOWS becomes | TECH emphasises | OPERATIONS emphasises |
|---|---|---|---|
| Service or pipeline with actors (the reference case) | actors, entity lifecycle, automatic and manual flows, failure table | components, decisions, concurrency, security | install, schedules, update/rollback, troubleshooting |
| Web or mobile app | user journeys and screen-to-screen flows, what each role can do, empty and error states | front/back split, state management, API, auth, performance budget | build, deploy, environments, feature flags, rollback |
| Library or SDK | the lifecycle of a typical use (configure, call, handle errors, upgrade), plain words | module map, public API, versioning and compatibility policy, extension points | install, upgrade between versions, troubleshooting common errors |
| CLI tool | the commands as a journey (first run, daily, failure) and what each changes | command structure, config files, exit codes, plugin points | install, upgrade, shell integration, troubleshooting |
| Data or ML pipeline | the data's life from source to output, quality gates, reprocessing | stages, schemas, scheduling, reproducibility, cost | running, backfills, monitoring, failure recovery |
| Infrastructure as code | what gets created and changed per environment, approvals | modules, state, naming, drift handling | plan/apply procedure, rollbacks, break-glass |

If a document would honestly be under about 30 lines, keep it anyway and short; the fixed structure is what lets a reader find things in a project they have never seen. A monorepo gets one set at the root and a short `docs/` pointer in each service that has its own operations.

## 4. Size budgets

README 60, FLOWS 200, TECH 300, OPERATIONS 200, ROADMAP 80 lines. The linter warns, it does not fail, because a budget is a pressure to cut, not a law. Exceeding it by a lot usually means the document is doing two jobs (split the job, not the file: move detail to history or delete it), or it is explaining instead of listing (convert prose to a table).

## 5. Mapping to public standards

- **Diataxis** (tutorial, how-to, reference, explanation): README start steps are the tutorial, OPERATIONS is how-to, TECH is reference plus explanation, FLOWS is explanation of behaviour.
- **C4 model**: TECH section 1 is the container level (people, systems, containers, how they talk). Add a context diagram only when external systems are many.
- **ADR**: the decisions table is an ADR log in compact form (decision, why, cost). Add "rejected alternative" when it is the thing a newcomer will propose.
- **Keep a Changelog 1.1.0 and SemVer 2.0.0** for CHANGELOG.
- **Docs as code**: documents live in the repo, change in the same pull request as the code, and are linted in CI.
- **Twelve-factor configuration**: TECH lists every environment variable with default and meaning.

Standards move: confirm a version before quoting it in a new project's documents.

## 6. Anti-patterns

- A "docs/architecture", "docs/design", "docs/overview" and "docs/internals" that all describe the same system.
- Flows documents that name the framework, the queue or the table ("the worker POSTs /api/claim"). That sentence belongs in TECH section 5.
- A TECH document that narrates the happy path in prose (that is FLOWS).
- OPERATIONS steps that say "configure the system" without the command or the dashboard path.
- Status written as adjectives ("robust", "optimized") instead of numbers and dates.
- Diagrams with more than about 15 nodes, crossing arrows, or labels that restate the arrow.
- Screenshots of text, or drawing-tool exports as the only copy of a diagram.
- A roadmap that keeps every finished phase in full; it becomes the longest, least read file.
- A "Not verified" section that is missing, or that is empty because nobody looked.
