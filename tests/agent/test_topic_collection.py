"""Collecting by topic: which categories are read, how a scan is reported, and which candidates are downloaded."""

import inspect
import json
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

    def test_tab_ids_belong_to_known_tabs_and_name_the_stream(self):
        self.assertEqual(set(douyin.TAG_IDS), set(douyin.TABS))
        self.assertEqual(len(set(douyin.TAG_IDS.values())), len(douyin.TAG_IDS))
        names = {"jingxuan", "jingxuan_pets", "jingxuan_food"}
        url = (
            "https://www.douyin.com/aweme/v2/web/module/feed/?module_id=3003101&count=20&refresh_index=1&tag_id=%s" % douyin.TAG_IDS["pets"]
        )
        self.assertEqual(douyin.stream_of(url, names), "jingxuan_pets")
        self.assertIsNone(douyin.stream_of(url.replace(douyin.TAG_IDS["pets"], "999"), names))  # an id we do not know
        self.assertIsNone(douyin.stream_of(url, {"jingxuan"}))  # a tab that is not being read in this scan
        self.assertIsNone(douyin.stream_of("https://www.douyin.com/aweme/v2/web/module/feed/?count=20", names))

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

    def test_with_more_chips_wanted_than_the_limit_they_take_turns(self):
        scanned = []

        def fake(ctx, url, match, parse, before_scroll=None, **kw):
            return []

        every = list(tiktok.CHIPS)
        with mock.patch.object(tiktok, "capture", fake):
            first = sorted(tiktok.scan_tiktok(None, every))
        self.assertEqual(len(first), tiktok.MAX_CHIPS)
        with mock.patch("trendvn_agent.collector.rules.time.time", lambda: 10800):
            with mock.patch.object(tiktok, "capture", fake):
                later = sorted(tiktok.scan_tiktok(None, every))
        self.assertNotEqual(first, later)
        del scanned

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
        page.locator.return_value.first.wait_for.side_effect = RuntimeError("timeout")
        with self.assertRaises(capture.NotThere):
            tiktok.click_chip("Food")(page)

    def test_click_chip_waits_for_the_chip_to_appear_before_clicking(self):
        page = mock.MagicMock()
        tiktok.click_chip("Food")(page)
        chip = page.locator.return_value.first
        chip.wait_for.assert_called_once()
        chip.click.assert_called_once()


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
    def run_streams(self, script, enters, **kw):
        import json

        page = FakePage([[json.dumps(p).encode() for p in phase] for phase in script])
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        streams = [("general", None)] + [(name, enter) for name, enter in enters]
        parse = lambda payload: [{"source_id": i} for i in payload["ids"]]  # noqa: E731
        result = capture.capture_streams(ctx, "https://x", lambda u: "feed" in u, parse, streams, scrolls=1, quiet_ms=0, **kw)
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

    def test_a_response_is_filed_by_the_category_in_its_request_however_late_it_arrives(self):
        import json

        # the pets answer comes in after the click on "food": by the tag in its URL it still belongs to pets
        page = FakePage([])
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page

        def payload(ids):
            return json.dumps({"ids": ids}).encode()

        def respond(url, ids):
            response = mock.MagicMock(status=200, url=url, headers={"content-type": "application/json"})
            response.body.return_value = payload(ids)
            page.handler(response)

        def enter_pets(p):
            respond("https://x/feed?tag_id=2", ["p1"])

        def enter_food(p):
            respond("https://x/feed?tag_id=2", ["p2-late"])  # arrives while "food" is the stream being read
            respond("https://x/feed?tag_id=3", ["f1"])

        streams = [("general", None), ("pets", enter_pets), ("food", enter_food)]
        route = lambda url: {"2": "pets", "3": "food"}.get(url.rsplit("=", 1)[1])  # noqa: E731
        result = capture.capture_streams(
            ctx,
            "https://x",
            lambda u: "feed" in u,
            lambda d: [{"source_id": i} for i in d["ids"]],
            streams,
            route=route,
            quiet_ms=0,
            scrolls=1,
        )
        self.assertEqual([i["source_id"] for i in result["pets"]], ["p1", "p2-late"])
        self.assertEqual([i["source_id"] for i in result["food"]], ["f1"])

    def test_a_failure_while_reading_one_category_keeps_everything_read_before_it(self):
        def breaks_the_page(page):
            page.advance()
            raise RuntimeError("page crashed")

        result, _ = self.run_streams([[{"ids": ["g1"]}], [{"ids": ["a1"]}]], [("a", breaks_the_page), ("b", lambda page: page.advance())])
        self.assertEqual([i["source_id"] for i in result["general"]], ["g1"])
        self.assertEqual([i["source_id"] for i in result["a"]], ["a1"])  # what arrived before the crash is kept

    def test_an_empty_load_is_retried_with_a_fresh_page_then_reported(self):
        pages = [FakePage([[]]), FakePage([[json.dumps({"ids": ["g1"]}).encode()]])]
        ctx = mock.MagicMock()
        ctx.new_page.side_effect = pages
        with mock.patch.object(capture.time, "sleep", lambda s: None):
            result = capture.capture_streams(
                ctx,
                "https://x",
                lambda u: "feed" in u,
                lambda d: [{"source_id": i} for i in d["ids"]],
                [("g", None)],
                quiet_ms=0,
                scrolls=1,
            )
        self.assertEqual([i["source_id"] for i in result["g"]], ["g1"])
        empty = mock.MagicMock()
        empty.new_page.side_effect = lambda: FakePage([[]])
        with mock.patch.object(capture.time, "sleep", lambda s: None), self.assertRaises(capture.Blocked):
            capture.capture_streams(empty, "https://x", lambda u: "feed" in u, lambda d: [], [("g", None)], quiet_ms=0, scrolls=1)
        self.assertEqual(empty.new_page.call_count, 3)


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


