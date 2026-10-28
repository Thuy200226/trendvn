# Security, privacy and risks to know

## 1. The biggest risk is not in the software

**Copyright and account.** The system takes videos created by others and reposts them on your channel. There is no step to ask for permission from the author, and no software claims copyright or usage rights. Possible consequences: video removed, copyright removal, reduced distribution, channel blocking; For videos with commercial music (the most vulnerable group), the music may be muted or blocked by TikTok. Reposting depends on the terms of each source platform and the laws of your location. You are responsible for the content posted. Suggestions to reduce risk:

- Turn on "Verify before posting" for the first time and watch each video.
- Priority is given to videos with the creator's own original music or entertainment without commercial music; lower "Number of posts per day" to low.
- Only hitting the "hard limit" (sex, children in danger, real blood, hatred, self-harm/crime, dangerous advice, private life) will be blocked waiting for you; Politics, drama, conflict, hot news are posted normally. The more controversial the content, the higher the risk of it being taken down/reduced in distribution, which is the trade-off you've chosen.

**Browser-based method** (no API) depends on the page interface; Platforms can change the interface or block automation. The system is designed so that when you encounter an abnormality, you *stop and report*, do not try to overtake.

## 2. What the system prohibits itself

| Behavior | How to ensure |
|---|---|
| Enter your password | There is no code to do this; Sign in only through your own Chrome window (`./trendvn tiktok login`) |
| Hide automation from website | Do not use: do not disable flag `AutomationControlled`, do not edit User-Agent, do not simulate human operations. The browser correctly declares itself as Chrome because of the control program |
| CAPTCHA bypass/verification | `looks_blocked` (collect) and `has_challenge` (poster) detect, report errors and **pause posting** until you solve it yourself (`./trendvn tiktok trust`); There is no decode or dodge code |
| Mislabeled US source | Refuse to scan TikTok/Instagram if exit IP ≠ US (`exit_country`); `ingest` also rejects `country` platform mismatch |
| Post when in doubt | `publish_unknown` block all subsequent postings; do not try again the clicked Post |
| Posted outside the law | Automatic calendar: switches, golden hours, day limits, spacing are all checked at workers in a transaction. **Manual Post** (Post Now button) bypasses those rules because you clicked, but is still blocked when there is a post in progress, there is an unconfirmed post, or TikTok is asking for verification; Each click only posts the selected video (double click does not post twice) |
| Post changed file | SHA-256 hash of `final.mp4` must match when building |
| Believe the words in the video | Prompt considers the video to be unreliable data and repeats it immediately after the video; Gemini output is hard-checked: duplicate JSON key rejected, multiple objects, non-string description; Description and subtitles are filtered for links, @name, phone number, email, hidden/inverted characters (`domain/text.py`) |

## 3. Attack surface and measures

