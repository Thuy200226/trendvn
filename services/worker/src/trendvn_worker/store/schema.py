"""Database schema and its migrations.

The schema version is kept in SQLite's `PRAGMA user_version`. Migrations run once each, in order, inside the opening
transaction. The first migration is idempotent on purpose: databases created by TrendVN 1.0 - 1.3 carry no version number but
already have these tables, so they are adopted as version 1 without touching their data.
"""

import json

from ..domain.settings import DEFAULTS, RETIRED_MODELS, RETIRED_TTS

BASELINE_TABLES = """
CREATE TABLE IF NOT EXISTS streams (name TEXT PRIMARY KEY, last_scan REAL);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, platform TEXT, source_id TEXT, url TEXT, country TEXT,
    title TEXT, first_seen REAL, last_seen REAL, state TEXT, reason TEXT,
    source_file TEXT, content_hash TEXT, fingerprint TEXT, duration REAL,
    analysis TEXT, route TEXT, output_file TEXT, output_hash TEXT,
    lease TEXT, attempts INTEGER DEFAULT 0, target TEXT, publish_url TEXT,
    updated REAL, UNIQUE(platform, source_id), UNIQUE(url));
CREATE TABLE IF NOT EXISTS observations (
    job_id TEXT, stream TEXT, observed REAL, rank INTEGER, views INTEGER,
    evidence TEXT, PRIMARY KEY(job_id, stream, observed));
CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, at REAL, job_id TEXT, event TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS api_calls (at REAL, model TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS post_stats (job_id TEXT, at REAL, views INTEGER, likes INTEGER, comments INTEGER, shares INTEGER);
CREATE TABLE IF NOT EXISTS notif_log (kind TEXT, key TEXT, at REAL);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, kind TEXT, job_id TEXT, state TEXT, started REAL, finished REAL,
    steps TEXT, result TEXT, error TEXT);
CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_ps ON jobs(platform, state);
CREATE INDEX IF NOT EXISTS idx_jobs_updated ON jobs(updated);
CREATE INDEX IF NOT EXISTS idx_events_job ON events(job_id);
CREATE INDEX IF NOT EXISTS idx_stats_job ON post_stats(job_id, at);
CREATE INDEX IF NOT EXISTS idx_events_at ON events(at);
"""

# Columns added to `jobs` over the releases (older databases get them one by one).
JOB_COLUMNS = (
    "published_at REAL",
    "caption TEXT",
    "publish_lease TEXT",
    "approved INTEGER DEFAULT 0",
    "meta TEXT",
    "caption_user TEXT",
    "output_info TEXT",
    "prev_state TEXT",
    "publish_fails INTEGER DEFAULT 0",
    "last_publish_fail REAL",
)


def _baseline(db):
    db.executescript(BASELINE_TABLES)
    present = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    for column in JOB_COLUMNS:
        if column.split()[0] not in present:
            db.execute("ALTER TABLE jobs ADD COLUMN " + column)


MIGRATIONS = [_baseline]


def migrate(db):
    """Bring the database to the latest schema version."""
    version = db.execute("PRAGMA user_version").fetchone()[0]
    for number, step in enumerate(MIGRATIONS, start=1):
        if number > version:
            step(db)
            db.execute("PRAGMA user_version = %d" % number)


def seed_settings(db):
    """Insert default settings that are missing, and move settings that name a model Google has retired to the current default."""
    for key, value in DEFAULTS.items():
        db.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
    for key, retired in (("model", RETIRED_MODELS), ("tts_model", RETIRED_TTS)):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row and json.loads(row[0]) in retired:
            db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(DEFAULTS[key]), key))


def initialise(db):
    """Open-time setup: WAL mode, schema, default settings."""
    db.execute("PRAGMA journal_mode=WAL")
    migrate(db)
    seed_settings(db)
