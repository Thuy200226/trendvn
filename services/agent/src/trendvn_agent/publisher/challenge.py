"""TikTok's human-verification pages: detect them, never solve them."""

import time

from .constants import CHALLENGE_GRACE, CHALLENGE_TEXT


class Challenge(Exception):
    """TikTok asked for human verification. We never solve it: stop, report, let the owner pass it once with `trust`."""


def has_challenge(page):
    try:
        if page.locator('#captcha_container, .captcha_verify_container, [class*="captcha" i]').count():
            return True
        text = page.inner_text("body", timeout=3000)
    except Exception:
        return False
    return any(w in text for w in CHALLENGE_TEXT)


def wait_for_upload_ui(page, seconds=150):
    """TikTok Studio needs 20-30s to build its upload page. Returns (frame, file_input); raises Challenge if a CAPTCHA persists."""
    deadline = time.time() + seconds
    challenge_since = None
    while time.time() < deadline:
        for frame in [page] + list(page.frames):
            try:
                loc = frame.locator('input[type="file"]')
                if loc.count():
                    return frame, loc.first
            except Exception:
                continue  # TikTok creates and destroys child frames while the page builds itself
        if has_challenge(page):
            challenge_since = challenge_since or time.time()
            if time.time() - challenge_since > CHALLENGE_GRACE:
                raise Challenge("TikTok yêu cầu xác minh (CAPTCHA)")
        else:
            challenge_since = None
        page.wait_for_timeout(1500)
    return page, None
