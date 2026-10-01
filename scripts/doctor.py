#!/usr/bin/env python3
"""Chẩn đoán TrendVN trong một lệnh (./trendvn doctor). Chỉ đọc, không đổi gì. Thoát mã 1 nếu có mục bắt buộc bị lỗi."""

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


check("Docker chạy được", sh("docker", "info")[0] == 0, fix="Khởi động Docker và cấp quyền cho user hiện tại.")
check("Có file .env", (ROOT / ".env").exists() and len(TOKEN) >= 32, fix="Chạy: ./trendvn install")
rc, out = sh("docker", "compose", "ps", "--format", "{{.Service}} {{.State}} {{.Health}}")
states = {l.split()[0]: l for l in out.splitlines() if l.strip()}
check("Container n8n", "n8n running" in states.get("n8n", ""), states.get("n8n", "không có"), "./trendvn up")
check(
    "Container worker khỏe", "worker running healthy" in states.get("worker", ""), states.get("worker", "không có"), "./trendvn logs worker"
)

status = None
try:
    status = get("http://127.0.0.1:%s/api/status" % WORKER_PORT, auth=True)
    running = str(get("http://127.0.0.1:%s/health" % WORKER_PORT).get("version"))
    wanted = (ROOT / "VERSION").read_text().strip()
    check("Worker trả lời API", True, "phiên bản " + running)
    check(
        "Worker đúng phiên bản của mã",
        running == wanted,
        "%s (mã: %s)" % (running, wanted),
        "./trendvn update  (dựng lại image và khởi động lại)",
    )
except Exception as e:
    check("Worker trả lời API", False, str(e)[:80], "Kiểm tra TRENDVN_BIND và ./trendvn logs worker")

try:
    a = get("http://%s:%s/health" % (GATEWAY, AGENT_PORT))
    check("Agent trình duyệt chạy", a.get("ok", False), "bận" if a.get("busy") else "rảnh")
except Exception as e:
    check(
        "Agent trình duyệt chạy",
        False,
        str(e)[:80],
        "./trendvn agent restart, rồi ./trendvn agent logs  (chưa cài dịch vụ: ./trendvn agent install)",
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
        "Container gọi được agent",
        rc == 0,
        "ổn" if rc == 0 else (out.splitlines() or ["lỗi"])[-1][:90],
        "Agent chưa chạy (./trendvn agent restart) hoặc tường lửa của máy chặn cầu nối Docker. Linux/ufw: sudo ufw allow from <dải TRENDVN_SUBNET> to any port %s"
        % AGENT_PORT,
    )

try:
    urllib.request.urlopen("http://127.0.0.1:%s/healthz" % N8N_PORT, timeout=8)
    check("n8n phản hồi", True, "http://localhost:" + N8N_PORT)
except Exception as e:
    check("n8n phản hồi", False, str(e)[:80], "./trendvn logs n8n")

rc, out = sh(
    "docker", "compose", "exec", "-T", "-e", "N8N_RUNNERS_BROKER_PORT=5690", "n8n", "n8n", "list:workflow", "--active=true", timeout=90
)
active = [l.split("|")[0] for l in out.splitlines() if l.startswith("trendvn")]
check(
    "Lịch n8n đã bật (01, 02, 03)",
    {"trendvn01daily", "trendvn02publish", "trendvn03daily"} <= set(active),
    ", ".join(active) or "chưa workflow nào bật",
    "./trendvn n8n activate  (hoặc mở n8n, bật Publish cho workflow 01, 02, 03)",
)

# Playwright drives Google Chrome by channel name ("chrome"), which it finds only in Chrome's standard location: Chromium or snap builds do not count.
chrome = (
    shutil.which("google-chrome")
    or shutil.which("google-chrome-stable")
    or next((p for p in ("/opt/google/chrome/chrome", "/Applications/Google Chrome.app") if Path(p).exists()), None)
)
check(
    "Có Google Chrome",
    bool(chrome),
    chrome or "",
    "Cài Google Chrome bản của Google (Mac: vào thư mục /Applications): https://www.google.com/chrome/",
)
venv_py = ROOT / ".venv/bin/python"
py_ok = venv_py.exists() and sh(str(venv_py), "-c", "import sys; sys.exit(sys.version_info < (3, 10))")[0] == 0
check("Python của agent từ 3.10", py_ok, fix="./trendvn agent venv  (cần Python 3.10+; macOS: brew install python@3.12)")
check(
    "Playwright đã cài",
    venv_py.exists() and sh(str(venv_py), "-c", "import playwright")[0] == 0,
    fix="./trendvn agent venv  (tạo lại .venv)",
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
        "Chrome mở được qua Playwright",
        rc == 0,
        "ổn" if rc == 0 else out.strip().splitlines()[-1][:90] if out.strip() else "lỗi không rõ",
        "Cài lại Google Chrome; rồi ./trendvn agent update",
    )
