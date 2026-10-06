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

    def test_nothing_to_compare_is_unverified_not_a_match(self):
        self.assertEqual(match_identity({}, "anything")["level"], "unverified")


class TokenTests(unittest.TestCase):
    def test_accents_case_chinese_runs_and_model_boundaries_are_normalised(self):
        self.assertEqual(tokens("Bàn Phím ĐẸP"), {"ban", "phim", "dep"})
        self.assertIn("ace", tokens("ACE68"))
        self.assertIn("68", tokens("ACE68"))
        self.assertIn("mchose", tokens("迈从 ACE68"))


if __name__ == "__main__":
    unittest.main()
