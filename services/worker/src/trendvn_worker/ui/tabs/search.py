"""Tìm kiếm: one chat for everything about a product. The owner writes, pastes or attaches what they have; the answers (what the product
is, which videos exist for it in their account, whether a pasted share link is that product) come back in the same thread."""

import json
import time

from ...domain.channels import NAMES as CHANNEL_NAMES
from ...domain.chat_history import search_messages
from ...domain.discovery import PRODUCT_CATEGORIES
from ...domain.product_match import candidate_match
from ...domain.topics import TOPIC_LABEL
from ..controls import button, hidden, checkbox, textarea, input_control, copy_field
from ..components import chip, select
from ..format import ago, escape as E
from ..messages import user_message

ACCEPT = ".png,.jpg,.jpeg,.webp,.pdf,.docx,.txt"
SOURCES = {"auto": "Các kênh đã đăng nhập", **CHANNEL_NAMES}
VERDICTS = {
    "exact": ("Đúng sản phẩm", "good"),
    "found": ("Đã đọc sản phẩm", "info"),
    "likely": ("Có vẻ đúng", "warn"),
    "unknown": ("Chưa rõ", "warn"),
    "different": ("Sản phẩm khác", "bad"),
    "invalid": ("Không hợp lệ", "bad"),
}
STATE_CHIPS = {
    "ok": ("Sẵn sàng · phiên đã lưu", "good"),
    "out": ("Chưa đăng nhập", "bad"),
    "wall": ("Chờ xác minh", "warn"),
    "unknown": ("Chưa xác nhận phiên", "mute"),
    None: ("Chưa kiểm", "mute"),
}
EMPTY = {"messages": [], "picked": {}, "accounts": {}, "roster": [], "channels": {}, "saved": {}}
CONFIRM = {
    "affiliate": "Đây đúng là link hoa hồng của tôi",
    "short": "Tôi đã sao chép link này từ Showcase",
    "plain": "Vẫn dùng link này (không có dấu hiệu hoa hồng)",
}
MARKS = {"ok": "✓", "warn": "⚠", "bad": "✗", "info": "ℹ"}
WELCOME = (
    "<p><b>Gửi cho mình một trong những thứ bạn có về sản phẩm:</b> tên/model, ảnh, PDF/DOCX/TXT hoặc link.</p>"
    '<ul class="plain"><li>Mình nhận diện sản phẩm, rồi tìm video về nó: TikTok qua phiên đã đăng nhập của tài khoản bạn chọn, Douyin qua hồ sơ riêng của tài khoản đó.</li>'
    "<li>Link hoa hồng chỉ có trong app TikTok (Showcase → sản phẩm → Chia sẻ → Sao chép link). Dán nó vào đây, mình kiểm tra "
    "có đúng sản phẩm đang bàn không rồi lưu lại cho bạn.</li></ul>"
    '<p class="small muted">Mình không thể tự lấy link hoa hồng hay biết link đó là của tài khoản nào: bạn xác nhận lần đầu, '
    "mình nhớ dấu hiệu nhà sáng tạo để so các link sau.</p>"
)


def _busy(message):
    return message["state"] in ("pending", "running")


def _working(text):
    return '<p><span class="spin" aria-hidden="true"></span> %s</p>' % E(text)


def _failed(message, extra=""):
    return '<p class="note warn" role="alert">%s</p>%s' % (E(user_message(message["body"].get("error"), True)), extra)


def _button(label, action, cls="ghost", aria=None, **data):
    """A button that asks the chat to do something. `aria` names it for a screen reader when the visible label alone is not enough
    (four identical 'Đăng nhập' buttons in a column)."""
    attrs = {"data_" + k: v for k, v in data.items()}
    return button(label, cls, type="button", data_chat_act=action, **attrs, aria_label=aria)


def user_bubble(message, names, now):
    body = message["body"]
    files = "".join("<li>📎 %s</li>" % E(f["name"]) for f in body.get("files", []))
    return '<div class="msg me" data-message-id="%s"><div class="bubble"><p>%s</p>%s<small>@%s · %s</small></div></div>' % (
        message["id"],
        E(body.get("text", "")),
        '<ul class="files">%s</ul>' % files if files else "",
        E(names.get(message["account"], "?")),
        ago(message["created"], now),
    )


