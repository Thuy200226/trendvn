"""Everything the tabs share about the current moment: counts, what is busy, what needs attention, and the two buttons that appear on several tabs."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from .components import task_panel  # noqa: F401  (re-exported for the tabs)
from .format import escape as E

BROWSER_TASKS = ("collect", "publish", "dryrun", "stats", "update")
PROCESS_TASKS = ("process", "update")


class View:
    """Read-only facts derived from the dashboard data, computed once per page."""

    def __init__(self, data, csrf, now=None):
        self.d = data
        self.csrf = csrf
        self.now = now or time.time()
        self.cfg = data["settings"]
        self.counts = data["counts"]
        self.ready = data.get("ready", [])
        self.tasks = data.get("tasks", [])
        running = [t for t in self.tasks if t["state"] == "running"]
        self.busy_browser = any(t["kind"] in BROWSER_TASKS for t in running)
        self.busy_process = any(t["kind"] in PROCESS_TASKS for t in running)
        self.challenge_on = bool(data.get("publisher_challenge"))
        self.attention = len(data["review"]) + len(data["unresolved"]) + (1 if self.challenge_on else 0)
        self.waiting = self.counts.get("queued", 0) + self.counts.get("processing", 0)
        self.n8n_url = data.get("n8n_url") or "http://localhost:5680"

    def takers(self, topic):
        """The enabled accounts that take a video of this topic (a video without a topic goes anywhere)."""
        return [a for a in self.d.get("accounts", []) if a["enabled"] and (topic is None or topic in a["topics"])]

    def destination(self, topic):
        """Where the 'Đăng ngay' button sends a video of this topic. Same rule as the worker: of the accounts that take the topic the one
        with the fewest posts today, and when none does, the default account (the first enabled one)."""
        takers = self.takers(topic)
        if takers:
            return min(takers, key=lambda a: (a["logged_in"] is False, a["published_today"]))
        enabled = [a for a in self.d.get("accounts", []) if a["enabled"]]
        return enabled[0] if enabled else None

    @property
    def clock(self):
        return datetime.fromtimestamp(self.now, ZoneInfo(self.cfg["timezone"])).strftime("%H:%M %d/%m")

    def action(self, kind, label, css, disabled, next_tab="home"):
        """A button that starts a background task and brings you back to the tab it was pressed on."""
        return (
            '<form method="post" action="/task"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="%s">'
            '<button class="%s" name="kind" value="%s"%s>%s</button></form>'
        ) % (self.csrf, next_tab, css, kind, " disabled" if disabled else "", label)

    def enable_processing(self, next_tab):
        """One tap to switch video processing on (or, without a Gemini key, the way to get one)."""
        if not self.d["gemini_configured"]:
            return (
                '<p class="note warn">Chưa có khóa Gemini nên chưa bật được. <a href="#settings">Dán khóa ở Thêm → Cài đặt</a>, '
                "rồi quay lại bật xử lý video.</p>"
            )
        return (
            '<form method="post" action="/settings"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="%s">'
            '<input type="hidden" name="processing_enabled" value="true"><button class="go big" '
            'data-confirm="Bật xử lý video? Video sẽ được gửi tới Google Gemini để phân tích.">✔ Bật xử lý video</button></form>'
        ) % (self.csrf, next_tab)

    def funnel(self):
        """The four steps a video goes through, each linking to the tab that shows it."""
        steps = (
            ("Ứng viên", self.counts.get("candidate", 0), "queue"),
            ("Chờ xử lý", self.waiting, "queue"),
            ("Sẵn sàng", len(self.ready), "publish"),
            ("Đã đăng", self.counts.get("published", 0), "posted"),
        )
        items = "".join('<a class="step" href="#%s"><b>%d</b><small>%s</small></a>' % (tab, n, E(label)) for label, n, tab in steps)
        return '<div class="funnel">%s</div>' % items
