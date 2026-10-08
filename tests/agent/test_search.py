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
        for source, links, human in (("unknown", [], False), ("auto", [], True), ("tiktok", "x", False)):
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

    def test_what_each_source_turned_out_to_be_is_reported_so_the_dashboard_can_offer_sign_in(self):
        from trendvn_agent.channels import SignedOut, Wall

        with mock.patch("trendvn_agent.search.report") as report:
            self.run_search({"account": "main", "source": "auto", "query": "x"}, douyin={"side_effect": Wall("captcha")})
        self.assertEqual([c.args for c in report.call_args_list], [("main", "douyin", "wall"), ("main", "tiktok", "ok", "creator")])
        with mock.patch("trendvn_agent.search.report") as report:
            with self.assertRaises(ValueError):
                self.run_search({"account": "main", "source": "tiktok", "query": "x"}, tiktok={"side_effect": SignedOut("no session")})
        self.assertEqual([c.args for c in report.call_args_list], [("main", "tiktok", "out")])
        with mock.patch("trendvn_agent.search.report") as report:
            with self.assertRaises(ValueError):
                self.run_search({"account": "main", "source": "tiktok", "query": "x"}, tiktok={"side_effect": TimeoutError("slow")})
        report.assert_not_called()  # a timeout says nothing about the sign-in

    def test_a_source_that_says_it_proves_nothing_about_the_session_is_not_reported_as_ready(self):
        with mock.patch("trendvn_agent.search.report") as report:
            self.run_search(
                {"account": "main", "source": "douyin", "query": "x"},
                douyin={"return_value": {"items": [video("7", platform="douyin")], "note": "", "proves_session": False}},
            )
        report.assert_not_called()

    def test_an_exception_that_merely_has_a_state_attribute_is_not_taken_for_a_session_state(self):
        class Odd(ValueError):
            state = "banana"

        with mock.patch("trendvn_agent.search.report") as report:
            with self.assertRaises(ValueError):
                self.run_search({"account": "main", "source": "tiktok", "query": "x"}, tiktok={"side_effect": Odd("x")})
        report.assert_not_called()

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

    def run_four(self, payload, sources=("tiktok", "douyin", "kuaishou", "instagram")):
        asked = []

        def ask(platform, account, payload_, query, human):
            asked.append((platform, query))
            return {"items": [video(platform + "1", platform=platform)], "note": platform}

        with mock.patch("trendvn_agent.search._account", return_value=self.ACCOUNT), mock.patch("trendvn_agent.search._ask", ask):
            result = search(dict(payload, source="auto", sources=list(sources)))
        return result, dict(asked)

    def test_a_source_the_plan_has_no_words_for_borrows_the_words_of_its_own_language_instead_of_aborting_the_whole_search(self):
        plan = {"tiktok": "mchose ace68", "douyin": "迈从 ACE68"}  # what a product taken from a link or a video has
        result, asked = self.run_four({"queries": plan, "links": []})
        self.assertEqual(asked, {"tiktok": "mchose ace68", "douyin": "迈从 ACE68", "kuaishou": "迈从 ACE68", "instagram": "mchose ace68"})
        self.assertEqual(len(result["items"]), 4)

    def test_a_chinese_source_with_no_chinese_words_is_skipped_with_a_note_and_the_others_still_run(self):
        result, asked = self.run_four({"queries": {"tiktok": "bàn phím mchose"}, "query": "bàn phím mchose"})
        self.assertEqual(sorted(asked), ["instagram", "tiktok"])  # never Vietnamese sent to a Chinese site
        self.assertIn("douyin: chưa có từ khóa tiếng Trung", result["note"])
        self.assertIn("kuaishou: chưa có từ khóa tiếng Trung", result["note"])

    def test_with_only_the_plain_query_the_latin_sources_use_it(self):
        _, asked = self.run_four({"query": "mchose ace68"}, sources=("tiktok", "instagram"))
        self.assertEqual(asked, {"tiktok": "mchose ace68", "instagram": "mchose ace68"})

    def test_each_source_uses_its_own_words_before_borrowing_any(self):
        plan = {"tiktok": "t words", "instagram": "i words", "douyin": "抖 words", "kuaishou": "快 words"}
        _, asked = self.run_four({"queries": plan, "query": "plain"})
        self.assertEqual(asked, plan)

    def test_the_latin_sources_borrow_from_each_other_before_the_plain_query(self):
        _, asked = self.run_four({"queries": {"instagram": "i words"}, "query": "plain"}, sources=("tiktok", "instagram"))
        self.assertEqual(asked, {"tiktok": "i words", "instagram": "i words"})
        _, asked = self.run_four({"queries": {}, "query": "plain"}, sources=("tiktok", "instagram"))
        self.assertEqual(asked, {"tiktok": "plain", "instagram": "plain"})

    def test_the_chinese_sources_borrow_from_each_other_and_never_from_the_plain_query(self):
        _, asked = self.run_four({"queries": {"kuaishou": "快 words"}, "query": "plain"}, sources=("douyin", "kuaishou"))
        self.assertEqual(asked, {"douyin": "快 words", "kuaishou": "快 words"})

    def test_a_plan_that_is_missing_or_empty_never_hands_a_vietnamese_query_to_a_chinese_source(self):
        for plan in ({}, None):
            _, asked = self.run_four({"queries": plan, "query": "bàn phím cơ mini"})
            self.assertEqual(sorted(asked), ["instagram", "tiktok"], plan)

    def test_a_plain_model_name_or_chinese_query_may_go_to_the_chinese_sources(self):
        for plain in ("迈从 ACE68", "iPhone 15 Pro", "迈从 ACE68 bàn phím".replace(" bàn phím", "")):
            _, asked = self.run_four({"query": plain}, sources=("douyin", "kuaishou", "tiktok"))
            self.assertEqual(asked, {"douyin": plain, "kuaishou": plain, "tiktok": plain})

    def test_a_latin_source_with_no_words_is_skipped_without_losing_what_the_other_found(self):
        result, asked = self.run_four({"queries": {"douyin": "迈从 ACE68"}}, sources=("douyin", "tiktok"))
        self.assertEqual(list(asked), ["douyin"])
        self.assertEqual(len(result["items"]), 1)
        self.assertIn("tiktok: chưa có từ khóa", result["note"])

    def test_when_every_source_is_skipped_the_notes_are_the_error(self):
        with self.assertRaises(ValueError) as caught:
            self.run_four({"queries": {"tiktok": "x"}}, sources=("douyin", "kuaishou"))
        self.assertIn("tiếng Trung", str(caught.exception))

    def test_a_missing_or_oversized_keyword_stops_before_any_browser_opens(self):
        for queries in ({"tiktok": ""}, {"tiktok": "x" * 161}, {"tiktok": 5}):
            with self.subTest(queries=queries), self.assertRaises(ValueError):
                self.run_search({"account": "main", "source": "tiktok", "queries": queries})


