"""Keeping the disk from filling: expire what nobody acted on, delete the files of finished videos, trim the history tables.

A full disk stops the database, so it stops everything. Videos are the big part (a source file is 15-250 MB, the render another
10-30 MB). Rows are never deleted for videos: the row is what remembers "this video was already seen/posted" and keeps duplicates out.
Only the files (and rows of pure history: observations, events, tasks, API calls) go. Every limit below is a day count and can be
changed in one place; the defaults keep a week of files, which is enough to look at what was posted and to re-approve a mistake.
"""

import shutil
import time

# Days a finished video (published, rejected, duplicate, failed) keeps its source and its render after it was last touched.
KEEP_FILES_DAYS = 7
# A found video that was never downloaded stops being a candidate after this long: a trend is a few days old at best.
CANDIDATE_EXPIRY_DAYS = 3
# A video that nobody approved, reviewed or posted (needs_review, awaiting_approval, ready) is let go after this long.
UNDECIDED_EXPIRY_DAYS = 21
KEEP_OBSERVATIONS_DAYS = 30  # one row per video per scan
KEEP_EVENTS_DAYS = 60
KEEP_TASKS_DAYS = 14
KEEP_SCREENSHOTS_DAYS = 14
ORPHAN_GRACE_HOURS = 24  # a file no job knows about is only removed after this, so one being written right now is never touched
BATCH = 200  # most jobs whose files are removed per call; the rest wait for the next call
FINISHED = ("published", "rejected", "duplicate", "failed")
KEEP_IN_JOB_FOLDER = ("manifest.json", "poster.jpg")  # a few KB: the record of how a video was made, and its thumbnail
DAY = 86400


