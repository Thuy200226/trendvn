"""The agent's log: stdout (systemd/launchd keep it) and data/agent/agent.log."""

import os
import time

from .config import DATA, ensure_dirs

MAX_LOG_BYTES = 5 * 1024 * 1024  # agent.log keeps this much; the previous generation is kept as agent.log.1


def log(msg):
    """Print and append to data/agent/agent.log. Logging must never break the job it describes (disk full, wrong owner, read-only mount)."""
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        ensure_dirs()
        path = DATA / "agent.log"
        if path.exists() and path.stat().st_size > MAX_LOG_BYTES:
            os.replace(path, DATA / "agent.log.1")
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
