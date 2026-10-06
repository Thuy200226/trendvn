"""Account-scoped reference input and human selection of video/product candidates."""

from ...domain.search_queries import SOURCES
from ..components import field, select, task_panel
from ..format import escape as E


def reference_form(view):
    options = [(a["id"], "@" + a["username"]) for a in view.d["accounts"]]
    return (
        '<form data-search-form class="card stack"><input name="csrf" type="hidden" value="%s">%s%s'
        '<label class="stack">Thông tin sản phẩm (không bắt buộc)<textarea name="text" rows="4" maxlength="12000" '
        'placeholder="Tên, thương hiệu, model, biến thể… hoặc dán đường dẫn sản phẩm/video"></textarea></label>'
        '<div class="search-drop stack" tabindex="0" data-search-drop aria-label="Kéo tệp hoặc dán ảnh vào đây">'
        '<label>Ảnh hoặc tài liệu<input type="file" name="files" multiple accept=".png,.jpg,.jpeg,.webp,.pdf,.docx,.txt"></label>'
        '<p class="small muted">Kéo vào hoặc dán ảnh. Tối đa 3 tệp, 4 MiB/tệp, tổng 8 MiB. Ảnh/PDF dùng Gemini để nhận diện và tạo từ khóa; tên/model bạn nhập được ưu tiên. Ảnh không được gửi vào ô tìm kiếm TikTok.</p>'
        '<ul data-search-files></ul><button type="button" class="ghost" data-search-clear>Bỏ các tệp</button></div>'
        '<p class="small muted">Để trống: video dùng luồng thu thập cũ; sản phẩm dùng danh sách đã đồng bộ của tài khoản.</p>'
        '<p role="status" aria-live="polite" data-search-message></p><button class="go">Tìm và chuyển tới lựa chọn</button></form>'
    ) % (
        view.csrf,
        field("Tài khoản nhận video", select("account", options[0][0] if options else "", options)),
        field("Nguồn video", select("source", "auto", SOURCES)),
    )


def result_card(view, search, item):
    key = item["source_id"]
    selected = next(
        (j for j in search.get("jobs", []) if j["source_id"] == key and j.get("platform") == item.get("platform", "tiktok")), None
    )
    disabled = item["match"]["level"] == "different" or selected and selected["state"] != "search_selected"
    form = (
        '<form method="post" action="/search-select" class="stack"><input type="hidden" name="csrf" value="%s">'
        '<input type="hidden" name="search" value="%s"><input type="hidden" name="source_id" value="%s"><input type="hidden" name="platform" value="%s">'
        '<label class="search-check"><input type="checkbox" name="confirmed" value="yes" required> Tôi đã xem và xác nhận đúng sản phẩm, model và biến thể</label>'
        '<button class="go"%s>Chọn và tải để xử lý</button></form>'
    ) % (view.csrf, E(search["id"]), E(key), E(item.get("platform", "tiktok")), " disabled" if disabled else "")
    status = '<p class="hint">%s · %s</p>' % (E(selected["state_label"]), E(selected["reason"] or "")) if selected else ""
    return (
        '<article class="card stack"><h4>%s</h4><p class="small">%s</p><a href="%s" target="_blank" rel="noopener noreferrer">'
        "Xem nguồn để đối chiếu sản phẩm ↗</a>%s%s</article>"
    ) % (E(item.get("title") or "Kết quả"), E(item["match"]["reason"]), E(item["url"]), status, form)


def render(view):
    names = {a["id"]: a["username"] for a in view.d["accounts"]}
    states = {"pending": "Đang chờ", "running": "Đang tìm", "done": "Chọn kết quả", "error": "Chưa tìm được"}
    cards = []
    for search in view.d.get("searches", []):
        identity = search["identity"]
        description = " · ".join(filter(None, [identity.get(k) for k in ("name", "brand", "model", "variant", "uncertainty")]))
        warnings = " · ".join(identity.get("warnings", []))
        results = "".join(result_card(view, search, i) for i in search["results"])
        if not results and search["state"] == "done":
            results = "<p>Không có ứng viên. Thử thêm tên/model hoặc đường dẫn video cụ thể.</p>"
        queries = identity.get("queries", {})
        preview = "".join(
            '<p class="small">%s: <code>%s</code></p>' % (label, E(queries.get(key, "")))
            for key, label in (("tiktok", "TikTok"), ("douyin", "Douyin"))
            if queries.get(key)
        )
        notices = "".join('<p class="hint">%s</p>' % E(value) for value in (warnings, search["error"], search["note"]) if value)
        retry = retry_form(view, search) if search["state"] in ("error", "done") else ""
        cards.append(
            '<div class="stack search-session"><h3>@%s · %s</h3><p>%s</p><p class="hint">%s</p><p class="small">%s</p>%s</div>'
            % (
                E(names.get(search["account"], "tài khoản đã xóa")),
                E(states[search["state"]]),
                E(description),
                "Tên/model là thông tin đối chiếu, chưa chứng minh video đúng sản phẩm.",
                "Khớp từ khóa/giống hình chưa chứng minh đúng sản phẩm. Hãy xem nguồn trước khi chọn.",
                preview + notices + retry + results,
            )
        )
    return (
        '<p class="hint">Nhập → tìm ứng viên → lựa chọn → tải → xử lý và duyệt như trước.</p>'
        + task_panel(view.tasks)
        + reference_form(view)
        + "".join(cards)
    )


def retry_form(view, search):
    return (
        '<form method="post" action="/search-retry" class="card stack">'
        '<input type="hidden" name="csrf" value="%s"><input type="hidden" name="search" value="%s">'
        '<label>Tên/model để tìm lại<input name="name" maxlength="160" value="%s" required></label>%s'
        '<p class="small muted">Nếu nguồn yêu cầu xác minh, chọn một nguồn và mở cửa sổ để tự đăng nhập/xác minh (tối đa 4 phút), rồi hệ thống tiếp tục lấy kết quả.</p>'
        '<button class="ghost" name="action" value="retry">Tìm lại bằng từ khóa này</button>'
        '<button class="go" name="action" value="open">Mở cửa sổ để tự xác minh và tìm</button></form>'
    ) % (
        view.csrf,
        E(search["id"]),
        E(search["identity"].get("name") or search["identity"].get("query", "")),
        field("Nguồn", select("source", "douyin", SOURCES)),
    )
