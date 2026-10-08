"""Discovery side of the queue: observations from the collector, downloaded media, duplicate detection by content hash."""

import re
import time
import uuid

from ..domain.observations import validate_batch
from ..domain.platforms import COUNTRIES
from ..domain.topics import topic_hint
from ..files import file_hash


class IngestMixin:
    """New videos arriving from the browser agent."""

    def ingest(self, batch, now=None):
        """Record one scan of one platform stream. The first scan of a stream only records a baseline (nothing becomes a candidate)."""
        now = now or time.time()
        report = validate_batch(batch, now)
        result = {"baseline": False, "new": 0, "existing": 0, "candidate_ids": [], "candidates": []}
        with self.transaction() as db:
            last = db.execute("SELECT * FROM streams WHERE name=?", (report.stream,)).fetchone()
            if last and report.observed <= last["last_scan"]:
                raise ValueError("Scan already ingested or older than last scan")
            result["baseline"] = baseline = last is None
            for item in report.items:
                self._observe(db, report, item, baseline, now, result)
            db.execute("INSERT OR REPLACE INTO streams VALUES(?,?)", (report.stream, report.observed))
        return result

    def _observe(self, db, report, item, baseline, now, result):
        """One video seen in a scan: refresh a known job, or create a new one (baseline or candidate)."""
        row = db.execute("SELECT id FROM jobs WHERE platform=? AND source_id=?", (report.platform, item.source_id)).fetchone()
        if row:
            job_id = row["id"]
            result["existing"] += 1
            hint = topic_hint(report.topic, item.title)
            # a stream with its own category (a Douyin tab) knows better than the keywords that guessed when the video first appeared
            keep = "COALESCE(?,topic_hint)" if report.topic else "COALESCE(topic_hint,?)"
            # `updated` is when the job's STATE last changed (retention, recovery and the lists order by it): seeing the video again
            # does not change its state, so it must not make a rejected job's files look recent or keep an undecided one from expiring
            db.execute(
                "UPDATE jobs SET last_seen=?,meta=CASE WHEN search_id IS NOT NULL THEN meta ELSE COALESCE(?,meta) END,topic_hint=%s WHERE id=?"
                % keep,
                (report.observed, item.meta, hint, job_id),
            )
        else:
            job_id = uuid.uuid4().hex
            state = "baseline" if baseline else "candidate"
            reason = "Initial observation only" if baseline else "New in monitored source; validate evidence before processing"
            db.execute(
                """INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated,meta,topic_hint)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    report.platform,
                    item.source_id,
                    item.url,
                    COUNTRIES[report.platform],
                    item.title,
                    report.observed,
                    report.observed,
                    state,
                    reason,
                    now,
                    item.meta,
                    topic_hint(report.topic, item.title),
                ),
            )
            result["new"] += 1
            if not baseline:
                result["candidate_ids"].append(job_id)
                result["candidates"].append({"id": job_id, "source_id": item.source_id})
            self.event(db, job_id, state)
        db.execute(
            "INSERT INTO observations VALUES(?,?,?,?,?,?)",
            (job_id, report.stream, report.observed, item.rank, item.views, item.evidence),
        )

    def attach(self, jid, filename):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,150}", filename):
            raise ValueError("Invalid file name")
        p = (self.root / "inbox" / filename).resolve()
        if p.parent != self.root / "inbox" or not p.is_file():
            raise ValueError("Source file missing")
        digest = file_hash(p)
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
            if not row or row["state"] not in ("candidate", "awaiting_media"):
                raise ValueError("Job not eligible for media")
            dup = db.execute("SELECT id FROM jobs WHERE content_hash=? AND id<>?", (digest, jid)).fetchone()
            state = "duplicate" if dup else "queued"
            db.execute(
                "UPDATE jobs SET source_file=?,content_hash=?,state=?,reason=?,updated=? WHERE id=?",
                (str(p), digest, state, "Duplicate of " + dup["id"] if dup else "", time.time(), jid),
            )
            self.event(db, jid, state)
        return {"id": jid, "state": state}

    def candidates_without_media(self, limit=20, platform=None, source_ids=None):
        """Videos found but not downloaded, best score first. Newest-first would let a burst of weak new videos push the best ones past
        `limit`; `platform` keeps another platform's rows out of the way. `source_ids` (what the scan asking has just seen) restricts the
        list BEFORE it is cut to `limit`: a scan can only download what it saw, and a pool of old high scores must not hide it."""
        where, args = "state='candidate' AND search_id IS NULL", []
        if platform is not None:
            where += " AND platform=?"
            args.append(platform)
        if source_ids is not None:
            if not source_ids:
                return []
            where += " AND source_id IN (%s)" % ",".join("?" * len(source_ids))
            args.extend(source_ids)
        with self.connect() as db:
            return [
                dict(r)
                for r in db.execute(
                    "SELECT id,platform,source_id,url,title,topic_hint FROM jobs WHERE %s "
                    "ORDER BY COALESCE(json_extract(meta,'$.score'),0) DESC, first_seen DESC, id LIMIT ?" % where,
                    (*args, max(1, min(int(limit), 200))),
                )
            ]

    def mark_media_failed(self, jid, reason):
        with self.transaction() as db:
            db.execute(
                "UPDATE jobs SET state=CASE WHEN attempts>=2 THEN 'failed' ELSE state END,attempts=attempts+1,reason=?,updated=? WHERE id=? AND state='candidate'",
                (reason[:700], time.time(), jid),
            )
            self.event(db, jid, "media_failed", reason)
