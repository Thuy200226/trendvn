"""Platform parsers, engagement gates and the trending score."""

import time
import unittest
from pathlib import Path

from tests.support import TZ, StoreCase, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_agent.collector.rules import qualifies, score
from trendvn_agent.collector.sources import douyin, instagram, kuaishou, tiktok

ROOT = Path(__file__).resolve().parents[2]


TH = {"min_views": {"kuaishou": 1000000, "tiktok": 1000000}, "min_likes": {"douyin": 150000}, "max_duration": 180}


class ParserTests(unittest.TestCase):
    def test_douyin_keeps_only_real_videos(self):
        video = {
            "aweme_id": "123456",
            "aweme_type": 0,
            "desc": "hi",
            "duration": 30000,
            "statistics": {"digg_count": 200000},
            "video": {"play_addr": {"url_list": ["http://v5.zjcdn.com/a.mp4"]}},
        }
        payload = {
            "aweme_list": [
                video,
                dict(video, aweme_id="9", aweme_type=68),
                dict(video, aweme_id="8", is_ads=True),
                {"aweme_id": "7", "aweme_type": 101},
                dict(video, aweme_id="6", statistics={}),
            ]
        }
        items = douyin.parse_douyin(payload)
        self.assertEqual([i["source_id"] for i in items], ["123456"])
        self.assertTrue(items[0]["media"]["url"].startswith("https://"))
        self.assertEqual(items[0]["url"], "https://www.douyin.com/video/123456")

    def test_kuaishou_feed(self):
        feed = {
            "photo": {
                "id": "3xabc",
                "caption": "c",
                "viewCount": "2000000",
                "realLikeCount": 5,
                "duration": 20000,
                "photoUrl": "https://v.kwaicdn.com/x.mp4",
            }
        }
        items = kuaishou.parse_kuaishou(
            {"data": {"brilliantTypeData": {"feeds": [feed, {"photo": {"id": "x/../y", "photoUrl": "u"}}, {}]}}}
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["views"], 2000000)
        self.assertEqual(items[0]["duration"], 20.0)

    def test_tiktok_skips_ads_and_bad_ids(self):
        good = {
            "id": "7688988035727363348",
            "desc": "d",
            "author": {"uniqueId": "user.one"},
            "stats": {"playCount": 4400000, "diggCount": 1},
            "video": {"duration": 13, "playAddr": "https://v16.tiktok.com/v.mp4"},
        }
        items = tiktok.parse_tiktok(
            {"itemList": [good, dict(good, isAd=True), dict(good, id="12"), dict(good, author={"uniqueId": "a/b"})]}
        )
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://www.tiktok.com/@user.one/video/7688988035727363348")

    def test_instagram_codes_deduplicated_in_order(self):
        text = '/reels/DdPgJ99Ps8d/ "code":"Ddz3t5_K43z" /reel/DdPgJ99Ps8d/ /reels/audio/ "code":"en_US"'
        self.assertEqual(instagram.parse_instagram_codes(text), ["DdPgJ99Ps8d", "Ddz3t5_K43z"])  # locale tags are not reel codes


class GateTests(unittest.TestCase):
    def item(self, **kw):
        return dict({"duration": 30, "views": 2000000, "likes": 200000}, **kw)

    def test_long_video_rejected(self):
        self.assertFalse(qualifies("tiktok", self.item(duration=181), TH))

    def test_low_views_rejected(self):
        self.assertFalse(qualifies("kuaishou", self.item(views=999999), TH))

    def test_douyin_needs_likes(self):
        self.assertFalse(qualifies("douyin", self.item(views=None, likes=1000), TH))
        self.assertTrue(qualifies("douyin", self.item(views=None, likes=200000), TH))

    def test_unknown_views_rejected_where_required(self):
        self.assertFalse(qualifies("tiktok", self.item(views=None), TH))

    def test_instagram_unknown_duration_allowed(self):
        self.assertTrue(qualifies("instagram", {"duration": None, "views": None, "likes": 5}, TH))


class TopicBarTests(unittest.TestCase):
    def test_a_topic_tab_may_carry_older_videos(self):
        now = 1_790_000_000
        thresholds = {"max_age_days": 7, "max_duration": 180}
        month_old = {"duration": 30, "created": now - 20 * 86400}
        self.assertFalse(qualifies("douyin", month_old, thresholds, now=now))
        self.assertTrue(qualifies("douyin", month_old, thresholds, now=now, topic_stream=True))
        self.assertFalse(qualifies("douyin", dict(month_old, created=now - 40 * 86400), thresholds, now=now, topic_stream=True))

    def test_a_topic_tab_uses_a_lower_engagement_bar_than_the_general_feed(self):
        thresholds = {"min_likes": {"douyin": 150_000}, "max_duration": 180}
        item = {"likes": 30_000, "duration": 40, "created": None}
        self.assertFalse(qualifies("douyin", item, thresholds))
        self.assertTrue(qualifies("douyin", item, thresholds, topic_stream=True))
        self.assertFalse(qualifies("douyin", dict(item, likes=5_000), thresholds, topic_stream=True))  # still not a nobody
        self.assertFalse(
            qualifies("douyin", dict(item, duration=300), thresholds, topic_stream=True)
        )  # length and freshness stay as they were
        views = {"min_views": {"kuaishou": 1_000_000}, "max_duration": 180}
        self.assertTrue(qualifies("kuaishou", {"views": 200_000, "duration": 30}, views, topic_stream=True))
        self.assertFalse(qualifies("kuaishou", {"views": 100_000, "duration": 30}, views, topic_stream=True))


class ScoringTests(unittest.TestCase):
    def test_fresh_beats_stale_and_weight_applies(self):
        now = time.time()
        fresh = {"views": 2_000_000, "created": now - 10 * 3600}
        stale = {"views": 2_000_000, "created": now - 100 * 3600}
        self.assertGreater(score("tiktok", fresh, None, now), 2 * score("tiktok", stale, None, now))
        self.assertGreater(score("tiktok", fresh, {"tiktok": 1.5}, now), score("tiktok", fresh, {"tiktok": 1.0}, now))

    def test_age_gate(self):
        now = time.time()
        th = {"max_age_days": 7, "min_views": {"tiktok": 1}}
        self.assertTrue(qualifies("tiktok", {"views": 5, "duration": 20, "created": now - 3 * 86400}, th, now))
        self.assertFalse(qualifies("tiktok", {"views": 5, "duration": 20, "created": now - 9 * 86400}, th, now))
        self.assertTrue(qualifies("tiktok", {"views": 5, "duration": 20, "created": None}, th, now))  # unknown age is not held against it

    def test_parsers_carry_creation_time(self):
        d = douyin.parse_douyin(
            {
                "aweme_list": [
                    {
                        "aweme_id": "1",
                        "aweme_type": 0,
                        "create_time": 1700000000,
                        "duration": 5000,
                        "statistics": {"digg_count": 1},
                        "video": {"play_addr": {"url_list": ["https://a.zjcdn.com/x"]}},
                    }
                ]
            }
        )
        self.assertEqual(d[0]["created"], 1700000000)
        k = kuaishou.parse_kuaishou(
            {
                "data": {
                    "brilliantTypeData": {
                        "feeds": [{"photo": {"id": "abc", "photoUrl": "https://x", "timestamp": 1700000000123, "duration": 5000}}]
                    }
                }
            }
        )
        self.assertEqual(k[0]["created"], 1700000000)


if __name__ == "__main__":
    unittest.main()
