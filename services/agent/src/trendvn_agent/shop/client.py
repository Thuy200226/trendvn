"""Signed TikTok Shop creator requests. Credentials never enter URLs, logs, or API responses."""

import hashlib
import hmac
import http.client
import json
import re
import time
from urllib.parse import urlencode

from . import credentials

HOST = "open-api.tiktokglobalshop.com"
PATHS = (
    "/affiliate_creator/202508/profiles",
    "/affiliate_creator/202405/showcases/products",
    "/affiliate_creator/202405/open_collaborations/products/search",
    "/affiliate_creator/202509/open_collaborations/products",
    "/affiliate_creator/202505/videos/video_files",
    "/affiliate_creator/202603/videos",
)


def sign(secret, path, params, body=b"", multipart=False):
    text = path + "".join(k + str(params[k]) for k in sorted(params) if k not in ("sign", "access_token"))
    raw = text.encode() + (b"" if multipart else body)
    return hmac.new(secret.encode(), secret.encode() + raw + secret.encode(), hashlib.sha256).hexdigest()


class Client:
    def __init__(self, account):
        self.credentials = credentials.read(account)
        expiry = self.credentials.get("expires_at", 0)
        if not isinstance(expiry, (int, float)):
            raise ValueError("Hạn kết nối TikTok Shop không hợp lệ; hãy cấp quyền lại")
        if self.credentials.get("refresh_token") and expiry <= time.time() + 120:
            from .tokens import request

            renewed = request(self.credentials, refresh=self.credentials["refresh_token"])
            self.credentials = renewed
            credentials.write(account, renewed)
        for key in ("app_key", "app_secret", "access_token"):
            value = self.credentials.get(key)
            if not isinstance(value, str) or not 5 <= len(value) <= 4096 or re.search(r"\s", value):
                raise ValueError(
                    "Chưa kết nối dữ liệu hoa hồng. Đăng nhập nhà sáng tạo và cấp quyền qua ứng dụng TikTok Shop đã được duyệt"
                )

    def request(self, path, params=None, body=None, multipart=None):
        if path not in PATHS and not re.fullmatch(r"/affiliate_creator/202509/videos/\d{6,25}/status", path):
            raise ValueError("API TikTok Shop không được hỗ trợ")
        params = dict(params or {}, app_key=self.credentials["app_key"], timestamp=int(time.time()))
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode() if body is not None else b""
        params["sign"] = sign(self.credentials["app_secret"], path, params, raw, bool(multipart))
        headers = {"Content-Type": "application/json", "x-tts-access-token": self.credentials["access_token"]}
        if multipart:
            headers["Content-Type"], raw = multipart
        conn = http.client.HTTPSConnection(HOST, timeout=90 if multipart else 20)
        try:
            conn.request("POST" if body is not None or multipart else "GET", path + "?" + urlencode(params), raw or None, headers)
            response = conn.getresponse()
            data = response.read((2 << 20) + 1)
            if response.status != 200 or len(data) > 2 << 20:
                raise ValueError("TikTok Shop không trả dữ liệu (HTTP %s); kiểm tra token/quyền kết nối" % response.status)
            result = json.loads(data)
            if not isinstance(result, dict) or type(result.get("code")) is not int:
                raise ValueError("TikTok Shop trả dữ liệu không hợp lệ")
            if result.get("code") != 0:
                # Third parties may echo a request; never expose arbitrary messages containing a token.
                raise ValueError("TikTok Shop từ chối (mã %s); kiểm tra token nhà sáng tạo, quyền API và sản phẩm" % result.get("code"))
            if not isinstance(result.get("data"), dict):
                raise ValueError("TikTok Shop trả dữ liệu không hợp lệ")
            return result["data"]
        except (OSError, http.client.HTTPException):
            raise ValueError("Không kết nối được TikTok Shop; chưa xác nhận thao tác") from None
        finally:
            conn.close()

    def profile(self, expected):
        profile = self.request(PATHS[0])
        if str(profile.get("username", "")).casefold() != expected.casefold():
            raise ValueError("Token TikTok Shop không thuộc đúng @" + expected)
        return profile
