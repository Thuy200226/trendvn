"""Dashboard form handlers. Each takes the app and the parsed form and returns a Redirect (where to go, with which message)."""

import json
import re
from collections import namedtuple

from .. import notify
from ..ai.prompts import VOICE_SAMPLE
from ..ai.tts import tts
from ..domain.platforms import PLATFORMS
from ..tasks import TaskBusy

Redirect = namedtuple("Redirect", "key err anchor", defaults=(None, None, ""))

SETTINGS_TABS = ("home", "publish", "attention", "queue", "posted", "more", "settings")
SWITCHES = ("processing_enabled", "publisher_enabled", "require_approval", "voiceover_enabled")
NUMBERS = ("daily_limit", "max_age_days", "max_duration", "max_candidates_per_scan", "max_backlog", "gemini_daily_limit")
TEXTS = ("target", "voice", "model", "tts_model", "visibility", "caption_style", "voiceover_scope", "voice_mode", "hard_sub_mask")


def parse_windows(text):
    """'11-14, 19-23' -> [[11, 14], [19, 23]]."""
    text = text.strip()
    if not text:
        return []
    windows = []
    for part in re.split(r"[,;]", text):
        match = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", part)
        if not match:
            raise ValueError("Gi\u1edd v\u00e0ng nh\u1eadp d\u1ea1ng 11-14, 19-23")
        windows.append([int(match.group(1)), int(match.group(2))])
    return windows


def settings_patch(form):
    """Translate the dashboard form into validated settings (validation itself lives in domain.settings.validate_settings)."""

    def field(key):
        return form.get(key, [""])[0].strip()

    patch = {}
    for key in SWITCHES:
        if key in form:
            patch[key] = field(key) == "true"
    for key in NUMBERS:
        if field(key):
            patch[key] = float(field(key)) if re.fullmatch(r"\d{1,9}(\.\d+)?", field(key)) else -1
    if field("gap_hours"):
        if not re.fullmatch(r"\d{1,3}(\.\d{1,2})?", field("gap_hours")):
            raise ValueError("Gi\u00e3n c\u00e1ch nh\u1eadp s\u1ed1 gi\u1edd, v\u00ed d\u1ee5 3 ho\u1eb7c 2.5")
        patch["min_publish_gap"] = round(float(field("gap_hours")) * 3600)
    if field("audio_confidence"):
        patch["audio_confidence"] = float(field("audio_confidence")) if re.fullmatch(r"\d(\.\d{1,3})?", field("audio_confidence")) else -1
    if "post_windows" in form:
        patch["post_windows"] = parse_windows(field("post_windows"))
    for key in TEXTS:
        if field(key):
            patch[key] = field(key)
    views = {p: int(field("views_" + p)) for p in PLATFORMS if re.fullmatch(r"\d+", field("views_" + p))}
    if views:
        patch["min_views"] = views
    if re.fullmatch(r"\d+", field("likes_douyin")):
        patch["min_likes"] = {"douyin": int(field("likes_douyin"))}
    return patch


def save_gemini_key(app, form):
    key = form.get("key", [""])[0].strip()
    if not key:
        return Redirect(err="Ch\u01b0a nh\u1eadp kh\u00f3a", anchor="#settings")
    if len(key) < 20 or len(key) > 300 or any(c.isspace() for c in key):
        raise ValueError("Kh\u00f3a kh\u00f4ng \u0111\u00fang \u0111\u1ecbnh d\u1ea1ng")
    path = app.store.root / "gemini.key"
    path.write_text(key)
    path.chmod(0o600)
    app.store.key_accepted()  # a new key: the old rejection no longer applies (a wrong one is found out by the next call)
    return Redirect("key", anchor="#settings")


def save_settings(app, form):
    app.store.update_settings(settings_patch(form))
    back = form.get("next", ["settings"])[0]
    return Redirect("saved", anchor="#" + (back if back in SETTINGS_TABS else "settings"))


def _optional_int(value):
    """Blank = 'use the global setting' (None); digits = the number; anything else is passed on as -1 for the validator to refuse."""
    if not value:
        return None
    return int(value) if re.fullmatch(r"\d{1,9}", value) else -1


