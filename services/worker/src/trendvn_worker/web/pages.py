"""Build the data the dashboard needs and render it."""

from .. import notify, ui
from ..ui.labels import STATE_LABELS


def chat_data(store):
    """The product chat as the page shows it: the latest messages, the videos picked from each answer, who the accounts are."""
    messages = store.chat_thread()
    ids = [str(m["id"]) for m in messages if m["kind"] == "videos"]
    picked = {}
    if ids:
        with store.connect() as db:
            for row in db.execute(
                "SELECT id,source_id,platform,state,reason,search_id FROM jobs WHERE search_id IN (%s)" % ",".join("?" * len(ids)), ids
            ):
                picked.setdefault(row["search_id"], []).append(dict(row, state_label=STATE_LABELS.get(row["state"], row["state"])))
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


def dashboard_html(app, flash=None, host=""):
    """The whole dashboard page for the visitor who used `host` in the address bar."""
    store = app.store
    data = store.dashboard_data()
    data["ready"] = store.ready_list()
    data["tasks"] = store.tasks_recent(6)
    data["chat"] = chat_data(store)
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
