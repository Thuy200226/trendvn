# Layout and module rules

## Why these rules
A reader should find where a behaviour lives in under a minute, change it in one place, and test it without starting the whole system. The structure below achieved that on a 6,000-line two-service project; it is not the only valid structure, but the *properties* are what matter.

## Reference layout (Python, adapt names to the stack)

```
tool                      single front door (shell wrapper or CLI): install | up | down | update | doctor | test | fmt | package | ...
Makefile                  shortcuts only; no logic
compose.yaml / Dockerfile runtime definition; image labelled with the version, healthcheck, read-only root fs, non-root user
VERSION  CHANGELOG.md  README.md  pyproject.toml  requirements-dev.txt
services/
  <service-a>/
    Dockerfile  requirements.txt
    src/<package_a>/
      domain/      pure rules: validation, scoring, scheduling, routing decisions. No I/O imports.
      store/       persistence, one mixin/module per concern (queue, publishing, reporting, accounts, schema)
      ai/ media/   adapters to external systems (LLM API, ffmpeg)
      web/         HTTP handlers, forms, API routes (thin: parse -> call store/domain -> respond)
      ui/          rendering (components, one file per tab/page, static assets)
      tasks.py  pipeline.py   orchestration of steps (small named step functions)
  <service-b>/src/<package_b>/
      <feature>/   e.g. collector/ with sources/<one file per source> and a registry
      <feature2>/
scripts/           install, backup, restore, package, doctor, lint helpers (shell + small python)
tests/
  <service-a>/  <service-b>/  tools/  e2e/    mirror the code; support.py holds shared fixtures
docs/              ROADMAP, ARCHITECTURE, OPERATIONS, API, COMMANDS, SECURITY, DEPLOY
data/              runtime state and secrets (never packaged, never committed)
```

## Rules

1. **One responsibility per file.** First docstring line states it. Files rarely exceed ~250 lines; when one does, find the second responsibility.
2. **Dependency direction is one way.** domain <- store/adapters <- web/tasks <- ui. If domain needs I/O, the design is wrong: pass data in, return a decision out. Example: `choose_route(kind, has_segments) -> (route, reason)` is pure and table-tested.
3. **Name the steps.** `process_one` became `_source`, `_voice_or_subtitles`, `_checked_output`, `_write_manifest`. A 98-line function and an 88-line function were the two places a refactor bug hid; short functions are reviewable.
4. **Variants are data plus one file.** A registry dict maps name -> module/function. Contract tests assert every variant exposes the same interface (e.g. every source's `scan` accepts `topics`).
5. **Pure parse, impure fetch.** For anything that talks to the outside (HTML/JSON of a site, an API), keep `parse_*` pure and unit-tested on fixtures; keep the fetching code thin.
6. **Config in one place.** Defaults + strict validation in a single module; environment variables parsed defensively (a typo must not stop the service from starting: parse with a fallback and log it).
7. **Constants have a home and a reason.** A magic number gets a named constant with a comment saying where the number came from (a measurement, a limit, a spec).
8. **No shadowing.** Never reuse the name of an imported function for a local variable in the same scope (a refactor turned `shot(...)` calls into `UnboundLocalError` by adding `shot = shot(...)` in one branch). Linters catch some cases; reading catches the rest.
9. **Data layout.** Runtime state and secrets in `data/` and `.env` only; the package/tarball excludes them; backups include a versioned schema.
10. **Docs mirror the layout.** An architecture doc lists where each decision lives ("how is a video routed?" -> `domain/route.py::choose_route`). When code moves, the doc-lint fails until the doc is fixed.

## Moving code safely (restructure without behaviour change)

- Move first, change later. Use a mechanical move (git mv + import rewrites), run all tests, commit; only then change behaviour.
- Preserve public entry points and data paths, or provide a migration (`update`/`refresh` command that rewrites service units; schema migrations that adopt old databases).
- Prove equivalence independently: an old-vs-new comparison by a reviewer that does not know what you intended (AST comparison per function, identical command-line arguments for every external call across a matrix of inputs, identical HTTP responses for a battery of requests, identical database rows).
- Search for what tests cannot see: code paths only reached on rare branches, string-built shell/ffmpeg arguments, lazily imported modules, `__file__`-relative paths that moved one directory level.

## Smells that mean "split now"
A function with two reasons to change; a module imported by everything; a helper named `utils` with unrelated content; tests that need the whole system to check one rule; a docstring that needs "and".
