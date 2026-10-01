"""Assemble the whole page: head, header, one section per tab, bottom navigation, script."""

from string import Template

from ..version import VERSION
from .assets import CSS, JS
from .components import ICONS
from .format import escape as E
from .tabs import attention, home, more, posted, publish, queue
from .view import View

PAGE = Template("""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0e1522" media="(prefers-color-scheme: dark)"><meta name="theme-color" content="#f4f6fb" media="(prefers-color-scheme: light)">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="TrendVN">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%230b7a66'/%3E%3Cpath d='M16 42l12-14 8 8 14-18' stroke='white' stroke-width='6' fill='none' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<title>TrendVN · Bảng điều khiển</title><style>$css</style></head><body>
<header><div class="wrap head"><div class="brand"><h1>TrendVN</h1><p class="muted">TikTok <b>@$target</b> · $clock</p></div>
<nav class="topnav">$top<a href="$n8n" target="_blank" rel="noopener">n8n ↗</a></nav><button class="refresh ghost" onclick="location.reload()" aria-label="Làm mới">↻</button></div></header>
<main class="wrap">$flash
<section data-tab="home" id="home" class="stack">$home</section>
<section data-tab="queue" id="queue" class="stack">$queue</section>
<section data-tab="publish" id="publish" class="stack">$publish</section>
<section data-tab="attention" id="attention" class="stack">$attention</section>
<section data-tab="posted" id="posted" class="stack">$posted</section>
<section data-tab="more" id="more" class="stack">$more</section>
<footer class="muted">TrendVN $version</footer></main>
<nav class="bottomnav" aria-label="Điều hướng">$bottom</nav>
<script>$js</script></body></html>""")


def navigation(view):
    """(top bar, bottom bar) HTML. Blue badges count plain things; red only for what needs the owner."""
    entries = [
        ("home", "Tổng quan", "home", 0),
        ("queue", "Hàng đợi", "list", view.waiting),
        ("publish", "Đăng bài", "send", len(view.ready)),
        ("attention", "Cần xem", "bell", view.attention),
        ("posted", "Đã đăng", "chart", 0),
        ("more", "Thêm", "menu", 0),
    ]

    def badge(tab, count):
        return '<i class="%s">%d</i>' % ("" if tab == "attention" else "n", count)

    bottom = "".join(
        '<a href="#%s" data-go="%s"><span class="ic">%s%s</span><small>%s</small></a>'
        % (tab, tab, ICONS[icon], badge(tab, n) if n else "", E(label))
        for tab, label, icon, n in entries
    )
    top = "".join(
        '<a href="#%s" data-go="%s">%s%s</a>' % (tab, tab, E(label), (" " + badge(tab, n)) if n else "") for tab, label, _, n in entries
    )
    return top, bottom


def render(data, csrf, flash=None, now=None):
    """The dashboard as one HTML document. `data` comes from store.dashboard_data() plus ready/tasks/n8n_url/notify_channels."""
    view = View(data, csrf, now)
    top, bottom = navigation(view)
    flash_html = ""
    if flash:
        flash_html = '<div class="flash %s" role="status">%s</div>' % ("bad" if flash[0] == "err" else "good", E(flash[1]))
    return PAGE.substitute(
        css=CSS,
        js=JS,
        target=E(data["target"]),
        clock=E(view.clock),
        top=top,
        bottom=bottom,
        n8n=E(view.n8n_url),
        flash=flash_html,
        home=home.render(view),
        queue=queue.render(view),
        publish=publish.render(view),
        attention=attention.render(view),
        posted=posted.render(view),
        more=more.render(view),
        version=E(VERSION),
    )
