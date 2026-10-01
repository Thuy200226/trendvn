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
                value["detail"] = {**before, **value["detail"]}  # a partial run must not erase what other sources last reported
            db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", ("hb_" + component, json.dumps(value, ensure_ascii=False)[:8000]))
        if not ok:
            names = {"discovery": "Bộ thu thập", "publisher": "Trình đăng TikTok"}
            self.emit(
                "component",
                "🔌 %s cần chú ý: %s"
                % (names[component], detail if isinstance(detail, str) else json.dumps(detail, ensure_ascii=False)[:300]),
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
