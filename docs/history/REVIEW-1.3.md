# Review log version 1.3 (packaged for handover)

Version 1.3 does not change system behavior; it changes the layout, packaging and operation. So the review focuses on: does the installation from the package run correctly,
Do all the commands do what the documentation says, and is there anything that could cause data loss or affect other systems on the same machine.
Three rounds: (1) static self-test, (2) dynamic self-test on a clean install, (3) three independent reviewers, each with their own perspective, reading only the code.

## Round 1 — Static screening (automated to `./trendvn test lint`)

How to do it: anything that is checked by hand once is easily damaged again, so each discovery is turned into a test that runs each time.

| Test | What to catch |
|---|---|
| `n8n/build.py --check` | The file workflow in the repo has the wrong generation code |
| Python syntax and shell, forbidden pattern for bash 3.2/BSD (macOS) | `declare -A`, `mapfile`, `sed -i`, `readlink -f`... |
| `shellcheck` (style level) | Quote error, unset variable, `cd` unchecked |
| The background service template points to the real file | **True error: ** after changing the directory, the systemd/launchd template still points to the old `agent/server.py` and `agent_data/`, so the background service will never run. The trial installation uses `--no-service` so it is not detected; Only visible when printing the sample to view. Now there is a test (tried to destroy it intentionally to make sure the test caught it) |
| `scripts/doclint.py` | Command `./trendvn …` in the documentation does not exist (catch `agent venv` present in code but missing in help), relative link broken, path/scriptname remnant of old layout |

Edited in this round in addition to the above items: 5 places in the document also record old commands/paths, error messages in the interface and agent pointing to `./trendvn tiktok trust`, check `docker compose` version ≥ 2.20 when installing, refuse to install on paths with spaces or special characters (background service cannot handle it), workers write useful logs (startup, each call API, error with traceback; does not record token, cookie, request body, query string).

## Round 2 — Dynamic testing on a clean install

Instructions: `./trendvn package` → extract into an empty folder → Docker project and private port → install for real. Repeat after each correction.

| Job | Result |
|---|---|
| `install` from packaging (build image, generate + load workflow, enable schedule) | successful, 2 containers `healthy` |
| Run `install` a second time | successfully, no data destroyed |
| Container tightened (read-only root filesystem, removed all capabilities, `no-new-privileges`, user uid) | worker still `healthy`, full panel with 6 tabs |
| `n8n deactivate / activate 01 / import / export / status` | correct; **Reloading does not turn off active calendar** |
| `agent start / status / logs / stop` (background process) | true |
| `backup --keep`, `restore` backup created by itself | correct |
| `restore` a backup copy of **1.2** real (real system data and n8n) | correct: data readable, console shows correct queue, machine's network lock remains intact |
| `restart`, `down`, `up`, `update`, `uninstall`, `uninstall --purge` | correct; `--purge` wipe `data/`, `.venv`, volume |
| `test container`: all tests in the image have ffmpeg + real video editing | 159/159 |
| `test e2e`: Real Chrome, 7 sizes × 6 tabs, all button threads | 76/76 |

### Problem during testing: I mistakenly stopped the real system for a few minutes

Step `restore` backup 1.2 first run in test folder with configuration **wrong inclusion**: `.env` taken from backup so `COMPOSE_PROJECT_NAME` of test folder is lost,
Docker returns to the default name `trendvn` — the same name as the real running 1.2 system. Command `docker compose down` and then restore volume n8n run to **real system**:
two containers deleted (about 3 minutes), volume n8n overwritten by backup at 10:45. The worker data (`runtime/`, queues, videos, keys) is outside the volume so it is not touched.
Fix now: `docker compose up -d` in folder 1.2 and reload 6 workflows; The automatic calendar is already turned off so no posts are lost or mistakes are posted.

Completely fixed (all tested, tried with a fake project `guardtest`, did not touch the real system):
1. **`guard_project`**: all commands that change (`up`, `down`, `restart`, `update`, `backup`, `restore`, `uninstall`, `n8n import/activate/deactivate`) refuses to run if this Docker project is running from **directory other than**, and clearly states how to switch or run in parallel. Can be bypassed with `TRENDVN_ALLOW_TAKEOVER=1`.
2. **Incorporate `.env` when restoring** changes to: the value of the current machine always wins; The backup only contributes the two required private keys (`N8N_ENCRYPTION_KEY`, `TRENDVN_TOKEN`) and these machine options are not set.
3. Before overwriting, `restore` clearly prints the project and volume to be overwritten.
4. All subsequent destructive tests give their own project name, and compare the real system's container code before/after (unchanged).

