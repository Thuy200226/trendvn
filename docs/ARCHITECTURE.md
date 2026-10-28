# Architecture and where each rule is located

Diagram: [architecture.drawio](architecture.drawio) has two pages, the three blocks and the life cycle of a video (open it in draw.io; this text is the source of truth).

## 1. Three blocks and why they separated like that

```
┌──────────────── Docker (trendvn_private private network) ────────────────┐ ┌──── Server ────┐
│ n8n :5680 scheduled dispatch, API call using HTTP │ │ agent :5682 │
│ worker :5681 data, rules, ffmpeg, Gemini, console │◄────►│ Real Chrome (Playwright)│
│ volume: data/worker/ (SQLite, video) n8n_data (n8n information) │ │ profile: data/agent/ │
└──────────────────────────────────────────────────────────────────────┘      └────────────────────────┘
```

- **worker** holds all *decisions* (posted no, this video gets no) and all *data*. Don't touch the browser.
- **agent** just *does* what requires real Chrome: scan four sources, download videos, post, read views. Doesn't make any decisions on its own: every time it posts, it must ask the worker for permission and report back the results.
- **n8n** only *timer and steps*. All business logic resides in the worker, so changing the workflow cannot break security rules.
- Agent needs real Chrome and its screen/profile should run directly on the host (user systemd service). It only listens on the Docker bridge address (`TRENDVN_AGENT_BIND`, default `172.20.0.1`), which is called `trendvn-agent`.
- Three blocks use the same key `TRENDVN_TOKEN` (Bearer). n8n holds the key in the "TrendVN · Private Worker" credential.
- **How to find an agent:** Linux uses the project's bridge address (`TRENDVN_AGENT_HOSTREF`); macOS/Windows (Docker Desktop, containers running in virtual machines) uses `host-gateway` and the agent listens at `127.0.0.1`. `scripts/setup_env.py` selects automatically according to the operating system.

## 2. Life cycle of a video (state machine)

```
                 first scan
   (scan) ─────► baseline (only to detect new videos, never process)
        │ next scan, never seen video
        ▼
     candidate ──download error 3 times──► failed
        │ downloaded, no hash match
        ▼
      queued ──duplicate hash──► duplicate
        │ worker accepts job
        ▼
    processing ──duplicate / off topic / sensitive / Gemini not sure / error──► needs_review ──your approval──► queued (skip judgment check)
        │ completed └──you quit──► rejected
        ├── "hand approval" setting on ─► awaiting_approval ──approval──► ready │ reject──► rejected
        ▼
       ready ──eligible to post──► publishing ──confirmed on profile──► published
                                        │ ├─ Post button has not been clicked but error ─► ready (try again later)
                                        │ ├─ duplicate description already exists ─► duplicate
                                        │ └─ clicked but not confirmed ─► publish_unknown ──you/agent confirmed──► published │ ready
```

Important invariants (all tested):

1. **`publish_unknown` blocks all subsequent posting attempts.** There is no mechanism to automatically retry a post that has been clicked Post.
2. **Only one post at a time is in state `publishing`** (check and place in the same SQLite transaction `BEGIN IMMEDIATE`).
3. **Lease:** `processing` and `publishing` carry one token; If the result returns an incorrect token, the token is rejected, so the old process (hangs, reruns) does not overwrite the new result.
4. **`baseline` never becomes a candidate.** The first scan of each stream records only the landmark; Thus, the system does not massively post previously popular videos.
5. Scans older than the previous one were rejected (`observed_at`), if the batch has one wrong entry, the entire batch will not be recorded.

### Additional points in 1.2

- **Background task** (`services/worker/src/trendvn_worker/tasks.py`): each button on the control panel creates a line in table `tasks` and a background thread. Lock: one browser use at a time (same lock as agent, so also schedule n8n), one process at a time (same `process_lock` with `/api/process`). Restarting the worker marks unfinished work as an error.
- **Posting status:** `publishing` remember `prev_state` (to post failed hand without accidentally browsing the video), `publish_fails` and `last_publish_fail` (rest 1 hour after error, 3 times then `needs_review`). The result `deferred` does not account for errors. The threshold `publishing` → `publish_unknown` is 45 minutes.
- **Edit video:** one ffmpeg pass: set to 1080×1920 vertical frame (blurred background for landscape, square, 4:5, 3:4 videos), get properly rotated video, subtitles set to avoid TikTok text area, normalize volume −14 LUFS, remove metadata, max 30 fps, measure output quality (`qc`) and create a preview image.
- **Description and hashtag:** Gemini recommended; code is always filtered again (`build_caption`: remove platform name hashtag, standardize Unicode, crop at word boundary), `lint_caption` shows quality, you can edit before posting.

