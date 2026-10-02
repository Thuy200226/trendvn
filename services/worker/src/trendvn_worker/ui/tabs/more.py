"""Thêm: accounts, sources, settings, phone notifications, the event log and the manual-import box."""

import json

from ..components import (
    PLAIN_INPUT,
    accordion,
    cell,
    chip,
    field,
    fieldset,
    number_input,
    select,
    switch_select,
    table,
    text_input,
)
from ..format import ago, escape as E, windows_text
from . import accounts
from ..labels import EVENT_LABELS, PLATFORM, STATE_LABELS, vi_reason


def sources(view):
    """One card per platform: when it was last scanned, what its jobs look like, what the collector last said."""
    d = view.d
    detail = d.get("discovery_detail") if isinstance(d.get("discovery_detail"), dict) else {}
    last_scan = {}
    for stream in d["streams"]:
        platform = stream["name"].split(":")[0]
        last_scan[platform] = max(last_scan.get(platform, 0), stream["last_scan"] or 0)
    cards = []
    for platform, (name, country) in PLATFORM.items():
        states = d["by_platform"].get(platform, {})
        info = detail.get(platform)
        text = json.dumps(info, ensure_ascii=False) if isinstance(info, dict) else (info or "")
        skipped = isinstance(info, str) and "IP" in info
        tone = "warn" if skipped else ("good" if last_scan.get(platform) else "mute")
        label = "Cần IP %s" % country if skipped else ("Đang thu thập" if last_scan.get(platform) else "Chưa quét")
        counts = (
            " ".join("<span>%s <b>%d</b></span>" % (E(STATE_LABELS.get(k, k)), n) for k, n in sorted(states.items())) or "Chưa có dữ liệu"
        )
        cards.append(
            '<div class="card src"><div class="row"><h3>%s</h3>%s</div><p class="muted">Quét gần nhất: <b>%s</b></p>'
            '<div class="mini">%s</div><small class="muted">%s</small><small>Trọng số ưu tiên: <b>%.2f</b></small></div>'
            % (E(name), chip(label, tone), ago(last_scan.get(platform), view.now), counts, E(text[:260]), d["weights"].get(platform, 1.0))
        )
    return '<div class="grid4">%s</div>' % "".join(cards)


def _automation_group(view):
    d, cfg = view.d, view.cfg
    return fieldset(
        "Tự động",
        "".join(
            (
                field("Xử lý video bằng Gemini", switch_select("processing_enabled", d["processing_enabled"], "Bật", "Tắt")),
                field(
                    "Tự đăng lên TikTok",
                    switch_select("publisher_enabled", d["publisher_enabled"], "Bật", "Tắt"),
                    "Luôn kiểm tra hash, trùng lặp và giới hạn ngày.",
                ),
                field(
                    "Duyệt tay trước khi đăng",
                    switch_select("require_approval", cfg["require_approval"], "Bật — chờ tôi duyệt", "Tắt — hoàn toàn tự động"),
                ),
                field(
                    "Lồng tiếng Việt cho video thuyết minh",
                    switch_select("voiceover_enabled", cfg["voiceover_enabled"], "Bật", "Tắt — chỉ Vietsub"),
                    "Hãy nghe thử giọng đọc trước khi bật.",
                ),
            )
        ),
    )


def _schedule_group(view):
    cfg = view.cfg
    visibility = (("public", "Mọi người (công khai)"), ("friends", "Bạn bè"), ("self", "Chỉ mình tôi (dùng để chạy thử an toàn)"))
    return fieldset(
        "Lịch đăng",
        "".join(
            (
                field("Số bài tối đa mỗi ngày", number_input("daily_limit", cfg["daily_limit"], 1, 10)),
                field("Giãn cách tối thiểu (giờ)", number_input("gap_hours", round(cfg["min_publish_gap"] / 3600, 2), 0, 24, "0.25")),
                field(
                    "Giờ vàng (giờ Việt Nam)",
                    text_input("post_windows", windows_text(cfg["post_windows"]), 'placeholder="11-14, 19-23" inputmode="text"'),
                    "Để trống nếu muốn đăng bất kỳ lúc nào.",
                ),
                field(
                    "Tài khoản TikTok mặc định",
                    text_input("target", cfg["target"], PLAIN_INPUT),
                    "Thêm tài khoản khác ở mục Tài khoản TikTok và chủ đề.",
                ),
                field("Chế độ hiển thị bài đăng", select("visibility", cfg["visibility"], visibility), "Áp dụng cho mọi bài sắp đăng."),
            )
        ),
        False,
    )