def product_card(message):
    body = message["body"]
    if _busy(message):
        return _working("Đang nhận diện sản phẩm…")
    if message["state"] == "error":
        return _failed(message)
    identity = body["identity"]
    name = identity.get("name") or identity.get("query", "")
    facts = "".join(
        chip("%s: %s" % (label, identity[key]), "info")
        for key, label in (("brand", "Hãng"), ("model", "Model"), ("variant", "Biến thể"))
        if identity.get(key)
    )
    queries = identity.get("queries", {})
    shown = "".join(
        '<p class="small">%s: <code>%s</code></p>' % (label, E(queries[key])) for key, label in CHANNEL_NAMES.items() if queries.get(key)
    )
    notes = "".join('<p class="note warn">%s</p>' % E(w) for w in identity.get("warnings", []))
    origin = '<p class="small muted">Lấy từ link bạn dán (mã sản phẩm %s).</p>' % E(identity["product_id"]) if body.get("from_link") else ""
    matched = identity.get("matched_affiliate")
    affiliate_info = ""
    if matched:
        affiliate_info = (
            '<p class="note info">🛒 <b>Đã khớp link hoa hồng trong tài khoản:</b> %s (%s). Sẽ tự động ghim giỏ hàng khi đăng TikTok.</p>'
            % (E(matched.get("title") or matched.get("product_id")), E(matched.get("url")))
        )
    elif body.get("discovery", {}).get("sales"):
        affiliate_info = '<p class="hint">ℹ️ Chưa có link hoa hồng cho sản phẩm này trong tài khoản. Dán link sao chép từ Showcase app TikTok vào đây để kiểm tra và lưu.</p>'
    actions = "".join(
        _button("Tìm video trên " + SOURCES[s], "find", "go" if s == "tiktok" else "ghost", id=message["id"], source=s)
        for s in CHANNEL_NAMES
    )
    return (
        '<h4>%s</h4><div class="facts">%s</div>%s%s%s%s<p class="hint">%s</p><div class="btns two">%s</div>%s'
        % (
            E(name), facts, origin, affiliate_info, shown, notes, E(identity.get("uncertainty", "")), actions,
            _button("Sửa tên/model", "fill", "ghost", text=name),
        )
    )  # fmt: skip


