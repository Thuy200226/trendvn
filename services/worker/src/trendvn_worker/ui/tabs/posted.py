"""Đã đăng: what was posted and how it performed."""

from ..components import cell, platform_badge, table, task_panel
from ..controls import action_form
from ..format import ago, escape as E, headline, num
from ..labels import ROUTE_LABEL
from ..messages import user_message


def _delete_action(view, post):
    state = post.get("delete_state")
    if state in ("deleted", "pending", "deleting", "unknown", "failed"):
        label = {
            "deleted": "Đã xóa trên TikTok",
            "pending": "Chờ xóa",
            "deleting": "Đang xóa",
            "unknown": "Cần kiểm tra trên TikTok",
            "failed": "Chưa xóa được",
        }[state]
        detail = "<p>%s</p><small>%s</small>" % (E(label), E(user_message(post.get("delete_reason") or "", state in ("unknown", "failed"))))
        if state in ("unknown", "failed"):
            detail += action_form(
                view.csrf,
                "/post-delete-checked",
                "Đã kiểm tra: bài đã xóa",
                {
                    "id": post["id"],
                    "url": post.get("publish_url") or "",
                    "account": post.get("account") or "main",
                    "confirmed": "true",
                    "outcome": "deleted",
                },
                css="ghost",
                data_confirm="Bạn đã kiểm tra đúng bài trong tài khoản sở hữu và xác nhận nó đã xóa? Chỉ cập nhật trạng thái, không gửi lệnh xóa.\n%s"
                % (post.get("publish_url") or ""),
            )
            detail += action_form(
                view.csrf,
                "/post-delete",
                "Thử xóa lại",
                {"id": post["id"], "url": post.get("publish_url") or "", "account": post.get("account") or "main", "confirmed": "true"},
                css="ghost danger",
                disabled=view.busy_browser,
                data_confirm="Thử gửi lại lệnh xóa bài trên TikTok?\n%s" % (post.get("publish_url") or ""),
            )
            detail += action_form(
                view.csrf,
                "/post-delete-checked",
                "Đã kiểm tra: bài vẫn còn",
                {"id": post["id"], "url": post.get("publish_url") or "", "account": post.get("account") or "main", "confirmed": "true", "outcome": "present"},
                css="ghost",
                data_confirm="Bạn đã mở đúng bài và kiểm tra nó vẫn còn trên TikTok? Chỉ xác nhận sau khi kiểm tra.\n%s"
                % (post.get("publish_url") or ""),
            )
        return detail
    who = post.get("target") or "?"
    fields = {"id": post["id"], "url": post.get("publish_url") or "", "account": post.get("account") or "main", "confirmed": "true"}
    return action_form(
        view.csrf,
        "/post-delete",
        "Xóa bài TikTok",
        fields,
        css="ghost danger",
        icon_name="trash",
        disabled=view.busy_browser or not post.get("publish_url"),
        data_confirm="Xóa bài ‘%s’ trên TikTok @%s?\n%s" % (post.get("title", ""), who, post.get("publish_url") or ""),
    )


def _performance_table(view):
    rows = []
    for post in view.d["performance"]:
        title = headline(post, 80)
        link = (
            ('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (E(post["publish_url"]), title))
            if post["publish_url"]
            else title
        )
        rows.append(
            "<tr>%s%s%s%s%s%s%s</tr>"
            % (
                cell("Nguồn", platform_badge(post["platform"])),
                cell("Bài đăng", link, "t"),
                cell("Kiểu", E(ROUTE_LABEL.get(post["route"], post["route"] or ""))),
                cell("Lượt xem", num(post["views"])),
                cell("Tim", num(post["likes"])),
                cell("Đăng", ago(post["published_at"], view.now)),
                cell("Thao tác", _delete_action(view, post)),
            )
        )
    return table(("Nguồn", "Bài đăng", "Kiểu", "Lượt xem", "Tim", "Đăng", "Thao tác"), rows, "Chưa có bài nào được đăng.")


def render(view):
    return (
        '<h2>Đã đăng và hiệu quả</h2><div class="card stack"><p class="hint">Đọc lượt xem và tim từ hồ sơ TikTok để cập nhật bảng '
        "và để hệ thống học nguồn nào hiệu quả hơn.</p>%s%s</div>%s"
    ) % (
        view.action("stats", "📊 Đọc lượt xem ngay", "ghost", view.busy_browser, "posted"),
        task_panel(view.tasks, view.now, ("stats", "delete_post")),
        _performance_table(view),
    )
