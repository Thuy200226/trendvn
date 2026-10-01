"""Calls to the worker API with the shared bearer token."""

import json
import urllib.error
import urllib.request

from .config import TOKEN, WORKER_URL


def worker(path, payload=None, timeout=900):
    """Call the isolated worker API with the shared bearer token."""
    if len(TOKEN) < 32:
        raise RuntimeError("TRENDVN_TOKEN missing; run ./trendvn install")
    data = json.dumps(payload if payload is not None else {}).encode()
    req = urllib.request.Request(
        WORKER_URL + path,
        data=data if payload is not None or path.startswith("/api/") else None,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"worker {path} -> {e.code}: {detail}") from None


def worker_get(path, timeout=30):
    req = urllib.request.Request(WORKER_URL + path, headers={"Authorization": "Bearer " + TOKEN})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)
