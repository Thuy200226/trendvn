"""Cần xem: what only the owner can decide (TikTok verification, unconfirmed posts, videos held back)."""

import re

from ..cards import review_card
from ..format import ago, escape as E, shown_of


def _challenge(view):
    return (
        '<div class="card alert stack"><h3>🧩 TikTok đang yêu cầu xác minh%s</h3><p>Đăng bài đang <b>tạm dừng</b> để không kích hoạt thêm. '
        "Hãy giải hình xác minh một lần trong cửa sổ Chrome thật:</p>"
        '<p><code>%s</code></p><p class="muted small">Mac: nhấp đúp <code>macos/Xac-minh-TikTok.command</code>. '
        "Xong hệ thống tự đăng tiếp.</p></div>"
    ) % (E(view.challenge_who), E(view.challenge_command))


def _key_rejected():
    return (
        '<div class="card alert stack"><h3>🔑 Khóa Gemini bị Google từ chối</h3><p>Khóa sai, đã thu hồi hoặc thiếu quyền, nên <b>không video nào xử lý được</b>. '
        "Các video vẫn nằm chờ trong hàng đợi, không bị đánh dấu hỏng. Vào <b>Thêm → Cài đặt</b> dán khóa mới "
        "(lấy ở <code>https://aistudio.google.com/apikey</code>); xong hệ thống tự chạy lại.</p></div>"
    )


def _unresolved(view, job):
    """A post that may or may not be on TikTok: which account it was meant for, what it said and since when, so the owner knows where to look."""
    caption = re.sub(r"\s+", " ", re.sub(r"#\w+", "", job.get("caption") or "")).strip() or (job.get("title") or "")
    who = "@" + job["target"] if job.get("target") else "tài khoản mặc định"
    return (
        '<form method="post" action="/resolve" class="card alert stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
        "<h3>🚨 Chưa xác nhận đã đăng: %s</h3>"
        '<p class="small"><b>%s</b> · bấm Đăng %s</p>'
        '<p>Hệ thống đã dừng đăng để không đăng trùng. Mở TikTok của %s kiểm tra rồi chọn:</p><div class="btns">'
        '<button name="outcome" value="published" class="go">Bài đã lên TikTok</button>'
        '<button name="outcome" value="failed" class="ghost">Chưa có, cho phép đăng lại</button></div></form>'
    ) % (view.csrf, E(job["id"]), E(caption[:100]), E(who), E(ago(job.get("updated"), view.now)), E(who))


def render(view):
    d = view.d
    parts = [_challenge(view)] if view.challenge_on else []
    parts += [_key_rejected()] if view.key_rejected else []
    parts += [_unresolved(view, job) for job in d["unresolved"]]
    held = view.counts.get("needs_review", 0)
    if held > len(d["review"]):
        parts.append(
            '<p class="muted small">Đang hiện %s video bị giữ lại: xử lý bớt rồi tải lại trang để thấy phần còn lại.</p>'
            % E(shown_of(len(d["review"]), held))
        )
    parts += [review_card(dict(job), view.csrf) for job in d["review"]]
    if not parts:
        parts = [
            '<div class="card empty stack"><p>Không có việc nào cần bạn xem. 🎉</p><p class="small">Video đang chờ xử lý nằm ở tab '
            '<a href="#queue">Hàng đợi</a>; video đã xử lý xong nằm ở tab <a href="#publish">Đăng bài</a>.</p></div>'
        ]
    return "<h2>Cần xem</h2>" + "".join(parts)
