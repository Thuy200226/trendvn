# The n8n system: how it was built

n8n here is **a private n8n of the project**, running in Docker with workers, not shared with any other n8n and does not need an account
n8n online. Its entire content (6 workflows + 1 credential) **is generated from the code**, so rebuilding it on any machine will give identical results.

```
n8n/build.py ──birth──► n8n/workflows/*.json ──n8n import──► n8n (Docker) ──schedule──► worker / agent
   (canonical source) (result, available in repo) manage.py HTTP, with token
```

## Ingredients

| File | Role |
|---|---|
| `n8n/build.py` | **Standard source.** Each workflow is several lines describing the node and connecting edges. Read `.env` to get the agent port and time zone. The node id is deduced from the name so it is regenerated for the same file; `--check` reports an error if the JSON in the repo has the wrong code |
| `n8n/workflows/*.json` | The output, **does not contain the secret**. Compose mounts this directory to container n8n (`/import`, read-only) |
| `n8n/manage.py` | Load / enable / disable / list / export via n8n official CLI (`docker compose exec n8n n8n …`) |
| credential `TrendVN · Private worker` | Created at load from `TRENDVN_TOKEN` in `.env`; located in volume n8n (encrypted with `N8N_ENCRYPTION_KEY`), not in workflow |

## Six workflows

| Id | Name | Enable | What does |
|---|---|---|---|
| `trendvn01daily` | 01 · Collect and process | every 3 hours | checks TikTok sessions → compares unconfirmed posts → collects 4 sources → cleans up interrupted tasks → processes (Vietsub/cage voice) |
| `trendvn02publish` | 02 · Post during golden hours | every 30 minutes | asks if worker can post (switch, golden hour, day limit, spacing) then let agent post |
| `trendvn03daily` | 03 · Final date | 23:30 | read views to learn which sources are effective, send summary |
| `trendvn00status` | 00 · Check connectivity and availability | press | read the real status of workers and agents |
| `trendvn10inbox` | 10 · Get observations | webhook with authentication | import video list from external tool |
| `trendvn20process` | 20 · Process Vietnamese video and subtitles | hand press | runs the processing step separately |

Only **01, 02, 03** is automatic calendar; `./trendvn n8n activate` turns on these three. The buttons on the control panel are additional, sharing keys with the calendar, so they never overlap.

## Workflow

```bash
# Change system n8n: fix n8n/build.py, then
./trendvn n8n build            # regenerates JSON
./trendvn n8n import           # loaded into n8n is running (calendar is still on)
./trendvn test lint            # ensures the JSON in the repo matches the code

# You edit directly in the n8n interface and want to keep it?
./trendvn n8n export           # save to n8n/exported/*.json, then transfer the part to keep to n8n/build.py

# Enable/disable calendar, view status
./trendvn n8n activate         # 01, 02, 03
./trendvn n8n deactivate
./trendvn n8n status
```

`./trendvn install` and `./trendvn update` already call `build` + `import` (+ `activate`), you don't need to run it manually during the first installation.

## Log in to n8n from another device

No need to pack an account: each device has its own n8n, the first time you open `http://localhost:5680` you create a master account.
Workflow calls `http://worker:8080` and `http://trendvn-agent:<port>`, two names that only exist in the project's Docker network, so **don't** put this workflow in another n8n
(it won't find workers). If you want to view the device's password at home remotely: use SSH tunnel or VPN (see [DEPLOY.md](DEPLOY.md)).

## Upgrade version n8n

The version is pinned in `compose.yaml` (`docker.n8n.io/n8nio/n8n:<version>`), because the workflow was generated and tested for that version.
To upgrade: change the version number, `./trendvn backup`, `./trendvn up`, `./trendvn n8n import`, `./trendvn n8n status`, then wait a calendar cycle and see Executions.
