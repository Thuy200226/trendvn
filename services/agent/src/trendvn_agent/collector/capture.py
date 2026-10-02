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


class Feed:
    """The matching JSON answers a page loads, filed by stream, and a way to wait until the page has gone quiet (instead of sleeping a
    fixed time: a fast page costs seconds, a slow one still gets its chance)."""

    def __init__(self, page, match, parse, names, route=None):
        self.page, self.match, self.parse, self.route = page, match, parse, route
        self.found = {name: {} for name in names}
        self.order = {name: [] for name in names}
        self.current = names[0]
        self.last = 0.0  # when the last matching answer arrived
        page.on("response", self._on_response)

    def _on_response(self, r):
        try:
            if r.status == 200 and self.match(r.url) and "json" in r.headers.get("content-type", ""):
                items = self.parse(json.loads(r.body()))
                if not items:
                    return  # an answer without videos (a config call, a login query) says nothing about whether the feed has arrived
                self.last = time.time()
                named = self.route(r.url) if self.route else None
                name = named if named in self.found else self.current
                bucket, ids = self.found[name], self.order[name]
                for item in items:
                    if item["source_id"] not in bucket:
                        bucket[item["source_id"]] = item
                        ids.append(item["source_id"])
        except Exception:
            pass

    def count(self):
        return len(self.order[self.current])

    def settle(self, floor_ms, ceiling_ms, quiet_ms, since):
        """Wait at least floor_ms; then until an answer has arrived after `since` and none for quiet_ms; never longer than ceiling_ms."""
        waited = 0
        while waited < ceiling_ms:
            self.page.wait_for_timeout(250)
            waited += 250
            if waited >= floor_ms and self.last > since and time.time() - self.last >= quiet_ms / 1000:
                return

    def drain(self, quiet_ms, ceiling_ms=6000):
        """Let the previous category's late answers arrive before the next click, so they are not filed under the next one."""
        waited = 0
        while waited < ceiling_ms and time.time() - self.last < quiet_ms / 1000:
            self.page.wait_for_timeout(250)
            waited += 250

    def scroll(self, times):
        """Scroll down for more; stop after two scrolls in a row that bring nothing new (the feed is exhausted; one empty scroll can just
        be a slow answer or a page that needs a longer scroll)."""
        empty = 0
        for _ in range(times):
            before, mark = self.count(), time.time()
            self.page.mouse.wheel(0, 1400)
            self.settle(750, 3000, 1000, mark)
            empty = empty + 1 if self.count() == before else 0
            if empty == 2:
                return

    def result(self):
        for name, ids in self.order.items():
            for n, sid in enumerate(ids, 1):
                self.found[name][sid]["rank"] = n
        return {name: [self.found[name][sid] for sid in ids] for name, ids in self.order.items()}


def capture_once(ctx, url, match, parse, scrolls=4, wait_ms=12000, before_scroll=None):
    page = ctx.new_page()
    feed = Feed(page, match, parse, ["feed"])
    try:
        mark = time.time()
        try:
            page.goto(url, wait_until="commit", timeout=60000)
        except Exception as e:
            log("goto warning %s: %s" % (url, str(e)[:100]))
        feed.settle(4000, wait_ms, 2500, mark)
        if before_scroll:
            mark = time.time()
            before_scroll(page)
            feed.settle(2000, 4000, 1500, mark)
        feed.scroll(scrolls)
        if not feed.count() and looks_blocked(page):
            raise Blocked("verification or login wall shown")
        return feed.result()["feed"]
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
        if n < attempts:
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
    feed = Feed(page, match, parse, [name for name, _ in streams], route)
    try:
        mark = time.time()
        try:
            page.goto(url, wait_until="commit", timeout=60000)
        except Exception as e:
            log("goto warning %s: %s" % (url, str(e)[:100]))
        feed.settle(4000, wait_ms, 2500, mark)
        for index, (name, enter) in enumerate(streams):
            started = time.time()
            try:
                feed.current = name
                if enter is not None:
                    feed.drain(quiet_ms)
                    mark = time.time()
                    enter(page)
                    feed.settle(2000, settle_ms, 1500, mark)
                feed.scroll(scrolls)
                if index == 0 and not feed.count() and looks_blocked(page):
                    raise Blocked("verification or login wall shown")
            except Blocked:
                raise
            except Exception as e:
                log("category %s skipped: %s" % (name, str(e)[:100]))
            log("read %s: %d videos in %.0fs" % (name, feed.count(), time.time() - started))
        return feed.result()
    finally:
        page.close()
