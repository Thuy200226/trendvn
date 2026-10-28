# Daily operations and troubleshooting

## 1. A typical day on autopilot

| Time | Things happen (without you) |
|---|---|
| Every 3 hours | Workflow 01: scan 4 sources, download emerging videos only (maximum 3/time, total queue ≤ 4), process with Gemini and ffmpeg |
| Every 30 minutes | Workflow 02: ask if worker can post. Only when it is during golden hours (default 11–2pm and 7–11pm), not enough 2 posts today, ≥ 3 hours from previous post |
| 23:30 | Workflow 03: read post views, update source weight, send date summary |

You just need to open the control panel (**http://localhost:5681**) when you receive a notification, or occasionally to see the effect.

## 1b. Hand operation buttons

The dashboard has six tabs: **Overview**, **Queue**(pending video),**Posting**(processed video),**Need see**(something you need to decide),**Posted**, **Added** (source, settings, notifications, logs). The buttons are just additional: the n8n calendar still collects, processes and posts the same.

- **Overview → ▶ Getting Started:** collects new videos and processes them. Can leave pages, background tasks; The page refreshes itself when done. If "Video processing" is off, the button just collects and states that.
- **Post:** Each processed video is a card with preview, description box and hashtag (number of characters, number of hashtags, check the quality of updates when typing), buttons Post now, Preview, Save description, Browse for self-posting schedule (only when "Hand review" is enabled), Skip video. Click Post Now to have a confirmation box stating the account, display mode and warning if there are enough posts today or it is outside of prime time.
- **When there is a job running** (of button or calendar): buttons of the same type are locked and have an explanation line, so that overlapping cannot be pressed. Processing (Gemini) and using the browser are two separate keys so they can run in parallel.
- **Video error when posting:**error 1–2 times, rest for 1 hour and then try again; If it fails 3 times, it will switch to "Need to see" with a notification. There, click**↩ Bring back ready to post**(video has been edited, no more Gemini views) or**Review** (rebuild from scratch). Your Post Now button is not limited to a 1-hour break.

## 2. Read the control panel

From top to bottom:

1. **Status bar:** is green only when all four things are done: setup is complete (Gemini lock, Video processing, Self-posting), there are no more things to watch, there are no videos waiting for you to review, and both the collector and the publisher have reported in the last 7 hours. Orange = one of the four is missing, and the bar says which one is missing (calendar n8n off or agent not running appears here).
2. **Status Tag:** four lines Collect video · Post TikTok · Happy hour (is it open or what time is it open) · Drive. Each line fits inside the card, does not scroll horizontally.
3. **Set up n/6:** to-do list to achieve full automation, each unfinished item has a suggestion right below.
4. **Processing flow:** Candidate → Pending → Ready → Posted. Tap each step to open the correct tab (Queue, Posting, Posted).
5. **Must see:** collects three types of jobs, see below.
6. **Queue Tab**and**Posting**has its own instructions when empty (see section below);**Posted and Effective, Collection Sources, Settings, Notifications, Logs** are in the remaining tabs.

### Three places a video can be located

| Tab | What does it contain | Why might it be empty |
|---|---|---|
| **Queue**| Video has been loaded, waiting for Gemini to make Vietsub or dub (put in the correct order will be processed), same list of candidates not yet loaded | No new videos yet: click**Collect videos new** |
| **Post now**| Videos have been edited, each video has a button**Post now**| If empty, the page itself tells the reason: switch** Video handler**is OFF (with on button), or there are N videos waiting (with button**Process now**), or nothing (with button **Update**) |
| **Need to see**| Things you need to decide: verify TikTok, unconfirmed post, video withheld by the system | It's good to be empty. "Pending" video** is not ** located here but in Queue |

### "Need to see" Jobs

| Tag | Meaning | What do you do |
|---|---|---|
| 🚨 **Posting has not been confirmed** | The system has clicked Post but the post has not been seen on the TikTok profile. Posting stops automatically to avoid duplicates. | Open TikTok to check. **Post is up**→ click "Post is up on TikTok".**Not available** → click "Not available, allow repost" |
| ⚠️ **Need approval** | The system retains and records the reason (off topic, sensitive, Gemini is not sure, may duplicate processed video...) | Watch the original video. Okay → "Rerun, skip checks" (rerun and skip judgment checks, keep structure checks). No → "Quit" |

When "Hands on review before posting" is turned on, the video is finished. **is not** located in Need to watch but in the tab **Posting** (with green dot): watch the video and then click "Approve and post" or "Cancel"; If not approved, the calendar will not be automatically posted.

## 3. Settings (can be changed right on the control panel)

| Setting | Default | Meaning |
|---|---|---|
| Video processing with Gemini | Off | On the video is sent to Google Gemini for analysis. Lock lever |
| Self-post to TikTok | Off | Final switch. Only you turn on |
| Review before posting | Turn off | When turned on, the edited video stops at "Waiting for your approval" |
| Vietnamese dubbing | Enable | Prioritize dubbing when appropriate: voice-over videos and videos **one person speaking** with voice change at no cost (Gemini decides). Comedy, drama, controversy, many speakers always keep the original voice with Vietsub. Change the range in "Voice for" |
| Select reading voice | Automatic | Voice according to speaker (male/female, nuance) and speed according to speech window; "Always use the voice below" to fix (default Kore). Verified voices at docs/QUALITY.md |
| Blur original subtitles | Automatic | Only when Vietnamese subtitles will overlap the original text, and only when they appear; `Always` or `Never` if you want |
| Post description type | Headline | `Headline`: opening sentence that stimulates curiosity, still sticking to the video content; `Neutral`: straight description. Change to More → Settings → Gemini |
| Maximum posts per day | 2 | 1–10 |
| Minimum interval | 3 hours | Between two articles |
| Golden hour | 11-14, 19-23 | Vietnam time; Leave blank to post anytime |
| New videos in (days) | 7 | Remove older videos |
| Maximum length | 180 seconds | |
| Maximum Load Per Scan / Maximum Queue | 3 / 4 | Gemini Cost Control |
| Popularity threshold | Douyin ≥ 150,000 hearts; Kuaishou, TikTok ≥ 1,000,000 views | Videos below the threshold do not enter the queue |
| Minimum Gemini certainty | 0.90 | Below this level the video is in "Need approval" |
| Gemini call limit / 24 hours | 12 | Each video costs 1 time to analyze, plus 1 to 2 times to create voice if dubbing (second time only if the first voice is longer than the lyrics window by more than 15%) and 1 time to shorten if the subtitles are too fast. Increase if your Gemini plan allows |

All values are checked for valid ranges in the worker (`validate_settings`), entering incorrectly will report an error but not save.

### Multiple TikTok accounts, each with several topics

More → **TikTok account and topic**. Each card is an account: touch to select the topics it receives (comedy, pets, cuisine...), press **Save account**. Open "Name, on/off and personal limits" if you want your account to have a maximum number of posts per day, spacing, golden hours or a different display mode than the general settings (leave blank to use the general settings).

1. **Add account:** enter TikTok username, select topic, click Add.
2. **Single sign in for that account:** runs the command shown in the tab, of the form `./trendvn tiktok login --account <id>`, then signs in itself in the Chrome window that appears (each account has its own Chrome profile). The tag says "logged in" after the next calendar session check.
3. From the next collection, the system finds videos belonging to topics that have recipient accounts (the first scan of each new topic tab only records landmarks, so the first video of the new topic arrives after the second scan, up to a few hours), and then posts each video to its correct topic recipient account.

The video tag in the Posting tab specifies the subject and the account that will receive it. Videos on topics that no account has accepted are kept at "Need to watch" (you can still post manually to the default account).

### When posting, a Chrome window appears

The default poster opens **a real Chrome window** (when the device has a screen), about 1–2 minutes per post: download video, fill in description, click Post, confirm. Don't close it halfway. On a server without a screen, it runs in the background (TikTok will require more verification). Press either way using `TRENDVN_PUBLISH_HEADED=1` or `0` in `.env`. On Linux using the systemd service, `./trendvn install` wrote the current `DISPLAY` to the service; If the window does not appear, check `systemctl --user cat trendvn-agent`.

### Run a safety test before posting publicly

Put **Post visibility = Only me** In Settings → Posting Schedule, turn on Auto Post, so the system will post a few real posts that only you can see. See caption quality, description, and editing style in TikTok Studio; If it's okay, change it to "Everyone". Private posts are still confirmed by the Studio's profile or content page.

### Used on phones

Open the console address (via VPN or SSH tunnel, see [DEPLOY.md](DEPLOY.md)). The interface automatically switches to mobile form: navigation bar at the bottom of the screen (Overview, Queue, Posting, Need to See, Posted, More), tabbed panel, large buttons. On the screen **Overview**there are two quick switches:**Video processing**and**TikTok self-posting**(touch to turn on/off immediately, used as an emergency stop button). Browse videos: open tab**Need to watch**, preview the video and then click the button at the bottom of the card.

## 4. Troubleshooting according to symptoms

Starts with: `./trendvn doctor` (each error line has a fix), then `./trendvn status`. View log: `./trendvn logs -f` (worker + n8n), `./trendvn logs agent -f` (Chrome on computer; file `data/agent/agent.log`).

| Symptoms | Common causes | Treatment |
|---|---|---|
| There are no new videos in the queue | (1) The first scan only records landmarks. (2) The threshold is too high. (3) Queue is full | Waiting for 2nd scan; lower threshold in Settings; see Collection source |
| TikTok, Instagram says "Need US IP" | Exit IP is not US | Put `TRENDVN_US_PROXY` in `.env`, then `./trendvn agent restart` |
| "Submission: Needs attention" | Not logged in or session expired | `./trendvn tiktok login` |
| Videos stuck at "Need approval" for a lot of reasons Gemini | Wrong key, expired limit, changed model | Check the key and limit in Google AI Studio; see `docs/PROMPTS.md` |
| One source says "verify or log in" | Page shows CAPTCHA or forces login | System **does not pass CAPTCHAZ**. Usually goes away on its own after a few hours; Reduce scanning frequency or use another IP |
| Kuaishou sometimes reports error | Page disconnected | Retried itself 3 times; Normal transient error |
| The dashboard says "TikTok is requesting verification" | TikTok displays CAPTCHA images for sessions automatically (appears randomly, especially when opening the upload page multiple times in a row) | System **does not solve or bypass CAPTCHA** and has paused posting. Run `./trendvn tiktok trust` (Mac: double click `macos/Verify-TikTok.command`), solve the verification yourself in the window that appears; Once finished, the system automatically posts again. Avoid running `dry-run` continuous |
| Post "File selection box not found" | TikTok changes TikTok Studio interface, or the page loads too slowly | View photos in `data/agent/shots/`; fix element selector at `services/agent/src/trendvn_agent/publisher/post.py::_publish_one` |
| Pressing the button says "Agent is busy" | Automatic calendar or another button is using the browser | Normal, wait a few minutes then press again |
| `./trendvn doctor` reports "Container calling agent" error even though the agent is running | The machine's firewall blocks the Docker bridge (Linux/ufw) | `sudo ufw allow from <TRENDVN_SUBNET from .env> to any port <TRENDVN_AGENT_PORT>` |
| Pressing the button says "Unable to call agent" | Agent service not running | `./trendvn doctor`, then `./trendvn agent restart` and `./trendvn agent logs` |
| Opening the control panel from another device is redirected to the login page | You opened it from another device | Enter password `TRENDVN_UI_PASSWORD` in `.env` (see [DEPLOY.md](DEPLOY.md)) |
| Video is stuck "Waiting for processing" and the log says "Gemini is overloaded" | Google reports model temporary overload (503) | Normal: system tried again, changed model and re-queued video; run automatically next time |
| Error "Gemini HTTP 404 ... no longer available" | Google stops the model you are selecting | Automatically switch to the next model; If the error persists, change the model name in Settings → Gemini (see Google's `GET /v1beta/models`) |
| Click Post but the post does not appear | TikTok is censoring or there is a network error | The system automatically marks "unconfirmed" and stops; manual confirmation (item 2) |
| Phone message "Step 01 collect (or another) of the automatic schedule failed" | n8n marks every run green, so a failing step reports itself: the message names the step and the error (one message per step per 6 hours) | `./trendvn doctor`; open that run under Executions in n8n for the full error; the next steps of the run still ran |
| Phone message "agent /api/... still running after N minutes" | A browser job passed its limit (collect, session and verify 15 minutes, publish 32, stats 10) and still holds the browser; later calls get "Agent busy" | `./trendvn agent logs`; if Chrome is stuck, `./trendvn agent restart` (a post that was in progress is confirmed or marked unconfirmed by the next verify) |
| Workflow n8n running but "Agent busy" | Agent is doing something else | Normal; Next time run it yourself. One browser at a time |
| `agent` cannot listen | Docker network is not up | Agent retries every 15 seconds; `./trendvn up` |
| Disk full | Original and edited videos | Delete old videos: see section 5 |

## 5. Cleaning and maintenance

- Self-cleaning system: video files completed after 7 days, candidates have not been downloaded after 3 days, videos have not been resolved after 21 days (`store/retention.py`); records in SQLite are always kept. When the drive is exhausted but not yet expired, you can clean up: safely delete folders `data/worker/jobs/<id>/` and `data/worker/inbox/*` of videos with status `published`, `rejected`, `duplicate`, `failed` (records in SQLite are kept for anti-duplication).
- Do not delete `data/worker/trendvn.sqlite3`: losing it means losing the entire anti-disinfection history, the system will repost videos that have already been posted.
- Regular backup: `./trendvn backup --keep 8` (include in cron if desired; cron has a very short PATH so declare to find `docker`: `0 3 * * 0 PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin; cd /path/to/trendvn && ./trendvn backup --keep 8`).
- n8n execution history deletes itself after 7 days (`EXECUTIONS_DATA_MAX_AGE`).

## 6. Recover scenarios

- **Power failure mid-processing:** when the worker restarts, the video being processed is immediately re-queued (and `housekeeping` does that for videos that hang for more than 30 minutes); The video was interrupted twice before entering "Need to watch" for you to browse.
- **Power failure in the middle of posting:** `publishing` status after 45 minutes automatically changed to "Unconfirmed" (checked at each post request and at `housekeeping`, so other accounts don't have to wait); The agent compares the records in the next run 01. If they cannot confirm, you confirm manually.
- **Restarter (Linux):** agent runs under `systemd --user`, so it only runs automatically after you log in screen, unless `sudo loginctl enable-linger $USER` is enabled once (`./trendvn doctor` prompt). Without a login screen, Chrome runs in the background and TikTok requires verification more often.
- **Change TikTok password or get logged out:** log in again with `./trendvn tiktok login`. Posting stops automatically ("Submission: Needs attention") until a session becomes available.
- **Gemini deviation:** uses "Manual review before posting" for the first few days to check the quality of subtitles and descriptions before leaving it fully automatic.
- **Want to stop everything immediately:** set "Self-posting: Off" on the control panel (effective immediately on the next ask). To stop all collection: turn off Publish of workflow 01 in n8n.

## 7. Testing

```bash
./trendvn test              # fast: lint + more than 500 tests on the machine
./trendvn test container    # full test in Docker image (with ffmpeg, including real video editing)
./trendvn test e2e          # Real Chrome: 7 size × 6 tab layout and every button click flow
./trendvn test all
```
