"""Vietnamese wording shown in the dashboard: states, sources, components, events, and the plain-language version of internal reasons."""

import re

from ..domain.platforms import REGISTRY

STATE_LABELS = {
    "search_selected": "Chờ tải video đã chọn",
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
    "search_selected": "warn",
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
    "delete_requested": "Bạn yêu cầu xóa bài TikTok",
    "delete_checked_present": "Bạn đã kiểm tra bài TikTok vẫn còn",
    "delete_checked_deleted": "Bạn đã kiểm tra bài TikTok đã xóa",
    "post_deleted": "Đã xóa bài TikTok",
    "post_failed": "Chưa xóa được bài TikTok",
    "post_unknown": "Chưa xác nhận kết quả xóa bài",
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
    "account_added": "Thêm tài khoản TikTok",
    "account_updated": "Sửa tài khoản TikTok",
    "account_deleted": "Xóa tài khoản TikTok",
    "caption_edited": "Bạn sửa mô tả",
    "challenge_on": "TikTok đòi xác minh: tạm dừng đăng",
    "challenge_off": "Đã giải xác minh: đăng lại bình thường",
    "expired": "Quá hạn, hệ thống bỏ",
    "publish_deferred": "Hoãn đăng (không phải lỗi của video)",
    "operator_retry": "Bạn đưa về sẵn sàng đăng",
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
    ("Invalid audio classification", "Gemini trả loại âm thanh không hợp lệ"),
    ("Invalid confidence", "Gemini trả độ chắc chắn không hợp lệ"),
    ("Invalid segments", "Gemini trả phụ đề không hợp lệ"),
    ("Invalid subtitle time", "Gemini trả mốc thời gian phụ đề không hợp lệ"),
    ("Invalid translated segment", "Gemini trả bản dịch phụ đề không hợp lệ"),
    ("Music-only classification conflicts with speech", "Gemini xếp là chỉ có nhạc nhưng video lại có lời nói: cần bạn xem"),
    ("On-screen information requires translation", "Video có chữ quan trọng trên màn hình mà chưa có bản dịch: cần bạn xem"),
    ("duplicate key", "Gemini trả dữ liệu bị lặp khóa nên không đọc được"),
    ("Analysis proxy exceeds", "Bản xem trước gửi Gemini quá nặng (hơn 12 MB): video quá dài hoặc quá nặng"),
    ("Source file changed after attachment", "File video bị đổi sau khi tải về: cần bạn xem"),
    ("Gemini HTTP", "Gemini báo lỗi khi phân tích video này (có thể thử lại bằng nút Duyệt)"),
)


VIETNAMESE_LETTER = re.compile(r"[àáạảãâăấầẩẫậắằẳẵặèéẹẻẽêếềểễệìíịỉĩòóọỏõôốồổỗộơớờởỡợùúụủũưứừửữựỳýỵỷỹđ]", re.I)


def vi_reason(text):
    """Plain-language version of an internal reason (unknown reasons, and ones already written in Vietnamese, are shown as they are:
    a Vietnamese sentence that quotes Google's English after a colon must not lose itself to the table entry for that English)."""
    if text and VIETNAMESE_LETTER.search(text):
        return text
    for fragment, vietnamese in REASONS:
        if text and fragment in text:
            return vietnamese
    return text or ""


# the settings the owner types a number for, named as on the dashboard
FIELD_NAMES = {
    "daily_limit": "Số bài tối đa mỗi ngày",
    "gemini_daily_limit": "Hạn mức gọi Gemini mỗi 24 giờ",
    "min_publish_gap": "Giãn cách giữa hai bài (giây)",
    "max_age_days": "Số ngày tối đa của video",
    "max_duration": "Độ dài tối đa của video (giây)",
    "max_candidates_per_scan": "Số video tải mỗi lần quét",
    "max_backlog": "Số video chờ tối đa",
    "window start": "Giờ bắt đầu của giờ vàng",
    "window end": "Giờ kết thúc của giờ vàng",
}


