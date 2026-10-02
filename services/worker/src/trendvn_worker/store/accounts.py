"""TikTok accounts: which topics each takes, its own limits, and routing a video to the right one."""

import json
import time

from ..domain import topics as topic_menu
from ..domain.accounts import MAX_ACCOUNTS, accepts, slug, validate_account

COLUMNS = "id,username,label,topics,enabled,daily_limit,min_gap,windows,visibility,created"


def _row(row):
    account = dict(row)
    account["topics"] = json.loads(account["topics"])
    account["enabled"] = bool(account["enabled"])
    account["windows"] = json.loads(account["windows"]) if account["windows"] else None
    return account


class AccountsMixin:
    """The `accounts` table. The first enabled account is the default one (the single account of 1.0 - 1.3 is `main`)."""

    def accounts(self, enabled_only=False):
        with self.connect() as db:
            return self._accounts_in(db, enabled_only)

    @staticmethod
    def _accounts_in(db, enabled_only=False):
        sql = "SELECT %s FROM accounts %s ORDER BY created,id" % (COLUMNS, "WHERE enabled=1" if enabled_only else "")
        return [_row(r) for r in db.execute(sql)]

    def account(self, account_id):
        with self.connect() as db:
            row = db.execute("SELECT %s FROM accounts WHERE id=?" % COLUMNS, (account_id,)).fetchone()
        return _row(row) if row else None

    def account_by_username(self, username):
        with self.connect() as db:
            row = db.execute("SELECT %s FROM accounts WHERE username=?" % COLUMNS, (username,)).fetchone()
        return _row(row) if row else None

    def default_account(self):
        """The account used when nothing else decides: the first enabled one, else the first one."""
        accounts = self.accounts()
        return next((a for a in accounts if a["enabled"]), accounts[0] if accounts else None)

    def wanted_topics(self):
        """Topics at least one enabled account takes, in menu order: what the collector should look for."""
        taken = {t for a in self.accounts(enabled_only=True) for t in a["topics"]}
        return [t for t in topic_menu.TOPIC_IDS if t in taken]

    def accounts_for_topic(self, topic, enabled_only=True):
        return [a for a in self.accounts(enabled_only) if accepts(a, topic)]

    def add_account(self, data):
        clean = validate_account(data, creating=True)
        account_id = slug(data.get("id") or clean["username"])
        with self.transaction() as db:
            if db.execute("SELECT count(*) FROM accounts").fetchone()[0] >= MAX_ACCOUNTS:
                raise ValueError("Tối đa %d tài khoản" % MAX_ACCOUNTS)
            if db.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
                raise ValueError("Mã tài khoản đã có: " + account_id)
            if db.execute("SELECT 1 FROM accounts WHERE username=?", (clean["username"],)).fetchone():
                raise ValueError("Tài khoản @%s đã có" % clean["username"])
            db.execute(
                "INSERT INTO accounts(id,username,label,topics,enabled,created) VALUES (?,?,?,?,?,?)",
                (
                    account_id,
                    clean["username"],
                    clean.get("label") or clean["username"],
                    json.dumps(clean["topics"]),
                    1 if clean.get("enabled", True) else 0,
                    time.time(),
                ),
            )
            for field in ("daily_limit", "min_gap", "visibility"):
                if clean.get(field) is not None:
                    db.execute("UPDATE accounts SET %s=? WHERE id=?" % field, (clean[field], account_id))
            if clean.get("windows") is not None:
                db.execute("UPDATE accounts SET windows=? WHERE id=?", (json.dumps(clean["windows"]), account_id))
            self.event(db, "", "account_added", account_id)
        return self.account(account_id)

    def update_account(self, account_id, patch):
        clean = validate_account(patch)
        if not clean:
            raise ValueError("Không có gì để đổi")
        with self.transaction() as db:
            if not db.execute("SELECT 1 FROM accounts WHERE id=?", (account_id,)).fetchone():
                raise ValueError("Không có tài khoản này")
            if (
                "username" in clean
                and db.execute("SELECT 1 FROM accounts WHERE username=? AND id<>?", (clean["username"], account_id)).fetchone()
            ):
                raise ValueError("Tài khoản @%s đã có" % clean["username"])
            if clean.get("enabled") is False:
                others = db.execute("SELECT count(*) FROM accounts WHERE enabled=1 AND id<>?", (account_id,)).fetchone()[0]
                if not others:
                    raise ValueError("Phải còn ít nhất một tài khoản đang bật")
            for field, value in clean.items():
                if field == "topics":
                    value = json.dumps(value)
                elif field == "windows" and value is not None:
                    value = json.dumps(value)
                elif field == "enabled":
                    value = 1 if value else 0
                elif field == "label":
                    value = (
                        value
                        or clean.get("username")
                        or db.execute("SELECT username FROM accounts WHERE id=?", (account_id,)).fetchone()[0]
                    )
                db.execute("UPDATE accounts SET %s=? WHERE id=?" % field, (value, account_id))
            self.event(db, "", "account_updated", "%s: %s" % (account_id, ", ".join(sorted(clean))))
        return self.account(account_id)

    def delete_account(self, account_id):
        """Remove an account. Its past posts keep the username they were posted with. The last account cannot go, and neither can one
        with a post in flight or waiting for confirmation."""
        with self.transaction() as db:
            row = db.execute("SELECT username FROM accounts WHERE id=?", (account_id,)).fetchone()
            if not row:
                raise ValueError("Không có tài khoản này")
            if db.execute("SELECT count(*) FROM accounts").fetchone()[0] <= 1:
                raise ValueError("Phải giữ lại ít nhất một tài khoản")
            if db.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('publishing','publish_unknown') AND COALESCE(account,'main')=?", (account_id,)
            ).fetchone()[0]:
                raise ValueError("Tài khoản đang có bài đăng chưa xác nhận")
            if not db.execute("SELECT count(*) FROM accounts WHERE enabled=1 AND id<>?", (account_id,)).fetchone()[0]:
                raise ValueError("Phải còn ít nhất một tài khoản đang bật")
            db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            self.event(db, "", "account_deleted", account_id)

    def set_default_username(self, username):
        """The 'Tài khoản TikTok đích' setting of 1.3: renames the default account (kept so single-account setups and the API work as before)."""
        account = self.default_account()
        if account is None:
            return self.add_account({"username": username, "id": "main", "topics": list(topic_menu.DEFAULT_TOPICS)})
        return self.update_account(account["id"], {"username": username})
