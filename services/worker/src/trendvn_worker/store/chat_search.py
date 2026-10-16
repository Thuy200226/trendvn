"""Claim one search answer per product, receiver and source; retries keep the same message and references."""

import json

from ..jsonsafe import loads
from .chat import BUSY_LIMIT


class ChatSearchMixin:
    def chat_find(self, account, body):
        """Return (id, start, previous): duplicate clicks reuse work; errors alone can be retried."""
        with self.transaction() as db:
            parent = db.execute("SELECT hidden FROM chat WHERE id=?", (body["product"],)).fetchone()
            if not parent or parent[0]:
                raise ValueError("Lượt tìm đã xóa khỏi lịch sử; hãy gửi yêu cầu mới")
            rows = db.execute(
                "SELECT * FROM chat WHERE hidden=0 AND kind='videos' AND account=? "
                "AND json_valid(body) AND json_extract(body,'$.product')=? "
                "AND json_extract(body,'$.source')=? AND json_extract(body,'$.account_username')=? "
                "ORDER BY (state IN ('pending','running')) DESC,id DESC LIMIT 1",
                (account, body["product"], body["source"], body["account_username"]),
            ).fetchone()
            if not rows:
                return self._insert(db, "bot", "videos", "running", account, body), True, None
            previous = dict(rows)
            if rows["state"] != "error":
                return rows["id"], False, previous
            if db.execute("SELECT count(*) FROM chat WHERE state IN ('pending','running')").fetchone()[0] >= BUSY_LIMIT:
                raise ValueError("Đang có việc chưa xong; đợi nó hoàn tất rồi gửi tiếp")
            old_body = loads(rows["body"], {})
            updated = old_body | body
            updated["results"] = old_body.get("results", [])
            updated.pop("error", None)
            db.execute("UPDATE chat SET state='running',body=? WHERE id=?", (json.dumps(updated, ensure_ascii=False), rows["id"]))
            return rows["id"], True, previous

    def chat_find_refused(self, mid, previous):
        """A refused start preserves the original error, including any candidate/job references."""
        with self.transaction() as db:
            if previous is None:
                db.execute("DELETE FROM chat WHERE id=? AND state='running'", (mid,))
            else:
                db.execute(
                    "UPDATE chat SET state=?,body=? WHERE id=? AND state='running'",
                    (previous["state"], previous["body"], mid),
                )

    def chat_find_results(self, mid, results):
        """A retry may add new candidates, but cannot lose media already referenced by a selected job."""
        with self.connect() as db:
            row = db.execute("SELECT body FROM chat WHERE id=?", (mid,)).fetchone()
            referenced = {(r[0], r[1]) for r in db.execute("SELECT platform,source_id FROM jobs WHERE search_id=?", (str(mid),))}
        seen = {(i.get("platform", "tiktok"), i["source_id"]) for i in results}
        kept = (
            [
                i
                for i in loads(row[0], {}).get("results", [])
                if (i.get("platform", "tiktok"), i["source_id"]) in referenced and (i.get("platform", "tiktok"), i["source_id"]) not in seen
            ]
            if row
            else []
        )
        return results + kept
