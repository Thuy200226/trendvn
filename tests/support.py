"""Shared test setup: source folders on sys.path, a temporary Store, and helpers to insert jobs."""

import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
for source in (ROOT / "services" / "worker" / "src", ROOT / "services" / "agent" / "src"):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from trendvn_agent import log as agent_log  # noqa: E402
from trendvn_worker import pipeline  # noqa: E402
from trendvn_worker.store import Store  # noqa: E402

# the agent log of the real installation (data/agent/agent.log) must not collect lines written by tests
_LOG_FOLDER = tempfile.TemporaryDirectory()
agent_log.DATA = Path(_LOG_FOLDER.name)

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


def at(hour, minute=0):
    """A fixed day (2026-09-30) at the given Vietnam local time, as Unix seconds."""
    return datetime(2026, 9, 30, hour, minute, tzinfo=TZ).timestamp()


class StoreCase(unittest.TestCase):
    """A test with a fresh database in a temporary folder (`self.s`, `self.tmp`) and shortcuts to insert jobs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)
        # processing refuses to start on a nearly full disk; a test must not depend on how full the machine running it happens to be
        patch = mock.patch.object(pipeline, "free_bytes", lambda path: 100 << 30)
        patch.start()
        self.addCleanup(patch.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def job(self, job_id, state, **fields):
        columns = dict(
            id=job_id,
            platform="douyin",
            source_id=job_id,
            url="https://www.douyin.com/video/" + job_id,
            country="CN",
            title="Tiêu đề " + job_id,
            first_seen=1,
            last_seen=1,
            state=state,
            updated=time.time(),
        )
        columns.update(fields)
        with self.s.transaction() as db:
            db.execute("INSERT INTO jobs(%s) VALUES (%s)" % (",".join(columns), ",".join("?" * len(columns))), list(columns.values()))

    def ready(self, job_id, **fields):
        """A rendered video waiting to be posted."""
        analysis = {"kind": "dialogue", "caption_vi": "Mô tả " + job_id, "hashtags": ["a", "b", "c"]}
        self.job(job_id, "ready", output_file="/d/%s.mp4" % job_id, output_hash="h", analysis=json.dumps(analysis), **fields)
