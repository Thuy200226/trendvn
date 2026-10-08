"""Short user-facing explanations; technical evidence stays in the diagnostic journal."""

import re

from .labels import TEXT_LIMIT, VIETNAMESE_LETTER, vi_error, vi_reason

TECHNICAL = re.compile(
    r"Locator\.|Call log:|Traceback|\b(?:TimeoutError|HTTPError|ConnectionError|Exception)\b|"
    r"waiting for locator|\b(?:SELECT|INSERT|UPDATE)\b.{1,200}?\b(?:FROM|INTO|SET)\b|\{[\s\"']|/Users/|/data/|/tmp/",
    re.I | re.S,
)
FALLBACK = "Chưa hoàn tất thao tác. Dữ liệu được giữ; xem chi tiết trong Thêm → Nhật ký."


def user_message(text, failed=False):
    """Translate known failures, preserve useful Vietnamese instructions and bound noisy output."""
    text = str(text or "")[:TEXT_LIMIT]
    low = text.lower()
    if "gemini" in low and any(word in low for word in ("503", "504", "timeout", "timed out", "hết thời gian")):
        return "Gemini đang bận. Video được giữ trong hàng chờ để thử lại."
    if any(word in low for word in ("connection refused", "urlopen error", "failed to establish")):
        return "Chưa kết nối được agent trên máy. Video được giữ; kiểm tra tình trạng trong Thêm."
    if "busy" in low or "agent đang bận" in low:
        return "Trình duyệt đang bận với việc khác. Chờ việc đó xong rồi thử lại."
    text = vi_error(vi_reason(text))
    technical = TECHNICAL.search(text)
    if technical:
        prefix = text[: technical.start()].strip(" .:\n")
        text = prefix if VIETNAMESE_LETTER.search(prefix) else FALLBACK
    if failed and not VIETNAMESE_LETTER.search(text):
        text = FALLBACK
    return text[:450] or (FALLBACK if failed else "")
