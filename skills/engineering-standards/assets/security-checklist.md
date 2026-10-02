# Security checklist (run on every PR that touches code, config, CI or dependencies)

Tick or write "n/a". Anything unticked needs a note: owner, date, why accepted. Based on OWASP Top 10:2025 / ASVS 5.0 / CWE Top 25 (2025).

## Access and identity
- [ ] Every new route/handler/job checks **authentication** and **authorization per object** (another user's id is refused); deny by default
- [ ] No ids or roles trusted from the client; tenant filter present in every query
- [ ] Sessions/tokens: secure cookie flags, rotation on login, short lifetimes, scopes minimal; OAuth uses code + PKCE, exact redirect URIs
- [ ] Passwords hashed with Argon2id (>= 19 MiB, t=2, p=1) or equivalent; MFA for admin/sensitive actions

## Input, output, injection
- [ ] All input validated at the boundary (type, length, range, allow-list); size and depth limits
- [ ] SQL parameterized; no string-built shell commands (argument arrays); no `eval`/unsafe deserialization
- [ ] Output encoded for its context (HTML/attr/JS/URL); no user text in dangerous sinks; CSP unchanged or tightened
- [ ] File uploads: content-type + extension checks, random names, outside web root, size cap
- [ ] Paths resolved and confined to an allowed root (traversal); outbound requests allow-listed (SSRF)
- [ ] State-changing requests protected against CSRF (token or SameSite + Origin check), tested in a real browser

## Secrets and data
- [ ] No secret in code, tests, fixtures, logs, images, error messages; `.env.example` updated, `.env` ignored
- [ ] New secrets are scoped, rotatable, short-lived where possible; secret scan passes
- [ ] PII minimized, not logged, encrypted at rest/in transit; retention considered
- [ ] Errors are generic to clients; details only in server logs; every error path fails closed

## Supply chain and runtime
- [ ] New/updated dependencies reviewed (maintainers, size, install scripts); lockfile updated; SCA scan clean or accepted
- [ ] CI changes keep read-only default token, SHA-pinned actions, no secrets to fork PRs
- [ ] Container: non-root numeric UID, read-only rootfs, capabilities dropped, minimal base, image scanned
- [ ] Rate limits/quotas on new expensive or sensitive endpoints; timeouts on outbound calls

## Logging and operations
- [ ] Security-relevant events logged (auth, access denied, admin actions, validation failures) without secrets
- [ ] Alerts exist for new failure modes; runbook updated
- [ ] Migration/rollback plan for any data change; backup/restore unaffected

## Tests
- [ ] Authorization test (cross-user), validation boundary test, injection payload test, unhappy-path/error-leak test added
- [ ] If an agent/LLM feature: tool allow-list, human approval for irreversible actions, untrusted-content handling tested