## 3. Where is the decision?

| Question | Where to decide | Function / configuration |
|---|---|---|
| Which videos are worth considering? | `services/agent/src/trendvn_agent/collector/rules.py` + `collector/sources/*.py` | `parse_*` (normalized per source), `qualifies` (duration, age, views/heart), `score` |
| Which video loads first? | `services/agent/src/trendvn_agent/collector/rules.py` | `score` = engagement ÷ (age in hours, min 6)^0.6 × source weight |
| Are there additional downloads? | `services/agent/src/trendvn_agent/collector/run.py` | `fetch_pooled`: stop when queue ≥ `max_backlog`; every platform scanned in the same browser session shares one pool, ranked by `score` |
| Which queued video is processed first? | `services/worker/src/trendvn_worker/store/queue.py` | `Store.claim`: the one that has waited longest since it entered the queue (`updated`); a video sent back goes behind the others, and after `MAX_DEFERRALS` (10) transient Gemini failures it waits for the owner |
| New or old video? | `services/worker/src/trendvn_worker/store/ingest.py` | `Store.ingest` (baseline/candidate, matches `(platform, source_id)` and URL) |
| Duplicate files? | `services/worker/src/trendvn_worker/store/ingest.py` | `Store.attach` (SHA-256 content) |
| Same image even though encoding is different? | `services/worker/src/trendvn_worker/media/fingerprint.py` | `fingerprint` (5 frames, 64-bit hash) + `similar` |
| Music or lyrics? Topic? Sensitive? | Gemini according to `services/worker/src/trendvn_worker/ai/prompts.py` | hard retest at `domain/analysis.py::validate_analysis` |
| Which way to handle? | `services/worker/src/trendvn_worker/domain/route.py` | `choose_route` return route and reason; `validate_analysis` (analysis.py) checks then calls it |
| Video editing | `services/worker/src/trendvn_worker/media/` and `ai/tts.py` | `render`, `ass_subtitles`, `make_voice` |
| Posted now? | `services/worker/src/trendvn_worker/store/publishing.py` | `publish_claim`: switch → no unconfirmed posts → happy hour → day limit → spacing → select highest scoring post |
| Post and confirm | `services/agent/src/trendvn_agent/publisher/post.py`, `publisher/jobs.py` | `publish_one`, `verify_unresolved` |
| Learn from results | `services/worker/src/trendvn_worker/store/feedback.py` | `record_stats`, `platform_weights` (need ≥ 8 posts > 24 hours) |
| Send notification | `services/worker/src/trendvn_worker/notify.py` | `Notifier` (anti-spam by type + lock) |
| Redeemable settings | `services/worker/src/trendvn_worker/domain/settings.py` | `validate_settings` (each key has a tight range) |

## 3b. Topics and multiple accounts

- **Topic menu** (`domain/topics.py`): 15 topics (music/dance, comedy, pets, food, travel, family, beauty, sports, games, anime, movies, life, knowledge, hot news/drama, general entertainment) plus `other` (advertisement, sales goods, spam; only approved owners post). Gemini prompt, schema and interface are all generated from this same table.
- **Twice to decide the topic.** Before downloading: Free *hints* from the source's category (Douyin tab, TikTok chip) and keywords in the title (measured on 230 real Douyin titles: 67% of titles with keywords are correctly guessed; the source's category itself is noisy so it is only used to choose to download). After analysis: **Gemini decision**; The video belongs to a topic that no account has accepted as "Need to watch" for a clear reason.
- **Account**(`accounts`, `store/accounts.py`, `domain/accounts.py`): each account has its own TikTok name, list of topics to receive, and (optional) date limit, spacing, prime time, unique display mode; If left blank, use general settings. Version 1.0–1.3 account becomes `main` (receive old topics: entertainment, music, comedy, pets, family, life; migration version 4 adds `tin n\u00f3ng` if the owner has not edited the list). Each account has** its own Chrome profile** (`data/agent/profiles/publisher-<id>`; `main` keeps `publisher`) so the login session is not mixed.
- **Posting schedule** (`store/publishing.py`): each time asking, try the active accounts in turn, the longest posting account first; Any account that has space available (prime time, limited days, spacing, no unconfirmed posts) and has a high scoring video on its topic will receive that video. Unconfirmed posts only block its account; A post being posted blocks all accounts (the agent can only do one browsing job at a time). The Post Now button selects the account receiving that topic (fewest posts today), if not, then the default account.
- **Collect by topic** (`collector/sources`): Douyin: once open the `jingxuan` page, read the default stream and then click the tab of each topic needed (maximum 6 tabs per scan, rotating by clock); Kuaishou does not have a category for non-logged in guests; TikTok: themed chips; If the chip is not there, skip it and try again. The threshold for the topic tab is lower than the general stream because it is measured on 520 real Douyin videos: only 12% of the videos in the tab reach the 150k hearts mark of the general stream (median 10–70k) and the median age is 39 days so the 7-day limit only passes 10%; Topic streams use 15% heart/view threshold and allow 4 times older (28 days), ranking still prioritizes new videos. Select download (`choose_downloads`): remove videos with suggested topics that no one accepts, split turns between topics, high scores first, so that a crowded topic does not overwhelm other topics. The candidates of every platform scanned in the same browser session (Douyin and Kuaishou share one) are chosen from one pool (`fetch_pooled`): filling the room platform by platform, in the order of `SOURCES`, gave all of it to the first platform and made the source weights meaningless.

