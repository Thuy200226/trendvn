"""Extra source search never substitutes a suggested feed for the requested keywords."""

import unittest
from types import SimpleNamespace
from trendvn_agent.search_extra import _query_matches, instagram_items, kuaishou_items


class ExtraSourceTests(unittest.TestCase):
    def test_exact_query_must_belong_to_network_request(self):
        def response(url, body=None):
            return SimpleNamespace(url=url, request=SimpleNamespace(post_data=body))

        self.assertTrue(_query_matches(response("https://www.instagram.com/api/v1/search/?q=ACE68"), "ACE68"))
        self.assertFalse(_query_matches(response("https://www.instagram.com/api/v1/feed/timeline/"), "ACE68"))
        self.assertFalse(_query_matches(response("https://www.instagram.com/api/v1/search/?q=ACE60"), "ACE68"))
        self.assertTrue(_query_matches(response("https://www.instagram.com/graphql", 'variables={"query":"ACE68"}'), "ACE68"))

    def test_only_actual_videos_are_candidates(self):
        media = {
            "media_type": 2,
            "code": "ABC_def123",
            "caption": {"text": "ACE68"},
            "video_versions": [{"url": "https://cdninstagram.com/video.mp4"}],
        }
        self.assertEqual(instagram_items({"items": [media]})[0]["source_id"], "ABC_def123")
        self.assertEqual(instagram_items({"items": [media | {"media_type": 1}]}), [])
        self.assertEqual(kuaishou_items({"data": {"recommendFeed": {"feeds": []}}}), [])
