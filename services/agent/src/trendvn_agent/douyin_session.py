"""Verify Douyin's own account from its page, never infer authentication from stale cookies or public videos."""

import json
from urllib.parse import urlsplit

from .browser_errors import navigation_error

SELF_PATH = "/aweme/v1/web/user/profile/self/"
MAX_SELF = 1 << 20


class Session:
    def __init__(self, page):
        self.who = ""
        self.proven = False
        page.on("response", self.observe)

    def observe(self, response):
        location = urlsplit(response.url)
        if location.hostname != "www.douyin.com" or location.path != SELF_PATH:
            return
        self.proven, self.who = False, ""
        if response.status != 200:
            return
        try:
            raw = response.body()
            if len(raw) > MAX_SELF:
                return
            data = json.loads(raw)
            user, status = data.get("user"), data.get("status_code")
            valid = (
                type(status) is int
                and status == 0
                and isinstance(user, dict)
                and all(isinstance(user.get(key), str) and user[key].strip() for key in ("uid", "sec_uid"))
            )
            self.proven = bool(valid)
            name = (user.get("unique_id") or user.get("nickname") or "") if valid else ""
            self.who = name[:80] if isinstance(name, str) else ""
        except Exception:
            pass  # no proof is preferable to guessing; never log a private response

    def state(self, page):
        from .search_douyin import blocked

        if page.is_closed():
            return "unknown"
        location = urlsplit(page.url)
        if location.scheme != "https" or location.hostname not in ("www.douyin.com", "douyin.com"):
            return "unknown"
        if blocked(page):
            return "wall"
        login = page.get_by_text("登录", exact=True)
        if any(login.nth(i).is_visible() for i in range(login.count())):
            self.proven, self.who = False, ""
            return "out"
        return "ok" if self.proven else "unknown"


def probe(ctx, url, owner_wait=False):
    """Check the account in its own profile/region; a visible verification wall waits for its owner."""
    page = ctx.new_page()
    session = Session(page)
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as error:
            if not navigation_error(error):
                raise
        rounds = 0
        while rounds < 8 and not page.is_closed():
            try:
                page.wait_for_timeout(1500)
                state = session.state(page)
            except Exception as error:
                if owner_wait and navigation_error(error) and not page.is_closed():
                    continue
                raise
            if state in ("ok", "wall"):
                return state, session.who
            rounds += 1
        return session.state(page), session.who
    finally:
        if not page.is_closed():
            page.close()