## 3c. Performance (measured on real video, 12-core machine)

Time to process a video: Gemini about two-thirds (30–100 seconds, depending on when the API is free; often the 503 "overload" error lasts for a long time so blocking and queuing are more important than optimization), editing about a quarter, the rest is preview, fingerprinting and testing (measured: 78 second video built in 24 seconds; 153 second horizontal video built in 40 seconds).

- **Parallel processing** (`pipeline.process_many`): default 2 videos at the same time (`TRENDVN_PROCESS_PARALLEL`, 1 = sequentially). Since most of the time a video is waiting for Gemini, two threads almost double the throughput without competing for CPU; Stop generating new jobs as soon as a stop status is encountered (shutdown, missing key, out of limit, out of queue).
- **Preserve picture** (`media/render.can_copy_video`): video **preserve** (music, no lyrics) is already vertical H.264 8-bit in frame 1080×1920, ≤ 30 frames/sec, bitrate ≤ 6 Mb/s, only adjust the volume, the image is copied pixel by pixel (check with md5). Measured on real video: 3.3 seconds instead of 24 seconds, 13.8 MB file instead of 24.8 MB, no quality loss.
- **Adaptive wait on crawl Douyin**(`collector/capture.Feed`): replace fixed waits with "wait until page has responded and is quiet"; stopping scrolling after two consecutive rolls is nothing new. The number of videos per tab measured is still 40–59 as before. Kuaishou and TikTok**holding fixed**: Kuaishou data returns sporadically for about 25 seconds (seen at seconds 4, 16–19, 21, 25) and sometimes gets stuck on the first request; A direct comparison is inconclusive because the device is limited to loop loading (0 to 98 videos with both encodings), so there is no trade-off in reliability for a few seconds.
- Unchanged after measurement: 9:16 frame filter (1080p decoding and over half image shrink, try variations not faster), `veryfast` encoding (selected in Phase B), console page (8–12 ms per load on small real database; measured on 20,000 video dummy database: page build 39 ms, `status` 17 ms, `record_stats` 200 items 9 ms; before review 52, 22 and 927 ms).

## 4. Collection source

| Source | How to get | Notes |
|---|---|---|
| Douyin | Trang 精选 (`/jingxuan`), capture JSON `aweme/v2/web/module/feed`; each topic tab (音乐, 小剧场, 动物, 美食, 旅行, 亲子, 美妆穿搭, 体育, 游戏, 二次元, 影视, 生活vlog,知识) for about 40 private videos | Self-signed browser required; only get `aweme_type == 0` (video), remove ads and photo album |
| Kuaishou | Page `brilliant`, catch GraphQL `brilliantTypeData` | Sometimes disconnects: retry up to 3 times |
| TikTok | Explore page, click on the themed chips (Singing & Dancing, Comedy, Animals, Food...), catch `explore/item_list` | **Only runs when the exit IP is US** |
| Instagram | Public Reels page, get reel code, `yt-dlp` get metadata and load | **Only run when exit IP is US** |

Douyin and Kuaishou only serve domestic content, so every IP is the correct Chinese source. TikTok and Instagram exchange content by IP, so the agent checks the country of the exit IP (`exit_country`) before each scan. If a CAPTCHA or login request is encountered, the flow throws an error instead of trying to pass.

## 5. Data

