"""Tìm kiếm: one chat for everything about a product. The owner writes, pastes or attaches what they have; the answers (what the product
is, which videos exist for it in their account, whether a pasted share link is that product) come back in the same thread."""

import json
import time

from ...domain.channels import NAMES as CHANNEL_NAMES
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
STATE_CHIPS = {"ok": ("Sẵn sàng", "good"), "out": ("Chưa đăng nhập", "bad"), "wall": ("Đòi xác minh", "warn"), None: ("Chưa kiểm", "mute")}
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
    actions = "".join(
        _button("Tìm video trên " + SOURCES[s], "find", "go" if s == "tiktok" else "ghost", id=message["id"], source=s)
        for s in CHANNEL_NAMES
    )
    return (
        '<h4>%s</h4><div class="facts">%s</div>%s%s%s<p class="hint">%s</p><div class="btns two">%s</div>%s'
        % (
            E(name), facts, origin, shown, notes, E(identity.get("uncertainty", "")), actions,
            _button("Sửa tên/model", "fill", "ghost", text=name),
        )
    )  # fmt: skip


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
    return '<article class="card stack">%s%s</article>' % (
        head,
        ('<p class="note warn">Khác sản phẩm đã nhận diện.</p>' if different else pick)
        + _button(
            "Bỏ ứng viên", "dismiss", "ghost danger", id=message_id, source_id=item["source_id"], platform=item.get("platform", "tiktok")
        ),
    )


def videos_card(message, picked, product_id):
    body = message["body"]
    where = "@%s · %s" % (body.get("account_username", "?"), SOURCES.get(body.get("source"), ""))
    if _busy(message):
        return "<h4>Video cho %s</h4>%s" % (
            E(where),
            _working("Đang tìm trên nguồn đã chọn bằng phiên của tài khoản này; có thể mất vài phút. Có thể tiếp tục gửi tin khác."),
        )
    if message["state"] == "error":
        retry = "".join(_button(label, "find", "ghost", id=body.get("product", product_id), source=s, **extra) for label, s, extra in (
            ("Thử lại", body.get("source", "tiktok"), {}),
            ("Mở cửa sổ chờ tôi xác minh rồi tìm lại", body.get("source", "tiktok"), {"human": "true"}),
        ) if body.get("source") != "auto" or "human" not in extra)  # fmt: skip
        sources = ("tiktok", "douyin") if body.get("source") == "auto" else (body.get("source", "tiktok"),)
        sign_in = "".join(
            _button("Đăng nhập " + CHANNEL_NAMES[c], "login", "ghost", channel=c, account=message["account"])
            for c in sources
            if c in CHANNEL_NAMES
        )
        return '<h4>Video cho %s</h4>%s<div class="btns">%s%s</div>' % (E(where), _failed(message), retry, sign_in)
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


def login_card(message):
    body = message["body"]
    name, who = CHANNEL_NAMES.get(body.get("channel"), "?"), "@" + body.get("account_username", "?")
    checking = body.get("mode") == "check"
    title = "%s %s · %s" % ("Kiểm tra" if checking else "Đăng nhập", name, who)
    again = _button("Đăng nhập " + name, "login", "go", channel=body.get("channel"), account=message["account"])
    if _busy(message):
        if checking:
            return "<h4>%s</h4>%s" % (E(title), _working("Đang đọc phiên đã lưu…"))
        return '<h4>%s</h4>%s<p class="small muted">%s</p>' % (
            E(title),
            _working("Đã mở cửa sổ Chrome trên máy chạy TrendVN (không phải trình duyệt bạn đang xem). Đăng nhập trong cửa sổ đó."),
            "Quét mã QR hoặc dùng số điện thoại như bình thường, tối đa 10 phút; cửa sổ tự đóng khi xong. Mình không nhập mật khẩu thay bạn.",
        )
    if message["state"] == "error":
        return '<h4>%s</h4>%s<div class="btns">%s</div>' % (E(title), _failed(message), again)
    if body.get("ok") and checking:  # a check reads cookies: it cannot tell whose session it is, and says so
        return '<h4>%s</h4><p class="note">Hồ sơ có phiên đăng nhập %s. Chưa kiểm đúng tài khoản: lần tìm kiếm sẽ kiểm.</p>' % (
            E(title),
            E(name),
        )
    if body.get("ok"):
        return '<h4>%s</h4><p class="note">✓ Đã đăng nhập: tìm kiếm trên %s dùng được.</p>' % (E(title), E(name))
    return '<h4>%s</h4><p class="note warn">Chưa đăng nhập.</p><div class="btns">%s</div>' % (E(title), again)


