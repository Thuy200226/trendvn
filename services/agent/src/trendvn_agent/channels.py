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
DOUYIN_HOME = "https://www.douyin.com/"
NAMES = {"tiktok": "TikTok", "douyin": "Douyin", "kuaishou": "Kuaishou", "instagram": "Instagram"}
SITES = {"tiktok": "tiktok.com", "douyin": "douyin.com", "kuaishou": "kuaishou.com", "instagram": "instagram.com"}
# What a signed-in visitor has and a guest has not (Douyin's names are a best reading: a guest was measured to carry none of them, a signed-in
# one could not be measured without the owner's account; the dashboard says so and a search that works puts the state right).
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


def report(account_id, channel, state, who=""):
    """Tell the worker what was found. Bookkeeping only: it never fails a search or a sign-in."""
    try:
        worker("/api/channel/report", {"account": account_id, "channel": channel, "state": state, "who": who}, timeout=15)
    except Exception as error:
        log("could not report the %s sign-in state: %s" % (channel, str(error)[:120]))


def read(account, channel):
    """Is the profile signed in on the channel? Reads the cookies kept in it without opening any page, so it is quick and quiet. It only
    knows that a session cookie is present: not whose it is."""
    with chrome(profile(channel, account["id"]), locale=LOCALES[channel], headless=True) as ctx:
        return signed_in(channel, ctx.cookies())


def check(account, channel):
    ok = read(account, channel)
    report(account["id"], channel, "ok" if ok else "out")
    return {"logged_in": ok, "channel": channel}


def _open_douyin_panel(page):
    """Open Douyin's sign-in panel (the QR code) for the owner. A click on a public button: nothing is typed or submitted."""
    try:
        page.get_by_text("登录", exact=True).first.click(timeout=4000)
    except Exception:
        pass  # the owner can click it themselves


def _douyin_window(account, minutes):
    """Keep a window open on Douyin until the owner has signed in, closes it, or the time is up."""
    deadline = time.time() + 60 * minutes
    with chrome(profile("douyin", account["id"]), locale=LOCALES["douyin"], region="CN", headless=False, viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(DOUYIN_HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        _open_douyin_panel(page)
        log("Đăng nhập Douyin trong cửa sổ vừa mở. Hệ thống không nhập mật khẩu thay bạn.")
        while time.time() < deadline:
            try:
                if signed_in("douyin", ctx.cookies()):
                    page.wait_for_timeout(4000)  # let the session settle into the profile before the window closes
                    return
                shown = [p for p in ctx.pages if not p.is_closed()]
                if not shown:
                    return
                shown[0].wait_for_timeout(2000)
            except Exception:  # the owner closed the browser under us
                return


def _source_window(account, channel, minutes):
    deadline = time.time() + 60 * minutes
    region = "CN" if channel == "kuaishou" else "US"
    with chrome(profile(channel, account["id"]), locale=LOCALES[channel], region=region, headless=False, viewport=(1280, 900)) as ctx:
        page = ctx.new_page()
        page.goto("https://www." + SITES[channel] + "/", wait_until="domcontentloaded", timeout=45000)
        while time.time() < deadline:
            try:
                if signed_in(channel, ctx.cookies()):
                    page.wait_for_timeout(4000)
                    return
                if not ctx.pages or all(p.is_closed() for p in ctx.pages):
                    return
                page.wait_for_timeout(2000)
            except Exception:
                return


def login(account, channel, minutes=LOGIN_MINUTES):
    """Open a visible window for the owner to sign in to the channel and wait for it (up to `minutes`). The answer is read back from the
    profile once the window is gone, so a session that did not survive the window closing does not count. {'ok','who','reason','channel'}"""
    if not window_ok():
        raise ValueError(NO_SCREEN[channel])
    try:
        if channel == "tiktok":
            from .publisher.session import login as tiktok_login

            ok = bool(tiktok_login(minutes=minutes, account=account["id"], expected=account["username"]))
        elif channel == "douyin":
            _douyin_window(account, minutes)
            ok = True
        else:
            _source_window(account, channel, minutes)
            ok = True
        ok = ok and read(account, channel)
        reason = "" if ok else "Chưa thấy đăng nhập %s trong thời gian chờ. Bấm Đăng nhập để mở lại cửa sổ." % NAMES[channel]
        if channel == "tiktok" and not ok:
            reason = (
                "Chưa thấy đăng nhập TikTok đúng @%s trong thời gian chờ (cửa sổ phải đăng nhập đúng tài khoản này). Bấm Đăng nhập để mở lại."
                % account["username"]
            )
    except Exception as error:  # the window was closed, or a page would not load
        log("sign-in window to %s ended early: %s" % (channel, str(error)[:120]))
        ok, reason = False, "Cửa sổ đăng nhập đã bị đóng hoặc không mở được trang %s. Bấm Đăng nhập để mở lại." % NAMES[channel]
    who = account["username"] if ok and channel == "tiktok" else ""
    report(account["id"], channel, "ok" if ok else "out", who)
    return {"ok": ok, "who": who, "reason": reason, "channel": channel}
