# Security standard (any stack)

Goal: secure by default, verifiable, proportionate. Aligned with OWASP Top 10:2025, OWASP ASVS 5.0, the 2025 CWE Top 25, NIST SSDF and SLSA (see "Sources"). Use **ASVS Level 1 as the minimum for every app, Level 2 for anything holding user data or money, Level 3 for high-value targets**. Security is a property of design and process, not a late scan: do the threat model first.

## 0. Threat model in 15 minutes (before designing or reviewing)
List: **assets** (data, accounts, compute, reputation), **entry points** (HTTP routes, CLI args, files, queues, webhooks, admin tools, CI, dependencies, LLM/tool outputs), **actors** (anonymous, user, other tenant, admin, insider, compromised dependency), **abuse cases** ("user A reads user B's order", "an upload runs code", "a leaked token publishes as us", "a prompt-injected agent deletes data"). Each abuse case gets a control and a test. Keep the list in the repo (`docs/SECURITY.md`).

## 1. OWASP Top 10:2025 - what to do about each
1. **A01 Broken Access Control** (includes SSRF): deny by default; check authorization on *every* object access server-side (CWE-862/863/639); never trust ids from the client; tenant isolation in queries; block SSRF (allow-list outbound hosts, no internal ranges, no redirects to them).
2. **A02 Security Misconfiguration**: hardened defaults, no debug in prod, no default credentials, minimal exposed ports (bind to localhost unless needed), security headers (below), same config process in all environments, config reviewed as code.
3. **A03 Software Supply Chain Failures**: lockfiles committed; pinned versions (hashes where the ecosystem supports it); vulnerability scan (SCA) + secret scan in CI; SBOM generated; minimal, signed, provenance-attested artifacts (SLSA build level >= 2 target); CI actions pinned to commit SHA, read-only token, OIDC instead of stored cloud keys; review new dependencies (maintainers, size, install scripts); automated update PRs.
4. **A04 Cryptographic Failures**: TLS 1.2+ (prefer 1.3) everywhere incl. internal; HSTS; AEAD ciphers (AES-GCM, ChaCha20-Poly1305); no custom crypto; random from the OS CSPRNG; keys in a KMS/secret manager with rotation; encrypt sensitive data at rest; never log or return secrets. Passwords: **Argon2id** (OWASP minimum: 19 MiB memory, 2 iterations, parallelism 1; or equivalent m/t trade-offs), unique salt; bcrypt/scrypt only if Argon2id is unavailable.
5. **A05 Injection** (SQL CWE-89, OS command 78/77, code 94, XSS CWE-79, template, LDAP, header): parameterized queries/ORM bind variables; no shell strings (pass argument arrays, `shell=False`); contextual output encoding and a strict CSP; never `eval` input; allow-list validation of anything that reaches an interpreter.
6. **A06 Insecure Design**: threat model, abuse-case tests, rate limits and quotas by design (CWE-770), business-logic limits (money, counts, state transitions).
7. **A07 Authentication Failures**: MFA for admins and sensitive roles; passkeys/WebAuthn where possible; lockout/throttling; secure session cookies (`HttpOnly`, `Secure`, `SameSite`), session rotation on login, short idle timeouts; no credentials in URLs; password-reset flows that don't leak account existence. OAuth/OIDC per **RFC 9700**: authorization code + **PKCE** (mandatory for public clients), exact redirect-URI match, no implicit or password grants, short-lived access tokens, sender-constrained tokens where possible. JWTs: pin algorithms, validate `iss`/`aud`/`exp`, never accept `none`.
8. **A08 Software or Data Integrity Failures**: no unsafe deserialization of untrusted data (CWE-502; use data-only formats); verify signatures/checksums of updates and artifacts; protect CI/CD and release paths; integrity of config and migrations.
9. **A09 Security Logging and Alerting Failures**: log authentication events, access-control failures, input-validation failures, admin actions, with who/what/when/where; never log secrets or full PII; tamper-resistant, central; **alert** on suspicious patterns; test that alerts fire.
10. **A10 Mishandling of Exceptional Conditions**: fail closed; every error path returns a safe generic message (no stack traces, SQL, paths); no empty `catch`; timeouts and resource limits on every outbound call; handle partial failures and retries idempotently; test the unhappy paths (fuzz, fault injection).

