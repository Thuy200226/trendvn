"""Sign in once yourself, pass TikTok's check once, and check the session."""

import time

from ..browser import chrome
from ..log import log
from ..worker_client import worker
from .challenge import has_challenge
from .constants import HEADED, LOGIN_URL, UPLOAD_URL
from .profile import account_flag, logged_in, profile_name, wrong_account


def _report(account, ok):
    from .jobs import report_login

    report_login(account, ok)


def login(minutes=10, account=None, expected=None):
    """Open a visible window and wait (default 10 minutes) for you to finish signing in yourself. With `expected` (the account's TikTok
    name) it only counts once the window is signed in as that account, so a wrong sign-in can be corrected before the window closes."""
    with chrome(profile_name(account), headless=False, locale="vi-VN", viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        log("Đăng nhập TikTok trong cửa sổ vừa mở. Hệ thống không nhập mật khẩu thay bạn.")
        deadline = time.time() + 60 * minutes
        told = False
        while time.time() < deadline:
            if logged_in(ctx):
                page.wait_for_timeout(4000)
                mismatch = wrong_account(ctx, expected) if expected else None
                if not mismatch:
                    log("Đã có phiên đăng nhập; phiên chỉ lưu trong hồ sơ trình duyệt riêng.")
                    _report(account, True)
                    return True
                if not told:
                    log(mismatch + " Hãy đăng xuất và đăng nhập lại đúng tài khoản trong cửa sổ này.")
                    told = True
                page.wait_for_timeout(6000)
            page.wait_for_timeout(2000)
    return False


def trust(minutes=15, account=None):
    """Open the upload page in a visible window so YOU can pass TikTok's human check once. Nothing is uploaded or posted."""
    with chrome(profile_name(account), headless=False, locale="vi-VN", viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        log("Nếu TikTok hiện hình xác minh, hãy tự giải trong cửa sổ vừa mở. Hệ thống không giải thay bạn.")
        deadline = time.time() + 60 * minutes
        while time.time() < deadline:
            if page.locator('input[type="file"]').count() and not has_challenge(page):
                page.wait_for_timeout(3000)
                log("Trang tải lên đã sẵn sàng, không còn yêu cầu xác minh.")
                try:
                    worker(
                        "/api/publisher/challenge", {"active": False, "account": account or "main"}
                    )  # resumes on its own, if it was this account's
                except Exception:
                    pass
                return True
            page.wait_for_timeout(2000)
    return False


def session_status(deep=False, account=None, expected=None):
    """Shallow (default, used by the schedule): is there a login cookie? No window opens. Deep (CLI `status`): load Studio and confirm.
    expected: the TikTok handle the profile must be signed in as; a profile signed in as somebody else is reported as not signed in."""
    with chrome(profile_name(account), locale="vi-VN", headless=not (deep and HEADED)) as ctx:
        if not logged_in(ctx):
            return {"logged_in": False, "reason": "Chưa đăng nhập. Chạy: ./trendvn tiktok login" + account_flag(account)}
        if expected:
            mismatch = wrong_account(ctx, expected)
            if mismatch:
                return {"logged_in": False, "reason": mismatch}
        if not deep:
            return {"logged_in": True}
        page = ctx.new_page()
        try:
            page.goto(UPLOAD_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(6000)
            if "/login" in page.url:
                return {"logged_in": False, "reason": "Phiên đã hết hạn. Đăng nhập lại: ./trendvn tiktok login" + account_flag(account)}
            return {"logged_in": True}
        finally:
            page.close()
