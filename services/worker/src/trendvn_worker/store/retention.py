"""Keeping the disk from filling: expire what nobody acted on, delete the files of finished videos, trim the history tables.

A full disk stops the database, so it stops everything. Videos are the big part (a source file is 15-250 MB, the render another
10-30 MB). Rows are never deleted for videos: the row is what remembers "this video was already seen/posted" and keeps duplicates out.
Only the files (and rows of pure history: observations, events, tasks, API calls) go. Every limit below is a day count and can be
changed in one place; the defaults keep a week of files, which is enough to look at what was posted and to re-approve a mistake.
"""

import re
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
KEEP_CHAT_DAYS = 30  # finished chat messages (the search history); saved links, picked videos and sign-ins are not history
ORPHAN_GRACE_HOURS = 24  # a file no job knows about is only removed after this, so one being written right now is never touched
BATCH = 200  # most jobs whose files are removed per call; the rest wait for the next call
RETRY_AFTER_FAILURE_HOURS = 24  # a job whose files could not be removed (read-only folder, odd path) is tried again after this long
INBOX_NAME = re.compile(r"[A-Za-z0-9_.-]{1,150}")  # what attach() accepts as a file name: anything else is never turned into a path
FINISHED = ("published", "rejected", "duplicate", "failed")
KEEP_IN_JOB_FOLDER = ("manifest.json", "poster.jpg")  # a few KB: the record of how a video was made, and its thumbnail
DAY = 86400


