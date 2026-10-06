"""Read TikTok search in the selected account's real Chrome session, then download only the owner's selection."""

import json
import re
from urllib.parse import quote

from .browser import chrome
from .collector.download import download
from .collector.sources.tiktok import parse_tiktok
from .config import RUNTIME
from .publisher.profile import logged_in, profile_name, signed_in_as
from .search_capture import Capture, wait_for_results
from .worker_client import worker, worker_get

VIDEO_URL = re.compile(r"https://(?:www\.)?tiktok\.com/@[A-Za-z0-9._-]{1,50}/video/(\d{6,25})")


def video_items(payload):
    """Known TikTok response shapes only; suggestions and user search results are not videos."""
    items = list(payload.get("itemList") or [])
    item = (payload.get("itemInfo") or {}).get("itemStruct")
    if isinstance(item, dict):
        items.append(item)
    for entry in (payload.get("data") or [])[:50]:
        if isinstance(entry, dict):
            item = entry.get("item") or entry.get("itemStruct")
            if isinstance(item, dict):
                items.append(item)
    return [dict(i, platform="tiktok") for i in parse_tiktok({"itemList": items})]


def _account(payload):
    account = next((a for a in worker_get("/api/status").get("accounts", []) if a["id"] == payload.get("account")), None)
    if not account:
        raise ValueError("Không có tài khoản này")
    return account


def _verify(ctx, account):
    if not logged_in(ctx):
        flag = "" if account["id"] == "main" else " --account " + account["id"]
        raise ValueError(
            "Chưa đăng nhập TikTok cho @%s (khách không tìm kiếm được): chạy ./trendvn tiktok login%s" % (account["username"], flag)
        )
    who = signed_in_as(ctx)
    if not who or who.casefold() != account["username"].casefold():
        raise ValueError("Không xác minh được phiên tìm kiếm đúng @" + account["username"])


def _blocked(page):
    if "/login" in page.url:
        raise ValueError("Phiên TikTok hết hạn; hãy đăng nhập lại")
    captcha = page.locator('[id*="captcha"], [class*="captcha-verify"]')
    if any(captcha.nth(i).is_visible() for i in range(captcha.count())):
        raise ValueError("TikTok yêu cầu xác minh; hãy tự xác minh rồi tìm lại")


def _embedded(page, capture):
    """A video page can carry its data in the page itself rather than fetch it."""
    raw = page.locator("#__UNIVERSAL_DATA_FOR_REHYDRATION__")
    if raw.count():
        data = json.loads(raw.text_content() or "{}").get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
        capture.take(video_items(data))


def _read_page(ctx, url, capture, human, direct):
    page = ctx.new_page()
    page.on("response", capture.on_response)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        wait_for_results(page, capture, human, _blocked, rounds=5)
        if not page.is_closed():
            _embedded(page, capture)
            if capture.seen and not direct:
                page.mouse.wheel(0, 1000)  # a search page loads more results as it scrolls
                page.wait_for_timeout(2500)
                _blocked(page)
    finally:
        if not page.is_closed():
            page.close()


def _tiktok_search(payload, human=False):
    account = _account(payload)
    query = payload.get("query")
    if not isinstance(query, str) or not 1 <= len(query) <= 160:
        raise ValueError("Từ khóa tìm kiếm không hợp lệ")
    direct = [link for link in payload.get("links", [])[:3] if isinstance(link, str) and VIDEO_URL.fullmatch(link)]
    capture = Capture(("/api/search/", "/api/item/detail/"), video_items, direct)
    with chrome(profile_name(account["id"]), locale="vi-VN", headless=not human) as ctx:
        if not human:
            _verify(ctx, account)
        for url in direct or ["https://www.tiktok.com/search/video?q=" + quote(query)]:
            _read_page(ctx, url, capture, human, direct)
        if human and capture.seen:
            _verify(ctx, account)  # whatever the owner did in the open window, the results are taken only from the right account
    if not capture.seen:
        raise ValueError(
            "TikTok không trả video: có thể lỗi máy chủ, hạn chế tìm kiếm hoặc không có kết quả. Thử đường dẫn video cụ thể hoặc từ khóa khác."
        )
    return {"items": list(capture.seen.values())[:20], "note": "Ứng viên từ TikTok; cần xem video, model và biến thể trước khi chọn."}


