"""TikTok search distinguishes actual video payloads and visible human verification from hidden components."""

from unittest import mock

from tests.support import StoreCase
from trendvn_agent.search import _blocked, video_items, download_selected


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
