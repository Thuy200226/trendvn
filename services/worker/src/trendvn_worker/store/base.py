"""Connection handling, transactions, settings and the event log that every other store module builds on."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from ..domain import schedule
from ..domain.settings import DEFAULT_TARGET, DEFAULTS, validate_settings
from .schema import initialise

DATA_FOLDERS = ("inbox", "jobs", "exports")
PARTIAL_DICT_SETTINGS = ("min_views", "min_likes")


class StoreBase:
    """SQLite access shared by the store modules."""

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.notifier = None  # callable(kind, text, key), set by the web app; its failures never affect the queue
        self.root.mkdir(parents=True, exist_ok=True)
        for folder in DATA_FOLDERS:
            (self.root / folder).mkdir(exist_ok=True)
        self.db = self.root / "trendvn.sqlite3"
        with self.connect() as db:
            initialise(db)

    # ------------------------------------------------------------------ connections
    def connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    @contextmanager
    def transaction(self):
        """One writer at a time (BEGIN IMMEDIATE); commits on success, rolls back on any error."""
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ------------------------------------------------------------------ settings
    def settings(self):
        """All settings. `target` (the TikTok account of 1.0 - 1.3) is not stored: it is the default account's username."""
        with self.connect() as db:
            cfg = {}
            for row in db.execute("SELECT * FROM settings"):
                try:
                    cfg[row["key"]] = json.loads(row["value"])
                except ValueError:  # one unreadable row must not take every page down; its default applies
                    if row["key"] in DEFAULTS:
                        cfg[row["key"]] = DEFAULTS[row["key"]]
            default = db.execute("SELECT username FROM accounts ORDER BY enabled DESC, created, id LIMIT 1").fetchone()
        cfg["target"] = default[0] if default else DEFAULT_TARGET
        return cfg

    def update_settings(self, patch):
        clean = validate_settings(patch)
        if clean.get("processing_enabled") and not (self.root / "gemini.key").exists():
            raise ValueError("Gemini key is required to enable processing")
        target = clean.pop("target", None)  # renames the default account instead of being stored
        if target is not None:
            self.set_default_username(target)  # first: a name another account already uses must not leave the other settings half saved
        with self.transaction() as db:
            for key, value in clean.items():
                if key in PARTIAL_DICT_SETTINGS:  # a partial form must never erase the other sources' thresholds
                    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
                    value = {**(json.loads(row["value"]) if row else {}), **value}
                    clean[key] = value
                db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
            self.event(db, "", "settings", ", ".join(sorted(clean)))
        if target is not None:
            clean["target"] = target
        return clean

    # ------------------------------------------------------------------ event log and notifications
    def event(self, db, job_id, name, detail=""):
        db.execute("INSERT INTO events(at, job_id, event, detail) VALUES (?, ?, ?, ?)", (time.time(), job_id, name, detail[:1000]))

    def emit(self, kind, text, key=""):
        """Send a phone notification; a failing channel must never break the operation that raised it."""
        if self.notifier:
            try:
                self.notifier(kind, text, key)
            except Exception:
                pass

    # ------------------------------------------------------------------ time (the timezone is a setting)
    def local_now(self, now=None):
        return schedule.local_now(self.settings()["timezone"], now)

    def day_start(self, now=None):
        """Start of the current local day in the configured timezone, as Unix seconds."""
        return schedule.day_start(self.settings()["timezone"], now)

    def window_state(self, cfg=None, now=None):
        """(inside_window, human text of the next opening). No windows configured means any time."""
        cfg = cfg or self.settings()
        return schedule.window_state(cfg.get("post_windows") or [], cfg["timezone"], now)
