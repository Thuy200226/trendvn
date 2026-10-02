"""Optional outbound notifications: Telegram bot, ntfy topic, or a generic webhook (Discord and Slack compatible).

Nothing is sent until you configure a channel on the dashboard or in .env. Secrets are stored in data/worker/notify.json
(mode 0600) and are never returned by the API or written to logs. Sending failures never affect the queue.
"""

import ipaddress
import json
import os
import re
import socket
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

# minimum seconds between two messages with the same (kind, key); 0 means always send
THROTTLE = {
    "component": 12 * 3600,
    "publish_failed": 3 * 3600,
    "error": 3600,
    "urgent": 6 * 3600,
    "review": 0,
    "approval": 0,
    "published": 0,
    "summary": 0,
    "test": 0,
}
ENV_KEYS = {
    "telegram_token": "TRENDVN_TELEGRAM_TOKEN",
    "telegram_chat": "TRENDVN_TELEGRAM_CHAT",
    "webhook": "TRENDVN_NOTIFY_WEBHOOK",
    "ntfy": "TRENDVN_NTFY_URL",
}


INTERNAL_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")
DNS_NAME = re.compile(r"(?:[a-z0-9-]+\.)+[a-z][a-z0-9-]*")  # at least one dot and a last label that starts with a letter: never an IP


def _safe_https(url):
    """An https URL on a public DNS name: not an IP address (in any notation), not localhost or an internal suffix, no user-info."""
    u = urlsplit(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not host or u.username or u.password or len(url) > 400 or any(c.isspace() or c == "\\" for c in url):
        raise ValueError("Cần địa chỉ https hợp lệ")
    if not DNS_NAME.fullmatch(host) or host == "localhost" or host.endswith(INTERNAL_SUFFIXES):
        raise ValueError("Không dùng địa chỉ nội bộ")
    return url


def _public_only(url):
    """At send time: the name must resolve to public addresses only (a name pointing at 127.0.0.1 or 169.254.x.x is refused)."""
    host = urlsplit(url).hostname
    for info in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(info[4][0].split("%")[0]).is_global:
            raise ValueError("Địa chỉ nội bộ")


def validate(cfg):
    out = {}
    if cfg.get("telegram_token") or cfg.get("telegram_chat"):
        if not re.fullmatch(r"\d{6,12}:[A-Za-z0-9_-]{30,60}", cfg.get("telegram_token", "")):
            raise ValueError("Telegram token không đúng định dạng")
        if not re.fullmatch(r"-?\d{4,20}|@[A-Za-z0-9_]{4,40}", cfg.get("telegram_chat", "")):
            raise ValueError("Telegram chat id không đúng định dạng")
        out["telegram_token"], out["telegram_chat"] = cfg["telegram_token"], cfg["telegram_chat"]
    for key in ("webhook", "ntfy"):
        if cfg.get(key):
            out[key] = _safe_https(cfg[key])
    return out


def load_config(root):
    cfg = {k: os.environ.get(v, "").strip() for k, v in ENV_KEYS.items()}
    f = Path(root) / "notify.json"
    if f.exists():
        try:
            cfg.update({k: v for k, v in json.loads(f.read_text()).items() if k in ENV_KEYS and isinstance(v, str) and v})
        except Exception:
            pass
    try:
        return validate({k: v for k, v in cfg.items() if v})
    except ValueError:
        return {}


def save_config(root, cfg):
    clean = validate(cfg)
    f = Path(root) / "notify.json"
    f.write_text(json.dumps(clean))
    f.chmod(0o600)
    return sorted(channels(clean))


def clear_config(root):
    f = Path(root) / "notify.json"
    if f.exists():
        f.unlink()


def channels(cfg):
    names = []
    if cfg.get("telegram_token") and cfg.get("telegram_chat"):
        names.append("Telegram")
    if cfg.get("webhook"):
        names.append("Webhook (Discord/Slack)")
    if cfg.get("ntfy"):
        names.append("ntfy")
    return names


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A webhook that answers 302 could point us at an internal address: a redirect counts as a failure instead of being followed."""

    def redirect_request(self, *args, **kwargs):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _post(url, data, headers, check_host=False):
    if check_host:
        _public_only(url)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with _OPENER.open(req, timeout=15) as r:
        return 200 <= r.status < 300


def send(cfg, text):
    """Deliver to every configured channel; returns {channel: ok}. Never raises, never echoes secrets."""
    text = text[:3500]
    results = {}
    if cfg.get("telegram_token") and cfg.get("telegram_chat"):
        try:
            results["Telegram"] = _post(
                "https://api.telegram.org/bot%s/sendMessage" % cfg["telegram_token"],
                json.dumps({"chat_id": cfg["telegram_chat"], "text": text, "disable_web_page_preview": True}).encode(),
                {"Content-Type": "application/json"},
            )
        except Exception:
            results["Telegram"] = False
    if cfg.get("webhook"):
        try:
            results["Webhook (Discord/Slack)"] = _post(
                cfg["webhook"],
                # allowed_mentions: a message can never ping @everyone or a role, whatever text it carries
                json.dumps({"content": text[:1900], "text": text, "allowed_mentions": {"parse": []}}).encode(),
                {"Content-Type": "application/json"},
                check_host=True,
            )
        except Exception:
            results["Webhook (Discord/Slack)"] = False
    if cfg.get("ntfy"):
        try:
            results["ntfy"] = _post(cfg["ntfy"], text.encode("utf-8"), {"Title": "TrendVN"}, check_host=True)
        except Exception:
            results["ntfy"] = False
    return results


class Notifier:
    """Callable hooked into Store.emit; throttles repeats so a broken source cannot flood your phone."""

    def __init__(self, store):
        self.store = store

    def config(self):
        return load_config(self.store.root)

    def __call__(self, kind, text, key=""):
        cfg = self.config()
        if not channels(cfg):
            return
        window = THROTTLE.get(kind, 3600)
        now = time.time()
        if window:
            with self.store.connect() as db:
                if db.execute("SELECT 1 FROM notif_log WHERE kind=? AND key=? AND at>?", (kind, key, now - window)).fetchone():
                    return
        send(cfg, text)
        with self.store.transaction() as db:
            db.execute("INSERT INTO notif_log VALUES (?,?,?)", (kind, key, now))
            db.execute("DELETE FROM notif_log WHERE at<?", (now - 7 * 86400,))
