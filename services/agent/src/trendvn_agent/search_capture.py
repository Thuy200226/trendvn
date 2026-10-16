"""The part every search shares: collect the videos a page's own network responses carry, and wait for them while watching for a check
that only the owner may solve. Nothing is ever guessed from page text."""

import json
from urllib.parse import urlsplit

from .browser_errors import navigation_error

MAX_RESPONSE = 4 << 20


class Capture:
    """The videos found so far, by source id. `markers` are the path parts of the responses worth reading, `parse` turns a decoded JSON
    answer into videos, and `wanted` (when the owner gave exact links) keeps out every video that is not one of them."""

    def __init__(self, markers, parse, wanted=()):
        self.markers, self.parse, self.wanted, self.seen = markers, parse, tuple(wanted), {}

    def take(self, items):
        for item in items:
            if not self.wanted or item["url"] in self.wanted:
                self.seen[item["source_id"]] = item

    def on_response(self, response):
        path = urlsplit(response.url).path
        if response.status != 200 or not any(marker in path for marker in self.markers):
            return
        try:
            raw = response.body()
            if len(raw) <= MAX_RESPONSE:
                try:
                    self.take(self.parse(json.loads(raw)))
                except Exception:
                    text = raw.decode("utf-8", errors="replace")
                    for line in text.splitlines():
                        line = line.strip()
                        if line.startswith("{") and line.endswith("}"):
                            try:
                                self.take(self.parse(json.loads(line)))
                            except Exception:
                                pass
        except Exception:
            return  # an unreadable browser response is never a guessed video


def navigate(page, url, human):
    """A navigation failure must not take away the window the owner is trying to recover."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
    except Exception:
        if not human:
            raise


def wait_for_results(page, capture, human, check, rounds, resume=None, owner_window=False):
    """Poll until videos arrive, bounded only for unattended searches. `check(page)` raises ValueError for a login or verification wall: with
    the owner's own window open that is something to wait out, otherwise it is the answer."""
    was_blocked = False
    remaining = rounds
    while remaining > 0:
        remaining -= 1
        if page.is_closed():
            return
        try:
            page.wait_for_timeout(2000)
            check(page)
        except ValueError:
            if human or owner_window:
                was_blocked = True
                remaining += 1  # a verification round does not consume the bounded result wait
                continue
            raise
        except Exception as error:
            if not (human or owner_window) or not navigation_error(error):
                raise
            remaining += 1
            continue
        if resume and resume(page, was_blocked):
            continue
        if capture.seen:
            return
