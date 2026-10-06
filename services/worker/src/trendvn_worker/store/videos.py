"""Videos found from a chat answer: ranking against the product, and the owner's explicit pick into the processing queue, pinned to
the account the owner chose."""

import json
import re
import time
import uuid

from ..domain.platforms import canonical_url, COUNTRIES
from ..domain.product_match import match_identity

MAX_RESULTS = 20


class VideosMixin:
    def videos_rank(self, mid, items):
        """The candidates an agent reported, as the chat shows them: each judged against the product, best first, different products last."""
        identity = self.chat_get(mid)["body"].get("identity", {})
        out = []
        for item in items[:40]:
            source_id = item.get("source_id")
            if not isinstance(source_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", source_id):
                continue
            candidate = {k: item.get(k) for k in ("source_id", "title", "platform", "media", "duration", "product_id")}
            try:
                candidate["url"] = canonical_url(item.get("platform", "tiktok"), item.get("url", ""))
            except (ValueError, KeyError, AttributeError, TypeError):
                continue  # one video the agent described badly is left out, not a reason to lose the others
            candidate["match"] = match_identity(identity, item.get("title", ""), str(item.get("product_id") or ""))
            out.append(candidate)
        return sorted(out, key=lambda i: i["match"]["score"], reverse=True)[:MAX_RESULTS]

    def _videos_message(self, mid):
        message = self.chat_get(mid)
        if message["kind"] != "videos" or message["state"] != "done":
            raise ValueError("Cần chọn video và xác nhận đã xem đúng sản phẩm")
        if (self.account(message["account"]) or {}).get("username") != message["body"].get("account_username"):
            raise ValueError("Tài khoản đã thay đổi từ lúc tìm kiếm; hãy tìm lại")
        return message

    def videos_select(self, mid, source_id, confirmed=False, platform=None):
        """Idempotent and pinned to its account. A video already used by another search or account is never reassigned or posted twice."""
        if not confirmed:
            raise ValueError("Cần chọn video và xác nhận đã xem đúng sản phẩm")
        message = self._videos_message(mid)
        body = message["body"]
        matches = [
            i
            for i in body.get("results", [])
            if i["source_id"] == source_id and (platform is None or i.get("platform", "tiktok") == platform)
        ]
        if len(matches) != 1:
            raise ValueError("Cần chọn đúng nguồn và video trong kết quả")
        item = matches[0]
        if item["match"]["level"] == "different":
            raise ValueError("Video thuộc sản phẩm khác; không thể chọn")
        sid = str(mid)
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM accounts WHERE id=?", (message["account"],)).fetchone():
                raise ValueError("Tài khoản đã bị xóa")
            row = db.execute("SELECT id,search_id FROM jobs WHERE url=?", (item["url"],)).fetchone()
            if row:
                if row["search_id"] != sid:
                    raise ValueError("Video đã có trong hệ thống; không chuyển sang tài khoản khác hoặc đăng trùng")
                return row["id"]
            jid, now = uuid.uuid4().hex, time.time()
            platform = item.get("platform") or "tiktok"
            if db.execute("SELECT 1 FROM jobs WHERE platform=? AND source_id=?", (platform, source_id)).fetchone():
                raise ValueError("Video đã có trong hệ thống (cùng mã, có thể khác tên kênh); không chọn lại")
            meta = {"product_reference": body.get("identity", {}), "search_username": body.get("account_username")}
            db.execute(
                "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated,meta,search_id,search_account) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid, platform, source_id, item["url"], COUNTRIES[platform], item.get("title") or "Video đã chọn", now, now,
                    "search_selected", "Bạn đã chọn; đang chờ tải", now, json.dumps(meta), sid, message["account"],
                ),
            )  # fmt: skip
        return jid

    def videos_media_ready(self, jid):
        """Claim a picked video for downloading: {'id','item','account'}. Only a video still waiting to be downloaded can be claimed. A pick
        whose answer is gone (older than the log keeps) or whose account changed can never be downloaded: it is rejected, not left waiting.
        """
        stale = False
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND state='search_selected'", (jid,)).fetchone()
            if not row:
                raise ValueError("Video đã được tải hoặc không còn chờ tải")
            try:
                message = self._videos_message(int(row["search_id"]))
                item = next(
                    i
                    for i in message["body"]["results"]
                    if i["source_id"] == row["source_id"] and i.get("platform", "tiktok") == row["platform"]
                )
            except (ValueError, StopIteration, KeyError):
                stale = True
                db.execute(
                    "UPDATE jobs SET state='rejected',reason=?,updated=? WHERE id=?",
                    ("Lượt chọn không còn dùng được (tin nhắn đã cũ hoặc tài khoản đã đổi); hãy tìm và chọn lại", time.time(), jid),
                )
            else:
                db.execute("UPDATE jobs SET state='candidate',updated=? WHERE id=?", (time.time(), jid))
        if stale:  # raised after the transaction closes, or the rejection would be rolled back with it
            raise ValueError("Lượt chọn này không còn dùng được; hãy tìm và chọn lại")
        return {"id": jid, "item": item, "account": row["search_account"]}

    def video_download_failed(self, jid, reason):
        """A download that failed puts the pick back to 'waiting', with the reason, so the owner can pick it again."""
        with self.transaction() as db:
            db.execute(
                "UPDATE jobs SET state='search_selected',reason=? WHERE id=? AND state='candidate' AND source_file IS NULL",
                (reason[:700], jid),
            )
