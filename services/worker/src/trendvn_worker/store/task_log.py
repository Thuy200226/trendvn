"""Rows of the background tasks started from dashboard buttons."""

import json
import time
import uuid
from ..jsonsafe import loads


class TaskLogMixin:
    """Progress of background tasks, so a page reload never loses it."""

    # ------------------------------------------------------------------ background tasks (dashboard buttons)
    def task_create(self, kind, job_id=None):
        tid = uuid.uuid4().hex
        with self.transaction() as db:
            db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)", (tid, kind, job_id, "running", time.time(), None, "[]", "", ""))
        return tid

    def task_update(self, tid, steps=None, state=None, result=None, error=None):
        with self.transaction() as db:
            sets, vals = [], []
            if steps is not None:
                sets.append("steps=?")
                vals.append(json.dumps(steps, ensure_ascii=False))
            if state:
                sets.append("state=?")
                vals.append(state)
                sets.append("finished=?")
                vals.append(time.time() if state != "running" else None)
            if result is not None:
                sets.append("result=?")
                vals.append(result[:1500])
            if error is not None:
                sets.append("error=?")
                vals.append(error[:800])
            if sets:
                db.execute("UPDATE tasks SET %s WHERE id=?" % ",".join(sets), (*vals, tid))

    def tasks_recent(self, limit=8):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM tasks ORDER BY started DESC LIMIT ?", (limit,))]
        for r in rows:
            r["steps"] = loads(r["steps"], [])
        return rows

    def tasks_running(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,kind,job_id,started FROM tasks WHERE state='running'")]

    def tasks_reap(self):
        """After a restart nothing is really running: mark leftovers as interrupted so the buttons become usable again."""
        with self.transaction() as db:
            db.execute(
                "UPDATE tasks SET state='error',finished=?,error='Bị gián đoạn (worker khởi động lại)' WHERE state='running'",
                (time.time(),),
            )
            db.execute("DELETE FROM tasks WHERE started<?", (time.time() - 14 * 86400,))