def top_products_card(message, store=None):
    body = message["body"]
    cat = body.get("category") or ""
    cat_label = body.get("category_label") or (PRODUCT_CATEGORIES.get(cat, ("", ""))[0] if cat else "Ngành hàng")
    account = message.get("account") or body.get("account") or ""
    account_username = body.get("account_username") or account

    # Luôn kiểm tra và làm mới thời gian thực từ store: loại trừ video đã có và sản phẩm đã bỏ qua
    if store and cat:
        products = store.category_top_products(cat, account=account)
        dismissed = store.dismissed_products(account)
    else:
        products = body.get("products") or []
        dismissed = body.get("dismissed") or []

    restore_btn = ""
    if dismissed:
        restore_btn = _button(
            "↺ Khôi phục %d sản phẩm đã bỏ qua" % len(dismissed),
            "undismiss_products",
            "ghost",
            account=account,
            category=cat,
        )

    if not products:
        return (
            '<div class="search-session-box">'
            '<div class="search-meta-bar">'
            '<div class="search-meta-tags">'
            '<span class="search-meta-tag">👤 @%s</span>'
            '<span class="search-meta-tag">📦 %s</span>'
            "</div>"
            '<span class="small muted">Lần tìm kiếm #%s</span>'
            "</div>"
            "<h4>🔥 Top sản phẩm bán chạy · %s</h4>"
            '<p class="note info">Tất cả sản phẩm bán chạy trong ngành hàng này bạn đều đã có video xử lý hoặc đã bỏ qua!</p>'
            '<p class="hint">Bạn có thể đổi ngành hàng hoặc nhập tên/model sản phẩm cụ thể vào ô chat bên dưới để tìm video mới.</p>'
            "%s</div>"
            % (
                E(account_username),
                E(cat_label),
                message["id"],
                E(cat_label),
                ('<div class="btns" style="margin-top:8px;">%s</div>' % restore_btn) if restore_btn else "",
            )
        )

    rows = []
    for idx, p in enumerate(products):
        name = p.get("name") or ""
        brand = p.get("brand") or ""
        model = p.get("model") or ""
        zh = p.get("query_zh") or ""
        display = "%s (%s %s)" % (name, brand, model) if brand or model else name
        query_val = model if model else name
        p_json = json.dumps(
            {
                "name": name,
                "brand": brand,
                "model": model,
                "query_zh": zh or query_val,
                "product_id": p.get("product_id") or "",
                "url": p.get("url") or "",
            }
        )

        brand_chip = ('<span class="product-brand-chip">%s</span>' % E(brand)) if brand else ""
        model_chip = ('<span class="product-model-chip">%s</span>' % E(model)) if model else ""
        showcase_chip = (
            '<span class="product-brand-chip" style="background:#065f46;color:#a7f3d0;" title="Sản phẩm có trong Showcase kênh">⭐ Giỏ hàng</span>'
            if p.get("is_showcase")
            else ""
        )
        c_cnt = p.get("existing_count", 0)
        cnt_chip = (
            (
                '<span class="product-model-chip" style="background:#1e293b;color:#94a3b8;" title="Đã có video trong hệ thống">🎞️ %d video</span>'
                % c_cnt
            )
            if c_cnt > 0
            else ""
        )

        check_input = (
            '<label class="product-label-wrap">'
            '<span class="product-compact-check">'
            '<input type="checkbox" class="batch-product-check" checked data-product="%s" '
            'aria-label="Chọn sản phẩm %s">'
            "</span>"
            '<div class="product-title-group">'
            '<div class="product-title-row">'
            '<span class="product-index-badge">%02d</span>'
            '<span class="product-name-txt">%s</span>'
            "%s%s%s%s"
            "</div>"
            '<div class="product-douyin-query">'
            "<span>🔍 Douyin:</span>"
            "<code>%s 测评 开箱</code>"
            "</div>"
            "</div></label>"
            % (E(p_json), E(display), idx + 1, E(name), brand_chip, model_chip, showcase_chip, cnt_chip, E(zh or query_val))
        )

        btn_find = _button(
            "🎬 Tìm lẻ video",
            "quick_find",
            "ghost btn-action-single",
            query=query_val,
            category=cat,
            sales="true",
            source="douyin",
            account=account,
        )
        btn_dismiss = _button(
            "❌ Bỏ qua",
            "dismiss_product",
            "ghost danger btn-action-dismiss",
            item_key=query_val,
            account=account,
            category=cat,
            aria="Bỏ qua sản phẩm " + display,
        )

        rows.append(
            '<div class="product-card-row top-product-row">'
            '<div class="product-card-header">%s</div>'
            '<div class="product-card-actions">%s%s</div>'
            "</div>" % (check_input, btn_find, btn_dismiss)
        )

    batch_toolbar = (
        '<div class="batch-toolbar-card">'
        '<div class="batch-toolbar-top">'
        '<div><b>Thao tác hàng loạt:</b> <span class="muted">Tự tìm Douyin, gắn giỏ hàng & xếp vào hàng đợi</span></div>'
        '<span class="batch-count-pill">Đã chọn: <b data-batch-count>%d</b> / %d sản phẩm</span>'
        "</div>"
        '<div class="batch-toolbar-btns">'
        "%s"
        "%s"
        "%s"
        "</div></div>"
        % (
            len(products),
            len(products),
            _button("Chọn tất cả / Bỏ chọn", "toggle_batch_all", "ghost"),
            _button(
                "🚀 Tìm kiếm & Tạo video hàng loạt",
                "batch_find",
                "go btn-batch-run",
                account=account,
                category=cat,
            ),
            restore_btn or '<span class="small muted" style="align-self:center;text-align:right;">Đã lọc trùng</span>',
        )
    )

    meta_bar = (
        '<div class="search-meta-bar">'
        '<div class="search-meta-tags">'
        '<span class="search-meta-tag">👤 @%s</span>'
        '<span class="search-meta-tag">📦 %s</span>'
        '<span class="search-meta-tag">🔥 %d sản phẩm gợi ý</span>'
        "</div>"
        '<span class="small muted">Lần tìm kiếm #%s</span>'
        "</div>"
        '<div class="search-steps-guide">'
        '<div class="search-step-pill"><b>1</b><span>Tick chọn sản phẩm muốn làm video</span></div>'
        '<div class="search-step-pill"><b>2</b><span>Bấm Tạo video hàng loạt (hoặc Tìm lẻ)</span></div>'
        '<div class="search-step-pill"><b>3</b><span>Hệ thống tự gắn giỏ hàng & vào Queue</span></div>'
        "</div>" % (E(account_username), E(cat_label), len(products), message["id"])
    )

    return (
        '<div class="top-products-container search-session-box">'
        "%s"
        "%s"
        '<div class="product-items-list">%s</div>'
        "</div>" % (meta_bar, batch_toolbar, "".join(rows))
    )


def duplicate_confirm_card(message):
    body = message["body"]
    query = body.get("query") or ""
    existing = body.get("existing") or []
    items_html = "".join(
        '<li>• <b>%s</b> — <span class="chip warn">%s</span></li>'
        % (E(item.get("title") or "Video " + item.get("id", "")[:8]), E(item.get("state_label") or item.get("state")))
        for item in existing
    )
    continue_btn = _button(
        "Tiếp tục tìm video mới",
        "confirm_duplicate",
        "go",
        id=message["id"],
        account=message.get("account"),
    )
    view_links = '<a class="btn ghost" href="#publish">Xem video ở Đăng bài →</a> ' '<a class="btn ghost" href="#queue">Xem hàng chờ →</a>'
    return (
        "<h4>⚠️ Sản phẩm đã có video trong hệ thống</h4>"
        '<p>Sản phẩm <b>"%s"</b> đã có video đang được lưu hoặc xử lý:</p>'
        '<ul class="plain" style="margin:8px 0;">%s</ul>'
        '<p class="hint">Tiếp tục tìm video mới theo yêu cầu ban đầu, vẫn loại video đã có trong hệ thống.</p>'
        '<div class="btns two" style="margin-top:10px;">%s%s</div>' % (E(query), items_html, continue_btn, view_links)
    )


