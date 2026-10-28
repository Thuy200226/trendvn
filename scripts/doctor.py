#!/usr/bin/env python3
"""Diagnose TrendVN in one command (./trendvn doctor). Just read, don't change anything. Exit code 1 if there is a required item in error."""

import getpass
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import parse  # noqa: E402

ENV = parse(ROOT / ".env")
TOKEN = ENV.get("TRENDVN_TOKEN", "")
GATEWAY = ENV.get("TRENDVN_AGENT_BIND") or ENV.get("TRENDVN_GATEWAY") or "172.20.0.1"
AGENT_PORT = ENV.get("TRENDVN_AGENT_PORT", "5682")
WORKER_PORT = ENV.get("TRENDVN_WORKER_PORT", "5681")
N8N_PORT = ENV.get("TRENDVN_N8N_PORT", "5680")
MAC = sys.platform == "darwin"
BIND = ENV.get("TRENDVN_BIND", "127.0.0.1")
rows = []


def check(name, ok, detail="", fix="", required=True):
    rows.append((name, ok, detail, fix, required))


def sh(*args, timeout=30, err=False):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=ROOT)
        return p.returncode, (p.stdout + (p.stderr if err else "")).strip()
    except Exception as e:
        return 1, str(e)


def get(url, auth=False, timeout=8):
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + TOKEN} if auth else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


check(
    "Docker ch\u1ea1y \u0111\u01b0\u1ee3c",
    sh("docker", "info")[0] == 0,
    fix="Kh\u1edfi \u0111\u1ed9ng Docker v\u00e0 c\u1ea5p quy\u1ec1n cho user hi\u1ec7n t\u1ea1i.",
)
check("C\u00f3 file .env", (ROOT / ".env").exists() and len(TOKEN) >= 32, fix="Ch\u1ea1y: ./trendvn install")
rc, out = sh("docker", "compose", "ps", "--format", "{{.Service}} {{.State}} {{.Health}}")
states = {l.split()[0]: l for l in out.splitlines() if l.strip()}
check("Container n8n", "n8n running" in states.get("n8n", ""), states.get("n8n", "kh\u00f4ng c\u00f3"), "./trendvn up")
check(
    "Container worker kh\u1ecfe",
    "worker running healthy" in states.get("worker", ""),
    states.get("worker", "kh\u00f4ng c\u00f3"),
    "./trendvn logs worker",
)

status = None
try:
    status = get("http://127.0.0.1:%s/api/status" % WORKER_PORT, auth=True)
    running = str(get("http://127.0.0.1:%s/health" % WORKER_PORT).get("version"))
    wanted = (ROOT / "VERSION").read_text().strip()
    check("Worker tr\u1ea3 l\u1eddi API", True, "phi\u00ean b\u1ea3n " + running)
    check(
        "Worker \u0111\u00fang phi\u00ean b\u1ea3n c\u1ee7a m\u00e3",
        running == wanted,
        "%s (m\u00e3: %s)" % (running, wanted),
        "./trendvn update  (d\u1ef1ng l\u1ea1i image v\u00e0 kh\u1edfi \u0111\u1ed9ng l\u1ea1i)",
    )
except Exception as e:
    check("Worker tr\u1ea3 l\u1eddi API", False, str(e)[:80], "Ki\u1ec3m tra TRENDVN_BIND v\u00e0 ./trendvn logs worker")

try:
    a = get("http://%s:%s/health" % (GATEWAY, AGENT_PORT))
    check("Agent tr\u00ecnh duy\u1ec7t ch\u1ea1y", a.get("ok", False), "b\u1eadn" if a.get("busy") else "r\u1ea3nh")
except Exception as e:
    check(
        "Agent tr\u00ecnh duy\u1ec7t ch\u1ea1y",
        False,
        str(e)[:80],
        "./trendvn agent restart, r\u1ed3i ./trendvn agent logs  (ch\u01b0a c\u00e0i d\u1ecbch v\u1ee5: ./trendvn agent install)",
    )