class DouyinWallTests(StoreCase):
    """What a visitor Douyin does not trust meets (measured 2026-10-06): a blank page titled '验证码中间页', with no widget on it at all."""

    def page(self, title, widget=False):
        page = mock.Mock()
        page.title.return_value = title
        page.locator.return_value.count.return_value = 1 if widget else 0
        page.locator.return_value.nth.return_value.is_visible.return_value = widget
        return page

    def test_the_blank_verification_page_is_a_wall_even_with_no_widget_on_it(self):
        from trendvn_agent.channels import Wall
        from trendvn_agent.search_douyin import blocked, check

        self.assertTrue(blocked(self.page("验证码中间页")))
        self.assertTrue(blocked(self.page("  验证码中间页 ")))
        with self.assertRaises(Wall) as caught:
            check(self.page("验证码中间页"))
        self.assertIn("xác minh", str(caught.exception))

    def test_a_video_whose_title_merely_mentions_verification_is_not_a_wall(self):
        from trendvn_agent.search_douyin import blocked

        for title in (
            "Verify your phone - 抖音",
            "如何获取验证码 - 抖音",
            "Captcha solver demo",
            "验证码中间页教程 - 抖音",
            "迈从 ACE68 - 抖音搜索",
        ):
            self.assertFalse(blocked(self.page(title)), title)

    def test_a_widget_is_a_wall_whatever_the_title(self):
        from trendvn_agent.search_douyin import blocked

        self.assertTrue(blocked(self.page("抖音搜索", widget=True)))

    def test_a_page_that_is_changing_under_us_is_asked_again_not_a_crash(self):
        from trendvn_agent.search_douyin import blocked

        page = self.page("x")
        page.title.side_effect = RuntimeError("Execution context was destroyed")
        self.assertFalse(blocked(page))

    def test_a_keyword_search_that_found_videos_proves_a_session_and_a_video_opened_by_its_address_does_not(self):
        from trendvn_agent import search_douyin

        link = "https://www.douyin.com/video/7234567890123456789"
        item = {"source_id": "7234567890123456789", "url": link, "platform": "douyin"}

        def run(links, cookies):
            ctx = mock.Mock()
            ctx.cookies.return_value = cookies
            ctx.new_page.return_value = mock.Mock(is_closed=mock.Mock(return_value=False))

            def wait(page, capture, human, check, rounds):
                capture.take([item])

            from contextlib import contextmanager

            @contextmanager
            def launched(*args, **kwargs):
                yield ctx

            with (
                mock.patch.object(search_douyin, "chrome", launched),
                mock.patch.object(search_douyin, "wait_for_results", wait),
                mock.patch.object(search_douyin, "window_ok", return_value=True),
            ):
                return search_douyin.search({"id": "main"}, "x", links)

        guest, member = [{"name": "ttwid", "domain": ".douyin.com", "value": "x"}], [
            {"name": "sessionid", "domain": ".douyin.com", "value": "x"}
        ]
        self.assertTrue(run([], guest)["proves_session"])  # got past the wall with a keyword
        self.assertFalse(run([link], guest)["proves_session"])  # a public video opens for anyone
        self.assertTrue(run([link], member)["proves_session"])