def candidate(item, job, message_id):
    """One video the search found: what it is, why it matches, and either the pick button or where the pick has got to."""
    different = item["match"]["level"] == "different"
    link = '<a href="%s" target="_blank" rel="noopener noreferrer">Xem video để đối chiếu ↗</a>' % E(item["url"])
    head = '<p class="ttl">%s</p><p class="small">%s</p>%s' % (E(item.get("title") or "Video"), E(item["match"]["reason"]), link)
    if job:
        state = job.get("state")
        return '<article class="card stack">%s<p class="hint">%s · %s</p><a class="next-link" href="#%s">%s →</a></article>' % (
            head,
            E(job.get("state_label") or ""),
            E(user_message(job.get("reason") or "")),
            "publish" if state in ("ready", "awaiting_approval") else "queue",
            "Xem bản dựng" if state in ("ready", "awaiting_approval") else "Xem hàng chờ",
        )
    pick = checkbox(
        "confirm_video", "Tôi đã xem và xác nhận đúng sản phẩm, model và biến thể", css="search-check", data_chat_confirm=True
    ) + _button("Chọn và tải để xử lý", "pick", "go", id=message_id, source_id=item["source_id"], platform=item.get("platform", "tiktok"))
    variant_unmatched = "biến thể" in (item["match"].get("reason") or "").lower()
    if different and not variant_unmatched:
        action_area = '<p class="note warn">Khác sản phẩm đã nhận diện.</p>'
    elif different and variant_unmatched:
        action_area = '<p class="note warn">Chưa rõ biến thể trong tiêu đề; hãy xem video đối chiếu rồi tích xác nhận để chọn.</p>' + pick
    else:
        action_area = pick
    return '<article class="card stack">%s%s</article>' % (
        head,
        action_area
        + _button(
            "Bỏ ứng viên", "dismiss", "ghost danger", id=message_id, source_id=item["source_id"], platform=item.get("platform", "tiktok")
        ),
    )


def videos_card(message, picked, product_id):
    body = message["body"]
    where = "@%s · %s" % (body.get("account_username", "?"), SOURCES.get(body.get("source"), ""))
    if _busy(message):
        status_note = (
            '<div class="captcha-status" style="margin-top:8px;">'
            '<p class="note info">🤖 <b>Agent tích hợp trong trình duyệt đang tự động kiểm tra và giải CAPTCHA.</b> '
            "Cửa sổ Chrome đang mở; nếu xuất hiện thanh trượt hoặc xác minh, Agent sẽ tự động kéo/xác nhận. "
            "Bạn cũng có thể trực tiếp thao tác trên Chrome.</p>"
            '<div class="btns" style="margin-top:6px;">'
            '<button type="button" class="ghost" data-chat-act="refresh_check">🔄 Kiểm tra trạng thái ngay</button>'
            "</div></div>"
            if body.get("human")
            else ""
        )
        return "<h4>Video cho %s</h4>%s%s" % (
            E(where),
            _working(
                "Chờ bạn trong cửa sổ Chrome; hệ thống tiếp tục lấy video khi đăng nhập/xác minh xong. Đóng cửa sổ để dừng."
                if body.get("human")
                else "Đang tìm bằng phiên đã lưu; có thể mất vài phút. Nếu Chrome yêu cầu đăng nhập/xác minh, hãy làm trong cửa sổ đó; hệ thống chờ bạn. Đóng cửa sổ để dừng."
            ),
            status_note,
        )
    if message["state"] == "error":
        err_text = str(body.get("error") or message.get("error") or "")
        is_captcha = any(k in err_text.lower() for k in ("captcha", "xác minh", "xác nhận", "wall"))
        source = body.get("source", "tiktok")
        retry_buttons = []
        if is_captcha:
            target_source = "douyin" if "douyin" in err_text.lower() or source == "auto" else source
            retry_buttons.append(
                _button("Tôi đã xác nhận CAPTCHA, tiếp tục tìm", "find", "go", id=body.get("product", product_id), source=target_source)
            )
            retry_buttons.append(
                _button("Mở cửa sổ giải CAPTCHA", "find", "ghost", id=body.get("product", product_id), source=target_source, human="true")
            )
        else:
            retry_buttons.append(_button("Thử lại", "find", "ghost", id=body.get("product", product_id), source=source))
            if source != "auto":
                retry_buttons.append(
                    _button(
                        "Mở cửa sổ chờ tôi xác minh rồi tìm lại",
                        "find",
                        "ghost",
                        id=body.get("product", product_id),
                        source=source,
                        human="true",
                    )
                )
        if source == "auto":
            retry_buttons.append(_button("Tìm trên Douyin", "find", "ghost", id=body.get("product", product_id), source="douyin"))
            retry_buttons.append(_button("Tìm trên TikTok", "find", "ghost", id=body.get("product", product_id), source="tiktok"))
        retry = "".join(retry_buttons)
        sources = ("tiktok", "douyin") if source == "auto" else (source,)
        sign_in = "".join(
            _button("Đăng nhập " + CHANNEL_NAMES[c], "login", "ghost", channel=c, account=message["account"])
            for c in sources
            if c in CHANNEL_NAMES
        )
        captcha_banner = (
            '<p class="note warn">⚠️ Cần xác nhận CAPTCHA trên nguồn này. Bạn có thể bấm <b>"Mở cửa sổ giải CAPTCHA"</b> để mở Chrome thật thao tác (hệ thống cũng tự động hỗ trợ kéo slider), sau đó bấm <b>"Tôi đã xác nhận CAPTCHA, tiếp tục tìm"</b> để lấy video ngay.</p>'
            if is_captcha
            else ""
        )
        return '<h4>Video cho %s</h4>%s%s<div class="btns">%s%s</div>' % (E(where), _failed(message), captcha_banner, retry, sign_in)
    cards = "".join(
        candidate(
            dict(i, match=candidate_match(body.get("identity", {}), i)),
            next(
                (
                    j
                    for j in picked.get(str(message["id"]), [])
                    if j["source_id"] == i["source_id"] and j["platform"] == i.get("platform", "tiktok")
                ),
                None,
            ),
            message["id"],
        )
        for i in body.get("results", [])
    )
    empty = "" if cards else "<p>Không có ứng viên. Thử thêm tên/model hoặc dán link video cụ thể.</p>"
    note = '<p class="hint">%s</p>' % E(body["note"]) if body.get("note") else ""
    return (
        '<h4>Video cho %s</h4>%s%s%s<p class="small muted">Khớp từ khóa chưa chứng minh đúng sản phẩm: hãy xem video trước khi chọn.</p>'
        % (E(where), note, empty, cards)
    )


