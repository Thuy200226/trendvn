"""Delete one confirmed owned TikTok post; uncertain outcomes are reported once and never retried automatically."""

import re
import time
from pathlib import Path

from ..browser import chrome
from ..browser_errors import navigation_error
from ..worker_client import worker
from ..search import _verify, _blocked, VIDEO_URL
from ..channels import SignedOut, Wall
from .profile import profile_name
from .screenshots import shot
from .delete_evidence import arm_notice, wait_notice
from ..owner_wait import wait
from .constants import LOGIN_URL

DELETE = re.compile(r"^(Delete|Xóa|Delete video|Xóa video|Xóa bài đăng)$", re.I)


def _same_post(page, post):
    current = VIDEO_URL.fullmatch(page.url.split("?", 1)[0].rstrip("/"))
    expected = VIDEO_URL.fullmatch(post["url"])
    if not current or current[1] != expected[1] or not page.url.split("/video/")[0].casefold().endswith("/@" + post["username"].casefold()):
        raise ValueError("Trang không còn là đúng bài đã xác nhận; chưa xóa")


def _studio_query(caption):
    """One bounded caption term; exact post ID and unique-row checks still decide which post may be deleted."""
    text = str(caption) if caption is not None else ""
    words = [word for word in re.findall(r"(?<![#\w])\w{4,}", text) if any(c.isalpha() for c in word)]
    return max(words, key=len)[:64] if words else text[:64]


