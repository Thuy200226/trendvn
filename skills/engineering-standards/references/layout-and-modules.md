# Layout and module standard (any stack)

Goal: a reader finds where a behaviour lives in under a minute, changes it in one place, and tests it without starting the whole system. These are *properties* to achieve; the folder names below are examples to adapt (Python, TypeScript, Go, Java/Kotlin, Rust all fit). When the repo already has a convention, follow it and apply the properties inside it.

## The properties
1. **One responsibility per module, stated in its first docstring/comment line.** If you cannot say it in one sentence without "and", split it. Files rarely exceed ~250-300 lines; functions stay <= ~60 lines (investigate > 80). A long function is several named steps.
2. **Dependencies point one way.** `domain` (pure rules, no I/O) <- `adapters/infrastructure` (database, files, network, external APIs) <- `application/services` (use cases, jobs, orchestration) <- `interfaces` (HTTP/CLI/UI). Domain never imports I/O. This is the single biggest lever for testability and speed of change.
3. **Variants are data plus one file.** New provider/source/format/tab = one new module plus one registry line, never an edit through five files. A contract test asserts every variant exposes the same interface.
4. **Separate parse from fetch.** Keep `parse_*`/`validate_*`/`decide_*` pure and fixture-tested; keep fetching/writing thin.
5. **Boundaries validate; the inside trusts.** Parse and validate input at the edge into typed objects; internal code doesn't re-validate everything (and doesn't trust unparsed data).
6. **Configuration in one place**: defaults + strict validation in one module; environment parsing centralized; no scattered `os.environ`/`process.env` reads.
7. **Named constants with provenance.** A magic number becomes a constant with a comment on where it came from (a measurement, a limit, a spec) and the date.
8. **No shadowing, no wildcard imports, no cycles.** Never reuse an imported function's name for a local in the same scope; enforce cycle-free imports with a tool.
9. **Public surface is small and documented**; everything else is private (`_name`, unexported). Changing a private helper must not break any caller outside its module.
10. **Tests mirror the code layout and live outside the shipped package**; shared test helpers in one `support` module; end-to-end tests in their own folder.
11. **Docs mirror the layout**: an architecture doc answers "where does X live?" with module paths and function names; a doc-lint fails when paths or commands rot.
12. **State and secrets live in dedicated, git-ignored locations** (`data/`, `.env`); never in the package, image or repository.

## Reference shapes (pick what fits; keep the properties)

**Single service, layered (Python/TS/Go):**
```
<tool>                    one front door: install | run | test | lint | fmt | build | update | doctor | package (script or Makefile)
src/<package>/
  domain/                 pure rules: validation, scoring, scheduling, state machines, decisions (no I/O)
  store/ or repo/         persistence, one module per concern (queue, accounts, reporting, schema/migrations)
  adapters/ (ai, media, payments, mail ...)  one module per external system, thin
  api/ or web/            handlers: parse -> call use case -> respond (thin)
  ui/                     rendering (components, one file per page/tab, static assets)
  jobs/ tasks.py          orchestration as small named step functions
tests/                    mirrors src; support.py shared; e2e/ separate
docs/                     ROADMAP, ARCHITECTURE, OPERATIONS, API, SECURITY, DEPLOY, COMMANDS
scripts/                  install, backup, restore, package, doctor (shell + small scripts; shellcheck-clean)
```
**Multiple services / monorepo:** `services/<name>/` each with its own package, tests and Dockerfile; shared contracts in `contracts/` (schemas, API specs) with contract tests on both sides; shared code only in versioned internal libraries (not copy-paste); one root front door and one CI gate.
**Frontend app:** `features/<feature>/{components,hooks,api,state,types}` + `shared/`; pages thin; data-fetching separated from presentation; design tokens in one place.
**Library:** `src/` public API in one entry module, internal modules private, examples and docs tested.

## Naming and style
Names say what a thing is or does, not how; no `utils`/`helpers`/`misc` dumping grounds (name the concept); consistent casing; boring and explicit beats clever. One formatter and one linter, **pinned to exact versions**, run by one command; style arguments are settled by the tool, not by review.

## Moving code safely (restructure without behaviour change)
- Move first, change later: mechanical move (`git mv` + import rewrites), run all tests, commit; then change behaviour in a separate commit.
- Preserve public entry points and data locations, or ship a migration (an `update` command that rewrites stale service definitions; schema migrations that adopt old databases).
- **Prove equivalence independently**: an old-vs-new comparison by a reviewer who doesn't know your intent: per-function AST comparison, identical command-line arguments for every external call over a matrix of inputs, identical HTTP responses for a battery of requests, identical database rows after the same operations. Existing tests are not enough: refactors break rare branches, string-built commands, lazily imported modules and `__file__`-relative paths.
- Re-run linters that find undefined names and shadowing; read every rare branch.

## Smells that mean "split now"
A function with two reasons to change; a module imported by everything; tests that need the whole system to check one rule; a docstring that needs "and"; a switch on type repeated in many places; a config value read in five files; a shared mutable global.