free_gb = shutil.disk_usage(ROOT).free / 1e9
check("Ổ đĩa còn trống", free_gb > 3, "%.1f GB" % free_gb, "Dọn ổ đĩa: video và image Docker cần chỗ")
if MAC:
    rc, out = sh("pmset", "-g")
    sleeping = [l for l in out.splitlines() if l.strip().startswith("sleep ") and l.split()[1] not in ("0",)]
    check(
        "Mac không tự ngủ khi cắm điện",
        not sleeping,
        (sleeping[0].strip() if sleeping else "ổn"),
        "Cài đặt hệ thống → Màn hình khóa/Pin: không cho Mac tự ngủ khi cắm sạc (lịch chỉ chạy khi Mac thức)",
        required=False,
    )

if status:
    check("Khóa Gemini", status["gemini_configured"], fix="Nhập trong bảng điều khiển → Cài đặt", required=False)
    check("Xử lý video bật", status["processing_enabled"], fix="Bảng điều khiển → Cài đặt → Xử lý video: Bật", required=False)
    check(
        "Bộ thu thập từng chạy thành công",
        status["discovery"] == "connected",
        status["discovery"],
        "Chờ workflow 01 chạy hoặc chạy tay trong n8n",
        required=False,
    )
    check("Đã đăng nhập TikTok", status["publisher"] == "connected", status["publisher"], "./trendvn tiktok login", required=False)
    check(
        "Tự đăng",
        status["publisher_enabled"],
        "BẬT" if status["publisher_enabled"] else "TẮT (bạn tự bật khi đã chạy thử dry-run)",
        required=False,
    )
    if status["unresolved_publishes"]:
        check("Không có bài chưa xác nhận", False, "%d bài" % status["unresolved_publishes"], "Mở bảng điều khiển → Cần xem")
    d = status.get("discovery_detail")
    if isinstance(d, dict):
        us = {p: d.get(p) for p in ("tiktok", "instagram")}
        skipped = [p for p, v in us.items() if isinstance(v, str) and "IP" in v]
        unknown = [p for p, v in us.items() if v is None]
        check(
            "Nguồn Mỹ (TikTok, Instagram)",
            not skipped and not unknown,
            "đang bị bỏ qua vì IP không phải Mỹ" if skipped else ("chưa có lần quét nào" if unknown else "đang thu thập"),
            "Đặt TRENDVN_US_PROXY trong .env rồi ./trendvn agent restart" if skipped else "Chờ workflow 01 chạy",
            required=False,
        )

exposed = BIND not in ("127.0.0.1", "localhost")
if ENV.get("TRENDVN_UI_HOSTS") or exposed:
    check(
        "Bảng điều khiển mở ra ngoài đã có mật khẩu",
        bool(ENV.get("TRENDVN_UI_PASSWORD")) and len(ENV.get("TRENDVN_UI_PASSWORD", "")) >= 12,
        "chưa đặt" if not ENV.get("TRENDVN_UI_PASSWORD") else "mật khẩu quá ngắn (cần ≥ 12 ký tự)",
        "Đặt TRENDVN_UI_PASSWORD (≥ 12 ký tự) trong .env rồi ./trendvn up; hoặc dùng đường hầm SSH thay vì mở cổng",
    )
check(
    "Truy cập chỉ từ máy này",
    not exposed,
    "TRENDVN_BIND=" + BIND,
    "Ưu tiên đường hầm SSH thay vì mở ra mạng (docs/DEPLOY.md)",
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
print("\n%s" % ("Mọi mục bắt buộc đều ổn." if not bad else "%d mục bắt buộc đang lỗi." % bad))
sys.exit(1 if bad else 0)
