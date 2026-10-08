"""Douyin product keyword search in a persistent source profile; human verification is never automated."""

import re
from urllib.parse import quote, unquote, urlsplit, parse_qs

from .browser import chrome
from .channels import Wall, SignedOut, signed_in, window_ok
from .collector.sources.douyin import parse_douyin
from .search_capture import Capture, wait_for_results

VIDEO = re.compile(r"https://www\.douyin\.com/video/(\d{6,25})")


def video_items(payload):
    awemes = list(payload.get("aweme_list") or [])
    for entry in (payload.get("data") or [])[:50]:
        if isinstance(entry, dict) and isinstance(entry.get("aweme_info"), dict):
            awemes.append(entry["aweme_info"])
    return [dict(i, platform="douyin") for i in parse_douyin({"aweme_list": awemes}) if VIDEO.fullmatch(i["url"])]


WALL_TITLE = (
    "验证码中间页"  # Douyin's blank interstitial ("verification code intermediate page"): its whole title, never a piece of a video's
)


def blocked(page):
    """A verification wall: the blank interstitial page Douyin serves a visitor it does not trust (no widget on it at all), or the widget."""
    try:
        title = (page.title() or "").strip()
    except Exception:  # the page is navigating: ask again on the next round
        title = ""
    if title == WALL_TITLE:
        return True
    nodes = page.locator('[id*="captcha"], [class*="captcha"], [class*="verify-wrap"]')
    return any(nodes.nth(i).is_visible() for i in range(nodes.count()))


def check(page):
    if blocked(page):
        raise Wall(
            "Douyin đòi xác minh (khách chưa đăng nhập không tìm kiếm được). Bấm Đăng nhập Douyin trong khung Kênh tìm kiếm, "
            "hoặc Mở cửa sổ để tự xác minh rồi tìm lại."
        )


def payload_videos(data):
    """A search answer or a single video's detail, as videos."""
    if isinstance(data.get("aweme_detail"), dict):
        data = {"aweme_list": [data["aweme_detail"]]}
    return video_items(data)


def resume_query(url, capture):
    """Restore the requested page once after the owner passes a wall; never navigate while blocked."""
    restored = False

    def resume(page, was_blocked):
        nonlocal restored
        wanted, current = urlsplit(url), urlsplit(page.url)
        same = (
            wanted.hostname == current.hostname
            and unquote(wanted.path).rstrip("/") == unquote(current.path).rstrip("/")
            and parse_qs(wanted.query).get("type") == parse_qs(current.query).get("type")
        )
        if not was_blocked or restored or same:
            return False
        restored = True
        capture.seen.clear()
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        return True

    return resume


def search(account, query, links=(), human=False, require_session=False):
    direct = [u for u in links[:3] if isinstance(u, str) and VIDEO.fullmatch(u)]
    urls = direct or ["https://www.douyin.com/search/" + quote(query) + "?type=video"]
    capture = Capture(("/search/", "/aweme/detail/"), payload_videos, direct)
    # Douyin turns a hidden (headless) Chrome away even from its home page (measured 2026-10-06): with a screen it is searched in a window
    with chrome("search-cn-" + account["id"], locale="zh-CN", region="CN", headless=not (human or window_ok())) as ctx:
        if require_session and not signed_in("douyin", ctx.cookies()):
            raise SignedOut("Chưa đăng nhập Douyin trong hồ sơ tài khoản này; hãy bấm Đăng nhập Douyin.")
        for url in urls:
            page = ctx.new_page()

            def on_response(response):
                if direct or parse_qs(urlsplit(response.url).query).get("keyword", []) == [query]:
                    capture.on_response(response)

            page.on("response", on_response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                options = {"resume": resume_query(url, capture)} if human else {}
                wait_for_results(page, capture, human, check, rounds=6, **options)
            finally:
                if not page.is_closed():
                    page.close()
        signed = signed_in("douyin", ctx.cookies())
    if not capture.seen:
        raise ValueError(
            "Douyin chưa trả video. Có thể cần đăng nhập/xác minh hoặc không có kết quả; không tự thay bằng video khác sản phẩm."
        )
    return {
        "items": list(capture.seen.values())[:20],
        "note": "Đã tìm Douyin bằng từ khóa tiếng Trung; cần xem đúng model và biến thể.",
        "proves_session": signed
        or not direct,  # a keyword search that returned videos got past the wall; a video opened by its address proves nothing
    }
