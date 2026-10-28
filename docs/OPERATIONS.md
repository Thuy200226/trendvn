# Operations: install, run, update, fix

For owners and operators. What the system does is in [FLOWS.md](FLOWS.md); what it is made of is in [TECH.md](TECH.md). Every command is `./trendvn <command>` run in the project folder; `./trendvn help` prints the list. Messages on screen are in Vietnamese; the symptoms below are translated.

## 1. Install

| Need | Detail |
|---|---|
| System | macOS or Linux (Windows: WSL2 with WSLg, to show the sign-in window, and Chrome installed inside it) |
| Docker | Docker Engine with Compose 2.20 or newer, usable without `sudo` on Linux; on a Mac, Docker Desktop (started once, with "Start when you sign in" on) |
| Python | **3.10 or newer** with `venv` for the agent. macOS ships 3.9: install 3.12 from python.org or `brew install python@3.12` (a Mac without `git` or `python3` gets them from `xcode-select --install`). The `./trendvn` script finds the newest one itself |
| Chrome | Google Chrome (on a Mac in `/Applications`; on Linux Google's package, not Chromium or snap) |
| Disk | at least 4 GB free (a warning, not a stop); the images are about 2 GB, mostly n8n |
| Accounts | a Gemini API key (https://aistudio.google.com/apikey); optionally a US proxy for the US sources |

On a Mac, keep the folder **outside** `Documents`, `Desktop` and `Downloads` (macOS does not let background jobs read them), keep the Mac awake while it should work (Settings: do not sleep on power; closing the lid still sleeps it; after a reboot the agent starts only once you log in), and run automation on **one** machine per TikTok channel. The double-click launchers in `macos/` do the same as the commands, with two differences: `Install.command` runs `install` without `--no-activate` (the schedule turns on; with Auto-post off nothing is posted) and `Verify-TikTok.command` passes a verification (`tiktok trust 20`), it does not settle unclear posts. If macOS blocks a launcher, run `xattr -dr com.apple.quarantine ~/trendvn` once. The Mac path has not been run on real hardware (see [ROADMAP.md](ROADMAP.md)): if something is odd, keep the output of `./trendvn doctor`.

**1. Get the code** into a plain folder:

```bash
git clone -b develop https://github.com/Thuy200226/trendvn.git ~/trendvn && cd ~/trendvn
```

Or extract a package built by `./trendvn package`: run `shasum -a 256 -c` on its `.sha256` file next to the tarball, then `tar xzf trendvn-<version>.tar.gz` (it unpacks to `trendvn-<version>/`; move that folder to `~/trendvn`).

**2. Install** (safe to run again; never destroys data). The first build is the slow one: the base image, ffmpeg and n8n are downloaded.

```bash
./trendvn install --no-activate
```

It checks the machine, creates `.env` with its secrets, builds the agent's Python environment, generates the n8n workflows, builds and starts the two containers, loads the workflows, and installs the agent as a background service. `--no-activate` leaves the schedule off until you turn it on; `--no-service` skips the background service (run it with `./trendvn agent run`).

**3. Check**, then open the dashboard (http://localhost:5681):

```bash
./trendvn doctor
```

```bash
./trendvn open
```

One red line (the schedule is off) and a few yellow ones (no Gemini key, not signed in, Auto-post off) are normal until the last step. n8n is at http://localhost:5680; its first visit asks you to create an owner account (any email and password, kept in the n8n volume and in the backup; nothing needs importing).

**4. Configure and sign in**, in this order (the full flow is [FLOWS.md](FLOWS.md) section 4.1): in More, Settings paste the Gemini key and turn on video processing; in the posting schedule set the default TikTok account to your channel (a fresh install holds a sample name, and a sign-in only counts when it is that account); optionally set a notification channel (Telegram, ntfy or webhook) so failures reach your phone. Then sign in once in the Chrome window that opens:

```bash
./trendvn tiktok login
```

**5. Rehearse**, then go live. Press Update all on the Overview (the first scan only records markers; press again hours later) and wait until the Posting tab holds a video, then:

```bash
./trendvn tiktok dry-run
```

It uploads and fills the caption but stops before Post and saves a screenshot in `data/worker/exports/`. A visible Chrome opens for 1 to 2 minutes: do not close it, and do not repeat the rehearsal many times (it provokes TikTok verification). `"status": "idle"` means no processed video exists yet, not an error. Set Post visibility to "Only me" for the first real posts, and turn on Review before posting for the first days. When satisfied, turn on Auto-post in the dashboard and:

```bash
./trendvn n8n activate
```

## 2. Daily use

| Command | Purpose |
|---|---|
| `./trendvn status` | containers, agent, which schedules are on |
| `./trendvn logs -f` | live log of worker and n8n (`logs agent -f` for the agent) |
| `./trendvn up` | start the containers again after `down`, or apply an edited `.env` to them |
| `./trendvn restart [worker\|n8n\|agent]` | restart one part, or all (an edited `.env` reaches the agent only after `agent restart`) |
| `./trendvn down` | stop n8n and worker, keep data (the agent keeps running: `./trendvn agent stop`). Never `docker compose down -v`: it deletes the n8n volume |
| `./trendvn n8n deactivate [id]` / `activate [id]` | schedule off / on; ids `trendvn01daily`, `trendvn02publish`, `trendvn03daily`, default all three (posting included); each change restarts n8n for 10 to 30 seconds |
| `./trendvn doctor` | full diagnosis, each red or yellow line says how to fix it |

**Reading the dashboard.** The status bar is green only when setup is complete, nothing needs you, no video waits for your approval, and both the collector and the poster reported in the last 7 hours; orange says which is missing (a refused AI key too). Tabs: Overview, Queue (downloaded, waiting), Posting (finished videos with a Post now button), Need to see (decisions: unconfirmed posts and held videos), Posted, More (sources, settings, accounts, notifications, log). The meaning of each state and decision is in [FLOWS.md](FLOWS.md) sections 2 and 4.3. Every post opens a visible Chrome window for a minute or two: leave it alone, closing it breaks the post.

**Settings** (More, Settings; every value is range-checked and a wrong one is refused; the AI key has its own form):

| Setting | Default |
|---|---|
| Video processing / Auto-post / Review before posting | off / off / off |
| Vietnamese dubbing | on (only for narration or one speaker the AI marks safe; comedy, drama, interviews and several speakers keep their voice with subtitles) |
| Reading voice | automatic by speaker (or one fixed voice, default Kore) |
| Blur original subtitles | automatic (only where ours overlap) / always / never |
| Caption style | headline (default) / neutral |
| Post visibility | public ("Only me" for safe tests) |
| Posts per day / minimum gap | 2 / 3 hours |
| Golden hours (Vietnam time, not changeable) | 11-14 and 19-23 (empty = any time) |
| Video age / maximum length | 7 days / 180 seconds |
| Downloads per scan / queue size | 3 / 4 |
| Popularity threshold | Douyin 150,000 likes; Kuaishou and TikTok 1,000,000 views |
| AI calls per 24 hours / minimum certainty | 12 / 0.90 |

**Several TikTok accounts** (More, TikTok accounts and topics): add the account name, tick the topics it takes, save, then sign it in with the command shown on its card, `./trendvn tiktok login --account <id>`. Each account has its own Chrome profile and its own optional limits. Videos of a topic nobody takes are held for you. The first scan of a newly wanted topic tab only records markers, so its first video arrives after the second scan (hours later).

## 3. Update, back up, move

```bash
./trendvn backup
```

Take a backup first. It writes `data/backups/trendvn-<stamp>.tar.gz` (mode 0600): `.env`, the Gemini key and the n8n data, so keep it private; it holds no video files, and n8n pauses for a few seconds. Add `--with-session` to include the TikTok sessions, `--keep N` to keep the newest N. Then extract the new version over the running folder (`tar xzf <package> --strip-components=1`; `.env` and `data/` are kept) or `git pull`, and:

```bash
./trendvn update
```

```mermaid
flowchart TD
  A["new version"] --> B["./trendvn backup"]
  B --> C["put the new files over the folder<br/>.env and data/ are kept"]
  C --> D["./trendvn update:<br/>regenerate workflows, rebuild and restart containers,<br/>remove old images, import workflows,<br/>refresh the agent, doctor"]
  D --> E{"doctor green?"}
  E -- no --> F["fix what it says, run update again"]
  F --> D
  E -- yes --> G["./trendvn tiktok dry-run"]
  G --> H["watch one cycle: workflow runs, dashboard status bar"]
  H --> I{"a problem?"}
  I -- no --> J(["done"])
  I -- yes --> K["./trendvn n8n deactivate"]
  K --> L["put the previous version back, ./trendvn update"]
  L --> M{"did the new version<br/>migrate the database?"}
  M -- no --> N["./trendvn n8n activate"]
  M -- yes --> O["./trendvn restore the first backup,<br/>then ./trendvn n8n activate"]
```

Going back: code and workflows return by installing the previous version again. The database only moves forward, so when the version's entry in [../CHANGELOG.md](../CHANGELOG.md) mentions a migration, or `MIGRATIONS` in `services/worker/src/trendvn_worker/store/schema.py` grew, restore the backup from step one (what happened since that backup is forgotten); a restore asks you to type a confirmation word (`--yes` skips it) and leaves the schedule off until you turn it on. To upgrade n8n: change its pinned version in `compose.yaml`, back up, `./trendvn up`, `./trendvn n8n import`, `./trendvn n8n status`, then watch one cycle under Executions.

**Move to another machine** (this order avoids two machines posting to one channel):

```bash
./trendvn n8n deactivate
```

```bash
./trendvn backup --with-session
```

Copy the backup file to the new machine. There: install with `./trendvn install --no-activate`, `./trendvn restore <backup file>`, `./trendvn doctor`, `./trendvn tiktok login` (TikTok may ask again), `./trendvn tiktok dry-run`, then `./trendvn n8n activate`. A weekly backup by cron needs a full PATH: `0 3 * * 0 PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; cd /path/to/trendvn && ./trendvn backup --keep 8`.

**From an old 1.2 folder on the same machine:** unpack the new version, do not install, run `./trendvn migrate <old-folder>`. It checks everything before stopping anything, backs up the old folder, stops its agent and containers (a few minutes without service), copies `.env` and data (TikTok sessions kept, Chrome cache dropped), runs `install --no-activate`, compares the video counts per state, keeps the schedule, Auto-post and settings as they were, keeps the old folder and prints the commands to go back. Side by side instead: a second `COMPOSE_PROJECT_NAME`, ports and `--no-service`, and never both on one TikTok channel.

**Uninstall:** `./trendvn uninstall` stops the services and containers and keeps the data; `--purge` also deletes data, sessions and the n8n volume but keeps `data/backups/` and `.env` (it asks you to type a confirmation word; it cannot be undone).

## 4. When something is wrong

| Symptom | Likely cause | Do |
|---|---|---|
| `install` stops with a message about Docker, Chrome, Compose, Python or the folder | a prerequisite is missing: Docker Desktop not running; no Google Chrome in `/Applications`; Compose older than 2.20; only the system Python 3.9 ("Need Python 3.10"; no `python3`: `xcode-select --install`); the folder is under Documents, Desktop or Downloads, or its path has spaces | fix the one the message names (e.g. install Python 3.12 and open a new terminal; move the folder to `~/trendvn`), run again |
| `install` stops: "volume `<project>_n8n_data` exists but `.env` has no key" | `.env` was lost and a new key would stop n8n starting | copy the old `.env` back, or (loses the n8n data) `docker volume rm <project>_n8n_data` |
| "Docker project runs from ANOTHER FOLDER" | the project name is already used by another folder | run `down` there, or give this folder its own `COMPOSE_PROJECT_NAME`, ports and `--no-service`; replacing it on purpose is `TRENDVN_ALLOW_TAKEOVER=1` |
| No new videos in the queue | the first scan only records markers; thresholds too high; the queue is full (4); video processing is off | press Update all again later; lower the popularity threshold; check Settings |
| "TikTok/Instagram need a US IP" | exit IP is not in the US | set `TRENDVN_US_PROXY` in `.env`, `./trendvn agent restart` |
| "Posting: needs attention" | signed out or session ended | `./trendvn tiktok login` (add `--account <id>`) |
| Dashboard says TikTok asks for verification | CAPTCHA on a session | pass it once: `./trendvn tiktok trust` |
| A source says "verification or sign in" | the site shows a wall | the system never passes it; try later |
| Many cards show the same AI error | the model gives unusable answers, or a retired model | read the reason on a card, change Model in Settings, approve one card to retry. A refused key shows a banner and videos wait; a used-up quota retries by itself |
| "Agent is busy" on a button | the schedule or another button holds the browser | wait a few minutes |
| "Cannot reach the agent" | the agent service is not running, or it cannot listen yet (Docker network not up: it retries every 15 s) | `./trendvn doctor`, `./trendvn up`, then `./trendvn agent restart` |
| Container cannot call the agent although it runs | a firewall blocks the bridge | Linux with ufw: `sudo ufw allow from <TRENDVN_SUBNET from .env> to any port <agent port>` (`doctor` prints it); on a Mac check `TRENDVN_AGENT_BIND=127.0.0.1` and `TRENDVN_AGENT_HOSTREF=host-gateway` in `.env` |
| Phone message "Step 01 collect (or another) failed" | a step of the schedule failed; n8n itself still shows green | `./trendvn doctor`; open that run under Executions in n8n for the error |
| Phone message "agent /api/... still running after N minutes" | a browser job passed its limit and still holds the browser | `./trendvn agent logs`; if Chrome is stuck, `./trendvn agent restart` (an unfinished post is settled by the next check) |
| No Chrome window when posting (Linux) | `install` stored the `DISPLAY` of that moment | `systemctl --user cat trendvn-agent`; set `TRENDVN_PUBLISH_HEADED=1` (visible) or `0` (hidden: TikTok asks for verification more often), then `agent restart` |
| "File input not found" when posting | TikTok changed its page, or it loaded slowly | look at the failure screenshot in `data/agent/shots/`; if it repeats, report it with that picture |
| Click Post but the post does not show | TikTok review or a network error | the system settles it on the next check; or answer "up" or "not" in Need to see |
| `tiktok ...` command fails while the system works | it opens the agent's own Chrome profile without its lock, and a job was running | run those commands only when no agent job runs (`./trendvn status`, `logs agent`); a clash counts as a video failure (open item in [ROADMAP.md](ROADMAP.md)) |
| Dashboard from another device redirects to a login, or answers 403 | it is not "this machine"; a password is required | set `TRENDVN_UI_PASSWORD` and `TRENDVN_UI_HOSTS` (on a Mac 403 also `TRENDVN_TRUSTED_PEERS`), `./trendvn up`; or use a tunnel: `ssh -N -L 5680:127.0.0.1:5680 -L 5681:127.0.0.1:5681 user@host` |
| The token may have leaked | `TRENDVN_TOKEN` is shared by the three parts | change it in `.env`, then `./trendvn up`, `./trendvn n8n import`, `./trendvn agent restart` |
| Disk full | videos and renders | see section 5 |

To stop posting at once, turn Auto-post off (effective at the next 30-minute check). To stop only collecting: `./trendvn n8n deactivate trendvn01daily`; plain `deactivate` stops all three schedules, posting included.

## 5. Keeping it healthy

- Files clean themselves up (see [TECH.md](TECH.md) section 4). To free space by hand, delete `data/worker/jobs/<id>/` and `data/worker/inbox/*` of videos already published or rejected. Never delete `data/worker/trendvn.sqlite3`: without it the system forgets what it posted and may repost.
- n8n keeps run history for 7 days.
- Linux: the agent starts after you sign in unless `sudo loginctl enable-linger $USER` was run once (`doctor` says so). A Mac only works while awake; `doctor` warns when it will sleep, and agent start-up errors are in `data/agent/launchd.log`.
- Two copies on one machine need their own project name and ports ([TECH.md](TECH.md) section 9).

## 6. Command reference

| Command | Purpose |
|---|---|
| `./trendvn install [--no-activate] [--no-service]` | first installation |
| `./trendvn up`, `down`, `restart [worker\|n8n\|agent]`, `status`, `open`, `doctor` | run and inspect |
| `./trendvn logs [worker\|n8n\|agent\|all] [-f] [-n N]` | logs |
| `./trendvn build [--no-cache]` | rebuild the worker image |
| `./trendvn update` | apply a new version |
| `./trendvn n8n build [--check]\|import\|activate [id...]\|deactivate [id...]\|status\|export [dir]` | generate and load the workflows (`--check` fails when the committed JSON differs), schedule on or off, which are on, save the ones in n8n to JSON (default `n8n/exported/`) |
| `./trendvn agent install\|uninstall\|start\|stop\|restart\|status\|logs\|run\|venv\|update` | the browser agent service, its Python environment, yt-dlp and Playwright upgrade |
| `./trendvn tiktok login\|trust [minutes]\|dry-run\|status\|verify\|stats [--account ID]` | sign in, pass a verification once (`--account` applies to login, trust, status and dry-run), rehearse, check, settle unclear posts, read views |
| `./trendvn backup [--with-session] [--keep N]`, `restore <file> [--yes]`, `package` | backup, restore, a secret-free archive with checksum |
| `./trendvn migrate <old-folder-1.2> [--yes] [--no-service]` | move a running 1.2 installation into this folder |
| `./trendvn uninstall [--purge]` | remove the service and containers |
| `./trendvn test [lint\|unit\|container\|e2e\|all]`, `./trendvn fmt`, `./trendvn version` | tests, formatting (needs `pip install -r requirements-dev.txt`), version |

A real scan without n8n, for debugging: `PYTHONPATH=services/agent/src .venv/bin/python -m trendvn_agent.collector [douyin kuaishou tiktok instagram]`.
