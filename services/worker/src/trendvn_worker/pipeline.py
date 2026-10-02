"""The processing pipeline: one queued video in, one rendered, checked, captioned video (or a reason) out."""

import json
import os
import shutil
import threading
from pathlib import Path

from .ai.analyzer import analyze
from .ai.errors import RateLimited
from .ai.prompts import PROMPT_VERSION
from .ai.tts import make_voice
from .domain.readability import TOO_FAST, fit_reading_speed
from .domain.route import REASONS
from .files import file_hash
from .media.ffmpeg import probe
from .media.fingerprint import fingerprint, similar
from .media.geometry import display_size, layout
from .media.render import covered_hard_subtitles, make_poster, qc, render

REASON_LIMIT = 700
MIN_FREE_BYTES = 512 << 20  # below this much free disk nothing new is processed: a render needs room, and a full disk stops the database
MIN_SIDE = 64  # pixels: a 1x1 or 2x2 "video" (a tracking pixel, a broken download) cannot become a post
TERMINAL_STATUSES = ("disabled", "blocked", "idle", "rate_limited")  # after one of these there is nothing more to do right now


# Videos processed at once. A video spends most of its time waiting for Gemini (about two thirds), so a second one in flight nearly doubles
# throughput; more than a few would only fight over the CPU for ffmpeg. TRENDVN_PROCESS_PARALLEL=1 gives the old one-at-a-time behaviour.
def _parallel_setting(text):
    """TRENDVN_PROCESS_PARALLEL as a number from 1 to 4; anything unreadable means the default 2 (a typo must not stop the worker starting)."""
    try:
        return max(1, min(4, int(str(text).strip())))
    except ValueError:
        return 2


PARALLEL = _parallel_setting(os.environ.get("TRENDVN_PROCESS_PARALLEL") or 2)


def free_bytes(path):
    """Free space on the disk holding `path` (a function of its own so tests need not depend on the real disk)."""
    return shutil.disk_usage(path).free


