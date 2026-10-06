"""Products and commissions obtained from the selected creator's authorized API, never public product metadata."""

import re
import time
from urllib.parse import urlsplit

from .client import Client
from ..worker_client import worker_get


def context(account_id):
    account = next((a for a in worker_get("/api/status").get("accounts", []) if a["id"] == account_id), None)
    if not account:
        raise ValueError("Không có tài khoản TikTok này")
    client = Client(account_id)
    profile = client.profile(account["username"])
    if "ADD_AFFILIATE_PERMISSION" not in profile.get("permissions", []):
        raise ValueError("TikTok Shop chưa cấp quyền tiếp thị liên kết cho @" + account["username"])
    return account, client, profile


def product_row(raw, showcase=False):
    pid, title = raw.get("id"), raw.get("title")
    commission = (raw.get("commission") or {}).get("rate")
    if not isinstance(pid, str) or not re.fullmatch(r"\d{6,25}", pid) or not isinstance(title, str):
        return None
    if isinstance(commission, bool) or not isinstance(commission, (int, float)) or not 0 < commission <= 10000:
        return None
    status = raw.get("status") or {}
    available = (
        (
            status.get("inventory_status") == "IN_STOCK"
            and status.get("review_status") == "APPROVED"
            and status.get("is_hidden") is False
            and status.get("added_status") == "ADDED"
        )
        if showcase
        else raw.get("has_inventory") is True
    )
    if not available:
        return None
    # A misleading API URL must not replace the authoritative product id (the official sample itself has mismatched ids).
    link = raw.get("detail_link") or ""
    u = urlsplit(link)
    if u.scheme != "https" or u.hostname != "shop.tiktok.com" or u.username or u.password:
        return None
    url = "https://shop.tiktok.com/view/product/" + pid
    return {
        "product_id": pid,
        "title": title[:500],
        "url": url,
        "commission": "%g%%" % (commission / 100),
        "eligible": True,
        "can_attach": showcase,
        "source": "creator_authorized",
        "in_showcase": showcase,
    }


def showcase_products(client):
    products, token, tokens = [], "", set()
    deadline = time.monotonic() + 120
    for _ in range(100):
        if time.monotonic() > deadline:
            raise ValueError("Đồng bộ quá 2 phút; thử lại sau, không dùng danh sách dở dang")
        data = client.request(
            "/affiliate_creator/202405/showcases/products",
            {"origin": "SHOWCASE", "page_size": 20, **({"page_token": token} if token else {})},
        )
        for raw in data.get("products", []):
            row = product_row(raw, True)
            if row:
                products.append(row)
        token = data.get("next_page_token")
        if not token:
            return products
        if token in tokens:
            raise ValueError("TikTok Shop lặp trang danh sách; không dùng dữ liệu chưa đầy đủ")
        tokens.add(token)
    if token:
        raise ValueError("Danh sách vượt 2.000 sản phẩm; cần thu hẹp trước khi đồng bộ")
    return products


def search(payload):
    account, client, profile = context(payload.get("account"))
    products = showcase_products(client)
    query = payload.get("query", "")
    if not isinstance(query, str) or len(query) > 160:
        raise ValueError("Từ khóa tìm sản phẩm không hợp lệ")
    pid = payload.get("product_id", "")
    if pid and (not isinstance(pid, str) or not re.fullmatch(r"\d{6,25}", pid)):
        raise ValueError("Mã sản phẩm không hợp lệ")
    if pid:
        data = client.request("/affiliate_creator/202509/open_collaborations/products", {"product_ids": pid}, {})
    elif query:
        data = client.request(
            "/affiliate_creator/202405/open_collaborations/products/search", {"page_size": 20}, {"title_keywords": query.split()[:20]}
        )
    else:
        data = {}
    if data:
        known = {p["product_id"] for p in products}
        for raw in data.get("products", []):
            row = product_row(raw)
            if row and row["product_id"] not in known:
                products.append(row)
    products = products[:2020]
    return {
        "account": account["id"],
        "username": account["username"],
        "source": "creator_authorized",
        "products": products,
        "region": profile.get("selection_region"),
        "permissions": profile.get("permissions", []),
    }
