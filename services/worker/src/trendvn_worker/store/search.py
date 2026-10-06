"""Account-scoped search sessions and explicit selection into the existing processing queue."""

import json
import re
import time
import uuid

from ..domain.platforms import canonical_url, COUNTRIES
from ..domain.product_search import match_identity
from ..jsonsafe import loads


class SearchMixin:
    def search_create(self, account_id, reference, mode="videos"):
        if mode not in ("videos", "products") or not self.account(account_id):
            raise ValueError("Tài khoản hoặc kiểu tìm kiếm không hợp lệ")
        sid = uuid.uuid4().hex
        with self.transaction() as db:
            if db.execute("SELECT count(*) FROM searches WHERE state IN ('pending','running')").fetchone()[0] >= 3:
                raise ValueError("Đã có tìm kiếm đang chờ; đợi hoàn tất rồi thử lại")
            db.execute(
                "INSERT INTO searches(id,account,mode,created,state,reference,identity,results,error,note,account_username) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sid,
                    account_id,
                    mode,
                    time.time(),
                    "pending",
                    json.dumps(reference),
                    "{}",
                    "[]",
                    "",
                    "",
                    self.account(account_id)["username"],
                ),
            )
        return sid

    def search_get(self, sid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM searches WHERE id=?", (sid,)).fetchone()
        if not row:
            raise ValueError("Không có yêu cầu tìm kiếm này")
        row = dict(row)
        for key, fallback in (("reference", {}), ("identity", {}), ("results", [])):
            row[key] = loads(row[key], fallback)
        return row

    def searches_recent(self, limit=8):
        with self.connect() as db:
            ids = [r[0] for r in db.execute("SELECT id FROM searches ORDER BY created DESC LIMIT ?", (limit,))]
        return [self.search_get(sid) | {"reference": {}} for sid in ids]

    def search_update(self, sid, state, identity=None, results=None, error="", note=""):
        if state not in ("running", "done", "error"):
            raise ValueError("Trạng thái tìm kiếm không hợp lệ")
        with self.transaction() as db:
            db.execute(
                "UPDATE searches SET state=?,identity=COALESCE(?,identity),results=COALESCE(?,results),error=?,note=? WHERE id=?",
                (
                    state,
                    json.dumps(identity, ensure_ascii=False) if identity is not None else None,
                    json.dumps(results, ensure_ascii=False) if results is not None else None,
                    error[:700],
                    note[:1000],
                    sid,
                ),
            )
            if state != "running":
                db.execute("UPDATE searches SET reference='{}' WHERE id=?", (sid,))  # do not retain private documents after recognition

    def search_rank(self, sid, items):
        identity = self.search_get(sid)["identity"]
        out = []
        for item in items[:40]:
            url = canonical_url(item.get("platform", "tiktok"), item.get("url", ""))
            if not isinstance(item.get("source_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", item["source_id"]):
                continue
            candidate = {k: item.get(k) for k in ("source_id", "title", "platform", "media", "duration", "product_id", "commission")}
            candidate.update(url=url, match=match_identity(identity, item.get("title", ""), str(item.get("product_id") or "")))
            out.append(candidate)
        return sorted(out, key=lambda i: i["match"]["score"], reverse=True)[:20]

    def search_retry(self, sid, name="", source="tiktok"):
        from ..domain.search_queries import explicit, query_plan

        if source not in ("tiktok", "douyin", "auto"):
            raise ValueError("Nguồn tìm kiếm không hợp lệ")
        search = self.search_get(sid)
        if search["state"] not in ("done", "error") or search["mode"] != "videos":
            raise ValueError("Đợi tìm kiếm hoàn tất rồi thử lại")
        if (self.account(search["account"]) or {}).get("username") != search["account_username"]:
            raise ValueError("Tài khoản đã thay đổi; hãy tạo tìm kiếm mới")
        identity = explicit(name) if name else search["identity"]
        if not identity or not identity.get("query"):
            raise ValueError("Nhập tên/model để tìm lại")
        identity = dict(identity, queries=query_plan(identity), source=source)
        # New session keeps previously selected videos tied to their original results.
        new = self.search_create(search["account"], {"reuse_identity": True, "source": source}, "videos")
        self.search_update(new, "running", identity=identity)
        return new

    def search_select(self, sid, source_id, confirmed=False, platform=None):
        """Selection is idempotent and pinned to its account. It never reassigns a video already used by another search/account."""
        search = self.search_get(sid)
        if search["state"] != "done" or not confirmed or search["mode"] != "videos":
            raise ValueError("Cần chọn video và xác nhận đã xem đúng sản phẩm")
        if (self.account(search["account"]) or {}).get("username") != search["account_username"]:
            raise ValueError("Tài khoản đã thay đổi từ lúc tìm kiếm; hãy tìm lại")
        matches = [
            i for i in search["results"] if i["source_id"] == source_id and (platform is None or i.get("platform", "tiktok") == platform)
        ]
        if len(matches) != 1:
            raise ValueError("Cần chọn đúng nguồn và video trong kết quả")
        item = matches[0]
        if not item or item["match"]["level"] == "different":
            raise ValueError("Video không thuộc kết quả hoặc chưa khớp model sản phẩm")
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM accounts WHERE id=?", (search["account"],)).fetchone():
                raise ValueError("Tài khoản đã bị xóa")
            row = db.execute("SELECT id,search_id FROM jobs WHERE url=?", (item["url"],)).fetchone()
            if row:
                if row["search_id"] != sid:
                    raise ValueError("Video đã có trong hệ thống; không chuyển sang tài khoản khác hoặc đăng trùng")
                return row["id"]
            jid, now = uuid.uuid4().hex, time.time()
            db.execute(
                "INSERT INTO jobs(id,platform,source_id,url,country,title,first_seen,last_seen,state,reason,updated,meta,search_id,search_account) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    jid,
                    item.get("platform") or "tiktok",
                    source_id,
                    item["url"],
                    COUNTRIES[item.get("platform") or "tiktok"],
                    item.get("title") or "Video đã chọn",
                    now,
                    now,
                    "search_selected",
                    "Bạn đã chọn; đang chờ tải",
                    now,
                    json.dumps({"product_reference": search["identity"], "search_username": search["account_username"]}),
                    sid,
                    search["account"],
                ),
            )
        return jid

    def search_media_ready(self, jid):
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND state='search_selected'", (jid,)).fetchone()
            if not row:
                raise ValueError("Video đã được tải hoặc không còn chờ tải")
            search = self.search_get(row["search_id"])
            if (self.account(search["account"]) or {}).get("username") != search["account_username"]:
                raise ValueError("Tài khoản đã thay đổi; không tải video vào tài khoản mới")
            item = next(
                i for i in search["results"] if i["source_id"] == row["source_id"] and i.get("platform", "tiktok") == row["platform"]
            )
            db.execute("UPDATE jobs SET state='candidate',updated=? WHERE id=?", (time.time(), jid))
        return {"id": jid, "item": item, "account": row["search_account"]}

    def search_recover(self):
        with self.transaction() as db:
            db.execute(
                "UPDATE searches SET state='error',reference='{}',error='Tìm kiếm bị gián đoạn; hãy tìm lại' WHERE state IN ('pending','running')"
            )
            db.execute(
                "UPDATE jobs SET state='search_selected',reason='Tải bị ngắt; hãy chọn lại để thử' WHERE search_id IS NOT NULL AND state='candidate' AND source_file IS NULL"
            )