def _selection_group(view):
    cfg = view.cfg
    return fieldset(
        "Chọn video",
        "".join(
            (
                field(
                    "Video mới trong (ngày)", number_input("max_age_days", cfg["max_age_days"], 1, 60), "Chỉ lấy video được đăng gần đây."
                ),
                field("Độ dài tối đa (giây)", number_input("max_duration", cfg["max_duration"], 10, 600)),
                field("Tải tối đa mỗi lần quét", number_input("max_candidates_per_scan", cfg["max_candidates_per_scan"], 1, 10)),
                field("Hàng chờ tối đa", number_input("max_backlog", cfg["max_backlog"], 1, 20), "Đủ số này thì tạm ngừng tải thêm."),
                field("Độ chắc chắn tối thiểu của Gemini", number_input("audio_confidence", cfg["audio_confidence"], 0.5, 0.99, "0.01")),
            )
        ),
        False,
    )


def _threshold_group(view):
    min_views, min_likes = view.cfg["min_views"], view.cfg["min_likes"]
    return fieldset(
        "Ngưỡng thịnh hành",
        "".join(
            (
                field("Douyin: tim tối thiểu", number_input("likes_douyin", min_likes.get("douyin", 0), 0, 10**9)),
                field("Kuaishou: lượt xem tối thiểu", number_input("views_kuaishou", min_views.get("kuaishou", 0), 0, 10**10)),
                field("TikTok: lượt xem tối thiểu", number_input("views_tiktok", min_views.get("tiktok", 0), 0, 10**10)),
                field("Instagram: lượt xem tối thiểu", number_input("views_instagram", min_views.get("instagram", 0), 0, 10**10)),
                field("Douyin: lượt xem tối thiểu", number_input("views_douyin", min_views.get("douyin", 0), 0, 10**10)),
            )
        ),
        False,
    )


def _gemini_group(view):
    cfg = view.cfg
    return fieldset(
        "Gemini",
        "".join(
            (
                field("Giọng đọc", text_input("voice", cfg["voice"], PLAIN_INPUT), "Tên giọng Gemini, ví dụ Kore, Puck, Charon."),
                field(
                    "Hạn mức gọi Gemini / 24 giờ",
                    number_input("gemini_daily_limit", cfg["gemini_daily_limit"], 1, 500),
                    "Tăng nếu tài khoản Gemini của bạn cho phép.",
                ),
                field(
                    "Model phân tích",
                    text_input("model", cfg["model"], PLAIN_INPUT),
                    "Google có thể ngừng model cũ; hệ thống tự chuyển sang model mới hơn khi gặp lỗi 404.",
                ),
                field("Model giọng đọc", text_input("tts_model", cfg["tts_model"], PLAIN_INPUT)),
                field(
                    "Kiểu mô tả bài đăng",
                    select(
                        "caption_style",
                        cfg["caption_style"],
                        (("hook", "Giật tít, kích thích tò mò"), ("factual", "Điềm đạm, mô tả đúng nội dung")),
                    ),
                    "Giật tít vẫn bám đúng điều có trong video, không bịa sự kiện hay lời của người thật.",
                ),
            )
        ),
        False,
    )


def settings_form(view):
    groups = (_automation_group(view), _schedule_group(view), _selection_group(view), _threshold_group(view), _gemini_group(view))
    return (
        '<form method="post" action="/settings" class="settings stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="next" value="settings">%s'
        '<div class="btns"><button class="go">Lưu cài đặt</button></div></form>'
    ) % (view.csrf, "".join(groups))


