"""What a TikTok or Douyin link points at, from its text alone (no network): the one place that knows these shapes."""

import unittest

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.product_links import attribution, classify, from_text, product_link


class ClassifyTests(unittest.TestCase):
    def test_a_product_page_gives_its_exact_id_whichever_host_and_shape_it_uses(self):
        for url in (
            "https://www.tiktok.com/view/product/1729384756102938475",
            "https://shop.tiktok.com/view/product/1729384756102938475?region=VN&locale=vi-VN",
            "https://shop-vn.tiktok.com/view/product/1729384756102938475/",
            "https://www.tiktok.com/shop/pdp/ban-phim-mchose-ace68/1729384756102938475",
            "https://www.tiktok.com/shop/pdp/1729384756102938475",
            "https://affiliate.tiktok.com/product/1729384756102938475?shop_region=VN",
            "https://www.tiktok.com/anything?product_id=1729384756102938475",
        ):
            link = classify(url)
            self.assertEqual((link["kind"], link["product_id"]), ("product", "1729384756102938475"), url)

    def test_videos_of_both_platforms_give_their_ids_and_the_query_string_is_dropped(self):
        link = classify("https://www.tiktok.com/@shop.abc/video/7290000000000000001?is_from_webapp=1&sender_device=pc")
        self.assertEqual((link["kind"], link["platform"], link["video_id"]), ("video", "tiktok", "7290000000000000001"))
        self.assertEqual(link["canonical"], "https://www.tiktok.com/@shop.abc/video/7290000000000000001")
        link = classify("https://www.douyin.com/video/7290000000000000002?previous_page=app_code_link")
        self.assertEqual((link["kind"], link["platform"], link["video_id"]), ("video", "douyin", "7290000000000000002"))

    def test_short_links_are_marked_for_resolution_and_nothing_is_guessed_from_them(self):
        for url in ("https://vt.tiktok.com/ZSabc123/", "https://vm.tiktok.com/ZMabc123/", "https://www.tiktok.com/t/ZTabc123/"):
            link = classify(url)
            self.assertEqual((link["kind"], link["product_id"]), ("short", None), url)

    def test_other_tiktok_pages_and_foreign_hosts_are_not_product_or_video_links(self):
        self.assertEqual(classify("https://www.tiktok.com/@someone")["kind"], "tiktok")
        for url in (
            "https://evil.example/view/product/1729384756102938475",
            "https://tiktok.com.evil.example/view/product/1729384756102938475",
        ):
            link = classify(url)
            self.assertEqual((link["kind"], link["product_id"]), ("other", None), url)

    def test_text_that_is_not_a_clean_https_link_is_refused(self):
        for url in (
            "http://www.tiktok.com/view/product/1729384756102938475",
            "https://user:pw@www.tiktok.com/view/product/1729384756102938475",
            "https://www.tiktok.com:8443/view/product/1729384756102938475",
            "javascript:alert(1)",
            "",
            None,
            7,
            "https://x/ y",
        ):
            self.assertIsNone(classify(url), url)

    def test_a_short_product_id_or_a_lookalike_path_is_not_an_id(self):
        self.assertIsNone(classify("https://www.tiktok.com/view/product/123")["product_id"])
        self.assertIsNone(classify("https://www.tiktok.com/view/product/abc1234567")["product_id"])
        self.assertIsNone(classify("https://www.tiktok.com/video/1729384756102938475")["product_id"])


class FromTextTests(unittest.TestCase):
    def test_links_are_found_in_prose_in_order_and_cut_at_the_punctuation_that_ends_a_sentence(self):
        text = "Xem https://www.tiktok.com/view/product/1729384756102938475). Và https://vt.tiktok.com/ZSabc123/, cảm ơn"
        self.assertEqual(
            [link["url"] for link in from_text(text)],
            ["https://www.tiktok.com/view/product/1729384756102938475", "https://vt.tiktok.com/ZSabc123/"],
        )

    def test_at_most_three_distinct_links_are_returned(self):
        text = " ".join("https://www.tiktok.com/view/product/17293847561029384%02d" % n for n in range(8))
        self.assertEqual(len(from_text(text)), 3)
        self.assertEqual(len(from_text("https://vt.tiktok.com/ZSa/ https://vt.tiktok.com/ZSa/")), 1)


