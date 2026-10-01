"""Read the JSON a site's own page loads, inside Chrome; never solve a CAPTCHA, report it."""

import json
import re
import time

from ..log import log


class Blocked(Exception):
    pass


def looks_blocked(page):
    try:
        text = page.inner_text("body", timeout=3000)[:2000].lower()
    except Exception:
        return False
    return any(w in text for w in ("captcha", "verify to continue", "验证码", "请完成验证", "security verification", "log in to continue"))


def exit_country(ctx):
    """Country of the browser's public exit IP, so region-bound streams are never guessed."""
    for url in ("https://ipinfo.io/country", "https://api.country.is/"):
        try:
            r = ctx.request.get(url, timeout=15000)
            if r.ok:
                text = r.text().strip()
                m = re.search(r"\b([A-Z]{2})\b", text.replace('"country":"', " ").replace('"', " "))
                if m:
                    return m.group(1)
        except Exception:
            continue
    return None


def capture(ctx, url, match, parse, attempts=3, **kw):
    """Sites reset connections now and then; retry with a fresh page before calling a stream empty."""
    last = None
    for n in range(1, attempts + 1):
        try:
            items = capture_once(ctx, url, match, parse, **kw)
            if items:
                return items
            last = Blocked("no videos returned") if n == attempts else None
        except Blocked:
            raise
        except Exception as e:
            last = e
        log("capture retry %d/%d for %s" % (n, attempts, url))
        time.sleep(6 * n)
    if last:
        raise last
    return []


def capture_once(ctx, url, match, parse, scrolls=4, wait_ms=12000, before_scroll=None):
    page = ctx.new_page()
    found = {}
    order = []

    def on_response(r):
        try:
            if r.status == 200 and match(r.url) and "json" in r.headers.get("content-type", ""):
                for it in parse(json.loads(r.body())):
                    if it["source_id"] not in found:
                        found[it["source_id"]] = it
                        order.append(it["source_id"])
        except Exception:
            pass

    page.on("response", on_response)
    try:
        try:
            page.goto(url, wait_until="commit", timeout=60000)
        except Exception as e:
            log("goto warning %s: %s" % (url, str(e)[:100]))
        page.wait_for_timeout(wait_ms)
        if before_scroll:
            before_scroll(page)
            page.wait_for_timeout(4000)
        for _ in range(scrolls):
            page.mouse.wheel(0, 1400)
            page.wait_for_timeout(2500)
        if not found and looks_blocked(page):
            raise Blocked("verification or login wall shown")
        for n, sid in enumerate(order, 1):
            found[sid]["rank"] = n
        return [found[s] for s in order]
    finally:
        page.close()