# The path n8n and the worker really use: from INSIDE the container to the agent on the host. A host firewall (ufw INPUT rules on the
# bridge interface) can block it while the host-side check above stays green.
if "worker running" in states.get("worker", ""):
    rc, out = sh(
        "docker",
        "compose",
        "exec",
        "-T",
        "worker",
        "python",
        "-c",
        "import urllib.request; urllib.request.urlopen('http://trendvn-agent:%s/health', timeout=6)" % AGENT_PORT,
        timeout=40,
        err=True,
    )
    check(
        "Container g\u1ecdi \u0111\u01b0\u1ee3c agent",
        rc == 0,
        "\u1ed5n" if rc == 0 else (out.splitlines() or ["l\u1ed7i"])[-1][:90],
        "Agent ch\u01b0a ch\u1ea1y (./trendvn agent restart) ho\u1eb7c t\u01b0\u1eddng l\u1eeda c\u1ee7a m\u00e1y ch\u1eb7n c\u1ea7u n\u1ed1i Docker. Linux/ufw: sudo ufw allow from <d\u1ea3i TRENDVN_SUBNET> to any port %s"
        % AGENT_PORT,
    )

try:
    urllib.request.urlopen("http://127.0.0.1:%s/healthz" % N8N_PORT, timeout=8)
    check("n8n ph\u1ea3n h\u1ed3i", True, "http://localhost:" + N8N_PORT)
except Exception as e:
    check("n8n ph\u1ea3n h\u1ed3i", False, str(e)[:80], "./trendvn logs n8n")

rc, out = sh(
    "docker", "compose", "exec", "-T", "-e", "N8N_RUNNERS_BROKER_PORT=5690", "n8n", "n8n", "list:workflow", "--active=true", timeout=90
)
active = [l.split("|")[0] for l in out.splitlines() if l.startswith("trendvn")]
check(
    "L\u1ecbch n8n \u0111\u00e3 b\u1eadt (01, 02, 03)",
    {"trendvn01daily", "trendvn02publish", "trendvn03daily"} <= set(active),
    ", ".join(active) or "ch\u01b0a workflow n\u00e0o b\u1eadt",
    "./trendvn n8n activate  (ho\u1eb7c m\u1edf n8n, b\u1eadt Publish cho workflow 01, 02, 03)",
)

# Playwright drives Google Chrome by channel name ("chrome"), which it finds only in Chrome's standard location: Chromium or snap builds do not count.
chrome = (
    shutil.which("google-chrome")
    or shutil.which("google-chrome-stable")
    or next((p for p in ("/opt/google/chrome/chrome", "/Applications/Google Chrome.app") if Path(p).exists()), None)
)
check(
    "C\u00f3 Google Chrome",
    bool(chrome),
    chrome or "",
    "C\u00e0i Google Chrome b\u1ea3n c\u1ee7a Google (Mac: v\u00e0o th\u01b0 m\u1ee5c /Applications): https://www.google.com/chrome/",
)
venv_py = ROOT / ".venv/bin/python"
py_ok = venv_py.exists() and sh(str(venv_py), "-c", "import sys; sys.exit(sys.version_info < (3, 10))")[0] == 0
check("Python c\u1ee7a agent t\u1eeb 3.10", py_ok, fix="./trendvn agent venv  (c\u1ea7n Python 3.10+; macOS: brew install python@3.12)")
check(
    "Playwright \u0111\u00e3 c\u00e0i",
    venv_py.exists() and sh(str(venv_py), "-c", "import playwright")[0] == 0,
    fix="./trendvn agent venv  (t\u1ea1o l\u1ea1i .venv)",
)
if chrome and venv_py.exists():
    rc, out = sh(
        str(venv_py),
        "-c",
        "from playwright.sync_api import sync_playwright\nwith sync_playwright() as p:\n    p.chromium.launch(channel='chrome', headless=True).close()",
        timeout=90,
        err=True,
    )
    check(
        "Chrome m\u1edf \u0111\u01b0\u1ee3c qua Playwright",
        rc == 0,
        "\u1ed5n" if rc == 0 else out.strip().splitlines()[-1][:90] if out.strip() else "l\u1ed7i kh\u00f4ng r\u00f5",
        "C\u00e0i l\u1ea1i Google Chrome; r\u1ed3i ./trendvn agent update",
    )
