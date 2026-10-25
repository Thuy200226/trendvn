"""TikTok accounts the channel posts to: what each accepts, and the limits that may differ from the global defaults."""

import re

from . import topics
from .settings import validate_settings

MAX_ACCOUNTS = 10
ID_RX = re.compile(r"[a-z0-9][a-z0-9_-]{0,23}")
USERNAME_RX = re.compile(r"[A-Za-z0-9._]{2,40}")
OVERRIDES = ("daily_limit", "min_gap", "windows", "visibility")  # None = use the global setting
SETTING_OF = {"daily_limit": "daily_limit", "min_gap": "min_publish_gap", "windows": "post_windows", "visibility": "visibility"}


def account_flag(account_id):
    """' --account ID' for a command line, or '' for the default account (the command line's own default)."""
    return "" if account_id in (None, "", "main", True) else " --account " + str(account_id)


def clean_username(value):
    name = str(value or "").strip().lstrip("@")
    if not USERNAME_RX.fullmatch(name):
        raise ValueError("T\u00ean t\u00e0i kho\u1ea3n TikTok kh\u00f4ng h\u1ee3p l\u1ec7")
    return name


def slug(value):
    """An account id from free text: lower case letters, digits, '_' and '-'."""
    value = re.sub(r"[^a-z0-9_-]+", "-", str(value or "").strip().lower()).strip("-_")[:24]
    if not ID_RX.fullmatch(value):
        raise ValueError("M\u00e3 t\u00e0i kho\u1ea3n kh\u00f4ng h\u1ee3p l\u1ec7")
    return value


def validate_account(data, creating=False):
    """The fields of a create or update request, checked and cleaned. Updates may carry any subset of them."""
    if not isinstance(data, dict):
        raise ValueError("T\u00e0i kho\u1ea3n ph\u1ea3i l\u00e0 m\u1ed9t \u0111\u1ed1i t\u01b0\u1ee3ng")
    out = {}
    if creating or "username" in data:
        out["username"] = clean_username(data.get("username"))
    if "label" in data:
        out["label"] = str(data.get("label") or "").strip()[:40]
    if creating or "topics" in data:
        out["topics"] = topics.valid_topics(data.get("topics"))
    if "enabled" in data:
        if not isinstance(data["enabled"], bool):
            raise ValueError("enabled ph\u1ea3i l\u00e0 true ho\u1eb7c false")
        out["enabled"] = data["enabled"]
    for field in OVERRIDES:
        if field in data:
            value = data[field]
            out[field] = None if value is None else validate_settings({SETTING_OF[field]: value})[SETTING_OF[field]]
    return out


def effective(account, cfg):
    """The limits that apply to an account: its own override, else the global setting."""
    return {
        "daily_limit": account["daily_limit"] if account["daily_limit"] is not None else cfg["daily_limit"],
        "min_gap": account["min_gap"] if account["min_gap"] is not None else cfg["min_publish_gap"],
        "windows": account["windows"] if account["windows"] is not None else cfg["post_windows"],
        "visibility": account["visibility"] or cfg["visibility"],
    }


def accepts(account, topic):
    """Does the account take a video of this topic? Videos without a topic (made before topics existed) go anywhere."""
    return topic is None or topic in account["topics"]
