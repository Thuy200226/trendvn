"""One-use deletion grants bind a confirmed action to the exact published URL and verified account."""

import re
import time
import uuid

POST = re.compile(r"https://www\.tiktok\.com/@([A-Za-z0-9._-]{1,50})/video/(\d{6,25})")


class PostDeletionsMixin:
    def delete_post_begin(self, jid, url, account):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND state='published'", (jid,)).fetchone()
            if not row or row["publish_url"] != url or (row["account"] or "main") != account:
                raise ValueError("Bài đăng hoặc tài khoản đã thay đổi; hãy tải lại trang")
            match = POST.fullmatch(url)
            who = db.execute("SELECT username FROM accounts WHERE id=?", (account,)).fetchone()
            if not match or not who or match[1].casefold() != who[0].casefold() or (row["target"] or "").casefold() != who[0].casefold():
                raise ValueError("Chưa xác minh được bài đăng thuộc tài khoản này")
            old = db.execute("SELECT state FROM post_deletions WHERE job_id=?", (jid,)).fetchone()
            if old and old[0] != "failed":
                raise ValueError("Bài đã xóa, đang xóa hoặc cần kiểm tra; không gửi lặp")
            token = uuid.uuid4().hex
            db.execute(
                "INSERT OR REPLACE INTO post_deletions VALUES(?,?,?,?,?,?,?,?)",
                (jid, token, "pending", account, who[0], url, "Bạn đã xác nhận xóa", time.time()),
            )
            self.event(db, jid, "delete_requested", url)
        return {"job_id": jid, "grant": token}

    def delete_post_claim(self, jid, grant):
        with self.transaction() as db:
            row = db.execute(
                "SELECT d.*,j.state job_state,j.account job_account,j.publish_url,j.target,a.username current_username FROM post_deletions d JOIN jobs j ON j.id=d.job_id JOIN accounts a ON a.id=d.account WHERE d.job_id=? AND d.grant_token=?",
                (jid, grant),
            ).fetchone()
            if not row or row["state"] != "pending" or time.time() - row["updated"] > 300:
                raise ValueError("Yêu cầu xóa đã nhận hoặc đã hết hạn")
            if (
                row["job_state"] != "published"
                or (row["job_account"] or "main") != row["account"]
                or row["url"] != row["publish_url"]
                or row["username"] != row["current_username"]
                or row["username"] != row["target"]
            ):
                raise ValueError("Danh tính bài đăng đã thay đổi")
            db.execute("UPDATE post_deletions SET state='deleting',updated=? WHERE job_id=?", (time.time(), jid))
        return {"id": jid, "url": row["url"], "account": row["account"], "username": row["username"]}

    def delete_post_finish(self, jid, grant, outcome, reason=""):
        if outcome not in ("deleted", "failed", "unknown"):
            raise ValueError("Kết quả xóa không hợp lệ")
        with self.transaction() as db:
            changed = db.execute(
                "UPDATE post_deletions SET state=?,reason=?,updated=? WHERE job_id=? AND grant_token=? AND state IN ('pending','deleting')",
                (outcome, reason[:700], time.time(), jid, grant),
            ).rowcount
            if changed != 1:
                raise ValueError("Yêu cầu xóa không còn hiệu lực")
            self.event(db, jid, "post_" + outcome, reason)

    def delete_post_cancel(self, jid, grant):
        with self.transaction() as db:
            db.execute(
                "UPDATE post_deletions SET state='failed',reason='Chưa bắt đầu được; hãy thử lại',updated=? WHERE job_id=? AND grant_token=? AND state='pending'",
                (time.time(), jid, grant),
            )

    def delete_post_checked_present(self, jid, url, account):
        """The owner explicitly checked the uncertain post still exists; never implies deletion."""
        self._delete_post_checked(jid, url, account, "present")

    def delete_post_checked_deleted(self, jid, url, account):
        """Reconcile an uncertain result only after the owner explicitly verifies deletion."""
        self._delete_post_checked(jid, url, account, "deleted")

    def _delete_post_checked(self, jid, url, account, outcome):
        with self.transaction() as db:
            row = db.execute(
                "SELECT d.*,j.publish_url,j.target,j.state job_state,j.account job_account,a.username current_username FROM post_deletions d JOIN jobs j ON j.id=d.job_id JOIN accounts a ON a.id=d.account WHERE d.job_id=?",
                (jid,),
            ).fetchone()
            if (
                not row
                or row["state"] != "unknown"
                or row["job_state"] != "published"
                or (row["job_account"] or "main") != account
                or row["url"] != url
                or row["publish_url"] != url
                or row["account"] != account
                or row["username"] != row["current_username"]
                or row["username"] != row["target"]
            ):
                raise ValueError("Bài hoặc trạng thái đã thay đổi; hãy tải lại trang")
            reason = "Chủ đã kiểm tra: bài đã xóa trên TikTok" if outcome == "deleted" else "Chủ đã kiểm tra: bài vẫn còn trên TikTok"
            db.execute(
                "UPDATE post_deletions SET state=?,reason=?,updated=? WHERE job_id=?",
                ("deleted" if outcome == "deleted" else "failed", reason, time.time(), jid),
            )
            if outcome == "deleted":
                self.event(db, jid, "delete_checked_deleted", url)
            else:
                self.event(db, jid, "delete_checked_present", url)

    def delete_post_recover(self):
        with self.transaction() as db:
            db.execute(
                "UPDATE post_deletions SET state='unknown',reason='Bị gián đoạn; cần kiểm tra trên TikTok, không tự xóa lại' WHERE state IN ('pending','deleting')"
            )
