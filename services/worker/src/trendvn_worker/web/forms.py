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
TEXTS = ("target", "voice", "model", "tts_model", "visibility")


def parse_windows(text):
    """'11-14, 19-23' -> [[11, 14], [19, 23]]."""
    text = text.strip()
    if not text:
        return []
    windows = []
    for part in re.split(r"[,;]", text):
        match = re.fullmatch(r"\s*(\d{1,2})\s*-\s*(\d{1,2})\s*", part)
        if not match:
            raise ValueError("Giờ vàng nhập dạng 11-14, 19-23")
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
            raise ValueError("Giãn cách nhập số giờ, ví dụ 3 hoặc 2.5")
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
        return Redirect(err="Chưa nhập khóa", anchor="#settings")
    if len(key) < 20 or len(key) > 300 or any(c.isspace() for c in key):
        raise ValueError("Khóa không đúng định dạng")
    path = app.store.root / "gemini.key"
    path.write_text(key)
    path.chmod(0o600)
    return Redirect("key", anchor="#settings")


def save_settings(app, form):
    app.store.update_settings(settings_patch(form))
    back = form.get("next", ["settings"])[0]
    return Redirect("saved", anchor="#" + (back if back in SETTINGS_TABS else "settings"))


def start_task(app, form):
    kind = form.get("kind", [""])[0]
    job = form.get("id", [""])[0] or None
    if job and not re.fullmatch(r"[0-9a-f]{32}", job):
        raise ValueError("Mã video không hợp lệ")
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
        raise ValueError("Chưa có kênh thông báo nào")
    results = notify.send(config, "✅ TrendVN: tin thử. Thông báo hoạt động.")
    if not any(results.values()):
        raise ValueError("Gửi không thành công; kiểm tra lại token, chat id hoặc địa chỉ")
    return Redirect("notify_sent", anchor="#notify")


def test_voice(app, form):
    if not app.process_lock.acquire(blocking=False):
        raise ValueError("Worker đang bận, thử lại sau")
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
}

# what the page says after each successful form (shown once, as a green banner)
FLASH = {
    "started": "Đã bắt đầu. Tiến độ hiện ngay trên trang, không cần tải lại.",
    "caption_saved": "Đã lưu mô tả và hashtag.",
    "caption_reset": "Đã trả về mô tả do hệ thống soạn.",
    "saved": "Đã lưu cài đặt.",
    "key": "Đã lưu khóa Gemini.",
    "decided": "Đã ghi nhận quyết định của bạn.",
    "resolved": "Đã cập nhật trạng thái bài đăng.",
    "notify": "Đã lưu kênh thông báo.",
    "notify_cleared": "Đã xóa kênh thông báo.",
    "notify_sent": "Đã gửi tin thử. Hãy kiểm tra điện thoại.",
    "ingested": "Đã nhập dữ liệu quan sát.",
    "voice": "Đã tạo giọng đọc thử. Kéo xuống mục Cài đặt để nghe.",
}
