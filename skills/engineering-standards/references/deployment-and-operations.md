# Deployment and operations standard (any stack)

Goal: any change reaches production through the same automated, repeatable, reversible path; the system tells you when it is unhealthy; you can recover from the worst day. Based on twelve-factor practice, SRE practice, SLSA and OpenTelemetry (see "Sources").

## 1. Build and configuration
- **Build once, promote the same artifact** through environments; no rebuilding per environment. Artifacts are immutable and versioned (SemVer + commit SHA in a label/metadata).
- **Config in the environment** (twelve-factor): same code everywhere, differences only in config; `.env.example` committed with every variable documented; secrets from a secret manager; validate config at startup and fail fast with a message that names the variable, but parse tolerant optional tunables defensively (a typo in a performance knob must not crash-loop the service).
- **Dev/prod parity**: same container image, same database engine/version, same migration path. A reproducible dev setup in one command.
- **Dependencies pinned and locked**; base images pinned (by digest for releases); build reproducibly (same input -> same bytes where practical).
- One **front door** for operators and CI (`./tool`, Makefile, task runner): install, run, test, lint, fmt, build, update, doctor, backup, restore, package. Docs list exactly these, and a doc-lint keeps them true.

## 2. CI/CD pipeline (the gate is the same locally and in CI)
Stages in order, fast first, each blocking: format/lint -> unit tests -> build -> integration tests (real database/tools in containers) -> security scans (secret scan, SCA, SAST, IaC/Dockerfile lint, image scan) -> SBOM + provenance + sign -> deploy to staging -> smoke/e2e -> promote to production. Required checks on protected branches; at least one review; no direct pushes. Secrets only in protected environments; least-privilege tokens; OIDC to cloud. Keep the pipeline under ~10 minutes for the fast gate; cache dependencies; parallelize tests. Template: `assets/ci-github-actions.yml`.

## 3. Releases
- Versioning: SemVer; a CHANGELOG entry per release (what changed for users, migrations, breaking changes); tag the commit; build the package from the tag.
- **Strategies**: rolling, blue/green or canary with automatic rollback on SLO burn; **feature flags** to decouple deploy from release (flags have owners and expiry dates); small, frequent releases beat big ones.
- **Rollback is a feature**: every release has a tested way back (previous artifact, down-migration or forward-fix plan). Practice it before you need it.
- **Database migrations**: versioned and ordered, applied by the deploy (not by hand); each migration runs in one transaction together with the version bump where the engine supports it; read the version under the lock; first migration adopts unversioned databases idempotently. Use **expand/contract** for zero downtime: add (nullable/new) -> deploy code that writes both -> backfill -> switch reads -> remove old later. Backfill legacy rows explicitly rather than letting code guess. Test on a copy of real data, with odd rows (NULL, malformed JSON), and with two processes starting at once.
- Post-deploy verification: health/readiness, a smoke test of the critical path, dashboards watched for a defined period.

## 4. Runtime
- Containers per `security-standard.md` section 3 (non-root, read-only rootfs, minimal image, limits). **Healthcheck** (liveness vs readiness), graceful shutdown (handle SIGTERM, finish in-flight work), restart policies, resource requests/limits.
- **Idempotent, retry-safe operations**: jobs use leases; crash recovery frees half-done work; "release without burning an attempt" for rate limits; retries with backoff and jitter; poison items parked for a human after N failures; classify failures as "not the item's fault" (overload, signed out, challenge) vs "the item failed".
- **Third parties fail**: timeouts, circuit breaking, fallbacks, queueing and re-queue on overload (503/429) instead of marking good work broken.
- Time: UTC internally, explicit time zones at the edges. Clocks are not trusted for ordering across machines.

## 5. Observability
- **Structured logs** (JSON or key=value) with request/trace ids, levels, no secrets or PII; one log line per significant event; log rotation or a collector.
- **Metrics** for RED/USE and business KPIs; **traces** with OpenTelemetry (traces, metrics and logs are stable across major SDKs; continuous profiling is still alpha, don't depend on it for critical production use); propagate trace context across services.
- **Alerts on symptoms** (SLO burn, error rate, latency, queue age, failed jobs), not on every cause; every alert has a runbook link and an owner; delete alerts nobody acts on.
- A `doctor`/diagnostics command that reports every prerequisite with the exact fix command and distinguishes required from advisory.

## 6. Backups, recovery and continuity
- Define **RPO/RTO**; automate backups; encrypt them; keep copies off the machine; **restore-test regularly** (an untested backup is a hope). Restore must keep machine-specific secrets of the target, and must switch schedulers/cron off so two machines never act on the same account or data.
- Keep secrets, keys and the encryption key for any encrypted volume recoverable separately from the data.
- Disaster drills for the worst realistic day: lose the machine, lose the database, leak a key.

## 7. Live systems: work without harming them
- Identify what is live before running anything: containers, services, ports, data folders, scheduled jobs, the instance/project name that scopes shared resources.
- **Guard commands**: mutating commands refuse when the resources belong to another instance/folder (override only by the owner). Destructive tests use a unique project name, ports and data folder, and check live container IDs before and after. (A real incident: a clean-room restore test lost the project name from a merged config and hit the live project.)
- Deploy with the project's own update command (rebuild, re-render service units, apply migrations, restart, doctor), never by hand-editing running systems. If paths or layout changed, make the update rewrite stale service definitions.
- The machine can reboot or lose temp space: services must come back by themselves (restart policy, user units) and `doctor` must confirm; recreate dev tooling from pinned versions.
- **External side effects** (money, email/SMS, publishing, deleting data, changing someone's settings) need explicit consent for that exact action; provide dry-run/rehearsal modes that stop before the irreversible step; after an irreversible step, anything not verified is "unknown" and halts further automatic action until a human resolves it; never retry blindly. Never bypass CAPTCHAs, bot checks or login walls: detect, pause, tell the owner.
- Never delete the user's data or an old deployment yourself: give the exact command and warn about shared volumes/images.

## 8. Cost and sustainability
Right-size, schedule non-prod to sleep, set budgets and alerts, clean old images/artifacts (watch disk space: a full disk is an outage), measure cost per unit of work next to latency.

## Sources (re-check)
The Twelve-Factor App (12factor.net), Google SRE books (SLOs, error budgets, postmortems), SLSA v1.2 (slsa.dev), OpenTelemetry docs (opentelemetry.io), GitHub Actions hardening guide, OWASP Docker and CI/CD cheat sheets, NIST SSDF.
