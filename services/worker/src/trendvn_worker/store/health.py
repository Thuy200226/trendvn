"""Heartbeats: is the collector / publisher alive and fine?"""

import json
import time

HEARTBEAT_MAX_AGE = 30 * 3600


class HealthMixin:
    """Component health reported by the browser agent."""

    def heartbeat(self, component, ok, detail=None):
        if component not in ("discovery", "publisher"):
            raise ValueError("Unknown component")
        value = {"at": time.time(), "ok": bool(ok), "detail": detail if isinstance(detail, (dict, list, str)) else None}
        with self.transaction() as db:
            prev = db.execute("SELECT value FROM settings WHERE key=?", ("hb_" + component,)).fetchone()
            before = json.loads(prev["value"]).get("detail") if prev else None
            if isinstance(value["detail"], dict) and isinstance(before, dict):
                merged = {**before, **value["detail"]}  # a partial run must not erase what other sources last reported
                if isinstance(before.get("login"), dict) and isinstance(value["detail"].get("login"), dict):
                    merged["login"] = {**before["login"], **value["detail"]["login"]}
                value["detail"] = merged
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_" + component, json.dumps(value, ensure_ascii=False)[:8000]))
        if not ok:
            names = {"discovery": "Bộ thu thập", "publisher": "Trình đăng TikTok"}
            text = detail.get("text") if isinstance(detail, dict) and detail.get("text") else detail
            self.emit(
                "component",
                "🔌 %s cần chú ý: %s" % (names[component], text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)[:300]),
                component,
            )

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
            value.update(detail=detail, at=time.time(), ok=all(login.values()))
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_publisher", json.dumps(value, ensure_ascii=False)))
