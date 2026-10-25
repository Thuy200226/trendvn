"""Background tasks behind the dashboard buttons (update everything, collect, process, post one video, rehearse, read stats).

They run the same code paths as the n8n schedule and take the same locks (one browser job at a time in the agent, one processing run
at a time in the worker), so pressing a button can never collide with a scheduled run: if something is already running you are told
so and nothing starts. Progress is stored in the database, so the page can poll it and a restart never leaves a task "running" forever.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from .domain.platforms import NAMES
from .pipeline import process_many

PROCESS_BATCH = 4  # videos processed per press of the button
BROWSER_KINDS = {"collect", "publish", "dryrun", "stats"}
LABELS = {
    "update": "C\u1eadp nh\u1eadt t\u1ed5ng h\u1ee3p",
    "collect": "Thu th\u1eadp video m\u1edbi",
    "process": "X\u1eed l\u00fd video \u0111ang ch\u1edd",
    "publish": "\u0110\u0103ng video",
    "dryrun": "Xem th\u1eed (kh\u00f4ng \u0111\u0103ng)",
    "stats": "\u0110\u1ecdc l\u01b0\u1ee3t xem",
}
PLATFORM_NAMES = NAMES
PROCESS_LABELS = {
    "ready": "s\u1eb5n s\u00e0ng \u0111\u0103ng",
    "awaiting_approval": "ch\u1edd b\u1ea1n duy\u1ec7t",
    "needs_review": "c\u1ea7n duy\u1ec7t",
    "rate_limited": "ch\u1edd Gemini h\u1ebft qu\u00e1 t\u1ea3i",
    "error": "l\u1ed7i",
    "blocked": "b\u1ecb ch\u1eb7n",
}


class AgentError(Exception):
    """Something between the worker and the browser agent failed; the message is written for the owner, not for a log."""


class TaskBusy(ValueError):
    pass


def agent_url():
    base = os.environ.get("TRENDVN_AGENT_URL")
    return base or "http://trendvn-agent:%s" % os.environ.get("TRENDVN_AGENT_PORT", "5682")


def call_agent(path, payload, token, timeout=1500):
    req = urllib.request.Request(
        agent_url() + path,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            raise AgentError(
                "Tr\u00ecnh duy\u1ec7t agent \u0111ang b\u1eadn vi\u1ec7c kh\u00e1c (c\u00f3 th\u1ec3 l\u1ecbch t\u1ef1 \u0111\u1ed9ng \u0111ang ch\u1ea1y). Th\u1eed l\u1ea1i sau v\u00e0i ph\u00fat."
            ) from None
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except Exception:
            pass
        raise AgentError("Agent b\u00e1o l\u1ed7i %d%s" % (e.code, ": " + detail[:200] if detail else "")) from None
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        raise AgentError(
            "Kh\u00f4ng g\u1ecdi \u0111\u01b0\u1ee3c agent tr\u00ecnh duy\u1ec7t. Ki\u1ec3m tra d\u1ecbch v\u1ee5 trendvn-agent \u0111ang ch\u1ea1y (./trendvn doctor)."
        ) from None


def summarize_collect(report):
    """One readable line per source from the agent's collect report."""
    lines = []
    for p, r in (report or {}).items():
        name = PLATFORM_NAMES.get(p, p)
        if r.get("status") == "skipped":
            lines.append("%s: b\u1ecf qua (%s)" % (name, r.get("reason", "").split(". ")[0].rstrip(".")[:90]))
        elif r.get("status") != "ok":
            lines.append("%s: l\u1ed7i, %s" % (name, (r.get("reason") or "")[:80]))
        else:
            streams = [v for k, v in (r.get("summary") or {}).items() if isinstance(v, dict) and k != "media"]
            seen = sum(s.get("seen", 0) for s in streams)
            good = sum(s.get("qualified", 0) for s in streams)
            new = sum(s.get("new", 0) for s in streams if not s.get("baseline"))
            media = (r.get("summary") or {}).get("media") or {}
            base = any(s.get("baseline") for s in streams)
            lines.append(
                "%s: \u0111\u1ecdc %d, \u0111\u1ea1t ng\u01b0\u1ee1ng %d, %s, t\u1ea3i %d"
                % (
                    name,
                    seen,
                    good,
                    "l\u1ea7n \u0111\u1ea7u: ch\u1ec9 ghi m\u1ed1c" if base else "m\u1edbi %d" % new,
                    media.get("downloaded", 0),
                )
            )
    return "\n".join(lines) or "Kh\u00f4ng c\u00f3 ngu\u1ed3n n\u00e0o ch\u1ea1y."


