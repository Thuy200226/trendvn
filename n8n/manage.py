#!/usr/bin/env python3
"""Manage TrendVN's workflows inside the running n8n container, through the official n8n CLI (docker compose exec).

    manage.py status               list the workflows and which schedules are on
    manage.py import               load the worker credential + n8n/workflows/*.json (workflows that were on stay on)
    manage.py activate [id ...]    turn schedules on (default: 01, 02, 03); n8n restarts once so it takes effect
    manage.py deactivate [id ...]  turn schedules off (default: every TrendVN workflow)
    manage.py export [dir]         save what is in n8n now (for example after editing in its UI) as one JSON file per workflow
                                   (default dir: n8n/exported/)

Only TrendVN's own objects are touched; other credentials in n8n are never read. The token is written to a 0600 temp file,
copied into the container, imported and deleted; it is never printed. Works with any compose project name and on macOS/Linux.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEDULES = ["trendvn01daily", "trendvn02publish", "trendvn03daily"]  # 01 collect+process, 02 publish, 03 day close
N8N_CLI = [
    "exec",
    "-T",
    "-e",
    "N8N_RUNNERS_BROKER_PORT=5690",
    "n8n",
    "n8n",
]  # the CLI must not fight the running server for the broker port


def die(msg, code=1):
    print("Lỗi: " + msg, file=sys.stderr)
    sys.exit(code)


def read_env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from envfile import parse

    return parse(ROOT / ".env")


def compose(*args, check=True, capture=False, timeout=180, stdin=None):
    envv = dict(os.environ, TRENDVN_VERSION=(ROOT / "VERSION").read_text().strip())
    p = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        env=envv,
        text=True,
        timeout=timeout,
        input=stdin,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if check and p.returncode != 0:
        detail = ((p.stderr or "") + (p.stdout or "")).strip()[-400:] if capture else ""
        die("lệnh docker compose %s thất bại.%s" % (" ".join(args[:3]), ("\n" + detail) if detail else ""))
    return p


def n8n_cli(*args, check=True):
    return compose(*N8N_CLI, *args, check=check, capture=True, timeout=240)


def require_n8n():
    p = compose("ps", "--status", "running", "--services", check=False, capture=True, timeout=60)
    if "n8n" not in (p.stdout or "").split():
        die("n8n chưa chạy. Chạy ./trendvn up trước.")


def guard():
    """Refuse to change an n8n that belongs to another folder's copy of the project (same compose project name)."""
    if os.environ.get("TRENDVN_ALLOW_TAKEOVER") == "1":
        return
    cid = (compose("ps", "-q", "n8n", check=False, capture=True, timeout=60).stdout or "").strip()
    if not cid:
        return
    label = subprocess.run(
        ["docker", "inspect", "-f", '{{index .Config.Labels "com.docker.compose.project.working_dir"}}', cid],
        capture_output=True,
        text=True,
    ).stdout.strip()
    here = {str(ROOT), str(ROOT.resolve())}
    if label and label not in here:
        die(
            "n8n đang chạy từ thư mục khác (%s). Không thay đổi nó từ đây. Xem docs/DEPLOY.md mục 11, "
            "hoặc đặt COMPOSE_PROJECT_NAME và cổng riêng trong .env của thư mục này." % label
        )


def workflows():
    """[(id, name)] of every workflow in n8n, and the set of ids that are on."""
    everything = [tuple(l.split("|", 1)) for l in n8n_cli("list:workflow").stdout.splitlines() if "|" in l]
    active = {l.split("|", 1)[0] for l in n8n_cli("list:workflow", "--active=true").stdout.splitlines() if "|" in l}
    return everything, active


def restart_n8n():
    compose("restart", "n8n", timeout=120)
    for _ in range(40):  # wait until the server answers again (it takes 10-30 s)
        if (
            compose(
                *["exec", "-T", "n8n", "wget", "-qO-", "http://localhost:5678/healthz"], check=False, capture=True, timeout=20
            ).returncode
            == 0
        ):
            return
        time.sleep(3)
    die("n8n không khởi động lại kịp. Xem: ./trendvn logs n8n")


def cmd_status(_args):
    require_n8n()
    everything, active = workflows()
    if not everything:
        print("Chưa có workflow nào. Chạy: ./trendvn n8n import")
    for wid, name in sorted(everything):
        print("%s  %-18s %s" % ("BẬT " if wid in active else "tắt ", wid, name))
    missing = [w for w in SCHEDULES if w not in active]
    if everything and missing:
        print("\nLịch tự động chưa bật đủ (thiếu: %s). Chạy: ./trendvn n8n activate" % ", ".join(missing))
    return 0


