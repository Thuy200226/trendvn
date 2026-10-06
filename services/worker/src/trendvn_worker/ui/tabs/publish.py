"""Đăng bài: every processed video with its caption editor and the Post button; and, when empty, why and what to do."""

from ..cards import ready_card
from ..components import task_panel
from ..format import escape as E
from ..format import meta_of
from ..labels import VISIBILITY_LABEL


def blocked_reason(view, job=None):
    """Why posting this video cannot start right now (shown on its card), or ''. The verification pause holds every account; an unconfirmed
    post holds only its own account, the one this video would go to."""
    if job and job.get("search_account") and not view.destination(None, job["search_account"]):
        return "Tài khoản đã chọn đang tắt hoặc đã bị xóa; không thể đăng."
    if job and job.get("search_account"):
        account = view.destination(None, job["search_account"])
        if account and meta_of(job).get("search_username") != account["username"]:
            return "Tài khoản thực đã thay đổi từ lúc tìm; cần tìm lại để chọn đúng tài khoản."
    if view.challenge_on:
        return "TikTok đang đòi xác minh%s: giải một lần bằng %s (xem mục Cần xem)." % (view.challenge_who, view.challenge_command)
    if view.d["unresolved_publishes"]:
        destination = view.destination((job or {}).get("topic"), (job or {}).get("search_account"))
        if view.unconfirmed_for(destination):
            who = " của @%s" % destination["username"] if destination else ""
            return "Có bài đăng%s chưa xác nhận: xử lý ở mục Cần xem trước." % who
    return ""


def _today(view):
    """Posts made today: one total, or one figure per account when there are several."""
    d = view.d
    enabled = [a for a in d["accounts"] if a["enabled"]]
    if len(enabled) < 2:
        return "%d / %d" % (d["published_today"], d["daily_limit"])
    return " · ".join("@%s %d/%d" % (a["username"], a["published_today"], a["daily_limit"]) for a in enabled)


def _strip(view):
    d, cfg = view.d, view.cfg
    window = "đang mở" if d["in_window"] else E("mở lúc " + (d["next_window"] or "—"))
    return (
        '<div class="card strip"><div><small>Hôm nay</small><b>%s</b></div><div><small>Hiển thị</small><b>%s</b></div>'
        "<div><small>Giờ vàng</small><b>%s</b></div></div>"
    ) % (E(_today(view)), E(VISIBILITY_LABEL.get(cfg["visibility"], cfg["visibility"])), window)


def _empty_guide(view):
    """Nothing is ready: say which of the three situations this is, with the one button that moves it forward."""
    waiting, candidates = view.waiting, view.counts.get("candidate", 0)
    if waiting and not view.d["processing_enabled"]:
        why = (
            '<p><b>%d video đang chờ xử lý</b> nhưng công tắc "Xử lý video" đang <b>TẮT</b>, nên chưa video nào được dựng.</p>'
            '<p class="hint">Bật lên để Gemini làm Vietsub hoặc lồng tiếng. Video xong sẽ hiện ở đây để bạn đăng.</p>%s'
        ) % (waiting, view.enable_processing("publish"))
    elif waiting:
        why = ("<p><b>%d video đang chờ xử lý</b> (mỗi video khoảng 1–3 phút). Xử lý xong sẽ hiện ở đây.</p>%s") % (
            waiting,
            view.action("process", "⚙️ Xử lý ngay (%d)" % waiting, "go big", view.busy_process, "publish"),
        )
    else:
        extra = (" (có %d ứng viên chưa tải về)" % candidates) if candidates else ""
        why = (
            '<p>Chưa có video nào để xử lý%s.</p><p class="hint">Bấm cập nhật để thu thập video mới và xử lý; video xong sẽ hiện ở đây.</p>%s'
        ) % (extra, view.action("update", "▶ Cập nhật &amp; chuẩn bị đăng", "go big", view.busy_browser or view.busy_process, "publish"))
    hints = []
    if view.attention:
        hints.append('%d video đang ở tab <a href="#attention">Cần xem</a> (hệ thống giữ lại để bạn duyệt).' % view.attention)
    hints.append('<a href="#queue">Xem hàng đợi →</a>')
    return '<div class="card stack empty-guide"><h3>Chưa có video nào xử lý xong</h3>%s<p class="small muted">%s</p></div>' % (
        why,
        " ".join(hints),
    )


def render(view):
    body = "".join(ready_card(job, view, blocked_reason(view, job)) for job in view.ready) if view.ready else _empty_guide(view)
    return (
        '<h2>Đăng bài</h2><p class="hint">Đây là các video đã xử lý xong. Xem thử, sửa mô tả và hashtag nếu muốn, rồi bấm <b>Đăng ngay</b> để đăng đúng video đó. '
        'Lịch tự động vẫn tự chọn bài điểm cao nhất để đăng trong giờ vàng.</p>%s%s<div class="stack">%s</div>'
    ) % (task_panel(view.tasks, view.now, ("publish", "dryrun", "update")), _strip(view), body)
