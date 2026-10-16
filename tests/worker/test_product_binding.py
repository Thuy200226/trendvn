"""No generic token, variant, borrowed catalog or old render may authorize an automatic product cart."""

from unittest import TestCase
from trendvn_worker.domain.product_binding import catalog_binding, strict_title, verify_evidence
from trendvn_worker.ai.product_verify import proof_from_answer

PID = "1731815189062584653"
IDENTITY = {"name": "Obagi Clenziderm 148ml", "brand": "Obagi", "model": "Clenziderm", "variant": "148ml"}
LINK = {"product_id": PID, "url": "https://www.tiktok.com/view/product/" + PID, "title": "Obagi Clenziderm 148ml", "account": "a"}


class ProductBindingTests(TestCase):
    def test_exact_catalog_and_variant_are_required(self):
        good = catalog_binding(IDENTITY, [LINK], "a", "creator")
        self.assertEqual(good["product_id"], PID)
        for title in ("Obagi serum 148ml", "Obagi Clenziderm 200ml", "Obagi Clenziderm 148ml 200ml", "Ốp lưng Obagi Clenziderm 148ml"):
            self.assertIsNone(catalog_binding(IDENTITY, [dict(LINK, title=title)], "a", "creator"))
        self.assertIsNone(catalog_binding(IDENTITY, [dict(LINK, product_id="Clenziderm")], "a", "creator"))
        self.assertIsNone(catalog_binding(IDENTITY, [LINK], "b", "other"))
        self.assertIsNone(
            catalog_binding(
                IDENTITY,
                [LINK, dict(LINK, product_id="1731815189062584654", url="https://www.tiktok.com/view/product/1731815189062584654")],
                "a",
                "creator",
            )
        )

    def test_model_prefix_and_title_only_are_not_exact(self):
        ref = {"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68"}
        for title in (
            "MCHOSE ACE68V2",
            "MCHOSE ACE68 GT",
            "MCHOSE ACE68 Turbo",
            "MCHOSE ACE68 cover",
            "MCHOSE ACE68 SE",
            "MCHOSE ACE75 ACE68",
        ):
            self.assertFalse(strict_title(ref, title), title)
        self.assertTrue(strict_title(ref, "迈从 ACE68 磁轴键盘"))
        self.assertFalse(strict_title({"name": "bàn phím"}, "bàn phím MCHOSE"))

    def test_video_proof_is_pinned_to_bytes_account_product_and_binding(self):
        binding = catalog_binding(IDENTITY, [LINK], "a", "creator")
        answer = {
            "status": "same",
            "brand": "Obagi",
            "model": "Clenziderm",
            "variant": "148ml",
            "evidence": [{"second": 2, "text": "Obagi Clenziderm 148ml"}],
        }
        proof = proof_from_answer(answer, binding, "digest", 10)
        self.assertTrue(verify_evidence(proof, binding, "digest", "a", "creator"))
        for hash_, account, username in (("other", "a", "creator"), ("digest", "b", "creator"), ("digest", "a", "renamed")):
            with self.assertRaises(ValueError):
                verify_evidence(proof, binding, hash_, account, username)
        answer["evidence"] = [{"second": 2, "text": "Obagi"}]
        self.assertEqual(proof_from_answer(answer, binding, "digest", 10)["status"], "unknown")
        answer["evidence"] = [{"second": 100, "text": "Obagi Clenziderm 148ml"}]
        self.assertEqual(proof_from_answer(answer, binding, "digest", 10)["status"], "unknown")

    def test_dimension_edition_and_conflicting_query_ids_are_rejected(self):
        self.assertFalse(strict_title({"name": "Acme X1 10cm", "brand": "Acme", "model": "X1"}, "Acme X1 20cm"))
        link = dict(LINK, url=LINK["url"] + "?product_id=" + PID + "&product_id=1731815189062584654")
        self.assertIsNone(catalog_binding(IDENTITY, [link], "a", "creator"))


from tests.support import StoreCase
import json
from trendvn_worker.search.runner import batch_sales_search


