"""Đã đăng: what was posted and how it performed."""

from ..components import cell, platform_badge, table, task_panel
from ..format import ago, escape as E, num
from ..labels import ROUTE_LABEL


def _performance_table(view):
    rows = []
    for post in view.d["performance"]:
        title = E((post["title"] or "")[:80])
        link = (
            ('<a href="%s" target="_blank" rel="noopener noreferrer">%s</a>' % (E(post["publish_url"]), title))
            if post["publish_url"]
            else title
        )
        rows.append(
            "<tr>%s%s%s%s%s%s</tr>"
            % (
                cell("Nguồn", platform_badge(post["platform"])),
                cell("Bài đăng", link, "t"),
                cell("Kiểu", E(ROUTE_LABEL.get(post["route"], post["route"] or ""))),
                cell("Lượt xem", num(post["views"])),
                cell("Tim", num(post["likes"])),
                cell("Đăng", ago(post["published_at"], view.now)),
            )
        )
    return table(("Nguồn", "Bài đăng", "Kiểu", "Lượt xem", "Tim", "Đăng"), rows, "Chưa có bài nào được đăng.")


def render(view):
    return (
        '<h2>Đã đăng và hiệu quả</h2><div class="card stack"><p class="hint">Đọc lượt xem và tim từ hồ sơ TikTok để cập nhật bảng '
        "và để hệ thống học nguồn nào hiệu quả hơn.</p>%s%s</div>%s"
    ) % (
        view.action("stats", "📊 Đọc lượt xem ngay", "ghost", view.busy_browser, "posted"),
        task_panel(view.tasks, view.now, ("stats",)),
        _performance_table(view),
    )
