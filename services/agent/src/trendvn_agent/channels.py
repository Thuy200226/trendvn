"""The channels the owner searches on (TikTok, Douyin): where each account's session lives, how to tell it is signed in, and the visible
window to sign in with. The agent never types a password: the owner signs in themselves (QR code, phone, whatever the site offers)."""

import os
import re
import sys
import time
from pathlib import Path

from .browser import chrome
from .log import log
from .publisher.constants import wants_window
from .publisher.profile import profile_name
from .worker_client import worker

LOGIN_MINUTES = 10
DOUYIN_HOME = "https://www.douyin.com/jingxuan"
NAMES = {"tiktok": "TikTok", "douyin": "Douyin", "kuaishou": "Kuaishou", "instagram": "Instagram"}
SITES = {"tiktok": "tiktok.com", "douyin": "douyin.com", "kuaishou": "kuaishou.com", "instagram": "instagram.com"}
# Cookie presence selects potentially usable profiles; Douyin requires page evidence before reporting authentication.
SESSION_COOKIES = {
    "tiktok": ("sessionid",),
    "douyin": ("sessionid", "sessionid_ss", "sid_tt", "sid_guard"),
    "kuaishou": ("kuaishou.server.web_st",),
    "instagram": ("sessionid",),
}
LOCALES = {"tiktok": "vi-VN", "douyin": "zh-CN", "kuaishou": "zh-CN", "instagram": "en-US"}
ACCOUNT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,23}")
NO_SCREEN = {
    "tiktok": "Máy chạy TrendVN không có màn hình nên không mở được cửa sổ đăng nhập. Đăng nhập bằng ./trendvn tiktok login trên máy có màn hình.",
    "douyin": "Máy chạy TrendVN không có màn hình nên không mở được cửa sổ đăng nhập Douyin. Hãy chạy TrendVN trên máy có màn hình.",
}
NO_SCREEN.update({c: "Máy chạy TrendVN cần màn hình để bạn đăng nhập " + NAMES[c] for c in ("kuaishou", "instagram")})


class SignedOut(ValueError):
    """The channel asked for a signed-in session and the profile has none."""

    state = "out"


class Wall(ValueError):
    """A verification page (captcha, slider) is in the way: only the owner may pass it."""

    state = "wall"


def profile(channel, account_id):
    """The Chrome profile folder: TikTok shares the account's publishing profile (one sign-in serves both), Douyin has its own."""
    if channel not in NAMES:
        raise ValueError("Kênh không hợp lệ")
    if channel == "tiktok":
        return profile_name(account_id)
    if not ACCOUNT_ID.fullmatch(str(account_id)):
        raise ValueError("Mã tài khoản không hợp lệ")
    return ("search-cn-" if channel == "douyin" else "search-" + channel + "-") + account_id


def _on_site(domain, site):
    host = str(domain).lstrip(".").lower()
    return host == site or host.endswith("." + site)


def signed_in(channel, cookies):
    """Does this cookie jar hold a signed-in session of the channel? A cookie counts only from the channel's own site (never a look-alike
    host), with a value that is not empty."""
    if channel not in SITES:
        raise ValueError("Kênh không hợp lệ")
    for cookie in cookies:
        if not _on_site(cookie["domain"], SITES[channel]) or not cookie.get("value"):
            continue
        if cookie["name"] in SESSION_COOKIES[channel] or (
            channel == "douyin" and cookie["name"] == "LOGIN_STATUS" and cookie["value"] == "1"
        ):
            return True
    return False


def display_alive():
    """Is there a screen to open a window on right now? The service's DISPLAY was fixed when it was installed: a session that has gone
    away since leaves a name with nothing behind it."""
    if sys.platform in ("darwin", "win32"):
        return True
    shown = re.fullmatch(r":(\d+)(?:\.\d+)?", os.environ.get("DISPLAY", ""))
    if shown and Path("/tmp/.X11-unix/X" + shown.group(1)).exists():
        return True
    wayland, runtime = os.environ.get("WAYLAND_DISPLAY", ""), os.environ.get("XDG_RUNTIME_DIR", "")
    return bool(wayland and runtime and (Path(runtime) / wayland).exists())


