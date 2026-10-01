#!/usr/bin/env python3
"""Small helpers for scripts/migrate.sh (kept out of the shell script so nothing needs heredocs inside $(...), which bash 3.2 mishandles).

migrate_tools.py info <old .env>            prints "<token> <worker port>" of the old deployment
migrate_tools.py tasks <port> <token>       prints how many tasks the old worker is running now, or "unreachable"
migrate_tools.py compare <root> <port> <token>   prints job counts per state: copied database vs the new running worker
"""

import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import parse  # noqa: E402


def get(port, token, path):
    req = urllib.request.Request("http://127.0.0.1:%s%s" % (port, path), headers={"Authorization": "Bearer " + token})
    return json.load(urllib.request.urlopen(req, timeout=8))


def main():
    cmd, args = sys.argv[1], sys.argv[2:]
    if cmd == "info":
        env = parse(args[0])
        print(env.get("TRENDVN_TOKEN", "none"), env.get("TRENDVN_WORKER_PORT") or "5681")
    elif cmd == "tasks":
        try:
            print(len(get(args[0], args[1], "/api/tasks")["running"]))
        except Exception:
            print("unreachable")
    elif cmd == "compare":
        root, port, token = args
        db = sqlite3.connect("file:%s/data/worker/trendvn.sqlite3?mode=ro" % root, uri=True)
        copied = dict(db.execute("SELECT state, COUNT(*) FROM jobs GROUP BY state").fetchall())
        live = get(port, token, "/api/status")["counts"]
        print("Dữ liệu đã chép:", copied)
        print("Hệ thống mới   :", live)
        print("KHỚP" if copied == live else "KHÁC (nhẹ là bình thường nếu một lịch vừa chạy giữa hai lần đọc)")
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