def gemini_key_form(view):
    d = view.d
    audio = '<audio controls preload="none" src="/media/voice-sample"></audio>' if d.get("voice_sample") else ""
    return (
        '<form method="post" action="/setup" class="stack"><input type="hidden" name="csrf" value="%s">'
        '<p class="muted">Khóa được lưu trong <code>data/worker/gemini.key</code>, không gửi vào n8n hay nhật ký. %s</p>'
        '%s<div class="btns"><button class="go">Lưu khóa</button></div></form>'
        '<form method="post" action="/voice-test"><input type="hidden" name="csrf" value="%s"><div class="btns">'
        '<button class="ghost" title="Dùng 1 lượt gọi Gemini">🔊 Nghe thử giọng đọc</button></div></form>%s'
    ) % (
        view.csrf,
        "Đã có khóa." if d["gemini_configured"] else "Chưa có khóa.",
        field("Gemini API key (để trống để giữ khóa hiện tại)", '<input type="password" name="key" autocomplete="off">'),
        view.csrf,
        audio,
    )


def notify_form(view):
    telegram = field(
        "Bot token", '<input type="password" name="telegram_token" autocomplete="off" placeholder="để trống để giữ nguyên">'
    ) + field("Chat id", '<input name="telegram_chat" autocomplete="off" inputmode="text" placeholder="-100123456 hoặc @kenh">')
    return (
        '<p class="muted">Kênh đang dùng: <b>%s</b>. Thông báo gửi khi có video cần duyệt, đăng xong, lỗi hoặc bài chưa xác nhận.</p>'
        '<form method="post" action="/notify-save" class="stack"><input type="hidden" name="csrf" value="%s">%s%s%s'
        '<div class="btns"><button class="go">Lưu kênh thông báo</button></div></form>'
        '<div class="btns two"><form method="post" action="/notify-test"><input type="hidden" name="csrf" value="%s"><button class="ghost">Gửi tin thử</button></form>'
        '<form method="post" action="/notify-clear"><input type="hidden" name="csrf" value="%s"><button class="ghost">Xóa các kênh</button></form></div>'
    ) % (
        E(", ".join(view.d["notify_channels"]) or "chưa cấu hình"),
        view.csrf,
        fieldset("Telegram", telegram),
        fieldset(
            "Discord / Slack (webhook https)",
            field("Địa chỉ webhook", '<input type="password" name="webhook" autocomplete="off" placeholder="https://...">'),
            False,
        ),
        fieldset(
            "ntfy (https)",
            field("Địa chỉ chủ đề", '<input type="password" name="ntfy" autocomplete="off" placeholder="https://ntfy.sh/ten-rieng">'),
            False,
        ),
        view.csrf,
        view.csrf,
    )


def event_log(view):
    rows = [
        "<tr>%s%s%s%s</tr>"
        % (
            cell("Lúc", ago(e["at"], view.now)),
            cell("Sự kiện", E(EVENT_LABELS.get(e["event"], e["event"]))),
            cell("Video", E((e["title"] or "")[:70]), "t"),
            cell("Chi tiết", E(vi_reason(e["detail"] or "")[:120])),
        )
        for e in view.d["events"]
    ]
    return table(("Lúc", "Sự kiện", "Video", "Chi tiết"), rows, "Chưa có sự kiện.")


def manual_import(view):
    return (
        '<form method="post" action="/ingest-form" class="stack"><input type="hidden" name="csrf" value="%s">'
        '<textarea name="batch" rows="5" placeholder=\'{"platform":"douyin","stream":"hot_music","observed_at":0,"items":[]}\'></textarea>'
        '<div class="btns"><button class="ghost">Kiểm tra và nhập</button></div></form>'
    ) % view.csrf


def render(view):
    return "".join(
        (
            '<h2 class="desk">Nguồn, cài đặt, thông báo, nhật ký</h2>',
            accordion("accounts", "Tài khoản TikTok và chủ đề", accounts.render(view)),
            accordion("sources", "Nguồn thu thập", sources(view)),
            accordion("settings", "Cài đặt", settings_form(view) + '<h3 class="sub">Khóa Gemini và giọng đọc</h3>' + gemini_key_form(view)),
            accordion("notify", "Thông báo điện thoại", notify_form(view)),
            accordion("log", "Nhật ký", event_log(view)),
            accordion("advanced", "Nâng cao: nhập quan sát bằng tay", manual_import(view)),
        )
    )