def _platforms(source, links, human):
    """Which sources to ask. Exact video links decide it: a TikTok link is never looked up on Douyin."""
    from .search_douyin import VIDEO as DOUYIN_URL

    if source not in ("auto", "tiktok", "douyin") or human and source == "auto":
        raise ValueError("Chọn một nguồn để tìm hoặc tự xác minh")
    if not isinstance(links, list):
        raise ValueError("Đường dẫn không hợp lệ")
    platforms = ("douyin", "tiktok") if source == "auto" else (source,)
    given = {
        p
        for p, pattern in (("tiktok", VIDEO_URL), ("douyin", DOUYIN_URL))
        if any(isinstance(link, str) and pattern.fullmatch(link) for link in links[:3])
    }
    if given:
        platforms = tuple(p for p in platforms if p in given)
        if not platforms:
            raise ValueError("Nguồn đã chọn không khớp đường dẫn video; hãy chọn đúng nguồn")
    return platforms


def _ask(platform, account, payload, query, human):
    if platform == "douyin":
        from .search_douyin import search as chinese_search

        return chinese_search(account, query, payload.get("links", []), human)
    return _tiktok_search(dict(payload, query=query), human)


def search(payload, human=False):
    platforms = _platforms(payload.get("source", "tiktok"), payload.get("links", []), human)
    account = _account(payload)
    queries = payload.get("queries") or {"tiktok": payload.get("query", ""), "douyin": payload.get("query", "")}
    if not isinstance(queries, dict):
        raise ValueError("Từ khóa không hợp lệ")
    items, notes = [], []
    for platform in platforms:
        query = queries.get(platform, "")
        if not isinstance(query, str) or not 1 <= len(query) <= 160:
            raise ValueError("Cần từ khóa/model để tìm")
        try:
            result = _ask(platform, account, payload, query, human)
        except Exception as error:  # one source failing in any way (a timeout, a page that changed) must not lose what the other found
            notes.append("%s: %s" % (platform, str(error)[:300]) if len(platforms) > 1 else str(error)[:300])
            continue
        items.extend(result["items"])
        notes.append(result.get("note", ""))
    if not items:
        raise ValueError(" · ".join(notes))
    return {"items": items[:40], "note": " · ".join(notes)[:1000]}


def download_selected(payload):
    account = _account(payload)
    item, jid = payload.get("item"), payload.get("job_id")
    if not isinstance(item, dict) or not isinstance(jid, str) or not re.fullmatch(r"[0-9a-f]{32}", jid):
        raise ValueError("Video được chọn không hợp lệ")
    platform = item.get("platform") or "tiktok"
    from .search_douyin import VIDEO as DOUYIN_URL

    pattern = VIDEO_URL if platform == "tiktok" else DOUYIN_URL if platform == "douyin" else None
    if not pattern or not pattern.fullmatch(item.get("url", "")) or not re.fullmatch(r"\d{6,25}", str(item.get("source_id", ""))):
        raise ValueError("Đường dẫn video không hợp lệ")
    if pattern.fullmatch(item["url"]).group(1) != item["source_id"]:
        raise ValueError("Mã video không khớp đường dẫn")
    if not isinstance(item.get("media"), dict) or item["media"].get("kind") != "direct":
        raise ValueError("Không có đường tải video đã xác minh")
    RUNTIME.joinpath("inbox").mkdir(exist_ok=True)
    profile = profile_name(account["id"]) if platform == "tiktok" else "search-cn-" + account["id"]
    options = {"locale": "vi-VN"} if platform == "tiktok" else {"locale": "zh-CN", "region": "CN"}
    with chrome(profile, **options) as ctx:
        if platform == "tiktok":
            _verify(ctx, account)
        try:
            name = download(ctx, item, platform)
        except ValueError:
            name = None
    if name is None:
        # CDN links expire. Refresh the exact selected video once, never substitute a keyword result.
        refreshed = search({"account": account["id"], "source": platform, "query": "Video đã chọn", "links": [item["url"]]})
        fresh = next((i for i in refreshed["items"] if i["source_id"] == item["source_id"]), None)
        if not fresh:
            raise ValueError("Không đọc lại được chính video đã chọn; chưa tải") from None
        with chrome(profile, **options) as ctx:
            if platform == "tiktok":
                _verify(ctx, account)
            name = download(ctx, fresh, platform)
    return worker("/api/attach", {"id": jid, "filename": name})
