"""Build the n8n workflows of TrendVN from code (the source of truth is THIS file, not the JSON files).

    python3 n8n/build.py            write n8n/workflows/*.json for this machine (reads .env: agent port, timezone)
    python3 n8n/build.py --check    exit 1 if the committed JSON differs from what this file generates (defaults, ignores .env)

The JSON contains no secret: the worker token lives in an n8n credential that `./trendvn n8n import` creates from .env.
Node ids are derived from names, so rebuilding gives byte-identical files (clean diffs, safe re-import).
"""

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "n8n" / "workflows"
CRED = {"httpHeaderAuth": {"id": "trendvnWorkerAuth", "name": "TrendVN · Worker ri\u00eang"}}
WORKER = "http://worker:8080"  # container-to-container address inside the project network
CHECK = "--check" in sys.argv[1:]
_NS = uuid.UUID("6f0c2a1e-7d3b-4c55-9a0e-2b7c1d4e5f60")


def _env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from envfile import parse

    return {} if CHECK else parse(ROOT / ".env")


ENV = _env()
AGENT = "http://trendvn-agent:%s" % ENV.get("TRENDVN_AGENT_PORT", "5682")  # host agent, reachable only from this project's containers
TZ = ENV.get("TRENDVN_TZ", "Asia/Ho_Chi_Minh")
DASH = "http://localhost:%s" % ENV.get("TRENDVN_WORKER_PORT", "5681")
WRITTEN = {}


def node(name, kind, params, x, y=0, version=1, **extra):
    return {
        "id": uuid.uuid5(_NS, kind + "|" + name).hex,
        "name": name,
        "type": "n8n-nodes-base." + kind,
        "typeVersion": version,
        "position": [x, y],
        "parameters": params,
        **extra,
    }


def request(name, path, x, method="POST", base=WORKER, body="{}", y=0, tolerant=False, timeout=900000):
    params = {
        "url": base + path,
        "method": method,
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "options": {"timeout": timeout},
    }
    if method == "POST":
        params.update({"sendBody": True, "specifyBody": "json", "jsonBody": body})
    extra = {"onError": "continueRegularOutput"} if tolerant else {}
    return node(name, "httpRequest", params, x, y, version=4.2, credentials=CRED, **extra)


def save(wid, name, nodes, edges):
    con = {}
    for a, b in edges:
        con.setdefault(a, {"main": [[]]})["main"][0].append({"node": b, "type": "main", "index": 0})
    workflow = {
        "id": wid,
        "name": name,
        "nodes": nodes,
        "connections": con,
        "active": False,
        "settings": {
            "executionOrder": "v1",
            "timezone": TZ,
            "saveDataErrorExecution": "all",
            "saveDataSuccessExecution": "all",
            "saveManualExecutions": True,
        },
        "pinData": {},
    }
    WRITTEN[wid + ".json"] = json.dumps(workflow, ensure_ascii=True, indent=2) + "\n"


def chain(nodes):
    return [
        (a["name"], b["name"])
        for a, b in zip(nodes, nodes[1:])
        if a["type"] != "n8n-nodes-base.stickyNote" and b["type"] != "n8n-nodes-base.stickyNote"
    ]