def checks_list(result):
    rows = "".join(
        '<li class="%s"><span class="tick">%s</span><span>%s<small>%s</small></span></li>'
        % (c["state"], MARKS.get(c["state"], "•"), E(c["label"]), E(c["detail"]))
        for c in result["checks"]
    )
    return '<ul class="check">%s</ul>' % rows


def link_card(message):
    body = message["body"]
    if _busy(message):
        return _working("Đang kiểm tra link…")
    if message["state"] == "error":
        return _failed(message)
    if body.get("video"):
        return (
            "<h4>Link video</h4><p>Link này dẫn tới một <b>video</b>, không phải trang sản phẩm. Mình đã thêm video đó ngay bên dưới: "
            "bấm tìm để lấy nó rồi xem và chọn.</p>"
        )
    result, found = body["verdict"], body["found"]
    label, tone = VERDICTS[result["verdict"]]
    head = '<div class="row"><h4>Link chia sẻ</h4>%s</div><p>%s</p>%s' % (chip(label, tone), E(result["summary"]), checks_list(result))
    if result["verdict"] in ("different", "invalid"):
        return head
    if body.get("saved"):
        return head + (
            '<p class="note">Đã lưu link cho sản phẩm này%s.</p>%s'
            % (" (link thường, không có dấu hiệu hoa hồng)" if result["kind"] == "plain" else "", copy_field(found["input"]))
        )
    return head + (
        '<p class="small muted">Mình không đăng nhập Shop/Affiliate của bạn nên không tự biết link này có phải của bạn. '
        "Chỉ xác nhận khi chính bạn đã sao chép nó từ Showcase trong app TikTok.</p>%s"
        % _button(CONFIRM.get(result["kind"], CONFIRM["affiliate"]), "confirm", "go", id=message["id"])
    )


