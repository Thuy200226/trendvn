"""Settings read from the environment, with defaults."""
import os

DB = os.environ.get("MAILQ_DB", "data/mailq.sqlite3")
RATE_PER_MIN = int(os.environ.get("MAILQ_RATE_PER_MIN", "30"))
PORT = int(os.environ.get("MAILQ_PORT", "8080"))
MAX_ATTEMPTS = int(os.environ.get("MAILQ_MAX_ATTEMPTS", "3"))
LEASE_SECONDS = int(os.environ.get("MAILQ_LEASE_SECONDS", "600"))
SMTP_HOST = os.environ.get("MAILQ_SMTP_HOST", "localhost")
SMTP_PORT = int(os.environ.get("MAILQ_SMTP_PORT", "587"))
TOKEN = os.environ.get("MAILQ_TOKEN", "")
