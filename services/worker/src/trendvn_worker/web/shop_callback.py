"""Receive a local single-use creator OAuth callback without exposing its code or state."""

import hmac
import json
import os
import re
import threading
import time

SCRIPT = 'history.replaceState(null,"","/shop-callback")'
LOCK = threading.Lock()


def capture(app, query):
    state = query.get("state", [])
    if len(state) != 1 or not re.fullmatch(r"[A-Za-z0-9_-]{43}", state[0]):
        raise ValueError("Phiên cấp quyền không hợp lệ hoặc đã hết hạn; hãy bắt đầu lại")
    folder = app.store.root / "creator_authorizations"
    with LOCK:
        for account in app.store.accounts():
            path = folder / (account["id"] + ".json")
            if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
                continue
            try:
                saved = json.loads(path.read_text())
            except (OSError, ValueError):
                continue
            if not isinstance(saved, dict) or not isinstance(saved.get("state"), str):
                continue
            if not hmac.compare_digest(saved["state"], state[0]):
                continue
            created = saved.get("created")
            if saved.get("status") != "pending" or not isinstance(created, (int, float)) or not 0 <= time.time() - created <= 300:
                break
            if saved.get("username") != account["username"]:
                break
            code = query.get("code", [])
            if query.get("error"):
                saved["status"] = "denied"
            elif len(code) == 1 and 1 <= len(code[0]) <= 4096 and not any(c.isspace() for c in code[0]):
                saved.update(status="received", code=code[0])
            else:
                break
            part = path.with_suffix(".part")
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w") as handle:
                json.dump(saved, handle)
            part.replace(path)
            return saved["status"]
    raise ValueError("Phiên cấp quyền không hợp lệ hoặc đã dùng; hãy bắt đầu lại")


def page(message):
    # No OAuth value is rendered. Clear sensitive query parameters in browser history.
    return (
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Cấp quyền TikTok Shop</title><script>" + SCRIPT + "</script>"
        '<main style="font:16px/1.5 system-ui;max-width:36rem;margin:3rem auto;padding:1rem">'
        "<h1>Kết nối nhà sáng tạo</h1><p>" + message + '</p><a href="/#search">Quay lại tìm kiếm và xem kết quả xác minh</a></main>'
    )