def batch_search_card(message):
    body = message["body"]
    current = body.get("current", 0)
    total = body.get("total", 0) or 1
    created_jobs = body.get("created_jobs") or []
    logs = body.get("logs") or []
    summary = body.get("summary") or ""
    pct = min(100, int((current / total) * 100)) if total else 0

    if _busy(message):
        spinner = _working("Đang tìm kiếm & tải video review Douyin (%d/%d sản phẩm)…" % (current, total))
        log_rows = "".join("<li>%s</li>" % E(l) for l in logs[-6:])
        return (
            '<div class="batch-progress-box">'
            '<div class="batch-progress-header">'
            "<h4>🚀 Đang xử lý tìm kiếm & Tạo video hàng loạt</h4>"
            '<span class="badge info">%d%% (%d/%d SP)</span>'
            "</div>"
            '<div class="batch-progress-bar-wrap"><div class="batch-progress-bar-fill" style="width:%d%%;"></div></div>'
            "%s"
            '<ul class="plain small muted" style="margin-top:8px;">%s</ul>'
            "</div>" % (pct, current, total, pct, spinner, log_rows)
        )

    if message["state"] == "error":
        return '<div class="batch-progress-box"><h4>🚀 Tìm kiếm hàng loạt</h4>%s</div>' % _failed(message)

    job_rows = []
    for j in created_jobs:
        job_rows.append(
            '<div class="batch-job-item">'
            '<div><b>✓ %s</b>: <span class="muted">%s</span></div>'
            '<span class="chip good">Đã vào Queue</span>'
            "</div>" % (E(j.get("product_name", "")), E((j.get("video_title") or "")[:45]))
        )
    jobs_html = "".join(job_rows) if job_rows else "<p class='small muted'>Không có video mới nào được tải.</p>"
    return (
        '<div class="batch-progress-box">'
        '<div class="batch-progress-header">'
        "<h4>🚀 Hoàn tất tìm kiếm & Tạo video hàng loạt</h4>"
        '<span class="chip good">Xong %d/%d sản phẩm</span>'
        "</div>"
        '<div class="batch-progress-bar-wrap"><div class="batch-progress-bar-fill" style="width:100%%;"></div></div>'
        '<p class="note good" style="margin-bottom:10px;"><b>%s</b></p>'
        '<div style="margin-bottom:12px;">%s</div>'
        '<div class="btns two">'
        '<a class="btn go" href="#queue">Xem hàng chờ xử lý →</a>'
        '<a class="btn ghost" href="#publish">Xem trang Đăng bài →</a>'
        "</div></div>" % (len(created_jobs), total, E(summary or ("Đã xử lý xong %d/%d sản phẩm." % (len(created_jobs), total))), jobs_html)
    )


def bot_bubble(message, data):
    kind = message["kind"]
    if kind == "product":
        inner = product_card(message)
    elif kind == "videos":
        inner = videos_card(message, data["picked"], message["body"].get("product"))
    elif kind == "link":
        inner = link_card(message)
    elif kind == "top_products":
        inner = top_products_card(message, store=data.get("store"))
    elif kind == "batch_search":
        inner = batch_search_card(message)
    elif kind == "duplicate_confirm":
        inner = duplicate_confirm_card(message)
    else:
        inner = "<p>%s</p>" % E(message["body"].get("text", ""))
    delete = _button(
        "Xóa lượt này",
        "delete_history",
        "ghost danger",
        id=message["id"],
        ask="Xóa câu nhập và các kết quả thuộc lượt này? Video đã chọn và phiên đăng nhập vẫn giữ. Cửa sổ đang chờ tiếp tục hoạt động.",
    )
    return '<div class="msg bot" data-message-id="%s" data-state="%s"><div class="bubble stack">%s%s</div></div>' % (
        message["id"],
        message["state"],
        inner,
        delete,
    )


def chat_thread(data, now=None):
    """The messages, oldest first. `data-busy` tells the page whether to keep polling."""
    now = now or time.time()
    busy = any(_busy(m) for m in data["messages"] + data.get("waiting", [])) or any(
        job.get("downloading", False) for jobs in data["picked"].values() for job in jobs
    )
    rows = (
        "".join(
            user_bubble(m, data["accounts"], now) if m["role"] == "user" else bot_bubble(m, data)
            for m in search_messages(data["messages"], data["picked"])
        )
        or '<div class="msg bot"><div class="bubble stack">%s</div></div>' % WELCOME
    )
    return '<div id="chat-thread" class="thread" role="log" aria-live="polite" data-busy="%d">%s</div>' % (1 if busy else 0, rows)


