"""Tổng quan: state of the automation, the main buttons, the two switches, health, numbers and the setup checklist."""

from ..components import chip, component_chip, quick_switch, task_panel
from ..format import ago, escape as E, num, windows_text


def _accounts_text(d):
    """'@a' for one account, '3 tài khoản (@a, @b, @c)' for several."""
    names = ["@" + a["username"] for a in d["accounts"] if a["enabled"]]
    return names[0] if len(names) == 1 else "%d tài khoản (%s)" % (len(names), ", ".join(names))


def banner(view):
    if view.d["processing_enabled"] and view.d["publisher_enabled"] and not view.attention:
        return '<div class="banner good"><b>Đang tự động hoàn toàn.</b> Thu thập, xử lý và đăng chạy theo lịch.</div>'
    detail = "Có %d việc cần bạn xem ở tab Cần xem." % view.attention if view.attention else "Hoàn tất danh sách thiết lập để bật tự động."
    return '<div class="banner warn"><b>Chưa tự động hoàn toàn.</b> %s</div>' % detail


def control(view):
    """The 'start now' buttons. They are an addition: the n8n schedule keeps running on its own."""
    hint = (
        "Thu thập video mới → xử lý (Vietsub/lồng tiếng) → sẵn sàng đăng. "
        if view.d["processing_enabled"]
        else 'Xử lý video đang TẮT nên nút này chỉ thu thập; bật công tắc "Xử lý video" để đi trọn vòng. '
    )
    return (
        '<div class="card stack" id="control"><h2>Điều khiển</h2>%s<p class="hint">%sLịch tự động vẫn chạy song song như cũ.</p>'
        '<div class="btngrid">%s%s</div>%s</div>'
    ) % (
        view.action("update", "▶ Bắt đầu: cập nhật &amp; chuẩn bị đăng", "go xl", view.busy_browser or view.busy_process, "home"),
        E(hint),
        view.action("collect", "🔎 Thu thập video mới", "ghost", view.busy_browser, "queue"),
        view.action("process", "⚙️ Xử lý video chờ (%d)" % view.waiting, "ghost", view.busy_process, "queue"),
        task_panel(view.tasks, view.now),
    )


def switches(view):
    """Processing and auto-post, one tap each (the auto-post switch doubles as the emergency stop)."""
    d, cfg = view.d, view.cfg
    visibility = {"public": "công khai", "friends": "bạn bè", "self": "chỉ mình tôi"}.get(cfg["visibility"], cfg["visibility"])
    return '<div class="quick">%s%s</div>' % (
        quick_switch(
            view.csrf,
            "processing_enabled",
            "Xử lý video",
            d["processing_enabled"],
            "ĐANG BẬT",
            "ĐANG TẮT",
            confirm="Bật xử lý video? Video sẽ được gửi tới Google Gemini để phân tích.",
        ),
        quick_switch(
            view.csrf,
            "publisher_enabled",
            "Tự đăng TikTok",
            d["publisher_enabled"],
            "ĐANG BẬT · chạm để dừng",
            "ĐANG TẮT",
            danger=True,
            confirm="Bật tự đăng? Hệ thống sẽ tự đăng lên %s theo lịch (tối đa %d bài/ngày, chế độ %s)."
            % (_accounts_text(d), d["daily_limit"], visibility),
        ),
    )


def health(view):
    """Three rows: collector, publisher, golden hour."""
    d = view.d

    def row(label, state_html):
        return '<div class="pill"><span>%s</span>%s</div>' % (E(label), state_html)

    window = chip("Đang mở" if d["in_window"] else "Mở lúc " + (d["next_window"] or "—"), "good" if d["in_window"] else "mute")
    rows = (
        row("Thu thập video", component_chip(d["discovery"])) + row("Đăng TikTok", component_chip(d["publisher"])) + row("Giờ vàng", window)
    )
    return '<div class="card pills"><h3>Tình trạng</h3>%s</div>' % rows