# 00 · readiness check (worker + host agent)
manual = node("Ch\u1ea1y ki\u1ec3m tra", "manualTrigger", {}, 0)
status = request("\u0110\u1ecdc tr\u1ea1ng th\u00e1i worker", "/api/status", 260, "GET")
agent = node(
    "Ki\u1ec3m tra agent tr\u00ecnh duy\u1ec7t",
    "httpRequest",
    {"url": AGENT + "/health", "method": "GET", "options": {"timeout": 15000}},
    520,
    version=4.2,
    onError="continueRegularOutput",
)
code = node(
    "T\u1ed5ng h\u1ee3p ph\u1ea7n c\u00f2n thi\u1ebfu",
    "code",
    {"jsCode": """const s=$('\u0110\u1ecdc tr\u1ea1ng th\u00e1i worker').first().json;
const a=$input.first().json;
const missing=[];
if(!a.ok) missing.push('Agent tr\u00ecnh duy\u1ec7t tr\u00ean m\u00e1y ch\u01b0a ch\u1ea1y (systemd: trendvn-agent)');
if(!s.gemini_configured) missing.push('Ch\u01b0a c\u00f3 kh\u00f3a Gemini API');
if(!s.processing_enabled) missing.push('X\u1eed l\u00fd video \u0111ang t\u1eaft');
if(s.discovery!=='connected') missing.push('B\u1ed9 thu th\u1eadp ch\u01b0a c\u00f3 l\u1ea7n ch\u1ea1y th\u00e0nh c\u00f4ng');
if(s.publisher!=='connected') missing.push('Ch\u01b0a \u0111\u0103ng nh\u1eadp TikTok trong h\u1ed3 s\u01a1 ri\u00eang c\u1ee7a tr\u00ecnh \u0111\u0103ng');
if(!s.publisher_enabled) missing.push('C\u00f4ng t\u1eafc T\u1ef1 \u0111\u0103ng \u0111ang t\u1eaft (ch\u1ec9 b\u1ea1n b\u1eadt tr\u00ean b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n)');
if(s.unresolved_publishes>0) missing.push('C\u00f3 b\u00e0i ch\u01b0a x\u00e1c nh\u1eadn \u0111\u00e3 \u0111\u0103ng hay ch\u01b0a');
return [{json:{...s,agent_ok:!!a.ok,ready_for_unattended_publishing:missing.length===0,missing}}];"""},
    780,
    version=2,
)
note = node(
    "Ghi ch\u00fa",
    "stickyNote",
    {
        "content": "## Ki\u1ec3m tra m\u1ee9c s\u1eb5n s\u00e0ng\n\u0110\u1ecdc tr\u1ea1ng th\u00e1i th\u1eadt t\u1eeb worker v\u00e0 agent. Kh\u00f4ng \u0111\u1ed5i d\u1eef li\u1ec7u.\nB\u1ea3ng \u0111i\u1ec1u khi\u1ec3n: "
        + DASH,
        "height": 200,
        "width": 520,
    },
    100,
    -300,
)
save(
    "trendvn00status",
    "TrendVN | 00 · Ki\u1ec3m tra k\u1ebft n\u1ed1i v\u00e0 m\u1ee9c s\u1eb5n s\u00e0ng",
    [manual, status, agent, code, note],
    chain([manual, status, agent, code]),
)

# 01 · collect + process (every 3 hours)
schedule = node(
    "M\u1ed7i 3 gi\u1edd", "scheduleTrigger", {"rule": {"interval": [{"field": "hours", "hoursInterval": 3}]}}, 0, 200, version=1.2
)
manual = node("Ch\u1ea1y th\u1eed to\u00e0n chu tr\u00ecnh", "manualTrigger", {}, 0, 0)
session = request(
    "Ki\u1ec3m tra phi\u00ean TikTok", "/api/session", 260, base=AGENT, tolerant=True, timeout=600000
)  # a Chrome launch per account
verify = request(
    "\u0110\u1ed1i chi\u1ebfu b\u00e0i ch\u01b0a x\u00e1c nh\u1eadn", "/api/verify", 520, base=AGENT, tolerant=True, timeout=300000
)
collect = request("Thu th\u1eadp xu h\u01b0\u1edbng v\u00e0 t\u1ea3i video m\u1edbi", "/api/collect", 780, base=AGENT, tolerant=True)
house = request("Ph\u00e1t hi\u1ec7n t\u00e1c v\u1ee5 gi\u00e1n \u0111o\u1ea1n", "/api/housekeeping", 1040, tolerant=True)
process = request(
    "Ph\u00e2n lo\u1ea1i nh\u1ea1c, t\u1ea1o Vietsub ho\u1eb7c l\u1ed3ng ti\u1ebfng", "/api/process", 1300, body='{"max":4}', tolerant=True
)
note = node(
    "Thu th\u1eadp v\u00e0 x\u1eed l\u00fd",
    "stickyNote",
    {
        "content": "## Chu tr\u00ecnh 3 gi\u1edd/l\u1ea7n\n1. Ki\u1ec3m tra phi\u00ean TikTok, \u0111\u1ed1i chi\u1ebfu b\u00e0i ch\u01b0a r\u00f5 k\u1ebft qu\u1ea3\n2. Thu th\u1eadp Douyin, Kuaishou, TikTok M\u1ef9, Instagram M\u1ef9; ch\u1ec9 t\u1ea3i video M\u1edaI, \u01b0u ti\u00ean theo \u0111i\u1ec3m th\u1ecbnh h\u00e0nh\n3. Nh\u1ea1c gi\u1eef nguy\u00ean; h\u1ed9i tho\u1ea1i th\u00eam Vietsub; thuy\u1ebft minh c\u00f3 th\u1ec3 l\u1ed3ng ti\u1ebfng Vi\u1ec7t\n4. L\u1ec7ch ch\u1ee7 \u0111\u1ec1 ho\u1eb7c nh\u1ea1y c\u1ea3m b\u1ecb gi\u1eef l\u1ea1i ch\u1edd b\u1ea1n duy\u1ec7t (c\u00f3 th\u00f4ng b\u00e1o)\nVi\u1ec7c \u0111\u0103ng n\u1eb1m \u1edf workflow 02 \u0111\u1ec3 canh \u0111\u00fang gi\u1edd v\u00e0ng.",
        "height": 300,
        "width": 760,
    },
    260,
    -360,
)
first = [session, verify, collect, house, process]
save(
    "trendvn01daily",
    "TrendVN | 01 · Thu th\u1eadp v\u00e0 x\u1eed l\u00fd (3 gi\u1edd/l\u1ea7n)",
    [schedule, manual] + first + [note],
    [(schedule["name"], session["name"]), (manual["name"], session["name"])] + chain(first),
)

