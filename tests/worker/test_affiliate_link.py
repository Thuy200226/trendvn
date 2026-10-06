"""Is a pasted share link the exact product the owner is working on? Judged from the link and its page only, never from an account API."""

import unittest
from unittest import mock

from tests.support import TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker.search import affiliate

PID = "1729384756102938475"
SHARE = "https://vt.tiktok.com/ZSabc123/"
LONG = "https://www.tiktok.com/view/product/%s?region=VN&share_creator_id=7000000000000000001&utm_source=copy" % PID


def found(**fields):
    base = {
        "input": SHARE,
        "chain": [SHARE, LONG],
        "final": LONG,
        "product_id": PID,
        "title": "",
        "markers": {"share_creator_id": "7000000000000000001"},
        "tracked": True,
        "stopped": "",
    }
    base.update(fields)
    return base


def states(result):
    return {check["label"]: check["state"] for check in result["checks"]}


class InspectTests(unittest.TestCase):
    def inspect(self, chain, title="", fail_title=False):
        def follow(url, allow=None, hops=6):
            return {"chain": chain, "status": 200, "stopped": ""}

        def page_title(url):
            if fail_title:
                raise ValueError("403")
            return title, url

        return affiliate.inspect(chain[0], follow=follow, page_title=page_title)

    def test_the_product_id_title_and_creator_parameters_are_read_from_the_chain(self):
        result = self.inspect([SHARE, LONG], title="Bàn phím MCHOSE ACE68")
        self.assertEqual((result["product_id"], result["title"], result["tracked"]), (PID, "Bàn phím MCHOSE ACE68", True))
        self.assertEqual(result["markers"], {"share_creator_id": "7000000000000000001"})
        self.assertEqual(result["final"], LONG)

    def test_an_unreadable_page_still_gives_the_id_and_says_it_could_not_read_the_name(self):
        result = self.inspect([SHARE, LONG], fail_title=True)
        self.assertEqual((result["product_id"], result["title"]), (PID, ""))

    def test_a_link_that_leaves_tiktok_is_not_followed_further_and_gives_no_product(self):
        def follow(url, allow=None, hops=6):
            return {"chain": [SHARE, "https://evil.example/x"], "status": 302, "stopped": "evil.example"}

        result = affiliate.inspect(SHARE, follow=follow, page_title=mock.Mock(side_effect=AssertionError("must not fetch a foreign page")))
        self.assertIsNone(result["product_id"])
        self.assertEqual(result["stopped"], "evil.example")

    def test_a_login_wall_title_is_not_taken_for_a_product_name(self):
        result = self.inspect([SHARE, LONG], title="TikTok - Make Your Day")
        self.assertEqual((result["product_id"], result["title"]), (PID, ""))

    def test_the_id_is_taken_from_the_first_hop_that_names_one(self):
        result = self.inspect(["https://www.tiktok.com/view/product/%s" % PID, "https://www.tiktok.com/view/product/9999999999"])
        self.assertEqual(result["product_id"], PID)

    def test_text_that_is_not_a_tiktok_link_is_refused_at_once(self):
        for url in ("https://example.com/view/product/%s" % PID, "http://vt.tiktok.com/a", "not a link"):
            with self.assertRaises(ValueError, msg=url):
                affiliate.inspect(url, follow=mock.Mock(), page_title=mock.Mock())


class VerdictTests(unittest.TestCase):
    def test_the_same_product_id_as_the_owner_gave_is_exact(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[{"share_creator_id": "7000000000000000001"}])
        self.assertEqual((result["verdict"], result["kind"], result["needs_confirmation"]), ("exact", "affiliate", False))

    def test_another_product_id_than_the_owner_gave_is_different_and_never_confirmed(self):
        result = affiliate.verdict({"product_id": "1111111111"}, found(), known=[])
        self.assertEqual(result["verdict"], "different")
        self.assertEqual(states(result)["Mã sản phẩm"], "bad")

    def test_a_title_that_matches_brand_and_model_is_likely_and_needs_the_owner_to_look(self):
        identity = {"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68"}
        result = affiliate.verdict(
            identity, found(title="Bàn phím cơ MCHOSE ACE68 Magnetic"), known=[{"share_creator_id": "7000000000000000001"}]
        )
        self.assertEqual((result["verdict"], result["needs_confirmation"]), ("likely", True))

    def test_a_title_of_another_model_is_different(self):
        identity = {"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68"}
        result = affiliate.verdict(identity, found(title="Bàn phím MCHOSE ACE68 Air"), known=[])
        self.assertEqual(result["verdict"], "different")

    def test_no_readable_title_and_no_id_to_compare_is_unknown_and_needs_the_owner(self):
        result = affiliate.verdict({"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68"}, found(title=""), known=[])
        self.assertEqual((result["verdict"], result["needs_confirmation"]), ("unknown", True))

    def test_with_no_product_in_the_chat_the_link_itself_is_the_product_and_nothing_is_compared(self):
        result = affiliate.verdict({}, found(title="Bàn phím MCHOSE"), known=[{"share_creator_id": "7000000000000000001"}])
        self.assertEqual((result["verdict"], result["needs_confirmation"]), ("found", False))
        first = affiliate.verdict({}, found(title="Bàn phím MCHOSE"), known=[])
        self.assertEqual((first["verdict"], first["needs_confirmation"]), ("found", True))

    def test_a_link_without_a_product_id_is_invalid_and_says_nothing_about_creators(self):
        result = affiliate.verdict({"product_id": PID}, found(product_id=None, title=""), known=[])
        self.assertEqual((result["verdict"], result["needs_confirmation"]), ("invalid", False))
        self.assertEqual([c["label"] for c in result["checks"]], ["Mã sản phẩm"])

    def test_a_plain_product_link_is_flagged_as_not_a_commission_link(self):
        result = affiliate.verdict({"product_id": PID}, found(markers={}, tracked=False), known=[])
        self.assertEqual(result["kind"], "plain")
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(states(result)["Dấu hiệu nhà sáng tạo"], "warn")

    def test_the_first_link_of_an_account_sets_the_mark_and_asks_the_owner_once(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[])
        self.assertTrue(result["needs_confirmation"])
        self.assertIn("mốc", " ".join(c["detail"] for c in result["checks"]))

    def test_a_creator_code_that_differs_from_the_links_already_confirmed_is_warned_about(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[{"share_creator_id": "7999999999999999999"}])
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(states(result)["Mã nhà sáng tạo"], "warn")

    def test_a_creator_code_that_matches_is_marked_ok(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[{"share_creator_id": "7000000000000000001"}])
        self.assertEqual(states(result)["Mã nhà sáng tạo"], "ok")


if __name__ == "__main__":
    unittest.main()