class BindingIntegrationTests(StoreCase):
    def saved(self):
        account = self.s.account("main")
        self.s.commission_save("main", {"input": LINK["url"], "title": LINK["title"], "product_id": PID, "markers": {}, "tracked": False})
        return account

    def test_publish_claim_refuses_legacy_missing_stale_and_altered_proof_before_lease(self):
        account = self.saved()
        binding = catalog_binding(IDENTITY, [dict(LINK, account="main")], "main", account["username"])
        self.job(
            "commerce", "ready", product_binding=json.dumps(binding), output_hash="digest", output_file="/data/jobs/commerce/final.mp4"
        )
        with self.assertRaises(ValueError):
            self.s.publish_claim(job_id="commerce")
        self.assertEqual(self.s.job("commerce")["state"], "ready")
        answer = {
            "status": "same",
            "brand": "Obagi",
            "model": "Clenziderm",
            "variant": "148ml",
            "evidence": [{"second": 1, "text": "Obagi Clenziderm 148ml"}],
        }
        proof = proof_from_answer(answer, binding, "digest", 10)
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET meta=? WHERE id=?", (json.dumps({"product_verification": proof}), "commerce"))
        claim = self.s.publish_claim(job_id="commerce")
        self.assertEqual(claim["status"], "claimed")
        self.assertTrue(claim["commerce_required"])
        self.assertEqual(claim["product_verification"]["product_id"], PID)

    def test_batch_ranks_this_product_and_never_takes_a_different_model_or_rejected_video(self):
        account = self.saved()
        product = dict(IDENTITY, product_id=PID, query_zh="Obagi Clenziderm")
        mid = self.s.chat_add("bot", "batch_search", {"products": [product], "account_username": account["username"]}, account="main")

        def item(sid, title):
            return {
                "source_id": sid,
                "platform": "douyin",
                "url": "https://www.douyin.com/video/" + sid,
                "title": title,
                "likes": 1000,
                "duration": 30,
            }

        old = item("7627431070878744001", "Obagi Clenziderm 148ml")
        self.job("rejected-old", "rejected", platform="douyin", source_id=old["source_id"], url=old["url"])
        wrong = item("7627431070878744002", "Obagi serum 200ml")
        right = item("7627431070878744003", "Obagi Clenziderm 148ml")

        def agent(path, payload, timeout):
            return {"items": [wrong, old, right]} if path == "/api/search" else {"state": "queued"}

        batch_sales_search(self.s, mid, agent)
        created = self.s.chat_get(mid)["body"]["created_jobs"]
        self.assertEqual(len(created), 1)
        chosen = self.s.job(created[0]["job_id"])
        self.assertEqual(chosen["source_id"], right["source_id"])
        self.assertEqual(json.loads(chosen["product_binding"])["product_id"], PID)

    def test_shop_listing_capacity_is_pinned_even_when_request_is_generic(self):
        ref = {"name": "Samsung Galaxy S24", "brand": "Samsung", "model": "S24"}
        link = dict(LINK, title="Samsung Galaxy S24 256GB")
        binding = catalog_binding(ref, [link], "a", "creator")
        answer = {
            "status": "same",
            "brand": "Samsung",
            "model": "S24",
            "variant": "128GB",
            "evidence": [{"second": 1, "text": "Samsung Galaxy S24 128GB"}],
        }
        self.assertEqual(proof_from_answer(answer, binding, "digest", 10)["status"], "unknown")

    def test_final_authorization_rechecks_the_claim_and_current_binding(self):
        account = self.saved()
        binding = catalog_binding(IDENTITY, [dict(LINK, account="main")], "main", account["username"])
        proof = proof_from_answer(
            {
                "status": "same",
                "brand": "Obagi",
                "model": "Clenziderm",
                "variant": "148ml",
                "evidence": [{"second": 1, "text": "Obagi Clenziderm 148ml"}],
            },
            binding,
            "digest",
            10,
        )
        self.job(
            "final-check",
            "ready",
            product_binding=json.dumps(binding),
            meta=json.dumps({"product_verification": proof}),
            output_hash="digest",
            output_file="/data/jobs/final-check/final.mp4",
        )
        claim = self.s.publish_claim(job_id="final-check")
        self.assertEqual(self.s.product_publish_authorize("final-check", claim["lease"], binding, "digest"), {"ok": True})
        with self.s.transaction() as db:
            db.execute("UPDATE jobs SET publish_lease=NULL WHERE id='final-check'")
        with self.assertRaises(ValueError):
            self.s.product_publish_authorize("final-check", claim["lease"], binding, "digest")

    def test_shop_color_is_part_of_content_evidence(self):
        ref = {"name": "Samsung S24", "brand": "Samsung", "model": "S24"}
        binding = catalog_binding(ref, [dict(LINK, title="Samsung S24 màu đỏ")], "a", "creator")
        answer = {
            "status": "same",
            "brand": "Samsung",
            "model": "S24",
            "variant": "black",
            "evidence": [{"second": 1, "text": "Samsung S24 black"}],
        }
        self.assertEqual(proof_from_answer(answer, binding, "digest", 10)["status"], "unknown")

    def test_caption_only_recovery_cannot_confirm_a_commerce_post(self):
        binding = {"product_id": PID, "account": "main", "username": "creator"}
        url = "https://www.tiktok.com/@creator/video/7695350773474921749"
        self.job("unknown-commerce", "publish_unknown", product_binding=json.dumps(binding), publish_url=url, target="creator")
        with self.assertRaises(ValueError):
            self.s.resolve_unknown("unknown-commerce", "published", url)
        self.assertEqual(self.s.job("unknown-commerce")["state"], "publish_unknown")
        self.s.resolve_unknown("unknown-commerce", "published", url, cart_product_id=PID, owner_confirmed=True)
        self.assertEqual(self.s.job("unknown-commerce")["state"], "published")

    def test_commerce_intent_alone_blocks_caption_recovery(self):
        self.job("commerce-without-binding", "publish_unknown", meta=json.dumps({"commerce_required": True}))
        with self.assertRaises(ValueError):
            self.s.resolve_unknown("commerce-without-binding", "published", "https://www.tiktok.com/@creator/video/7695350773474921749")
        entry = next(j for j in self.s.unresolved() if j["id"] == "commerce-without-binding")
        self.assertTrue(entry["commerce_required"])
        self.assertNotIn("meta", entry)

    def test_legacy_sales_intent_and_cross_account_binding_cannot_recover(self):
        url = "https://www.tiktok.com/@creator/video/7695350773474921749"
        self.job("legacy-sales", "publish_unknown", meta=json.dumps({"product_reference": {"sales": True}}), target="creator")
        with self.assertRaises(ValueError):
            self.s.resolve_unknown("legacy-sales", "published", url)
        self.assertTrue(next(j for j in self.s.unresolved() if j["id"] == "legacy-sales")["commerce_required"])
        for account, username in (("pets", "creator"), ("main", "other")):
            binding = {"product_id": PID, "account": account, "username": username}
            self.job("cross-" + account + username, "publish_unknown", product_binding=json.dumps(binding), target="creator")
            with self.assertRaises(ValueError):
                self.s.resolve_unknown("cross-" + account + username, "published", url, cart_product_id=PID)

    def test_sales_text_without_known_brand_model_is_recognized_not_generic_search(self):
        from unittest import mock
        from trendvn_worker.search.identify import identify
        from trendvn_worker.web import chat_forms
        from types import SimpleNamespace

        tasks = mock.Mock()
        app = SimpleNamespace(store=self.s, tasks=tasks)
        chat_forms.send(app, {"account": "main", "source": "douyin", "sales": True, "category": "beauty", "text": "Torriden Dive In 50ml"})
        reference = tasks.start.call_args.args[2]
        self.assertTrue(reference["sales"])
        seen = {
            "name": "Torriden Dive In 50ml",
            "brand": "Torriden",
            "model": "Dive In",
            "variant": "50ml",
            "query": "Torriden Dive In 50ml",
            "query_zh": "Torriden Dive In 50ml 精华",
        }
        with mock.patch("trendvn_worker.search.identify.recognise", return_value=seen) as recognize:
            result = identify(self.s, reference)
        recognize.assert_called_once()
        self.assertEqual(result["brand"], "Torriden")
        self.assertIn("Dive In", result["queries"]["douyin"])