class AttributionTests(unittest.TestCase):
    def test_a_plain_product_link_carries_nothing_that_ties_it_to_a_creator(self):
        found = attribution("https://www.tiktok.com/view/product/1729384756102938475?region=VN&locale=vi-VN")
        self.assertEqual(found["markers"], {})
        self.assertFalse(found["tracked"])

    def test_creator_and_share_parameters_are_reported_by_name_and_value(self):
        found = attribution(
            "https://www.tiktok.com/view/product/1729384756102938475?share_creator_id=7000000000000000001&sec_user_id=MS4w&utm_source=copy&region=VN"
        )
        self.assertEqual(found["markers"]["share_creator_id"], "7000000000000000001")
        self.assertIn("sec_user_id", found["markers"])
        self.assertTrue(found["tracked"])
        self.assertNotIn("region", found["markers"])

    def test_repeated_and_oversized_values_are_cut_not_trusted(self):
        found = attribution("https://www.tiktok.com/view/product/1729384756102938475?creator_id=" + "9" * 500)
        self.assertLessEqual(len(found["markers"]["creator_id"]), 80)


class HardeningTests(unittest.TestCase):
    PID = "1729384756102938475"

    def test_a_video_address_is_a_video_whatever_its_query_says(self):
        link = classify("https://www.tiktok.com/@creator/video/7234567890123456789?product_id=" + self.PID)
        self.assertEqual((link["kind"], link["product_id"]), ("video", None))

    def test_an_address_that_names_two_different_products_is_no_product(self):
        link = classify("https://www.tiktok.com/view/product/%s?product_id=9999999999" % self.PID)
        self.assertEqual((link["kind"], link["product_id"], link["conflict"]), ("tiktok", None, True))
        same = classify("https://www.tiktok.com/view/product/%s?product_id=%s" % (self.PID, self.PID))
        self.assertEqual((same["kind"], same["product_id"], same["conflict"]), ("product", self.PID, False))

    def test_video_addresses_come_back_in_one_canonical_form_the_agent_recognises(self):
        for url, canonical in (
            ("https://WWW.TIKTOK.COM/@a/video/1234567890", "https://www.tiktok.com/@a/video/1234567890"),
            ("https://www.tiktok.com:443/@a/video/1234567890/?x=1", "https://www.tiktok.com/@a/video/1234567890"),
            ("https://m.tiktok.com/@a/video/1234567890", "https://www.tiktok.com/@a/video/1234567890"),
            ("https://douyin.com/video/7234567890123456789", "https://www.douyin.com/video/7234567890123456789"),
        ):
            self.assertEqual(classify(url)["canonical"], canonical, url)

    def test_bare_addresses_and_non_ascii_text_are_not_links_to_follow(self):
        for url in (
            "https://127.0.0.1/a",
            "https://[::1]/a",
            "https://[::ffff:7f00:1]/a",
            "https://2130706433/a",
            "https://www.tiktok.com/vi\u1ec7t",
            "https://t\u1ef7.tiktok.com/a",
        ):
            self.assertIsNone(classify(url), url)

    def test_a_mark_is_a_whole_word_of_the_parameter_name_not_a_piece_of_it(self):
        base = "https://www.tiktok.com/view/product/%s?" % self.PID
        for name in ("rug_x", "debug_mode", "partnership", "creators"):
            self.assertFalse(attribution(base + name + "=1")["tracked"], name)
        for name in ("share_creator_id", "creator_id", "sec_user_id", "u_code", "ug_btm", "affiliate_id", "partner"):
            self.assertTrue(attribution(base + name + "=1")["tracked"], name)


class ProductLinkTests(unittest.TestCase):
    def test_the_share_text_of_the_app_gives_its_link_whatever_words_surround_it(self):
        text = "Xem sản phẩm này trên TikTok Shop nhé! https://vt.tiktok.com/ZSabc123/ Cảm ơn"
        self.assertEqual(product_link(text)["url"], "https://vt.tiktok.com/ZSabc123/")

    def test_a_product_page_link_is_one_too_and_a_video_or_a_foreign_page_is_not(self):
        self.assertEqual(product_link("https://www.tiktok.com/view/product/1729384756102938475?x=1")["product_id"], "1729384756102938475")
        self.assertIsNone(product_link("https://www.tiktok.com/@a/video/1234567890"))
        self.assertIsNone(product_link("https://example.com/view/product/1729384756102938475"))
        self.assertIsNone(product_link("bàn phím mchose ace68"))


if __name__ == "__main__":
    unittest.main()
