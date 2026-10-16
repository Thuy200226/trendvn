"""Studio rows with similar names or an existing unrelated link cannot prove the requested Shop ID."""

from unittest import TestCase, mock
from trendvn_agent.publisher.product_anchor import exact_row, validate_proof


class AnchorTests(TestCase):
    def row(self, pid):
        row = mock.Mock()
        row.is_visible.return_value = True
        row.get_attribute.side_effect = lambda key: pid if key == "data-product-id" else None
        row.locator.return_value.evaluate_all.return_value = []
        row.inner_text.return_value = "Obagi Clenziderm"
        return row

    def test_first_row_mismatch_and_duplicate_ids_are_never_selected(self):
        pid = "1731815189062584653"
        wrong, right = self.row("1731815189062584654"), self.row(pid)
        modal = mock.Mock()
        rows = modal.locator.return_value
        rows.count.return_value = 2
        rows.nth.side_effect = lambda i: [wrong, right][i]
        self.assertIs(exact_row(modal, pid), right)
        rows.nth.side_effect = lambda i: [right, self.row(pid)][i]
        self.assertIsNone(exact_row(modal, pid))

    def test_old_commerce_job_cannot_upload_or_publish_without_content_proof(self):
        for pid in ("Windbreaker", "1731815189062584653"):
            with self.assertRaises(ValueError):
                validate_proof({"product_binding": {"product_id": pid}})

    def test_compatibility_slider_hook_does_not_attempt_verification(self):
        from trendvn_agent.search_douyin import try_solve_slider

        page = mock.Mock()
        self.assertFalse(try_solve_slider(page))
        page.assert_not_called()
        self.assertEqual(page.mock_calls, [])

    def test_commerce_intent_survives_missing_binding(self):
        with self.assertRaises(ValueError):
            validate_proof({"commerce_required": True})
        with self.assertRaises(ValueError):
            validate_proof({"product_verification": {"status": "same"}})

    def test_public_post_cart_proof_ignores_another_video_and_anchor_internal_id(self):
        from trendvn_agent.publisher.product_anchor import own_item_product_ids

        pid = "1731815189062584653"
        self.assertEqual(own_item_product_ids({"id": "other", "anchors": [{"product_id": pid}]}, "new"), set())
        self.assertEqual(own_item_product_ids({"id": "new", "anchors": [{"id": pid}]}, "new"), set())
        self.assertEqual(own_item_product_ids({"id": "new", "anchors": [{"product_id": pid}]}, "new"), {pid})

    def test_recommended_products_are_not_the_post_cart(self):
        from trendvn_agent.publisher.product_anchor import own_item_product_ids

        pid = "1731815189062584653"
        self.assertEqual(own_item_product_ids({"id": "new", "commerceInfo": {"recommendedProducts": [{"product_id": pid}]}}, "new"), set())

    def test_visible_douyin_search_waits_for_owner_and_filters_exact_dom_link(self):
        from trendvn_agent import search_douyin as source
        from trendvn_agent.search_capture import Capture

        url = "https://www.douyin.com/video/7234567890123456789"
        page = mock.Mock()
        page.is_closed.return_value = False
        page.url = url
        ctx = mock.Mock()
        ctx.new_page.return_value = page
        states = ["out", "out", "wall", "ok", "ok"]
        current = {"state": "out"}

        def state(_):
            current["state"] = states.pop(0) if len(states) > 1 else states[0]
            return current["state"]

        wanted = {"source_id": "7234567890123456789", "url": url}
        other = {"source_id": "7234567890123456780", "url": "https://www.douyin.com/video/7234567890123456780"}
        capture = Capture((), lambda d: [], [url])
        with (
            mock.patch.object(source, "Session") as observer,
            mock.patch.object(source, "window_ok", return_value=True),
            mock.patch.object(source, "blocked", side_effect=lambda p: current["state"] == "wall"),
            mock.patch.object(source, "report") as report,
            mock.patch.object(source, "navigate"),
            mock.patch.object(source, "resume_query", return_value=lambda p, b: False),
            mock.patch.object(source, "extract_dom_videos", return_value=[other, wanted]) as dom,
        ):
            observer.return_value.state.side_effect = state
            observer.return_value.who = "owner"
            signed, who = source._read_search(
                ctx, url, "Torriden DIVE IN", [url], capture, {"id": "main", "username": "creator"}, False, True
            )
        self.assertTrue(signed)
        self.assertEqual(who, "owner")
        self.assertEqual(set(capture.seen), {wanted["source_id"]})
        self.assertEqual([c.args[2] for c in report.call_args_list], ["out", "wall", "ok"])
        self.assertEqual(dom.call_count, 1)
        self.assertGreaterEqual(page.wait_for_timeout.call_count, 4)

    def test_douyin_dom_requires_exact_query_or_video_page(self):
        from trendvn_agent.search_douyin import requested_page

        expected = "https://www.douyin.com/jingxuan/search/Torriden%20DIVE%20IN"
        page = mock.Mock(url=expected)
        self.assertTrue(requested_page(page, expected))
        for actual in (
            "https://www.douyin.com/jingxuan",
            "https://www.douyin.com/jingxuan/search/Obagi",
            "https://www.douyin.com.evil.test/jingxuan/search/Torriden%20DIVE%20IN",
        ):
            page.url = actual
            self.assertFalse(requested_page(page, expected))
