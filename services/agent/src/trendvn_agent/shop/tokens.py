"""Official creator code exchange and token refresh, with identity/scope checks and sanitized errors."""

import http.client
import json
import time
from urllib.parse import urlencode

READ_SCOPES = {"creator.affiliate.info", "creator.affiliate_collaboration.read"}
HOST = "auth.tiktok-shops.com"


def request(app, code=None, refresh=None):
    path = "/api/v2/token/get" if code else "/api/v2/token/refresh"
    params = {
        "app_key": app["app_key"],
        "app_secret": app["app_secret"],
        "grant_type": "authorized_code" if code else "refresh_token",
        "auth_code" if code else "refresh_token": code or refresh,
    }
    conn = http.client.HTTPSConnection(HOST, timeout=20)
    try:
        conn.request("GET", path + "?" + urlencode(params))
        response = conn.getresponse()
        raw = response.read((1 << 20) + 1)
        if response.status != 200 or len(raw) > 1 << 20:
            raise ValueError("Không nhận được quyền TikTok Shop; hãy cấp quyền lại")
        data = json.loads(raw)
        if not isinstance(data, dict) or type(data.get("code")) is not int or data["code"] != 0 or not isinstance(data.get("data"), dict):
            raise ValueError("TikTok Shop chưa cấp token hợp lệ; kiểm tra ứng dụng và cấp quyền lại")
        return validate(app, data["data"])
    except (OSError, http.client.HTTPException, json.JSONDecodeError):
        raise ValueError("Kết nối cấp quyền TikTok Shop gián đoạn; hãy mở lại bước cấp quyền") from None
    finally:
        conn.close()


def validate(app, data):
    if type(data.get("user_type")) is not int or data["user_type"] != 1:
        raise ValueError("Cần đăng nhập nhà sáng tạo; token người bán không dùng được")
    scopes = data.get("granted_scopes")
    if (
        not isinstance(scopes, list)
        or not all(isinstance(s, str) for s in scopes)
        or not READ_SCOPES <= set(scopes)
        or not {"creator.showcase.read", "creator.video.write"} & set(scopes)
    ):
        raise ValueError("Ứng dụng chưa được cấp đủ quyền đọc showcase/tiếp thị liên kết nhà sáng tạo")
    for key in ("access_token", "refresh_token", "open_id"):
        if not isinstance(data.get(key), str) or not 1 <= len(data[key]) <= 4096 or any(c.isspace() for c in data[key]):
            raise ValueError("TikTok Shop trả thông tin cấp quyền không hợp lệ")
    if app.get("open_id") and app["open_id"] != data["open_id"]:
        raise ValueError("Quyền làm mới thuộc tài khoản khác; dừng kết nối")
    expiry = data.get("access_token_expire_in")
    if type(expiry) is not int or expiry <= 0:
        raise ValueError("TikTok Shop chưa xác nhận hạn token")
    expires_at = expiry if expiry > 1_000_000_000 else time.time() + expiry
    if expires_at <= time.time():
        raise ValueError("Token đã hết hạn; cần cấp quyền lại")
    return dict(
        app, **{k: data[k] for k in ("access_token", "refresh_token", "open_id", "user_type", "granted_scopes")}, expires_at=expires_at
    )