# 02 · publish in golden hours (every 30 minutes; the worker enforces switch, window, daily limit, spacing)
sched = node(
    "M\u1ed7i 30 ph\u00fat", "scheduleTrigger", {"rule": {"interval": [{"field": "minutes", "minutesInterval": 30}]}}, 0, 200, version=1.2
)
manual = node("Ch\u1ea1y th\u1eed \u0111\u0103ng", "manualTrigger", {}, 0, 0)
publish = request(
    "\u0110\u0103ng video t\u1ed1t nh\u1ea5t n\u1ebfu \u0111\u1ee7 \u0111i\u1ec1u ki\u1ec7n",
    "/api/publish",
    300,
    base=AGENT,
    tolerant=True,
    timeout=1500000,
)
note = node(
    "\u0110\u0103ng theo gi\u1edd v\u00e0ng",
    "stickyNote",
    {
        "content": "## \u0110\u0103ng b\u00e0i\nM\u1ed7i 30 ph\u00fat h\u1ecfi worker c\u00f3 \u0111\u01b0\u1ee3c \u0111\u0103ng kh\u00f4ng. Worker ch\u1ec9 cho ph\u00e9p khi: c\u00f4ng t\u1eafc T\u1ef1 \u0111\u0103ng b\u1eadt, \u0111ang trong gi\u1edd v\u00e0ng, ch\u01b0a qu\u00e1 s\u1ed1 b\u00e0i m\u1ed7i ng\u00e0y, \u0111\u1ee7 gi\u00e3n c\u00e1ch, kh\u00f4ng c\u00f3 b\u00e0i ch\u01b0a x\u00e1c nh\u1eadn.\nKh\u00f4ng \u0111\u1ee7 \u0111i\u1ec1u ki\u1ec7n th\u00ec tr\u1ea3 l\u1eddi ngay, kh\u00f4ng m\u1edf tr\u00ecnh duy\u1ec7t.",
        "height": 240,
        "width": 560,
    },
    100,
    -300,
)
save(
    "trendvn02publish",
    "TrendVN | 02 · \u0110\u0103ng theo gi\u1edd v\u00e0ng (30 ph\u00fat/l\u1ea7n)",
    [sched, manual, publish, note],
    [(sched["name"], publish["name"]), (manual["name"], publish["name"])],
)

# 03 · end of day: performance feedback + summary notification
cron = node(
    "23:30 m\u1ed7i ng\u00e0y",
    "scheduleTrigger",
    {"rule": {"interval": [{"field": "cronExpression", "expression": "30 23 * * *"}]}},
    0,
    200,
    version=1.2,
)
manual = node("Ch\u1ea1y th\u1eed ch\u1ed1t ng\u00e0y", "manualTrigger", {}, 0, 0)
stats = request(
    "\u0110\u1ecdc l\u01b0\u1ee3t xem c\u00e1c b\u00e0i \u0111\u00e3 \u0111\u0103ng",
    "/api/stats",
    300,
    base=AGENT,
    tolerant=True,
    timeout=300000,
)
summary = request("G\u1eedi t\u00f3m t\u1eaft ng\u00e0y", "/api/notify", 560, body='{"kind":"summary"}', tolerant=True)
note = node(
    "Ch\u1ed1t ng\u00e0y",
    "stickyNote",
    {
        "content": "## Ch\u1ed1t ng\u00e0y\n\u0110\u1ecdc l\u01b0\u1ee3t xem, tim c\u1ee7a b\u00e0i \u0111\u00e3 \u0111\u0103ng \u0111\u1ec3 h\u1ec7 th\u1ed1ng t\u1ef1 \u0111i\u1ec1u ch\u1ec9nh \u0111\u1ed9 \u01b0u ti\u00ean t\u1eebng ngu\u1ed3n (c\u1ea7n t\u1ed1i thi\u1ec3u 8 b\u00e0i), r\u1ed3i g\u1eedi t\u00f3m t\u1eaft qua k\u00eanh th\u00f4ng b\u00e1o b\u1ea1n \u0111\u00e3 c\u1ea5u h\u00ecnh.",
        "height": 220,
        "width": 560,
    },
    100,
    -280,
)
save(
    "trendvn03daily",
    "TrendVN | 03 · Ch\u1ed1t ng\u00e0y: hi\u1ec7u qu\u1ea3 v\u00e0 t\u00f3m t\u1eaft",
    [cron, manual, stats, summary, note],
    [(cron["name"], stats["name"]), (manual["name"], stats["name"]), (stats["name"], summary["name"])],
)

