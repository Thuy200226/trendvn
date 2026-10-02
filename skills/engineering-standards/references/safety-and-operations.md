# Safety and operations

## Live systems
- **Identify what is live before running anything.** `docker ps`, systemd units, ports, data folders. Learn the project/instance name that scopes shared resources (compose project, volume names).
- **Guard commands.** The front-door tool refuses mutating commands when the project's resources belong to another folder/instance (an override env var exists for the owner). An earlier incident: a clean-room restore test dropped the project name from a merged `.env`, so `down` + volume restore hit the *live* project. Every destructive test exports a unique project name explicitly and checks container IDs before and after.
- **Never deploy by hand-editing** the running system. Use the project's `update` command, which rebuilds, re-renders service units/templates, reloads workflows, restarts, and runs the doctor. If the layout changed, make `update` rewrite stale service units (an old unit pointing at a deleted file would silently break after a restart).
- A `doctor` command reports every prerequisite with the exact fix command; keep it honest (required vs advisory).
- **The machine may reboot or lose scratch space.** Services should survive (restart policies, user units); check `doctor` after a reboot; recreate dev tooling from pinned versions.

## Data and migrations
- Schema version in the database (`PRAGMA user_version` or a migrations table). Each migration runs once, in order, **in one transaction with the version bump**, reading the version under the lock; the first migration adopts unversioned databases idempotently. Test: crash mid-migration leaves no trace; two processes opening at once; a copy of a *real* old database; odd rows (NULL, malformed JSON).
- Backfill legacy rows explicitly (a later migration), instead of letting code guess ("posts without an account belong to the main account").
- Back up before risky steps; restore must keep machine-specific secrets of the target machine, and must switch schedules off so two machines never act on one account.
- Secrets live in `.env`/`data/` (mode 0600), never in git, never in the package, never in logs or API responses. Don't copy secrets into scratch dirs; if you must, delete them when done.

## Real-world side effects
- Posting, paying, emailing, deleting accounts' content, changing someone's settings: only with fresh, explicit consent for that exact action. Dry-run/rehearsal modes stop before the irreversible click. After the irreversible step, anything not verified is "unknown" and stops further automatic action until a human resolves it (never retry blindly).
- Never bypass CAPTCHAs, bot checks or login walls; detect and pause, and tell the owner what to do.
- Don't permanently delete the user's data or an old deployment yourself. Give the exact command and warn about shared volumes/images.
- Multi-account/multi-tenant: one browser profile (or credential store) per account; verify the signed-in identity matches the account *before* the irreversible step; a not-signed-in account is skipped, not counted as the item's failure, and must not starve the others.

## Reliability patterns that paid off
- Outcome vocabulary that distinguishes "not the item's fault" (deferred, signed out, challenge) from "the item failed" (counted; N strikes then park for a human).
- Leases for claims; housekeeping that frees work a crash left half-done; "release without burning an attempt" for rate limits.
- Retries with a fresh page/connection; partial results survive one failing step; waits have ceilings.
- Third-party overload is normal: treat 503/429 as "re-queue later", not as a broken item; keep a fallback model chain; do not leave jobs in limbo.
- Defensive config parsing: a typo in an env var must not crash-loop a container.

## Honest reporting (always)
End with: what changed, how it was verified (numbers), what was *not* verified and why, and the actions only the user can take. Do not claim "optimal" or "done" for things you could not test; say "implemented and tested with fakes; not run against the real X".