def window_ok():
    """Searches and sign-ins run in a real window when this machine has a screen (TRENDVN_PUBLISH_HEADED=0 forces hidden)."""
    return wants_window() and display_alive()


def report(account_id, channel, state, who="", expected_username=None):
    """Tell the worker what was found. Bookkeeping only: it never fails a search or a sign-in."""
    try:
        payload = {"account": account_id, "channel": channel, "state": state, "who": who}
        if expected_username is not None:
            payload["expected_username"] = expected_username
        worker("/api/channel/report", payload, timeout=15)
    except Exception as error:
        log("could not report the %s sign-in state: %s" % (channel, str(error)[:120]))


def read(account, channel):
    """Is the profile signed in on the channel? Reads the cookies kept in it without opening any page, so it is quick and quiet. It only
    knows that a session cookie is present: not whose it is."""
    with chrome(profile(channel, account["id"]), locale=LOCALES[channel], headless=True) as ctx:
        return signed_in(channel, ctx.cookies())


def check(account, channel, report_result=True):
    if channel == "douyin":
        from .douyin_session import probe

        with chrome(profile(channel, account["id"]), locale=LOCALES[channel], region="CN", headless=not window_ok()) as ctx:
            state, who = probe(ctx, DOUYIN_HOME, owner_wait=False)
        result = {"logged_in": state == "ok", "state": state, "who": who, "channel": channel}
    else:
        ok = read(account, channel)
        result = {"logged_in": ok, "channel": channel}
    if report_result:
        report(
            account["id"],
            channel,
            result.get("state", "ok" if result["logged_in"] else "out"),
            **({"who": result["who"]} if result.get("who") else {}),
            expected_username=account["username"],
        )
    return result


def _open_douyin_panel(page):
    """Open Douyin's sign-in panel (the QR code) for the owner. A click on a public button: nothing is typed or submitted."""
    try:
        page.get_by_text("登录", exact=True).first.click(timeout=4000)
    except Exception:
        pass  # the owner can click it themselves


def _session_ready(channel, page, ctx):
    """A saved cookie does not mean the owner has finished a verification page."""
    from urllib.parse import urlsplit

    location = urlsplit(page.url)
    if location.scheme != "https" or not _on_site(location.hostname or "", SITES[channel]):
        return False
    if not signed_in(channel, ctx.cookies()):
        return False
    if channel == "douyin":
        return False  # Douyin requires Session's page evidence, never this generic cookie helper
    if any(part in page.url for part in ("/challenge", "/checkpoint", "/login")):
        return False
    nodes = page.locator('[id*="captcha"], [class*="captcha"], [class*="verify-wrap"]')
    return not any(nodes.nth(i).is_visible() for i in range(nodes.count()))


