"""Commission links the owner confirmed: one per account and product, and the creator marks they carry (what later links are compared to)."""

import json
import time

from ..jsonsafe import loads


class CommissionMixin:
    def commission_known(self, account):
        """The creator marks of every link this account's owner confirmed: [{parameter: value}, ...]."""
        with self.connect() as db:
            rows = db.execute("SELECT markers FROM commission_links WHERE account=? AND tracked=1", (account,)).fetchall()
        return [loads(r["markers"], {}) for r in rows]

    def commission_get(self, account, product_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM commission_links WHERE account=? AND product_id=?", (account, product_id)).fetchone()
        return dict(row) | {"markers": loads(row["markers"], {})} if row else None

    def commission_save(self, account, found):
        """Keep the link the owner confirmed (replacing an older one for the same product on the same account)."""
        if not self.account(account) or not found.get("product_id"):
            raise ValueError("Thiếu tài khoản hoặc mã sản phẩm")
        with self.transaction() as db:
            db.execute(
                "INSERT OR REPLACE INTO commission_links(account,product_id,created,url,title,markers,tracked) VALUES(?,?,?,?,?,?,?)",
                (
                    account, found["product_id"], time.time(), found["input"][:600], (found.get("title") or "")[:300],
                    json.dumps(found.get("markers") or {}), 1 if found.get("tracked") else 0,
                ),
            )  # fmt: skip

    def commission_list(self, account):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM commission_links WHERE account=? ORDER BY created DESC LIMIT 50", (account,)).fetchall()
        return [dict(r) | {"markers": loads(r["markers"], {})} for r in rows]