def _integer(match):
    name = match.group(1)
    threshold = re.fullmatch(r"(min_views|min_likes)\.(\w+)", name)
    label = FIELD_NAMES.get(name) or (
        "%s (%s)" % ("Lượt xem tối thiểu" if threshold.group(1) == "min_views" else "Số tim tối thiểu", threshold.group(2))
        if threshold
        else name
    )
    return "%s phải là số nguyên từ %s đến %s" % (label, match.group(2), match.group(3))


# (regex of the internal English error, the Vietnamese text or a function of the match): messages of forms and buttons
ERRORS = (
    (re.compile(r"(\S[\w. ]*?) must be an integer between (\S+) and (\S+)"), _integer),
    (re.compile(r"Settings must be an object"), "Dữ liệu cài đặt không hợp lệ"),
    (re.compile(r"audio_confidence must be"), "Độ chắc chắn tối thiểu của Gemini phải từ 0,5 đến 0,99"),
    (re.compile(r"post_windows: at most"), "Tối đa 6 khung giờ vàng"),
    (re.compile(r"post_windows entries"), "Mỗi giờ vàng gồm giờ bắt đầu và giờ kết thúc"),
    (re.compile(r"window start must be before end"), "Giờ bắt đầu phải nhỏ hơn giờ kết thúc"),
    (re.compile(r"Invalid TikTok username"), "Tên tài khoản TikTok không hợp lệ (chỉ gồm chữ, số, dấu chấm và gạch dưới)"),
    (re.compile(r"visibility must be"), "Chế độ hiển thị phải là công khai, bạn bè hoặc chỉ mình tôi"),
    (re.compile(r"Invalid model name"), "Tên model không hợp lệ"),
    (re.compile(r"caption_style must be"), "Kiểu mô tả phải là giật tít hoặc điềm đạm"),
    (re.compile(r"^\S+ must be one of"), "Giá trị không nằm trong các lựa chọn cho phép"),
    (re.compile(r"Invalid voice name"), "Tên giọng đọc không hợp lệ"),
    (re.compile(r"^\S+ must be true or false"), "Công tắc chỉ nhận bật hoặc tắt"),
    (re.compile(r"needs per-platform numbers"), "Ngưỡng cần là số cho từng nền tảng"),
    (re.compile(r"Setting cannot be changed here"), "Cài đặt này không đổi được ở đây"),
    (re.compile(r"Invalid processing terminal state|Invalid fields|Invalid action"), "Thao tác không hợp lệ"),
    (re.compile(r"Stale (publish )?lease"), "Việc này đã được nhận lại ở nơi khác; hãy tải lại trang rồi thử lại"),
    (
        re.compile(r"Job is not awaiting confirmation"),
        "Bài này không còn ở trạng thái chờ xác nhận (đã được xử lý ở nơi khác); tải lại trang",
    ),
    (re.compile(r"Invalid (publish )?(outcome|URL)|Unknown component"), "Dữ liệu không hợp lệ"),
    (re.compile(r"Job not found"), "Không tìm thấy video này (có thể đã bị dọn)"),
    (re.compile(r"Job cannot be rejected in this state"), "Video đang ở trạng thái không bỏ được"),
    (re.compile(r"Nothing to approve in this state"), "Video này không có gì để duyệt ở trạng thái hiện tại"),
    (re.compile(r"Source file is gone; cannot reprocess"), "File video gốc đã bị dọn nên không xử lý lại được"),
    (re.compile(r"Gemini key is required to enable processing"), "Cần nhập khóa Gemini trước khi bật xử lý video"),
    (re.compile(r"items must be a list"), "Dữ liệu thống kê không hợp lệ"),
)


def vi_error(text):
    """Plain-language version of an error message from a form or a button (Vietnamese and unknown messages are returned as they are)."""
    if re.match(r"Gemini HTTP|Media operation failed", text or ""):
        return text  # an error of an outside service: its own words, not a guess about which setting it was
    for pattern, vietnamese in ERRORS:
        match = pattern.search(text or "")
        if match:
            return vietnamese(match) if callable(vietnamese) else vietnamese
    return text or ""
