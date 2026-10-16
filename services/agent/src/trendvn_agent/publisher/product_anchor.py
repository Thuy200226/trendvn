"""Select and verify a single exact Shop ID in Studio; names and the first search row are never identity proof."""

import re
from urllib.parse import urlsplit, parse_qs

ID = re.compile(r"[0-9]{6,25}")


def link_ids(href):
    location = urlsplit(href or "")
    if location.hostname and not (location.hostname == "tiktok.com" or location.hostname.endswith(".tiktok.com")):
        return set()
    if location.scheme not in ("", "https"):
        return set()
    ids = set()
    match = re.search(r"/(?:view/product/|shop/pdp/(?:[^/]+/)?|product/)(\d{6,25})(?:/|$)", location.path)
    if match:
        ids.add(match.group(1))
    ids.update(p for p in parse_qs(location.query).get("product_id", []) if ID.fullmatch(p))
    return ids


def node_ids(node):
    ids = set()
    for key in ("data-product-id", "data-product_id"):
        value = node.get_attribute(key)
        if isinstance(value, str) and ID.fullmatch(value):
            ids.add(value)
    for href in node.locator("a[href]").evaluate_all('(nodes)=>nodes.map(n=>n.getAttribute("href"))'):
        ids.update(link_ids(href))
    # Product ID displayed in the row, never a partial substring of a longer number.
    ids.update(re.findall(r"(?<![0-9])[0-9]{16,25}(?![0-9])", node.inner_text()))
    return ids


def exact_row(modal, pid):
    rows = modal.locator("tbody tr")
    matched = [rows.nth(i) for i in range(rows.count()) if rows.nth(i).is_visible() and node_ids(rows.nth(i)) == {pid}]
    return matched[0] if len(matched) == 1 else None


def attached_id(target, pid):
    nodes = target.locator('[data-product-id],[data-product_id],a[href*="/view/product/"],a[href*="/shop/pdp/"],a[href*="product_id="]')
    found = set()
    for i in range(nodes.count()):
        node = nodes.nth(i)
        if not node.is_visible() or node.locator('xpath=ancestor::*[@role="dialog"]').count():
            continue
        # Include the node itself when it is the link/attribute holder.
        value = node.get_attribute("data-product-id") or node.get_attribute("data-product_id")
        if isinstance(value, str) and ID.fullmatch(value):
            found.add(value)
        href = node.get_attribute("href")
        if href:
            found.update(link_ids(href))
    return found == {pid}


def validate_proof(job):
    binding = job.get("product_binding")
    if not binding:
        if job.get("commerce_required") or job.get("product_verification"):
            raise ValueError("Video bán hàng thiếu giỏ hàng đã đối chiếu; không đăng video trống giỏ")
        return
    proof = job.get("product_verification")
    if not isinstance(binding, dict) or not isinstance(binding.get("product_id"), str) or not ID.fullmatch(binding["product_id"]):
        raise ValueError("Giỏ hàng thiếu mã Shop hợp lệ; dừng trước tải video")
    expected = {
        "version": 1,
        "status": "same",
        "account": job.get("account"),
        "username": job.get("target"),
        "output_hash": job.get("output_hash"),
        "product_id": binding["product_id"],
        "binding": binding,
    }
    if not isinstance(proof, dict) or any(proof.get(k) != v for k, v in expected.items()):
        raise ValueError("Chưa xác minh nội dung thành phẩm đúng sản phẩm giỏ hàng; dừng đăng")


def own_item_product_ids(item, video_id):
    """Explicit commerce identifiers on the exact newly posted item, never recommended items or an anchor's own ID."""
    if not isinstance(item, dict) or str(item.get("id")) != video_id:
        return set()
    found = set()

    def explicit(value):
        if not isinstance(value, dict):
            return
        for key in ("product_id", "productId"):
            pid = value.get(key)
            if isinstance(pid, str) and ID.fullmatch(pid):
                found.add(pid)

    # No arbitrary recursion: recommendation trees are not this video's cart.
    for key in ("anchors", "productAnchors"):
        entries = item.get(key)
        if isinstance(entries, list):
            for anchor in entries[:100]:
                explicit(anchor)
    for key in ("commerceInfo", "commerce_info"):
        explicit(item.get(key))

    return found


