"""SQLite store: enqueue, claim with a lease, finish, recover. One writer at a time."""
import sqlite3
import time

from . import config
from .states import DEAD, FAILED, PENDING, SENDING, SENT, UNKNOWN


def connect():
    db = sqlite3.connect(config.DB, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY, to_addr TEXT, subject TEXT, body TEXT, state TEXT,"
               " attempts INTEGER DEFAULT 0, not_before REAL DEFAULT 0, lease_until REAL DEFAULT 0, updated REAL)")
    return db


def enqueue(db, to_addr, subject, body):
    cur = db.execute("INSERT INTO jobs (to_addr, subject, body, state, updated) VALUES (?,?,?,?,?)", (to_addr, subject, body, PENDING, time.time()))
    return cur.lastrowid


def claim(db, now=None):
    """Take the oldest due pending job and lease it; None when nothing is due."""
    now = now or time.time()
    db.execute("BEGIN IMMEDIATE")
    row = db.execute("SELECT * FROM jobs WHERE state=? AND not_before<=? ORDER BY updated LIMIT 1", (PENDING, now)).fetchone()
    if row:
        db.execute("UPDATE jobs SET state=?, lease_until=?, updated=? WHERE id=?", (SENDING, now + config.LEASE_SECONDS, now, row["id"]))
    db.execute("COMMIT")
    return row


def finish(db, job_id, outcome, now=None):
    """outcome: sent | temporary | permanent | unknown. A report for a job that is not sending is ignored."""
    now = now or time.time()
    row = db.execute("SELECT * FROM jobs WHERE id=? AND state=?", (job_id, SENDING)).fetchone()
    if not row:
        return False
    attempts = row["attempts"] + 1
    if outcome == "sent":
        state, wait = SENT, 0
    elif outcome == "unknown":
        state, wait = UNKNOWN, 0
    elif outcome == "temporary" and attempts < config.MAX_ATTEMPTS:
        state, wait = PENDING, 2 ** attempts * 60
    else:
        state, wait = (DEAD if outcome == "permanent" or attempts >= config.MAX_ATTEMPTS else FAILED), 0
    db.execute("UPDATE jobs SET state=?, attempts=?, not_before=?, updated=? WHERE id=?", (state, attempts, now + wait, now, job_id))
    return True


def recover(db, now=None):
    """A job still 'sending' after its lease ran out may or may not have gone out: mark it unknown, never resend by itself."""
    now = now or time.time()
    db.execute("UPDATE jobs SET state=?, updated=? WHERE state=? AND lease_until<?", (UNKNOWN, now, SENDING, now))


def resolve(db, job_id, answer):
    """The owner says an unknown job was 'sent' or should be retried ('retry')."""
    state = SENT if answer == "sent" else PENDING
    cur = db.execute("UPDATE jobs SET state=?, not_before=0, updated=? WHERE id=? AND state=?", (state, time.time(), job_id, UNKNOWN))
    return cur.rowcount == 1
