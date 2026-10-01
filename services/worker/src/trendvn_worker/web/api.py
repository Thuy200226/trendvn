"""The token-protected JSON API used by n8n and the browser agent. One small function per route."""

import re

from .. import notify
from ..pipeline import process_one

JOB_ID = re.compile(r"[0-9a-f]{32}")
TERMINAL_STATUSES = ("disabled", "blocked", "idle", "rate_limited")
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
    return function(app, payload)


def _job_id(value):
    if value is not None and not JOB_ID.fullmatch(str(value)):
        raise ValueError("Mã video không hợp lệ")
    return value


# ------------------------------------------------------------------ discovery
@route("/api/ingest")
def ingest(app, payload):
    return app.store.ingest(payload)


@route("/api/attach")
def attach(app, payload):
    return app.store.attach(payload["id"], payload["filename"])


@route("/api/media/pending")
def media_pending(app, payload):
    return {"items": app.store.candidates_without_media(int(payload.get("limit", 20)))}


@route("/api/media/failed")
def media_failed(app, payload):
    app.store.mark_media_failed(payload["id"], str(payload.get("reason", "")))
    return OK


@route("/api/heartbeat")
def heartbeat(app, payload):
    app.store.heartbeat(payload["component"], payload["ok"], payload.get("detail"))
    return OK


# ------------------------------------------------------------------ processing
@route("/api/housekeeping")
def housekeeping(app, payload):
    return app.store.housekeeping()


@route("/api/process")
def process(app, payload):
    if not app.process_lock.acquire(blocking=False):
        raise Busy("Worker busy; do not run concurrently")
    try:
        count = max(1, min(int(payload.get("max", 1)), MAX_PROCESS_BATCH))
        results = []
        for _ in range(count):
            result = process_one(app.store)
            results.append(result)
            if result.get("status") in TERMINAL_STATUSES:
                break
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
    return app.store.publish_peek(payload.get("job_id"))


@route("/api/publish/claim")
def publish_claim(app, payload):
    return app.store.publish_claim(job_id=_job_id(payload.get("job_id")))


@route("/api/publish/finish")
def publish_finish(app, payload):
    app.store.publish_finish(payload["id"], payload["lease"], payload["outcome"], payload.get("url", ""), str(payload.get("reason", "")))
    return OK


@route("/api/publish/unresolved")
def publish_unresolved(app, payload):
    return {"items": app.store.unresolved()}


@route("/api/publish/resolve")
def publish_resolve(app, payload):
    app.store.resolve_unknown(payload["id"], payload["outcome"], payload.get("url", ""))
    return OK


@route("/api/publisher/challenge")
def publisher_challenge(app, payload):
    app.store.set_challenge(bool(payload.get("active")))
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
