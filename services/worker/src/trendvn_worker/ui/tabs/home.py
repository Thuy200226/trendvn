"""Tổng quan: state of the automation, the main buttons, the two switches, health, numbers and the setup checklist."""

from ..components import chip, component_chip, quick_switch, task_panel
from ..format import ago, escape as E, num, windows_text


def _accounts_text(d):
    """'@a' for one account, '3 tài khoản (@a, @b, @c)' for several."""
    names = ["@" + a["username"] for a in d["accounts"] if a["enabled"]]
    return names[0] if len(names) == 1 else "%d tài khoản (%s)" % (len(names), ", ".join(names))


def _banner_problem(view):
    """Why the automation is not fully running by itself, in the owner's words, or '' when it is. Green means every part reports in."""
    d = view.d
    if view.key_rejected:
        return "Khóa Gemini bị Google từ chối: vào Thêm → Cài đặt đổi khóa (các video vẫn nằm chờ, không mất)."
    if not (d["gemini_configured"] and d["processing_enabled"] and d["publisher_enabled"]):
        return "Hoàn tất danh sách thiết lập để bật tự động."
    if view.attention:
        return "Có %d việc cần bạn xem ở tab Cần xem." % view.attention
    waiting = view.counts.get("awaiting_approval", 0)
    if waiting:  # (also after the approval switch was turned off: the scheduler posts only videos that were released)
        return "Có %d video đang chờ bạn duyệt ở tab Đăng bài; chưa duyệt thì chưa đăng." % waiting
    parts = (("Bộ thu thập", d["discovery"]), ("Trình đăng TikTok", d["publisher"]))
    erred = [name for name, state in parts if state == "error"]
    if erred:
        return "%s đang báo lỗi: xem dòng Tình trạng bên dưới hoặc chạy ./trendvn doctor." % ", ".join(erred)
    silent = [name for name, state in parts if state != "connected"]
    if silent:
        return (
            "%s chưa báo cáo gần đây: lịch tự động có thể đã tắt (chạy ./trendvn n8n activate) hoặc agent không chạy (./trendvn doctor)."
            % ", ".join(silent)
        )
    return ""


def banner(view):
    if view.key_rejected:
        return (
            '<div class="banner warn"><b>Chưa tự động hoàn toàn.</b> Khóa Gemini bị Google từ chối: vào Thêm → Cài đặt đổi khóa (các video vẫn nằm chờ, không mất).</div>'
        )
    if not view.d["publisher_enabled"]:
        return '<div class="banner neutral"><b>Chế độ thủ công.</b> Xem và duyệt bản dựng ở Đăng bài; tự đăng đang tắt.</div>'
    problem = _banner_problem(view)
    if problem:
        return '<div class="banner warn"><b>Chưa tự động hoàn toàn.</b> %s</div>' % E(problem)
    return '<div class="banner good"><b>Đang tự động hoàn toàn.</b> Thu thập, xử lý và đăng chạy theo lịch.</div>'


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
        view.action("update", "Thu thập và xử lý ngay", "go xl", view.busy_browser or view.busy_process, "home"),
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
        row("Thu thập video", component_chip(d["discovery"]))
        + row("Đăng TikTok", component_chip(d["publisher"]))
        + row("Giờ vàng", window)
        + row("Ổ đĩa", _disk_chip(d.get("disk_free_mb")))
    )
    return '<div class="card pills"><h3>Tình trạng</h3>%s</div>' % rows


def _disk_chip(free_mb):
    """Free disk space: a full disk stops everything, so it is on the front page. Under 1 GB downloads pause, under 512 MB so does rendering."""
    if free_mb is None:
        return chip("Không rõ", "mute")
    text = "%.1f GB trống" % (free_mb / 1024) if free_mb >= 1024 else "%d MB trống" % free_mb
    return chip(text, "good" if free_mb >= 2048 else ("warn" if free_mb >= 1024 else "bad"))


def numbers(view):
    d = view.d
    read = [
        p["views"] for p in d["performance"] if p["views"] is not None
    ]  # None = never read from TikTok, which is not the same as 0 views
    total_views = sum(read)
    tiles = (
        ("Đăng hôm nay", "%d / %d" % (d["published_today"], d["daily_limit"])),
        ("Chờ xử lý", view.waiting),
        ("Sẵn sàng đăng", view.ready_total),
        ("Cần xem", view.attention),
        ("Tổng đã đăng", view.counts.get("published", 0)),
        ("Lượt xem (30 bài gần nhất)", num(total_views) if read else "—"),
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
        (d.get("gemini_configured", False), "Khóa Gemini API", "Nhập khóa ở mục Cài đặt bên dưới."),
        (d.get("processing_enabled", False), "Bật xử lý video", "Video sẽ được gửi tới Google Gemini để phân tích khi bạn bật."),
        (d.get("discovery") == "connected", "Bộ thu thập chạy được", "Cần agent trên máy và workflow n8n 01 đã bật."),
        (
            any(a.get("logged_in") is True for a in d.get("accounts", []) if a.get("enabled")),
            "Tài khoản TikTok đã kiểm tra đăng nhập",
            "Mở Hàng đợi → Tìm video → Kênh tìm kiếm để kiểm tra từng tài khoản.",
        ),
        (d.get("publisher_enabled", False), "Bật tự đăng", "Nên chạy thử dry-run và xem ảnh chụp trước khi bật."),
        (bool(d.get("notify_channels")), "Nhận thông báo điện thoại", "Tùy chọn: Telegram, ntfy hoặc webhook (mục Thông báo)."),
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
        (
            "<h2>Tổng quan</h2>",
            banner(view),
            flow_card(view),
            _next_action(view),
            control(view),
            health(view),
            numbers(view),
            schedule(view),
            setup_card(view),
            '<details class="card acc"><summary>Chế độ xử lý và tự đăng</summary><div class="accbody">%s</div></details>' % switches(view),
        )
    )


def _next_action(view):
    if view.attention:
        text, href = "%d việc cần bạn quyết định" % view.attention, "attention"
    elif view.ready_total:
        text, href = "%d video đã dựng — xem và duyệt trước khi đăng" % view.ready_total, "publish"
    elif view.waiting:
        text, href = "%d video trong hàng đợi" % view.waiting, "queue"
    else:
        text, href = "Tìm video để bắt đầu", "search"
    return '<div class="card stack"><h3>Bước tiếp theo</h3><a class="next-link" href="#%s">%s →</a></div>' % (href, E(text))
