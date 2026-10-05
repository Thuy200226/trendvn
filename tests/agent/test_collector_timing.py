"""The collector logs how long a page took to answer after each scroll and tab click (what its waits are tuned against, Phase H)."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_agent.collector import capture


class Clock:
    def __init__(self):
        self.now = 1000.0

    def time(self):
        return self.now


class FakePage:
    """A page on a fake clock: an answer with videos arrives `delays` seconds after each wheel (a missing delay is an empty scroll)."""

    def __init__(self, clock, delays):
        self.clock, self.delays, self.handler, self.wheeled_at, self.sent = clock, list(delays), None, None, 0
        self.mouse = SimpleNamespace(wheel=self.wheel)

    def on(self, event, handler):
        self.handler = handler

    def wheel(self, dx, dy):
        self.wheeled_at, self.due = self.clock.now, self.delays.pop(0)

    def wait_for_timeout(self, ms):
        self.clock.now += ms / 1000
        if self.due is not None and self.clock.now - self.wheeled_at >= self.due:
            self.due = None
            ids = ["v%d" % (self.sent + n) for n in range(20)]
            self.sent += 20
            self.handler(
                SimpleNamespace(
                    status=200,
                    url="https://x/feed",
                    headers={"content-type": "application/json"},
                    body=lambda ids=ids: json.dumps(ids).encode(),
                )
            )


class ScrollTimingTests(unittest.TestCase):
    def feed(self, delays):
        clock = Clock()
        page = FakePage(clock, delays)
        feed = capture.Feed(page, lambda url: True, lambda body: [{"source_id": i} for i in body], ["s"])
        return feed, clock

    def test_every_scroll_logs_what_it_brought_and_how_fast_the_page_answered(self):
        feed, clock = self.feed([1.0, None])  # the first scroll is answered after one second, the second brings nothing
        lines = []
        with mock.patch.multiple(capture, time=clock, log=lines.append):
            feed.scroll(2)
        self.assertEqual(len(lines), 2)
        self.assertIn("scroll 1/2: +20 videos, answer after", lines[0])
        self.assertRegex(lines[0], r"answer after 1\.0s, settled after 2\.0s")
        self.assertIn("scroll 2/2: +0 videos, no answer, settled after 3.0s", lines[1])  # an empty scroll waits the whole ceiling

    def test_the_feed_is_read_the_same_way_with_the_log_in_place(self):
        feed, clock = self.feed([0.5, 0.5, 0.5])
        with mock.patch.multiple(capture, time=clock, log=lambda line: None):
            feed.scroll(3)
        self.assertEqual(feed.count(), 60)


if __name__ == "__main__":
    unittest.main()