def _account_data(form):
    """The account fields a dashboard form carries, ready for the store's validation. Blank limits mean 'use the global setting'."""

    def field(key):
        return form.get(key, [""])[0].strip()

    data = {"topics": form.get("topic", []), "label": field("label"), "daily_limit": _optional_int(field("daily_limit"))}
    gap = field("gap_hours")
    if gap and not re.fullmatch(r"\d{1,3}(\.\d{1,2})?", gap):
        raise ValueError("Gi\u00e3n c\u00e1ch nh\u1eadp s\u1ed1 gi\u1edd, v\u00ed d\u1ee5 3 ho\u1eb7c 2.5")
    data["min_gap"] = round(float(gap) * 3600) if gap else None
    data["windows"] = parse_windows(field("post_windows")) if field("post_windows") else None
    data["visibility"] = field("visibility") or None
    if field("enabled") in ("true", "false"):  # anything else leaves the account as it is
        data["enabled"] = field("enabled") == "true"
    return data


def account_add(app, form):
    data = _account_data(form)
    data["username"] = form.get("username", [""])[0]
    app.store.add_account({k: v for k, v in data.items() if v is not None and v != ""})
    return Redirect("account_added", anchor="#accounts")


def account_save(app, form):
    app.store.update_account(form["id"][0], _account_data(form))
    return Redirect("account_saved", anchor="#accounts")


def account_delete(app, form):
    app.store.delete_account(form["id"][0])
    return Redirect("account_deleted", anchor="#accounts")


def start_task(app, form):
    kind = form.get("kind", [""])[0]
    job = form.get("id", [""])[0] or None
    if job and not re.fullmatch(r"[0-9a-f]{32}", job):
        raise ValueError("M\u00e3 video kh\u00f4ng h\u1ee3p l\u1ec7")
    caption = form.get("caption", [None])[0]
    if kind in ("publish", "dryrun") and job and caption is not None:
        app.store.set_caption(job, caption)  # what you see in the box is what gets posted, even if you did not press Save first
    back = form.get("next", [""])[0]  # the tab that has the button, so the progress shows where you pressed it
    if back not in ("home", "queue", "publish", "posted"):
        back = "publish" if kind in ("publish", "dryrun") else "posted" if kind == "stats" else "queue" if kind == "process" else "home"
    try:
        app.tasks.start(kind, job)
    except TaskBusy as busy:
        return Redirect(err=str(busy), anchor="#" + back)
    return Redirect("started", anchor="#" + back)


def edit_caption(app, form):
    job = form["id"][0]
    if form.get("action", ["save"])[0] == "reset":
        app.store.reset_caption(job)
        return Redirect("caption_reset", anchor="#publish")
    app.store.set_caption(job, form.get("caption", [""])[0])
    return Redirect("caption_saved", anchor="#publish")


def decide(app, form):
    app.store.decide(form["id"][0], form["action"][0])
    return Redirect("decided", anchor="#attention")


def resolve_unknown(app, form):
    app.store.resolve_unknown(form["id"][0], form["outcome"][0])
    return Redirect("resolved", anchor="#attention")


def ingest_batch(app, form):
    app.store.ingest(json.loads(form.get("batch", ["{}"])[0]))
    return Redirect("ingested", anchor="#queue")


def save_notify(app, form):
    config_file = app.store.root / "notify.json"
    config = json.loads(config_file.read_text()) if config_file.exists() else {}
    for key in ("telegram_token", "telegram_chat", "webhook", "ntfy"):
        value = form.get(key, [""])[0].strip()
        if value:
            config[key] = value
    notify.save_config(app.store.root, config)
    return Redirect("notify", anchor="#notify")


def clear_notify(app, form):
    notify.clear_config(app.store.root)
    return Redirect("notify_cleared", anchor="#notify")