def summarize_process(results):
    """One sentence for the dashboard. Results arrive in the order the runs finished, so look at all of them, not the first."""
    if not results:
        return "Kh\u00f4ng c\u00f3 video n\u00e0o \u0111\u1ec3 x\u1eed l\u00fd."
    statuses = [r.get("status") for r in results]
    if "disabled" in statuses:
        return 'X\u1eed l\u00fd video \u0111ang T\u1eaeT. B\u1eadt c\u00f4ng t\u1eafc "X\u1eed l\u00fd video" r\u1ed3i b\u1ea5m l\u1ea1i.'
    blocked = next((r for r in results if r.get("status") == "blocked"), None)
    if blocked and all(s in ("blocked", "idle") for s in statuses):
        return blocked.get("reason", "Ch\u01b0a x\u1eed l\u00fd \u0111\u01b0\u1ee3c.")
    if all(s == "idle" for s in statuses):
        return "Kh\u00f4ng c\u00f3 video n\u00e0o \u0111ang ch\u1edd x\u1eed l\u00fd."
    counts = {}
    for r in results:
        counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
    return (
        "\u0110\u00e3 x\u1eed l\u00fd: "
        + ", ".join("%d %s" % (n, PROCESS_LABELS.get(k, k)) for k, n in counts.items() if k not in ("idle",))
        + "."
    )


def summarize_publish(res):
    s = res.get("status")
    if s == "published":
        return "\u0110\u00e3 \u0111\u0103ng v\u00e0 x\u00e1c nh\u1eadn tr\u00ean h\u1ed3 s\u01a1." + (
            (" " + res["url"]) if res.get("url") else ""
        )
    if s == "dry_run":
        shot = str(res.get("screenshot") or "")
        link = " Xem \u1ea3nh ch\u1ee5p: /media/shot/" + shot if re.fullmatch(r"shot_\d{9,12}\.png", shot) else ""
        return (
            "Ch\u1ea1y th\u1eed xong: \u0111\u00e3 t\u1ea3i video, \u0111i\u1ec1n m\u00f4 t\u1ea3 v\u00e0 d\u1eebng tr\u01b0\u1edbc n\u00fat \u0110\u0103ng."
            + link
        )
    if s == "challenge":  # the agent's reason names the account's own command (`... trust --account pets`)
        return (
            res.get("reason")
            or "TikTok \u0111\u00f2i x\u00e1c minh. \u0110\u0103ng t\u1ea1m d\u1eebng; gi\u1ea3i m\u1ed9t l\u1ea7n b\u1eb1ng `./trendvn tiktok trust`."
        )
    if s == "unknown":
        return "\u0110\u00e3 b\u1ea5m \u0110\u0103ng nh\u01b0ng ch\u01b0a x\u00e1c nh\u1eadn \u0111\u01b0\u1ee3c. H\u1ec7 th\u1ed1ng d\u1eebng \u0111\u0103ng; xem m\u1ee5c C\u1ea7n xem."
    return res.get("reason") or "Ch\u01b0a \u0111\u0103ng \u0111\u01b0\u1ee3c (%s)." % s


