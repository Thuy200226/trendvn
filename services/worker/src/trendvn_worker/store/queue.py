"""Processing side of the queue: claim a job, finish it, human decisions, crash recovery."""

import json
import time
import uuid
from pathlib import Path

from ..files import free_bytes

LOW_DISK_BYTES = 1 << 30  # the same line the collector stops downloading at
STALE_PUBLISHING_SECONDS = 45 * 60  # a post claimed this long ago and never finished has an unknown outcome
from ..jsonsafe import loads


class QueueMixin:
    """The processing queue and the human decisions on its results."""

    def claim(self):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY first_seen LIMIT 1").fetchone()
            if not row:
                return None
            token = uuid.uuid4().hex
            db.execute(
                "UPDATE jobs SET state='processing',lease=?,attempts=attempts+1,updated=? WHERE id=?", (token, time.time(), row["id"])
            )
            self.event(db, row["id"], "processing")
            return dict(row) | {"lease": token}

    def finish(self, jid, lease, state, **fields):
        if state not in ("ready", "awaiting_approval", "needs_review", "failed", "duplicate"):
            raise ValueError("Invalid processing terminal state")
        allowed = {"reason", "analysis", "route", "output_file", "output_hash", "fingerprint", "duration", "output_info", "topic"}
        if set(fields) - allowed:
            raise ValueError("Invalid fields")
        with self.transaction() as db:
            query = (
                "UPDATE jobs SET state=?,lease=NULL,updated=?"
                + "".join(", " + k + "=?" for k in fields)
                + " WHERE id=? AND lease=? AND state='processing'"
            )
            changed = db.execute(query, [state, time.time(), *fields.values(), jid, lease]).rowcount
            if changed != 1:
                raise ValueError("Stale lease")
            self.event(db, jid, state, str(fields.get("reason", "")))
            title = (db.execute("SELECT title FROM jobs WHERE id=?", (jid,)).fetchone() or ["?"])[0][:60]
        reason = str(fields.get("reason", ""))
        if state == "needs_review":
            self.emit("review", "⚠️ C\u1ea7n b\u1ea1n duy\u1ec7t: %s\nL\u00fd do: %s" % (title, reason), jid)
        elif state == "awaiting_approval":
            self.emit("approval", "🎬 Video \u0111\u00e3 d\u1ef1ng, ch\u1edd b\u1ea1n duy\u1ec7t \u0111\u0103ng: %s" % title, jid)
        elif state == "failed":
            self.emit("error", "❌ X\u1eed l\u00fd th\u1ea5t b\u1ea1i: %s\n%s" % (title, reason), jid)

    def reserve_fingerprint(self, jid, lease, fingerprint, duration, similar, check=True):
        """Look for an earlier video that looks the same and, in the same transaction, record this video's fingerprint so that one being
        processed at the same moment sees it. Returns the id of the look-alike, or None. `similar(a, b)` compares two fingerprints."""
        with self.transaction() as db:
            twin = None
            if check:
                for row in db.execute("SELECT id,fingerprint,duration FROM jobs WHERE fingerprint IS NOT NULL AND id<>?", (jid,)):
                    if abs(row["duration"] - duration) < 2 and similar(fingerprint, loads(row["fingerprint"], [])):
                        twin = row["id"]
                        break
            changed = db.execute(
                "UPDATE jobs SET fingerprint=?,duration=? WHERE id=? AND lease=? AND state='processing'",
                (json.dumps(fingerprint), duration, jid, lease),
            ).rowcount
            if changed != 1:
                raise ValueError("Stale lease")
            return twin

    def release(self, jid, lease, reason):
        """Put a claimed job back in the queue untouched (e.g. rate limit); does not count as an attempt."""
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE jobs SET state='queued',lease=NULL,attempts=MAX(attempts-1,0),reason=?,updated=? WHERE id=? AND lease=? AND state='processing'",
                (reason[:700], time.time(), jid, lease),
            ).rowcount
            if changed != 1:
                raise ValueError("Stale lease")
            self.event(db, jid, "released", reason)

    def decide(self, jid, action):
        """Human decision from the dashboard. approve on needs_review re-runs processing with the checks waived."""
        if action not in ("approve", "reject", "retry"):
            raise ValueError("Invalid action")
        with self.transaction() as db:
            row = db.execute("SELECT state,source_file,output_file FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row:
                raise ValueError("Job not found")
            now = time.time()
            if action == "retry":
                # a video parked after repeated posting failures: the rendered file is fine, so put it back in the list of postable videos
                if row["state"] != "needs_review" or not row["output_file"] or not Path(row["output_file"]).is_file():
                    raise ValueError("Video n\u00e0y ch\u01b0a c\u00f3 b\u1ea3n d\u1ef1ng \u0111\u1ec3 \u0111\u0103ng l\u1ea1i")
                db.execute(
                    "UPDATE jobs SET state='ready',publish_fails=0,last_publish_fail=NULL,reason='B\u1ea1n \u0111\u01b0a v\u1ec1 s\u1eb5n s\u00e0ng \u0111\u0103ng',updated=? WHERE id=?",
                    (now, jid),
                )
            elif action == "reject":
                if row["state"] not in ("awaiting_approval", "needs_review", "ready", "candidate", "queued"):
                    raise ValueError("Job cannot be rejected in this state")
                db.execute("UPDATE jobs SET state='rejected',reason='Rejected by operator',updated=? WHERE id=?", (now, jid))
            elif row["state"] == "awaiting_approval":
                db.execute("UPDATE jobs SET state='ready',reason='Approved by operator',updated=? WHERE id=?", (now, jid))
            elif row["state"] == "needs_review":
                if not row["source_file"] or not Path(row["source_file"]).is_file():
                    raise ValueError("Source file is gone; cannot reprocess")
                db.execute(
                    "UPDATE jobs SET state='queued',approved=1,publish_fails=0,last_publish_fail=NULL,reason='Approved by operator; reprocessing',updated=? WHERE id=?",
                    (now, jid),
                )
                # the owner's decision starts the voice's busy-Google allowance afresh (once: `approved` stays on the row for good)
                (self.root / "jobs" / jid / "voice_retries").unlink(missing_ok=True)
            else:
                raise ValueError("Nothing to approve in this state")
            self.event(db, jid, "operator_" + action)

    def housekeeping(self):
        """Crash recovery and the disk: stuck work is freed, then the retention rules run (see store/retention.py)."""
        now = time.time()
        processing = self._recover_processing(now - 1800)
        unknown = self.expire_stale_publishing(now)
        pruned = self.prune(now)
        free = free_bytes(self.root)
        if (
            free < LOW_DISK_BYTES
        ):  # the dashboard shows it too, but a phone message is what gets the disk cleaned before it stops everything
            self.emit(
                "urgent",
                "💾 \u1ed4 \u0111\u0129a ch\u1ec9 c\u00f2n %d MB tr\u1ed1ng: h\u1ec7 th\u1ed1ng \u0111\u00e3 ng\u1eebng t\u1ea3i v\u00e0 d\u1ef1ng th\u00eam video. H\u00e3y d\u1ecdn \u1ed5 \u0111\u0129a (xem ./trendvn doctor)."
                % (free >> 20),
                "disk",
            )
        return {"interrupted_processing": processing, "uncertain_publishing": unknown, "pruned": pruned, "disk_free_mb": free >> 20}

    def expire_stale_publishing(self, now):
        """A post claimed more than 45 minutes ago and never finished (the agent died mid-post) has an unknown outcome: it may be on TikTok.
        It is never retried by itself and its account waits for the owner's confirmation. Called by housekeeping and by every claim, so the
        other accounts do not wait for the next housekeeping (up to three hours) to be allowed to post. Returns how many were found."""
        with self.transaction() as db:
            unknown = db.execute(
                "UPDATE jobs SET state='publish_unknown',reason='Publishing confirmation missing; never retry automatically' WHERE state='publishing' AND updated<?",
                (now - STALE_PUBLISHING_SECONDS,),
            ).rowcount
        if unknown:
            self.emit(
                "urgent",
                "🚨 C\u00f3 %d b\u00e0i \u0111\u0103ng ch\u01b0a x\u00e1c nh\u1eadn. H\u1ec7 th\u1ed1ng \u0111\u00e3 d\u1eebng \u0111\u0103ng \u0111\u1ec3 tr\u00e1nh tr\u00f9ng; m\u1edf b\u1ea3ng \u0111i\u1ec1u khi\u1ec3n \u0111\u1ec3 x\u00e1c nh\u1eadn."
                % unknown,
                "unknown",
            )
        return unknown

    def recover_after_restart(self):
        """The worker process has just started, so nothing it had claimed is still running: put those videos back right away instead of
        waiting half an hour for housekeeping."""
        return self._recover_processing(time.time() + 1)

    def _recover_processing(self, older_than):
        """Videos claimed for processing and then abandoned (a crash, kill -9, a power cut). One that has been tried once goes back in the
        queue untouched; one that has been tried twice is the problem, not the crash, so it waits for the owner. Returns how many were found.
        """
        with self.transaction() as db:
            again = db.execute(
                "UPDATE jobs SET state='queued',lease=NULL,reason='X\u1eed l\u00fd b\u1ecb ng\u1eaft; x\u1ebfp l\u1ea1i h\u00e0ng \u0111\u1ee3i',updated=? "
                "WHERE state='processing' AND updated<? AND attempts<2",
                (time.time(), older_than),
            ).rowcount
            parked = db.execute(
                "UPDATE jobs SET state='needs_review',reason='Processing interrupted; inspect before retry',lease=NULL "
                "WHERE state='processing' AND updated<?",
                (older_than,),
            ).rowcount
        return again + parked
