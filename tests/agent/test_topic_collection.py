"""Collecting by topic: which categories are read, how a scan is reported, and which candidates are downloaded."""

import inspect
import unittest
from unittest import mock

from tests.support import StoreCase
from trendvn_agent.collector import capture, run
from trendvn_agent.collector.rules import choose_downloads
from trendvn_agent.collector.sources import SOURCES, douyin, tiktok
from trendvn_worker.domain import topics


def job(source_id, hint=None):
    return {"id": "id-" + source_id, "platform": "douyin", "source_id": source_id, "topic_hint": hint}


class ChooseDownloadsTests(unittest.TestCase):
    def test_topics_take_turns_best_score_first(self):
        pending = [job("a1", "pets"), job("a2", "pets"), job("b1", "food"), job("c1", None), job("a3", "pets")]
        scores = {"a1": 90, "a2": 80, "a3": 70, "b1": 50, "c1": 60}
        picked = [j["source_id"] for j in choose_downloads(pending, scores, ["pets", "food"], 4)]
        self.assertEqual(picked, ["a1", "c1", "b1", "a2"])  # one from each group before a second from the busiest

    def test_a_busy_topic_cannot_crowd_out_the_others(self):
        pending = [job("p%d" % i, "pets") for i in range(10)] + [job("f1", "food")]
        scores = {j["source_id"]: 100 - i for i, j in enumerate(pending)}
        scores["f1"] = 1
        picked = {j["source_id"] for j in choose_downloads(pending, scores, ["pets", "food"], 3)}
        self.assertIn("f1", picked)

    def test_videos_of_a_topic_nobody_takes_are_skipped_but_unknown_ones_are_kept(self):
        pending = [job("g", "gaming"), job("u", None), job("p", "pets")]
        picked = [j["source_id"] for j in choose_downloads(pending, {"g": 99, "u": 1, "p": 2}, ["pets"], 5)]
        self.assertEqual(sorted(picked), ["p", "u"])

    def test_without_wishes_nothing_is_filtered_and_the_limit_holds(self):
        pending = [job("g", "gaming"), job("p", "pets"), job("x", None)]
        self.assertEqual(len(choose_downloads(pending, {}, [], 2)), 2)
        self.assertEqual(choose_downloads([], {}, ["pets"], 3), [])
        self.assertEqual(choose_downloads(pending, {}, [], 0), [])


class DouyinTabsTests(unittest.TestCase):
    def test_every_tab_belongs_to_a_known_topic(self):
        self.assertTrue(set(douyin.TABS) <= set(topics.TOPIC_IDS))
        self.assertTrue(set(tiktok.CHIPS) <= set(topics.TOPIC_IDS))

    def test_tabs_are_limited_and_take_turns(self):
        every = list(douyin.TABS)
        self.assertEqual(douyin.tabs_this_scan(["pets", "nothing"]), ["pets"])  # only topics that have a tab
        self.assertEqual(douyin.tabs_this_scan([]), [])
        first = douyin.tabs_this_scan(every, now=0)
        later = douyin.tabs_this_scan(every, now=10800)
        self.assertEqual((len(first), len(later)), (douyin.MAX_TABS, douyin.MAX_TABS))
        self.assertNotEqual(first, later)
        seen = {t for hour in range(len(every)) for t in douyin.tabs_this_scan(every, now=hour * 10800)}
        self.assertEqual(seen, set(every))  # every topic gets its turn

    def test_the_scan_has_the_general_feed_plus_one_stream_per_wanted_tab(self):
        def fake(ctx, url, match, parse, streams, **kw):
            self.assertEqual([name for name, _ in streams], ["jingxuan", "jingxuan_pets", "jingxuan_food"])
            self.assertIsNone(streams[0][1])  # the first stream is the page as it loads
            return {"jingxuan": [{"source_id": "1"}], "jingxuan_pets": [{"source_id": "2"}], "jingxuan_food": []}

        with mock.patch.object(douyin, "capture_streams", fake):
            found = douyin.scan_douyin(None, ["pets", "food", "nothing"])
        self.assertNotIn("topic", found["jingxuan"][0])  # the general feed has no category of its own
        self.assertEqual(found["jingxuan_pets"][0]["topic"], "pets")

    def test_nothing_at_all_is_reported_as_blocked(self):
        with mock.patch.object(douyin, "capture_streams", lambda *a, **k: {"jingxuan": [], "jingxuan_pets": []}):
            with self.assertRaises(capture.Blocked):
                douyin.scan_douyin(None, ["pets"])

    def test_every_source_accepts_the_topic_list(self):
        for name, source in SOURCES.items():
            self.assertIn("topics", inspect.signature(source["scan"]).parameters, name)