class RetentionMixin:
    """Called by housekeeping (n8n runs it on a schedule): `prune()` is safe to run any time and as often as you like."""

    def prune(self, now=None):
        """Apply every retention rule. Returns what was done; a rule that fails is skipped, never fatal."""
        now = now or time.time()
        result = {"expired": 0, "files_removed": 0, "freed_mb": 0.0, "rows_trimmed": 0, "orphans": 0}
        for step in (self._expire, self._remove_finished_files, self._trim_history, self._remove_orphans):
            try:
                for key, value in step(now).items():
                    result[key] += value
            except Exception as error:  # noqa: BLE001  (one failing rule must not stop the others)
                result.setdefault("errors", []).append("%s: %s" % (step.__name__, str(error)[:120]))
        result["freed_mb"] = round(result["freed_mb"], 1)
        return result

    # ------------------------------------------------------------------ rows that stop waiting
    def _expire(self, now):
        """Candidates and undecided videos that waited too long become `rejected` (with the reason), freeing their files for removal."""
        with self.transaction() as db:
            stale = db.execute(
                "SELECT id,state FROM jobs WHERE (state='candidate' AND first_seen<?) OR "
                "(state IN ('needs_review','awaiting_approval','ready') AND updated<?) LIMIT ?",
                (now - CANDIDATE_EXPIRY_DAYS * DAY, now - UNDECIDED_EXPIRY_DAYS * DAY, BATCH),
            ).fetchall()
            for row in stale:
                why = (
                    "Quá %d ngày không được tải" % CANDIDATE_EXPIRY_DAYS
                    if row["state"] == "candidate"
                    else ("Quá %d ngày không ai quyết định" % UNDECIDED_EXPIRY_DAYS)
                )
                db.execute(
                    "UPDATE jobs SET state='rejected',reason=?,updated=? WHERE id=? AND state=?", (why, now, row["id"], row["state"])
                )
                self.event(db, row["id"], "expired", why)
        return {"expired": len(stale)}

    # ------------------------------------------------------------------ files of finished videos
    def _remove_finished_files(self, now):
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,source_file FROM jobs WHERE pruned_at IS NULL AND (source_file IS NOT NULL OR output_file IS NOT NULL) "
                "AND state IN (%s) AND COALESCE(published_at,updated)<? LIMIT ?" % ",".join("?" * len(FINISHED)),
                (*FINISHED, now - KEEP_FILES_DAYS * DAY, BATCH),
            ).fetchall()
        removed, freed = 0, 0
        for row in rows:
            count, size = self._remove_job_files(row["id"], row["source_file"])
            removed, freed = removed + count, freed + size
        if rows:
            with self.transaction() as db:
                db.executemany("UPDATE jobs SET source_file=NULL,pruned_at=? WHERE id=?", [(now, row["id"]) for row in rows])
        return {"files_removed": removed, "freed_mb": freed / 1048576}

    def _remove_job_files(self, jid, source_file):
        """Delete one job's source and render files, keeping manifest.json and the poster. Only paths inside the data folder are touched.
        Returns (files removed, bytes freed)."""
        count = size = 0
        targets = []
        if source_file:
            targets.append(self.root / "inbox" / (source_file.rsplit("/", 1)[-1]))
        folder = self.root / "jobs" / jid
        if folder.is_dir() and not folder.is_symlink():
            targets += [path for path in folder.iterdir() if path.name not in KEEP_IN_JOB_FOLDER]
        for path in targets:
            gone = self._delete_inside_root(path)
            count, size = count + (1 if gone is not None else 0), size + (gone or 0)
        return count, size

    def _delete_inside_root(self, path):
        """Remove a file or folder if it really lives under the data folder (never follows a symlink out of it). Returns bytes freed, or
        None when there was nothing to remove."""
        try:
            if path.is_symlink():
                path.unlink()
                return 0
            resolved = path.resolve()
            if self.root not in resolved.parents or not resolved.exists():
                return None
            if resolved.is_dir():
                size = sum(f.stat().st_size for f in resolved.rglob("*") if f.is_file() and not f.is_symlink())
                shutil.rmtree(resolved, ignore_errors=True)
            else:
                size = resolved.stat().st_size
                resolved.unlink()
            return size
        except OSError:
            return None

    # ------------------------------------------------------------------ history tables
    def _trim_history(self, now):
        with self.transaction() as db:
            trimmed = 0
            for sql, days in (
                ("DELETE FROM observations WHERE observed<?", KEEP_OBSERVATIONS_DAYS),
                ("DELETE FROM events WHERE at<?", KEEP_EVENTS_DAYS),
                ("DELETE FROM tasks WHERE COALESCE(finished,started)<? AND state<>'running'", KEEP_TASKS_DAYS),
                ("DELETE FROM api_calls WHERE at<?", 2),  # the daily Gemini allowance looks back 24 hours only
                ("DELETE FROM notif_log WHERE at<?", 7),
            ):
                trimmed += db.execute(sql, (now - days * DAY,)).rowcount
        return {"rows_trimmed": trimmed}

    # ------------------------------------------------------------------ files nothing refers to
    def _remove_orphans(self, now):
        """Source files in inbox/ that no job points at (a download whose attach failed), job folders of jobs that do not exist, and old
        screenshots. Anything newer than the grace period is left alone: it may be in the middle of being written."""
        cutoff = now - ORPHAN_GRACE_HOURS * 3600
        with self.connect() as db:
            used = {row[0].rsplit("/", 1)[-1] for row in db.execute("SELECT source_file FROM jobs WHERE source_file IS NOT NULL")}
            known = {row[0] for row in db.execute("SELECT id FROM jobs")}
        removed, freed = 0, 0
        candidates = [p for p in (self.root / "inbox").iterdir() if p.name not in used]
        candidates += [p for p in (self.root / "jobs").iterdir() if p.name not in known]
        candidates += [p for p in (self.root / "exports").glob("shot_*.png") if p.stat().st_mtime < now - KEEP_SCREENSHOTS_DAYS * DAY]
        for path in candidates:
            try:
                if path.stat().st_mtime >= cutoff and path.parent.name != "exports":
                    continue
            except OSError:
                continue
            gone = self._delete_inside_root(path)
            if gone is not None:
                removed, freed = removed + 1, freed + gone
        return {"orphans": removed, "freed_mb": freed / 1048576}