def bot_bubble(message, data):
    kind = message["kind"]
    if kind == "product":
        inner = product_card(message)
    elif kind == "videos":
        inner = videos_card(message, data["picked"], message["body"].get("product"))
    elif kind == "link":
        inner = link_card(message)
    elif kind == "login":
        inner = login_card(message)
    else:
        inner = "<p>%s</p>" % E(message["body"].get("text", ""))
    delete = (
        ""
        if _busy(message)
        else _button(
            "Xóa lượt này",
            "delete_history",
            "ghost danger",
            id=message["id"],
            ask="Xóa riêng lượt này khỏi lịch sử? Video đã chọn vẫn giữ.",
        )
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
    busy = any(_busy(m) for m in data["messages"]) or any(job.get("downloading", False) for jobs in data["picked"].values() for job in jobs)
    rows = (
        "".join(user_bubble(m, data["accounts"], now) if m["role"] == "user" else bot_bubble(m, data) for m in data["messages"])
        or '<div class="msg bot"><div class="bubble stack">%s</div></div>' % WELCOME
    )
    return '<div id="chat-thread" class="thread" role="log" aria-live="polite" data-busy="%d">%s</div>' % (1 if busy else 0, rows)


def _sign_in_row(account, channel, entry, now):
    label, tone = STATE_CHIPS.get((entry or {}).get("state"), STATE_CHIPS[None])
    since = " · " + ago(entry["at"], now) if entry else ""
    who, name = "@" + account["username"], CHANNEL_NAMES[channel]
    buttons = _button(
        "Đăng nhập", "login", "go", aria="Đăng nhập %s cho %s" % (name, who), channel=channel, account=account["id"]
    ) + _button("Kiểm tra", "check", "ghost", aria="Kiểm tra đăng nhập %s của %s" % (name, who), channel=channel, account=account["id"])
    return (
        '<div class="chan"><div class="row"><b>%s</b><span>%s<small class="muted">%s</small></span></div><div class="btns two">%s</div></div>'
        % (
            E(CHANNEL_NAMES[channel]),
            chip(label, tone),
            E(since),
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
            '<div class="acct-row stack"><p class="ttl">@%s</p>%s</div>'
            % (E(a["username"]), "".join(_sign_in_row(a, c, data.get("channels", {}).get(a["id"], {}).get(c), now) for c in CHANNEL_NAMES))
            for a in roster
        )
        or '<p class="note warn">Chưa có tài khoản nào đang bật.</p>'
    )
    saved = (
        "".join(
            '<div class="stack"><p class="small muted">@%s</p>%s</div>'
            % (E(a["username"]), _saved_rows(a, data.get("saved", {}).get(a["id"], [])))
            for a in roster
            if data.get("saved", {}).get(a["id"])
        )
        or '<p class="hint">Chưa có link nào. Dán link chia sẻ vào chat, kiểm tra xong và xác nhận thì nó nằm ở đây.</p>'
    )
    return (
        '<aside id="chat-side" class="stack">'
        '<section class="card stack"><h3>Kênh tìm kiếm</h3>'
        '<p class="hint">Tìm video trên bốn nguồn dùng phiên đã đăng nhập của hồ sơ tương ứng. Cửa sổ đăng nhập mở trên máy chạy TrendVN; bạn tự đăng nhập '
        "(quét mã QR hoặc số điện thoại), hệ thống không nhập mật khẩu hộ và chỉ nhớ phiên trong hồ sơ trình duyệt riêng của tài khoản.</p>%s</section>"
        '<section class="card stack"><h3>Link hoa hồng đã lưu</h3>%s</section>'
        '<section class="card stack"><h3>Lịch sử tìm kiếm</h3><p class="hint">Xóa các tin đã xong trong khung chat. Link đã lưu, video đã chọn '
        "và trạng thái đăng nhập được giữ nguyên.</p>%s</section></aside>"
    ) % (
        sign_ins,
        saved,
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
