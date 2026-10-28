# TrendVN

Finds trending videos (Douyin and Kuaishou in China; TikTok and Instagram Reels through a US connection), understands them with Google Gemini, adds Vietnamese subtitles or a Vietnamese voice-over, and posts them to your TikTok channel or channels through a real Chrome, on a schedule you control. A dashboard on your own machine lets you review, edit captions and press Post now.

Three parts, each with one job: the **worker** (Docker) decides and remembers, the **agent** (on your machine, with Chrome) looks, downloads and posts, and a **schedule** (n8n, Docker) only starts them on a timer.

## Start

Needs Docker (Desktop on a Mac), Python 3.10 or newer, Google Chrome and a Gemini API key. Keep the folder outside `Documents`, `Desktop` and `Downloads` on a Mac.

```bash
git clone -b develop https://github.com/Thuy200226/trendvn.git ~/trendvn && cd ~/trendvn
./trendvn install --no-activate   # build and start everything; the schedule stays off
./trendvn doctor                  # check; one red line (schedule off) and yellow ones are normal for now
./trendvn open                    # dashboard: add the Gemini key, turn on video processing, set your TikTok account
./trendvn tiktok login            # sign in once in the Chrome window (you type the password)
./trendvn tiktok dry-run          # rehearse without posting (after the first video is ready)
./trendvn n8n activate            # turn the schedule on (after turning Auto-post on in the dashboard)
```

The reasons for each step and what to do when one fails are in [docs/OPERATIONS.md](docs/OPERATIONS.md).

## Documents

| Read | For |
|---|---|
| [docs/FLOWS.md](docs/FLOWS.md) | what happens: the life of a video, the automatic schedules, the buttons, and what to do when something goes wrong. No technology. |
| [docs/TECH.md](docs/TECH.md) | what it is made of and why: components, design decisions, data, interfaces, AI usage, performance, security, deployment, how to extend. |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | install, run, update, back up, troubleshoot, every command. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | status, open items, decisions that are yours, what is not verified. Evidence and older logs are in `docs/history/`. |
| [CHANGELOG.md](CHANGELOG.md) | what changed in each version. |
| [AGENTS.md](AGENTS.md) | rules for anyone, human or agent, who changes the code or the documents. |

## Limits to know

- **One automatic runner per TikTok channel.** Other machines are for testing only.
- **TikTok sometimes shows a verification page.** The system never solves or passes it: it pauses posting and asks you to pass it once.
- **US sources need a US exit IP** (`TRENDVN_US_PROXY` in `.env`); without one they are skipped, never mislabeled.
- **Copyright and platform terms are your responsibility.** The system blocks duplicates and hard-stop content by rule; it does not check rights.
- **Everything listens on this machine only** (`127.0.0.1`; on Linux the agent listens on the private Docker bridge). For remote access use an SSH tunnel or a VPN ([docs/TECH.md](docs/TECH.md) section 9).