def _studio_link(page, post, pulse):
    """Anchor Studio actions to an exact post link, never a row index or caption match."""
    studio = "https://www.tiktok.com/tiktokstudio/content"
    try:
        if page.url.startswith("chrome-error:"):
            page.goto("about:blank", wait_until="domcontentloaded", timeout=5000)
        page.goto(studio, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        pass  # leave the existing window available for the owner to reload or sign in
    path = post["url"].removeprefix("https://www.tiktok.com")
    link = page.locator('a[href="%s"],a[href="%s"]' % (path, post["url"]))

    def ready():
        try:
            _blocked(page)
        except ValueError:
            return False
        if page.url.split("?", 1)[0].rstrip("/") != studio:
            return False
        if link.count() > 1:
            raise ValueError("Dòng bài trong TikTok Studio đã thay đổi; chưa xóa")
        return link.count() == 1 and link.first.is_visible()

    _wait_action(page, ready, pulse)
    return link


def _wait_action(page, ready, pulse=None):
    """Before a delete click, keep waiting through login/CAPTCHA and transient browser navigation errors."""

    def available():
        try:
            _blocked(page)
            return ready()
        except (SignedOut, Wall):
            return False
        except Exception as error:
            if navigation_error(error):
                return False
            raise

    wait(page, available, pulse)


def _studio_menu(page, post, pulse=None):
    """Filter to the unique exact post, then recheck the row before any action."""
    studio = "https://www.tiktok.com/tiktokstudio/content"
    link = _studio_link(page, post, pulse)
    caption = ""

    def read_caption():
        nonlocal caption
        caption = link.inner_text(timeout=2000).strip()
        return bool(caption)

    _wait_action(page, read_caption, pulse)
    search = page.get_by_placeholder("Tìm kiếm mô tả bài đăng", exact=True)
    query = _studio_query(caption)

    def filter_post():
        search.fill(query, timeout=2000)
        search.press("Enter", timeout=2000)
        return True

    _wait_action(page, filter_post, pulse)
    videos = page.locator('a[href*="/video/"]')
    _wait_action(page, lambda: videos.count() == 1 and link.count() == 1 and link.is_visible(), pulse)
    row = link.locator("xpath=ancestor::*[.//button and count(.//a[contains(@href,'/video/')])=1][1]")

    def same():
        _blocked(page)
        if (
            page.url.split("?", 1)[0].rstrip("/") != studio
            or search.input_value() != query
            or videos.count() != 1
            or link.count() != 1
            or row.count() != 1
            or not link.is_visible()
        ):
            raise ValueError("Dòng bài trong TikTok Studio đã thay đổi; chưa xóa")

    _wait_action(page, lambda: (same(), True)[1], pulse)
    menu = row.get_by_role("button", name="", exact=True)
    if menu.count() != 1:
        raise ValueError("Không xác định được menu riêng của đúng bài trong TikTok Studio; chưa xóa")
    menu.click(timeout=5000)
    return same


def _open_menu(page, post, pulse=None):
    settings = page.locator('[data-e2e="video-setting"], [data-e2e="video-settings"]')
    try:
        settings.first.wait_for(state="visible", timeout=15000)
    except Exception:
        _wait_action(page, lambda: (_same_post(page, post), True)[1], pulse)
        return _studio_menu(page, post, pulse)
    _blocked(page)
    _same_post(page, post)
    if settings.count() != 1:
        raise ValueError("Chưa tìm thấy menu quản lý duy nhất của bài này; chưa xóa")
    settings.click(timeout=5000)

    def same():
        _blocked(page)
        _same_post(page, post)

    return same


def _perform(page, post, mark_attempted, pulse=None):
    goto_failed = False
    try:
        page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
    except Exception:
        goto_failed = True

    if goto_failed:
        same = _studio_menu(page, post, pulse)
    else:

        def unblocked():
            try:
                _blocked(page)
                return True
            except ValueError:
                return False

        _wait_action(page, unblocked, pulse)
        _same_post(page, post)
        same = _open_menu(page, post, pulse)
    remove = page.get_by_role("menuitem", name=DELETE)
    if remove.count() != 1:
        remove = page.get_by_text(DELETE, exact=True)
    _wait_action(page, lambda: remove.count() == 1 and remove.first.is_visible(), pulse)
    if remove.count() != 1:
        raise ValueError("TikTok chưa hiển thị duy nhất một thao tác Xóa; chưa xóa")
    _wait_action(page, lambda: (same(), True)[1], pulse)
    mark_attempted()
    same()
    remove.click(timeout=5000)
    confirm = page.get_by_role("dialog").get_by_role("button", name=DELETE)
    confirm.first.wait_for(state="visible", timeout=10000)
    if confirm.count() != 1:
        raise ValueError("Không xác định được nút xác nhận xóa; chưa xóa")
    same()
    arm_notice(page)
    mark_attempted()
    same()
    confirm.click(timeout=10000)
    wait_notice(page)
    return "TikTok xác nhận đã xóa bài " + VIDEO_URL.fullmatch(post["url"])[1]


def _wait_signed_in(ctx, page, account, pulse):
    try:
        _verify(ctx, account)
        return
    except ValueError:
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
        except Exception:
            pass

    def signed():
        try:
            _blocked(page)
            _verify(ctx, account)
            return True
        except ValueError:
            return False

    _wait_action(page, signed, pulse)


def delete_post(payload):
    jid, grant = payload.get("job_id"), payload.get("grant")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) for value in (jid, grant)):
        raise ValueError("Yêu cầu xóa không hợp lệ")
    post = worker("/api/post-delete/claim", {"job_id": jid, "grant": grant})
    attempted = False
    last_pulse = 0

    def pulse(force=False):
        nonlocal last_pulse
        if force or time.monotonic() - last_pulse >= 30:
            worker("/api/post-delete/authorize", {"job_id": jid, "grant": grant}, timeout=15)
            last_pulse = time.monotonic()

    def mark_attempted():
        nonlocal attempted
        pulse(True)
        _verify(ctx, account)
        pulse(True)  # identity lookup navigates another tab: authority may have changed during it
        attempted = True

    try:
        if not VIDEO_URL.fullmatch(post.get("url", "")):
            raise ValueError("Đường dẫn bài đăng không hợp lệ")
        with chrome(profile_name(post["account"]), locale="vi-VN", headless=False) as ctx:
            page = ctx.new_page()
            account = {"id": post["account"], "username": post["username"]}
            _wait_signed_in(ctx, page, account, pulse)
            try:
                reason = _perform(page, post, mark_attempted, pulse)
            except Exception:
                snapshot = shot(page, "delete")
                if snapshot:
                    try:
                        Path(snapshot).with_suffix(".txt").write_text(page.locator("body").aria_snapshot(), encoding="utf-8")
                    except Exception:
                        pass
                raise
        status = "deleted"
    except Exception as error:
        status = "unknown" if attempted else "failed"
        reason = (
            "Đã mở thao tác xóa nhưng chưa biết TikTok xóa thành công; hãy kiểm tra bài, không tự thử lại. "
            if attempted
            else "Chưa xóa bài. "
        ) + str(error)[:350]
    worker("/api/post-delete/finish", {"job_id": jid, "grant": grant, "outcome": status, "reason": reason})
    return {"status": status, "reason": reason}
