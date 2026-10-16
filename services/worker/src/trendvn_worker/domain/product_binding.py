"""Resolve a unique Shop product and bind content evidence to its account and exact rendered bytes."""

import re
from urllib.parse import urlsplit, parse_qs

from .product_links import classify
from .product_match import match_identity, tokens

PRODUCT_ID = re.compile(r"[0-9]{6,25}")
VERSION = 1


def commerce_required(binding, metadata):
    """Preserve commerce intent, including old jobs before a dedicated flag existed."""
    metadata = metadata if isinstance(metadata, dict) else {}
    reference = metadata.get("product_reference")
    return bool(
        binding
        or metadata.get("commerce_required")
        or metadata.get("product_verification")
        or (isinstance(reference, dict) and reference.get("sales"))
    )


def _colors(text):
    groups = {
        "black": r"\bblack\b|\bđen\b|黑色",
        "white": r"\bwhite\b|\btrắng\b|白色",
        "red": r"\bred\b|\bđỏ\b|红色",
        "blue": r"\bblue\b|xanh dương|蓝色",
        "green": r"\bgreen\b|xanh lá|绿色",
        "pink": r"\bpink\b|\bhồng\b|粉色",
    }
    return {name for name, pattern in groups.items() if re.search(pattern, text, re.I)}


def strict_title(identity, title):
    """A suggestion is never exact just because one word or the search product ID matches."""
    if not isinstance(identity, dict) or not isinstance(title, str):
        return False
    if any(not isinstance(identity.get(k, ""), str) for k in ("name", "brand", "model", "variant")):
        return False
    asked = " ".join(identity.get(k, "") for k in ("name", "model", "variant"))
    expected_colors, found_colors = _colors(asked), _colors(title)
    if expected_colors and expected_colors != found_colors:
        return False
    for unit in ("ml", "l", "gb", "tb", "mah", "w", "%", "cm", "mm", "kg", "g", "inch"):
        pattern = r"(?<![a-z0-9])(\d+(?:[.,]\d+)?)\s*" + re.escape(unit) + r"(?![a-z])"
        wanted = set(re.findall(pattern, asked.casefold()))
        found = set(re.findall(pattern, title.casefold()))
        if wanted and wanted != found:
            return False
    editions = {"se", "neo", "edition", "gen", "ultra", "pro", "max", "mini", "lite", "plus", "air", "turbo", "gt"}
    if (tokens(title) & editions) - tokens(asked):
        return False
    accessory = {"case", "cover", "replacement", "adapter", "sleeve"}
    if (tokens(title) & accessory) - tokens(asked) or ("op" in tokens(title) and "lung" in tokens(title) and "op" not in tokens(asked)):
        return False
    comparable = dict(identity, product_id="", soft=False, variant_soft=False)
    result = match_identity(comparable, title)
    if result["level"] != "candidate" or result["score"] != 100:
        return False
    brand, model = tokens(identity.get("brand") or ""), tokens(identity.get("model") or "")
    if not brand or not model:
        return False  # a generic product/category has no unique model to attach automatically
    return brand <= tokens(title) and model <= tokens(title)


def catalog_binding(identity, links, account, username):
    """Only a unique, structurally valid product from this receiver's saved catalog is eligible."""
    expected = str(identity.get("product_id") or "")
    found = []
    for entry in links:
        pid = str(entry.get("product_id") or "")
        link = classify(entry.get("url", ""))
        if not PRODUCT_ID.fullmatch(pid) or not link or link["platform"] != "tiktok" or link["conflict"]:
            continue
        ids = set(parse_qs(urlsplit(entry["url"]).query).get("product_id", []))
        if ids and ids != {pid}:
            continue
        # Saved short links carry a resolved catalog ID; Studio must still verify that ID and its live title.
        if link["kind"] != "short" and link["product_id"] != pid:
            continue
        if entry.get("account", account) != account:
            continue
        if expected and pid != expected:
            continue
        if not strict_title(identity, entry.get("title") or ""):
            continue
        found.append(
            {
                "product_id": pid,
                "url": entry["url"],
                "title": entry["title"],
                "account": account,
                "username": username,
                "identity": {
                    "name": entry["title"],
                    "brand": identity.get("brand", ""),
                    "model": identity.get("model", ""),
                    "variant": identity.get("variant", ""),
                },
            }
        )
    unique = {i["product_id"]: i for i in found}
    return next(iter(unique.values())) if len(unique) == 1 else None


def validate_binding(binding, links, account, username):
    if (
        not isinstance(binding, dict)
        or not isinstance(binding.get("identity"), dict)
        or binding.get("account") != account
        or binding.get("username") != username
    ):
        raise ValueError("Giỏ hàng chưa được đối chiếu đúng tài khoản; cần chọn lại sản phẩm Shop")
    identity = dict(binding.get("identity") or {}, product_id=binding.get("product_id"))
    current = catalog_binding(identity, links, account, username)
    if not current or any(current.get(k) != binding.get(k) for k in ("product_id", "url", "title", "identity")):
        raise ValueError("Sản phẩm Shop đã đổi hoặc chưa khớp chính xác hãng/model/biến thể; dừng đăng")
    return current


def verify_evidence(proof, binding, output_hash, account, username):
    if not isinstance(proof, dict) or not isinstance(binding, dict):
        raise ValueError("Chưa xác minh sản phẩm trong thành phẩm với giỏ hàng; dừng đăng")
    expected = {
        "version": VERSION,
        "output_hash": output_hash,
        "product_id": binding["product_id"],
        "account": account,
        "username": username,
        "binding": binding,
    }
    if proof.get("status") != "same" or any(proof.get(k) != v for k, v in expected.items()):
        raise ValueError("Bằng chứng video và sản phẩm thiếu hoặc đã thay đổi; cần kiểm lại trước khi đăng")
    return True
