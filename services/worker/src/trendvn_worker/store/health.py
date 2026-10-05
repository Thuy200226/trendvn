"""Heartbeats: is the collector / publisher alive and fine?"""

import json
import time
from ..domain.accounts import account_flag
from ..jsonsafe import loads

HEARTBEAT_MAX_AGE = 7 * 3600  # the schedule runs every 3 hours: two runs missed in a row means it is off, not just late
HEARTBEAT_MAX_CHARS = 6000  # a heartbeat is a status line, not a log; the agent's detail is cut to this before it is stored


def bounded(detail):
    """`detail` as it will be stored: only dict/list/str survive, and an oversize one is replaced by a truncated text (cutting the JSON
    itself in the middle would leave a settings row that cannot be read back)."""
    if not isinstance(detail, (dict, list, str)):
        return None
    text = json.dumps(detail, ensure_ascii=False)
    if len(text) <= HEARTBEAT_MAX_CHARS:
        return detail
    return {"text": text[:1500] + "…", "truncated": True}


class HealthMixin:
    """Component health reported by the browser agent."""

    def heartbeat(self, component, ok, detail=None):
        if component not in ("discovery", "publisher"):
            raise ValueError("Unknown component")
        value = {"at": time.time(), "ok": bool(ok), "detail": bounded(detail)}
        signed_out = []
        with self.transaction() as db:
            prev = db.execute("SELECT value FROM settings WHERE key=?", ("hb_" + component,)).fetchone()
            before = self._stored_detail(prev["value"]) if prev else None
            if isinstance(value["detail"], dict) and isinstance(before, dict):
                merged = {**before, **value["detail"]}  # a partial run must not erase what other sources last reported
                if isinstance(before.get("login"), dict) and isinstance(value["detail"].get("login"), dict):
                    merged["login"] = self._merged_login(before["login"], value["detail"]["login"])
                value["detail"] = bounded(merged)
            if component == "publisher" and isinstance(value["detail"], dict) and isinstance(value["detail"].get("login"), dict):
                new_login = value["detail"]["login"]
                old_login = before.get("login") if isinstance(before, dict) and isinstance(before.get("login"), dict) else {}
                signed_out = [a for a, state in new_login.items() if state is False and old_login.get(a) is not False]
                enabled = {r["id"] for r in db.execute("SELECT id FROM accounts WHERE enabled=1")}
                value["ok"] = value["ok"] and all(state for key, state in new_login.items() if key in enabled)
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_" + component, json.dumps(value, ensure_ascii=False)))
        for account_id in signed_out:
            self._announce_sign_out(account_id)
        if not ok:
            names = {"discovery": "Bộ thu thập", "publisher": "Trình đăng TikTok"}
            text = detail.get("text") if isinstance(detail, dict) and detail.get("text") else detail
            self.emit(
                "component",
                "🔌 %s cần chú ý: %s" % (names[component], text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)[:300]),
                component,
            )

    def set_key_rejected(self, rejected):
        """Google refused the Gemini key: the dashboard says so until a call goes through or a new key is saved."""
        with self.transaction() as db:
            if rejected:
                db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("gemini_key_rejected", "true"))
            else:
                db.execute("DELETE FROM settings WHERE key='gemini_key_rejected'")

    def key_accepted(self):
        """A Gemini call went through, or a new key was saved: the key is no longer called rejected. Cheap when it never was."""
        with self.connect() as db:
            rejected = db.execute("SELECT 1 FROM settings WHERE key='gemini_key_rejected'").fetchone()
        if rejected:
            self.set_key_rejected(False)

    @staticmethod
    def _merged_login(before, new):
        """The sign-in flags after a heartbeat. The heartbeat's check only sees a cookie, which a session TikTok has ended still carries:
        it can report an account signed out, but only a real sign-in (the login command, or a post that got past the sign-in page) can
        say it is signed in again."""
        merged = dict(before)
        for account_id, state in new.items():
            if state is False or merged.get(account_id) is not False:
                merged[account_id] = state
        return merged

    def _announce_sign_out(self, account_id):
        account = self.account(account_id)
        if account:
            self.emit(
                "urgent",
                "🔑 TikTok @%s chưa đăng nhập hoặc đã bị đăng xuất. Lịch tạm bỏ qua tài khoản này; các tài khoản khác vẫn đăng. Đăng nhập: ./trendvn tiktok login%s"
                % (account["username"], account_flag(account_id)),
                "login:" + account_id,
            )

    @staticmethod
    def _stored_detail(raw):
        value = loads(raw)
        return value.get("detail") if isinstance(value, dict) else None

    def component_state(self, component, cfg=None):
        cfg = cfg or self.settings()
        hb = cfg.get("hb_" + component)
        if not hb:
            return "not_connected"
        if time.time() - hb["at"] > HEARTBEAT_MAX_AGE:
            return "stale"
        return "connected" if hb["ok"] else "error"

    @staticmethod
    def login_map(cfg):
        """{account id: True/False} as last reported by the browser agent; an account it never reported on is simply absent (unknown)."""
        detail = (cfg.get("hb_publisher") or {}).get("detail")
        login = detail.get("login") if isinstance(detail, dict) else None
        return login if isinstance(login, dict) else {}

    def set_account_login(self, account_id, ok):
        """The agent (or the `tiktok login` command) found the browser signed in, or not, to one account."""
        account = self.account(account_id)
        if not account:
            raise ValueError("Không có tài khoản này")
        with self.transaction() as db:
            row = db.execute("SELECT value FROM settings WHERE key='hb_publisher'").fetchone()
            value = json.loads(row["value"]) if row else {"at": time.time(), "ok": True, "detail": None}
            detail = value["detail"] if isinstance(value.get("detail"), dict) else {}
            login = dict(detail.get("login") or {})
            newly_signed_out = not ok and login.get(account_id) is not False  # every tick reports the same logout: tell the owner once
            login[account_id] = bool(ok)
            detail["login"] = login
            enabled = {r["id"] for r in db.execute("SELECT id FROM accounts WHERE enabled=1")}
            # healthy unless an account that is switched on is known to be signed out (a disabled or deleted one's old flag is history)
            value.update(detail=detail, at=time.time(), ok=all(state for key, state in login.items() if key in enabled))
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_publisher", json.dumps(value, ensure_ascii=False)))
        if newly_signed_out:
            self._announce_sign_out(account_id)