class TikTokSearchTests(StoreCase):
    ACCOUNT = {"id": "main", "username": "creator"}

    def run_search(self, human, found=True, links=(), screen=False):
        events = []

        def read(ctx, url, capture, human, direct):
            events.append(("read", url))
            if found:
                capture.take([video()])

        with (
            mock.patch("trendvn_agent.search._account", return_value=self.ACCOUNT),
            mock.patch("trendvn_agent.search._verify", side_effect=lambda ctx, account: events.append(("verify",))),
            mock.patch("trendvn_agent.search._read_page", side_effect=read),
            mock.patch("trendvn_agent.search.window_ok", return_value=screen),
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

    def test_with_a_screen_the_search_runs_in_a_window_like_publishing_does(self):
        _, events, chrome = self.run_search(False, screen=True)
        self.assertEqual(chrome.call_args.kwargs["headless"], False)
        self.assertEqual([e[0] for e in events], ["verify", "read"])  # still verified before reading: a window is not a reason to skip it

    def test_in_the_owners_window_the_account_is_verified_after_the_results_and_only_when_there_are_some(self):
        _, events, chrome = self.run_search(True)
        self.assertEqual([e[0] for e in events], ["read", "verify"])
        self.assertEqual(chrome.call_args.kwargs["headless"], False)
        with self.assertRaises(ValueError):
            self.run_search(True, found=False)

    def test_a_profile_signed_in_as_someone_else_is_a_signed_out_state_naming_the_account_wanted(self):
        from trendvn_agent.channels import SignedOut
        from trendvn_agent.search import _verify

        with (
            mock.patch("trendvn_agent.search.logged_in", return_value=True),
            mock.patch("trendvn_agent.search.signed_in_as", return_value="somebody_else"),
            self.assertRaises(SignedOut) as caught,
        ):
            _verify(mock.Mock(), {"id": "main", "username": "creator"})
        self.assertIn("@creator", str(caught.exception))

    def test_a_signed_out_profile_is_told_how_to_sign_in_for_that_very_account(self):
        from trendvn_agent.search import _verify

        for account_id, flag in (("main", ""), ("pets", " --account pets")):
            with mock.patch("trendvn_agent.search.logged_in", return_value=False), self.assertRaises(ValueError) as caught:
                _verify(mock.Mock(), {"id": account_id, "username": "creator"})
            self.assertIn("./trendvn tiktok login" + flag, str(caught.exception))
            self.assertTrue(str(caught.exception).endswith(flag or "login"))

    def test_exact_links_are_opened_instead_of_a_search_and_other_text_is_not_a_link(self):
        _, events, _ = self.run_search(False, links=[TIKTOK, "https://evil.example/x"])
        self.assertEqual([e[1] for e in events if e[0] == "read"], [TIKTOK])

    def test_no_videos_is_an_error_that_says_what_to_try(self):
        with self.assertRaises(ValueError) as caught:
            self.run_search(False, found=False)
        self.assertIn("TikTok không trả video", str(caught.exception))


class ChannelRouteTests(StoreCase):
    def test_a_channel_request_needs_a_known_channel_and_account(self):
        from trendvn_agent import server

        with mock.patch("trendvn_agent.search._account", return_value={"id": "main", "username": "creator"}):
            self.assertEqual(server._channel_args({"channel": "douyin", "account": "main"})[2], "douyin")
            for payload in ({"channel": "myspace", "account": "main"}, {"account": "main"}, {"channel": None}):
                with self.subTest(payload=payload), self.assertRaises(ValueError):
                    server._channel_args(payload)
        self.assertIn("/api/channel/login", server.ROUTES)
        self.assertIn("/api/channel/check", server.ROUTES)
