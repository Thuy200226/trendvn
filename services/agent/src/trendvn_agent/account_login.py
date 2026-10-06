"""Owner-operated login in the chosen TikTok profile, confirmed by the actual signed-in username."""

import time

from .browser import chrome
from .publisher.constants import LOGIN_URL
from .publisher.jobs import report_login
from .publisher.profile import logged_in, profile_name, signed_in_as
from .search import _account


def login(payload):
    account = _account(payload)
    with chrome(profile_name(account["id"]), headless=False, locale="vi-VN", viewport=(1280, 900)) as ctx:
        page = ctx.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline:
            if page.is_closed():
                break
            page.wait_for_timeout(2500)
            if not logged_in(ctx):
                continue
            who = signed_in_as(ctx)
            if who and who.casefold() == account["username"].casefold():
                current = _account(payload)
                if current["username"] != account["username"]:
                    raise ValueError("Tài khoản đã thay đổi trong lúc đăng nhập; hãy mở lại")
                report_login(account["id"], True)
                return {"logged_in": True, "username": account["username"]}
        raise ValueError("Chưa xác minh đăng nhập đúng @" + account["username"] + "; hãy đăng nhập lại đúng tài khoản")
