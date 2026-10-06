"""The channels the owner searches on (TikTok, Douyin): where each account's session lives, how to tell it is signed in, and the visible
window to sign in with. The agent never types a password: the owner signs in themselves (QR code, phone, whatever the site offers)."""

import re
import time

from .browser import chrome
from .log import log
from .publisher.constants import wants_window
from .publisher.profile import profile_name
from .worker_client import worker

LOGIN_MINUTES = 10
DOUYIN_HOME = "https://www.douyin.com/"
DOUYIN_SESSION = ("sessionid", "sessionid_ss", "sid_tt", "uid_tt")  # set by Douyin's web sign-in; a guest has none of them
NAMES = {"tiktok": "TikTok", "douyin": "Douyin"}
SETTINGS = {"tiktok": {"locale": "vi-VN", "region": None}, "douyin": {"locale": "zh-CN", "region": "CN"}}
ACCOUNT_ID = re.compile(r"[a-z0-9][a-z0-9_-]{0,23}")


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
    return "search-cn-" + account_id


def signed_in(channel, cookies):
    """Does this cookie jar hold a signed-in session of the channel? Judged from cookie names and the site only, never their values."""
    if channel == "tiktok":
        return any(c["name"] == "sessionid" and "tiktok.com" in c["domain"] for c in cookies)
    return any(
        "douyin.com" in c["domain"]
        and ((c["name"] in DOUYIN_SESSION and c.get("value")) or (c["name"] == "LOGIN_STATUS" and c.get("value") == "1"))
        for c in cookies
    )


def report(account_id, channel, state, who=""):
    """Tell the worker what was found. Bookkeeping only: it never fails a search or a sign-in."""
    try:
        worker("/api/channel/report", {"account": account_id, "channel": channel, "state": state, "who": who}, timeout=15)
    except Exception as error:
        log("could not report the %s sign-in state: %s" % (channel, str(error)[:120]))


def check(account, channel):
    """Is the account signed in on the channel? Reads the profile's cookies without opening any page, so it is quick and quiet."""
    settings = SETTINGS[channel]
    with chrome(profile(channel, account["id"]), locale=settings["locale"], headless=True) as ctx:
        ok = signed_in(channel, ctx.cookies())
    report(account["id"], channel, "ok" if ok else "out", account["username"] if ok and channel == "tiktok" else "")
    return {"logged_in": ok, "channel": channel}


def _open_douyin_panel(page):
    """Open Douyin's sign-in panel (the QR code) for the owner. A click on a public button: nothing is typed or submitted."""
    try:
        page.get_by_text("登录", exact=True).first.click(timeout=4000)
    except Exception:
        pass  # the owner can click it themselves


def _douyin_window(account, minutes):
    deadline = time.time() + 60 * minutes
    with chrome(profile("douyin", account["id"]), locale="zh-CN", region="CN", headless=False, viewport=(1280, 900)) as ctx:
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(DOUYIN_HOME, wait_until="domcontentloaded")
        page.wait_for_timeout(2500)
        _open_douyin_panel(page)
        log("Đăng nhập Douyin trong cửa sổ vừa mở. Hệ thống không nhập mật khẩu thay bạn.")
        while time.time() < deadline:
            try:
                if signed_in("douyin", ctx.cookies()):
                    page.wait_for_timeout(4000)  # let the session settle into the profile before the window closes
                    return True
                if all(p.is_closed() for p in ctx.pages):
                    break
            except Exception:  # the owner closed the browser under us
                break
            page.wait_for_timeout(2000)
    return False


def login(account, channel, minutes=LOGIN_MINUTES):
    """Open a visible window for the owner to sign in to the channel and wait for it (up to `minutes`). Returns {'ok','who','reason'}."""
    if not wants_window():
        raise ValueError(
            "Máy chạy TrendVN không có màn hình nên không mở được cửa sổ đăng nhập. Đăng nhập bằng ./trendvn tiktok login trên máy có màn hình."
        )
    if channel == "tiktok":
        from .publisher.session import login as tiktok_login

        ok = tiktok_login(minutes=minutes, account=account["id"], expected=account["username"])
    else:
        ok = _douyin_window(account, minutes) or check(account, "douyin")["logged_in"]  # a window closed too early may still have signed in
    who = account["username"] if ok and channel == "tiktok" else ""
    report(account["id"], channel, "ok" if ok else "out", who)
    reason = "" if ok else "Chưa thấy đăng nhập %s trong thời gian chờ. Bấm Đăng nhập để mở lại cửa sổ." % NAMES[channel]
    return {"ok": ok, "who": who, "reason": reason, "channel": channel}
