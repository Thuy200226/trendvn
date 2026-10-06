"""Everything the tabs share about the current moment: counts, what is busy, what needs attention, and the two buttons that appear on several tabs."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

from ..domain.accounts import account_flag
from .components import task_panel  # noqa: F401  (re-exported for the tabs)
from .format import escape as E

BROWSER_TASKS = ("collect", "publish", "dryrun", "stats", "update", "search", "search_download", "shop_sync")
PROCESS_TASKS = ("process", "update")


class View:
    """Read-only facts derived from the dashboard data, computed once per page."""

    def __init__(self, data, csrf, now=None):
        self.d = data
        self.csrf = csrf
        self.now = now or time.time()
        self.cfg = data["settings"]
        self.counts = data["counts"]
        self.ready = data.get("ready", [])  # the best 30 rendered videos (what the Đăng bài tab lists)
        self.ready_total = self.counts.get("ready", 0) + self.counts.get("awaiting_approval", 0)  # how many there really are
        self.tasks = data.get("tasks", [])
        running = [t for t in self.tasks if t["state"] == "running"]
        self.busy_browser = any(t["kind"] in BROWSER_TASKS for t in running)
        self.busy_process = any(t["kind"] in PROCESS_TASKS for t in running)
        self.key_rejected = bool(data.get("gemini_key_rejected"))
        self.challenge_on = bool(data.get("publisher_challenge"))
        who = next((a for a in data.get("accounts", []) if a["id"] == data.get("publisher_challenge_account")), None)
        self.challenge_command = "./trendvn tiktok trust" + account_flag(data.get("publisher_challenge_account"))
        self.challenge_who = " ở @" + who["username"] if who else ""
        self.attention = (
            max(len(data["review"]), self.counts.get("needs_review", 0))
            + len(data["unresolved"])
            + (1 if self.challenge_on else 0)
            + (1 if self.key_rejected else 0)
        )
        self.waiting = self.counts.get("queued", 0) + self.counts.get("processing", 0)
        self.n8n_url = data.get("n8n_url") or "http://localhost:5680"

    def unconfirmed_for(self, account):
        """The posts of this account that may or may not be on TikTok (a post without an account belongs to the first enabled one)."""
        default = next((a for a in self.d.get("accounts", []) if a["enabled"]), None)
        mine = account["id"] if account else None
        return [u for u in self.d.get("unresolved", []) if account is None or (u.get("account") or (default and default["id"])) == mine]

    def takers(self, topic):
        """The enabled accounts that take a video of this topic (a video without a topic goes anywhere)."""
        return [a for a in self.d.get("accounts", []) if a["enabled"] and (topic is None or topic in a["topics"])]

    def destination(self, topic, account_id=None):
        """Where the 'Đăng ngay' button sends a video of this topic. Same rule as the worker: of the accounts that take the topic the one
        with the fewest posts today, and when none does, the default account (the first enabled one)."""
        if account_id:
            return next((a for a in self.d.get("accounts", []) if a["enabled"] and a["id"] == account_id), None)
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
            ("Sẵn sàng", self.ready_total, "publish"),
            ("Đã đăng", self.counts.get("published", 0), "posted"),
        )
        items = "".join('<a class="step" href="#%s"><b>%d</b><small>%s</small></a>' % (tab, n, E(label)) for label, n, tab in steps)
        return '<div class="funnel">%s</div>' % items
