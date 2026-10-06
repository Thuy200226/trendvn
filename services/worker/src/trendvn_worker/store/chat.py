"""The product chat log: what the owner said and what the system answered, each answer with a state the page polls while it works."""

import json
import time

from ..jsonsafe import loads

KINDS = ("say", "product", "videos", "link", "note")
STATES = ("pending", "running", "done", "error")
KEEP = 300  # messages kept; older ones go (a long chat is not a record anyone needs, and attachments never are kept at all)
BUSY_LIMIT = 3  # answers that may be unfinished at once: a sign-in window or a slow video call must not pile up work behind it


class ChatMixin:
    def _insert(self, db, role, kind, state, account, body):
        if role not in ("user", "bot") or kind not in KINDS or state not in STATES:
            raise ValueError("Tin nhắn không hợp lệ")
        if (
            state in ("pending", "running")
            and db.execute("SELECT count(*) FROM chat WHERE state IN ('pending','running')").fetchone()[0] >= BUSY_LIMIT
        ):
            raise ValueError("Đang có việc chưa xong; đợi nó hoàn tất rồi gửi tiếp")
        mid = db.execute(
            "INSERT INTO chat(created,role,kind,state,account,body) VALUES(?,?,?,?,?,?)",
            (time.time(), role, kind, state, account, json.dumps(body, ensure_ascii=False)),
        ).lastrowid
        db.execute("DELETE FROM chat WHERE id<=?", (mid - KEEP,))
        return mid

    def chat_add(self, role, kind, body, state="done", account=None):
        with self.transaction() as db:
            return self._insert(db, role, kind, state, account, body)

    def chat_ask(self, account, said, kind, body):
        """The owner's message and the answer now being worked on, added together: when the answer cannot start, the message is not kept
        either. Returns the answer's id."""
        with self.transaction() as db:
            self._insert(db, "user", "say", "done", account, said)
            return self._insert(db, "bot", kind, "running", account, body)

    def chat_get(self, mid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM chat WHERE id=?", (mid,)).fetchone()
        if not row:
            raise ValueError("Không có tin nhắn này")
        return dict(row) | {"body": loads(row["body"], {})}

    def chat_set(self, mid, state=None, **fields):
        """Move a message to a new state and/or merge fields into its body."""
        if state is not None and state not in STATES:
            raise ValueError("Trạng thái không hợp lệ")
        with self.transaction() as db:
            row = db.execute("SELECT body FROM chat WHERE id=?", (mid,)).fetchone()
            if not row:
                raise ValueError("Không có tin nhắn này")
            body = loads(row["body"], {}) | fields
            db.execute("UPDATE chat SET state=COALESCE(?,state),body=? WHERE id=?", (state, json.dumps(body, ensure_ascii=False), mid))

    def chat_thread(self, limit=60):
        """The latest messages, oldest first."""
        with self.connect() as db:
            rows = db.execute("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) | {"body": loads(r["body"], {})} for r in reversed(rows)]

    def chat_product(self):
        """The product the chat is about now: the latest finished 'product' answer, or None."""
        with self.connect() as db:
            row = db.execute("SELECT * FROM chat WHERE kind='product' AND state='done' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(row) | {"body": loads(row["body"], {})} if row else None

    def chat_recover(self):
        """After a restart nothing is really running: whatever was unfinished becomes an error the owner can retry."""
        with self.transaction() as db:
            db.execute(
                "UPDATE chat SET state='error',body=json_set(body,'$.error','Bị gián đoạn; hãy gửi lại') WHERE state IN ('pending','running')"
            )
            db.execute(
                "UPDATE jobs SET state='search_selected',reason='Tải bị ngắt; hãy chọn lại để thử' WHERE search_id IS NOT NULL AND state='candidate' AND source_file IS NULL"
            )