free_gb = shutil.disk_usage(ROOT).free / 2**30  # GiB, like the dashboard chip and the worker
# the same lines as the dashboard chip and the worker: amber below 2 GiB; below 1 GiB the worker stops downloading and below 512 MiB rendering
check(
    "\u1ed4 \u0111\u0129a c\u00f2n tr\u1ed1ng",
    free_gb >= 2,
    "%.1f GiB" % free_gb,
    "D\u1ecdn \u1ed5 \u0111\u0129a: video v\u00e0 image Docker c\u1ea7n ch\u1ed7 (d\u01b0\u1edbi 1 GiB h\u1ec7 th\u1ed1ng ng\u1eebng t\u1ea3i video, d\u01b0\u1edbi 512 MiB ng\u1eebng d\u1ef1ng)",
    required=free_gb < 1,
)
if not MAC and shutil.which("loginctl"):
    rc, out = sh("loginctl", "show-user", getpass.getuser(), "-p", "Linger", "--value")
    if rc == 0:
        check(
            "Agent t\u1ef1 ch\u1ea1y sau khi kh\u1edfi \u0111\u1ed9ng m\u00e1y",
            out.strip() == "yes",
            "c\u00f3" if out.strip() == "yes" else "ch\u1ec9 ch\u1ea1y sau khi b\u1ea1n \u0111\u0103ng nh\u1eadp m\u00e0n h\u00ecnh",
            "sudo loginctl enable-linger %s  (m\u1ed9t l\u1ea7n; kh\u00f4ng c\u00f3 th\u00ec l\u1ecbch \u0111\u0103ng d\u1eebng sau m\u1ed7i l\u1ea7n kh\u1edfi \u0111\u1ed9ng l\u1ea1i cho t\u1edbi khi b\u1ea1n \u0111\u0103ng nh\u1eadp)"
            % getpass.getuser(),
            required=False,
        )
if MAC:
    rc, out = sh("pmset", "-g")
    sleeping = [l for l in out.splitlines() if l.strip().startswith("sleep ") and l.split()[1] not in ("0",)]
    check(
        "Mac kh\u00f4ng t\u1ef1 ng\u1ee7 khi c\u1eafm \u0111i\u1ec7n",
        not sleeping,
        (sleeping[0].strip() if sleeping else "\u1ed5n"),
        "C\u00e0i \u0111\u1eb7t h\u1ec7 th\u1ed1ng → M\u00e0n h\u00ecnh kh\u00f3a/Pin: kh\u00f4ng cho Mac t\u1ef1 ng\u1ee7 khi c\u1eafm s\u1ea1c (l\u1ecbch ch\u1ec9 ch\u1ea1y khi Mac th\u1ee9c)",
        required=False,
    )

