# Install TrendVN on your Mac at home (30–60 minutes for brand new Mac; 10–15 minutes if you already have Docker, Python, Chrome)

## 1. Preparation (do once)

| Need | Install |
|---|---|
| **Docker Desktop** | https://www.docker.com/products/docker-desktop/ → open it, wait for the stationary whale icon |
| **Google Chrome** | https://www.google.com/chrome/ |
| **Python 3.10 or later**| macOS only comes with Python 3.9 (after installing "Command Line Tools": type `xcode-select --install`),**too old** for agents. Install more: `brew install python@3.12` or download the installation version here https://www.python.org/downloads/macos/ . Check: `python3.12 --version` |

With Homebrew is more compact: `brew install python@3.12` and install Docker Desktop, Chrome (Docker's cask package name can be `docker-desktop` or `docker` depending on the Homebrew version). Open Docker Desktop once and enable **Start Docker Desktop when you sign in** (Settings → General) so that after restarting the Mac, the container will start up automatically.

Google Chrome must be in the folder **/Applications** (this is the default setting).

## 2. Copy project to Mac

On **machine running**, packaging (no password, key or data included):

```bash
./trendvn package        # creates dist/trendvn-1.6.tar.gz and .sha256 file
```

Copy the file to Mac using AirDrop, USB or `scp`, then double-click to extract it into the `trendvn-1.6` folder. **Move that folder to `~/trendvn`** (your home folder), don't put it in Downloads, Documents or Desktop: macOS restricts background programs from accessing these folders so the agent may not be able to run.

## 3. Install

Open Terminal:

```bash
cd ~/trendvn      # the folder you just moved into
./trendvn install
```

Or double click `macos/Install.command`. If blocked by macOS (files downloaded by browser or AirDrop are flagged as quarantined): System Settings → Privacy & Security → **Still open**, or remove the quarantine flag for the entire folder with `xattr -dr com.apple.quarantine ~/trendvn` and then double-click again (this also applies to other `.command` files). Using Terminal with `./trendvn install` is not blocked.

Script to self-test the machine, build containers, generate and load 6 workflows into n8n, turn on the schedule and install background services. Finally it prints the diagnostic table: the lines **✓**are fine; The gold lines**!** (no Gemini key, not logged in to TikTok, Self-publishing is off...) are normal at this time and are the 5 tasks in section 4. The first time building an image takes a few minutes.

## 4. Five things only you can do

1. `./trendvn open` (or http://localhost:5681) → **More → Settings**: paste the Gemini key (created in https://aistudio.google.com/apikey), enable "Video processing".
2. **More → Settings → Posting schedule → "Default TikTok account"**: change to your correct channel, **before** when logging in (the login command only accepts this exact account) (default is a sample account; if false, any posts will not is confirmed and posting stops automatically).
3. Log in to TikTok once (enter it yourself in the Chrome window that appears): `./trendvn tiktok login` (or double-click `macos/Sign-in-TikTok.command`).
4. Waiting for a video to try. The first scan only recorded **as**, nothing was loaded; the video only appears from the second scan. Click **▶ Get Started**in Overview, click again after a few hours (or wait for 3 hours schedule) until tab**Posting**has a video. Then test it,** is not really posted**; A real Chrome window will appear for about 1–2 minutes, don't close it halfway:
   ```bash
   ./trendvn tiktok dry-run
   ```
   The result `"status": "idle"` means that the video has not yet been edited (not an error). If TikTok displays a verification image, resolve it automatically in that window (cannot be resolved instead). View photo: `data/worker/exports/shot_*.png` (name printed in results; "Preview" button on Post tab also shows photo).
5. Go to the control panel and turn on **"Auto Post"**. Tip: for the first few songs, set Settings → Display mode = "Only me" to test it out in TikTok Studio, then set it to "Everyone".

## Use daily

```bash
./trendvn status          # is everything running
./trendvn logs -f         # view log directly (worker + n8n); ./trendvn logs agent -f for agent
./trendvn restart         # restarts
./trendvn doctor          # diagnoses, each error comes with a fix
```

Double click `macos/Open-dashboard.command` to open the console. Note: `./trendvn down` only stops n8n and workers; **agent (Chrome) still running **, stop it with `./trendvn agent stop`. After restarting the Mac: log in to your macOS account, let Docker Desktop run automatically (enabled in item 1), the container and agent will automatically launch; Check with `./trendvn status`.

Full list: [COMMANDS.md](COMMANDS.md).

## n8n require any additional login or packaging?

**No.**n8n here runs right on your Mac, not a network account. `./trendvn install` has generated and loaded all 6 workflows and authentication information ([N8N.md](N8N.md)). The first time you open**http://localhost:5680**, n8n forces you to create a new home account (optional email and password). If you want to keep the account, history and settings of the old device intact, do the following: `./trendvn backup` on the old device, copy the files in `data/backups/` to Mac, install and run `./trendvn restore data/backups/<file>`.

## Note only for Mac

- **Mac must be on and not sleeping** for the schedule to run. Plug in charger, set "Prevent Mac from sleeping when plugged in" in System Settings; Folding the laptop screen will put the laptop to sleep. The background service used `caffeinate` to prevent the machine from sleeping while working.
- **Only one device running automatically for one TikTok channel.** Turn off the old device (`./trendvn uninstall`) before turning on the new device.
- **TikTok and Instagram US** need US IP. In Vietnam, these two sources are ignored (Douyin and Kuaishou still run). If you have an American proxy/VPN, add `.env`: `TRENDVN_US_PROXY=http://user:pass@host:port`, then `./trendvn agent restart`.
- **Uninstall completely:** `./trendvn uninstall` (data hold) or `./trendvn uninstall --purge`.

## If an error occurs

| Error | How to handle |
|---|---|
| "Docker Desktop is not running" | Open the Docker application, wait for it to start, run again |
| "There is no Google Chrome yet" | Install Chrome in the Applications folder |
| The "Run browser agent" item is red | `./trendvn agent status`, then `./trendvn agent logs` (startup error is located at `data/agent/launchd.log`) |
| n8n cannot call agent | Check lines `TRENDVN_AGENT_HOSTREF=host-gateway` and `TRENDVN_AGENT_BIND=127.0.0.1` in `.env` |
| macOS blocks file `.command` | Privacy & Security → Leave open, or `xattr -dr com.apple.quarantine ~/trendvn`; or use Terminal with `./trendvn …` |
| Stop installation at Python step ("Need Python 3.10") | `brew install python@3.12` then run again `./trendvn install` |

> Honest notes: actually ran on Linux: clean install from package (skip background services step), n8n call agent, backup and restore; Posting it to TikTok and analyzing it with Gemini also worked (in the previous version). The new systemd/launchd background service is statically checked (the generated content is valid and points to the correct file). **The entire macOS section has not been tested on a real Mac** (launchd, `host-gateway` of Docker Desktop, Python 3.10+ via Homebrew, file quarantine flag); Scripts only use syntax that runs on macOS bash 3.2/BSD (with automatic testing). If there is anything strange, send the result `./trendvn doctor` for quick correction.
