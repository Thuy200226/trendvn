# API

All `POST` calls (except console forms) use `Authorization: Bearer <TRENDVN_TOKEN>` and JSON. The response is always JSON; Check error returns `400` with `{"error": "..."}`.

## Worker — `http://127.0.0.1:5681`

### Read

| Method, path | Authentication | Return |
|---|---|---|
| `GET /health` | no | `{ok, project, version}` |
| `GET /api/status` | token or internal control board | Compact status: `counts`, `jobs` (latest 100), `discovery`, `publisher`, `published_today`, `daily_limit` (total limit of active accounts), `accounts` (each account: `id, username, topics, enabled, daily_limit, published_today, logged_in`...), `wanted_topics` (topic with receiving account: collector finds these topics correctly), `thresholds`, `weights`, `unresolved_publishes`... Collector and n8n use this |
| `GET /api/dashboard` | as above | Complete console data: `review`, `approval`, `pipeline`, `performance`, `events`, `settings`, `by_platform`... |
| `GET /` | only `Host` enables | HTML console |
| `GET /media/<id>/final`, `/source`, `/media/voice-sample` | only `Host` allows | Video/audio, supports `Range` |

### Ghi (token)

| Path | Content | Note |
|---|---|---|
| `POST /api/ingest` | `{platform, stream, observed_at, topic?, items:[{source_id, url, country, title, rank, views, evidence_url, meta}]}` | ≤ 100 entries; `topic` (optional) is the category of the stream itself (Douyin tab, TikTok chip), a code in the theme menu; From that and from the keywords in the worker title, the topic suggestion of each video is deduced. The first pass of each flow is the baseline. Return `{baseline, new, existing, candidates:[{id, source_id}]}` |
| `POST /api/media/pending` | `{limit, platform?}` | Candidates without a video, highest score first (filter by platform if available) |
| `POST /api/attach` | `{id, filename}` | Mount the downloaded file in `data/worker/inbox`; Pay `queued` or `duplicate` |
| `POST /api/media/failed` | `{id, reason}` | Load write error (3rd time to `failed`) |
| `POST /api/process` | `{max}` (1–8) | Maximum processing `max` consecutive videos; stop when `disabled`, `blocked`, `idle`, `rate_limited` |
| `POST /api/housekeeping` | `{}` | Release hangs (process over 30 minutes requeue, post over 45 minutes waiting for confirmation) and disk cleanup (`pruned`: expired, files, history, orphan files; see ARCHITECTURE section 5) |
| `POST /api/heartbeat` | `{component: discovery\|publisher, ok, detail}` | Update status; `detail` object form **merged** with previous |
| `POST /api/publish/claim` | `{}` | `{status: claimed\|disabled\|blocked\|wait\|limit\|idle, ...}`; when `claimed` comes with `id, lease, caption, output_file, output_hash, account` (account code, agent used to open the correct Chrome profile), `target` (TikTok name), `visibility`. The schedule automatically tries the accounts in turn (the account with the longest posting first), each account according to its golden hour, with its own day limit and spacing, and selects the highest scoring video on that account's topic to receive |
| `POST /api/publish/finish` | `{id, lease, outcome: published\|failed\|unknown\|duplicate, url, reason}` | `lease` must be true; `url` should be address `*.tiktok.com` |
| `POST /api/publish/peek` | `{}` | Next article (test run, no change in status) |
| `POST /api/publish/unresolved`, `/api/publish/resolve` | `{}` / `{id, outcome: published\|failed, url}` | Unconfirmed post |
| `POST /api/stats` | `{items:[{video_id, views, likes, comments, shares}]}` | Match posted by `/video/<id>` |
| `POST /api/publisher/challenge` | `{active: bool, account?: string}` | Turn on/off the status "TikTok is asking for verification": when turned on, `publish/claim` returns `blocked` until turned off. `account` is the account code that has a CAPTCHA profile: the message and suggested command correctly state `--account`, and turning it off for another account will not unblock it (if you don't send `account`, you can turn it off for any account) |
| `POST /api/accounts` | `{}` | `{accounts, wanted_topics}` |
| `POST /api/accounts/add` | `{username, topics:[...], id?, label?, enabled?, daily_limit?, min_gap?, windows?, visibility?}` | Add account (maximum 10). Limit blank/`null` = use general setting |
| `POST /api/accounts/update` | `{id, ...c\u00e1c tr\u01b0\u1eddng nh\u01b0 tr\u00ean}` | Edit; Don't disable the last active account |
| `POST /api/accounts/login` | `{id, ok: bool}` | Agent tells the browser if the correct account is logged in (the calendar automatically ignores logged out accounts) |
| `POST /api/accounts/delete` | `{id}` | Delete; Do not delete the last account or account with unconfirmed posts |
| `POST /api/settings` | Part of the installation (see `validate_settings`) | Return `{changed:[...]}` |
| `POST /api/notify` | `{kind:"summary"}` or `{kind:"text", text}` | Send via configured channels; which channel is successful |

### Background task (control panel button)

| Path | Content | Note |
|---|---|---|
| `POST /api/tasks/start` (token) | `{kind: update\|collect\|process\|publish\|dryrun\|stats, job_id?}` | Pay `{id}`; `409`-equivalent to error 400 "There is a browser session in progress..." when duplicate key |
| `GET /api/tasks` (token or internal interface) | | `{running, tasks:[{id, kind, state, steps, result, error}]}` |
| `GET /fragment/tasks` | | Progress table HTML (interface for live updates) |
| `POST /api/publish/claim`, `/api/publish/peek` | `{job_id?}` | Yes `job_id`: receive/watch the correct video (post manually: ignore switches, golden hours, limits, spacing; security guards remain) |
| `POST /api/publish/finish` | `outcome: published\|failed\|deferred\|unknown\|duplicate` | `failed` is counted (3 times, switch to Watch, rest 1 hour between times); `deferred` does not count (TikTok requires verification, duplicate description when posting) |
| `GET /media/<id>/final\|source\|poster`, `/media/shot/<shot_*.png>` | | Video, preview photo, preview photo |

## Agent — `http://<TRENDVN_AGENT_BIND>:5682` (default `172.20.0.1`)

Only one browser at a time; busy paying `409`.

| Link | Content | Job |
|---|---|---|
| `GET /health` | not authenticated | `{ok, busy}` |
| `POST /api/collect` | `{platforms?: [...], download?: bool}` | Scan, score, import into worker, download new videos. Return report by source |
| `POST /api/publish` | `{job_id?}` | Please worker `claim` (yes `job_id` = post that exact video according to the button); If possible, open Chrome to post, confirm on profile, report `finish`. Never throw errors: error before clicking Post is `failed`, after clicking is `unknown` |
| `POST /api/dry-run` | `{job_id?}` | Upload video (next or selected) to TikTok Studio, fill in description, take photo in `data/worker/exports/shot_*.png` then stop, **don't click Post** |
| `POST /api/session` | `{}` | Check if you are logged in to TikTok, send heartbeat |
| `POST /api/verify` | `{}` | Check "unconfirmed" post with public profile |
| `POST /api/stats` | `{}` | Read views/hearts from public profile, send worker |

## Command line

| Command | Effect |
|---|---|
| `PYTHONPATH=services/agent/src .venv/bin/python -m trendvn_agent.collector [douyin kuaishou tiktok instagram]` | Real scan and import into worker |
| `./trendvn tiktok login\|trust\|status\|dry-run\|verify\|stats` | Login, solve one-time verification, check session, test run, compare, read views |
| `./trendvn doctor` | Diagnostics |
| `./trendvn n8n build && ./trendvn n8n import` | Regenerate and reload workflow |

## Example

```bash
TOKEN=$(grep '^TRENDVN_TOKEN=' .env | cut -d= -f2)
curl -s -H "Authorization: Bearer $TOKEN" localhost:5681/api/status | python3 -m json.tool | head
curl -s -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     -d '{"daily_limit": 1, "post_windows": [[19, 22]]}' localhost:5681/api/settings
```
