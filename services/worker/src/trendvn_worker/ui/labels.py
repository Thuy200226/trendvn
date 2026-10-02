"""Vietnamese wording shown in the dashboard: states, sources, components, events, and the plain-language version of internal reasons."""

from ..domain.platforms import REGISTRY

STATE_LABELS = {
    "baseline": "Mốc ban đầu",
    "candidate": "Ứng viên",
    "queued": "Chờ xử lý",
    "processing": "Đang xử lý",
    "awaiting_approval": "Chờ bạn duyệt",
    "ready": "Sẵn sàng đăng",
    "publishing": "Đang đăng",
    "published": "Đã đăng",
    "needs_review": "Cần duyệt",
    "publish_unknown": "Chưa xác nhận",
    "duplicate": "Trùng",
    "failed": "Lỗi",
    "rejected": "Đã bỏ",
}
STATE_TONE = {
    "published": "good",
    "ready": "good",
    "awaiting_approval": "warn",
    "needs_review": "warn",
    "publish_unknown": "bad",
    "failed": "bad",
    "processing": "info",
    "publishing": "info",
    "queued": "info",
    "candidate": "mute",
    "baseline": "mute",
    "duplicate": "mute",
    "rejected": "mute",
}
PLATFORM = {p.id: (p.name, p.country) for p in REGISTRY}
COMPONENT = {
    "connected": ("Hoạt động", "good"),
    "not_connected": ("Chưa kết nối", "mute"),
    "stale": ("Lâu chưa báo cáo", "warn"),
    "error": ("Cần chú ý", "bad"),
}
ROUTE_LABEL = {"vietsub": "Vietsub", "voiceover": "Lồng tiếng + Vietsub", "original": "Giữ nguyên"}
VISIBILITY_LABEL = {"public": "Công khai", "friends": "Bạn bè", "self": "Chỉ mình tôi"}

EVENT_LABELS = {
    "processing": "Bắt đầu xử lý",
    "queued": "Đã tải, chờ xử lý",
    "ready": "Đã dựng, sẵn sàng đăng",
    "awaiting_approval": "Chờ bạn duyệt",
    "needs_review": "Cần bạn duyệt",
    "publishing": "Đang đăng",
    "publish_published": "Đã đăng thành công",
    "publish_unknown": "Đăng chưa xác nhận",
    "publish_failed": "Đăng chưa thành công",
    "publish_duplicate": "Bỏ vì trùng bài đã có",
    "candidate": "Phát hiện video mới",
    "failed": "Lỗi",
    "duplicate": "Trùng video đã có",
    "released": "Xếp lại hàng đợi",
    "media_failed": "Tải video lỗi",
    "operator_approve": "Bạn đã duyệt",
    "operator_reject": "Bạn đã bỏ",
    "resolved_published": "Xác nhận đã đăng",
    "resolved_failed": "Xác nhận chưa đăng",
    "settings": "Đổi cài đặt",
}

# (fragment of the internal English reason, what to tell the owner)
REASONS = (
    ("Audio needs review", "Gemini chưa đủ chắc chắn về loại âm thanh"),
    (
        "Sensitive content",
        "Chạm giới hạn cứng (tình dục, trẻ em gặp nguy, máu me thật, thù ghét, tự hại/tội phạm, lời khuyên nguy hiểm, đời tư): cần bạn quyết định",
    ),
    ("Off-topic", "Nội dung không thuộc loại giải trí"),
    ("Possible visual duplicate", "Có thể trùng với một video đã xử lý"),
    ("Video duration outside", "Thời lượng ngoài giới hạn cho phép"),
    ("Speech detected without transcript", "Có lời nói nhưng không chép được lời"),
    ("Subtitle timestamps", "Mốc thời gian phụ đề không hợp lệ"),
    ("Topic/sensitivity missing", "Gemini không trả đủ thông tin chủ đề"),
    (
        "Gemini output truncated",
        "Mô hình Gemini viết lan man quá dài nên câu trả lời bị cắt dở (lỗi của mô hình, không phải của video); bấm Duyệt để phân tích lại",
    ),
    ("Gemini did not return valid", "Gemini trả dữ liệu không đọc được"),
    ("Gemini returned no analysis", "Gemini từ chối hoặc không trả lời video này"),
    ("Invalid caption", "Gemini không viết được mô tả cho video"),
    ("Processing interrupted", "Xử lý bị gián đoạn"),
    ("Local rolling 24-hour limit", "Hết hạn mức Gemini trong 24 giờ; sẽ tự xử lý lại"),
    ("Initial observation only", "Chỉ ghi mốc ban đầu"),
    ("Rejected by operator", "Bạn đã bỏ video này"),
    ("Approved by operator", "Bạn đã duyệt"),
)


def vi_reason(text):
    """Plain-language version of an internal reason (unknown reasons are shown as they are)."""
    for fragment, vietnamese in REASONS:
        if text and fragment in text:
            return vietnamese
    return text or ""
