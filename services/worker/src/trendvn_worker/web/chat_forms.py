"""What the product chat accepts from the page: a message (words, links, photos, documents) and an action on one of the answers.
Both arrive as JSON from the page's script and are checked here; the handler has already checked origin and CSRF."""

import re
import threading

from ..domain import discovery
from ..domain.channels import CHANNELS
from ..domain.discovery import PRODUCT_CATEGORIES
from ..domain.product_links import product_link
from ..domain.product_search import validate_input

SOURCES = ("auto", "tiktok", "douyin", "kuaishou", "instagram")
SEND_LOCK = threading.Lock()
SAID_LIMIT = 1000  # of the owner's words kept in the log; the full text only goes to the job that reads it


def _account(app, payload, fallback=None):
    account = payload.get("account") or fallback
    if not isinstance(account, str) or not app.store.account(account):
        raise ValueError("Chọn tài khoản nhận video")
    return account


def _said(reference, link):
    return {
        "text": reference["text"][:SAID_LIMIT],
        "files": [{"name": f["name"], "kind": "image" if "mime" in f and f["mime"].startswith("image/") else "document"} for f in reference["files"]],
        "link": bool(link),
    }  # fmt: skip


def _start(app, mid, kind, key=None, reference=None, discard=False):
    """Start the job behind an answer. When it cannot start the answer says so instead of staying 'running'; an answer that nobody asked
    for in words (a sign-in or a search started by a button) is dropped instead, the refusal reaching the owner as the click's own message.
    """
    try:
        app.tasks.start(kind, str(key or mid), reference)
    except Exception as error:
        if discard:
            app.store.chat_delete(mid)
        else:
            app.store.chat_set(mid, "error", error=str(error)[:300] or "Không bắt đầu được")
        raise
    return {"id": mid}


