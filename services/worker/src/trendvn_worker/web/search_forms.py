"""Search reference submissions, account-bound video selection and product pairing."""

import json

from ..domain.product_search import validate_input
from .forms import Redirect


def submit(app, payload):
    account = payload.get("account")
    reference = validate_input(payload)
    source = payload.get("source", "auto")
    if source not in ("auto", "douyin", "tiktok"):
        raise ValueError("Nguồn tìm kiếm không hợp lệ")
    reference["source"] = source
    if not reference["text"] and not reference["files"] and payload.get("mode", "videos") == "videos":
        return {"task": app.tasks.start("collect"), "default": True}
    sid = app.store.search_create(account, reference, payload.get("mode", "videos"))
    try:
        task = app.tasks.start("search", sid)
    except ValueError:
        app.store.search_update(sid, "error", error="Chưa bắt đầu được; đợi việc đang chạy xong rồi tìm lại")
        raise
    return {"id": sid, "task": task}


def select_video(app, form):
    jid = app.store.search_select(
        form["search"][0], form["source_id"][0], form.get("confirmed", [""])[0] == "yes", form.get("platform", [None])[0]
    )
    app.tasks.start("search_download", jid)
    return Redirect("started", anchor="#search")


def pair_product(app, form):
    from ..search.catalog import search_catalog

    sid, jid, pid = form["search"][0], form["job_id"][0], form["product_id"][0]
    search = app.store.search_get(sid)
    if (
        search["state"] != "done"
        or not any(p.get("product_id") == pid for p in search["results"])
        or search["mode"] != "products"
        or form.get("confirmed", [""])[0] != "yes"
    ):
        raise ValueError("Cần xác nhận video thể hiện đúng sản phẩm và biến thể")
    if (app.store.account(search["account"]) or {}).get("username") != search["account_username"]:
        raise ValueError("Tài khoản đã thay đổi; hãy tìm lại sản phẩm")
    product = next(
        (p for p in search_catalog(app.store, search["account"], {"query": "", "product_id": pid}) if p["product_id"] == pid), None
    )
    if not product or not product["eligible"] or not product["can_attach"]:
        raise ValueError("Sản phẩm hoặc quyền gắn giỏ hàng chưa được xác minh")
    with app.store.transaction() as db:
        row = db.execute("SELECT search_account,state,meta FROM jobs WHERE id=?", (jid,)).fetchone()
        if (
            not row
            or row["search_account"] != search["account"]
            or json.loads(row["meta"] or "{}").get("search_username") != search["account_username"]
            or row["state"] not in ("queued", "ready", "awaiting_approval", "needs_review", "search_selected")
        ):
            raise ValueError("Video không thuộc đúng tài khoản hoặc đang được xử lý/đăng")
        db.execute("UPDATE jobs SET product_binding=? WHERE id=?", (json.dumps(dict(product, confirmed=True)), jid))
    return Redirect("product_paired", anchor="#search")


def retry(app, form):
    source = form.get("source", ["tiktok"])[0]
    human = form.get("action", ["retry"])[0] == "open"
    if human and source == "auto":
        raise ValueError("Chọn TikTok hoặc Douyin để mở cửa sổ xác minh")
    sid = app.store.search_retry(form["search"][0], form.get("name", [""])[0].strip(), source)
    try:
        app.tasks.start("search_human" if human else "search", sid)
    except ValueError:
        app.store.search_update(sid, "error", error="Trình duyệt đang bận; hãy thử lại khi việc đang chạy hoàn tất")
        raise
    return Redirect("started", anchor="#search")


def account_login(app, form):
    account = form.get("account", form.get("id", [""]))[0]
    if not app.store.account(account):
        raise ValueError("Không có tài khoản này")
    app.tasks.start("account_login", account)
    return Redirect("started", anchor="#search")