# 10 · authenticated observation intake (unchanged contract)
webhook = node(
    "Nh\u1eadn quan s\u00e1t ngu\u1ed3n",
    "webhook",
    {"httpMethod": "POST", "path": "trendvn-observations", "authentication": "headerAuth", "responseMode": "lastNode", "options": {}},
    0,
    version=2,
    credentials=CRED,
    webhookId="trendvn-observations",
)
ingest = request("L\u01b0u m\u1ed1c v\u00e0 nh\u1eadn di\u1ec7n video m\u1edbi", "/api/ingest", 280)
ingest["parameters"]["jsonBody"] = "={{ JSON.stringify($json.body) }}"
note = node(
    "H\u1ee3p \u0111\u1ed3ng d\u1eef li\u1ec7u",
    "stickyNote",
    {
        "content": "## \u0110\u1ea7u v\u00e0o JSON c\u00f3 x\u00e1c th\u1ef1c (nh\u1eadp tay ho\u1eb7c c\u00f4ng c\u1ee5 kh\u00e1c)\nplatform, stream, observed_at (Unix seconds), items[]\nM\u1ed7i item: source_id, url HTTPS ch\u00ednh ch\u1ee7, country CN/US, title, rank ho\u1eb7c views, evidence_url.\nL\u1ea7n \u0111\u1ea7u ch\u1ec9 t\u1ea1o baseline. B\u1ed9 thu th\u1eadp t\u1ef1 \u0111\u1ed9ng d\u00f9ng workflow 01, kh\u00f4ng c\u1ea7n webhook n\u00e0y.",
        "height": 230,
        "width": 560,
    },
    0,
    -300,
)
save(
    "trendvn10inbox",
    "TrendVN | 10 · Nh\u1eadn quan s\u00e1t v\u00e0 ch\u1ed1ng tr\u00f9ng ID",
    [webhook, ingest, note],
    [(webhook["name"], ingest["name"])],
)

# 20 · manual processing run
manual = node("Ch\u1ea1y x\u1eed l\u00fd th\u1eed", "manualTrigger", {}, 0)
house = request("Ph\u00e1t hi\u1ec7n t\u00e1c v\u1ee5 gi\u00e1n \u0111o\u1ea1n", "/api/housekeeping", 260)
process = request("Ph\u00e2n lo\u1ea1i nh\u1ea1c v\u00e0 t\u1ea1o Vietsub", "/api/process", 520, body='{"max":4}')
note = node(
    "X\u1eed l\u00fd th\u1ee7 c\u00f4ng",
    "stickyNote",
    {
        "content": "## Ch\u1ea1y tay b\u01b0\u1edbc x\u1eed l\u00fd\nNh\u1ea1c: gi\u1eef nguy\u00ean \u00e2m thanh. H\u1ed9i tho\u1ea1i/thuy\u1ebft minh: Vietsub.\nKi\u1ec3m tra hash ngu\u1ed3n, d\u1ea5u v\u00e2n tay h\u00ecnh \u1ea3nh, th\u1eddi l\u01b0\u1ee3ng, ch\u1ee7 \u0111\u1ec1, nh\u1ea1y c\u1ea3m v\u00e0 gi\u1ea3i m\u00e3 \u0111\u1ea7u ra.\nL\u1ecbch t\u1ef1 \u0111\u1ed9ng n\u1eb1m \u1edf workflow 01 (thu th\u1eadp, x\u1eed l\u00fd) v\u00e0 02 (\u0111\u0103ng).",
        "height": 240,
        "width": 560,
    },
    150,
    -300,
)
save(
    "trendvn20process",
    "TrendVN | 20 · X\u1eed l\u00fd video v\u00e0 ph\u1ee5 \u0111\u1ec1 Vi\u1ec7t",
    [manual, house, process, note],
    chain([manual, house, process]),
)

if CHECK:
    stale = [n for n, text in WRITTEN.items() if not (OUT / n).exists() or (OUT / n).read_text() != text]
    extra = [f.name for f in OUT.glob("*.json") if f.name not in WRITTEN]
    if stale or extra:
        print("n8n/workflows kh\u00f4ng kh\u1edbp n8n/build.py: %s. Ch\u1ea1y ./trendvn n8n build." % ", ".join(stale + extra))
        sys.exit(1)
    print("OK: %d workflow kh\u1edbp m\u00e3 sinh." % len(WRITTEN))
else:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in WRITTEN.items():
        (OUT / name).write_text(text)
    print(
        "\u0110\u00e3 sinh %d workflow (ch\u01b0a b\u1eadt, kh\u00f4ng ch\u1ee9a b\u00ed m\u1eadt): %s"
        % (len(WRITTEN), OUT.relative_to(ROOT))
    )
