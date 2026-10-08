"""Delete one confirmed owned TikTok post; uncertain outcomes are reported once and never retried automatically."""

import re
from pathlib import Path

from ..browser import chrome
from ..worker_client import worker
from ..search import _verify, _blocked, VIDEO_URL
from .profile import profile_name
from .screenshots import shot
from .delete_evidence import arm_notice, wait_notice

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


def _studio_menu(page, post):
    """Anchor Studio actions to an exact post link, never a row index or caption match."""
    studio = "https://www.tiktok.com/tiktokstudio/content"
    page.goto(studio, wait_until="domcontentloaded", timeout=45000)
    path = post["url"].removeprefix("https://www.tiktok.com")
    link = page.locator('a[href="%s"],a[href="%s"]' % (path, post["url"]))
    link.first.wait_for(state="visible", timeout=15000)
    if link.count() != 1:
        raise ValueError("Dòng bài trong TikTok Studio đã thay đổi; chưa xóa")
    try:
        caption = link.inner_text().strip()
    except Exception:
        caption = ""
    if not caption:
        raise ValueError("Chưa đọc được mô tả đúng bài trong Studio; chưa xóa")
    search = page.get_by_placeholder("Tìm kiếm mô tả bài đăng", exact=True)
    query = _studio_query(caption)
    search.fill(query)
    search.press("Enter")
    videos = page.locator('a[href*="/video/"]')
    page.wait_for_function("() => document.querySelectorAll('a[href*=\"/video/\"]').length === 1", timeout=10000)
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

    same()
    menu = row.get_by_role("button", name="", exact=True)
    if menu.count() != 1:
        raise ValueError("Không xác định được menu riêng của đúng bài trong TikTok Studio; chưa xóa")
    menu.click(timeout=5000)
    return same


def _open_menu(page, post):
    settings = page.locator('[data-e2e="video-setting"], [data-e2e="video-settings"]')
    try:
        settings.first.wait_for(state="visible", timeout=15000)
    except Exception:
        _blocked(page)
        _same_post(page, post)
        return _studio_menu(page, post)
    _blocked(page)
    _same_post(page, post)
    if settings.count() != 1:
        raise ValueError("Chưa tìm thấy menu quản lý duy nhất của bài này; chưa xóa")
    settings.click(timeout=5000)
    return lambda: _same_post(page, post)


def _perform(page, post, mark_attempted):
    goto_failed = False
    try:
        page.goto(post["url"], wait_until="domcontentloaded", timeout=30000)
    except Exception:
        goto_failed = True

    if goto_failed:
        same = _studio_menu(page, post)
    else:
        _blocked(page)
        _same_post(page, post)
        same = _open_menu(page, post)
    remove = page.get_by_role("menuitem", name=DELETE)
    if remove.count() != 1:
        remove = page.get_by_text(DELETE, exact=True)
    remove.first.wait_for(state="visible", timeout=5000)
    if remove.count() != 1:
        raise ValueError("TikTok chưa hiển thị duy nhất một thao tác Xóa; chưa xóa")
    same()
    mark_attempted()
    remove.click(timeout=5000)
    confirm = page.get_by_role("dialog").get_by_role("button", name=DELETE)
    confirm.first.wait_for(state="visible", timeout=10000)
    if confirm.count() != 1:
        raise ValueError("Không xác định được nút xác nhận xóa; chưa xóa")
    same()
    arm_notice(page)
    mark_attempted()
    confirm.click(timeout=10000)
    wait_notice(page)
    return "TikTok xác nhận đã xóa bài " + VIDEO_URL.fullmatch(post["url"])[1]


def delete_post(payload):
    jid, grant = payload.get("job_id"), payload.get("grant")
    if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value) for value in (jid, grant)):
        raise ValueError("Yêu cầu xóa không hợp lệ")
    post = worker("/api/post-delete/claim", {"job_id": jid, "grant": grant})
    attempted = False

    def mark_attempted():
        nonlocal attempted
        attempted = True

    try:
        if not VIDEO_URL.fullmatch(post.get("url", "")):
            raise ValueError("Đường dẫn bài đăng không hợp lệ")
        with chrome(profile_name(post["account"]), locale="vi-VN", headless=False) as ctx:
            _verify(ctx, {"id": post["account"], "username": post["username"]})
            page = ctx.new_page()
            try:
                reason = _perform(page, post, mark_attempted)
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
