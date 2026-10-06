"""Visible creator authorization; the owner logs in/approves and a local callback supplies a single-use code."""

import secrets
import time
from urllib.parse import urlencode

from ..browser import chrome
from ..publisher.profile import profile_name
from ..worker_client import worker_get
from . import credentials, tokens
from .client import Client


def authorize(payload):
    account_id = payload.get("account")
    account = next((a for a in worker_get("/api/status").get("accounts", []) if a["id"] == account_id), None)
    if not account:
        raise ValueError("Không có tài khoản này")
    app = credentials.read(account_id)
    if any(not isinstance(app.get(k), str) or not 5 <= len(app[k]) <= 4096 for k in ("app_key", "app_secret")):
        raise ValueError("Cần cấu hình App key/App secret của ứng dụng được TikTok cấp quyền")
    pending = {"state": secrets.token_urlsafe(32), "created": time.time(), "username": account["username"], "status": "pending"}
    credentials.write(account_id, pending, "creator_authorizations")
    url = "https://shop.tiktok.com/alliance/creator/auth?" + urlencode({"app_key": app["app_key"], "state": pending["state"]})
    deadline = time.monotonic() + 240
    try:
        with chrome(profile_name(account_id), headless=False, locale="vi-VN") as ctx:
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            while time.monotonic() < deadline:
                saved = credentials.read(account_id, "creator_authorizations")
                if saved.get("status") == "denied":
                    raise ValueError("Bạn chưa đồng ý cấp quyền TikTok Shop; có thể mở lại khi sẵn sàng")
                if saved.get("status") == "received" and saved.get("state") == pending["state"]:
                    code = saved.pop("code")
                    credentials.write(account_id, dict(saved, status="used"), "creator_authorizations")
                    return complete(account, app, code)
                if page.is_closed():
                    break
                page.wait_for_timeout(1500)
        raise ValueError(
            "Chưa nhận cấp quyền. Đăng nhập/đồng ý trong cửa sổ TikTok; Redirect URL của ứng dụng phải trỏ về /shop-callback trên máy này."
        )
    finally:
        # Codes and nonce are never retained after success, denial, browser close, or timeout.
        credentials.path_for(account_id, "creator_authorizations").unlink(missing_ok=True)


def complete(account, app, code):
    current = next((a for a in worker_get("/api/status").get("accounts", []) if a["id"] == account["id"]), None)
    if not current or current["username"] != account["username"]:
        raise ValueError("Tài khoản đã thay đổi trong lúc cấp quyền; hãy bắt đầu lại")
    granted = tokens.request(app, code=code)
    client = Client.__new__(Client)
    client.credentials = granted
    profile = client.profile(account["username"])
    if "ADD_AFFILIATE_PERMISSION" not in profile.get("permissions", []):
        raise ValueError("Tài khoản chưa có quyền tiếp thị liên kết nhà sáng tạo")
    credentials.write(account["id"], dict(granted, username=account["username"]))
    return {"authorized": True, "username": account["username"], "can_post": "creator.video.write" in granted["granted_scopes"]}
