"""Heartbeats: is the collector / publisher alive and fine?"""

import json
import time
from ..jsonsafe import loads

HEARTBEAT_MAX_AGE = 30 * 3600
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
        with self.transaction() as db:
            prev = db.execute("SELECT value FROM settings WHERE key=?", ("hb_" + component,)).fetchone()
            before = self._stored_detail(prev["value"]) if prev else None
            if isinstance(value["detail"], dict) and isinstance(before, dict):
                merged = {**before, **value["detail"]}  # a partial run must not erase what other sources last reported
                if isinstance(before.get("login"), dict) and isinstance(value["detail"].get("login"), dict):
                    merged["login"] = {**before["login"], **value["detail"]["login"]}
                value["detail"] = bounded(merged)
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_" + component, json.dumps(value, ensure_ascii=False)))
        if not ok:
            names = {"discovery": "Bộ thu thập", "publisher": "Trình đăng TikTok"}
            text = detail.get("text") if isinstance(detail, dict) and detail.get("text") else detail
            self.emit(
                "component",
                "🔌 %s cần chú ý: %s" % (names[component], text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)[:300]),
                component,
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
        if not self.account(account_id):
            raise ValueError("Không có tài khoản này")
        with self.transaction() as db:
            row = db.execute("SELECT value FROM settings WHERE key='hb_publisher'").fetchone()
            value = json.loads(row["value"]) if row else {"at": time.time(), "ok": True, "detail": None}
            detail = value["detail"] if isinstance(value.get("detail"), dict) else {}
            login = dict(detail.get("login") or {})
            login[account_id] = bool(ok)
            detail["login"] = login
            enabled = {r["id"] for r in db.execute("SELECT id FROM accounts WHERE enabled=1")}
            # healthy unless an account that is switched on is known to be signed out (a disabled or deleted one's old flag is history)
            value.update(detail=detail, at=time.time(), ok=all(state for key, state in login.items() if key in enabled))
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_publisher", json.dumps(value, ensure_ascii=False)))