- `data/worker/trendvn.sqlite3` (WAL): `jobs` (one video per stream), `observations` (rank/view history per scan), `events` (log), `settings`, `accounts` (TikTok accounts: receiving topics, separate limits), `api_calls` (count Gemini calls), `post_stats` (post views), `notif_log` (anti-notification spam).
- `data/agent/profiles/`: one Chrome profile for each TikTok account (`publisher` for `main`, `publisher-<id>` for additional accounts), `collector-cn`, `collector-us`.
- `data/worker/inbox/` original video download; `data/worker/jobs/<id>/` builds (`final.mp4`, `vi.ass`, `manifest.json` including prompt version).
- **Disk cleanup** (`store/retention.py`, running in `/api/housekeeping`): candidate has not been downloaded for more than 3 days and video is more than 21 days old and no one has decided to become `rejected`; posted/abandoned/duplicated video/error lost original file and version after 7 days (keep `manifest.json`, `poster.jpg` and stream in database to avoid duplicate posting); delete old history (observation 30 days, log 60, task 14); the clock of these rules is `updated`, which a scan that sees the video again no longer resets; Orphaned files and old snapshots. If less than 1 GB is free, stop downloading, if less than 512 MB, stop building; The "Drives" box on the Overview page shows how much is left. The worker restarts and automatically reschedules the unfinished video (each video can be tried a maximum of 2 times, then waits for the master to watch); orphan file age based on inode change time (`ctime`), not `mtime` (yt-dlp copies server date to `mtime`); Failed file deletion is not recorded as completed but retried after 24 hours; Another live video file in use is never deleted; If there is less than 1 GB free space, housekeeping will send a phone message.
- `data/worker/gemini.key`, `data/worker/notify.json`: secret, permission 0600, never returned via API.
- `data/agent/agent.log`, `data/agent/shots/` (picture taken when posting the error; the test run picture is at `data/worker/exports/` for the console to display).

## 6. Expand

- **Add new source (2 files + test):**create a file in `collector/sources/` with `parse_<source>` (returns list of items with `source_id`, `url`, `title`, `likes`, `views`, `duration`, `created`, `media`), `scan_<source>` and `CDN` (video streaming domain), register a line in `collector/sources/__init__.py` (put `geo_locked`), and add**a line** into `REGISTRY` at `services/worker/src/trendvn_worker/domain/platforms.py` (name, country, domain, default view threshold). The panel labels, threshold input boxes, default settings, banned hashtags, and names in notifications all come from `REGISTRY`; `tests/agent/test_collector.py::RegistryContractTests` checks that both sides match.
- **Add new tab (1 file + 1 line):** a module in `ui/tabs/` has `render(view)` and a line in `TABS` in `ui/page.py` (label, icon, badge count function); navigation item and `<section>` are generated from it.
- **Add new settings (5 places, intentionally):** `DEFAULTS` and `validate_settings` (domain/settings.py), `DASHBOARD_SETTINGS` (store/reporting.py), input box (ui/tabs/more.py), read forms (web/forms.py); test `tests/worker/test_settings.py`. It has not been collected into a declaration table because each installation has its own testing rules and the collection does not shorten anything significantly.
- **Change scoring method:** edit `score` (a pure function, tested in `tests/agent/test_collector.py::ScoringTests`).
- **Change security rules when posting:** only edit `publish_claim`; agent and n8n do not need to be changed.

## 7. Code and data layout

```
services/worker/
  Dockerfile
  src/trendvn_worker/ → packaged as Docker image (Python standard library only)
    domain/plain rules, nothing read/write: platforms, settings, analysis, route, readability, hardsubs, captions, schedule, states
    store/ SQLite: base, schema (migration with version number), ingest, queue, publishing, captions, health, task_log, feedback, reporting
    ai/ Gemini: gemini (call, budget, model backup), prompts, analyzer, tts, errors
    media/         ffmpeg: ffmpeg, fingerprint, geometry, subtitles, render
    pipeline.py a video going from the queue to the tested build
    web/           HTTP: handler, security, forms, api, media_files, pages, responses, app, server
    ui/ interface: view, components, cards, tabs/ (one file per tab), static/app.css, static/app.js
    notify.py  tasks.py  version.py
services/agent/
  src/trendvn_agent/ → runs on the machine (real Chrome), with the project's .venv
    collector/     sources/ (douyin, kuaishou, tiktok, instagram), rules, capture, download, run, cli
    publisher/     session, profile, studio, challenge, post, jobs, screenshots, cli
    browser.py  config.py  log.py  worker_client.py  server.py
n8n/ build.py (generate workflow) · manage.py (load/enable/export) · workflows/*.json (result)
scripts/           install · backup · restore · migrate · uninstall · test · doctor · package · setup_env · agent · lib · service/
data/ worker/ (attached to container) · agent/ (Chrome profile, log, snapshot) · backups/ ← generated at runtime, not packaged
```

Rules for placing files (one thing per file, written in the docstring line at the beginning of the file): business rules that do not depend on I/O are in `domain/` for quick testing; all SQLite accesses are located at `store/` (one concern per mixin, combined into `Store`); Everything that needs Chrome is located at `services/agent`; a new source = a file in `collector/sources/`; Each tab of the interface is a file in `ui/tabs/`; n8n indicates timing and stepping (see [N8N.md](N8N.md)); all operating commands pass through `./trendvn` (see [COMMANDS.md](COMMANDS.md)).
