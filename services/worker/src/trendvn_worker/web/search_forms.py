"""Search reference submissions, account-bound video selection and product pairing."""

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
