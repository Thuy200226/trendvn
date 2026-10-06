"""TikTok search distinguishes actual video payloads and visible human verification from hidden components."""

from unittest import mock

from tests.support import StoreCase
from trendvn_agent.search import _blocked, _platforms, _tiktok_search, download_selected, search, video_items
from trendvn_agent.search_capture import Capture, wait_for_results


class SearchTests(StoreCase):
    def test_hidden_captcha_does_not_report_false_block(self):
        page = mock.Mock(url="https://www.tiktok.com/search/video?q=product")
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.nth.return_value.is_visible.return_value = False
        _blocked(page)
        page.locator.return_value.nth.return_value.is_visible.return_value = True
        with self.assertRaises(ValueError):
            _blocked(page)
        page.url = "https://www.tiktok.com/login"
        with self.assertRaises(ValueError):
            _blocked(page)

    def test_known_video_shapes_have_exact_id_and_media(self):
        item = {
            "id": "1234567890",
            "author": {"uniqueId": "creator"},
            "desc": "Xiaomi Band 9",
            "video": {"playAddr": "https://v16-webapp-prime.tiktok.com/video.mp4", "duration": 12},
        }
        for payload in ({"itemList": [item]}, {"data": [{"item": item}]}, {"itemInfo": {"itemStruct": item}}):
            result = video_items(payload)
            self.assertEqual(result[0]["source_id"], "1234567890")
            self.assertEqual(result[0]["url"], "https://www.tiktok.com/@creator/video/1234567890")
        self.assertEqual(video_items({"data": [{"user": {"uniqueId": "creator"}}]}), [])

    def test_expired_media_refreshes_only_exact_selected_video_once(self):
        item = {
            "url": "https://www.tiktok.com/@creator/video/1234567890",
            "source_id": "1234567890",
            "media": {"kind": "direct", "url": "expired"},
        }
        account = {"id": "main", "username": "creator"}
        from pathlib import Path

        with (
            mock.patch("trendvn_agent.search._account", return_value=account),
            mock.patch("trendvn_agent.search._verify"),
            mock.patch("trendvn_agent.search.chrome"),
            mock.patch("trendvn_agent.search.RUNTIME", Path(self.tmp.name)),
            mock.patch("trendvn_agent.search.download", side_effect=[ValueError("expired"), "fresh.mp4"]) as download,
            mock.patch("trendvn_agent.search.search", return_value={"items": [item]}) as search,
            mock.patch("trendvn_agent.search.worker", return_value={"state": "queued"}) as worker,
        ):
            self.assertEqual(download_selected({"account": "main", "job_id": "a" * 32, "item": item})["state"], "queued")
        self.assertEqual(search.call_args.args[0]["links"], [item["url"]])
        self.assertEqual(download.call_count, 2)
        worker.assert_called_once_with("/api/attach", {"id": "a" * 32, "filename": "fresh.mp4"})


TIKTOK = "https://www.tiktok.com/@creator/video/1234567890"
DOUYIN = "https://www.douyin.com/video/7234567890123456789"


def video(source_id="1234567890", **fields):
    return {"source_id": source_id, "url": "https://www.tiktok.com/@creator/video/" + source_id, "platform": "tiktok"} | fields