| Surface | Measure |
|---|---|
| **Service Port** | Default is only `127.0.0.1`. Agent only listens on the project's Docker bridge address, does not expose LAN |
| **API worker and agent** | Bearer token 256-bit (`TRENDVN_TOKEN`), constant time comparison (`hmac.compare_digest`) |
| **Control panel** | Open without password only if `Host` is localhost **and**connect to from this machine (127.0.0.1, `::1` or the project's Docker bridge port); a fake `Host` from the network is not enough; Requests carrying reverse proxy headers (`X-Forwarded-For`, `X-Real-IP`, `Forwarded`...) are never considered local. All other `Host` in `TRENDVN_UI_HOSTS` required `TRENDVN_UI_PASSWORD` (session saved** on server** (random code, valid for 7 days, maximum 64 sessions): `/logout` and expires disable that code for real, restart the worker (also how to change password) log out all; cookie HttpOnly SameSite=Strict; locked 1 minute after 5 incorrect attempts), if you don't set a password, it will be rejected. Only answer `Host` in the whitelist; all check forms `Origin` and CSRF token; CSP no longer has `script-src 'unsafe-inline'` (only script allowed by hash, no `onclick` in HTML), `base-uri 'none'`, `Permissions-Policy`, `X-Frame-Options: DENY`, `nosniff`; All displayed values are escaped (with anti-code injection test) |
| **HTTP connection**| Socket expiration 30 seconds**for each read**(prevent idle client;**no** block slow drip bytes: limit 48 threads at the same time, return 503 for excess, is a blocking, and default port only listens to localhost), listen queue 64, maximum request body 2 MiB (worker) / 1 MiB (agent), negative or strange `Content-Length` rejected, does not reveal Python version; log cleans control characters (including C1), and logs the source address of all 401/403 |
| **Play preview video** | Only path is in `data/worker/`, id must be 32 hex characters, supports Range, only from internal interface |
| **Installation** | Each exchange key has a strict type and range; strange key rejected (`validate_settings`) |
| **Download video**| HTTPS only, strict URL syntax (no `\`, no `@`, no port, no IP address, no spaces/control characters), platform's own CDN domain only (`CDN` in each source file),** is also checked for each redirect before calling ** (`fetch_media`), limited to 250 MB, must be a real MP4 (checks `ftyp` on the first 12 bytes), writes to file `.part` and then renames. yt-dlp's proxy goes through environment variables, not on the command line (`ps` doesn't see password) |
| **File path** | `attach` only receives safe file names in `inbox/`; anti `..` |
| **Notice** | Webhook/ntfy only receives `https` on public domain (no IP of any kind, no `localhost`/`.local`/`.internal`), at send name must resolve to public address, no 3xx redirects, message never @everyone (`allowed_mentions`); secretly save `data/worker/notify.json` mode 0600, never return via API |
| **Gemini key** | `data/worker/gemini.key` mode 0600; Do not log, do not send to n8n; The key just goes in the header sent to Google. On error, display only the line `message` returned by Google (which never contains the key) |
| **Input content (n8n webhook 10)** | Authentication required; JSON cannot command post: queue video only after passing all checks |
| **n8n** | `N8N_ENCRYPTION_KEY` project-specific, telemetry off, master account created by you, export workflow contains no secrets |
| **Isolate** | n8n, volume, network, container, credentials all private, read nothing from other project |
| **Container** | worker runs using your uid (not root), root filesystem is read-only; both containers drop all Linux capabilities, `no-new-privileges`, RAM limits (worker 4 GB, n8n 2 GB), and number of processes (512); log rotates automatically so it doesn't fill disk |

## 4. Where is the secret, how to protect it

| Confidential | Location | Note |
|---|---|---|
| `N8N_ENCRYPTION_KEY`, `TRENDVN_TOKEN`, proxy, notification token | `.env` (0600, in `.gitignore`) | Back up the same data; do not post to git |
| Gemini Key | `data/worker/gemini.key` (0600) | |
| Message channel | `data/worker/notify.json` (0600) | |
| TikTok session | `data/agent/profiles/publisher` (account `main`) and `publisher-<id>` (each account adds a folder) | Whoever has this folder can log in to your channel. No default backup (new included `--with-session`) |
| Backup | `data/backups/*.tar.gz` (0600) | Contains secret; Encrypt or store in a safe place |

If suspected of exposing `TRENDVN_TOKEN`: edit the value in `.env`, run `./trendvn up`, `./trendvn n8n import` (update credential n8n) then `./trendvn agent restart`.

## 5. Data leaves your device

| Destination | Data | When |
|---|---|---|
| Google Gemini | 384px preview of the video to analyze; speech text to create voiceover | Only if you enable "Video processing" and have video in queue |
| Source platform | Access the page as a normal browser (via proxy if you set it) | Per scan |
| TikTok | Video and description when posting; read your public profile to confirm and get views | On posting and on closing date |
| Telegram/Discord/Slack/ntfy | Notification content (video title, reason, post path) | Only if you configure channel |
| ipinfo.io, api.country.is | the country of your exit IP, only to check that TikTok or Instagram would be read from the US | At the start of a scan that includes TikTok or Instagram (not for Douyin and Kuaishou alone) |
| None other than | No telemetry. n8n has diagnostics, release-note checks, the template library and the MCP registry switched off (`compose.yaml`); the only call n8n was seen making before that was to `api.n8n.io`, other n8n calls were not looked for | |

## 6. System thing **Are not** can do it

- Does not endorse copyright or correctness of content; Gemini's certainty is not a license.
- Can't control TikTok changing the interface (poster may be broken; when it's broken, the post will not be mistakenly posted).
- Does not override Google's cost limit; The limit of 12 times/24 hours is only a local blocking point.

## 7. Known and accepted risks (updated 2026-10-02)

| Risk | Why accept | Minimize |
|---|---|---|
| A shared token for n8n, worker and agent | One master, one machine system; Permission separation requires additional allocators and will complicate the installation of | 256-bit Token in `.env` (0600); port listens only to localhost and private bridge; To reveal the token, exchange it according to section 4 |
| Token holders can click "post now" via API, bypassing the automatic schedule | That is the manual post button; still blocked when there is a post being posted/unconfirmed/being verified | Only owner has token |
| yt-dlp doesn't pin version | Instagram keeps changing, old version broke within a few weeks | Only runs with URLs that have passed domain checks, the result should still be real MP4; Proactive updates using `./trendvn update` |
| DNS resolution at message sending and connection time is two steps (DNS rebinding) | Channel is only configured by the master; Completely blocked, need to manually connect by IP | Required public domain, no IP, no redirects, double check the address just before sending |
| `style-src 'unsafe-inline'` still in CSP | The interface uses the `style` attribute in many places; Replacing it with a CSS class is a big deal, but the benefit is small because the script is locked. | All displayed values are escaped; There is no inline script other than hashed file |
| No TLS between browser and console at localhost | Same machine; TLS needs certificate | When opening out, use SSH tunnel or TLS proxy and set `TRENDVN_UI_HTTPS=1` |
| Docker Desktop (macOS/Windows) can present a source address other than the bridge port | Not tested on real machine | If the console says "not this machine", add that address to `TRENDVN_TRUSTED_PEERS` (notice with address already written) |
| yt-dlp reads proxy from environment variable `HTTP(S)_PROXY`/`ALL_PROXY` | Verified by testing that the password is no longer on the command line; **yet** runs with a real proxy (no US proxy yet) | With a proxy, run a test reel and see `./trendvn doctor` |
| The text filter (`domain/text.py`) is heuristic | There may also be a strange link/phone number, or a rare cluster cut off (lowercase ASCII domain name, 10-11 digit number starting with 0) | Description can still be viewed by the owner before posting; The final filter is located at `build_caption` |
| `PrivateTmp` for agent service | Chrome with windows needs X11 socket in `/tmp`; isolate `/tmp` damage it | `NoNewPrivileges=true`; agent only listens to private bridge |
