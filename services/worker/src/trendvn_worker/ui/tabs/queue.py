"""Hàng đợi: videos waiting to be processed (in the order they will be), and candidates not yet downloaded."""

from ...domain import topics
from ..components import accordion, cell, platform_badge, state_chip, table, task_panel
from ..format import ago, escape as E, meta_of, num


def _topic_cell(job):
    """The topic Gemini decided on, or the collector's guess (marked with ~) while the video is still unprocessed."""
    if job.get("topic"):
        return E(topics.label(job["topic"]))
    return ("~" + E(topics.label(job["topic_hint"]))) if job.get("topic_hint") else "—"


def _video_table(items, now, empty):
    rows = [
        "<tr>%s%s%s%s%s%s</tr>"
        % (
            cell("Nguồn", platform_badge(j["platform"])),
            cell("Video", E((j["title"] or "")[:90]), "t"),
            cell("Chủ đề", _topic_cell(j)),
            cell("Trạng thái", state_chip(j["state"])),
            cell("Điểm", E(num(meta_of(j).get("score"))) if meta_of(j).get("score") else "—"),
            cell("Tìm thấy", ago(j["first_seen"], now)),
        )
        for j in items
    ]
    return table(("Nguồn", "Video", "Chủ đề", "Trạng thái", "Điểm", "Tìm thấy"), rows, empty)


def processing_card(view):
    """Either how to switch processing on, or the buttons that run it now."""
    waiting = view.waiting
    if not view.d["processing_enabled"]:
        backlog = ("<b>%d video</b> đang nằm chờ. " % waiting) if waiting else "sẽ nằm chờ ở đây. "
        return (
            '<div class="card stack alert-soft"><h3>Xử lý video đang TẮT</h3><p>Video vẫn được thu thập nhưng chưa được dựng, nên %s'
            "Bật lên để Gemini làm Vietsub hoặc lồng tiếng.</p>%s</div>"
        ) % (backlog, view.enable_processing("queue"))
    status = (
        ("Đang có <b>%d video</b> chờ Gemini làm Vietsub/lồng tiếng. Video xong sẽ chuyển sang tab Đăng bài." % waiting)
        if waiting
        else "Không có video nào chờ xử lý. Bấm <b>Thu thập</b> để tìm video mới."
    )
    process_label = "⚙️ Xử lý %d video chờ" % waiting if waiting else "⚙️ Không có video chờ"
    return '<div class="card stack"><h3>Xử lý</h3><p class="hint">%s</p><div class="btngrid">%s%s</div></div>' % (
        status,
        view.action("process", process_label, "go big", view.busy_process or not waiting, "queue"),
        view.action("collect", "🔎 Thu thập video mới", "ghost big", view.busy_browser, "queue"),
    )


def render(view):
    d = view.d
    candidates = accordion(
        "candidates",
        "Ứng viên chưa tải về (%d)" % view.counts.get("candidate", 0),
        '<p class="muted small">Đã tìm thấy và đạt ngưỡng thịnh hành; sẽ được tải về ở lần thu thập kế tiếp.</p>'
        + _video_table(d.get("candidates", []), view.now, "Không có ứng viên nào."),
    )
    return (
        '<h2>Hàng đợi</h2><p class="hint">Đường đi của một video: <b>Ứng viên</b> (đã tìm thấy, chưa tải) → <b>Chờ xử lý</b> (đã tải, chờ Gemini) → '
        "<b>Sẵn sàng</b> (sang tab Đăng bài) → <b>Đã đăng</b>.</p>%s%s%s"
        '<h3 class="sub">Đang chờ xử lý (%d)</h3>%s%s'
    ) % (
        view.funnel(),
        processing_card(view),
        task_panel(view.tasks, view.now, ("process", "update", "collect")),
        view.waiting,
        _video_table(d.get("queue", []), view.now, "Không có video nào chờ xử lý."),
        candidates,
    )
