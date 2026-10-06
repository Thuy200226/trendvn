"""Reusable HTML pieces: chips, tables that turn into cards on phones, form fields, switches, the task progress panel."""

import re
import time

from ..tasks import LABELS as TASK_LABELS
from .format import ago, escape as E
from .labels import COMPONENT, PLATFORM, STATE_LABELS, STATE_TONE

ICONS = {
    "home": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 11l9-8 9 8v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/></svg>',
    "send": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/></svg>',
    "search": '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M21 21l-5-5"/></svg>',
    "bell": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9a6 6 0 1 1 12 0c0 6 2 7 2 7H4s2-1 2-7zM10 20a2 2 0 0 0 4 0"/></svg>',
    "chart": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>',
    "list": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/></svg>',
    "menu": '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
}
TASK_ICON = {"running": '<span class="spin" aria-label="Đang chạy"></span>', "done": "✓", "error": "✗"}
STALE_TASK_SECONDS = 900  # a finished task older than this is not news on a tab you only just opened
PLAIN_INPUT = 'autocapitalize="none" autocorrect="off" spellcheck="false"'


# ------------------------------------------------------------------ small badges
def chip(text, tone="mute"):
    return '<span class="chip %s">%s</span>' % (tone, E(text))


def state_chip(state):
    return chip(STATE_LABELS.get(state, state), STATE_TONE.get(state, "mute"))


def component_chip(state):
    return chip(*COMPONENT.get(state, (state, "mute")))


def platform_badge(platform):
    name, country = PLATFORM.get(platform, (platform, ""))
    return '<span class="plat">%s <b>%s</b></span>' % (E(name), E(country))


# ------------------------------------------------------------------ tables and containers
def table(headers, rows, empty):
    """Desktop table that turns into a stack of cards on phones (every cell carries data-label)."""
    body = "".join(rows) if rows else '<tr class="none"><td colspan="%d" class="empty">%s</td></tr>' % (len(headers), E(empty))
    head = "".join("<th>%s</th>" % E(h) for h in headers)
    return '<div class="tablewrap"><table><tr class="hd">%s</tr>%s</table></div>' % (head, body)


def cell(label, value, css=""):
    return '<td data-label="%s"%s>%s</td>' % (E(label), (' class="%s"' % css) if css else "", value)


def fieldset(title, body, opened=True):
    return '<details class="fs"%s><summary>%s</summary><div class="fsbody">%s</div></details>' % (" open" if opened else "", E(title), body)


def accordion(anchor, title, body):
    return '<details class="acc card" id="%s"><summary>%s</summary><div class="accbody stack">%s</div></details>' % (anchor, E(title), body)


# ------------------------------------------------------------------ form fields
def field(label, inner, hint=""):
    return "<label>%s%s%s</label>" % (E(label), inner, ("<small>%s</small>" % E(hint)) if hint else "")


def text_input(name, value, extra=""):
    return '<input name="%s" value="%s" %s>' % (name, E(str(value)), extra)


def number_input(name, value, low, high, step="1"):
    mode = "decimal" if step != "1" else "numeric"
    return text_input(name, value, 'type="number" inputmode="%s" min="%s" max="%s" step="%s"' % (mode, low, high, step))


def select(name, current, options):
    items = "".join('<option value="%s"%s>%s</option>' % (v, " selected" if v == current else "", E(label)) for v, label in options)
    return '<select name="%s">%s</select>' % (name, items)


def switch_select(name, on, on_label, off_label):
    return select(name, "true" if on else "false", (("true", on_label), ("false", off_label)))


def quick_switch(csrf, key, label, on, on_text, off_text, next_tab="home", danger=False, confirm=""):
    """One-tap switch on the home screen: POSTs a single setting and returns to the same screen."""
    css = ("on" if on else "off") + (" danger" if danger and on else "")
    confirm_attr = (' data-confirm="%s"' % E(confirm)) if (confirm and not on) else ""
    return (
        '<form method="post" action="/settings" class="qs"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="%s">'
        '<input type="hidden" name="%s" value="%s"><button class="%s" aria-pressed="%s"%s><span>%s</span><b>%s</b></button></form>'
    ) % (
        csrf,
        next_tab,
        key,
        "false" if on else "true",
        css,
        "true" if on else "false",
        confirm_attr,
        E(label),
        E(on_text if on else off_text),
    )


# ------------------------------------------------------------------ background task progress
def task_panel(tasks, now=None, kinds=None):
    """Progress of the latest button-started task. data-running=1 makes the page poll it until it finishes.
    kinds: show it only when the latest task is one of these (so each tab shows only what is relevant to it); None = always."""
    now = now or time.time()
    if kinds is not None and (not tasks or tasks[0]["kind"] not in kinds):
        return ""
    if (
        kinds is not None
        and tasks[0]["state"] != "running"
        and now - (tasks[0].get("finished") or tasks[0]["started"]) > STALE_TASK_SECONDS
    ):
        return ""
    if not tasks:
        return '<div class="taskpanel idle" data-running="0"><p class="muted">Chưa chạy việc nào từ nút bấm. Bấm "Bắt đầu" để cập nhật.</p></div>'
    task = tasks[0]
    running = task["state"] == "running"

    def link(text):  # only our own screenshot file names become links
        return re.sub(
            r"/media/shot/(shot_\d{9,12}\.png)", r'<a href="/media/shot/\1" target="_blank" rel="noopener">mở ảnh chụp</a>', E(text)
        )

    steps = "".join(
        '<li class="%s"><span class="ti">%s</span><div><b>%s</b>%s</div></li>'
        % (E(s["state"]), TASK_ICON.get(s["state"], ""), E(s["name"]), ("<small>%s</small>" % link(s["detail"])) if s.get("detail") else "")
        for s in task["steps"]
    )
    if not steps and task.get("error"):
        steps = '<li class="error"><span class="ti">✗</span><div><b>%s</b></div></li>' % E(task["error"])
    state_chip_ = chip("Đang chạy…", "info") if running else (chip("Xong", "good") if task["state"] == "done" else chip("Có lỗi", "bad"))
    return (
        '<div class="taskpanel %s" data-running="%d"><div class="row"><b>%s</b>%s</div><ul class="steps">%s</ul><small class="muted">Bắt đầu %s%s</small></div>'
        % (
            E(task["state"]),
            1 if running else 0,
            E(TASK_LABELS.get(task["kind"], task["kind"])),
            state_chip_,
            steps,
            ago(task["started"], now),
            " · chạy nền, bạn có thể rời trang" if running else "",
        )
    )
