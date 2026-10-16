"""Wiring: the store, the background tasks, the security rules and the lock that keeps processing to one run at a time."""

import secrets
import threading

from pathlib import Path

from .. import notify
from ..pipeline import process_one
from ..store import Store
from ..tasks import Tasks
from . import log as _log
from .config import WebConfig
from .security import Access


class App:
    """Everything a request handler needs, created once at start-up."""

    def __init__(self, config=None):
        self.config = config or WebConfig.from_env()
        self.store = Store(self.config.data_dir)
        self.store.notifier = notify.Notifier(self.store)
        recovered = self.store.recover_after_restart()  # this process has just started: nothing it had claimed is still running
        if recovered:
            _log.log("restart: %d video(s) that were being processed went back to the queue or to review" % recovered)
        self.access = Access(self.config)
        self.csrf = self._load_or_create_csrf()
        self.process_lock = threading.Lock()  # scheduled /api/process and the dashboard buttons share it
        self.tasks = Tasks(self.store, self.config.token, process_one, self.process_lock)
        self.log = _log.log

    def _load_or_create_csrf(self):
        """Persist the CSRF token across worker updates/restarts so open dashboards never get 'Trang đã cũ'."""
        csrf_path = Path(self.config.data_dir) / "csrf.key"
        if csrf_path.is_file():
            try:
                token = csrf_path.read_text(encoding="utf-8").strip()
                if len(token) >= 32:
                    return token
            except Exception:
                pass
        token = secrets.token_urlsafe(32)
        try:
            csrf_path.write_text(token, encoding="utf-8")
        except Exception:
            pass
        return token
