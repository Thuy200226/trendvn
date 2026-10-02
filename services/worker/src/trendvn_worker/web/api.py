"""The token-protected JSON API used by n8n and the browser agent. One small function per route."""

import re

from .. import notify
from ..domain.platforms import PLATFORMS
from ..pipeline import process_many

JOB_ID = re.compile(r"[0-9a-f]{32}")
PROCESSED_STATUSES = ("ready", "awaiting_approval", "needs_review")
MAX_PROCESS_BATCH = 8
OK = {"ok": True}

ROUTES = {}


class NotFound(Exception):
    pass


class Busy(Exception):
    """Another processing run holds the lock."""


def route(path):
    def register(function):
        ROUTES[path] = function
        return function

    return register


def handle(app, path, payload):
    """Run one API call and return its JSON-able result. Raises NotFound or Busy; ValueError becomes a 400 in the handler."""
    function = ROUTES.get(path)
    if function is None:
        raise NotFound(path)
    if not isinstance(payload, dict):
        raise ValueError("Cần một đối tượng JSON")
    return function(app, payload)


def _job_id(value):
    if value is not None and not (isinstance(value, str) and JOB_ID.fullmatch(value)):
        raise ValueError("Mã video không hợp lệ")
    return value


def _text(payload, key, default=None):
    """payload[key] as a string; a list, number or object in its place is a client error (400), not a crash."""
    value = payload.get(key, default)
    if not isinstance(value, str):
        raise ValueError("%s phải là chuỗi" % key)
    return value


# ------------------------------------------------------------------ discovery
@route("/api/ingest")
def ingest(app, payload):
    return app.store.ingest(payload)


@route("/api/attach")
def attach(app, payload):
    return app.store.attach(_text(payload, "id"), _text(payload, "filename"))


@route("/api/media/pending")
def media_pending(app, payload):
    platform = payload.get("platform")
    if platform is not None and platform not in PLATFORMS:
        raise ValueError("Nền tảng không hợp lệ")
    return {"items": app.store.candidates_without_media(int(payload.get("limit", 20)), platform)}


@route("/api/media/failed")
def media_failed(app, payload):
    app.store.mark_media_failed(_text(payload, "id"), str(payload.get("reason", "")))
    return OK


@route("/api/heartbeat")
def heartbeat(app, payload):
    app.store.heartbeat(payload["component"], payload["ok"], payload.get("detail"))
    return OK


# ------------------------------------------------------------------ processing
@route("/api/housekeeping")
def housekeeping(app, payload):
    result = app.store.housekeeping()
    if any(result["pruned"].get(key) for key in ("expired", "files_removed", "rows_trimmed", "orphans")):
        app.log("housekeeping: " + ", ".join("%s=%s" % item for item in result["pruned"].items() if item[1]))
    return result


@route("/api/process")
def process(app, payload):
    if not app.process_lock.acquire(blocking=False):
        raise Busy("Worker busy; do not run concurrently")
    try:
        count = max(1, min(int(payload.get("max", 1)), MAX_PROCESS_BATCH))
        results = process_many(app.store, count)
    finally:
        app.process_lock.release()
    app.log("process: " + ", ".join("%s" % r.get("status") for r in results))
    if count == 1:
        return results[0]
    return {"results": results, "processed": sum(1 for r in results if r.get("status") in PROCESSED_STATUSES)}


@route("/api/tasks/start")
def start_task(app, payload):
    return {"id": app.tasks.start(payload.get("kind", ""), payload.get("job_id"))}


# ------------------------------------------------------------------ publishing
@route("/api/publish/peek")
def publish_peek(app, payload):
    return app.store.publish_peek(_job_id(payload.get("job_id")))


@route("/api/publish/claim")
def publish_claim(app, payload):
    return app.store.publish_claim(job_id=_job_id(payload.get("job_id")))


@route("/api/publish/finish")
def publish_finish(app, payload):
    app.store.publish_finish(
        _text(payload, "id"), _text(payload, "lease"), _text(payload, "outcome"), _text(payload, "url", ""), str(payload.get("reason", ""))
    )
    return OK


@route("/api/publish/unresolved")
def publish_unresolved(app, payload):
    return {"items": app.store.unresolved()}


@route("/api/publish/resolve")
def publish_resolve(app, payload):
    app.store.resolve_unknown(_text(payload, "id"), _text(payload, "outcome"), _text(payload, "url", ""))
    return OK


@route("/api/publisher/challenge")
def publisher_challenge(app, payload):
    app.store.set_challenge(bool(payload.get("active")))
    return OK


# ------------------------------------------------------------------ accounts
@route("/api/accounts")
def accounts(app, payload):
    return {"accounts": app.store.status()["accounts"], "wanted_topics": app.store.wanted_topics()}


@route("/api/accounts/add")
def add_account(app, payload):
    return app.store.add_account(payload)


@route("/api/accounts/update")
def update_account(app, payload):
    return app.store.update_account(str(payload.get("id", "")), {k: v for k, v in payload.items() if k != "id"})


@route("/api/accounts/login")
def account_login(app, payload):
    if not isinstance(payload.get("ok"), bool):
        raise ValueError("ok phải là true hoặc false")
    app.store.set_account_login(str(payload.get("id", "")), payload["ok"])
    return OK


@route("/api/accounts/delete")
def delete_account(app, payload):
    app.store.delete_account(str(payload.get("id", "")))
    return OK


# ------------------------------------------------------------------ feedback, settings, notifications
@route("/api/stats")
def stats(app, payload):
    return app.store.record_stats(payload["items"])


@route("/api/settings")
def settings(app, payload):
    return {"changed": sorted(app.store.update_settings(payload))}


@route("/api/notify")
def send_notification(app, payload):
    kind = payload.get("kind", "summary")
    text = app.store.summary_text() if kind == "summary" else str(payload.get("text", ""))[:1500]
    config = notify.load_config(app.store.root)
    channels = notify.channels(config)
    return {"channels": channels, "sent": notify.send(config, text) if channels else {}}