def send(app, payload):
    key = payload.get("request_key")
    if key is not None and (not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", key)):
        raise ValueError("Mã yêu cầu không hợp lệ")
    account = _account(app, payload)
    with SEND_LOCK:
        old = app.store.chat_request(key) if key else None
        if old and old["account"] != account:
            raise ValueError("Yêu cầu này thuộc tài khoản khác")
        if (
            old and old["state"] == "error"
        ):  # the first try failed (the browser was busy, the model was down): the same request is tried again
            app.store.chat_release_request(old["id"])
            old = None
        if old:
            return {"id": old["id"]}
        return _send(app, payload, account, key)


def _send(app, payload, account, key):
    """A message from the owner. A TikTok product link (without files) is checked as a share link against the product in the chat;
    anything else describes a product to recognise."""
    chosen = discovery.options(payload)
    reference = validate_input(payload)
    reference["sales"] = chosen["sales"]

    # 1. Nếu tick chọn tìm video bán hàng và chưa có text / file: tổng hợp top sản phẩm bán chạy theo ngành hàng
    if chosen.get("sales") and not reference["text"] and not reference["files"]:
        cat = chosen.get("category")
        top_items = app.store.category_top_products(cat, account=account)
        cat_label = PRODUCT_CATEGORIES.get(cat, ("", ""))[0]
        body = {
            "category": cat,
            "category_label": cat_label,
            "products": top_items,
            "account": account,
            "account_username": app.store.account(account)["username"],
            "discovery": chosen,
        }
        said_ref = dict(reference, text="Xem top sản phẩm bán chạy ngành " + cat_label)
        mid = app.store.chat_ask(account, _said(said_ref, None), "top_products", body, request_key=key)
        app.store.chat_set(mid, "done")
        return {"id": mid}

    if not reference["text"] and not reference["files"]:
        reference["text"] = discovery.fallback_text(chosen)
    if not reference["text"] and not reference["files"]:
        raise ValueError("Hãy nhập mô tả, dán link hoặc thêm ảnh/tài liệu")
    link = None if reference["files"] else product_link(reference["text"])
    if link:
        mid = app.store.chat_ask(account, _said(reference, link), "link", {"url": link["url"]}, request_key=key)
        return _start(app, mid, "link")

    # 2. Nếu tìm kiếm sản phẩm mà đã có video trong hệ thống và chưa có cờ allow_duplicate: cảnh báo xác nhận
    allow_duplicate = payload.get("allow_duplicate") in (True, "true", "1")
    if not allow_duplicate and reference["text"]:
        duplicates = app.store.existing_product_videos(reference["text"])
        if duplicates:
            body = {
                "query": reference["text"],
                "existing": duplicates,
                "account": account,
                "account_username": app.store.account(account)["username"],
                "discovery": chosen,
            }
            mid = app.store.chat_ask(account, _said(reference, None), "duplicate_confirm", body, request_key=key)
            app.store.chat_set(mid, "done")
            return {"id": mid}

    body = {"discovery": chosen, "account_username": app.store.account(account)["username"]} if "source" in payload else {}
    mid = app.store.chat_ask(account, _said(reference, None), "product", body, request_key=key)
    return _start(app, mid, "identify", reference=reference)


def find(app, payload):
    """Look for videos of the product an answer recognised, in the chosen account's own browser session."""
    product = app.store.chat_get(_message_id(payload))
    if product["hidden"] or product["kind"] != "product" or product["state"] != "done":
        raise ValueError("Chưa có sản phẩm đã nhận diện để tìm")
    source, human = payload.get("source", "auto"), payload.get("human") in (True, "true", "1")
    if source not in SOURCES or (human and source == "auto"):
        raise ValueError("Chọn một nguồn tìm kiếm")
    account = _account(app, payload, product["account"])
    body = {
        "identity": product["body"]["identity"], "source": source, "human": human, "product": product["id"],
        "account_username": app.store.account(account)["username"], "results": [], "note": "",
        "discovery": product["body"].get("discovery", {}),
        "turn_id": product["body"].get("turn_id", product["id"]),
    }  # fmt: skip
    with SEND_LOCK:
        mid, start, previous = app.store.chat_find(account, body)
        if start:
            try:
                app.tasks.start("search_human" if human else "search", str(mid))
            except Exception:
                app.store.chat_find_refused(mid, previous)
                raise
    return {"id": mid}


def delete_history(app, payload):
    mid = _message_id(payload)
    app.tasks.cancel_for_job(str(mid))
    return app.store.chat_forget(mid)


def dismiss(app, payload):
    return app.store.videos_dismiss(_message_id(payload), payload.get("platform"), payload.get("source_id"))


def pick(app, payload):
    """The owner has watched a candidate and confirms it is the product: take it into the processing queue, pinned to the account."""
    jid = app.store.videos_select(
        _message_id(payload), str(payload.get("source_id", "")), payload.get("confirmed") is True, payload.get("platform")
    )
    app.tasks.start("search_download", jid)
    return {"job": jid}


def confirm(app, payload):
    """The owner says this is their own commission link: keep it, and learn its creator marks for the links that follow."""
    message = app.store.chat_get(_message_id(payload))
    result = message["body"].get("verdict") or {}
    if message["kind"] != "link" or message["state"] != "done" or result.get("verdict") in (None, "different", "invalid"):
        raise ValueError("Link này không thể xác nhận")
    app.store.commission_save(message["account"], message["body"]["found"])
    app.store.chat_set(message["id"], saved=True, confirmed=True)
    return {"id": message["id"]}


def _message_id(payload):
    mid = payload.get("id")
    if not isinstance(mid, int) or isinstance(mid, bool) or not 0 < mid < 10**12:
        raise ValueError("Tin nhắn không hợp lệ")
    return mid


def _sign_in(app, payload, kind):
    channel = payload.get("channel")
    if channel not in CHANNELS:
        raise ValueError("Kênh không hợp lệ")
    account = _account(app, payload)
    body = {
        "channel": channel,
        "account_username": app.store.account(account)["username"],
        "mode": "check" if kind == "channel_check" else "login",
    }
    mid = app.store.chat_add("bot", "login", body, state="running", account=account)
    return _start(app, mid, kind, discard=True)


def login(app, payload):
    """Open a window on this machine for the owner to sign in to a search channel for an account."""
    return _sign_in(app, payload, "channel_login")


def check(app, payload):
    """Check the selected profile; Douyin requires evidence from its own page."""
    return _sign_in(app, payload, "channel_check")


def clear(app, payload):
    """Forget the finished part of the chat history. Saved links, picked videos and sign-ins are not history."""
    return {"removed": app.store.chat_clear()}


def forget(app, payload):
    """Drop one saved commission link."""
    account, product = _account(app, payload), payload.get("product_id")
    if not isinstance(product, str) or not app.store.commission_forget(account, product):
        raise ValueError("Không có link đã lưu này")
    return {"ok": True}


def confirm_duplicate(app, payload):
    """Continue exactly the saved request once; never relax video deduplication."""
    message = app.store.chat_get(_message_id(payload))
    if message["hidden"] or message["kind"] != "duplicate_confirm" or message["state"] != "done":
        raise ValueError("Không có lượt tìm cần xác nhận này")
    account = _account(app, payload, message["account"])
    if account != message["account"] or app.store.account(account)["username"] != message["body"].get("account_username"):
        raise ValueError("Tài khoản đã thay đổi; hãy tìm lại")
    chosen = discovery.options(message["body"].get("discovery", {}))
    return send(
        app,
        dict(
            chosen,
            account=account,
            text=message["body"]["query"],
            allow_duplicate=True,
            request_key="continue_duplicate_%s" % message["id"],
        ),
    )


def dismiss_product(app, payload):
    """Exclude a product from top catalog."""
    account = _account(app, payload)
    item_key = payload.get("item_key") or payload.get("model") or payload.get("name")
    if not item_key:
        raise ValueError("Thiếu thông tin sản phẩm cần bỏ qua")
    app.store.dismiss_product(account, item_key)
    return {"ok": True, "dismissed": item_key}


def undismiss_products(app, payload):
    """Restore all dismissed products."""
    account = _account(app, payload)
    app.store.undismiss_products(account)
    return {"ok": True}


def batch_find(app, payload):
    """Batch process: for each selected product, search Douyin, pick top candidate, download, bind affiliate, and queue for processing."""
    account = _account(app, payload)
    products = payload.get("products") or []
    if not isinstance(products, list) or not products:
        raise ValueError("Hãy chọn ít nhất 1 sản phẩm để tìm kiếm hàng loạt")
    products = products[:10]  # Giới hạn an toàn
    category = payload.get("category", "")
    body = {
        "category": category,
        "products": products,
        "account": account,
        "account_username": app.store.account(account)["username"],
        "status": "queued",
        "current": 0,
        "total": len(products),
        "jobs": [],
        "logs": [],
    }
    mid = app.store.chat_add("bot", "batch_search", body, state="running", account=account)
    try:
        app.tasks.start("batch_sales_search", str(mid))
    except Exception as error:
        app.store.chat_set(mid, "error", error=str(error)[:300] or "Không bắt đầu được")
        raise
    return {"id": mid}


ACTIONS = {
    "find": find,
    "pick": pick,
    "confirm": confirm,
    "login": login,
    "check": check,
    "clear": clear,
    "forget": forget,
    "delete_history": delete_history,
    "dismiss": dismiss,
    "confirm_duplicate": confirm_duplicate,
    "dismiss_product": dismiss_product,
    "undismiss_products": undismiss_products,
    "batch_find": batch_find,
}


def act(app, payload):
    action = ACTIONS.get(payload.get("action"))
    if not action:
        raise ValueError("Thao tác không hợp lệ")
    return action(app, payload)


# route -> (handler, largest body accepted): a message may carry files, an action is a few bytes
ROUTES = {"/chat/send": (send, 12 << 20), "/chat/act": (act, 16 << 10)}