## Round 3 — Three independent reviewers

Three agents that only read code (cannot run Docker or services), one each: (A) shell/CLI and macOS, (B) Docker, n8n, packaging, security, (C) documentation and new user journey on Mac.
They reported a total of 38 true findings (some duplicate entries; not counting "correct" entries). All are handled, or the reason is clearly stated if not corrected. Most notably, in order of impact on your Mac installation:

| Detect | Why is it important | Treat |
|---|---|---|
| **Python 3.9 of macOS cannot install agent**: `playwright` and `yt-dlp` both require Python ≥ 3.10 (checked on PyPI), while the documentation and `install.sh` only require 3.9 | Installation on a new Mac will stop at step 3 with a confusing pip error (this error is from version 1.2) | `install` requires Python 3.10+ for the agent, manually select the latest version on the machine (`python3.13` … `python3.10`, Homebrew), instructions `brew install python@3.12`; `.venv` old Python build rebuilt; `doctor` test; lint check server engine still runs on syntax 3.9 |
| **Switching from 1.2 will cause n8n to not boot**: New installation generates a new encryption key, but the old n8n volume can only be read with the old key (tried: "Mismatching encryption keys") | Lost n8n after switching folders | `install` refuse to generate new keys while the old volume is still available; Edited transfer instructions (copy `.env` old first) |
| **Installing a broken background service on Linux using Wayland** (`sed` encountered a line break, leaving an empty service file) | Installation stopped at step 8 | Background service created in Python (`scripts/render_service.py`), with automatic test, try with Wayland/X11/none/strange character |
| **Chrome test is wrong**: receives Chromium/snap and `~/Applications`, while Playwright only uses Google Chrome in standard position | Installed "successfully" but everything in the browser is broken | `install` and `doctor` check in the right place; `doctor` try opening Chrome with Playwright |
| **Dry-run of a newbie has nothing to run**(first scan only records landmarks) and**shots are not where the documentation says** | Newbie thinks it's broken | Documents and information Last notice `install` rewritten into 5 tasks, with step to set "Destination TikTok Account" |
| **Switching devices can double post **: n8n data restore remember schedule is on | Two devices post same channel | `restore` turn off schedule in n8n data **prev when** n8n starts; Machine transfer process reorders |
| `restore` merged `.env` before checking the backup, the message "no changes" is wrong | `.env` carries a strange key, n8n doesn't come up | Check the backup first; Get the private key only when the backup has n8n data included |
| `docker compose cp` creates root file 0600 that cannot be read by user n8n; token may stay in container | Load credential corrupted on Mac (uid 501); expose token | Token goes through stdin into file 0600 created by user n8n, deleted after use; ran real workflow 00 to prove that credential can use |
| `hmac.compare_digest` throws error with accented characters | Vietnamese password cannot log in; Strange header causes 500 | Comparison by bytes in worker and agent, with test (proved broken test when reverting fix) |
| `cp .env.example .env` causes the secret to be considered "given" (end of line comment read as value); readers `.env` one each type | Empty key, n8n and agent not running | One common reader `scripts/envfile.py` according to Compose rules; secret line in example as comment; Have test |
| `--purge` delete also `data/backups`; ask for confirmation after removing service | Lost backup; Uninstall unfinished | Ask first, keep `data/backups` and `.env` |
| `logs agent` does not show error when starting (file does not exist) | Does not see the reason the agent died | Shows all available log files, or systemd journals |
| Backup and copy volume n8n while n8n is running; unfinished tgz file is still packaged | N8n backup may be corrupted | Stop n8n for a few seconds when copying, always turn it back on; delete bad files; `restore` check before deleting |
| `doctor` only checks agents from the server | Firewall blocks containers from reaching agents but still shows green | Adds checks from inside the container and how to open ports for ufw |
| macOS prevents background services from reading Documents/Desktop/Downloads; Paths with spaces/special characters corrupt the service file | Agent does not run after installation | `install` refused and just moved in `~/trendvn` |
| File of type `.env.bak` may be included in the packaging; non-renewable packaging | Secret leak; hard to compare | Eliminate all `.env*` except `.env.example`; defined packaging (same code for same sha256) |
| Documentation: 15 minute install time (actual 30–60 minutes), old Gatekeeper advice (macOS 15+), `brew` cask name change, manual n8n command missing variables, cron missing PATH, wrong wait minutes (15 → 45), workflow name, exaggerated "fully tested" claim | New user stuck or misunderstood | Fix each item; The "not tested on Mac" section correctly rewrites |