def process_many(store, count, parallel=None, one=None):
    """Process up to `count` queued videos, `parallel` at a time (default PARALLEL). Each thread claims the next video when it is free;
    once any run reports a terminal status (disabled, blocked, idle, rate limited) nothing new is started. Returns the results in the
    order they finished; a run that raises is reported as an error instead of stopping the others."""
    one = one or process_one
    threads = max(1, min(parallel or PARALLEL, count))
    results, budget, stop, lock = [], [count], threading.Event(), threading.Lock()

    def work():
        while not stop.is_set():
            with lock:
                if budget[0] <= 0:
                    return
                budget[0] -= 1
            try:
                result = one(store)
            except Exception as error:  # process_one answers instead of raising; this is a safety net, not a code path
                result = {"status": "error", "reason": str(error)[:REASON_LIMIT]}
            with lock:
                results.append(result)
            if result.get("status") in TERMINAL_STATUSES:
                stop.set()

    if count <= 0:
        return []
    workers = [threading.Thread(target=work, name="process-%d" % n, daemon=True) for n in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    return results


def process_one(store):
    """Claim the next queued video and run it through `_process`. Always returns a small status dict, never raises."""
    cfg = store.settings()
    if not cfg["processing_enabled"]:
        return {"status": "disabled", "reason": "Enable processing after configuring Gemini"}
    if not (store.root / "gemini.key").exists():
        return {"status": "blocked", "reason": "Gemini API key missing"}
    free = free_bytes(store.root)
    if free < MIN_FREE_BYTES:
        return {"status": "blocked", "reason": "Ổ đĩa chỉ còn %d MB trống; chưa dựng thêm (dọn ổ đĩa rồi chạy lại)" % (free >> 20)}
    job = store.claim()
    if not job:
        return {"status": "idle", "reason": "No staged media in queue"}
    try:
        return _process(store, cfg, job)
    except RateLimited as e:
        reason = str(e)
        return _settle(job, "rate_limited", reason, lambda: store.release(job["id"], job["lease"], reason))
    except Exception as e:
        reason = str(e)[:REASON_LIMIT]
        return _settle(job, "needs_review", reason, lambda: store.finish(job["id"], job["lease"], "needs_review", reason=reason))


def _settle(job, status, reason, record):
    """Record how a run ended. If the job was taken away meanwhile (housekeeping gave it back after a long stall, so the lease is stale),
    that is reported as an error for this run instead of raising: process_one always answers."""
    try:
        record()
    except ValueError as error:
        return {"id": job["id"], "status": "error", "reason": "%s (%s)" % (str(error)[:200], reason[:400])}
    return {"id": job["id"], "status": status, "reason": reason}


def _process(store, cfg, job):
    jid, lease, approved = job["id"], job["lease"], bool(job.get("approved"))
    folder = store.root / "jobs" / jid
    folder.mkdir(exist_ok=True)
    path, duration = _source(job, cfg)
    fp = fingerprint(path, duration)
    # the owner's approval overrides the look-alike warning; the fingerprint is recorded in the same step so a look-alike processed at the
    # same moment (several videos run at once) cannot slip past
    twin = store.reserve_fingerprint(jid, lease, fp, duration, similar, check=not approved)
    if twin:
        store.finish(
            jid, lease, "needs_review", reason="Possible visual duplicate of " + twin, fingerprint=json.dumps(fp), duration=duration
        )
        return {"id": jid, "status": "needs_review"}
    a, route = analyze(store, path, duration, cfg, folder, lenient=approved)
    if not approved and not str(a.get("caption_vi") or "").strip():
        raise ValueError("Gemini không soạn được mô tả tiếng Việt; cần bạn xem lại")
    a["segments"], fastest = fit_reading_speed(a["segments"], duration)
    voice, route, why, note = _voice_or_subtitles(store, cfg, a, route, folder)
    out = render(path, folder, a, route, duration, voice)
    info = _checked_output(out, path, route, folder, duration)
    info["why"] = why
    if covered_hard_subtitles(a, route):
        info["hard_subs"] = True  # the source's own burned-in subtitles were blurred out
    if route != "original" and a["segments"]:
        info["max_cps"] = fastest
        if fastest > TOO_FAST:
            info["warning"] = info.get("warning") or "Phụ đề hơi nhanh (%.0f ký tự/giây)" % fastest
    digest = file_hash(out)
    _write_manifest(folder, job, cfg, a, route, digest, info)
    approval = cfg["require_approval"] and not approved
    state = "awaiting_approval" if approval else "ready"
    store.finish(
        jid,
        lease,
        state,
        analysis=json.dumps(a, ensure_ascii=False),
        topic=a.get("topic"),
        route=route,
        output_file=str(out),
        output_hash=digest,
        fingerprint=json.dumps(fp),
        duration=duration,
        output_info=json.dumps(info),
        reason=("Đã dựng, chờ bạn duyệt" if approval else "Đã dựng, sẵn sàng đăng") + note,
    )
    return {"id": jid, "status": state, "route": route}


def _source(job, cfg):
    """The downloaded file after sanity checks. Returns (path, duration)."""
    path = Path(job["source_file"])
    if file_hash(path) != job["content_hash"]:
        raise ValueError("Source file changed after attachment")
    duration, meta = probe(path)
    if not 1 <= duration <= cfg["max_duration"]:
        raise ValueError("Video duration outside configured limits")
    video = next(s for s in meta["streams"] if s["codec_type"] == "video")
    if min(video.get("width") or 0, video.get("height") or 0) < MIN_SIDE:
        raise ValueError("Video quá nhỏ (%sx%s): không dựng được" % (video.get("width"), video.get("height")))
    return path, duration


def _voice_or_subtitles(store, cfg, a, route, folder):
    """Turn the analysis' route into what will really be rendered. Returns (voice or None, route, why, note): `why` is the reason
    shown on the dashboard, `note` the detail appended to the job's status. A voice-over that cannot be made falls back to subtitles
    alone, which are a complete and safe result."""
    why = a.get("route_reason") or ""
    if route != "voiceover":
        return None, route, why, ""
    if not cfg["voiceover_enabled"]:
        return None, "vietsub", REASONS["narration_no_voice"], ""
    try:
        return make_voice(store, cfg, a, folder), "voiceover", why, ""
    except Exception as e:
        return None, "vietsub", REASONS["voice_failed"], " (lồng tiếng bỏ qua: %s)" % str(e)[:120]


def _checked_output(out, source, route, folder, duration):
    """Quality-check the render and describe it for the dashboard; blocking problems raise ValueError."""
    _, src_meta = probe(source)
    info, problems = qc(out, any(s["codec_type"] == "audio" for s in src_meta["streams"]))
    if problems:
        raise ValueError("Kiểm tra chất lượng video dựng: " + "; ".join(problems))
    info["route"] = route
    info["reframed"] = layout(*display_size(next(s for s in src_meta["streams"] if s["codec_type"] == "video")))["reframe"]
    try:
        make_poster(out, folder / "poster.jpg", duration)
        info["poster"] = True
    except Exception:
        info["poster"] = False
    return info


def _write_manifest(folder, job, cfg, analysis, route, digest, info):
    manifest = {
        "id": job["id"],
        "source_url": job["url"],
        "source_hash": job["content_hash"],
        "output_hash": digest,
        "route": route,
        "target": cfg["target"],
        "analysis": analysis,
        "prompt_version": PROMPT_VERSION,
        "output_info": info,
        "published": False,
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
