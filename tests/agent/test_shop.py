"""Official signature vector, creator catalogue eligibility and no-repeat publishing boundaries; offline only."""

import hashlib
from pathlib import Path
from unittest import mock

from tests.support import StoreCase
from trendvn_agent.shop.catalog import context, product_row, showcase_products
from trendvn_agent.shop.client import sign
from trendvn_agent.shop.post import publish


def raw_product():
    return {
        "id": "123456789",
        "title": "Samsung Galaxy S24",
        "commission": {"rate": 3000},
        "detail_link": "https://shop.tiktok.com/view/product/999999999",
        "has_inventory": True,
        "status": {"inventory_status": "IN_STOCK", "review_status": "APPROVED", "is_hidden": False, "added_status": "ADDED"},
    }


class ShopTests(StoreCase):
    def test_official_signature_vector(self):
        result = sign("e59af819cc", "/authorization/202309/shops", {"app_key": "29a39d", "timestamp": 1623812664})
        self.assertEqual(result, "b596b73e0cc6de07ac26f036364178ab16b0a907af13d43f0a0cd2345f582dc8")

    def test_exact_body_matters_and_multipart_is_excluded(self):
        self.assertNotEqual(sign("secret", "/p", {}, b"{}"), sign("secret", "/p", {}, b"{ }"))
        self.assertEqual(sign("secret", "/p", {}, b"a", True), sign("secret", "/p", {}, b"b", True))
        self.assertEqual(sign("secret", "/p", {"a": 1}), sign("secret", "/p", {"a": 1, "sign": "x", "access_token": "y"}))

    def test_product_id_is_authoritative_and_marketplace_cannot_attach(self):
        row = product_row(raw_product(), True)
        self.assertEqual(row["url"], "https://shop.tiktok.com/view/product/123456789")
        self.assertEqual(row["commission"], "30%")
        self.assertTrue(row["can_attach"])
        self.assertFalse(product_row(raw_product())["can_attach"])
        for key, value in (
            ("inventory_status", "OUT_OF_STOCK"),
            ("review_status", "REJECTED"),
            ("is_hidden", True),
            ("added_status", "REMOVED"),
        ):
            raw = raw_product()
            raw["status"][key] = value
            self.assertIsNone(product_row(raw, True))
        raw = raw_product()
        raw["commission"]["rate"] = True
        self.assertIsNone(product_row(raw, True))

    def test_creator_permissions_are_not_inferred_from_login(self):
        client = mock.Mock()
        client.profile.return_value = {"permissions": []}
        with (
            mock.patch("trendvn_agent.shop.catalog.worker_get", return_value={"accounts": [{"id": "main", "username": "a"}]}),
            mock.patch("trendvn_agent.shop.catalog.Client", return_value=client),
            self.assertRaises(ValueError),
        ):
            context("main")

    def test_showcase_reads_all_pages_and_refuses_repeated_token(self):
        client = mock.Mock()
        client.request.side_effect = [{"products": [raw_product()], "next_page_token": "next"}, {"products": []}]
        self.assertEqual(len(showcase_products(client)), 1)
        self.assertEqual(client.request.call_args.args[1]["page_token"], "next")
        client.request.side_effect = [{"products": [], "next_page_token": "next"}] * 2
        with self.assertRaises(ValueError):
            showcase_products(client)

    def publish_case(self, dry_run, failure=None, bad_md5=False):
        video = Path(self.tmp.name) / "test.mp4"
        video.write_bytes(b"video")
        client = mock.Mock()

        def request(path, *args, **kwargs):
            if path.endswith("video_files"):
                return {"video_file": {"id": "file_1", "md5": "bad" if bad_md5 else hashlib.md5(b"video").hexdigest()}}
            if path.endswith("/videos"):
                if failure:
                    raise ValueError("connection lost")
                return {"video": {"id": "123456789"}}
            return {"video": {"post_status": "SUCCESS"}}

        client.request.side_effect = request
        job = {
            "account": "main",
            "target": "a",
            "product": {"product_id": "123456789"},
            "caption": "Product #a #b #c",
            "visibility": "public",
        }
        state = {"clicked": False}
        with (
            mock.patch("trendvn_agent.shop.post.context", return_value=({"username": "a"}, client, {})),
            mock.patch("trendvn_agent.shop.post.showcase_products", return_value=[product_row(raw_product(), True)]),
        ):
            outcome = publish(job, video, dry_run, state)
        return outcome, client, state

    def test_dry_run_checks_md5_but_never_submits_post(self):
        outcome, client, state = self.publish_case(True)
        self.assertEqual(outcome[0], "dry_run")
        self.assertFalse(state["clicked"])
        self.assertEqual([call.args[0] for call in client.request.call_args_list], ["/affiliate_creator/202505/videos/video_files"])

    def test_bad_md5_defers_without_post(self):
        outcome, client, state = self.publish_case(False, bad_md5=True)
        self.assertEqual(outcome[0], "deferred")
        self.assertFalse(state["clicked"])
        self.assertEqual(client.request.call_count, 1)

    def test_lost_publish_response_is_unknown_and_never_retried(self):
        outcome, client, state = self.publish_case(False, failure=True)
        self.assertEqual(outcome[0], "unknown")
        self.assertTrue(state["clicked"])
        self.assertEqual(client.request.call_count, 2)

    def test_expired_token_defers_without_counting_video_failure(self):
        with mock.patch("trendvn_agent.shop.post.context", side_effect=ValueError("expired")):
            self.assertEqual(publish({"account": "main"}, Path("unused"), False, {"clicked": False})[0], "deferred")

    def test_changed_account_after_claim_never_uploads_or_posts(self):
        client = mock.Mock()
        with mock.patch("trendvn_agent.shop.post.context", return_value=({"username": "new_creator"}, client, {})):
            outcome = publish({"account": "main", "target": "old_creator"}, Path("unused"), False, {"clicked": False})
        self.assertEqual(outcome[0], "deferred")
        client.request.assert_not_called()

    def test_large_video_is_parked_before_any_upload(self):
        from trendvn_agent.shop.post import _upload, UPLOAD_LIMIT

        client = mock.Mock()
        path = Path(self.tmp.name) / "large.mp4"
        with path.open("wb") as handle:
            handle.truncate(UPLOAD_LIMIT + 1)
        with self.assertRaises(ValueError):
            _upload(client, path)
        client.request.assert_not_called()

    def test_malformed_api_code_does_not_echo_token(self):
        import json
        from trendvn_agent.shop.client import Client

        client = Client.__new__(Client)
        client.credentials = {"app_key": "fake-key", "app_secret": "fake-secret", "access_token": "fake-token"}
        response = mock.Mock(status=200)
        response.read.return_value = json.dumps({"code": "fake-token", "data": {}}).encode()
        conn = mock.Mock()
        conn.getresponse.return_value = response
        with mock.patch("trendvn_agent.shop.client.http.client.HTTPSConnection", return_value=conn), self.assertRaises(ValueError) as error:
            client.request("/affiliate_creator/202508/profiles")
        self.assertNotIn("fake-token", str(error.exception))
