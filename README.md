# TrendVN

System to automatically repost trending videos to your TikTok channel: collect trending videos every day
(Douyin, Kuaishou in China; TikTok, Instagram Reels in US) → detect video **new**→ keep music, add**Vietsub**or**Vietnamese dubbing** (Google Gemini) → posted via real Chrome browser during prime time. There is a control panel
(can be used on phones) to view the queue, edit description, press **Post now**, and the schedule runs completely automatically with its own n8n.

```
 Chrome on machine (agent) ── collect/post ──► worker (Docker) ◄── schedule ── n8n (Docker)
   Playwright + yt-dlp SQLite · ffmpeg · Gemini · console
```

## Installation (Mac or Linux; Brand new Mac takes about 30–60 minutes because you have to download Docker Desktop and build for the first time)

Needs: Docker (Desktop on Mac), **Python 3.10+** (macOS only comes with 3.9: install `brew install python@3.12`), Google Chrome version of Google. Step-by-step instructions on Mac: [docs/MAC.md](docs/MAC.md).

```bash
tar xzf trendvn-1.6.tar.gz && cd trendvn-1.6     # or double click macos/Install.command
./trendvn install                                # configures, builds Docker, loads n8n workflow, turns on schedule, installs agent
```

Then 5 things only you can do:
1. `./trendvn open` → More → Settings: paste Gemini key (taken from https://aistudio.google.com/apikey), enable **Video processing**.
2. More → Settings → Posting schedule: set **Default TikTok account**as your channel (when first installed it was a sample account). Do this step**before** when logging in: the login command only accepts this account.
3. `./trendvn tiktok login`: manually log into TikTok once in the Chrome window that appears.
4. Press **▶ Start**in Overview (the first scan only records landmarks, you should press again after a few hours or wait for the 3-hour schedule) until the**Post tab** has a video, then `./trendvn tiktok dry-run` (test run, not post; report `"status": "idle"` means there is no finished video yet, not an error).
5. Enable **Self-publish** when satisfied.

Automatic schedule (n8n) is enabled immediately upon installation: collects and processes every 3 hours, asks "can I post" every 30 minutes; turn it off with `./trendvn n8n deactivate`. When **Video Processing**is off, the schedule only collects; When**Auto Post** is off, the calendar still processes but nothing is posted.

## Frequently used command

| Job | Command |
|---|---|
| Run/stop/restart | `./trendvn up` · `./trendvn down` · `./trendvn restart [worker\|n8n\|agent]` |
| View logs | `./trendvn logs -f` · `./trendvn logs worker\|n8n\|agent -n 200` |
| Rebuild Docker image | `./trendvn build` (add `--no-cache` if needed) |
| Rebuild n8n system from code | `./trendvn n8n build` → `./trendvn n8n import` |
| Automatic calendar on/off | `./trendvn n8n activate` · `./trendvn n8n deactivate` |
| System health | `./trendvn status` · `./trendvn doctor` |
| Move the running system from the version 1.2 folder | extract this version in the new folder, then `./trendvn migrate <old-directory-1.2>` (docs/DEPLOY.md section 11) |
| Apply the new version | extract the new version overwriting the running directory (`tar xzf trendvn-X.tar.gz --strip-components=1`), then `./trendvn update` |
| Backup/restore | `./trendvn backup` · `./trendvn restore <file>` |
| Packaging and copying to another machine | `./trendvn package` |
| Test | `./trendvn test` (fast) · `./trendvn test all` (full, includes Docker and real Chrome) |

Entire command, with command `docker compose` equivalent: [docs/COMMANDS.md](docs/COMMANDS.md). `make help` also works.

## Folder layout

```
trendvn single command for everything (Makefile is shortcut)
compose.yaml  .env.example  VERSION  CHANGELOG.md
services/worker/ image Docker: queue, rules, Gemini, ffmpeg, console
  src/trendvn_worker/ domain/ store/ ai/ media/ web/ ui/ + tasks.py pipeline.py (one job per folder)
services/agent/ Chrome on device: collect and post TikToks
  src/trendvn_agent/ collector/ (sources/ one file per platform) publisher/ browser.py server.py
n8n/ build.py generate 6 workflows from code · manage.py load/enable/export · workflows/*.json
scripts/                install · backup · restore · doctor · package · fmt · service (systemd, launchd)
macos/ double click file for Mac
tests/ worker/ agent/ tools/ (more than 500 tests) + e2e/ (real Chrome interface)
docs/ detailed documents
data/ (self-generated, not packaged) data: worker/ agent/ backups/
```

## Document

[Mac](docs/MAC.md) · [Command](docs/COMMANDS.md) · [Deployment](docs/DEPLOY.md) · [Operation](docs/OPERATIONS.md) ·
[Architecture](docs/ARCHITECTURE.md) · [n8n](docs/N8N.md) · [Prompt Gemini](docs/PROMPTS.md) · [Security](docs/SECURITY.md) ·
[API](docs/API.md) · [Agent Rules](AGENTS.md) · [Roadmap 1.4](docs/ROADMAP.md) · [Review 1.3](docs/REVIEW-1.3.md) · [Changes](CHANGELOG.md)

## Limits to know

- **Only one autorunner for one TikTok channel**; The remaining device is only for testing.
- **TikTok sometimes shows a verification image.** The system does not solve or exceed: it pauses posting and tells you to solve once
  (`./trendvn tiktok trust`, or double-click `macos/Verify-TikTok.command`).
- **US Source** needs US IP (`TRENDVN_US_PROXY` in `.env`); If not, then ignore it and never mistakenly label Vietnamese content as an American trend.
- **Copyright and platform terms are your responsibility.** The system only blocks duplicate and sensitive content according to rules, does not check copyright.
- By default, everything only opens on this device (`127.0.0.1`). Remote viewing: using SSH/VPN tunnel ([docs/DEPLOY.md](docs/DEPLOY.md)).