## 2. Controls that cut across everything
- **Input**: validate type, length, range, format, allow-list at the trust boundary; reject, don't "fix"; limit body sizes, nesting depth and list lengths; validate file uploads by content and extension, store outside the web root, random names, scan; guard path traversal (CWE-22: resolve and confirm the path stays inside the allowed root).
- **Output**: encode for the sink (HTML, attribute, JS, URL, SQL, shell); JSON APIs with correct `Content-Type`; no reflected raw input.
- **CSRF** (CWE-352): anti-CSRF tokens or `SameSite` cookies plus Origin/Fetch-Metadata checks on state-changing requests; don't rely on `Referer` alone (some browsers send `Origin: null` for strict referrer policies: test real browsers, not only unit tests).
- **Headers** (web): `Content-Security-Policy` (no `unsafe-inline` where feasible; `frame-ancestors`), `Strict-Transport-Security`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, cache controls for sensitive pages; CORS allow-list, never `*` with credentials.
- **Secrets**: never in git, logs, images, test fixtures, tickets or scratch dirs; load from environment or a secret manager; files with mode 0600; `.env` in `.gitignore` with a committed `.env.example`; scan history on suspicion and **rotate** (deleting the commit is not enough); separate secrets per environment; short-lived credentials (OIDC/workload identity) over static keys.
- **Least privilege**: separate service accounts and DB roles (app role cannot DROP; read-only where reading suffices); network segmentation; admin interfaces not exposed publicly (bind localhost/VPN + auth).
- **Rate limiting and resource limits**: per IP/user/token on login, search, expensive endpoints; request timeouts; pagination caps; queue depth caps (CWE-770).
- **Data protection**: collect the minimum; classify data; encrypt at rest and in transit; retention limits; backups encrypted and restore-tested; PII out of logs; delete on request where law applies.
- **Dependencies in code**: avoid `pickle`/unsafe YAML load/`eval`; prefer maintained libraries for parsing, crypto, auth, HTML sanitizing.

## 3. Containers and runtime
Minimal base image (slim/distroless), multi-stage build, **non-root numeric UID** (e.g. 10001), **read-only root filesystem** with explicit writable tmp/data mounts, drop all Linux capabilities and add only what is needed, `no-new-privileges`, no privileged mode or host mounts of sockets, resource limits, healthcheck, image labels with version/commit, scan images (Trivy/Grype) in CI, sign (cosign/Sigstore) and verify, pin base images by digest in release builds. Template: `assets/Dockerfile.hardened`.

## 4. CI/CD hardening
Least-privilege token by default (`permissions: contents: read`; write only in the job that needs it); third-party actions/steps pinned to full commit SHA; OIDC to the cloud, no long-lived keys; separate build and deploy identities; protected branches, required reviews and status checks; secrets only in protected environments; no secrets to forked-PR workflows; SBOM and provenance generated and attached; deploy only signed artifacts built by CI. Template: `assets/ci-github-actions.yml`.

## 5. Verification (security you can prove)
- **Tests**: authorization tests ("user B cannot read/update/delete user A's X"), validation boundary tests, injection payloads on every input, error-path tests that assert no internal detail leaks, CSRF/Origin tests in a real browser.
- **Automated gates in CI**: SAST (e.g. Semgrep/CodeQL), SCA (OSV-Scanner/Dependabot/pip-audit/npm audit), secret scan (gitleaks/trufflehog), IaC and Dockerfile lint (hadolint, checkov/trivy config), container scan, DAST/ZAP on a staging build for web apps.
- **Fuzz and fault-inject** parsers and anything that builds external commands; randomized/model-based tests for state machines that move money or publish content.
- **Independent adversarial review** (`review-protocol.md`) with a harness, not a read-through.
- **Triage**: fix critical/high before release; document accepted risks with an owner and a date.

## 6. AI agents and LLM features (when present)
Everything the model reads (web pages, documents, tool results, other agents) is untrusted input and may carry instructions: never let it change permissions, call tools it was not asked to call, or exfiltrate data; give the agent least-privilege, short-lived credentials and an allow-list of tools; require human approval for irreversible or external actions (publish, pay, delete, send); log tool calls; sandbox code execution and file access; cap spend and loops; validate model output before using it (schema, ranges, allow-lists) and fail closed. Don't put secrets in prompts or repos the agent can read.

## 7. Incident readiness
Know how to rotate every secret in under an hour; have an on-call/owner list; keep audit logs; practice a restore; write blameless post-incident notes and turn each into a test or a gate.

## Sources (re-check; these evolve)
OWASP Top 10:2025 (top10.owasp.org/2025), OWASP ASVS 5.0.0 (owasp.org/www-project-application-security-verification-standard), OWASP Cheat Sheet Series (Password Storage, CSRF, XSS, Docker, REST), 2025 CWE Top 25 (cwe.mitre.org/top25), NIST SP 800-218 SSDF (Rev.1 / v1.2 draft Dec 2025), SLSA v1.2 (slsa.dev), RFC 9700 (OAuth 2.0 Security BCP), GitHub Actions security hardening docs.