class CaptureTests(StoreCase):
    def response(self, path="/api/search/item_list", status=200, body=b"{}"):
        return mock.Mock(url="https://www.tiktok.com" + path, status=status, body=mock.Mock(return_value=body))

    def test_only_answers_of_the_wanted_paths_with_status_200_are_read(self):
        capture = Capture(("/api/search/",), lambda data: [video()])
        for response in (self.response("/other"), self.response(status=403)):
            capture.on_response(response)
        self.assertEqual(capture.seen, {})
        capture.on_response(self.response())
        self.assertEqual(list(capture.seen), ["1234567890"])

    def test_unreadable_oversized_or_unexpected_answers_never_become_videos(self):
        parse = mock.Mock(return_value=[video()])
        capture = Capture(("/api/search/",), parse)
        capture.on_response(self.response(body=b"not json"))
        capture.on_response(self.response(body=b'{"a":"' + b"x" * (4 << 20) + b'"}'))
        parse.assert_not_called()
        capture.parse = mock.Mock(side_effect=KeyError("shape changed"))
        capture.on_response(self.response())
        self.assertEqual(capture.seen, {})

    def test_exact_links_keep_out_every_other_video(self):
        capture = Capture(("/api/",), lambda data: [video("1234567890"), video("9999999999")], wanted=[TIKTOK])
        capture.on_response(self.response("/api/x"))
        self.assertEqual(list(capture.seen), ["1234567890"])

    def page(self, closed=False):
        return mock.Mock(is_closed=mock.Mock(return_value=closed))

    def test_waiting_stops_as_soon_as_videos_arrive(self):
        capture, page = Capture((), None), self.page()
        page.wait_for_timeout.side_effect = lambda ms: capture.take([video()])
        wait_for_results(page, capture, False, lambda p: None, rounds=5)
        self.assertEqual(page.wait_for_timeout.call_count, 1)

    def test_a_wall_is_the_answer_headless_and_something_to_wait_out_in_the_owners_window(self):
        capture, page = Capture((), None), self.page()
        wall = mock.Mock(side_effect=ValueError("TikTok yêu cầu xác minh"))
        with self.assertRaises(ValueError):
            wait_for_results(page, capture, False, wall, rounds=5)
        page.wait_for_timeout.reset_mock()
        capture.take([video()])  # results are held back while the wall is up: the owner is still solving it
        walls = [ValueError("TikTok yêu cầu xác minh")] * 2 + [None]
        wait_for_results(page, capture, True, mock.Mock(side_effect=walls), rounds=5)
        self.assertEqual(page.wait_for_timeout.call_count, 3)

    def test_a_closed_page_ends_the_wait(self):
        page = self.page(closed=True)
        wait_for_results(page, Capture((), None), True, lambda p: None, rounds=5)
        page.wait_for_timeout.assert_not_called()


