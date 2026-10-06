"""Tài khoản TikTok: which topics each account takes, its own limits, and how to sign in to it."""

from ...domain import topics
from ..components import chip, field, number_input, select, text_input
from ..format import escape as E, windows_text

NO_OVERRIDE = (("", "Dùng cài đặt chung"), ("public", "Mọi người (công khai)"), ("friends", "Bạn bè"), ("self", "Chỉ mình tôi"))


def _toggles(chosen):
    """One big tap target per topic: a checkbox stretched over its label."""
    return '<div class="toggles">%s</div>' % "".join(
        '<label class="tg"><input type="checkbox" name="topic" value="%s"%s><span>%s</span></label>'
        % (t.id, " checked" if t.id in chosen else "", E(t.vi))
        for t in topics.TOPICS
    )


def _login_chip(account):
    state = account["logged_in"]
    if state is True:
        return chip("đã đăng nhập TikTok", "good")
    if state is False:
        return chip("chưa đăng nhập TikTok", "warn")
    return chip("chưa kiểm tra đăng nhập", "mute")


def _login_hint(account):
    command = "./trendvn tiktok login" + ("" if account["id"] == "main" else " --account " + account["id"])
    return (
        '<p class="small muted">Đăng nhập một lần: bấm Đăng nhập trong <a href="#search" data-search-account="%s">tab Tìm</a> (TikTok và Douyin), '
        "hoặc chạy <code>%s</code>, rồi tự đăng nhập trong cửa sổ Chrome hiện ra.</p>" % (E(account["id"]), E(command))
    )


def _overrides(account):
    own = account["own"]
    return "".join(
        (
            field(
                "Số bài tối đa mỗi ngày",
                number_input("daily_limit", own["daily_limit"] if own["daily_limit"] is not None else "", 1, 10),
                "Để trống = dùng số chung (%d)." % account["daily_limit"] if own["daily_limit"] is None else "",
            ),
            field(
                "Giãn cách tối thiểu (giờ)",
                number_input("gap_hours", round(own["min_gap"] / 3600, 2) if own["min_gap"] is not None else "", 0, 24, "0.25"),
            ),
            field(
                "Giờ vàng (giờ Việt Nam)",
                text_input(
                    "post_windows", windows_text(own["windows"]) if own["windows"] is not None else "", 'placeholder="11-14, 19-23"'
                ),
                "Để trống = dùng giờ vàng chung.",
            ),
            field("Chế độ hiển thị", select("visibility", own["visibility"] or "", NO_OVERRIDE)),
        )
    )


def _card(view, account):
    state = chip("đang bật", "good") if account["enabled"] else chip("đang tắt", "mute")
    today = chip("hôm nay %d/%d" % (account["published_today"], account["daily_limit"]), "info")
    enabled = select("enabled", "true" if account["enabled"] else "false", (("true", "Bật"), ("false", "Tắt")))
    return (
        '<form method="post" action="/account-save" class="card stack acct"><input type="hidden" name="csrf" value="%(csrf)s">'
        '<input type="hidden" name="id" value="%(id)s">'
        '<div class="row"><h3>@%(user)s</h3><div class="facts">%(state)s%(login)s%(today)s</div></div>'
        '<p><a href="#search" data-search-account="%(id)s">Tìm video và sản phẩm cho tài khoản này →</a></p>'
        '<p class="small muted">Nhận các chủ đề:</p>%(toggles)s%(hint)s'
        '<details class="fs"><summary>Tên gọi, bật/tắt và giới hạn riêng</summary><div class="fsbody">%(label)s%(enabled)s%(overrides)s</div></details>'
        '<div class="btns two"><button class="go">Lưu tài khoản</button>'
        '<button class="ghost danger" formaction="/account-delete" data-confirm="Xóa @%(user)s khỏi danh sách? Các bài đã đăng vẫn giữ nguyên.">Xóa</button></div></form>'
    ) % {
        "csrf": view.csrf,
        "id": E(account["id"]),
        "user": E(account["username"]),
        "state": state,
        "login": _login_chip(account),
        "today": today,
        "toggles": _toggles(account["topics"]),
        "hint": _login_hint(account),
        "label": field("Tên gọi (chỉ để bạn nhìn)", text_input("label", account["label"] or "", 'maxlength="40"')),
        "enabled": field("Trạng thái", enabled),
        "overrides": _overrides(account),
    }


def _add_form(view):
    return (
        '<form method="post" action="/account-add" class="card stack"><input type="hidden" name="csrf" value="%s"><h3>Thêm tài khoản</h3>%s'
        '<p class="small muted">Chọn các chủ đề tài khoản này nhận:</p>%s<div class="btns"><button class="go">Thêm tài khoản</button></div></form>'
    ) % (
        view.csrf,
        field("Tên người dùng TikTok", text_input("username", "", 'placeholder="ten_kenh" autocomplete="off" autocapitalize="off"')),
        _toggles(()),
    )


def render(view):
    accounts = view.d["accounts"]
    wanted = [topics.label(t) for t in view.d["wanted_topics"]]
    intro = (
        '<p class="hint">Mỗi tài khoản nhận một số chủ đề. Hệ thống chỉ tìm video thuộc chủ đề có tài khoản nhận (%s) và đăng mỗi video lên '
        "đúng tài khoản nhận chủ đề đó, theo giới hạn ngày, giãn cách và giờ vàng của chính tài khoản.</p>"
    ) % E(", ".join(wanted) or "chưa có")
    return intro + "".join(_card(view, a) for a in accounts) + _add_form(view)