def numbers(view):
    d = view.d
    total_views = sum(p["views"] or 0 for p in d["performance"])
    tiles = (
        ("Đăng hôm nay", "%d / %d" % (d["published_today"], d["daily_limit"])),
        ("Chờ xử lý", view.waiting),
        ("Sẵn sàng đăng", len(view.ready)),
        ("Cần xem", view.attention),
        ("Tổng đã đăng", view.counts.get("published", 0)),
        ("Lượt xem bài đã đăng", num(total_views)),
    )
    return '<div class="kpis">%s</div>' % "".join('<div class="kpi"><small>%s</small><b>%s</b></div>' % (E(a), E(str(b))) for a, b in tiles)


def schedule(view):
    cfg = view.cfg
    last_scan = view.d.get("discovery_at")
    return (
        '<div class="card stack"><h2>Lịch tự động</h2><ul class="plain"><li><b>Thu thập và xử lý:</b> mỗi 3 giờ (n8n)%s</li>'
        "<li><b>Đăng:</b> kiểm tra mỗi 30 phút, chỉ đăng trong giờ vàng %s, tối đa %d bài/ngày%s, cách nhau ≥ %s giờ</li>"
        "<li><b>Chốt ngày:</b> 23:30, đọc lượt xem và gửi tóm tắt</li></ul>"
        '<p class="muted small">Các nút ở trên chỉ là bổ sung; không thay thế và không làm gián đoạn lịch.</p></div>'
    ) % (
        (" · lần gần nhất %s" % ago(last_scan, view.now)) if last_scan else "",
        E(windows_text(cfg["post_windows"]) or "mọi lúc"),
        view.d["daily_limit"],
        " (tổng các tài khoản; mỗi tài khoản có giới hạn riêng)" if len(view.takers(None)) > 1 else "",
        E("%g" % round(cfg["min_publish_gap"] / 3600, 2)),
    )


def checklist(view):
    """(done, total, rows html): what is still needed for the system to run by itself."""
    d = view.d
    items = [
        (d["gemini_configured"], "Khóa Gemini API", "Nhập khóa ở mục Cài đặt bên dưới."),
        (d["processing_enabled"], "Bật xử lý video", "Video sẽ được gửi tới Google Gemini để phân tích khi bạn bật."),
        (d["discovery"] == "connected", "Bộ thu thập chạy được", "Cần agent trên máy và workflow n8n 01 đã bật."),
        (d["publisher"] == "connected", "Đã đăng nhập TikTok", "Chạy: ./trendvn tiktok login"),
        (d["publisher_enabled"], "Bật tự đăng", "Nên chạy thử dry-run và xem ảnh chụp trước khi bật."),
        (bool(d["notify_channels"]), "Nhận thông báo điện thoại", "Tùy chọn: Telegram, ntfy hoặc webhook (mục Thông báo)."),
    ]
    rows = "".join(
        '<li class="%s"><span class="tick">%s</span><div><b>%s</b><small>%s</small></div></li>'
        % ("ok" if ok else "todo", "✓" if ok else "○", E(title), "" if ok else E(hint))
        for ok, title, hint in items
    )
    return sum(1 for ok, _, _ in items if ok), len(items), rows


def setup_card(view):
    done, total, rows = checklist(view)
    return '<div class="card"><h2>Thiết lập <small>%d/%d hoàn tất</small></h2><ul class="check">%s</ul></div>' % (done, total, rows)


def flow_card(view):
    return (
        '<div class="card stack"><h2>Luồng xử lý</h2>%s<p class="muted small">Chạm vào từng bước để xem chi tiết. '
        "Mốc ban đầu (%d) chỉ để nhận diện video mới, không bao giờ đăng.</p></div>"
    ) % (view.funnel(), view.counts.get("baseline", 0))


def render(view):
    return "".join(
        (banner(view), control(view), switches(view), health(view), numbers(view), schedule(view), setup_card(view), flow_card(view))
    )