class Tasks:
    def __init__(self, store, token, process_fn, process_lock):
        self.store, self.token, self.process_fn, self.process_lock = store, token, process_fn, process_lock
        self.guard = threading.Lock()
        store.tasks_reap()

    def start(self, kind, job_id=None):
        if kind not in LABELS:
            raise ValueError("Vi\u1ec7c kh\u00f4ng h\u1ee3p l\u1ec7")
        if kind in ("publish", "dryrun") and not job_id:
            raise ValueError("C\u1ea7n ch\u1ecdn m\u1ed9t video")
        with self.guard:  # check-and-create is atomic, so a double click starts one task, not two
            running = {t["kind"] for t in self.store.tasks_running()}
            wants_browser = kind in BROWSER_KINDS or kind == "update"
            wants_gemini = kind in ("process", "update")
            if wants_browser and running & (BROWSER_KINDS | {"update"}):
                raise TaskBusy(
                    "\u0110ang c\u00f3 m\u1ed9t vi\u1ec7c d\u00f9ng tr\u00ecnh duy\u1ec7t ch\u1ea1y (%s). \u0110\u1ee3i n\u00f3 xong r\u1ed3i b\u1ea5m l\u1ea1i."
                    % ", ".join(LABELS[k] for k in running & (BROWSER_KINDS | {"update"}))
                )
            if wants_gemini and running & {"process", "update"}:
                raise TaskBusy("\u0110ang x\u1eed l\u00fd video r\u1ed3i. \u0110\u1ee3i n\u00f3 xong r\u1ed3i b\u1ea5m l\u1ea1i.")
            tid = self.store.task_create(kind, job_id)
        threading.Thread(target=self._run, args=(tid, kind, job_id), daemon=True, name="task-" + kind).start()
        return tid

    # ------------------------------------------------------------------ runners
    def _run(self, task_id, kind, job_id):
        steps = StepLog(self.store, task_id)
        try:
            outcomes = []
            if kind in ("update", "collect"):
                outcomes.append(self._collect_step(steps))
            if kind in ("update", "process"):
                outcomes.append(self._process_step(steps))
            if kind in ("publish", "dryrun"):
                outcomes.append(self._publish_step(steps, kind, job_id))
            if kind == "stats":
                outcomes.append(self._stats_step(steps))
            ok = any(outcomes)
            last_detail = steps.items[-1]["detail"] if steps.items else ""
            print(
                time.strftime("%Y-%m-%d %H:%M:%S ")
                + "task %s %s%s" % (kind, "done" if ok else "error", "" if ok else ": " + last_detail[:200].replace("\n", " ")),
                flush=True,
            )
            self.store.task_update(
                task_id,
                steps=steps.items,
                state="done" if ok else "error",
                result="\n".join("%s %s" % ("✓" if s["state"] == "done" else "✗", s["detail"] or s["name"]) for s in steps.items),
                error="" if ok else (last_detail or "Th\u1ea5t b\u1ea1i"),
            )
        except Exception as error:  # never leave a task "running" after an unexpected error
            self.store.task_update(task_id, steps=steps.items, state="error", error="L\u1ed7i b\u1ea5t ng\u1edd: %s" % str(error)[:300])

    def _collect_step(self, steps):
        index = steps.begin("Thu th\u1eadp video m\u1edbi t\u1eeb c\u00e1c ngu\u1ed3n")
        try:
            report = call_agent("/api/collect", {}, self.token).get("report", {})
        except AgentError as error:
            steps.end(index, "error", str(error))
            return False
        worked = any(r.get("status") == "ok" for r in (report or {}).values())  # every source failed or skipped: nothing was collected
        steps.end(index, "done" if worked else "error", summarize_collect(report))
        return worked

    def _process_step(self, steps):
        index = steps.begin("X\u1eed l\u00fd video \u0111ang ch\u1edd")
        try:
            text = self._process()
        except TaskBusy as busy:
            steps.end(index, "error", str(busy))
            return False
        steps.end(index, "done", text)
        return True

    def _publish_step(self, steps, kind, job_id):
        index = steps.begin(
            "\u0110\u0103ng video l\u00ean TikTok"
            if kind == "publish"
            else "Ch\u1ea1y th\u1eed: t\u1ea3i l\u00ean, \u0111i\u1ec1n m\u00f4 t\u1ea3, d\u1eebng tr\u01b0\u1edbc n\u00fat \u0110\u0103ng"
        )
        try:
            result = call_agent("/api/publish" if kind == "publish" else "/api/dry-run", {"job_id": job_id}, self.token)
        except AgentError as error:
            steps.end(index, "error", str(error))
            return False
        ok = result.get("status") in ("published", "dry_run")
        steps.end(index, "done" if ok else "error", summarize_publish(result))
        return ok

    def _stats_step(self, steps):
        index = steps.begin("\u0110\u1ecdc l\u01b0\u1ee3t xem t\u1eeb h\u1ed3 s\u01a1 TikTok")
        try:
            result = call_agent("/api/stats", {}, self.token)
        except AgentError as error:
            steps.end(index, "error", str(error))
            return False
        steps.end(
            index,
            "done",
            "\u0110\u1ecdc %d b\u00e0i, kh\u1edbp %d b\u00e0i \u0111\u00e3 \u0111\u0103ng."
            % (result.get("read", 0), result.get("matched", 0)),
        )
        return True

    def _process(self):
        """Process up to 4 queued videos, sharing the worker lock with the scheduled /api/process so they never overlap."""
        if not self.process_lock.acquire(blocking=False):
            raise TaskBusy(
                "Worker \u0111ang x\u1eed l\u00fd video cho l\u1ecbch t\u1ef1 \u0111\u1ed9ng. \u0110\u1ee3i n\u00f3 xong r\u1ed3i b\u1ea5m l\u1ea1i."
            )
        try:
            self.store.housekeeping()  # frees jobs a crash left 'processing' (the schedule does this too)
            results = process_many(self.store, PROCESS_BATCH, one=self.process_fn)
            return summarize_process(results)
        finally:
            self.process_lock.release()


class StepLog:
    """The steps of one task, saved to the database every time one starts or ends so the page can show live progress."""

    def __init__(self, store, task_id):
        self.store, self.task_id, self.items = store, task_id, []

    def begin(self, name):
        self.items.append({"name": name, "state": "running", "detail": ""})
        self.store.task_update(self.task_id, steps=self.items)
        return len(self.items) - 1

    def end(self, index, state, detail=""):
        self.items[index].update(state=state, detail=detail)
        self.store.task_update(self.task_id, steps=self.items)
