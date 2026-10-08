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
from .search import runner

PROCESS_BATCH = 4  # videos processed per press of the button
BROWSER_KINDS = {
    "queue_download",
    "delete_post",
    "identify",
    "collect",
    "publish",
    "dryrun",
    "stats",
    "search",
    "search_download",
    "search_human",
    "channel_login",
    "channel_check",
}
CHAT_KINDS = (
    "identify",
    "link",
    "search",
    "search_human",
    "search_download",
    "channel_login",
    "channel_check",
)  # the jobs behind the product chat (search/runner.py)
DELETE_TIMEOUT = 300  # seconds to wait for the agent to delete a post: longer than the slowest path through TikTok Studio (about 215 s)
LABELS = {
    "queue_download": "Tải ứng viên vào chờ xử lý",
    "delete_post": "Xóa bài trên TikTok",
    "channel_login": "Đăng nhập kênh tìm kiếm",
    "channel_check": "Kiểm tra đăng nhập kênh tìm kiếm",
    "identify": "Nhận diện sản phẩm",
    "link": "Kiểm tra link hoa hồng",
    "search_human": "Tự xác minh và tìm lại",
    "search": "Tìm video về sản phẩm",
    "search_download": "Tải video đã chọn",
    "update": "Cập nhật tổng hợp",
    "collect": "Thu thập video mới",
    "process": "Xử lý video đang chờ",
    "process_one": "Xử lý video đã chọn",
    "publish": "Đăng video",
    "dryrun": "Xem thử (không đăng)",
    "stats": "Đọc lượt xem",
}
PLATFORM_NAMES = NAMES
PROCESS_LABELS = {
    "ready": "sẵn sàng đăng",
    "awaiting_approval": "chờ bạn duyệt",
    "needs_review": "cần duyệt",
    "rate_limited": "chờ Gemini hết quá tải",
    "error": "lỗi",
    "blocked": "bị chặn",
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
            raise AgentError("Trình duyệt agent đang bận việc khác (có thể lịch tự động đang chạy). Thử lại sau vài phút.") from None
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except Exception:
            pass
        raise AgentError("Agent báo lỗi %d%s" % (e.code, ": " + detail[:200] if detail else "")) from None
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
        raise AgentError("Không gọi được agent trình duyệt. Kiểm tra dịch vụ trendvn-agent đang chạy (./trendvn doctor).") from None


def summarize_collect(report):
    """One readable line per source from the agent's collect report."""
    lines = []
    for p, r in (report or {}).items():
        name = PLATFORM_NAMES.get(p, p)
        if r.get("status") == "skipped":
            lines.append("%s: bỏ qua (%s)" % (name, r.get("reason", "").split(". ")[0].rstrip(".")[:90]))
        elif r.get("status") != "ok":
            lines.append("%s: lỗi, %s" % (name, (r.get("reason") or "")[:80]))
        else:
            streams = [v for k, v in (r.get("summary") or {}).items() if isinstance(v, dict) and k != "media"]
            seen = sum(s.get("seen", 0) for s in streams)
            good = sum(s.get("qualified", 0) for s in streams)
            new = sum(s.get("new", 0) for s in streams if not s.get("baseline"))
            media = (r.get("summary") or {}).get("media") or {}
            base = any(s.get("baseline") for s in streams)
            why = (
                " (%s)" % media["note"][:90] if media.get("note") else ""
            )  # e.g. the queue is full: the owner should know why nothing came
            lines.append(
                "%s: đọc %d, đạt ngưỡng %d, %s, tải %d%s"
                % (name, seen, good, "lần đầu: chỉ ghi mốc" if base else "mới %d" % new, media.get("downloaded", 0), why)
            )
    return "\n".join(lines) or "Không có nguồn nào chạy."


def summarize_process(results):
    """One sentence for the dashboard. Results arrive in the order the runs finished, so look at all of them, not the first."""
    if not results:
        return "Không có video nào để xử lý."
    statuses = [r.get("status") for r in results]
    if "disabled" in statuses:
        return 'Xử lý video đang TẮT. Bật công tắc "Xử lý video" rồi bấm lại.'
    blocked = next((r for r in results if r.get("status") == "blocked"), None)
    if blocked and all(s in ("blocked", "idle") for s in statuses):
        return blocked.get("reason", "Chưa xử lý được.")
    if all(s == "idle" for s in statuses):
        return "Không có video nào đang chờ xử lý."
    counts = {}
    for r in results:
        counts[r.get("status")] = counts.get(r.get("status"), 0) + 1
    return "Đã xử lý: " + ", ".join("%d %s" % (n, PROCESS_LABELS.get(k, k)) for k, n in counts.items() if k not in ("idle",)) + "."


def summarize_publish(res):
    s = res.get("status")
    if s == "published":
        return "Đã đăng và xác nhận trên hồ sơ." + ((" " + res["url"]) if res.get("url") else "")
    if s == "dry_run":
        shot = str(res.get("screenshot") or "")
        link = " Xem ảnh chụp: /media/shot/" + shot if re.fullmatch(r"shot_\d{9,12}\.png", shot) else ""
        return (res.get("reason") or "Chạy thử xong: đã tải video, điền mô tả và dừng trước nút Đăng.") + link
    if s == "challenge":  # the agent's reason names the account's own command (`... trust --account pets`)
        return res.get("reason") or "TikTok đòi xác minh. Đăng tạm dừng; giải một lần bằng `./trendvn tiktok trust`."
    if s == "unknown":
        return "Đã bấm Đăng nhưng chưa xác nhận được. Hệ thống dừng đăng; xem mục Cần xem."
    return res.get("reason") or "Chưa đăng được (%s)." % s


class Tasks:
    def __init__(self, store, token, process_fn, process_lock):
        self.store, self.token, self.process_fn, self.process_lock = store, token, process_fn, process_lock
        self.guard = threading.Lock()
        self.references = {}  # what the owner sent with a message, until its job has read it (never written to disk)
        store.tasks_reap()
        store.chat_recover()
        store.delete_post_recover()

    def start(self, kind, job_id=None, reference=None):
        if kind not in LABELS:
            raise ValueError("Việc không hợp lệ")
        if kind == "delete_post" and (not isinstance(reference, dict) or not reference.get("grant") or reference.get("job_id") != job_id):
            raise ValueError("Cần xác nhận xóa bài từ tab Đã đăng")
        if kind in ("publish", "dryrun", "process_one", "queue_download") and not job_id:
            raise ValueError("Cần chọn một video")
        if kind in CHAT_KINDS and not (
            isinstance(job_id, str) and re.fullmatch(r"[0-9a-f]{32}" if kind == "search_download" else r"\d{1,12}", job_id)
        ):
            raise ValueError("Mã tin nhắn không hợp lệ")
        with self.guard:  # check-and-create is atomic, so a double click starts one task, not two
            running = {t["kind"] for t in self.store.tasks_running()}
            wants_browser = kind in BROWSER_KINDS or kind == "update"
            if kind == "identify":
                wants_browser = bool(self.store.chat_get(int(job_id))["body"].get("discovery"))
            wants_gemini = kind in ("process", "process_one", "update")
            if wants_browser and running & (BROWSER_KINDS | {"update"}):
                raise TaskBusy(
                    "Đang có một việc dùng trình duyệt chạy (%s). Đợi nó xong rồi bấm lại."
                    % ", ".join(LABELS[k] for k in running & (BROWSER_KINDS | {"update"}))
                )
            if wants_gemini and running & {"process", "process_one", "update"}:
                raise TaskBusy("Đang xử lý video rồi. Đợi nó xong rồi bấm lại.")
            tid = self.store.task_create(kind, job_id)
            if reference is not None:
                self.references[job_id] = reference
        try:
            threading.Thread(target=self._run, args=(tid, kind, job_id), daemon=True, name="task-" + kind).start()
        except Exception:  # no thread to be had: the task must not stay 'running' (it would block every browser job until a restart)
            self.references.pop(job_id, None)
            self.store.task_update(tid, state="error", error="Không khởi động được việc; thử lại sau")
            raise
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
            if kind == "process_one":
                outcomes.append(self._process_step(steps, job_id))
            if kind in ("publish", "dryrun"):
                outcomes.append(self._publish_step(steps, kind, job_id))
            if kind == "stats":
                outcomes.append(self._stats_step(steps))
            if kind == "delete_post":
                outcomes.append(self._delete_post_step(steps, job_id))
            if kind == "queue_download":
                outcomes.append(self._queue_download_step(steps, job_id))
            if kind in CHAT_KINDS:
                outcomes.append(self._chat_step(steps, kind, job_id))
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
                error="" if ok else (last_detail or "Thất bại"),
            )
        except Exception as error:  # never leave a task "running" after an unexpected error
            self.store.task_update(task_id, steps=steps.items, state="error", error="Lỗi bất ngờ: %s" % str(error)[:300])

    def _collect_step(self, steps):
        index = steps.begin("Thu thập video mới từ các nguồn")
        try:
            report = call_agent("/api/collect", {}, self.token).get("report", {})
        except AgentError as error:
            steps.end(index, "error", str(error))
            return False
        worked = any(r.get("status") == "ok" for r in (report or {}).values())  # every source failed or skipped: nothing was collected
        steps.end(index, "done" if worked else "error", summarize_collect(report))
        return worked

    def _chat_step(self, steps, kind, key):
        index = steps.begin(LABELS[kind])

        def agent(path, payload, timeout):
            return call_agent(path, payload, self.token, timeout)

        ok, text = runner.run(self.store, kind, key, agent, self.references.pop(key, None))
        steps.end(index, "done" if ok else "error", text)
        return ok

    def _process_step(self, steps, job_id=None):
        index = steps.begin("Xử lý video đang chờ")

        def on_progress(msg):
            steps.step(index, msg)

        try:
            text = self._process(job_id, progress_fn=on_progress)
        except TaskBusy as busy:
            steps.end(index, "error", str(busy))
            return False
        steps.end(index, "done", text)
        return True

    def _publish_step(self, steps, kind, job_id):
        index = steps.begin("Đăng video lên TikTok" if kind == "publish" else "Chạy thử: tải lên, điền mô tả, dừng trước nút Đăng")
        try:
            result = call_agent("/api/publish" if kind == "publish" else "/api/dry-run", {"job_id": job_id}, self.token)
        except AgentError as error:
            steps.end(index, "error", str(error))
            return False
        ok = result.get("status") in ("published", "dry_run")
        steps.end(index, "done" if ok else "error", summarize_publish(result))
        return ok

    def _stats_step(self, steps):
        index = steps.begin("Đọc lượt xem từ hồ sơ TikTok")
        try:
            result = call_agent("/api/stats", {}, self.token)
        except AgentError as error:
            steps.end(index, "error", str(error))
            return False
        steps.end(index, "done", "Đọc %d bài, khớp %d bài đã đăng." % (result.get("read", 0), result.get("matched", 0)))
        return True

    def _delete_post_step(self, steps, job_id):
        index = steps.begin("Xác minh tài khoản và xóa đúng bài trên TikTok")
        grant = self.references.pop(job_id)
        try:
            result = call_agent("/api/post-delete", grant, self.token, timeout=DELETE_TIMEOUT)
        except Exception as error:
            # how far the agent got decides what this means (see delete_post_abort): never started = failed, started = for the owner to check
            self.store.delete_post_abort(job_id, grant["grant"], str(error)[:300])
            row = self.store.delete_post_state(job_id)
            steps.end(
                index,
                "error",
                (
                    "Chưa thử xóa bài; thử lại khi trình duyệt rảnh. "
                    if row == "failed"
                    else "Chưa xác nhận kết quả xóa; kiểm tra TikTok trước khi tiếp tục. "
                )
                + str(error)[:200],
            )
            return False
        ok = result.get("status") == "deleted"
        steps.end(index, "done" if ok else "error", result.get("reason", "Đã xóa bài trên TikTok" if ok else "Chưa xóa được"))
        return ok

    def _queue_download_step(self, steps, job_id):
        index = steps.begin("Tải chính ứng viên đã chọn")
        try:
            payload = self.store.candidate_download(job_id)
            result = call_agent("/api/search/download", payload, self.token, timeout=240)
            if result.get("state") not in ("queued", "duplicate"):
                raise ValueError("Tải chưa hoàn tất")
        except Exception as error:
            self.store.candidate_download_failed(job_id, str(error))
            steps.end(index, "error", str(error)[:500])
            return False
        steps.end(index, "done", "Video đã vào chờ xử lý" if result["state"] == "queued" else "Video trùng dữ liệu đã có")
        return True

    def _process(self, job_id=None, progress_fn=None):
        """Process up to 4 queued videos, sharing the worker lock with the scheduled /api/process so they never overlap."""
        if not self.process_lock.acquire(blocking=False):
            raise TaskBusy("Worker đang xử lý video cho lịch tự động. Đợi nó xong rồi bấm lại.")
        try:
            self.store.housekeeping()  # frees jobs a crash left 'processing' (the schedule does this too)

            def run_one(store, job=None):
                try:
                    if job is not None and progress_fn is not None:
                        return self.process_fn(store, job_id=job, progress_fn=progress_fn)
                    elif job is not None:
                        return self.process_fn(store, job_id=job)
                    elif progress_fn is not None:
                        return self.process_fn(store, progress_fn=progress_fn)
                    else:
                        return self.process_fn(store)
                except TypeError:
                    try:
                        if job is not None:
                            return self.process_fn(store, job_id=job)
                        return self.process_fn(store)
                    except TypeError:
                        return self.process_fn(store)

            results = (
                [run_one(self.store, job=job_id)]
                if job_id is not None
                else process_many(self.store, PROCESS_BATCH, one=lambda s, **kw: run_one(s), progress_fn=progress_fn)
            )
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

    def step(self, index, detail):
        if 0 <= index < len(self.items):
            self.items[index]["detail"] = detail
            self.store.task_update(self.task_id, steps=self.items)

    def end(self, index, state, detail=""):
        self.items[index].update(state=state, detail=detail)
        self.store.task_update(self.task_id, steps=self.items)
