"""The part every search shares: collect the videos a page's own network responses carry, and wait for them while watching for a check
that only the owner may solve. Nothing is ever guessed from page text."""

import json
from urllib.parse import urlsplit

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
                self.take(self.parse(json.loads(raw)))
        except Exception:
            return  # an unreadable browser response is never a guessed video


def wait_for_results(page, capture, human, check, rounds, resume=None):
    """Poll the page until videos arrive or the rounds run out. `check(page)` raises ValueError for a login or verification wall: with
    the owner's own window open that is something to wait out, otherwise it is the answer."""
    was_blocked = False
    for _ in range(120 if human else rounds):
        if page.is_closed():
            return
        page.wait_for_timeout(2000)
        try:
            check(page)
        except ValueError:
            if human:
                was_blocked = True
                continue
            raise
        if resume and resume(page, was_blocked):
            continue
        if capture.seen:
            return
