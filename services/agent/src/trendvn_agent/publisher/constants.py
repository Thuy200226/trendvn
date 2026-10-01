"""Selectors, labels and timings of the TikTok Studio upload page."""

import os
import re
import sys

from ..config import ENV

UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload?from=upload"


def wants_window():
    """A real, visible Chrome window is the honest default wherever a screen exists: TikTok challenges hidden automated browsers far
    more often, and the owner can solve a check on the spot. TRENDVN_PUBLISH_HEADED=0/1 overrides."""
    forced = ENV.get("TRENDVN_PUBLISH_HEADED")
    if forced in ("0", "1"):
        return forced == "1"
    return sys.platform in ("darwin", "win32") or bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


HEADED = wants_window()


LOGIN_URL = "https://www.tiktok.com/login"


POST_LABELS = re.compile(r"^\s*(Post|Đăng|Publish)\s*$", re.I)


NOT_NOW = re.compile(r"^\s*(Not now|Cancel|Later|Để sau|Hủy|Huỷ|Bỏ qua)\s*$", re.I)


UPLOADED_HINTS = ("Uploaded", "Đã tải lên", "Upload complete", "Tải lên hoàn tất")


VISIBILITY_LABELS = {"public": ("Mọi người", "Everyone"), "friends": ("Bạn bè", "Friends"), "self": ("Chỉ mình bạn", "Only me")}


POPUP_BUTTONS = (
    "Hủy",
    "Đã hiểu",
    "Cancel",
    "Got it",
)  # 'Hủy' here answers 'turn on automatic content checks?' with no: that is an account setting, yours to change


CHALLENGE_GRACE = 45  # TikTok sometimes clears a check by itself; only a persistent one pauses publishing


CHALLENGE_TEXT = (
    "Chọn 2 đối tượng",
    "Select 2 objects",
    "Kéo thanh trượt",
    "Drag the slider",
    "Xoay hình",
    "Rotate the image",
    "Verify to continue",
    "Xác minh để tiếp tục",
    "Hoàn thành xác minh",
)
