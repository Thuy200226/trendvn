"""First-run setup, safe to run again: creates the data folders, generates secrets once, picks a free private Docker subnet.

Never prints secrets and never overwrites values you already set in .env (it only appends what is missing).
Run by ./trendvn install; you rarely need to call it yourself.
"""

import ipaddress
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

os.umask(0o077)  # .env and the data folders are private from the first byte, not only after a later chmod
root = Path(os.environ.get("TRENDVN_SETUP_ROOT") or Path(__file__).resolve().parents[1])  # the override is for tests
for sub in ("worker", "agent", "backups"):  # data/worker = mounted into the worker container, data/agent = browser profiles + logs
    (root / "data" / sub).mkdir(parents=True, exist_ok=True, mode=0o700)


def used_subnets():
    """Subnets Docker already uses on this machine, so the project bridge never collides with another project."""
    try:
        names = subprocess.run(["docker", "network", "ls", "-q"], capture_output=True, text=True, timeout=30).stdout.split()
        if not names:
            return []
        out = subprocess.run(["docker", "network", "inspect", *names], capture_output=True, text=True, timeout=30).stdout
        return [
            ipaddress.ip_network(c["Subnet"])
            for n in json.loads(out)
            for c in (n.get("IPAM") or {}).get("Config") or []
            if c.get("Subnet") and ":" not in c["Subnet"]
        ]
    except Exception:
        return []


def pick_subnet():
    taken = used_subnets()
    for second in range(20, 32):
        net = ipaddress.ip_network("172.%d.0.0/16" % second)
        if not any(net.overlaps(t) for t in taken):
            return str(net), str(net[1])
    raise SystemExit("Không tìm được dải mạng Docker trống trong 172.20-172.31; đặt TRENDVN_SUBNET và TRENDVN_GATEWAY thủ công trong .env")


env = root / ".env"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import format_line, parse  # noqa: E402

existing = {k: v for k, v in parse(env).items() if v}  # an empty value (e.g. copied from .env.example) counts as not set

new = {}
for key in ("N8N_ENCRYPTION_KEY", "TRENDVN_TOKEN"):
    if key not in existing:
        new[key] = secrets.token_hex(32)
if "TRENDVN_GATEWAY" not in existing:
    if "N8N_ENCRYPTION_KEY" in existing:
        # A deployment created before these keys existed already runs on the compose defaults; keep it exactly as is.
        new.update(TRENDVN_SUBNET="172.20.0.0/16", TRENDVN_GATEWAY="172.20.0.1")
    else:
        subnet, gateway = pick_subnet()
        new.update(TRENDVN_SUBNET=subnet, TRENDVN_GATEWAY=gateway)
gateway = new.get("TRENDVN_GATEWAY") or existing.get("TRENDVN_GATEWAY")
# How containers reach the browser agent that runs on the host:
#  Linux           the agent listens on the project's bridge gateway (not visible to the LAN) and n8n resolves it by IP.
#  macOS/Windows   Docker Desktop runs containers in a VM without a host bridge; "host-gateway" is Docker's name for the host.
desktop = sys.platform in ("darwin", "win32")
if "TRENDVN_AGENT_BIND" not in existing:
    new["TRENDVN_AGENT_BIND"] = "127.0.0.1" if desktop else gateway
if "TRENDVN_AGENT_HOSTREF" not in existing:
    new["TRENDVN_AGENT_HOSTREF"] = "host-gateway" if desktop else gateway
if hasattr(os, "getuid"):
    # The worker container writes data/worker as you, so files stay yours and nothing needs chmod 777.
    for k, v in (("TRENDVN_UID", os.getuid()), ("TRENDVN_GID", os.getgid())):
        if k not in existing:
            new[k] = str(v)
if new:
    fresh = not env.exists() or env.stat().st_size == 0
    with open(env, "a") as f:
        if fresh:
            f.write(
                "# Cấu hình của máy này, do ./trendvn install tạo. KHÔNG chia sẻ, KHÔNG đưa vào git.\n"
                "# Các tùy chọn khác (proxy Mỹ, mật khẩu truy cập từ xa, thông báo...) xem .env.example.\n"
            )
        else:
            f.write("\n")
        f.write("\n".join(format_line(k, v) for k, v in new.items()) + "\n")
    env.chmod(0o600)
print("TrendVN: cấu hình sẵn sàng (%s). Bí mật không được hiển thị." % ("đã thêm %d mục" % len(new) if new else "không đổi"))
