"""Matching a title against the product the owner described: exclusions are firm, agreement is only ever a candidate."""

import unittest

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.domain.product_match import match_identity, tokens


class ExclusionTests(unittest.TestCase):
    def test_a_different_model_brand_variant_or_edition_is_excluded_however_much_else_overlaps(self):
        cases = [
            ("Samsung Galaxy S24", "Samsung Galaxy S23", {"model": "S24"}),
            ("Samsung Galaxy S24", "Samsung Galaxy S24 Ultra", {"model": "S24"}),
            ("Apple Watch 9", "Samsung Watch 9", {"brand": "Apple"}),
            ("Phone red", "Phone blue", {"variant": "red"}),
            ("Bàn phím MCHOSE ACE68", "Bàn phím MCHOSE ACE68 Air", {"brand": "MCHOSE", "model": "ACE68"}),
            ("Router X5 v1", "Router X5 v2", {"model": "X5"}),
        ]
        for name, title, extra in cases:
            self.assertEqual(match_identity(dict(name=name, **extra), title)["level"], "different", (name, title))

    def test_the_same_product_id_is_exact_and_a_different_one_excludes_whatever_the_title_says(self):
        self.assertEqual(match_identity({"product_id": "123456"}, "new title", "123456")["level"], "id")
        self.assertEqual(match_identity({"product_id": "123456"}, "same title", "654321")["level"], "different")

    def test_agreement_on_brand_and_model_is_a_candidate_with_its_evidence_listed(self):
        found = match_identity({"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68"}, "迈从ACE68磁轴键盘体验")
        self.assertEqual(found["level"], "candidate")
        facets = {e["facet"]: e["state"] for e in found["evidence"]}
        self.assertEqual(facets, {"Thương hiệu": "ok", "Model": "ok"})

    def test_a_failed_facet_is_listed_as_different_so_the_card_can_say_which_one(self):
        found = match_identity({"name": "Apple Watch 9", "brand": "Apple"}, "Samsung Watch 9")
        self.assertEqual(
            (found["level"], found["evidence"][0]), ("different", {"facet": "Thương hiệu", "state": "different", "value": "Apple"})
        )

    def test_a_variant_a_model_read_from_a_picture_is_noted_but_never_excludes_a_video(self):
        identity = {"name": "MCHOSE ACE68 Magnetic Gaming Keyboard", "brand": "MCHOSE", "model": "ACE68", "variant": "Magnetic"}
        title = "MCHOSE ACE68 review sau 1 tháng"
        self.assertEqual(match_identity(identity, title)["level"], "different")  # said by the owner: it must be there
        soft = match_identity(dict(identity, variant_soft=True), title)
        self.assertEqual(soft["level"], "candidate")
        self.assertIn({"facet": "Biến thể", "state": "unverified", "value": "Magnetic"}, soft["evidence"])
        other = match_identity(dict(identity, variant_soft=True), "MCHOSE ACE68 Air review")
        self.assertEqual(other["level"], "different")  # a different model line is still a different product

    def test_nothing_to_compare_is_unverified_not_a_match(self):
        self.assertEqual(match_identity({}, "anything")["level"], "unverified")


class ReviewFindingsTests(unittest.TestCase):
    """Cases an independent review found wrong: what must stay a candidate, and what must be a different product."""

    def level(self, identity, title):
        return match_identity(identity, title)["level"]

    def test_a_title_that_leaves_the_brand_out_is_still_a_candidate_unless_it_names_another_brand(self):
        identity = {"name": "Samsung Galaxy Buds2 Pro", "brand": "Samsung", "model": "Buds2 Pro"}
        self.assertEqual(self.level(identity, "Galaxy Buds2 Pro review"), "candidate")
        self.assertEqual(self.level(identity, "Xiaomi Buds2 Pro review"), "different")
        self.assertEqual(self.level({"name": "Apple Watch 9", "brand": "Apple"}, "Samsung Watch 9"), "different")

    def test_a_specification_in_the_request_is_not_a_model_code_the_title_must_repeat(self):
        identity = {"name": "iPhone 15 256GB", "model": "IPHONE 15"}
        self.assertEqual(self.level(identity, "iPhone 15 chính hãng"), "candidate")
        self.assertEqual(self.level(identity, "iPhone 14 chính hãng"), "different")
        self.assertEqual(self.level({"name": "Redmi Note 12 5G 128GB"}, "Redmi Note 12 unboxing"), "candidate")
        self.assertEqual(self.level({"name": "Redmi Note 12 5G 128GB"}, "Redmi Note 11 unboxing"), "different")

    def test_a_variant_word_the_owner_asked_for_must_be_in_the_title(self):
        self.assertEqual(self.level({"name": "Galaxy S24 Ultra", "model": "S24"}, "Samsung Galaxy S24 review"), "different")
        self.assertEqual(self.level({"name": "iPhone 15 Pro Max"}, "iPhone 15 Pro review"), "different")
        self.assertEqual(self.level({"name": "Galaxy S24 Ultra", "model": "S24"}, "Galaxy S24 Ultra review"), "candidate")

    def test_a_plus_sign_is_the_plus_variant(self):
        self.assertEqual(self.level({"name": "Galaxy S24", "model": "S24"}, "Galaxy S24+ review"), "different")
        self.assertEqual(self.level({"name": "Galaxy S24+", "model": "S24"}, "Galaxy S24 Plus review"), "candidate")

    def test_fullwidth_letters_and_digits_are_read_as_plain_ones(self):
        self.assertEqual(
            self.level({"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68"}, "ＭＣＨＯＳＥ ＡＣＥ６８ 键盘"), "candidate"
        )

    def test_a_page_title_is_never_turned_into_a_model_code_but_other_variants_still_exclude(self):
        from trendvn_worker.search.identify import from_page

        page = from_page("Bàn phím cơ MCHOSE ACE68 Air 8000Hz 3 mode kết nối chính hãng 2024", "1729384756102938475")
        self.assertTrue(page["soft"])
        for title in ("MCHOSE ACE68 Air bàn phím", "迈从ACE68 Air 键盘", "Review MCHOSE ACE68 Air sau 1 tháng"):
            self.assertEqual(self.level(page, title), "candidate", title)
        self.assertEqual(self.level(page, "MCHOSE ACE68 Pro bàn phím"), "different")
        self.assertEqual(self.level(page, "Keychron K2 bàn phím"), "different")  # not the brand of the page
        sony = from_page("Tai nghe Sony WH-1000XM4 chống ồn chính hãng pin 30 giờ", "1729384756102938476")
        self.assertEqual(self.level(sony, "Sony WH-1000XM4 review"), "candidate")


class TokenTests(unittest.TestCase):
    def test_accents_case_chinese_runs_and_model_boundaries_are_normalised(self):
        self.assertEqual(tokens("Bàn Phím ĐẸP"), {"ban", "phim", "dep"})
        self.assertIn("ace", tokens("ACE68"))
        self.assertIn("68", tokens("ACE68"))
        self.assertIn("mchose", tokens("迈从 ACE68"))


if __name__ == "__main__":
    unittest.main()
