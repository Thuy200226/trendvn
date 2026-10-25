# Command reference

Everything runs through **`./trendvn <l\u1ec7nh>`** (in the project directory). `make <l\u1ec7nh>` calls the correct command. `./trendvn help` prints this table briefly.
The right column is the equivalent Docker/system command, so you know what's underneath and can do it by hand if needed.

## Installation and lifecycle

| Command | Job | Equivalent to |
|---|---|---|
| `./trendvn install [--no-activate] [--no-service]` | Install for the first time, run again safely: check conditions → create `.env` and secret → `.venv` for agent → generate workflow → build + run container → load → turn on schedule → install agent service → `doctor` | (8 steps, see `scripts/install.sh`) |
| `./trendvn up` | Build image if changed, run n8n + worker, **wait until both are healthy** | `docker compose up -d --build --wait` |
| `./trendvn down` | Stop container, hold data | `docker compose down` |
| `./trendvn restart [worker\|n8n\|agent]` | Restart a component (leave blank = all three) | `docker compose restart …` / `systemctl --user restart trendvn-agent` / `launchctl kickstart -k …` |
| `./trendvn update` | Apply the new version after changing the code: regenerate workflow → build + run container again (then delete old images of this same project, including previous releases, ~570 MB each; docker refuses to delete images in use) → load workflow (the calendar is still on) → update package Agent Python → restart agent → `doctor` | `n8n build` + `up` + `n8n import` + `agent venv` + `agent restart` |
| `./trendvn status` | Container, agent, workflow on, address | `docker compose ps` + check agent + `docker compose exec -e N8N_RUNNERS_BROKER_PORT=5690 n8n n8n list:workflow` |
| `./trendvn doctor` | Full diagnostics; Each error line has a way to fix it; exit code 1 if there is a required entry error | `scripts/doctor.py` |
| `./trendvn open` | Open the console in the browser | `open` (Mac) / `xdg-open` (Linux) |
| `./trendvn uninstall [--purge]` | Remove agent service, stop container. `--purge` delete `data/worker`, `data/agent`, `.venv`, volume n8n (asks for confirmation) but KEEP `data/backups` and `.env` | `docker compose down [-v]` |
| `./trendvn migrate <old-directory-1.2> [--yes] [--no-service]` | Move the running system from the version 1.2 directory to this new directory ([DEPLOY.md](DEPLOY.md) section 11) | — |
| `./trendvn version` | Version number | `cat VERSION` |

## View logs

```bash
./trendvn logs                 # worker + n8n, last 100 lines
./trendvn logs -f              # live monitoring (Ctrl+C to exit)
./trendvn logs worker -n 300   # worker only, 300 lines
./trendvn logs n8n -f
./trendvn logs agent -f        # Chrome agent on the device: data/agent/agent.log
```

| Component | Log is located at | How to view manually |
|---|---|---|
| worker, n8n | container log (auto-rotate up to 5 × 10 MB per service) | `docker compose logs -f worker` |
| agent | `data/agent/agent.log` (Mac also has `data/agent/launchd.log` for boot error) | `tail -f data/agent/agent.log` |
| Business log (which video is in/out of which status) | Dashboard → More → Log | `GET /api/dashboard` |
| Workflow run history | n8n → Executions (hold 7 days) | |

## Build and n8n

| Command | Job |
|---|---|
| `./trendvn build [--no-cache]` | Build image `trendvn/worker:<version>` from `services/worker/` |
| `./trendvn n8n build` | Generate `n8n/workflows/*.json` from `n8n/build.py` (read `.env`: agent port, time zone). `--check` only checks if the file matches the code |
| `./trendvn n8n import` | Load credential (token taken from `.env`, not printed) and 6 workflows into running n8n. The previously enabled calendar will be enabled again |
| `./trendvn n8n activate [id…]` | Enable calendar (default `trendvn01daily`, `trendvn02publish`, `trendvn03daily`); n8n reboots itself once |
| `./trendvn n8n deactivate [id…]` | Turn off schedule (default for all TrendVN workflows) |
| `./trendvn n8n status` | Which workflow turns ON/OFF |
| `./trendvn n8n export [directory]` | Save existing workflow in n8n to JSON (default `n8n/exported/`), for example after you edit in n8n interface |

