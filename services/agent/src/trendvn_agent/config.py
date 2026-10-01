"""Paths and settings of the agent: the project's .env, the shared data folders, where the worker lives."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # services/agent/src/trendvn_agent/config.py -> the project root
DATA = ROOT / "data" / "agent"  # browser profiles and logs; never mounted into containers
RUNTIME = ROOT / "data" / "worker"  # shared with the worker container as /data


def load_env():
    """The project's .env (same reader every tool uses: comments, quotes), overridden by TRENDVN_* variables in the environment."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from envfile import parse

    env = parse(ROOT / ".env")
    env.update({k: v for k, v in os.environ.items() if k.startswith("TRENDVN_")})
    return env


ENV = load_env()
WORKER_URL = ENV.get("TRENDVN_WORKER_URL", "http://127.0.0.1:%s" % ENV.get("TRENDVN_WORKER_PORT", "5681"))
TOKEN = ENV.get("TRENDVN_TOKEN", "")


def ensure_dirs():
    DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
    (DATA / "shots").mkdir(exist_ok=True, mode=0o700)