No fix (noted): `pick_subnet` only looks at the Docker network and not the VPN route (duplicate ranges only show up as an obvious Docker error when `up`; `TRENDVN_SUBNET` can be set manually).

## Final result (on final package, install into empty folder with separate project and port)

| Test | Result |
|---|---|
| `./trendvn test lint` (code matching workflow, Python/shell, bash 3.2, background service sample, code matching documentation) | OK |
| Test suite on machine / in Docker image with ffmpeg / real video editing | 167 / 167 / passed |
| True Chrome, 7 sizes × 6 tabs, all button threads | 76/76 |
| `install` from the package, turn on the calendar, workflow 00 runs for real with just loaded credential | successfully |
| `doctor`: 15 green entries (including calling agent from container, Python 3.10, test opening Chrome) | passed; The remaining gold item is the work of user |
| `backup` → `restore`: automatic calendar is turned off before n8n goes up | correct |
| `export`, `update`, `uninstall`, `uninstall --purge` | true |
| Container: read-only root filesystem, remove all capabilities, `no-new-privileges`, init | correct when running real |
| Real system (1.2) running: container code before and after every test step | remains unchanged |
| Double generated packaging | with sha256 |

## Not verified, frankly speaking

- **macOS real:** launchd, `host-gateway` of Docker Desktop, Python 3.10+ via Homebrew, file quarantine flag, Chrome path. The script only uses bash 3.2/BSD syntax (with automatic checking) but does not run on Mac yet.
- **True systemd/launchd background service:** only checks generated content and paths; Do not actually install it because it will overwrite the agent service of the running system.
- **Converting a real system from 1.2 to 1.3:** The procedure in `docs/DEPLOY.md` section 11 has been tried in part (restoring the real 1.2 backup to a clean install, blocking incorrect n8n keys) but has not been fully executed on the same running system.
- Version 1.3 has not been run for a long time with a real schedule; TikTok can display verification images at any time (the system stops posting and reporting, not exceeding).

## Round 4 — Move the running system to the new directory

The next requirement is to run everything again from the new directory. This requires stopping the running 1.2 system and replacing the machine's agent service, and **the autoauthorizer refused** that stop command when I tried running it directly; so the real system has not been touched. Instead:

1. Run `./trendvn test all` right in the new folder: lint, 167 tests on the machine, 167 tests in Docker image, real video editing, 76 real Chrome tests: **passes all**.
2. Write `./trendvn migrate <old-directory-1.2>` (one command, with backtracking) and **practice** it on an isolated copy of system 1.2 (Docker project and private port, real data from backup, a workflow on). Result (last rehearsal): backup, stop old version, copy data (remove cache, keep records), install, compare **match each state** (19 baseline, 35 candidates, 3 queued, 1 ready), two active workflows (01 and 03) are still enabled, credential n8n is usable (workflow 00 runs successfully), secret key remains the same. Real system before and after: container code remains unchanged, agent service file remains unchanged.
3. **The first drill failed, and that's the drill to catch:**This machine has `/usr/bin/python3.12` but is missing the package `venv`, so the step to create the agent's Python environment has an error**after the old version has been stopped**(the way back prints correctly but still is loss of service). Fixed two things: choosing Python must also check `venv` (system Python preferred, only conda's Python when there is no other choice), and `migrate` runs all machine condition checks (Docker, Compose, Python, Chrome)**before** when stopping anything. Rehearse on final version: pass.
4. Rehearsal of intentional use `--no-service`, so the section replaces systemd/launchd's background service `migrate` **not actually run yet**: service stop code only touches service yes `WorkingDirectory` exactly equal to the old directory; Installing new services again `scripts/agent.sh install` Checked the generated content.

