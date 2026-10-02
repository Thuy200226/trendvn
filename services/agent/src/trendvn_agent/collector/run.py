"""One collection run: scan the sources, qualify, hand to the worker, download the best."""

import shutil
import time

from ..browser import chrome
from ..config import RUNTIME
from ..log import log
from ..worker_client import worker, worker_get
from .capture import Blocked, NoVideos, exit_country
from .download import MAX_BYTES as MAX_DOWNLOAD_BYTES
from .download import download
from .rules import age_hours, choose_downloads, qualifies, score
from .sources import SOURCES

MIN_FREE_BYTES = 1 << 30  # below 1 GiB free nothing new is downloaded: a full disk stops the database, not just this collector


def free_bytes():
    """Free space on the disk that holds the shared data folder (None when it cannot be read)."""
    try:
        return shutil.disk_usage(RUNTIME).free
    except OSError:
        return None


def collect(platforms=None, download_media=True, ingest=True, thresholds=None, limit=None):
    st = worker_get("/api/status")
    thresholds = dict(thresholds or st.get("thresholds") or {}, weights=st.get("weights") or {})
    limit = limit or thresholds.get("max_candidates_per_scan", 6)
    topics = st.get("wanted_topics") or []  # what the accounts take: the scan looks for these, the download picks among them
    report = {}
    selected = list(platforms or SOURCES)
    by_country = {}
    for p in selected:
        by_country.setdefault(SOURCES[p]["country"], []).append(p)
    for country, plats in by_country.items():
        try:
            with chrome("collector-" + country.lower(), locale=SOURCES[plats[0]]["locale"], region=country) as ctx:
                exit_c = exit_country(ctx)
                log("%s sources use exit country %s" % (country, exit_c))
                for platform in plats:
                    if SOURCES[platform]["geo_locked"] and exit_c != country:
                        report[platform] = {
                            "status": "skipped",
                            "reason": "Cần IP %s để lấy xu hướng đúng quốc gia; IP hiện tại: %s. Đặt TRENDVN_%s_PROXY."
                            % (country, exit_c or "không xác định", country),
                        }
                        continue
                    report[platform] = run_platform(ctx, platform, thresholds, download_media, ingest, limit, topics)
        except Exception as e:
            for platform in plats:
                report.setdefault(platform, {"status": "error", "reason": str(e)[:200]})
    ok = [p for p, r in report.items() if r.get("status") == "ok"]
    detail = {p: (r.get("summary") or r.get("reason")) for p, r in report.items()}
    if ingest:
        worker("/api/heartbeat", {"component": "discovery", "ok": bool(ok), "detail": detail})
    return report


def run_platform(ctx, platform, thresholds, download_media, ingest, limit, topics=()):
    cfg = SOURCES[platform]
    try:
        streams = cfg["scan"](ctx, topics)
    except NoVideos:
        return {
            "status": "error",
            "reason": "Trang không trả về video nào (có thể bị giới hạn tốc độ hoặc đổi giao diện); thử lại ở lần quét sau.",
        }
    except Blocked as e:
        return {"status": "error", "reason": "Trang yêu cầu xác minh/đăng nhập (%s); không vượt qua CAPTCHA." % e}
    except Exception as e:
        return {"status": "error", "reason": "Lỗi thu thập: " + str(e)[:160]}
    summary = {}
    downloads = []
    weights = thresholds.get("weights") or {}
    for stream, raw in streams.items():
        good = [i for i in raw if qualifies(platform, i, thresholds, topic_stream=bool(i.get("topic")))]
        for i in good:
            age = age_hours(i)
            i["score"] = score(platform, i, weights)
            i["meta"] = {
                k: v
                for k, v in (
                    ("score", i["score"]),
                    ("likes", i.get("likes")),
                    ("views", i.get("views")),
                    ("age_h", round(age, 1) if age is not None else None),
                    ("created", i.get("created")),
                )
                if v is not None
            }
        summary[stream] = {"seen": len(raw), "qualified": len(good)}
        if not ingest or not good:
            continue
        batch = {
            "platform": platform,
            "stream": stream,
            "observed_at": time.time(),
            "topic": next((i.get("topic") for i in raw if i.get("topic")), None),  # the source's own category for this stream
            "items": [
                {
                    "source_id": i["source_id"],
                    "url": i["url"],
                    "country": cfg["country"],
                    "title": i["title"],
                    "rank": i["rank"],
                    "views": i["views"],
                    "evidence_url": i["url"],
                    "meta": i["meta"],
                }
                for i in good[:100]
            ],
        }
        try:
            res = worker("/api/ingest", batch)
            summary[stream].update(baseline=res["baseline"], new=res["new"])
        except Exception as e:
            summary[stream]["error"] = str(e)[:160]
        downloads.extend(good)
    if download_media and ingest:
        summary["media"] = fetch_pending(ctx, platform, {i["source_id"]: i for i in downloads}, limit, topics)
    return {
        "status": "ok" if any(s.get("seen") for s in summary.values() if isinstance(s, dict)) else "error",
        "summary": summary,
        "reason": None if any(s.get("seen") for s in summary.values() if isinstance(s, dict)) else "Không đọc được video nào",
    }


def fetch_pending(ctx, platform, seen_now, limit, wanted=()):
    free = free_bytes()
    if free is not None and free < MIN_FREE_BYTES:
        return {
            "downloaded": 0,
            "failed": 0,
            "waiting": 0,
            "note": "Ổ đĩa chỉ còn %d MB trống; chưa tải thêm (dọn ổ đĩa rồi quét lại)" % (free >> 20),
        }
    status = worker_get("/api/status")
    # the worker's own figure leaves out rendered videos no account takes; the raw counts are the fallback for an older worker
    backlog = status.get("backlog")
    if backlog is None:
        backlog = sum(status["counts"].get(k, 0) for k in ("queued", "processing", "ready"))
    room = max(0, status["thresholds"].get("max_backlog", 4) - backlog)
    limit = min(limit, room)
    if limit == 0:
        return {"downloaded": 0, "failed": 0, "waiting": 0, "note": "Hàng chờ đã đủ; chưa tải thêm"}
    # the worker lists this platform's candidates best score first, so the newest 100 of other platforms cannot push the best ones out
    pending = [p for p in worker("/api/media/pending", {"limit": 100, "platform": platform})["items"] if p["source_id"] in seen_now]
    scores = {sid: item.get("score", 0) for sid, item in seen_now.items()}
    chosen = choose_downloads(pending, scores, wanted, limit)
    done = failed = 0
    for job in chosen:
        free = free_bytes()  # again before every download: up to 10 videos of 250 MB each can follow one check
        if free is not None and free - MAX_DOWNLOAD_BYTES < MIN_FREE_BYTES:
            log("%s: only %d MB free, no more downloads this scan" % (platform, free >> 20))
            break
        item = seen_now[job["source_id"]]
        try:
            name = download(ctx, item, platform)
            res = worker("/api/attach", {"id": job["id"], "filename": name})
            log("%s %s -> %s" % (platform, job["source_id"], res["state"]))
            done += 1
        except Exception as e:
            failed += 1
            log("download failed %s %s: %s" % (platform, job["source_id"], str(e)[:160]))
            try:
                worker("/api/media/failed", {"id": job["id"], "reason": str(e)[:300]})
            except Exception:
                pass
    return {"downloaded": done, "failed": failed, "waiting": max(0, len(pending) - len(chosen))}
