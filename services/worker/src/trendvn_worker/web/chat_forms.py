"""What the product chat accepts from the page: a message (words, links, photos, documents) and an action on one of the answers.
Both arrive as JSON from the page's script and are checked here; the handler has already checked origin and CSRF."""

import re
import threading

from ..domain import discovery
from ..domain.channels import CHANNELS
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
    if not reference["text"] and not reference["files"]:
        reference["text"] = discovery.fallback_text(chosen)
    if not reference["text"] and not reference["files"]:
        raise ValueError("Hãy nhập mô tả, dán link hoặc thêm ảnh/tài liệu")
    link = None if reference["files"] else product_link(reference["text"])
    if link:
        mid = app.store.chat_ask(account, _said(reference, link), "link", {"url": link["url"]}, request_key=key)
        return _start(app, mid, "link")
    body = {"discovery": chosen, "account_username": app.store.account(account)["username"]} if "source" in payload else {}
    mid = app.store.chat_ask(account, _said(reference, None), "product", body, request_key=key)
    return _start(app, mid, "identify", reference=reference)


def find(app, payload):
    """Look for videos of the product an answer recognised, in the chosen account's own browser session."""
    product = app.store.chat_get(_message_id(payload))
    if product["kind"] != "product" or product["state"] != "done":
        raise ValueError("Chưa có sản phẩm đã nhận diện để tìm")
    source, human = payload.get("source", "auto"), payload.get("human") is True
    if source not in SOURCES or (human and source == "auto"):
        raise ValueError("Chọn một nguồn tìm kiếm")
    account = _account(app, payload, product["account"])
    body = {
        "identity": product["body"]["identity"], "source": source, "human": human, "product": product["id"],
        "account_username": app.store.account(account)["username"], "results": [], "note": "",
        "discovery": product["body"].get("discovery", {}),
        "turn_id": product["body"].get("turn_id", product["id"]),
    }  # fmt: skip
    mid = app.store.chat_add("bot", "videos", body, state="running", account=account)
    return _start(app, mid, "search_human" if human else "search", discard=True)


def delete_history(app, payload):
    return app.store.chat_forget(_message_id(payload))


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
    """Look whether the account's profile is signed in on a channel (reads cookies, opens no page)."""
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
}


def act(app, payload):
    action = ACTIONS.get(payload.get("action"))
    if not action:
        raise ValueError("Thao tác không hợp lệ")
    return action(app, payload)


# route -> (handler, largest body accepted): a message may carry files, an action is a few bytes
ROUTES = {"/chat/send": (send, 12 << 20), "/chat/act": (act, 16 << 10)}