def _channel_activity(activity, channel, entry=None):
    if activity and _busy(activity):
        return (
            _working("Đang đọc phiên đã lưu…")
            if activity["body"].get("mode") == "check"
            else _working(
                "Chờ bạn đăng nhập trong cửa sổ Chrome trên máy chạy TrendVN; không tự đóng khi bạn chưa xong. Đóng cửa sổ để dừng. Hệ thống không nhập mật khẩu thay bạn."
            )
        )
    if activity and activity.get("state") == "error":
        return _failed(activity)

    entry_state = (entry or {}).get("state")
    if entry_state == "out":
        text = "Chưa đăng nhập. Bấm Đăng nhập để mở Chrome đăng nhập."
    elif entry_state == "wall":
        text = "%s cần bạn tự xác minh; hồ sơ phiên vẫn được giữ." % CHANNEL_NAMES[channel]
    elif entry_state == "unknown":
        text = "Chưa đọc được bằng chứng đăng nhập từ trang; hồ sơ đã lưu vẫn được giữ."
    elif entry_state == "ok":
        who = (entry or {}).get("who")
        if channel == "douyin" and who:
            text = "Douyin đã xác nhận tài khoản %s trong hồ sơ của bạn." % who
        elif channel == "tiktok" and who:
            text = "Hồ sơ có phiên đăng nhập TikTok (@%s)." % who
        else:
            text = "Đã đăng nhập; phiên đã lưu cho %s." % CHANNEL_NAMES[channel]
    elif activity:
        if activity["body"].get("session_state") == "wall":
            text = "Douyin cần bạn tự xác minh; hồ sơ phiên vẫn được giữ."
        elif activity["body"].get("session_state") == "unknown":
            text = "Chưa đọc được bằng chứng đăng nhập từ trang; hồ sơ đã lưu vẫn được giữ."
        elif not activity["body"].get("ok"):
            text = "Chưa đăng nhập."
        elif activity["body"].get("mode") == "check":
            text = (
                "Douyin đã xác nhận tài khoản %s trong hồ sơ của bạn." % (activity["body"].get("who") or "đã đăng nhập")
                if channel == "douyin"
                else "Hồ sơ có phiên đăng nhập %s; lần tìm kiếm kiểm lại tài khoản." % CHANNEL_NAMES[channel]
            )
        else:
            text = "Đã đăng nhập; phiên đã lưu cho %s." % CHANNEL_NAMES[channel]
    else:
        text = ""

    if not text:
        return ""
    return '<p class="small muted" role="status">%s</p>' % E(text)


def _sign_in_row(account, channel, entry, now, messages=()):
    label, tone = STATE_CHIPS.get((entry or {}).get("state"), STATE_CHIPS[None])
    since = " · " + ago(entry["at"], now) if entry else ""
    who, name = "@" + account["username"], CHANNEL_NAMES[channel]
    saved = (entry or {}).get("state") in ("ok", "wall")
    activity = next(
        (
            m
            for m in reversed(messages)
            if m.get("kind") == "login" and m.get("account") == account["id"] and (m.get("body") or {}).get("channel") == channel
        ),
        None,
    )
    if activity and (
        activity["body"].get("account_username", account["username"]) != account["username"]
        or activity["state"] == "error"
        and entry
        and entry["state"] in ("ok", "wall")
        and entry["at"] > activity["created"]
    ):
        activity = None
    status = _channel_activity(activity, channel, entry)
    buttons = _button(
        "Đổi đăng nhập" if saved else "Đăng nhập",
        "login",
        "ghost" if saved else "go",
        aria="Đăng nhập %s cho %s" % (name, who),
        channel=channel,
        account=account["id"],
    ) + _button("Kiểm tra", "check", "ghost", aria="Kiểm tra đăng nhập %s của %s" % (name, who), channel=channel, account=account["id"])
    return (
        '<div class="chan"><div class="row"><b>%s</b><span>%s<small class="muted">%s</small></span></div>%s<div class="btns two">%s</div></div>'
        % (
            E(CHANNEL_NAMES[channel]),
            chip(label, tone),
            E(since),
            status,
            buttons,
        )
    )


def _saved_rows(account, links):
    rows = []
    for link in links:
        rows.append(
            '<div class="saved"><p class="ttl">%s</p>%s%s</div>'
            % (
                E((link.get("title") or "Sản phẩm " + link["product_id"])[:90]),
                copy_field(link["url"], (link.get("title") or link["product_id"])[:60]),
                _button(
                    "Xóa link này",
                    "forget",
                    "ghost danger",
                    aria="Xóa link đã lưu: " + (link.get("title") or link["product_id"])[:60],
                    account=account["id"],
                    product_id=link["product_id"],
                    ask="Xóa link đã lưu này?",
                ),
            )
        )
    return "".join(rows)


