"""Read the JSON a site's own page loads, inside Chrome; never solve a CAPTCHA, report it."""

import json
import re
import time

from ..log import log


class Blocked(Exception):
    pass


class NotThere(Exception):
    """A category button the site no longer has: skipping it is right, retrying is a waste of minutes."""


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
        except (Blocked, NotThere):
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


def capture_streams(ctx, url, match, parse, streams, attempts=3, **kw):
    """One page load, several streams (see `capture_once_streams`), retried with a fresh page when nothing at all came back, like
    `capture` does for a single stream."""
    last = None
    for n in range(1, attempts + 1):
        try:
            result = capture_once_streams(ctx, url, match, parse, streams, **kw)
            if any(result.values()):
                return result
            last = Blocked("no videos returned") if n == attempts else None
        except (Blocked, NotThere):
            raise
        except Exception as e:
            last = e
        log("capture retry %d/%d for %s" % (n, attempts, url))
        time.sleep(6 * n)
    if last:
        raise last
    return {name: [] for name, _ in streams}


def capture_once_streams(ctx, url, match, parse, streams, route=None, wait_ms=12000, scrolls=3, settle_ms=6000, quiet_ms=1000):
    """The page as it loads is the first stream; each further stream is entered with a click on a category (`enter(page)`), after which
    the videos the page loads belong to it. `route(url)` may name the stream a response belongs to (a category id in the request), which
    is exact; without it a response goes to the stream being read, and a short quiet spell before each click keeps the previous
    category's late answers out of the next one. Returns {name: [items]}. A category that cannot be entered, or a failure while reading
    one, gives what was read so far for it and never costs the others. `streams` is [(name, enter or None), ...]."""
    page = ctx.new_page()
    found = {name: {} for name, _ in streams}
    order = {name: [] for name, _ in streams}
    current = [streams[0][0]]
    last_response = [time.time()]

    def on_response(r):
        try:
            if r.status == 200 and match(r.url) and "json" in r.headers.get("content-type", ""):
                last_response[0] = time.time()
                named = route(r.url) if route else None
                name = named if named in found else current[0]
                bucket, ids = found[name], order[name]
                for item in parse(json.loads(r.body())):
                    if item["source_id"] not in bucket:
                        bucket[item["source_id"]] = item
                        ids.append(item["source_id"])
        except Exception:
            pass

    def drain():
        waited = 0
        while time.time() - last_response[0] < quiet_ms / 1000 and waited < 6000:
            page.wait_for_timeout(250)
            waited += 250

    page.on("response", on_response)
    try:
        try:
            page.goto(url, wait_until="commit", timeout=60000)
        except Exception as e:
            log("goto warning %s: %s" % (url, str(e)[:100]))
        page.wait_for_timeout(wait_ms)
        for index, (name, enter) in enumerate(streams):
            try:
                if enter is not None:
                    drain()
                    current[0] = name
                    enter(page)
                    page.wait_for_timeout(settle_ms)
                for _ in range(scrolls):
                    page.mouse.wheel(0, 1400)
                    page.wait_for_timeout(2000)
                if index == 0 and not found[name] and looks_blocked(page):
                    raise Blocked("verification or login wall shown")
            except Blocked:
                raise
            except Exception as e:
                log("category %s skipped: %s" % (name, str(e)[:100]))
        for name, _ in streams:
            for n, sid in enumerate(order[name], 1):
                found[name][sid]["rank"] = n
        return {name: [found[name][s] for s in order[name]] for name, _ in streams}
    finally:
        page.close()