def cmd_import(_args):
    require_n8n()
    guard()
    env = read_env()
    token = env.get("TRENDVN_TOKEN", "")
    if len(token) < 32:
        die("Thiếu TRENDVN_TOKEN trong .env. Chạy ./trendvn install.")
    if not list((ROOT / "n8n" / "workflows").glob("*.json")):
        die("Chưa có workflow. Chạy: ./trendvn n8n build")
    _, was_active = workflows()
    credential = [
        {
            "id": "trendvnWorkerAuth",
            "name": "TrendVN · Worker riêng",
            "type": "httpHeaderAuth",
            "data": {"name": "Authorization", "value": "Bearer " + token},
        }
    ]
    # The token travels through stdin into a file that only the n8n user can read (umask 077) and is removed afterwards. No temp file on the
    # host, and no `docker compose cp` (it would create a root-owned 0600 file that the n8n user, who runs the CLI, could not read).
    remote = "/tmp/trendvn-credentials.json"
    compose("exec", "-T", "n8n", "sh", "-c", "umask 077; cat > " + remote, capture=True, stdin=json.dumps(credential))
    try:
        n8n_cli("import:credentials", "--input=" + remote)
        n8n_cli("import:workflow", "--separate", "--input=/import")
    finally:
        compose("exec", "-T", "n8n", "rm", "-f", remote, check=False, capture=True)
    print("Đã nạp workflow TrendVN vào n8n (không in bí mật).")
    ours = [w for w in was_active if w.startswith("trendvn")]
    if ours:  # importing replaces a workflow and switches it off; put back exactly what was on before
        return activate(sorted(ours), quiet=True)
    print("Các lịch tự động đang TẮT. Bật bằng: ./trendvn n8n activate")
    return 0


def activate(ids, quiet=False):
    failed = []
    for wid in ids:
        r = n8n_cli("publish:workflow", "--id=" + wid, check=False)
        if r.returncode != 0:
            failed.append(wid)
    restart_n8n()  # n8n only registers new schedules at start-up
    _, active = workflows()
    ok = [w for w in ids if w in active]
    print("Đã bật: %s" % (", ".join(ok) or "không có"))
    if failed or len(ok) != len(ids):
        print("Không bật được: %s. Bật tay trong n8n (mở workflow → Publish)." % ", ".join(sorted(set(ids) - set(ok))), file=sys.stderr)
        return 1
    return 0


def cmd_activate(args):
    require_n8n()
    guard()
    everything, _ = workflows()
    known = {w for w, _ in everything}
    ids = args or SCHEDULES
    unknown = [w for w in ids if w not in known]
    if unknown:
        die("Không có workflow: %s. Chạy ./trendvn n8n import trước, hoặc xem ./trendvn n8n status." % ", ".join(unknown))
    return activate(ids)


def cmd_deactivate(args):
    require_n8n()
    guard()
    everything, active = workflows()
    ids = args or sorted(w for w, _ in everything if w.startswith("trendvn") and w in active)
    for wid in ids:
        n8n_cli("unpublish:workflow", "--id=" + wid)
    if ids:
        restart_n8n()
    print("Đã tắt: %s" % (", ".join(ids) or "không có workflow nào đang bật"))
    return 0


def cmd_export(args):
    require_n8n()
    dest = Path(args[0]) if args else ROOT / "n8n" / "exported"
    dest.mkdir(parents=True, exist_ok=True)
    tmp = "/tmp/trendvn-export"
    compose("exec", "-T", "n8n", "rm", "-rf", tmp, check=False, capture=True)
    n8n_cli("export:workflow", "--all", "--separate", "--pretty", "--output=" + tmp)
    with tempfile.TemporaryDirectory(prefix="trendvn-export-") as td:
        compose("cp", "n8n:" + tmp + "/.", td, capture=True)
        compose("exec", "-T", "n8n", "rm", "-rf", tmp, check=False, capture=True)
        mine = sorted(Path(td).glob("trendvn*.json"))  # never copy workflows that are not TrendVN's own
        for f in mine:
            shutil.copyfile(f, dest / f.name)
    print("Đã xuất %d workflow TrendVN vào %s" % (len(mine), dest))
    print("Đây là bản đang chạy trong n8n. Nguồn chuẩn vẫn là n8n/build.py: chuyển thay đổi cần giữ vào đó.")
    return 0


COMMANDS = {"status": cmd_status, "import": cmd_import, "activate": cmd_activate, "deactivate": cmd_deactivate, "export": cmd_export}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(COMMANDS[sys.argv[1]](sys.argv[2:]))
    except subprocess.TimeoutExpired:
        die("lệnh chạy quá lâu. Kiểm tra ./trendvn logs n8n")