class ClockedPage:
    """A page on a fake clock: waiting advances it, and scripted answers arrive at given times."""

    def __init__(self, clock, answers):
        self.clock, self.answers, self.waited, self.feed = clock, sorted(answers), 0, None
        self.mouse = mock.MagicMock()
        self.mouse.wheel.side_effect = lambda *a: None

    def close(self):
        pass

    def inner_text(self, *a, **k):
        return ""

    def goto(self, *a, **k):
        pass

    def on(self, event, handler):
        self.handler = handler

    def wait_for_timeout(self, ms):
        self.clock.now += ms / 1000
        self.waited += ms
        while self.answers and self.answers[0][0] <= self.clock.now:
            _, ids = self.answers.pop(0)
            response = mock.MagicMock(status=200, url="https://x/feed", headers={"content-type": "application/json"})
            response.body.return_value = json.dumps({"ids": ids}).encode()
            self.handler(response)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class AdaptiveWaitTests(unittest.TestCase):
    def feed(self, answers):
        clock = Clock()
        page = ClockedPage(clock, [(clock.now + at, ids) for at, ids in answers])
        patcher = mock.patch.object(capture.time, "time", clock)
        patcher.start()
        self.addCleanup(patcher.stop)
        feed = capture.Feed(page, lambda u: True, lambda d: [{"source_id": i} for i in d["ids"]], ["s"])
        return feed, page, clock

    def test_a_fast_page_does_not_wait_out_the_ceiling(self):
        feed, page, clock = self.feed([(1.0, ["a"]), (1.5, ["b"])])
        feed.settle(floor_ms=2000, ceiling_ms=12000, quiet_ms=1500, since=clock.now)
        self.assertLessEqual(page.waited, 3500)  # floor 2 s, then 1.5 s of quiet after the last answer at 1.5 s
        self.assertEqual(feed.count(), 2)

    def test_a_slow_first_answer_is_waited_for(self):
        feed, page, clock = self.feed([(7.0, ["a"])])
        feed.settle(floor_ms=4000, ceiling_ms=12000, quiet_ms=1500, since=clock.now)
        self.assertEqual(feed.count(), 1)
        self.assertGreaterEqual(page.waited, 7000)
        self.assertLess(page.waited, 12000)

    def test_answers_without_videos_do_not_end_the_wait(self):
        """Kuaishou answers a config call and a login query long before the feed itself: those say nothing about the feed."""
        feed, page, clock = self.feed([(0.5, []), (1.0, []), (7.0, ["a", "b"])])
        feed.settle(floor_ms=4000, ceiling_ms=12000, quiet_ms=1500, since=clock.now)
        self.assertEqual(feed.count(), 2)
        self.assertGreaterEqual(page.waited, 7000)

    def test_a_page_that_never_answers_stops_at_the_ceiling(self):
        feed, page, clock = self.feed([])
        feed.settle(floor_ms=4000, ceiling_ms=12000, quiet_ms=1500, since=clock.now)
        self.assertEqual(page.waited, 12000)

    def test_answers_from_before_the_click_do_not_count_as_its_answer(self):
        feed, page, clock = self.feed([(0.5, ["old"]), (6.0, ["new"])])
        page.wait_for_timeout(1000)
        feed.settle(floor_ms=2000, ceiling_ms=10000, quiet_ms=1500, since=clock.now)  # the click happens now; "old" was before it
        self.assertEqual(feed.count(), 2)

    def test_scrolling_stops_after_two_empty_scrolls_in_a_row(self):
        feed, page, clock = self.feed([(0.5, ["a"]), (3.0, ["b"])])
        page.wait_for_timeout(1000)
        feed.scroll(6)
        # scroll 1 finds "b"; scrolls 2 and 3 find nothing: stop, the other three never happen
        self.assertEqual(page.mouse.wheel.call_count, 3)
        self.assertEqual(feed.count(), 2)

    def test_one_empty_scroll_is_not_the_end(self):
        feed, page, clock = self.feed([(0.5, ["a"]), (5.5, ["b"])])  # the next page needs longer than the first scroll's wait
        page.wait_for_timeout(1000)
        feed.scroll(4)
        self.assertEqual(feed.count(), 2)

    def test_a_later_stream_without_a_click_is_filed_under_its_own_name(self):
        clock = Clock()
        page = ClockedPage(clock, [(clock.now + 1.0, ["x1"])])
        ctx = mock.MagicMock()
        ctx.new_page.return_value = page
        with mock.patch.object(capture.time, "time", clock):
            result = capture.capture_once_streams(
                ctx, "https://x", lambda u: True, lambda d: [{"source_id": i} for i in d["ids"]], [("first", None), ("second", None)],
                quiet_ms=0, scrolls=1,
            )  # fmt: skip
        self.assertEqual(sorted(result), ["first", "second"])
        self.assertEqual([i["source_id"] for i in result["first"]] + [i["source_id"] for i in result["second"]], ["x1"])