class TikTokChipsTests(unittest.TestCase):
    def test_wanted_chips_are_read_and_a_missing_chip_is_skipped_without_retries(self):
        calls = []

        def fake(ctx, url, match, parse, before_scroll=None, **kw):
            calls.append(before_scroll)
            if len(calls) == 2:
                raise capture.NotThere("Food")
            return [{"source_id": str(len(calls))}]

        with mock.patch.object(tiktok, "capture", fake):
            found = tiktok.scan_tiktok(None, ["pets", "food", "gaming", "travel"])  # travel has no chip
        self.assertEqual(sorted(found), ["explore_food", "explore_gaming", "explore_pets"])
        self.assertEqual(found["explore_food"], [])
        self.assertEqual(found["explore_pets"][0]["topic"], "pets")
        self.assertEqual(len(calls), 3)

    def test_without_wishes_a_few_default_chips_are_read(self):
        with mock.patch.object(tiktok, "capture", lambda *a, **k: []):
            self.assertEqual(sorted(tiktok.scan_tiktok(None, [])), ["explore_comedy", "explore_movies", "explore_music"])

    def test_a_verification_wall_stops_the_scan(self):
        def blocked(*a, **k):
            raise capture.Blocked("wall")

        with mock.patch.object(tiktok, "capture", blocked):
            with self.assertRaises(capture.Blocked):
                tiktok.scan_tiktok(None, ["pets"])

    def test_click_chip_raises_not_there_when_the_chip_is_missing(self):
        page = mock.MagicMock()
        page.locator.return_value.first.count.return_value = 0
        with self.assertRaises(capture.NotThere):
            tiktok.click_chip("Food")(page)


class FakePage:
    """A page that 'loads' scripted responses: each stream phase gets the batches queued for it."""

    def __init__(self, script):
        self.script = script  # list of lists of response payloads, one list per phase
        self.phase = -1
        self.handler = None
        self.mouse = mock.MagicMock()
        self.closed = False

    def on(self, event, handler):
        self.handler = handler

    def goto(self, *a, **k):
        self.advance()

    def wait_for_timeout(self, ms):
        pass

    def advance(self):
        self.phase += 1
        for payload in self.script[self.phase] if self.phase < len(self.script) else []:
            response = mock.MagicMock(status=200, url="https://x/feed", headers={"content-type": "application/json"})
            response.body.return_value = payload
            self.handler(response)

    def inner_text(self, *a, **k):
        return ""

    def close(self):
        self.closed = True


class CaptureStreamsTests(unittest.TestCase):
    def run_streams(self, script, enters):
        import json

        page = FakePage([[json.dumps(p).encode() for p in phase] for phase in script])
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        streams = [("general", None)] + [(name, enter) for name, enter in enters]
        parse = lambda payload: [{"source_id": i} for i in payload["ids"]]  # noqa: E731
        result = capture.capture_streams(ctx, "https://x", lambda u: "feed" in u, parse, streams, scrolls=1)
        return result, page

    def test_each_category_gets_only_the_videos_loaded_after_its_click(self):
        enter_a, enter_b = (lambda page: page.advance()), (lambda page: page.advance())
        result, page = self.run_streams(
            [[{"ids": ["g1", "g2"]}], [{"ids": ["a1", "g1"]}], [{"ids": ["b1"]}]], [("a", enter_a), ("b", enter_b)]
        )
        self.assertEqual([i["source_id"] for i in result["general"]], ["g1", "g2"])
        self.assertEqual([i["source_id"] for i in result["a"]], ["a1", "g1"])  # a video may belong to several streams
        self.assertEqual([i["rank"] for i in result["a"]], [1, 2])
        self.assertEqual([i["source_id"] for i in result["b"]], ["b1"])
        self.assertTrue(page.closed)

    def test_a_category_that_cannot_be_entered_is_skipped_and_the_rest_still_read(self):
        def broken(page):
            raise RuntimeError("tab gone")

        result, _ = self.run_streams([[{"ids": ["g1"]}], [{"ids": ["b1"]}]], [("a", broken), ("b", lambda page: page.advance())])
        self.assertEqual((result["a"], [i["source_id"] for i in result["b"]]), ([], ["b1"]))


class RunPlatformTopicTests(StoreCase):
    def test_the_batch_carries_the_streams_topic_and_the_scan_gets_the_wanted_topics(self):
        sent, scanned = [], []
        now = 1_790_000_000

        def scan(ctx, topics):
            scanned.append(list(topics))
            item = {"source_id": "1", "url": "https://www.douyin.com/video/1", "title": "t", "likes": 10**6, "views": None, "duration": 30,
                    "created": now - 3600, "rank": 1, "media": {}}  # fmt: skip
            return {"jingxuan": [dict(item)], "jingxuan_pets": [dict(item, topic="pets")]}

        class Source(dict):
            pass

        fake = {"country": "CN", "locale": "zh-CN", "scan": scan, "geo_locked": False}
        with (
            mock.patch.dict(SOURCES, {"douyin": fake}),
            mock.patch.object(run, "worker", lambda path, payload=None, **k: sent.append((path, payload)) or {"baseline": True, "new": 0}),
            mock.patch.object(run.time, "time", lambda: now),
        ):
            report = run.run_platform(None, "douyin", {"min_likes": {"douyin": 0}, "max_age_days": 30}, False, True, 3, ["pets", "food"])
        self.assertEqual(scanned, [["pets", "food"]])
        topics_sent = {p["stream"]: p["topic"] for path, p in sent if path == "/api/ingest"}
        self.assertEqual(topics_sent, {"jingxuan": None, "jingxuan_pets": "pets"})
        self.assertEqual(report["status"], "ok")