Details of how the n8n system was born: [N8N.md](N8N.md).

## Browser and TikTok Agent

| Command | Job |
|---|---|
| `./trendvn agent install` / `uninstall` | Install/uninstall background services (user systemd on Linux, launchd on Mac); only touches the service of **this directory** |
| `./trendvn agent start` / `stop` / `restart` / `status` | Service control (without systemd/launchd, use background process + pid file) |
| `./trendvn agent logs [-f] [-n N]` | Log agent |
| `./trendvn agent run` | Run in this terminal (Ctrl+C stop), convenient for debugging |
| `./trendvn agent venv` / `update` | Rebuild `.venv` / upgrade yt-dlp and playwright then reboot |
| `./trendvn tiktok login [minutes] [--account ID]` | Open real Chrome to let **you** log in to TikTok once (the system never enters your password). Each account has its own Chrome profile; no `--account` is account `main` (default account). `ID` is the code displayed in the account tab in the control panel |
| `./trendvn tiktok trust [minutes] [--account ID]` | Solve TikTok's verification image once |
| `./trendvn tiktok dry-run [--account ID]` | Upload video to TikTok Studio, fill in description, take photo then stop — **don't post**. Photo: `data/worker/exports/shot_*.png` (name printed in results; "Preview" button on the control panel also shows the image). Video needs to be processed; message `"status": "idle"` means not available. The error image is located at `data/agent/shots/` |
| `./trendvn tiktok status [--account ID]` / `verify` / `stats` | Check an account's session / compare unconfirmed posts (on the correct account posted) / read views of all active accounts |

## Data and handover

| Command | Job |
|---|---|
| `./trendvn backup [--with-session] [--keep N]` | `data/backups/trendvn-<timestamp>.tar.gz` (0600): SQLite, Gemini key, message, `.env`, n8n data. `--with-session` with TikTok session; `--keep N` holds N latest version |
| `./trendvn restore <file> [--yes]` | Restore (overwrite, ask for confirmation). Keeps the network key/uid of the current machine; read backup from 1.2 |
| `./trendvn package` | Test then package `dist/trendvn-<version>.tar.gz` + `.sha256`: source code only, no `.env`, no `data/`, no `.venv` |

Regular backup (cron; cron uses a very short PATH so it must be declared to find `docker`): `0 3 * * 0 PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; cd /path/to/trendvn && ./trendvn backup --keep 8`.

## Test and format code

| Command | Job |
|---|---|
| `./trendvn fmt` | Python code formatting (black) and safe lint fixing (ruff). Need `python3 -m pip install -r requirements-dev.txt` |

### Test

| Command | Job |
|---|---|
| `./trendvn test` | `lint` + `unit` (several tens of seconds) |
| `./trendvn test lint` | Generative code matching workflow · Python/shell syntax · script runs on macOS bash 3.2 · `compose.yaml` is valid · shellcheck if present |
| `./trendvn test unit` | More than 150 unit/integration tests on machine |
| `./trendvn test container` | Build image and run again **entire** test in image (with ffmpeg) and build real video |
| `./trendvn test e2e` | Real Chrome: layout in 7 sizes × 6 tabs and all button click flows (requires `.venv`; `TRENDVN_SAMPLE=video.mp4` for real video) |
| `./trendvn test all` | All of the above |

## Variable environment variable (`.env`)

Sample and explanation of each variable: [.env.example](../.env.example). Add the line to `.env` then `./trendvn up` (container) or `./trendvn agent restart` (agent).

| Variable | Effect |
|---|---|
| `COMPOSE_PROJECT_NAME` | Docker project name (default `trendvn`); changed when running two copies on one machine |
| `TRENDVN_N8N_PORT`, `TRENDVN_WORKER_PORT`, `TRENDVN_AGENT_PORT` | Port (default 5680, 5681, 5682) |
| `TRENDVN_BIND` | `127.0.0.1` (default, this machine only) or `0.0.0.0` (with `TRENDVN_UI_PASSWORD`) |
| `TRENDVN_US_PROXY` | US proxy for TikTok/Instagram source |
| `TRENDVN_TZ` | Calendar time zone and golden hour |
