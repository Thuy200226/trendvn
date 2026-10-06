"""Database schema and its migrations.

The schema version is kept in SQLite's `PRAGMA user_version`. Each migration runs once, in order, in its own transaction
together with the version bump, so a crash half-way leaves the database as it was. The first migration is idempotent on purpose:
databases created by TrendVN 1.0 - 1.3 carry no version number but already have these tables, so they are adopted as version 1
without touching their data.
"""

import json
import time

from ..domain.settings import DEFAULT_TARGET, DEFAULTS, RETIRED_MODELS, RETIRED_TTS
from ..jsonsafe import loads

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
    for statement in BASELINE_TABLES.split(";"):  # one by one: executescript would commit the migration's transaction
        if statement.strip():
            db.execute(statement)
    present = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    for column in JOB_COLUMNS:
        if column.split()[0] not in present:
            db.execute("ALTER TABLE jobs ADD COLUMN " + column)


ACCOUNTS_TABLE = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, label TEXT, topics TEXT NOT NULL, enabled INTEGER DEFAULT 1,
    daily_limit INTEGER, min_gap INTEGER, windows TEXT, visibility TEXT, created REAL)
"""


# A migration must give the same result however the code around it changes later, so the constants it needs are written out here
# instead of imported: what the single account of 1.0 - 1.3 took, spelled out in the finer topics.
V2_MAIN_TOPICS = ("entertainment", "music", "comedy", "pets", "family", "lifestyle")


def _accounts(db):
    """Version 2: several TikTok accounts, each with its topics, and a topic on every video. The account of 1.0 - 1.3 becomes `main`."""
    db.execute(ACCOUNTS_TABLE)
    row = db.execute("SELECT value FROM settings WHERE key='target'").fetchone()
    target = loads(row[0] if row else None, "") or DEFAULT_TARGET
    db.execute(
        "INSERT OR IGNORE INTO accounts(id,username,label,topics,enabled,created) VALUES ('main',?,?,?,1,?)",
        (target, target, json.dumps(list(V2_MAIN_TOPICS)), time.time()),
    )
    present = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    for column in ("topic TEXT", "topic_hint TEXT", "account TEXT"):
        if column.split()[0] not in present:
            db.execute("ALTER TABLE jobs ADD COLUMN " + column)
    db.execute(
        "UPDATE jobs SET topic=json_extract(analysis,'$.topic') WHERE topic IS NULL AND analysis IS NOT NULL AND json_valid(analysis)"
    )


def _legacy_posts(db):
    """Version 3: posts made before accounts existed belong to `main`, whatever the default account is today."""
    row = db.execute("SELECT username FROM accounts WHERE id='main'").fetchone()
    if row:
        db.execute(
            "UPDATE jobs SET account='main',target=COALESCE(target,?) WHERE account IS NULL AND state IN ('publishing','published','publish_unknown')",
            (row[0],),
        )


def _news_topic(db):
    """Version 4: hot news and drama are wanted (owner's brief, October 2026). `main` takes them too, but only while it still has exactly
    the topics it was created with: an account the owner has edited is never touched."""
    row = db.execute("SELECT topics FROM accounts WHERE id='main'").fetchone()
    if row and loads(row[0], []) == list(V2_MAIN_TOPICS):  # an unreadable or edited list is left exactly as it is
        db.execute("UPDATE accounts SET topics=? WHERE id='main'", (json.dumps([*V2_MAIN_TOPICS, "news"]),))


def _retention(db):
    """Version 5: when a finished video's files were removed (so the cleanup never looks at it twice), and an index for the duplicate check
    that runs whenever a download is attached (a scan of every video before; measured 2 ms at 20,000 videos, growing with them)."""
    present = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    if "pruned_at" not in present:
        db.execute("ALTER TABLE jobs ADD COLUMN pruned_at REAL")
    db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_hash ON jobs(content_hash)")


def _product_search(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS searches (id TEXT PRIMARY KEY, account TEXT NOT NULL, mode TEXT, created REAL, state TEXT, reference TEXT, identity TEXT, results TEXT, error TEXT, note TEXT)"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_searches_created ON searches(created)")
    if "account_username" not in {r[1] for r in db.execute("PRAGMA table_info(searches)")}:
        db.execute("ALTER TABLE searches ADD COLUMN account_username TEXT")
    present = {row[1] for row in db.execute("PRAGMA table_info(jobs)")}
    for column in ("search_id TEXT", "search_account TEXT"):
        if column.split()[0] not in present:
            db.execute("ALTER TABLE jobs ADD COLUMN " + column)


MIGRATIONS = [_baseline, _accounts, _legacy_posts, _news_topic, _retention, _product_search]


def migrate(db):
    """Bring the database to the latest schema version."""
    for number, step in enumerate(MIGRATIONS, start=1):
        db.execute("BEGIN IMMEDIATE")  # one migrator at a time, and the version is read under that lock
        try:
            if db.execute("PRAGMA user_version").fetchone()[0] < number:
                step(db)
                db.execute("PRAGMA user_version = %d" % number)
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise


def seed_settings(db):
    """Insert default settings that are missing, and move settings that name a model Google has retired to the current default."""
    for key, value in DEFAULTS.items():
        db.execute("INSERT OR IGNORE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
    for key, retired in (("model", RETIRED_MODELS), ("tts_model", RETIRED_TTS)):
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        if row and loads(row[0], "") in retired:  # (a list or number in that row is simply not a retired name)
            db.execute("UPDATE settings SET value=? WHERE key=?", (json.dumps(DEFAULTS[key]), key))


def initialise(db):
    """Open-time setup: WAL mode, schema, default settings."""
    db.execute("PRAGMA journal_mode=WAL")
    migrate(db)
    seed_settings(db)
