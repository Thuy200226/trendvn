"""The product chat log: what the owner said and what the system answered, each answer with a state the page polls while it works."""

import json
import time

from ..jsonsafe import loads

KINDS = ("say", "product", "videos", "link", "login", "note")
STATES = ("pending", "running", "done", "error")
KEEP = 300  # messages kept; older ones go (a long chat is not a record anyone needs, and attachments never are kept at all)
REQUEST_KEEP = 30 * 86400  # deleting history must not make a retried request a new Gemini call
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
        db.execute(
            "DELETE FROM chat WHERE id<=? AND state IN ('done','error') "
            "AND (request_key IS NULL OR created<?) "
            "AND CAST(id AS TEXT) NOT IN (SELECT search_id FROM jobs WHERE search_id IS NOT NULL) "
            "AND id NOT IN (SELECT json_extract(body,'$.product') FROM chat WHERE state IN ('pending','running') AND json_valid(body) AND json_type(body,'$.product')='integer')",
            (mid - KEEP, time.time() - REQUEST_KEEP),
        )
        return mid

    def chat_add(self, role, kind, body, state="done", account=None):
        with self.transaction() as db:
            return self._insert(db, role, kind, state, account, body)

    def chat_ask(self, account, said, kind, body, request_key=None):
        """The owner's message and the answer now being worked on, added together: when the answer cannot start, the message is not kept
        either. Returns the answer's id."""
        with self.transaction() as db:
            user = self._insert(db, "user", "say", "done", account, said)
            mid = self._insert(db, "bot", kind, "running", account, body | {"user_message": user})
            if request_key:
                db.execute("UPDATE chat SET request_key=? WHERE id=?", (request_key, mid))
            return mid

    def chat_request(self, key):
        with self.connect() as db:
            row = db.execute("SELECT id,account FROM chat WHERE request_key=?", (key,)).fetchone()
        return dict(row) if row else None

    def chat_forget(self, mid):
        """Hide a completed search turn, retaining internal references needed by selected videos."""
        with self.transaction() as db:
            rows = {r["id"]: dict(r) | {"body": loads(r["body"], {})} for r in db.execute("SELECT * FROM chat")}
            row = rows.get(mid)
            if not row or row["role"] != "bot":
                raise ValueError("Chỉ xóa được lượt đã hoàn tất")
            product = row["body"].get("product") if row["kind"] == "videos" else None
            parent = rows.get(product) if isinstance(product, int) else None
            legacy_root = parent["body"].get("turn_id", product) if parent and parent["kind"] == "product" else mid
            root = row["body"].get("turn_id", legacy_root)
            if not isinstance(root, int) or root not in rows:
                root = mid
            turn = {root}
            turn.update(i for i, r in rows.items() if r["role"] == "bot" and r["body"].get("turn_id") == root)
            turn.update(
                i
                for i, r in rows.items()
                if r["kind"] == "videos" and isinstance(r["body"].get("product"), int) and r["body"]["product"] in turn
            )
            if any(rows[i]["state"] not in ("done", "error") for i in turn):
                raise ValueError("Chỉ xóa được lượt đã hoàn tất")
            user = rows[root]["body"].get("user_message")
            if isinstance(user, int) and not isinstance(user, bool) and user in rows and rows[user]["role"] == "user":
                turn.add(user)
            db.executemany("UPDATE chat SET hidden=1 WHERE id=?", [(i,) for i in turn])
        return {"removed": mid}

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
            rows = db.execute("SELECT * FROM chat WHERE hidden=0 ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) | {"body": loads(r["body"], {})} for r in reversed(rows)]

    def chat_product(self, account=None):
        """The product the chat is about now: the latest finished 'product' answer that names one (an answer that is only video links
        names none), or None."""
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM chat WHERE hidden=0 AND kind='product' AND state='done' "
                + ("AND (account=? OR account IS NULL) " if account else "")
                + "ORDER BY id DESC LIMIT 10",
                (account,) if account else (),
            ).fetchall()
        for row in rows:
            body = loads(row["body"], {})
            identity = body.get("identity") or {}
            if identity.get("name") or identity.get("product_id"):
                return dict(row) | {"body": body}
        return None

    def chat_delete(self, mid):
        """Drop one message (an answer that never started)."""
        with self.transaction() as db:
            db.execute("DELETE FROM chat WHERE id=?", (mid,))

    def chat_clear(self, before=None):
        """Forget the finished part of the history (only what is older than `before`, a Unix time, when given); returns how many messages
        went. What is still being worked on stays, and so does what it needs: the answer a waiting video was picked from, and the product
        a running search was started for (a failed search offers to try again on it). Picked or downloaded videos, saved links and sign-in
        records are not history and are never touched."""
        with self.transaction() as db:
            keep = {
                int(r[0])
                for r in db.execute("SELECT search_id FROM jobs WHERE search_id IS NOT NULL AND state IN ('search_selected','candidate')")
                if str(r[0]).isascii() and str(r[0]).isdigit()
            }
            for row in db.execute("SELECT body FROM chat WHERE state IN ('pending','running')"):
                product = loads(row["body"], {}).get("product")
                if isinstance(product, int) and not isinstance(product, bool):
                    keep.add(product)
            rows = db.execute(
                "SELECT id,request_key FROM chat WHERE hidden=0 AND state IN ('done','error') AND created<?",
                (float("inf") if before is None else before,),
            )
            selected = list(rows)
            ids = [r[0] for r in selected]
            db.executemany("UPDATE chat SET hidden=1 WHERE id=?", [(r[0],) for r in selected if r[1] or r[0] in keep])
            db.executemany("DELETE FROM chat WHERE id=?", [(r[0],) for r in selected if not r[1] and r[0] not in keep])
        return len(ids)

    def chat_recover(self):
        """After a restart nothing is really running: whatever was unfinished becomes an error the owner can retry."""
        with self.transaction() as db:
            db.execute(
                "UPDATE chat SET state='error',body=CASE WHEN json_valid(body) THEN json_set(body,'$.error',?) ELSE json_object('error',?) END "
                "WHERE state IN ('pending','running')",
                ("Bị gián đoạn; hãy gửi lại",) * 2,
            )
            db.execute(
                "UPDATE jobs SET state='search_selected',reason='Tải bị ngắt; hãy chọn lại để thử' WHERE search_id IS NOT NULL AND state='candidate' AND source_file IS NULL"
            )
