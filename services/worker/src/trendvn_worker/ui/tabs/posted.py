"""Posted: what was posted and how it performed."""

from ..components import cell, platform_badge, table, task_panel
from ..format import ago, escape as E, headline, num
from ..labels import ROUTE_LABEL


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
            "<tr>%s%s%s%s%s%s</tr>"
            % (
                cell("Ngu\u1ed3n", platform_badge(post["platform"])),
                cell("B\u00e0i \u0111\u0103ng", link, "t"),
                cell("Ki\u1ec3u", E(ROUTE_LABEL.get(post["route"], post["route"] or ""))),
                cell("L\u01b0\u1ee3t xem", num(post["views"])),
                cell("Tim", num(post["likes"])),
                cell("\u0110\u0103ng", ago(post["published_at"], view.now)),
            )
        )
    return table(
        ("Ngu\u1ed3n", "B\u00e0i \u0111\u0103ng", "Ki\u1ec3u", "L\u01b0\u1ee3t xem", "Tim", "\u0110\u0103ng"),
        rows,
        "Ch\u01b0a c\u00f3 b\u00e0i n\u00e0o \u0111\u01b0\u1ee3c \u0111\u0103ng.",
    )


def render(view):
    return (
        '<h2>\u0110\u00e3 \u0111\u0103ng v\u00e0 hi\u1ec7u qu\u1ea3</h2><div class="card stack"><p class="hint">\u0110\u1ecdc l\u01b0\u1ee3t xem v\u00e0 tim t\u1eeb h\u1ed3 s\u01a1 TikTok \u0111\u1ec3 c\u1eadp nh\u1eadt b\u1ea3ng '
        "v\u00e0 \u0111\u1ec3 h\u1ec7 th\u1ed1ng h\u1ecdc ngu\u1ed3n n\u00e0o hi\u1ec7u qu\u1ea3 h\u01a1n.</p>%s%s</div>%s"
    ) % (
        view.action("stats", "📊 \u0110\u1ecdc l\u01b0\u1ee3t xem ngay", "ghost", view.busy_browser, "posted"),
        task_panel(view.tasks, view.now, ("stats",)),
        _performance_table(view),
    )