def chat_side(data, now=None):
    """The column beside the chat: which channels each account is signed in on, the links saved, and the history to clear."""
    now = now or time.time()
    roster = data.get("roster", [])
    sign_ins = (
        "".join(
            '<div class="acct-row stack" data-channel-account="%s"><p class="ttl">@%s</p>%s</div>'
            % (
                E(a["id"]),
                E(a["username"]),
                "".join(
                    _sign_in_row(a, c, data.get("channels", {}).get(a["id"], {}).get(c), now, data["messages"] + data.get("waiting", []))
                    for c in CHANNEL_NAMES
                ),
            )
            for a in roster
        )
        or '<p class="note warn">Chưa có tài khoản nào đang bật.</p>'
    )
    hidden_waits = [m for m in data.get("waiting", []) if m["kind"] != "login"]
    waiting = (
        '<p class="hint" role="status">Có lượt đã ẩn vẫn đang chạy hoặc chờ bạn trong Chrome. Đóng cửa sổ đó để dừng.</p>'
        if hidden_waits
        else ""
    )
    saved = (
        "".join(
            '<div class="stack" data-channel-account="%s"><p class="small muted">@%s</p>%s</div>'
            % (E(a["id"]), E(a["username"]), _saved_rows(a, data.get("saved", {}).get(a["id"], [])))
            for a in roster
            if data.get("saved", {}).get(a["id"])
        )
        or '<p class="hint">Chưa có link nào. Dán link chia sẻ vào chat, kiểm tra xong và xác nhận thì nó nằm ở đây.</p>'
    )
    return (
        '<aside id="chat-side" class="stack">'
        '<section class="card stack"><h3>Kênh tìm kiếm</h3>'
        '<p class="hint">Tìm video trên bốn nguồn dùng phiên đã đăng nhập của hồ sơ tương ứng. Cửa sổ đăng nhập mở trên máy chạy TrendVN; bạn tự đăng nhập '
        "(quét mã QR hoặc số điện thoại), hệ thống không nhập mật khẩu hộ. Phiên được lưu riêng cho tài khoản nhận video đã chọn và dùng lại sau khi khởi động lại. Chỉ đăng nhập lại khi nguồn hết phiên; xác minh không có nghĩa là mất phiên.</p>%s</section>"
        '<section class="card stack"><h3>Link hoa hồng đã lưu</h3>%s</section>'
        '<section class="card stack"><h3>Lịch sử tìm kiếm</h3><p class="hint">Xóa toàn bộ lịch sử khỏi khung chat, kể cả lượt đang chạy. Link đã lưu, video đã chọn '
        "và trạng thái đăng nhập được giữ nguyên. Đóng cửa sổ Chrome nếu muốn dừng việc đang chờ.</p>%s%s</section></aside>"
    ) % (
        sign_ins,
        saved,
        waiting,
        _button(
            "Xóa lịch sử tìm kiếm",
            "clear",
            "ghost danger",
            ask="Xóa toàn bộ lịch sử tìm kiếm trong khung chat? Link đã lưu và video đã chọn vẫn giữ.",
        ),
    )


def chat_fragment(data, now=None):
    """What the page polls: the thread and the side column (a sign-in changes the second while the first is being written)."""
    return chat_thread(data, now) + chat_side(data, now)


def composer(view):
    accounts = [(a["id"], "@" + a["username"]) for a in view.d["accounts"] if a["enabled"]]
    if not accounts:
        return '<p class="note warn">Chưa có tài khoản nào đang bật. Thêm tài khoản ở mục Thêm trước khi tìm.</p>'
    topics = {a["id"]: next((t for t in a.get("topics", []) if t in TOPIC_LABEL), "") for a in view.d["accounts"] if a["enabled"]}
    chosen = '<div class="discovery-options" data-account-topics="%s">' % E(json.dumps(topics))
    chosen += '<label class="acc-pick">Tài khoản nhận video%s</label>' % select("account", accounts[0][0], accounts)
    chosen += "<label>Nguồn tìm video%s</label>" % select("source", "auto", SOURCES.items())
    chosen += "<label>Thể loại%s</label>" % select("topic", topics[accounts[0][0]], [("", "Không giới hạn"), *TOPIC_LABEL.items()])
    chosen += checkbox("sales", "Tìm video bán hàng", css="search-check", data_sales_toggle=True)
    chosen += "<label data-sales-category hidden>Ngành hàng%s</label></div>" % select(
        "category", "", [("", "Chọn ngành hàng"), *((k, v[0]) for k, v in PRODUCT_CATEGORIES.items())]
    )
    compose = button("", "ghost attach icon-only", "clip", type="button", data_chat_attach=True, aria_label="Đính kèm ảnh hoặc tài liệu")
    compose += textarea(
        "text", rows=2, maxlength=12000, aria_label="Tin nhắn", placeholder="Tên/model, từ khóa, link, hoặc dán/thả ảnh, PDF, DOCX…"
    )
    compose += button("Tìm video", "go send")
    return (
        '<form class="composer" data-chat-form>%s%s<ul class="files" data-chat-files></ul>'
        '<div class="compose-row">%s</div>%s'
        '<p class="small muted">Thể loại, từ khóa và sản phẩm được đưa vào tìm video trên nền tảng. Tối đa 3 tệp, 4 MiB/tệp, tổng 8 MiB. Ctrl/⌘+Enter để gửi. Ảnh/tài liệu được chuyển cho Gemini (Google) để nhận diện; không lưu tệp.</p>'
        '<p role="status" aria-live="polite" data-chat-message></p></form>'
    ) % (hidden("csrf", view.csrf), chosen, compose, input_control("files", type="file", multiple=True, accept=ACCEPT, hidden=True))


def render(view):
    chat = view.d.get("chat") or EMPTY
    return (
        '<div id="search" class="chat-layout" data-chat data-csrf="%s"><div class="card chat stack"><h3>Tìm video và sản phẩm</h3>%s%s</div>%s</div>'
        % (
            E(view.csrf),
            chat_thread(chat, view.now),
            composer(view),
            chat_side(chat, view.now),
        )
    )
