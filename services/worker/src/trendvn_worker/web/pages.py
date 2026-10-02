"""Build the data the dashboard needs and render it."""

from .. import notify, ui


def dashboard_html(app, flash=None, host=""):
    """The whole dashboard page for the visitor who used `host` in the address bar."""
    store = app.store
    data = store.dashboard_data()
    data["ready"] = store.ready_list()
    data["tasks"] = store.tasks_recent(6)
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
