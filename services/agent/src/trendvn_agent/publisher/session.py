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
        log(
            "\u0110\u0103ng nh\u1eadp TikTok trong c\u1eeda s\u1ed5 v\u1eeba m\u1edf. H\u1ec7 th\u1ed1ng kh\u00f4ng nh\u1eadp m\u1eadt kh\u1ea9u thay b\u1ea1n."
        )
        deadline = time.time() + 60 * minutes
        told = False
        while time.time() < deadline:
            if logged_in(ctx):
                page.wait_for_timeout(4000)
                mismatch = wrong_account(ctx, expected) if expected else None
                if not mismatch:
                    log(
                        "\u0110\u00e3 c\u00f3 phi\u00ean \u0111\u0103ng nh\u1eadp; phi\u00ean ch\u1ec9 l\u01b0u trong h\u1ed3 s\u01a1 tr\u00ecnh duy\u1ec7t ri\u00eang."
                    )
                    _report(account, True)
                    return True
                if not told:
                    log(
                        mismatch
                        + " H\u00e3y \u0111\u0103ng xu\u1ea5t v\u00e0 \u0111\u0103ng nh\u1eadp l\u1ea1i \u0111\u00fang t\u00e0i kho\u1ea3n trong c\u1eeda s\u1ed5 n\u00e0y."
                    )
                    told = True
                page.wait_for_timeout(6000)
            page.wait_for_timeout(2000)
    return False


def trust(minutes=15, account=None):
    """Open the upload page in a visible window so YOU can pass TikTok's human check once. Nothing is uploaded or posted."""
    with chrome(profile_name(account), headless=False, locale="vi-VN", viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(UPLOAD_URL, wait_until="domcontentloaded")
        log(
            "N\u1ebfu TikTok hi\u1ec7n h\u00ecnh x\u00e1c minh, h\u00e3y t\u1ef1 gi\u1ea3i trong c\u1eeda s\u1ed5 v\u1eeba m\u1edf. H\u1ec7 th\u1ed1ng kh\u00f4ng gi\u1ea3i thay b\u1ea1n."
        )
        deadline = time.time() + 60 * minutes
        while time.time() < deadline:
            if page.locator('input[type="file"]').count() and not has_challenge(page):
                page.wait_for_timeout(3000)
                log("Trang t\u1ea3i l\u00ean \u0111\u00e3 s\u1eb5n s\u00e0ng, kh\u00f4ng c\u00f2n y\u00eau c\u1ea7u x\u00e1c minh.")
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
            return {
                "logged_in": False,
                "reason": "Ch\u01b0a \u0111\u0103ng nh\u1eadp. Ch\u1ea1y: ./trendvn tiktok login" + account_flag(account),
            }
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
                return {
                    "logged_in": False,
                    "reason": "Phi\u00ean \u0111\u00e3 h\u1ebft h\u1ea1n. \u0110\u0103ng nh\u1eadp l\u1ea1i: ./trendvn tiktok login"
                    + account_flag(account),
                }
            return {"logged_in": True}
        finally:
            page.close()
