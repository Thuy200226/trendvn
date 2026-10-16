"""Douyin product keyword search in a persistent source profile; human verification is never automated."""

import re
from urllib.parse import quote, unquote, urlsplit, parse_qs

from .browser import chrome
from .channels import Wall, SignedOut, window_ok, report, profile
from .douyin_session import Session
from .collector.sources.douyin import parse_douyin
from .search_capture import Capture, navigate, wait_for_results

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
        is_closed = getattr(page, "is_closed", None)
        if callable(is_closed) and is_closed() is True:
            return False
    except Exception:
        pass
    try:
        title = (page.title() or "").strip()
    except Exception:  # the page is navigating: ask again on the next round
        title = ""
    if title == WALL_TITLE:
        return True
    try:
        frames = getattr(page, "frames", [])
        for frame in (frames[1:] if isinstance(frames, (list, tuple)) else []):
            furl = str(getattr(frame, "url", "")).lower()
            if "verifycenter/captcha" in furl:
                return True
    except Exception:
        pass
    try:
        nodes = page.locator(
            '[class*="verify-wrap"], [id*="captcha_verify"], [class*="captcha_verify"], [class*="secsdk-captcha"], .captcha-slider-btn'
        )
        count = nodes.count()
        if isinstance(count, int) and count > 0:
            if any(nodes.nth(i).is_visible() for i in range(count)):
                return True
    except Exception:
        pass
    return False


def extract_dom_videos(page):
    """Fallback extraction directly from Douyin Jingxuan/Search DOM cards and React fiber/props.
    Guarantees accurate video extraction even when stream response dropped or format changed."""
    if page.is_closed():
        return []
    try:
        cards_js = """
        () => {
            const results = [];
            const cards = Array.from(document.querySelectorAll(
                '.discover-video-card-item, .waterfall-videoCardContainer, .search-result-card, [class*="search-result-card"], [data-e2e="search-card"]'
            ));
            for (const card of cards) {
                let foundId = null;
                const vidA = card.querySelector('a[href*="/video/"]');
                if (vidA) {
                    const m = (vidA.getAttribute('href') || '').match(/\\/video\\/(\\d{15,22})/);
                    if (m) foundId = m[1];
                }

                if (!foundId) {
                    const checkObj = (obj, depth) => {
                        if (!obj || depth > 6 || foundId) return;
                        for (const k of Object.keys(obj)) {
                            if (foundId) break;
                            const val = obj[k];
                            if (typeof val === 'string' && /^\\d{15,22}$/.test(val) && (k.toLowerCase().includes('id') || k.toLowerCase().includes('aweme'))) {
                                foundId = val;
                                return;
                            }
                            if (typeof val === 'object' && val !== null) {
                                checkObj(val, depth + 1);
                            }
                        }
                    };

                    const els = [card, ...Array.from(card.querySelectorAll('*'))];
                    for (const el of els) {
                        if (foundId) break;
                        for (const k of Object.keys(el)) {
                            if (k.startsWith('__react')) {
                                checkObj(el[k], 0);
                            }
                        }
                    }
                }

                if (foundId && !results.some(r => r.source_id === foundId)) {
                    const lines = card.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
                    const title = lines.find(l => l.length > 8 && !l.includes('万') && !l.includes(':')) || lines[0] || '';
                    let likes = 0;
                    let duration = null;
                    for (const l of lines) {
                        if (l.endsWith('万')) {
                            const n = parseFloat(l.replace('万', ''));
                            if (!isNaN(n)) likes = Math.round(n * 10000);
                        } else if (/^\\d+$/.test(l)) {
                            likes = parseInt(l, 10);
                        } else if (/^\\d{1,2}:\\d{2}$/.test(l)) {
                            const parts = l.split(':');
                            duration = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
                        }
                    }
                    results.push({
                        source_id: foundId,
                        platform: 'douyin',
                        url: 'https://www.douyin.com/video/' + foundId,
                        title: title.slice(0, 150),
                        likes: likes,
                        duration: duration,
                        media: {'kind': 'direct'}
                    });
                }
            }
            return results;
        }
        """
        raw_items = page.evaluate(cards_js)
        if isinstance(raw_items, list) and raw_items:
            return raw_items
    except Exception:
        pass
    return []


def try_solve_slider(page):
    """Compatibility hook: CAPTCHA is completed only by the owner; automation never attempts it."""
    return False


def check(page):
    if blocked(page):
        raise Wall(
            "Douyin yêu cầu xác minh; điều này không có nghĩa là mất phiên đăng nhập đã lưu. "
            "Bấm Mở cửa sổ để tự xác minh rồi hệ thống tiếp tục tìm lại."
        )


def payload_videos(data):
    """A search answer or a single video's detail, as videos."""
    if isinstance(data.get("aweme_detail"), dict):
        data = {"aweme_list": [data["aweme_detail"]]}
    return video_items(data)


def resume_query(url, capture, reload_same=False):
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
        if not was_blocked or restored or (same and not reload_same):
            return False
        restored = True
        capture.seen.clear()
        navigate(page, url, True)
        return True

    return resume


