"""Keyword video search on signed-in Kuaishou and Instagram profiles; read only the search page's own video records."""

import json
import re
from urllib.parse import quote, parse_qs, urlsplit

from .browser import chrome
from .channels import profile, signed_in, SignedOut, Wall, window_ok
from .collector.sources.kuaishou import parse_kuaishou
from .collector.normalize import to_int
from .search_capture import Capture, wait_for_results

VIDEOS = {
    "kuaishou": re.compile(r"https://www\.kuaishou\.com/short-video/([A-Za-z0-9_-]{1,80})"),
    "instagram": re.compile(r"https://www\.instagram\.com/reel/([A-Za-z0-9_-]{6,20})/?"),
}
SEARCH_URLS = {
    "kuaishou": "https://www.kuaishou.com/search/video?searchKey=",
    "instagram": "https://www.instagram.com/explore/search/keyword/?q=",
}


def kuaishou_items(payload):
    data = payload.get("data") or {}
    found = data.get("visionSearchPhoto") or data.get("visionVideoDetail") or {}
    feeds = found.get("feeds") or ([{"photo": found["photo"]}] if found.get("photo") else [])
    return [dict(i, platform="kuaishou") for i in parse_kuaishou({"data": {"brilliantTypeData": {"feeds": feeds[:50]}}})]


def instagram_items(payload):
    """Known web media/section response shapes; a suggested account or a photo is never a video."""
    items = list(payload.get("items") or [])[:50]
    for section in (payload.get("sections") or [])[:20]:
        items.extend(((section.get("layout_content") or {}).get("medias") or [])[:20])
    out = []
    for entry in items[:100]:
        if not isinstance(entry, dict):
            continue
        media = entry.get("media") or entry
        code = str(media.get("code") or "")
        versions = media.get("video_versions") or []
        if media.get("media_type") != 2 or not re.fullmatch(r"[A-Za-z0-9_-]{6,20}", code) or not versions:
            continue
        url = "https://www.instagram.com/reel/" + code
        caption = media.get("caption") or {}
        out.append(
            {
                "platform": "instagram",
                "source_id": code,
                "url": url,
                "title": str(caption.get("text") or "")[:500],
                "views": to_int(media.get("play_count")),
                "likes": to_int(media.get("like_count")),
                "duration": media.get("video_duration"),
                "media": {"kind": "direct", "url": versions[0].get("url", ""), "referer": "https://www.instagram.com/"},
            }
        )
    return out


def _query_matches(response, query):
    """Ignore suggested feeds unless the request itself contains this exact search query."""
    fields = parse_qs(urlsplit(response.url).query)
    raw = response.request.post_data or ""
    try:
        fields.update(json.loads(raw))
    except (ValueError, TypeError):
        fields.update(parse_qs(raw))
    variables = fields.get("variables")
    if isinstance(variables, list):
        variables = variables[0] if variables else None
    if isinstance(variables, str):
        try:
            variables = json.loads(variables)
        except ValueError:
            variables = {}
    if isinstance(variables, dict):
        fields.update(variables)
    return any(
        query in (value if isinstance(value, list) else [value])
        for key, value in fields.items()
        if key in ("q", "query", "search_query", "keyword", "search_text")
    )


def _check(page):
    if any(part in page.url for part in ("/accounts/login", "/passport/login")):
        raise SignedOut("Phiên hết hạn; hãy đăng nhập lại nguồn tìm kiếm")
    if any(part in page.url for part in ("/challenge/", "/checkpoint/")):
        raise Wall("Nguồn yêu cầu xác minh; hãy tự xác minh rồi thử lại")
    nodes = page.locator('[id*="captcha"], [class*="captcha-verify"]')
    if any(nodes.nth(i).is_visible() for i in range(nodes.count())):
        raise Wall("Nguồn yêu cầu xác minh; không tiếp tục tìm")


def search(account, platform, query, links=(), human=False):
    if platform not in VIDEOS or not isinstance(query, str) or not 1 <= len(query) <= 160:
        raise ValueError("Nguồn hoặc truy vấn không hợp lệ")
    direct = [link for link in links[:3] if isinstance(link, str) and VIDEOS[platform].fullmatch(link)]
    parser = kuaishou_items if platform == "kuaishou" else instagram_items
    capture = Capture(("/graphql",) if platform == "kuaishou" else ("/api/v1/", "/graphql"), parser, direct)
    chinese = platform == "kuaishou"
    with chrome(
        profile(platform, account["id"]),
        locale="zh-CN" if chinese else "en-US",
        region="CN" if chinese else "US",
        headless=not (human or window_ok()),
    ) as ctx:
        if not signed_in(platform, ctx.cookies()):
            raise SignedOut("Chưa đăng nhập %s trong hồ sơ tài khoản này. Bấm Đăng nhập trong Kênh tìm kiếm." % platform)
        for url in direct or [SEARCH_URLS[platform] + quote(query)]:
            page = ctx.new_page()

            def take(response):
                if platform != "instagram" or direct or _query_matches(response, query):
                    capture.on_response(response)

            page.on("response", take)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                wait_for_results(page, capture, human, _check, rounds=6)
            finally:
                if not page.is_closed():
                    page.close()
    if not capture.seen:
        raise ValueError(
            "%s không trả video qua tìm kiếm này; có thể nền tảng chưa hỗ trợ tìm từ khóa trên web, cần xác minh hoặc không có kết quả. Chưa có video được chọn thay thế."
            % platform
        )
    return {"items": list(capture.seen.values())[:20], "note": "Truy vấn đã gửi trên %s: %s" % (platform, query)}
