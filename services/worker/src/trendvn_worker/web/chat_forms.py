"""What the product chat accepts from the page: a message (words, links, photos, documents) and an action on one of the answers.
Both arrive as JSON from the page's script and are checked here; the handler has already checked origin and CSRF."""

from ..domain.product_links import product_link
from ..domain.product_search import validate_input

SOURCES = ("auto", "tiktok", "douyin")
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


def _start(app, mid, kind, key=None, reference=None):
    """Start the job behind an answer; when it cannot start the answer says so instead of staying 'running'."""
    try:
        app.tasks.start(kind, str(key or mid), reference)
    except ValueError as error:
        app.store.chat_set(mid, "error", error=str(error)[:300])
        raise
    return {"id": mid}


def send(app, payload):
    """A message from the owner. A TikTok product link (without files) is checked as a share link against the product in the chat;
    anything else describes a product to recognise."""
    reference = validate_input(payload)
    if not reference["text"] and not reference["files"]:
        raise ValueError("Hãy nhập mô tả, dán link hoặc thêm ảnh/tài liệu")
    account = _account(app, payload)
    link = None if reference["files"] else product_link(reference["text"])
    if link:
        mid = app.store.chat_ask(account, _said(reference, link), "link", {"url": link["url"]})
        return _start(app, mid, "link")
    mid = app.store.chat_ask(account, _said(reference, None), "product", {})
    return _start(app, mid, "identify", reference=reference)


def find(app, payload):
    """Look for videos of the product an answer recognised, in the chosen account's own browser session."""
    product = app.store.chat_get(_message_id(payload))
    if product["kind"] != "product" or product["state"] != "done":
        raise ValueError("Chưa có sản phẩm đã nhận diện để tìm")
    source, human = payload.get("source", "auto"), payload.get("human") is True
    if source not in SOURCES or (human and source == "auto"):
        raise ValueError("Chọn TikTok hoặc Douyin")
    account = _account(app, payload, product["account"])
    body = {
        "identity": product["body"]["identity"], "source": source, "human": human, "product": product["id"],
        "account_username": app.store.account(account)["username"], "results": [], "note": "",
    }  # fmt: skip
    mid = app.store.chat_add("bot", "videos", body, state="running", account=account)
    return _start(app, mid, "search_human" if human else "search")


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


ACTIONS = {"find": find, "pick": pick, "confirm": confirm}


def act(app, payload):
    action = ACTIONS.get(payload.get("action"))
    if not action:
        raise ValueError("Thao tác không hợp lệ")
    return action(app, payload)


# route -> (handler, largest body accepted): a message may carry files, an action is a few bytes
ROUTES = {"/chat/send": (send, 12 << 20), "/chat/act": (act, 16 << 10)}