def test_notify(app, form):
    config = notify.load_config(app.store.root)
    if not notify.channels(config):
        raise ValueError("Ch\u01b0a c\u00f3 k\u00eanh th\u00f4ng b\u00e1o n\u00e0o")
    results = notify.send(config, "✅ TrendVN: tin th\u1eed. Th\u00f4ng b\u00e1o ho\u1ea1t \u0111\u1ed9ng.")
    if not any(results.values()):
        raise ValueError("G\u1eedi kh\u00f4ng th\u00e0nh c\u00f4ng; ki\u1ec3m tra l\u1ea1i token, chat id ho\u1eb7c \u0111\u1ecba ch\u1ec9")
    return Redirect("notify_sent", anchor="#notify")


def test_voice(app, form):
    if not app.process_lock.acquire(blocking=False):
        raise ValueError("Worker \u0111ang b\u1eadn, th\u1eed l\u1ea1i sau")
    try:
        (app.store.root / "exports").mkdir(exist_ok=True)
        tts(app.store, app.store.settings(), VOICE_SAMPLE, app.store.root / "exports" / "voice_sample.wav")
    finally:
        app.process_lock.release()
    return Redirect("voice", anchor="#settings")


FORMS = {
    "/setup": save_gemini_key,
    "/settings": save_settings,
    "/decide": decide,
    "/resolve": resolve_unknown,
    "/ingest-form": ingest_batch,
    "/notify-save": save_notify,
    "/notify-clear": clear_notify,
    "/notify-test": test_notify,
    "/voice-test": test_voice,
    "/task": start_task,
    "/caption": edit_caption,
    "/account-add": account_add,
    "/account-save": account_save,
    "/account-delete": account_delete,
}

# what the page says after each successful form (shown once, as a green banner)
FLASH = {
    "started": "\u0110\u00e3 b\u1eaft \u0111\u1ea7u. Ti\u1ebfn \u0111\u1ed9 hi\u1ec7n ngay tr\u00ean trang, kh\u00f4ng c\u1ea7n t\u1ea3i l\u1ea1i.",
    "caption_saved": "\u0110\u00e3 l\u01b0u m\u00f4 t\u1ea3 v\u00e0 hashtag.",
    "caption_reset": "\u0110\u00e3 tr\u1ea3 v\u1ec1 m\u00f4 t\u1ea3 do h\u1ec7 th\u1ed1ng so\u1ea1n.",
    "saved": "\u0110\u00e3 l\u01b0u c\u00e0i \u0111\u1eb7t.",
    "key": "\u0110\u00e3 l\u01b0u kh\u00f3a Gemini.",
    "decided": "\u0110\u00e3 ghi nh\u1eadn quy\u1ebft \u0111\u1ecbnh c\u1ee7a b\u1ea1n.",
    "resolved": "\u0110\u00e3 c\u1eadp nh\u1eadt tr\u1ea1ng th\u00e1i b\u00e0i \u0111\u0103ng.",
    "notify": "\u0110\u00e3 l\u01b0u k\u00eanh th\u00f4ng b\u00e1o.",
    "notify_cleared": "\u0110\u00e3 x\u00f3a k\u00eanh th\u00f4ng b\u00e1o.",
    "notify_sent": "\u0110\u00e3 g\u1eedi tin th\u1eed. H\u00e3y ki\u1ec3m tra \u0111i\u1ec7n tho\u1ea1i.",
    "ingested": "\u0110\u00e3 nh\u1eadp d\u1eef li\u1ec7u quan s\u00e1t.",
    "voice": "\u0110\u00e3 t\u1ea1o gi\u1ecdng \u0111\u1ecdc th\u1eed. K\u00e9o xu\u1ed1ng m\u1ee5c C\u00e0i \u0111\u1eb7t \u0111\u1ec3 nghe.",
    "account_added": "\u0110\u00e3 th\u00eam t\u00e0i kho\u1ea3n. \u0110\u0103ng nh\u1eadp TikTok cho t\u00e0i kho\u1ea3n n\u00e0y b\u1eb1ng l\u1ec7nh hi\u1ec7n trong th\u1ebb c\u1ee7a n\u00f3.",
    "account_saved": "\u0110\u00e3 l\u01b0u t\u00e0i kho\u1ea3n.",
    "account_deleted": "\u0110\u00e3 x\u00f3a t\u00e0i kho\u1ea3n.",
}