def published_cart(ctx, url, video_id, pid):
    """Public post verification is read-only and fails closed when TikTok's web response omits the cart."""
    import json

    page = ctx.new_page()
    found = set()

    def observed(response):
        if response.status != 200 or urlsplit(response.url).path != "/api/item/detail/":
            return
        try:
            raw = response.body()
            if len(raw) <= 4 << 20:
                item = (json.loads(raw).get("itemInfo") or {}).get("itemStruct")
                found.update(own_item_product_ids(item, video_id))
        except Exception:
            pass

    page.on("response", observed)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        data = page.locator("#__UNIVERSAL_DATA_FOR_REHYDRATION__")
        if data.count():
            detail = json.loads(data.text_content() or "{}").get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
            item = (detail.get("itemInfo") or {}).get("itemStruct")
            found.update(own_item_product_ids(item, video_id))
        return found == {pid}
    except Exception:
        return False
    finally:
        if not page.is_closed():
            page.close()


def _open_picker(page, target):
    heading = target.locator('span:has-text("Thêm liên kết")').first
    button = None
    if heading.count():
        candidate = heading.locator(
            'xpath=ancestor::div[contains(@class,"title-v2")]/following-sibling::div//button | ancestor::div[2]//button'
        ).first
        if candidate.count() and candidate.is_visible():
            button = candidate
    if button is None:
        candidate = target.locator('button:has-text("+ Thêm"),button:has-text("Thêm liên kết")').first
        if candidate.count() and candidate.is_visible():
            button = candidate
    if button is None:
        return None
    button.click()
    page.wait_for_timeout(2000)
    next_button = page.locator('button:has-text("Tiếp"),button:has-text("Next")').first
    if next_button.count() and next_button.is_visible():
        next_button.click()
        page.wait_for_timeout(2000)
    modal = page.locator('div[role="dialog"]').last
    return modal if modal.count() and modal.is_visible() else None


def _choose_product(page, modal, binding):
    from ..worker_client import worker

    search = modal.locator('input[placeholder*="Tìm kiếm sản phẩm"],input[placeholder*="Search products"]').first
    if not search.count() or not search.is_visible():
        return False
    pid = binding["product_id"]
    search.fill(pid)
    search.press("Enter")
    page.wait_for_timeout(2000)
    row = exact_row(modal, pid)
    if row is None:
        return False
    worker(
        "/api/product/check-row",
        {"account": binding["account"], "username": binding["username"], "binding": binding, "product_id": pid, "title": row.inner_text()},
        timeout=20,
    )
    radio = row.locator('input[type="radio"]')
    if radio.count() != 1:
        return False
    radio.check()
    if not radio.is_checked() or exact_row(modal, pid) is None:
        return False
    next_button = modal.locator('button:has-text("Tiếp"),button:has-text("Next")').first
    if not next_button.count() or not next_button.is_enabled():
        return False
    next_button.click()
    page.wait_for_timeout(2000)
    return True


def _add_product(page, target, binding):
    modal = page.locator('div[role="dialog"]').last
    name = modal.locator("input").first
    if not name.count() or not name.is_visible():
        return False
    clean = re.sub(r"[%@#$^&*+=~`|<>/\\]", " ", name.input_value() or binding["title"])
    name.fill(re.sub(r"\s+", " ", clean).strip()[:30].strip())
    button = modal.locator('button:has-text("Thêm"),button:has-text("Add")').last
    if not button.count() or not button.is_visible() or not button.is_enabled():
        return False
    button.click()
    page.wait_for_timeout(2000)
    return attached_id(target, binding["product_id"])


def attach(page, target, binding):
    from ..log import log

    try:
        pid = binding.get("product_id")
        if not isinstance(pid, str) or not ID.fullmatch(pid):
            return False
        if attached_id(target, pid):
            return True
        modal = _open_picker(page, target)
        if modal is None or not _choose_product(page, modal, binding):
            return False
        return _add_product(page, target, binding)
    except Exception as error:
        log("Không xác minh được giỏ hàng; dừng trước Đăng: " + str(error)[:120])
        return False
