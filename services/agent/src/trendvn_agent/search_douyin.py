"""Douyin product keyword search in a persistent source profile; human verification is never automated."""

import json
import re
from urllib.parse import quote, urlsplit

from .browser import chrome
from .collector.sources.douyin import parse_douyin

VIDEO = re.compile(r"https://www\.douyin\.com/video/(\d{6,25})")


def video_items(payload):
    awemes = list(payload.get("aweme_list") or [])
    for entry in (payload.get("data") or [])[:50]:
        if isinstance(entry, dict) and isinstance(entry.get("aweme_info"), dict):
            awemes.append(entry["aweme_info"])
    return [dict(i, platform="douyin") for i in parse_douyin({"aweme_list": awemes}) if VIDEO.fullmatch(i["url"])]


def blocked(page):
    nodes = page.locator('[id*="captcha"], [class*="captcha"], [class*="verify-wrap"]')
    return any(nodes.nth(i).is_visible() for i in range(nodes.count()))


def search(account, query, links=(), human=False):
    direct = [u for u in links[:3] if isinstance(u, str) and VIDEO.fullmatch(u)]
    urls = direct or ["https://www.douyin.com/search/" + quote(query) + "?type=video"]
    seen = {}
    with chrome("search-cn-" + account["id"], locale="zh-CN", region="CN", headless=not human) as ctx:
        for url in urls:
            page = ctx.new_page()

            def response(r):
                path = urlsplit(r.url).path
                if r.status != 200 or not ("/search/" in path or "/aweme/detail/" in path):
                    return
                try:
                    raw = r.body()
                    if len(raw) > 4 << 20:
                        return
                    data = json.loads(raw)
                    if isinstance(data.get("aweme_detail"), dict):
                        data = {"aweme_list": [data["aweme_detail"]]}
                    for item in video_items(data):
                        if not direct or item["url"] in direct:
                            seen[item["source_id"]] = item
                except Exception:
                    return  # an unreadable browser response is never a guessed video

            page.on("response", response)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                for _ in range(120 if human else 6):
                    if page.is_closed():
                        break
                    page.wait_for_timeout(2000)
                    if blocked(page):
                        if human:
                            continue
                        raise ValueError("Douyin yêu cầu xác minh. Bấm Mở cửa sổ để tự xác minh/đăng nhập, rồi tìm lại.")
                    if seen:
                        break
                if page.is_closed():
                    break
            finally:
                if not page.is_closed():
                    page.close()
    if not seen:
        raise ValueError(
            "Douyin chưa trả video. Có thể cần đăng nhập/xác minh hoặc không có kết quả; không tự thay bằng video khác sản phẩm."
        )
    return {"items": list(seen.values())[:20], "note": "Đã tìm Douyin bằng từ khóa tiếng Trung; cần xem đúng model và biến thể."}
