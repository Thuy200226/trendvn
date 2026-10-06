"""Tìm kiếm: one chat for everything about a product. The owner writes, pastes or attaches what they have; the answers (what the product
is, which videos exist for it in their account, whether a pasted share link is that product) come back in the same thread."""

import time

from ..components import chip, select
from ..format import ago, escape as E

ACCEPT = ".png,.jpg,.jpeg,.webp,.pdf,.docx,.txt"
SOURCES = {"tiktok": "TikTok", "douyin": "Douyin", "auto": "TikTok + Douyin"}
VERDICTS = {
    "exact": ("Đúng sản phẩm", "good"),
    "found": ("Đã đọc sản phẩm", "info"),
    "likely": ("Có vẻ đúng", "warn"),
    "unknown": ("Chưa rõ", "warn"),
    "different": ("Sản phẩm khác", "bad"),
    "invalid": ("Không hợp lệ", "bad"),
}
EMPTY = {"messages": [], "picked": {}, "accounts": {}}
MARKS = {"ok": "✓", "warn": "⚠", "bad": "✗", "info": "ℹ"}
WELCOME = (
    "<p><b>Gửi cho mình một trong những thứ bạn có về sản phẩm:</b> tên/model, ảnh, PDF/DOCX/TXT hoặc link.</p>"
    '<ul class="plain"><li>Mình nhận diện sản phẩm, rồi tìm video về nó ngay trong phiên TikTok/Douyin của tài khoản bạn chọn.</li>'
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
    return '<p class="note warn" role="alert">%s</p>%s' % (E(message["body"].get("error") or "Chưa làm được"), extra)


def _button(label, action, cls="ghost", **data):
    attrs = "".join(' data-%s="%s"' % (k.replace("_", "-"), E(str(v))) for k, v in data.items())
    return '<button type="button" class="%s" data-chat-act="%s"%s>%s</button>' % (cls, action, attrs, E(label))


def user_bubble(message, names, now):
    body = message["body"]
    files = "".join("<li>📎 %s</li>" % E(f["name"]) for f in body.get("files", []))
    return '<div class="msg me"><div class="bubble"><p>%s</p>%s<small>@%s · %s</small></div></div>' % (
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
        '<p class="small">%s: <code>%s</code></p>' % (label, E(queries[key]))
        for key, label in (("tiktok", "TikTok"), ("douyin", "Douyin"))
        if queries.get(key)
    )
    notes = "".join('<p class="note warn">%s</p>' % E(w) for w in identity.get("warnings", []))
    origin = '<p class="small muted">Lấy từ link bạn dán (mã sản phẩm %s).</p>' % E(identity["product_id"]) if body.get("from_link") else ""
    actions = "".join(
        _button("Tìm video trên " + SOURCES[s], "find", "go" if s == "tiktok" else "ghost", id=message["id"], source=s)
        for s in ("tiktok", "douyin")
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
        return '<article class="card stack">%s<p class="hint">%s · %s</p></article>' % (head, E(job["state_label"]), E(job["reason"] or ""))
    pick = (
        '<label class="search-check"><input type="checkbox" data-chat-confirm> Tôi đã xem và xác nhận đúng sản phẩm, model và biến thể</label>'
        + _button("Chọn và tải để xử lý", "pick", "go", id=message_id, source_id=item["source_id"], platform=item.get("platform", "tiktok"))
    )
    return '<article class="card stack">%s%s</article>' % (
        head,
        '<p class="note warn">Khác sản phẩm đã nhận diện.</p>' if different else pick,
    )


def videos_card(message, picked, product_id):
    body = message["body"]
    where = "@%s · %s" % (body.get("account_username", "?"), SOURCES.get(body.get("source"), ""))
    if _busy(message):
        return "<h4>Video cho %s</h4>%s" % (
            E(where),
            _working("Đang tìm trong phiên TikTok/Douyin của tài khoản này; có thể mất vài phút. Có thể tiếp tục gửi tin khác."),
        )
    if message["state"] == "error":
        retry = "".join(_button(label, "find", "ghost", id=body.get("product", product_id), source=s, **extra) for label, s, extra in (
            ("Thử lại", body.get("source", "tiktok"), {}),
            ("Mở cửa sổ để tự xác minh rồi tìm lại", body.get("source", "tiktok"), {"human": "true"}),
        ) if body.get("source") != "auto" or "human" not in extra)  # fmt: skip
        return '<h4>Video cho %s</h4>%s<div class="btns">%s</div>' % (E(where), _failed(message), retry)
    cards = "".join(
        candidate(
            i,
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
    result, found = body["verdict"], body["found"]
    label, tone = VERDICTS[result["verdict"]]
    head = '<div class="row"><h4>Link chia sẻ</h4>%s</div><p>%s</p>%s' % (chip(label, tone), E(result["summary"]), checks_list(result))
    if result["verdict"] in ("different", "invalid"):
        return head
    if body.get("saved"):
        return head + (
            '<p class="note">Đã lưu link cho sản phẩm này%s.</p><div class="copy"><input readonly value="%s" aria-label="Link đã lưu">'
            '<button type="button" class="ghost" data-copy>Chép link</button></div>'
            % (" (link thường, không có dấu hiệu hoa hồng)" if result["kind"] == "plain" else "", E(found["input"]))
        )
    return head + (
        '<p class="small muted">Mình không đăng nhập Shop/Affiliate của bạn nên không tự biết link này có phải của bạn. '
        "Chỉ xác nhận khi chính bạn đã sao chép nó từ Showcase trong app TikTok.</p>%s"
        % _button("Đây đúng là link hoa hồng của tôi", "confirm", "go", id=message["id"])
    )


def bot_bubble(message, data):
    kind = message["kind"]
    if kind == "product":
        inner = product_card(message)
    elif kind == "videos":
        inner = videos_card(message, data["picked"], message["body"].get("product"))
    elif kind == "link":
        inner = link_card(message)
    else:
        inner = "<p>%s</p>" % E(message["body"].get("text", ""))
    return '<div class="msg bot" data-state="%s"><div class="bubble stack">%s</div></div>' % (message["state"], inner)


def chat_thread(data, now=None):
    """The messages, oldest first. `data-busy` tells the page whether to keep polling."""
    now = now or time.time()
    busy = any(_busy(m) for m in data["messages"])
    rows = (
        "".join(user_bubble(m, data["accounts"], now) if m["role"] == "user" else bot_bubble(m, data) for m in data["messages"])
        or '<div class="msg bot"><div class="bubble stack">%s</div></div>' % WELCOME
    )
    return '<div id="chat-thread" class="thread" role="log" aria-live="polite" data-busy="%d">%s</div>' % (1 if busy else 0, rows)


def composer(view):
    accounts = [(a["id"], "@" + a["username"]) for a in view.d["accounts"] if a["enabled"]]
    if not accounts:
        return '<p class="note warn">Chưa có tài khoản nào đang bật. Thêm tài khoản ở mục Thêm trước khi tìm.</p>'
    return (
        '<form class="composer" data-chat-form><input type="hidden" name="csrf" value="%s">'
        '<label class="acc-pick">Gửi cho tài khoản%s</label><ul class="files" data-chat-files></ul>'
        '<div class="compose-row"><button type="button" class="ghost attach" data-chat-attach aria-label="Đính kèm ảnh hoặc tài liệu">📎</button>'
        '<textarea name="text" rows="2" maxlength="12000" aria-label="Tin nhắn" '
        'placeholder="Tên/model, link, hoặc dán/thả ảnh, PDF, DOCX…"></textarea><button class="go send" type="submit">Gửi</button></div>'
        '<input type="file" name="files" multiple accept="%s" hidden>'
        '<p class="small muted">Tối đa 3 tệp, 4 MiB/tệp, tổng 8 MiB. Ctrl/⌘+Enter để gửi.</p>'
        '<p role="status" aria-live="polite" data-chat-message></p></form>'
    ) % (view.csrf, select("account", accounts[0][0], accounts), ACCEPT)


def render(view):
    return '<div class="card chat stack" data-chat data-csrf="%s"><h2>Tìm sản phẩm</h2>%s%s</div>' % (
        E(view.csrf),
        chat_thread(view.d.get("chat") or EMPTY, view.now),
        composer(view),
    )