class BacklogTests(unittest.TestCase):
    def run_fetch(self, status):
        downloaded = []
        pending = [{"id": "id1", "platform": "douyin", "source_id": "s1", "topic_hint": None}]
        seen = {"s1": {"source_id": "s1", "score": 5}}

        def worker(path, payload=None, **k):
            return {"items": pending} if path == "/api/media/pending" else {"state": "queued"}

        with mock.patch.multiple(
            run,
            worker=worker,
            worker_get=lambda path, timeout=30: status,
            download=lambda ctx, item, platform: downloaded.append(item["source_id"]) or "f.mp4",
        ):
            report = run.fetch_pending(None, "douyin", seen, 3, [])
        return report, downloaded

    def test_rendered_videos_nobody_takes_do_not_stop_the_collector(self):
        status = {"counts": {"ready": 5}, "backlog": 0, "thresholds": {"max_backlog": 4}}
        report, downloaded = self.run_fetch(status)
        self.assertEqual((report["downloaded"], downloaded), (1, ["s1"]))

    def test_a_full_backlog_still_stops_it_and_an_older_worker_falls_back_to_the_counts(self):
        report, downloaded = self.run_fetch({"counts": {}, "backlog": 4, "thresholds": {"max_backlog": 4}})
        self.assertEqual((report["downloaded"], downloaded), (0, []))
        report, downloaded = self.run_fetch({"counts": {"ready": 4}, "thresholds": {"max_backlog": 4}})  # no "backlog" field
        self.assertEqual(downloaded, [])


class LoginWindowTests(unittest.TestCase):
    """`tiktok login` only counts once the window is signed in as the right account."""

    def test_a_wrong_sign_in_keeps_the_window_open_until_it_is_corrected(self):
        from trendvn_agent.publisher import session

        page = mock.MagicMock()
        ctx = mock.MagicMock(pages=[page])
        context = mock.MagicMock()
        context.__enter__.return_value = ctx
        context.__exit__.return_value = False
        answers = iter(["Hồ sơ đang đăng nhập @khac", "Hồ sơ đang đăng nhập @khac", None])
        reported = []
        with mock.patch.multiple(
            session,
            chrome=lambda *a, **k: context,
            logged_in=lambda c: True,
            wrong_account=lambda c, expected: next(answers),
            _report=lambda account, ok: reported.append((account, ok)),
        ):
            self.assertTrue(session.login(1, "pets", expected="meo"))
        self.assertEqual(reported, [("pets", True)])  # reported once, after the third look found the right account

    def test_without_an_expected_name_the_first_session_counts(self):
        from trendvn_agent.publisher import session

        context = mock.MagicMock()
        context.__enter__.return_value = mock.MagicMock(pages=[mock.MagicMock()])
        context.__exit__.return_value = False
        with mock.patch.multiple(session, chrome=lambda *a, **k: context, logged_in=lambda c: True, _report=lambda a, ok: None):
            self.assertTrue(session.login(1, None))
