"""Publishing: claim a rendered video, record the outcome, and the safety rails around the account."""

import json
import re
import time
import uuid

from ..domain.captions import build_caption


class PublishingMixin:
    """Everything between "a video is ready" and "it is on TikTok"."""

    def published_today(self, db=None, now=None):
        start = self.day_start(now)
        q = "SELECT count(*) FROM jobs WHERE state IN ('published','publishing','publish_unknown') AND COALESCE(published_at,updated)>=?"
        if db is not None:
            return db.execute(q, (start,)).fetchone()[0]
        with self.connect() as c:
            return c.execute(q, (start,)).fetchone()[0]

    def publish_claim(self, now=None, job_id=None):
        """Reserve a rendered video for publishing.
        Scheduled use (job_id=None): honours the switch, posting window, daily limit and spacing, and picks the best-scored video.
        Manual use (job_id given, from the dashboard button): the owner's click is the consent for that one video, so the switch,
        window, limit and spacing are waived; the safety rails that protect the account (one post in flight, unconfirmed posts,
        TikTok verification pause) still apply."""
        now = now or time.time()
        cfg = self.settings()
        manual = job_id is not None
        if not manual and not cfg["publisher_enabled"]:
            return {"status": "disabled", "reason": "Publishing switch is off"}
        if cfg.get("publisher_challenge"):
            return {"status": "blocked", "reason": "TikTok is asking for human verification; solve it once with `./trendvn tiktok trust`"}
        with self.transaction() as db:
            if db.execute("SELECT count(*) FROM jobs WHERE state IN ('publishing','publish_unknown')").fetchone()[0]:
                return {"status": "blocked", "reason": "A previous publish is unconfirmed; resolve it before publishing again"}
            if manual:
                row = self._chosen_video(db, job_id)
                if not row:
                    return {"status": "idle", "reason": "Video này không còn ở trạng thái sẵn sàng đăng"}
            else:
                refusal = self._schedule_refusal(db, cfg, now)
                if refusal:
                    return refusal
                row = self._best_ready_video(db, now)
                if not row:
                    return {"status": "idle", "reason": "No rendered video is waiting"}
            return self._reserve(db, row, cfg, now, manual)

    def _schedule_refusal(self, db, cfg, now):
        """Why the schedule may not post right now (outside the golden hours, daily limit, spacing), or None."""
        inside, opening = self.window_state(cfg, now)
        if not inside:
            return {"status": "wait", "reason": "Ngoài giờ vàng; lần tới lúc " + opening, "next_window": opening}
        if self.published_today(db, now) >= cfg["daily_limit"]:
            return {"status": "limit", "reason": "Daily limit reached"}
        last = db.execute("SELECT max(published_at) FROM jobs WHERE state='published'").fetchone()[0]
        if last and now - last < cfg["min_publish_gap"]:
            return {
                "status": "wait",
                "reason": "Minimum gap between posts not reached",
                "retry_after": int(last + cfg["min_publish_gap"] - now),
            }
        return None

    @staticmethod
    def _best_ready_video(db, now):
        """The highest-scored rendered video, skipping any that failed to post within the last hour."""
        return db.execute(
            "SELECT * FROM jobs WHERE state='ready' AND output_file IS NOT NULL AND COALESCE(last_publish_fail,0)<? "
            "ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 1",
            (now - 3600,),
        ).fetchone()

    @staticmethod
    def _chosen_video(db, job_id):
        return db.execute(
            "SELECT * FROM jobs WHERE id=? AND state IN ('ready','awaiting_approval') AND output_file IS NOT NULL", (job_id,)
        ).fetchone()

    def _reserve(self, db, row, cfg, now, manual):
        """Mark the video as being published (with a lease the agent must present when it reports back) and return the claim."""
        token = uuid.uuid4().hex
        db.execute(
            "UPDATE jobs SET state='publishing',publish_lease=?,prev_state=?,updated=? WHERE id=?", (token, row["state"], now, row["id"])
        )
        self.event(db, row["id"], "publishing", "thủ công" if manual else "")
        analysis = json.loads(row["analysis"]) if row["analysis"] else {}
        caption = row["caption_user"] or build_caption(analysis, row["title"])
        db.execute("UPDATE jobs SET caption=? WHERE id=?", (caption, row["id"]))
        return {
            "status": "claimed",
            "id": row["id"],
            "lease": token,
            "caption": caption,
            "route": row["route"],
            "manual": manual,
            "output_file": row["output_file"],
            "output_hash": row["output_hash"],
            "target": cfg["target"],
            "visibility": cfg["visibility"],
        }

    def publish_peek(self, job_id=None):
        """A rendered video for rehearsals (the next one, or a chosen one); changes nothing and ignores the publishing switch."""
        cfg = self.settings()
        with self.connect() as db:
            if job_id:
                row = db.execute(
                    "SELECT * FROM jobs WHERE id=? AND state IN ('ready','awaiting_approval') AND output_file IS NOT NULL", (job_id,)
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT * FROM jobs WHERE state='ready' AND output_file IS NOT NULL ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen LIMIT 1"
                ).fetchone()
        if not row:
            return {"status": "idle", "reason": "No rendered video is waiting"}
        a = json.loads(row["analysis"]) if row["analysis"] else {}
        return {
            "status": "ready",
            "id": row["id"],
            "caption": row["caption_user"] or build_caption(a, row["title"]),
            "route": row["route"],
            "output_file": row["output_file"],
            "output_hash": row["output_hash"],
            "target": cfg["target"],
            "visibility": cfg["visibility"],
        }

    def publish_finish(self, jid, lease, outcome, url="", reason=""):
        """outcome: published (confirmed on the account), failed (nothing was posted; counted), deferred (nothing was posted and it is
        not the video's fault, e.g. TikTok verification; not counted), unknown (may have posted), duplicate."""
        states = {"published": "published", "failed": "ready", "deferred": "ready", "unknown": "publish_unknown", "duplicate": "duplicate"}
        if outcome not in states:
            raise ValueError("Invalid publish outcome")
        if url and not re.fullmatch(r'https://[A-Za-z0-9.-]+\.tiktok\.com/[^\s"<>]{1,300}', url):
            raise ValueError("Invalid publish URL")
        parked = False
        with self.transaction() as db:
            row = db.execute("SELECT attempts,publish_lease,state,prev_state,publish_fails FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] != "publishing" or row["publish_lease"] != lease:
                raise ValueError("Stale publish lease")
            now = time.time()
            state = states[outcome]
            fails, last_fail = row["publish_fails"] or 0, None
            if outcome in ("failed", "deferred") and row["prev_state"] == "awaiting_approval":
                state = "awaiting_approval"  # a failed manual click must not silently approve the video for the scheduler
            if outcome == "failed":
                fails, last_fail = fails + 1, now
                if fails >= 3:
                    state, parked = "needs_review", True  # a video that keeps failing stops blocking the queue
                    reason = "Đăng thất bại %d lần liên tiếp, cần bạn xem: %s" % (fails, reason)
            db.execute(
                "UPDATE jobs SET state=?,publish_lease=NULL,publish_url=?,reason=?,published_at=?,updated=?,publish_fails=?,last_publish_fail=COALESCE(?,last_publish_fail) WHERE id=?",
                (state, url or None, reason[:700], now if outcome == "published" else None, now, fails, last_fail, jid),
            )
            self.event(db, jid, "publish_" + outcome, reason)
            title = (db.execute("SELECT title FROM jobs WHERE id=?", (jid,)).fetchone() or ["?"])[0][:60]
        if outcome == "published":
            self.emit("published", "✅ Đã đăng: %s\n%s" % (title, url), jid)
        elif outcome == "unknown":
            self.emit("urgent", "🚨 Đã bấm Đăng nhưng chưa xác nhận được: %s\nHệ thống dừng đăng. %s" % (title, reason), jid)
        elif parked:
            self.emit("review", "⚠️ Video đăng lỗi nhiều lần, đã chuyển sang Cần xem: %s\n%s" % (title, reason), jid)
        elif outcome == "failed":
            self.emit("publish_failed", "⚠️ Đăng chưa thành công (sẽ thử lại sau): %s" % reason, "publish_failed")

    def set_challenge(self, active):
        """TikTok asked for human verification. Publishing pauses (no retries that would keep triggering it) until the owner clears it."""
        with self.transaction() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("publisher_challenge", json.dumps(bool(active))))
            self.event(db, "", "challenge_on" if active else "challenge_off", "")
        if active:
            self.emit(
                "urgent",
                "🧩 TikTok đang yêu cầu xác minh (CAPTCHA). Đăng bài tạm dừng. Hãy giải một lần: chạy `./trendvn tiktok trust` (Mac: nhấp đúp macos/Xac-minh-TikTok.command).",
                "challenge",
            )

    def resolve_unknown(self, jid, outcome, url=""):
        """Operator/agent verified the account: mark an uncertain publish as published or as not posted."""
        if outcome not in ("published", "failed"):
            raise ValueError("Invalid outcome")
        with self.transaction() as db:
            row = db.execute("SELECT state,prev_state FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] != "publish_unknown":
                raise ValueError("Job is not awaiting confirmation")
            now = time.time()
            back = "awaiting_approval" if row["prev_state"] == "awaiting_approval" else "ready"
            db.execute(
                "UPDATE jobs SET state=?,publish_url=?,published_at=?,reason=?,updated=? WHERE id=?",
                (
                    "published" if outcome == "published" else back,
                    url or None,
                    now if outcome == "published" else None,
                    "Confirmed by account check",
                    now,
                    jid,
                ),
            )
            self.event(db, jid, "resolved_" + outcome)

    def unresolved(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,title,caption,updated FROM jobs WHERE state='publish_unknown'")]
