"""Reusable HTML pieces: chips, tables that turn into cards on phones, form fields, switches, the task progress panel."""

import re
import shlex
import time

from ..tasks import LABELS as TASK_LABELS
from .format import ago, escape as E
from .messages import user_message
from .labels import COMPONENT, PLATFORM, STATE_LABELS, STATE_TONE

from .icons import ICONS  # noqa: F401 (compatibility export)
from .controls import button, hidden, textarea, select_control, input_control, button_content  # noqa: F401

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
    attrs = {}
    for part in shlex.split(extra):
        key, separator, val = part.partition("=")
        attrs[key.replace("-", "_")] = val if separator else True
    return input_control(name, str(value), **attrs)


def number_input(name, value, low, high, step="1"):
    mode = "decimal" if step != "1" else "numeric"
    return text_input(name, value, 'type="number" inputmode="%s" min="%s" max="%s" step="%s"' % (mode, low, high, step))


def select(name, current, options):
    return select_control(name, current, options)


def switch_select(name, on, on_label, off_label):
    return select(name, "true" if on else "false", (("true", on_label), ("false", off_label)))


def quick_switch(csrf, key, label, on, on_text, off_text, next_tab="home", danger=False, confirm=""):
    """One-tap switch on the home screen: POSTs a single setting and returns to the same screen."""
    css = ("on" if on else "off") + (" danger" if danger and on else "")
    content = "<span>%s</span><b>%s</b>" % (E(label), E(on_text if on else off_text))
    controls = hidden("csrf", csrf) + hidden("next", next_tab) + hidden(key, "false" if on else "true")
    return '<form method="post" action="/settings" class="qs">%s%s</form>' % (
        controls,
        button_content(content, css, aria_pressed="true" if on else "false", data_confirm=confirm if confirm and not on else None),
    )


# ------------------------------------------------------------------ background task progress
def task_panel(tasks, now=None, kinds=None):
    """Progress of the most relevant active task, otherwise its recent result. data-running=1 makes the page poll it until it finishes.
    kinds: show it only when the latest task is one of these (so each tab shows only what is relevant to it); None = all kinds."""
    now = now or time.time()
    relevant = [t for t in tasks if kinds is None or t["kind"] in kinds]
    task = next((t for t in relevant if t["state"] == "running"), relevant[0] if relevant else None)
    if not task:
        return (
            ""
            if kinds is not None
            else '<div class="taskpanel idle" data-running="0"><p class="muted">Không có tác vụ đang chạy.</p></div>'
        )
    if kinds is not None and task["state"] != "running" and now - (task.get("finished") or task["started"]) > STALE_TASK_SECONDS:
        return ""
    running = task["state"] == "running"

    def link(text):  # only our own screenshot file names become links
        return re.sub(
            r"/media/shot/(shot_\d{9,12}\.png)", r'<a href="/media/shot/\1" target="_blank" rel="noopener">mở ảnh chụp</a>', E(text)
        )

    steps = "".join(
        '<li class="%s"><span class="ti">%s</span><div><b>%s</b>%s</div></li>'
        % (
            E(s["state"]),
            TASK_ICON.get(s["state"], ""),
            E(user_message(s["name"])),
            ("<small>%s</small>" % link(user_message(s["detail"], s["state"] == "error"))) if s.get("detail") else "",
        )
        for s in task["steps"]
    )
    if not steps and task.get("error"):
        steps = '<li class="error"><span class="ti">✗</span><div><b>%s</b></div></li>' % E(user_message(task["error"], True))
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
