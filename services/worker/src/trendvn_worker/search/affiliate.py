"""Is a pasted TikTok share link the product the owner is working on, and is it a commission link? Judged from the link and the page it
leads to; no account API is involved. Resolving the link is the only network part (`inspect`); the verdict itself is pure."""

from ..domain.product_links import attribution, classify, tiktok_host
from ..domain.product_match import match_identity
from . import fetch

# What a page says about itself when it shows a login or a consent wall instead of the product: not a product name.
GENERIC_TITLES = {"tiktok", "tiktok shop", "tiktok - make your day", "log in", "đăng nhập", "tiktok - làm cho ngày của bạn thêm tuyệt vời"}
LIKELY_FROM = 60  # a title that shares at least this much with what was asked is worth the owner's look; less is not an answer
SUMMARY = {
    "found": "Đã đọc được sản phẩm từ link; chưa có sản phẩm nào khác trong khung chat để đối chiếu.",
    "exact": "Đúng sản phẩm: cùng mã sản phẩm.",
    "likely": "Có vẻ đúng sản phẩm theo tên, nhưng chưa có mã để chắc chắn. Hãy xem lại trước khi dùng.",
    "unknown": "Chưa đủ thông tin để biết đây có phải sản phẩm đó không.",
    "different": "Đây là sản phẩm khác. Đừng dùng link này.",
    "invalid": "Đường dẫn này không dẫn tới một sản phẩm TikTok Shop.",
}


def inspect(url, follow=fetch.follow, page_title=fetch.page_title):
    """What the link leads to: {'input','chain','final','product_id','title','markers','tracked','stopped'}. Only TikTok addresses are
    followed (a hop to anywhere else is recorded, never requested); a page that cannot be read still gives the product id."""
    link = classify(url)
    if link is None or not tiktok_host(link["host"]):
        raise ValueError("Chỉ nhận đường dẫn https của TikTok")
    trail = follow(url, allow=tiktok_host)
    chain = list(trail["chain"])
    onsite = [u for u in chain if (classify(u) or {}).get("host") and tiktok_host(classify(u)["host"])]
    product_id = next((classify(u)["product_id"] for u in onsite if classify(u)["product_id"]), None)
    markers = {}
    for hop in onsite:
        for name, value in attribution(hop)["markers"].items():
            markers.setdefault(name, value)
    final = onsite[-1] if onsite else url
    title = ""
    if product_id:
        try:
            title = page_title(final)[0]
        except (ValueError, OSError):
            title = ""  # a wall or a timeout: the id alone still decides
        if title.strip().lower() in GENERIC_TITLES:
            title = ""
    return {
        "input": url, "chain": chain, "final": final, "product_id": product_id, "title": title,
        "markers": markers, "tracked": bool(markers), "stopped": trail["stopped"],
    }  # fmt: skip


def _check(label, state, detail):
    return {"label": label, "state": state, "detail": detail}


def _same_creator(markers, known):
    return any(markers.get(name) == value for earlier in known for name, value in earlier.items())


def _identity_check(identity, found):
    """(verdict, checks) of what the link says about the product itself."""
    expected, seen = str(identity.get("product_id") or ""), found["product_id"]
    if not seen:
        return "invalid", [_check("Mã sản phẩm", "bad", "Không đọc được mã sản phẩm từ đường dẫn này")]
    if not identity:
        return "found", [
            _check("Mã sản phẩm", "ok", "Mã %s" % seen),
            _check("Tên sản phẩm", "ok" if found["title"] else "warn", found["title"] or "Không đọc được tên trên trang"),
        ]
    if expected:
        same = expected == seen
        detail = "Mã %s trùng với sản phẩm đang tìm" % seen if same else "Mã %s khác mã %s đang tìm" % (seen, expected)
        return ("exact" if same else "different"), [_check("Mã sản phẩm", "ok" if same else "bad", detail)]
    checks = [_check("Mã sản phẩm", "warn", "Mã %s; chưa có mã của sản phẩm đang tìm để so" % seen)]
    if not found["title"]:
        return "unknown", checks + [_check("Tên sản phẩm", "warn", "Không đọc được tên trên trang; hãy tự mở link xem")]
    match = match_identity(identity, found["title"])
    state = {"candidate": "ok" if match["score"] >= LIKELY_FROM else "warn", "different": "bad"}.get(match["level"], "warn")
    checks.append(_check("Tên sản phẩm", state, "%s: %s" % (found["title"][:120], match["reason"])))
    if match["level"] == "different":
        return "different", checks
    return ("likely" if match["level"] == "candidate" and match["score"] >= LIKELY_FROM else "unknown"), checks


def _creator_checks(found, known):
    """(checks, settled): whether the link carries the owner's creator marks, and whether those agree with links already confirmed."""
    if not found["tracked"]:
        return [_check("Dấu hiệu nhà sáng tạo", "warn", "Không có mã nhà sáng tạo: link thường, bấm vào không tính hoa hồng")], False
    names = ", ".join(sorted(found["markers"]))
    checks = [_check("Dấu hiệu nhà sáng tạo", "ok", "Có tham số của người chia sẻ (%s)" % names)]
    if not known:
        return (
            checks + [_check("Mã nhà sáng tạo", "info", "Đây là link đầu tiên của tài khoản: xác nhận để lưu làm mốc cho các link sau")],
            False,
        )
    if _same_creator(found["markers"], known):
        return checks + [_check("Mã nhà sáng tạo", "ok", "Trùng mã của các link bạn đã xác nhận trước")], True
    return checks + [_check("Mã nhà sáng tạo", "warn", "Khác mã của các link bạn đã xác nhận trước: có thể là link của người khác")], False


def verdict(identity, found, known=()):
    """The judgement on a resolved link: {'verdict','summary','kind','needs_confirmation','checks','product_id','title'}.
    `identity` is what the thread is about, `known` the creator marks of links this account's owner already confirmed.
    The verdict is about the product (exact only on the same product id); `needs_confirmation` is about the link: nothing is ever
    accepted as the owner's commission link on the machine's word alone unless it carries the marks of the links already confirmed."""
    result, checks = _identity_check(identity, found)
    if result == "invalid":
        return {
            "verdict": result,
            "summary": SUMMARY[result],
            "kind": "plain",
            "needs_confirmation": False,
            "checks": checks,
            "product_id": None,
            "title": "",
        }
    creator, settled = _creator_checks(found, known)
    checks += creator
    needs = result in ("likely", "unknown") or (result in ("exact", "found") and not settled)
    return {
        "verdict": result, "summary": SUMMARY[result], "kind": "affiliate" if found["tracked"] else "plain",
        "needs_confirmation": needs, "checks": checks, "product_id": found["product_id"], "title": found["title"],
    }  # fmt: skip
