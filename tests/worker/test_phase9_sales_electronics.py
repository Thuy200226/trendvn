"""Verification of commercial video discovery and precise matching for electronics & accessories."""

from trendvn_worker.domain import discovery
from trendvn_worker.domain.product_match import commercial_intent, is_old_product, match_identity
from trendvn_worker.domain.search_queries import explicit, query_plan
from tests.support import StoreCase


class Phase9SalesElectronicsTests(StoreCase):
    def test_run1_general_electronics_discovery_query(self):
        """Run 1: General discovery for sales videos in electronics & accessories."""
        chosen = discovery.options({"category": "electronics", "sales": True, "source": "douyin"})
        identity = {"name": "", "query": ""}
        queries = discovery.queries(identity, chosen)
        douyin_query = queries["douyin"]
        self.assertIn("数码配件", douyin_query)
        self.assertIn("测评 开箱", douyin_query)

    def test_run2_explicit_model_sales_query_and_matching(self):
        """Run 2: Explicit product model retains identifiers and ranks as commercial candidate."""
        identity = explicit("bàn phím mchose ace68")
        identity["queries"] = query_plan(identity)
        chosen = discovery.options({"category": "electronics", "sales": True, "source": "douyin"})
        queries = discovery.queries(identity, chosen)
        douyin_query = queries["douyin"]
        self.assertIn("ace68", douyin_query.casefold())
        self.assertIn("测评 开箱", douyin_query)

        # Match video with commercial unboxing & magnetic switch desk setup
        title_zh = "迈从 ACE68 磁轴键盘 沉浸式开箱体验 桌搭好物分享"
        match = match_identity(identity, title_zh)
        self.assertEqual(match["level"], "candidate")
        self.assertTrue(match["commercial"])
        self.assertGreaterEqual(match["commercial_score"], 70)
        self.assertFalse(match["is_old"])

    def test_run3_anc_bluetooth_headphones_features(self):
        """Run 3: Audio accessories with ANC and Bluetooth extracted accurately."""
        identity = explicit("tai nghe bluetooth chống ồn")
        self.assertEqual(identity["category"], "headphones")
        self.assertIn("降噪", identity["features_zh"])
        self.assertIn("蓝牙", identity["features_zh"])

        title = "旗舰降噪 蓝牙耳机 深度体验 测评 开箱"
        is_comm, score = commercial_intent(title)
        self.assertTrue(is_comm)
        self.assertGreaterEqual(score, 70)

    def test_run4_powerbank_and_gan_charger_negative_exclusion(self):
        """Run 4: Fast charger / GaN accessories exclude second-hand and repairs."""
        identity = explicit("củ sạc nhanh 65W GaN")
        self.assertEqual(identity["category"], "charger")
        self.assertIn("快充", identity["features_zh"])
        self.assertIn("氮化镓", identity["features_zh"])

        # Second-hand or repaired titles must be excluded
        old_title = "65W 氮化镓 快充 二手 拆机 维修 垃圾佬捡漏"
        self.assertTrue(is_old_product(old_title))
        old_match = match_identity(identity, old_title)
        self.assertEqual(old_match["level"], "different")
        self.assertTrue(old_match["is_old"])

        # Brand-new review must pass with commercial intent
        new_title = "65W 氮化镓 快充 硬核测评 闭眼入 首发开箱"
        new_match = match_identity(identity, new_title)
        self.assertFalse(new_match["is_old"])
        self.assertTrue(new_match["commercial"])

    def test_run5_cross_industry_conflict_rejection(self):
        """Run 5: Strict topic precision rejects fashion/cosmetics when looking for electronics."""
        identity = explicit("bàn phím cơ")
        identity["category"] = "electronics"
        fashion_title = "爆款法式复古连衣裙 夏季显瘦穿搭"
        match = match_identity(identity, fashion_title)
        self.assertEqual(match["level"], "different")
        self.assertIn("ngành hàng", match["reason"])