if status:
    check(
        "Kh\u00f3a Gemini",
        status["gemini_configured"],
        fix="Nh\u1eadp trong b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n → C\u00e0i \u0111\u1eb7t",
        required=False,
    )
    check(
        "X\u1eed l\u00fd video b\u1eadt",
        status["processing_enabled"],
        fix="B\u1ea3ng \u0111i\u1ec1u khi\u1ec3n → C\u00e0i \u0111\u1eb7t → X\u1eed l\u00fd video: B\u1eadt",
        required=False,
    )
    check(
        "B\u1ed9 thu th\u1eadp t\u1eebng ch\u1ea1y th\u00e0nh c\u00f4ng",
        status["discovery"] == "connected",
        status["discovery"],
        "Ch\u1edd workflow 01 ch\u1ea1y ho\u1eb7c ch\u1ea1y tay trong n8n",
        required=False,
    )
    check(
        "\u0110\u00e3 \u0111\u0103ng nh\u1eadp TikTok",
        status["publisher"] == "connected",
        status["publisher"],
        "./trendvn tiktok login",
        required=False,
    )
    for account in status.get("accounts", []):
        if account["enabled"] and len(status["accounts"]) > 1:
            flag = "" if account["id"] == "main" else " --account " + account["id"]
            known = account["logged_in"]
            check(
                "  @%s \u0111\u00e3 \u0111\u0103ng nh\u1eadp" % account["username"],
                known is True,
                "ch\u01b0a ki\u1ec3m tra" if known is None else ("r\u1ed3i" if known else "ch\u01b0a"),
                "./trendvn tiktok login" + flag,
                required=False,
            )
    check(
        "T\u1ef1 \u0111\u0103ng",
        status["publisher_enabled"],
        "B\u1eacT" if status["publisher_enabled"] else "T\u1eaeT (b\u1ea1n t\u1ef1 b\u1eadt khi \u0111\u00e3 ch\u1ea1y th\u1eed dry-run)",
        required=False,
    )
    if status["unresolved_publishes"]:
        check(
            "Kh\u00f4ng c\u00f3 b\u00e0i ch\u01b0a x\u00e1c nh\u1eadn",
            False,
            "%d b\u00e0i" % status["unresolved_publishes"],
            "M\u1edf b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n → C\u1ea7n xem",
        )
    d = status.get("discovery_detail")
    if isinstance(d, dict):
        us = {p: d.get(p) for p in ("tiktok", "instagram")}
        skipped = [p for p, v in us.items() if isinstance(v, str) and "IP" in v]
        unknown = [p for p, v in us.items() if v is None]
        check(
            "Ngu\u1ed3n M\u1ef9 (TikTok, Instagram)",
            not skipped and not unknown,
            (
                "\u0111ang b\u1ecb b\u1ecf qua v\u00ec IP kh\u00f4ng ph\u1ea3i M\u1ef9"
                if skipped
                else ("ch\u01b0a c\u00f3 l\u1ea7n qu\u00e9t n\u00e0o" if unknown else "\u0111ang thu th\u1eadp")
            ),
            "\u0110\u1eb7t TRENDVN_US_PROXY trong .env r\u1ed3i ./trendvn agent restart" if skipped else "Ch\u1edd workflow 01 ch\u1ea1y",
            required=False,
        )

exposed = BIND not in ("127.0.0.1", "localhost")
if ENV.get("TRENDVN_UI_HOSTS") or exposed:
    check(
        "B\u1ea3ng \u0111i\u1ec1u khi\u1ec3n m\u1edf ra ngo\u00e0i \u0111\u00e3 c\u00f3 m\u1eadt kh\u1ea9u",
        bool(ENV.get("TRENDVN_UI_PASSWORD")) and len(ENV.get("TRENDVN_UI_PASSWORD", "")) >= 12,
        (
            "ch\u01b0a \u0111\u1eb7t"
            if not ENV.get("TRENDVN_UI_PASSWORD")
            else "m\u1eadt kh\u1ea9u qu\u00e1 ng\u1eafn (c\u1ea7n ≥ 12 k\u00fd t\u1ef1)"
        ),
        "\u0110\u1eb7t TRENDVN_UI_PASSWORD (≥ 12 k\u00fd t\u1ef1) trong .env r\u1ed3i ./trendvn up; ho\u1eb7c d\u00f9ng \u0111\u01b0\u1eddng h\u1ea7m SSH thay v\u00ec m\u1edf c\u1ed5ng",
    )
check(
    "Truy c\u1eadp ch\u1ec9 t\u1eeb m\u00e1y n\u00e0y",
    not exposed,
    "TRENDVN_BIND=" + BIND,
    "\u01afu ti\u00ean \u0111\u01b0\u1eddng h\u1ea7m SSH thay v\u00ec m\u1edf ra m\u1ea1ng (docs/TECH.md)",
    required=False,
)

width = max(len(r[0]) for r in rows)
bad = 0
for name, ok, detail, fix, required in rows:
    mark = "\033[32m✓\033[0m" if ok else ("\033[31m✗\033[0m" if required else "\033[33m!\033[0m")
    print("%s %-*s  %s" % (mark, width, name, detail))
    if not ok:
        print("    → " + fix)
        bad += required
print(
    "\n%s"
    % (
        "M\u1ecdi m\u1ee5c b\u1eaft bu\u1ed9c \u0111\u1ec1u \u1ed5n."
        if not bad
        else "%d m\u1ee5c b\u1eaft bu\u1ed9c \u0111ang l\u1ed7i." % bad
    )
)
sys.exit(1 if bad else 0)
