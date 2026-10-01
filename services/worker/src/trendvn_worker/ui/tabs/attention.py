"""Cần xem: what only the owner can decide (TikTok verification, unconfirmed posts, videos held back)."""

from ..cards import review_card
from ..format import escape as E


def _challenge():
    return (
        '<div class="card alert stack"><h3>🧩 TikTok đang yêu cầu xác minh</h3><p>Đăng bài đang <b>tạm dừng</b> để không kích hoạt thêm. '
        "Hãy giải hình xác minh một lần trong cửa sổ Chrome thật:</p>"
        '<p><code>./trendvn tiktok trust</code></p><p class="muted small">Mac: nhấp đúp <code>macos/Xac-minh-TikTok.command</code>. '
        "Xong hệ thống tự đăng tiếp.</p></div>"
    )


def _unresolved(csrf, job):
    return (
        '<form method="post" action="/resolve" class="card alert stack"><input type="hidden" name="csrf" value="%s"><input type="hidden" name="id" value="%s">'
        '<h3>🚨 Chưa xác nhận đã đăng: %s</h3><p>Hệ thống đã dừng đăng để không đăng trùng. Mở TikTok kiểm tra rồi chọn:</p><div class="btns">'
        '<button name="outcome" value="published" class="go">Bài đã lên TikTok</button>'
        '<button name="outcome" value="failed" class="ghost">Chưa có, cho phép đăng lại</button></div></form>'
    ) % (csrf, E(job["id"]), E((job["title"] or "")[:100]))


def render(view):
    d = view.d
    parts = [_challenge()] if view.challenge_on else []
    parts += [_unresolved(view.csrf, job) for job in d["unresolved"]]
    parts += [review_card(dict(job), view.csrf) for job in d["review"]]
    if not parts:
        parts = [
            '<div class="card empty stack"><p>Không có việc nào cần bạn xem. 🎉</p><p class="small">Video đang chờ xử lý nằm ở tab '
            '<a href="#queue">Hàng đợi</a>; video đã xử lý xong nằm ở tab <a href="#publish">Đăng bài</a>.</p></div>'
        ]
    return "<h2>Cần xem</h2>" + "".join(parts)
