"""The processing pipeline: one queued video in, one rendered, checked, captioned video (or a reason) out."""

import json
from pathlib import Path

from .ai.analyzer import analyze
from .ai.errors import RateLimited
from .ai.prompts import PROMPT_VERSION
from .ai.tts import make_voice
from .files import file_hash
from .media.ffmpeg import probe
from .media.fingerprint import fingerprint, similar
from .media.geometry import display_size, layout
from .media.render import make_poster, qc, render

REASON_LIMIT = 700


def process_one(store):
    """Claim the next queued video and run it through `_process`. Always returns a small status dict, never raises."""
    cfg = store.settings()
    if not cfg["processing_enabled"]:
        return {"status": "disabled", "reason": "Enable processing after configuring Gemini"}
    if not (store.root / "gemini.key").exists():
        return {"status": "blocked", "reason": "Gemini API key missing"}
    job = store.claim()
    if not job:
        return {"status": "idle", "reason": "No staged media in queue"}
    try:
        return _process(store, cfg, job)
    except RateLimited as e:
        store.release(job["id"], job["lease"], str(e))
        return {"id": job["id"], "status": "rate_limited", "reason": str(e)}
    except Exception as e:
        reason = str(e)[:REASON_LIMIT]
        store.finish(job["id"], job["lease"], "needs_review", reason=reason)
        return {"id": job["id"], "status": "needs_review", "reason": reason}


def _process(store, cfg, job):
    jid, lease, approved = job["id"], job["lease"], bool(job.get("approved"))
    folder = store.root / "jobs" / jid
    folder.mkdir(exist_ok=True)
    path, duration = _source(job, cfg)
    fp = fingerprint(path, duration)
    twin = None if approved else _look_alike(store, jid, fp, duration)  # the owner's approval overrides the look-alike warning
    if twin:
        store.finish(
            jid, lease, "needs_review", reason="Possible visual duplicate of " + twin, fingerprint=json.dumps(fp), duration=duration
        )
        return {"id": jid, "status": "needs_review"}
    a, route = analyze(store, path, duration, cfg, folder, lenient=approved)
    if not approved and not str(a.get("caption_vi") or "").strip():
        raise ValueError("Gemini không soạn được mô tả tiếng Việt; cần bạn xem lại")
    voice, route, note = _voice_or_subtitles(store, cfg, a, route, folder)
    out = render(path, folder, a, route, duration, voice)
    info = _checked_output(out, path, route, folder, duration)
    digest = file_hash(out)
    _write_manifest(folder, job, cfg, a, route, digest, info)
    approval = cfg["require_approval"] and not approved
    state = "awaiting_approval" if approval else "ready"
    store.finish(
        jid,
        lease,
        state,
        analysis=json.dumps(a, ensure_ascii=False),
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
    duration, _ = probe(path)
    if not 1 <= duration <= cfg["max_duration"]:
        raise ValueError("Video duration outside configured limits")
    return path, duration


def _look_alike(store, jid, fp, duration):
    """Id of an earlier video that looks the same (similar length and picture), or None."""
    with store.connect() as db:
        others = db.execute("SELECT id,fingerprint,duration FROM jobs WHERE fingerprint IS NOT NULL AND id<>?", (jid,)).fetchall()
    for row in others:
        if abs(row["duration"] - duration) < 2 and similar(fp, json.loads(row["fingerprint"])):
            return row["id"]
    return None


def _voice_or_subtitles(store, cfg, a, route, folder):
    """Turn the analysis' route into what will really be rendered. Returns (voice or None, route, note for the dashboard).
    A voice-over that cannot be made falls back to subtitles alone, which are a complete and safe result."""
    if route != "voiceover":
        return None, route, ""
    if not cfg["voiceover_enabled"]:
        return None, "vietsub", ""
    try:
        return make_voice(store, cfg, a, folder), "voiceover", ""
    except Exception as e:
        return None, "vietsub", " (lồng tiếng bỏ qua: %s)" % str(e)[:120]


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