class RetentionMixin:
    """Called by housekeeping (n8n runs it on a schedule): `prune()` is safe to run any time and as often as you like."""

    def prune(self, now=None):
        """Apply every retention rule. Returns what was done; a rule that fails is skipped, never fatal."""
        now = now or time.time()
        result = {"expired": 0, "files_removed": 0, "freed_mb": 0.0, "rows_trimmed": 0, "orphans": 0, "failed": 0}
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
                "SELECT id,state FROM jobs WHERE (state IN ('candidate','search_selected') AND first_seen<?) OR "
                "(state IN ('needs_review','awaiting_approval','ready') AND updated<?) LIMIT ?",
                (now - CANDIDATE_EXPIRY_DAYS * DAY, now - UNDECIDED_EXPIRY_DAYS * DAY, BATCH),
            ).fetchall()
            for row in stale:
                why = (
                    "Quá %d ngày không được tải" % CANDIDATE_EXPIRY_DAYS
                    if row["state"] in ("candidate", "search_selected")
                    else ("Quá %d ngày không ai quyết định" % UNDECIDED_EXPIRY_DAYS)
                )
                db.execute(
                    "UPDATE jobs SET state='rejected',reason=?,updated=? WHERE id=? AND state=?", (why, now, row["id"], row["state"])
                )
                self.event(db, row["id"], "expired", why)
        return {"expired": len(stale)}

    # ------------------------------------------------------------------ files of finished videos
    def _remove_finished_files(self, now):
        """pruned_at: NULL = files not removed yet; a positive time = removed then; a negative time = a removal failed then (retried after
        RETRY_AFTER_FAILURE_HOURS, so one stubborn job cannot starve the rest of the batch)."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,source_file FROM jobs WHERE (pruned_at IS NULL OR (pruned_at<0 AND -pruned_at<?)) "
                "AND (source_file IS NOT NULL OR output_file IS NOT NULL) "
                "AND state IN (%s) AND COALESCE(published_at,updated)<? LIMIT ?" % ",".join("?" * len(FINISHED)),
                (now - RETRY_AFTER_FAILURE_HOURS * 3600, *FINISHED, now - KEEP_FILES_DAYS * DAY, BATCH),
            ).fetchall()
            # a name another job that is still alive points at must survive (two jobs can only share a file through API misuse, but a
            # live video's source is not worth guessing about)
            live = {
                name
                for (path,) in db.execute(
                    "SELECT source_file FROM jobs WHERE source_file IS NOT NULL AND state NOT IN (%s)" % ",".join("?" * len(FINISHED)),
                    FINISHED,
                )
                if (name := self._inbox_name(path))
            }
        removed, freed, failed, outcome = 0, 0, 0, []
        for row in rows:
            count, size, ok = self._remove_job_files(row["id"], row["source_file"], live)
            removed, freed = removed + count, freed + size
            failed += 0 if ok else 1
            outcome.append((now if ok else -now, row["id"], ok))
        if rows:
            with self.transaction() as db:
                db.executemany(
                    "UPDATE jobs SET source_file=CASE WHEN ? THEN NULL ELSE source_file END,pruned_at=? WHERE id=?",
                    [(1 if ok else 0, stamp, jid) for stamp, jid, ok in outcome],
                )
        return {"files_removed": removed, "freed_mb": freed / 1048576, "failed": failed}

    @staticmethod
    def _inbox_name(source_file):
        """The file name a job's source_file stands for, or None when it is not a plain name (empty, '.', '..', odd characters)."""
        name = str(source_file or "").replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
        return name if INBOX_NAME.fullmatch(name) and name not in (".", "..") else None

    def _remove_job_files(self, jid, source_file, live=frozenset()):
        """Delete one job's source and render files, keeping manifest.json and the poster. Only paths inside the data folder are touched.
        Returns (files removed, bytes freed, ok): ok is False when something that should go could not be removed."""
        count = size = 0
        ok = True
        targets = []
        name = self._inbox_name(source_file)
        if name and name not in live:
            targets.append(self.root / "inbox" / name)
        folder = self.root / "jobs" / jid
        try:
            if folder.is_dir() and not folder.is_symlink():
                targets += [path for path in folder.iterdir() if path.name not in KEEP_IN_JOB_FOLDER]
        except OSError:
            ok = False
        for path in targets:
            gone = self._delete_inside_root(path)
            if gone is False:
                ok = False
            elif gone is not None:
                count, size = count + 1, size + gone
        return count, size, ok

    def _delete_inside_root(self, path):
        """Remove a file or folder if it really lives under the data folder (never follows a symlink out of it). Returns the bytes freed,
        None when there was nothing to remove, False when it should have been removed and could not be."""
        try:
            if path.is_symlink():
                path.unlink()
                return 0
            if not path.exists():
                return None
            resolved = path.resolve()
            if self.root not in resolved.parents:
                return False  # a path that leads out of the data folder (a symlinked inbox, say): never touched, never "done"
            if resolved.is_dir():
                size = sum(f.stat().st_size for f in resolved.rglob("*") if f.is_file() and not f.is_symlink())
                shutil.rmtree(resolved)
            else:
                size = resolved.stat().st_size
                resolved.unlink()
            return size
        except OSError:
            return False

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
        return {"rows_trimmed": trimmed + self.chat_clear(before=now - KEEP_CHAT_DAYS * DAY)}

    # ------------------------------------------------------------------ files nothing refers to
    def _remove_orphans(self, now):
        """Source files in inbox/ that no job points at (a download whose attach failed), job folders of jobs that do not exist, and old
        screenshots. Anything younger than the grace period is left alone: it may be in the middle of being written. Age is the inode
        change time, which a downloader cannot set (yt-dlp copies the server's Last-Modified into the modification time, so a fresh
        download can look weeks old by mtime)."""
        cutoff = now - ORPHAN_GRACE_HOURS * 3600
        with self.connect() as db:
            used = {
                name
                for (path,) in db.execute("SELECT source_file FROM jobs WHERE source_file IS NOT NULL")
                if (name := self._inbox_name(path))
            }
            known = {row[0] for row in db.execute("SELECT id FROM jobs")}
        removed, freed, failed = 0, 0, 0
        candidates = [(p, cutoff) for p in self._listing(self.root / "inbox") if p.name not in used]
        candidates += [(p, cutoff) for p in self._listing(self.root / "jobs") if p.name not in known]
        candidates += [
            (p, now - KEEP_SCREENSHOTS_DAYS * DAY) for p in self._listing(self.root / "exports") if re.fullmatch(r"shot_\d+\.png", p.name)
        ]
        for path, limit in candidates:
            try:
                if path.lstat().st_ctime >= limit:
                    continue
            except OSError:
                continue
            gone = self._delete_inside_root(path)
            if gone is False:
                failed += 1
            elif gone is not None:
                removed, freed = removed + 1, freed + gone
        return {"orphans": removed, "freed_mb": freed / 1048576, "failed": failed}

    @staticmethod
    def _listing(folder):
        try:
            return list(folder.iterdir())
        except OSError:
            return []
