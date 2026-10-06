"""Search a creator's explicitly supplied catalogue; unverified imports never assert commission eligibility."""

import json
import os
import re
import time

from ..domain.product_search import match_identity, public_url


def search_catalog(store, account, identity, allow_stale=False):
    path = store.root / "creator_catalogs" / (account + ".json")
    if not path.exists():
        raise ValueError(
            "Chưa có danh sách TikTok Shop được xác minh cho tài khoản này. Cần kết nối dữ liệu nhà sáng tạo; phiên đăng nhập TikTok thông thường chưa đủ để xác nhận hoa hồng."
        )
    saved = json.loads(path.read_text())
    if (
        saved.get("account") != account
        or saved.get("username") != (store.account(account) or {}).get("username")
        or (not allow_stale and time.time() - saved.get("verified_at", 0) > 3600)
    ):
        raise ValueError("Danh sách sản phẩm đã hết hạn xác minh; cần đồng bộ lại từ tài khoản nhà sáng tạo")
    results = []
    for product in saved.get("products", [])[:2020]:
        match = match_identity(identity, product.get("title", ""), product.get("product_id", ""))
        if match["level"] == "different" or (identity.get("query") and match["score"] == 0):
            continue
        results.append(dict(product, match=match))
    return sorted(results, key=lambda p: p["match"]["score"], reverse=True)[:20]


def save_catalog(store, payload):
    """Called by an authenticated connector after reading the creator context, never by pasted product details."""
    account = store.account(payload.get("account"))
    if not account or payload.get("username", "").casefold() != account["username"].casefold():
        raise ValueError("Danh sách không thuộc đúng tài khoản TikTok")
    if payload.get("source") != "creator_authorized" or not isinstance(payload.get("products"), list) or len(payload["products"]) > 2020:
        raise ValueError("Cần dữ liệu từ kết nối nhà sáng tạo được cấp quyền")
    products = []
    for product in payload["products"]:
        if not isinstance(product, dict):
            raise ValueError("Dữ liệu sản phẩm không hợp lệ")
        pid, title = product.get("product_id"), product.get("title")
        if not isinstance(pid, str) or not re.fullmatch(r"\d{6,25}", pid) or not isinstance(title, str) or not 0 < len(title) <= 500:
            raise ValueError("Mã hoặc tên sản phẩm không hợp lệ")
        commission = product.get("commission")
        if not isinstance(commission, str) or len(commission) > 80:
            raise ValueError("Cần thông tin hoa hồng từ kết nối nhà sáng tạo")
        if product.get("eligible") is not True:
            continue
        products.append(
            {
                "product_id": pid,
                "title": title,
                "url": public_url(product.get("url")),
                "commission": commission,
                "eligible": True,
                "can_attach": product.get("can_attach") is True,
                "source": "creator_authorized",
                "in_showcase": product.get("in_showcase") is True,
            }
        )
    folder = store.root / "creator_catalogs"
    folder.mkdir(exist_ok=True, mode=0o700)
    path = folder / (account["id"] + ".json")
    partial = path.with_suffix(".part")
    with os.fdopen(os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as handle:
        handle.write(
            json.dumps({"account": account["id"], "username": account["username"], "verified_at": time.time(), "products": products})
        )
    partial.replace(path)
    return {"count": len(products)}
