"""Build the data the dashboard needs and render it."""

from .. import notify, ui
from ..ui.labels import STATE_LABELS


def chat_data(store):
    """The product chat as the page shows it: the latest messages, the videos picked from each answer, who the accounts are."""
    messages = store.chat_thread()
    ids = [str(m["id"]) for m in messages if m["kind"] == "videos"]
    picked = {}
    if ids:
        downloading = {t["job_id"] for t in store.tasks_running() if t["kind"] == "search_download"}
        with store.connect() as db:
            for row in db.execute(
                "SELECT id,source_id,platform,state,reason,search_id FROM jobs WHERE search_id IN (%s)" % ",".join("?" * len(ids)), ids
            ):
                picked.setdefault(row["search_id"], []).append(
                    dict(row, state_label=STATE_LABELS.get(row["state"], row["state"]), downloading=row["id"] in downloading)
                )
    roster = [{"id": a["id"], "username": a["username"]} for a in store.accounts(enabled_only=True)]
    return {
        "roster": roster,
        "channels": store.channel_states(),
        "saved": {a["id"]: store.commission_list(a["id"]) for a in roster},
        "messages": messages,
        "picked": picked,
        "accounts": {a["id"]: a["username"] for a in store.accounts()},
        "product": (store.chat_product() or {}).get("body", {}).get("identity"),
    }


def chat_html(app):
    """Just the thread (what the page polls while an answer is being worked on)."""
    return ui.chat_fragment(chat_data(app.store))


def queue_html(app):
    """Refresh only the changing queue; the owner's draft and other settings remain in place."""
    from ..ui.tabs.queue import activity
    from ..ui.view import View

    data = app.store.dashboard_data()
    data["tasks"] = app.store.tasks_for_ui()
    return activity(View(data, app.csrf))


def dashboard_html(app, flash=None, host=""):
    """The whole dashboard page for the visitor who used `host` in the address bar."""
    store = app.store
    data = store.dashboard_data()
    data["ready"] = store.ready_list()
    data["tasks"] = store.tasks_for_ui()
    data["chat"] = chat_data(store)
    data["task_journal"] = store.tasks_recent(12)
    data["search_verifications"] = search_verifications(store)
    data["discovery_at"] = (store.settings().get("hb_discovery") or {}).get("at")
    # n8n lives on the same machine as this page: reuse the host the visitor used, swapping in n8n's port
    visitor_host = (host.rsplit(":", 1)[0] if host else "localhost") or "localhost"
    data["n8n_url"] = "http://%s:%s" % (visitor_host, app.config.n8n_port)
    data["notify_channels"] = notify.channels(notify.load_config(store.root))
    data["voice_sample"] = (store.root / "exports" / "voice_sample.wav").exists()
    data["remote"] = host not in app.config.loopback_hosts  # seen through the password gate: offer "Đăng xuất"
    for job in data["review"]:
        job["has_source"] = True
    return ui.render(data, app.csrf, flash)


def search_verifications(store):
    """Only the latest unresolved channel report is actionable, never an old chat failure."""
    enabled = {a["id"]: a["username"] for a in store.accounts(enabled_only=True)}
    return [
        dict(info, account=aid, username=enabled[aid], channel=channel)
        for aid, channels in store.channel_states().items()
        if aid in enabled
        for channel, info in channels.items()
        if info["state"] == "wall"
    ]


def live_data(app, tab):
    """Refresh one screen plus authoritative badges; the search composer and settings stay in place."""
    from ..ui.page import TABS
    from ..ui.tabs.queue import activity
    from ..ui.view import View

    if tab not in {entry[0] for entry in TABS}:
        raise ValueError("Tab không hợp lệ")
    store = app.store
    data = store.dashboard_data()
    data.update(tasks=store.tasks_for_ui(), search_verifications=search_verifications(store))
    if tab == "publish":
        data["ready"] = store.ready_list()
    view = View(data, app.csrf)
    renderer = next(entry[3] for entry in TABS if entry[0] == tab)
    html = activity(view) if tab == "queue" else (None if tab == "more" else renderer(view))
    return {
        "tab": tab,
        "html": html,
        "badges": {entry[0]: entry[4](view) for entry in TABS},
        "running": bool(store.tasks_running() or view.counts.get("processing") or view.counts.get("publishing")),
        "clock": view.clock,
    }
