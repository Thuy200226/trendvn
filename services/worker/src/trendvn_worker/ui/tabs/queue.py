"""Hàng đợi: videos waiting to be processed (in the order they will be), and candidates not yet downloaded."""

from ...domain import topics
from . import search
from ..components import accordion, cell, platform_badge, state_chip, table, task_panel
from ..controls import action_form
from ..format import ago, escape as E, headline, shown_of
from ..messages import user_message


def _topic_cell(job):
    """The topic Gemini decided on, or the collector's guess (marked with ~) while the video is still unprocessed."""
    if job.get("topic"):
        return E(topics.label(job["topic"]))
    return ("~" + E(topics.label(job["topic_hint"]))) if job.get("topic_hint") else "—"


def _actions(view, job):
    jid, state = job["id"], job["state"]
    if state == "candidate" and job.get("search_id"):
        return '<span class="muted">Đang tải video đã chọn</span>'
    if state not in ("candidate", "queued", "search_selected"):
        return '<span class="muted">Đang thực hiện</span>'
    remove = action_form(
        view.csrf,
        "/decide",
        "Bỏ ứng viên" if state != "queued" else "Bỏ chờ",
        {"id": jid, "action": "reject", "next": "queue"},
        css="ghost danger",
        icon_name="trash",
        data_confirm="Bỏ video này khỏi hàng đợi?",
    )
    if state == "search_selected":
        return (
            action_form(
                view.csrf,
                "/task",
                "Thử tải lại",
                {"id": jid, "kind": "search_download", "next": "queue"},
                css="go",
                disabled=view.busy_browser,
            )
            + remove
        )
    kind = "queue_download" if state == "candidate" else "process_one"
    run = action_form(
        view.csrf,
        "/task",
        "Đưa vào chờ xử lý" if state == "candidate" else "Xử lý video này",
        {"id": jid, "kind": kind, "next": "queue"},
        css="go",
        icon_name="plus" if state == "candidate" else "play",
        disabled=view.busy_browser if state == "candidate" else view.busy_process,
    )
    return '<div class="queue-actions">%s%s</div>' % (run, remove)


def _video_table(items, now, empty, view):
    """Keep video identity and its current reason together; metadata never crowds the title."""
    rows = []
    for job in items:
        detail = '<div class="video-meta">%s · %s · %s</div>' % (
            platform_badge(job["platform"]),
            _topic_cell(job),
            ago(job["first_seen"], now),
        )
        if job.get("reason"):
            detail += '<p class="hint">%s</p>' % E(user_message(job["reason"]))
        rows.append(
            "<tr>%s%s%s</tr>"
            % (
                cell("Video", headline(job, 140) + detail, "t"),
                cell("Trạng thái", state_chip(job["state"])),
                cell("Thao tác", _actions(view, job)),
            )
        )
    return '<div class="video-list">%s</div>' % table(("Video", "Trạng thái", "Thao tác"), rows, empty)


def processing_card(view):
    """Either how to switch processing on, or the buttons that run it now."""
    waiting = view.counts.get("queued", 0)
    processing = view.counts.get("processing", 0)
    if not view.d["processing_enabled"]:
        backlog = ("<b>%d video</b> đang nằm chờ. " % waiting) if waiting else "sẽ nằm chờ ở đây. "
        return (
            '<div class="card stack alert-soft"><h3>Xử lý video đang TẮT</h3><p>Video vẫn được thu thập nhưng chưa được dựng, nên %s'
            "Bật lên để Gemini làm Vietsub hoặc lồng tiếng.</p>%s</div>"
        ) % (backlog, view.enable_processing("queue"))
    status = (
        ("Đang có <b>%d video</b> chờ Gemini làm Vietsub/lồng tiếng. Video xong sẽ chuyển sang tab Đăng bài." % waiting)
        if waiting
        else (
            'Không còn video chờ. <a href="#publish">Xem %d bản dựng ở Đăng bài</a>.' % view.ready_total
            if view.ready_total
            else 'Không có video nào chờ xử lý. <a href="#search">Tìm video mới</a>.'
        )
    )
    if processing:
        status = "Đang xử lý <b>%d video</b>. %s" % (processing, status)
    process_label = "⚙️ Xử lý %d video chờ" % waiting if waiting else "⚙️ Không có video chờ"
    return '<div class="card stack"><h3>Xử lý</h3><p class="hint">%s</p><div class="btngrid">%s%s</div></div>' % (
        status,
        view.action("process", process_label, "go big", view.busy_process or not waiting, "queue"),
        view.action("collect", "🔎 Thu thập video mới", "ghost big", view.busy_browser, "queue"),
    )


def activity(view):
    """The changing queue region, independently refreshable without replacing the search draft."""
    d = view.d
    candidates = accordion(
        "candidates",
        "Ứng viên chưa tải về (%s)" % shown_of(len(d.get("candidates", [])), view.counts.get("candidate", 0)),
        '<p class="muted small">Đã tìm thấy và đạt ngưỡng thịnh hành; sẽ được tải về ở lần thu thập kế tiếp.</p>'
        + _video_table(d.get("candidates", []), view.now, "Không có ứng viên nào.", view),
    )
    return ('<div id="queue-live">%s%s%s<h3 class="sub">Đang chờ xử lý (%s)</h3>%s%s</div>') % (
        view.funnel(),
        processing_card(view),
        task_panel(view.tasks, view.now, ("process", "process_one", "queue_download", "update", "collect", "identify", "search")),
        shown_of(len(d.get("queue", [])), view.waiting),
        _video_table(d.get("queue", []), view.now, "Không có video nào chờ xử lý.", view),
        candidates,
    )


def render(view):
    return (
        '<h2>Hàng đợi</h2><p class="hint">Tìm và chọn video → xử lý → xem bản dựng ở Đăng bài.</p>'
        '<nav class="queue-nav" aria-label="Các bước trong hàng đợi">'
        '<a href="#search" data-queue-mode="search">Tìm video</a>'
        '<a href="#queue" data-queue-mode="waiting">Chờ xử lý <span data-waiting-count>%d</span></a></nav>'
        '<div data-queue-pane="search">%s</div><div data-queue-pane="waiting">%s</div>'
    ) % (view.waiting, search.render(view), activity(view))