def _navigate_login(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass  # keep this persistent-profile window open so the owner can reload


def _pause_login(ctx):
    """Transient navigation errors do not close the window; an owner-closed context ends the wait."""
    try:
        shown = [p for p in ctx.pages if not p.is_closed()]
        if shown:
            shown[0].wait_for_timeout(2000)
            return True
    except Exception:
        pass
    return False


def _douyin_window(account, minutes):
    """Wait for actual owner-account evidence, not a cookie; closing before it appears is cancellation."""
    from .douyin_session import Session

    deadline = None if minutes is None else time.time() + 60 * minutes
    with chrome(profile("douyin", account["id"]), locale=LOCALES["douyin"], region="CN", headless=False, viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        session = Session(ctx)  # includes account responses from owner-opened tabs
        _navigate_login(page, DOUYIN_HOME)
        try:
            page.wait_for_timeout(2500)
            if session.state(page) == "out":
                _open_douyin_panel(page)
        except Exception:
            pass  # login can redirect before the first state check; keep waiting below
        log("Đăng nhập Douyin trong cửa sổ vừa mở. Hệ thống chờ bạn, không nhập mật khẩu thay bạn.")
        while deadline is None or time.time() < deadline:
            try:
                shown = [p for p in ctx.pages if not p.is_closed()]
                if not shown:
                    return False
                for active in shown:
                    if session.state(active) == "ok":
                        active.wait_for_timeout(2000)
                        if session.state(active) == "ok":
                            return True
            except Exception:
                pass  # account login can navigate; keep the owner's window open
            if not _pause_login(ctx):
                return False
    return False


def _source_window(account, channel, minutes):
    deadline = None if minutes is None else time.time() + 60 * minutes
    region = "CN" if channel == "kuaishou" else "US"
    with chrome(profile(channel, account["id"]), locale=LOCALES[channel], region=region, headless=False, viewport=(1280, 900)) as ctx:
        page = ctx.new_page()
        _navigate_login(page, "https://www." + SITES[channel] + "/")
        while deadline is None or time.time() < deadline:
            try:
                if not ctx.pages or all(p.is_closed() for p in ctx.pages):
                    return
                if _session_ready(channel, page, ctx):
                    page.wait_for_timeout(4000)
                    return
            except Exception:
                pass
            if not _pause_login(ctx):
                return


def login(account, channel, minutes=LOGIN_MINUTES, report_result=True):
    """Open a visible window for the owner to sign in to the channel and wait for it (`minutes=None` has no deadline). The answer is read back from the
    profile once the window is gone, so a session that did not survive the window closing does not count. {'ok','who','reason','channel'}"""
    if not window_ok():
        raise ValueError(NO_SCREEN[channel])
    verified = None
    try:
        if channel == "tiktok":
            from .publisher.session import login as tiktok_login

            ok = bool(tiktok_login(minutes=minutes, account=account["id"], expected=account["username"], report_result=report_result))
        elif channel == "douyin":
            ok = _douyin_window(account, minutes)
        else:
            _source_window(account, channel, minutes)
            ok = True
        verified = check(account, channel, report_result=False) if ok and channel == "douyin" else None
        ok = bool(verified["logged_in"]) if verified else ok and read(account, channel)
        reason = "" if ok else "Cửa sổ đã đóng trước khi lưu được phiên %s. Bấm Đăng nhập để mở lại." % NAMES[channel]
        if verified and not ok:
            reason = {
                "wall": "Phiên Douyin đã lưu nhưng trang cần bạn xác minh. Mở tìm Douyin để hệ thống chờ bạn trong chính hồ sơ này.",
                "unknown": "Chưa đọc được bằng chứng phiên khi mở lại Douyin; hồ sơ được giữ. Bấm Kiểm tra hoặc mở tìm để tiếp tục.",
                "out": "Douyin chưa xác nhận đăng nhập khi mở lại hồ sơ. Hãy mở Đăng nhập và hoàn tất trong cửa sổ đó.",
            }.get(verified["state"], reason)
        if channel == "tiktok" and not ok:
            reason = (
                "Chưa thấy đăng nhập TikTok đúng @%s trước khi cửa sổ đóng (cần đăng nhập đúng tài khoản này). Bấm Đăng nhập để mở lại."
                % account["username"]
            )
    except Exception as error:  # the window was closed, or a page would not load
        log("sign-in window to %s ended early: %s" % (channel, str(error)[:120]))
        ok, reason = False, "Cửa sổ đăng nhập đã bị đóng hoặc không mở được trang %s. Bấm Đăng nhập để mở lại." % NAMES[channel]
    who = account["username"] if ok and channel == "tiktok" else (verified or {}).get("who", "")
    if report_result:
        state = (verified or {}).get("state", "ok" if ok else "out")
        report(account["id"], channel, state, who, expected_username=account["username"])
    return {"ok": ok, "who": who, "reason": reason, "channel": channel, **({"state": verified["state"]} if verified else {})}
