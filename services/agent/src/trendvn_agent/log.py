"""The agent's log: stdout (systemd/launchd keep it) and data/agent/agent.log."""

import time

from .config import DATA, ensure_dirs


def log(msg):
    """Print and append to data/agent/agent.log. Logging must never break the job it describes (disk full, wrong owner, read-only mount)."""
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        ensure_dirs()
        with open(DATA / "agent.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