class SearchRoutingTests(StoreCase):
    ACCOUNT = {"id": "main", "username": "creator"}

    def run_search(self, payload, tiktok=None, douyin=None, human=False):
        with (
            mock.patch("trendvn_agent.search._account", return_value=self.ACCOUNT),
            mock.patch("trendvn_agent.search._tiktok_search", **(tiktok or {"return_value": {"items": [video()], "note": "tt"}})) as tt,
            mock.patch(
                "trendvn_agent.search_douyin.search",
                **(douyin or {"return_value": {"items": [video("7", platform="douyin")], "note": "dy"}}),
            ) as dy,
        ):
            return search(payload, human), tt, dy

    def test_exact_links_choose_the_source_and_a_wrong_source_is_an_error(self):
        self.assertEqual(_platforms("auto", [TIKTOK], False), ("tiktok",))
        self.assertEqual(_platforms("auto", [DOUYIN], False), ("douyin",))
        self.assertEqual(_platforms("auto", [], False), ("douyin", "tiktok"))
        with self.assertRaises(ValueError):
            _platforms("douyin", [TIKTOK], False)
        for source, links, human in (("instagram", [], False), ("auto", [], True), ("tiktok", "x", False)):
            with self.subTest(source=source), self.assertRaises(ValueError):
                _platforms(source, links, human)

    def test_in_both_sources_each_gets_its_own_keywords_and_both_results_are_kept(self):
        result, tt, dy = self.run_search(
            {"account": "main", "source": "auto", "queries": {"tiktok": "mchose ace68", "douyin": "迈从 ACE68"}}
        )
        self.assertEqual(sorted(i["platform"] for i in result["items"]), ["douyin", "tiktok"])
        self.assertEqual(dy.call_args.args[1], "迈从 ACE68")
        self.assertEqual(tt.call_args.args[0]["query"], "mchose ace68")

    def test_one_source_failing_in_any_way_does_not_lose_the_other(self):
        for failure in (ValueError("CAPTCHA"), TimeoutError("page.goto: Timeout 45000ms exceeded"), RuntimeError("boom")):
            with self.subTest(failure=type(failure).__name__):
                result, _, _ = self.run_search({"account": "main", "source": "auto", "query": "x"}, douyin={"side_effect": failure})
                self.assertEqual([i["platform"] for i in result["items"]], ["tiktok"])
                self.assertIn("douyin: ", result["note"])

    def test_when_every_source_fails_the_reasons_are_the_error(self):
        with self.assertRaises(ValueError) as caught:
            self.run_search(
                {"account": "main", "source": "auto", "query": "x"},
                tiktok={"side_effect": TimeoutError("t")},
                douyin={"side_effect": ValueError("d")},
            )
        self.assertIn("douyin: d", str(caught.exception))
        self.assertIn("tiktok: t", str(caught.exception))

    def test_a_single_source_failure_is_the_error_itself(self):
        with self.assertRaises(ValueError) as caught:
            self.run_search(
                {"account": "main", "source": "tiktok", "query": "x"}, tiktok={"side_effect": TimeoutError("page.goto timed out")}
            )
        self.assertEqual(str(caught.exception), "page.goto timed out")

    def test_a_missing_or_oversized_keyword_stops_before_any_browser_opens(self):
        for queries in ({"tiktok": ""}, {"tiktok": "x" * 161}, {"tiktok": 5}):
            with self.subTest(queries=queries), self.assertRaises(ValueError):
                self.run_search({"account": "main", "source": "tiktok", "queries": queries})


class TikTokSearchTests(StoreCase):
    ACCOUNT = {"id": "main", "username": "creator"}

    def run_search(self, human, found=True, links=()):
        events = []

        def read(ctx, url, capture, human, direct):
            events.append(("read", url))
            if found:
                capture.take([video()])

        with (
            mock.patch("trendvn_agent.search._account", return_value=self.ACCOUNT),
            mock.patch("trendvn_agent.search._verify", side_effect=lambda ctx, account: events.append(("verify",))),
            mock.patch("trendvn_agent.search._read_page", side_effect=read),
            mock.patch("trendvn_agent.search.chrome") as chrome,
        ):
            result = _tiktok_search({"account": "main", "query": "mchose ace68", "links": list(links)}, human)
        return result, events, chrome

    def test_headless_the_session_is_verified_before_anything_is_read(self):
        result, events, chrome = self.run_search(False)
        self.assertEqual([e[0] for e in events], ["verify", "read"])
        self.assertEqual(chrome.call_args.kwargs["headless"], True)
        self.assertEqual(events[1][1], "https://www.tiktok.com/search/video?q=mchose%20ace68")
        self.assertEqual(result["items"][0]["source_id"], "1234567890")

    def test_in_the_owners_window_the_account_is_verified_after_the_results_and_only_when_there_are_some(self):
        _, events, chrome = self.run_search(True)
        self.assertEqual([e[0] for e in events], ["read", "verify"])
        self.assertEqual(chrome.call_args.kwargs["headless"], False)
        with self.assertRaises(ValueError):
            self.run_search(True, found=False)

    def test_exact_links_are_opened_instead_of_a_search_and_other_text_is_not_a_link(self):
        _, events, _ = self.run_search(False, links=[TIKTOK, "https://evil.example/x"])
        self.assertEqual([e[1] for e in events if e[0] == "read"], [TIKTOK])

    def test_no_videos_is_an_error_that_says_what_to_try(self):
        with self.assertRaises(ValueError) as caught:
            self.run_search(False, found=False)
        self.assertIn("TikTok không trả video", str(caught.exception))