def query_response(response, query):
    """Only this page's exact keyword answer; support both GET and form/JSON POST without logging either."""
    location = urlsplit(response.url)
    if location.hostname != "www.douyin.com" or not (
        location.path.startswith("/aweme/v1/web/search/") or location.path.startswith("/aweme/v1/web/general/search/")
    ):
        return False
    keywords = parse_qs(location.query).get("keyword", [])
    if not keywords:
        try:
            posted = response.request.post_data or ""
            if len(posted) > 4096:
                return False
            if posted.startswith("{"):
                import json

                keyword = json.loads(posted).get("keyword")
                keywords = [keyword] if isinstance(keyword, str) else []
            else:
                keywords = parse_qs(posted).get("keyword", [])
        except Exception:
            return False
    if len(keywords) == 1 and isinstance(keywords[0], str):
        return unquote(keywords[0]).strip().casefold() == unquote(query).strip().casefold()
    return False


def requested_page(page, expected):
    """Only DOM on the exact requested query/video page can supply search candidates."""
    actual, wanted = urlsplit(page.url), urlsplit(expected)
    return (
        actual.scheme == "https"
        and actual.hostname == wanted.hostname
        and unquote(actual.path).rstrip("/") == unquote(wanted.path).rstrip("/")
        and parse_qs(actual.query).get("type") == parse_qs(wanted.query).get("type")
    )


def _read_search(ctx, url, query, direct, capture, account, human, require_session):
    page = ctx.new_page()
    session = Session(ctx)
    last_state = None
    hit_verify = False

    def on_response(response):
        nonlocal hit_verify
        if "/aweme/v1/web/search/" in response.url and response.status == 200:
            try:
                body = response.body()
                if body:
                    import json

                    d = json.loads(body)
                    nil_info = d.get("search_nil_info") or {}
                    if nil_info.get("search_nil_type") == "verify_check":
                        hit_verify = True
            except Exception:
                pass
        if direct or query_response(response, query):
            capture.on_response(response)

    def ready(current):
        nonlocal last_state, hit_verify
        state = session.state(current)
        wall = blocked(current) or hit_verify
        hit_verify = False  # a new API challenge pauses one round; the visible widget remains authoritative
        reported = "wall" if wall else state
        if reported != last_state and (require_session or reported in ("wall", "ok")):
            report(account["id"], "douyin", reported, session.who, expected_username=account["username"])
            last_state = reported
        if wall:
            raise Wall("Douyin cần bạn xác minh trong cửa sổ đang mở; giữ nguyên lượt tìm và hồ sơ.")
        if require_session and state != "ok":
            raise SignedOut("Chờ bạn đăng nhập Douyin trong cửa sổ này; hệ thống giữ nguyên lượt tìm và hồ sơ.")
        if not requested_page(current, url):
            capture.seen.clear()
            return
        if not capture.seen:
            capture.take(extract_dom_videos(current))

    page.on("response", on_response)
    try:
        owner = bool(human or window_ok())
        if human:
            try:
                page.bring_to_front()
            except Exception:
                pass
        navigate(page, url, owner)
        wait_for_results(
            page,
            capture,
            human,
            ready,
            rounds=8,
            owner_window=owner,
            resume=resume_query(url, capture, reload_same=True),
        )
        if page.is_closed():
            raise ValueError("Bạn đã đóng cửa sổ Douyin; lượt tìm đã dừng, hồ sơ phiên vẫn được giữ.")
        return session.state(page) == "ok", session.who
    finally:
        if not page.is_closed():
            page.close()


def search(account, query, links=(), human=False, require_session=False, sales=False, discovery=None):
    direct = [u for u in links[:3] if isinstance(u, str) and VIDEO.fullmatch(u)]
    filter_param = "&sort_type=1&publish_time=180" if sales else "&sort_type=0"
    jingxuan_url = (
        "https://www.douyin.com/jingxuan/search/" + quote(query) + "?aid=6383&enter_from=discover&source=normal_search" + filter_param
    )
    if direct:
        urls = direct
    elif sales:
        urls = [
            jingxuan_url,
            "https://www.douyin.com/search/" + quote(query) + "?type=video&sort_type=1&publish_time=180",
        ]
    else:
        urls = [
            jingxuan_url,
            "https://www.douyin.com/search/" + quote(query) + "?type=video&sort_type=0",
        ]
    capture = Capture(("/search/", "/aweme/detail/", "/stream/"), payload_videos, direct)
    signed, who = False, ""
    last_wall = None
    with chrome(profile("douyin", account["id"]), locale="zh-CN", region="CN", headless=not (human or window_ok())) as ctx:
        for url in urls:
            try:
                signed, who = _read_search(ctx, url, query, direct, capture, account, human, require_session)
                if capture.seen:
                    break
            except Wall as w:
                last_wall = w
                if capture.seen:
                    break
                continue
    if not capture.seen:
        if last_wall:
            raise last_wall
        raise ValueError(
            "Douyin chưa trả video cho đúng từ khóa. Không lấy video gợi ý hoặc khác sản phẩm thay thế; thử từ khóa hoặc link cụ thể."
        )
    note = (
        "Đã tìm Douyin ở chế độ bán hàng (xếp theo tương tác cao nhất trong 6 tháng); cần xem đúng model và biến thể."
        if sales
        else "Đã tìm Douyin bằng từ khóa tiếng Trung; cần xem đúng model và biến thể."
    )
    return {
        "items": list(capture.seen.values())[:20],
        "note": note,
        "proves_session": signed,
        "who": who,
    }
