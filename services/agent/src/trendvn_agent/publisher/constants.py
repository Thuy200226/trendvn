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


POST_LABELS = re.compile("^\\s*(Post|\u0110\u0103ng|Publish)\\s*$", re.I)


NOT_NOW = re.compile("^\\s*(Not now|Cancel|Later|\u0110\u1ec3 sau|H\u1ee7y|Hu\u1ef7|B\u1ecf qua)\\s*$", re.I)


UPLOADED_HINTS = ("Uploaded", "\u0110\u00e3 t\u1ea3i l\u00ean", "Upload complete", "T\u1ea3i l\u00ean ho\u00e0n t\u1ea5t")


VISIBILITY_LABELS = {
    "public": ("M\u1ecdi ng\u01b0\u1eddi", "Everyone"),
    "friends": ("B\u1ea1n b\u00e8", "Friends"),
    "self": ("Ch\u1ec9 m\u00ecnh b\u1ea1n", "Only me"),
}


POPUP_BUTTONS = (
    "H\u1ee7y",
    "\u0110\u00e3 hi\u1ec3u",
    "Cancel",
    "Got it",
)  # 'Cancel' here answers 'turn on automatic content checks?' with no: that is an account setting, yours to change


CHALLENGE_GRACE = 45  # TikTok sometimes clears a check by itself; only a persistent one pauses publishing


CHALLENGE_TEXT = (
    "Ch\u1ecdn 2 \u0111\u1ed1i t\u01b0\u1ee3ng",
    "Select 2 objects",
    "K\u00e9o thanh tr\u01b0\u1ee3t",
    "Drag the slider",
    "Xoay h\u00ecnh",
    "Rotate the image",
    "Verify to continue",
    "X\u00e1c minh \u0111\u1ec3 ti\u1ebfp t\u1ee5c",
    "Ho\u00e0n th\u00e0nh x\u00e1c minh",
)
