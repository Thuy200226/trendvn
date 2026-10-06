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
        "kind": "product",
        "status": 200,
    }
    base.update(fields)
    return base


def states(result):
    return {check["label"]: check["state"] for check in result["checks"]}


class InspectTests(unittest.TestCase):
    def inspect(self, chain, title="", fail_title=False):
        def follow(url, allow=None, hops=6):
            return {"chain": chain, "status": 200, "stopped": ""}

        def page_title(url, allow=None):
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

    def test_a_product_page_that_sends_on_to_another_site_still_gives_its_id_and_never_requests_that_site(self):
        def follow(url, allow=None, hops=6):
            return {"chain": [LONG, "https://evil.example/x"], "status": 302, "stopped": "evil.example"}

        fetched = []

        def page_title(url, allow=None):
            fetched.append(url)
            return "Bàn phím", url

        result = affiliate.inspect(LONG, follow=follow, page_title=page_title)
        self.assertEqual((result["product_id"], result["stopped"], result["final"], fetched), (PID, "evil.example", LONG, [LONG]))

    def test_a_link_that_leaves_tiktok_is_not_followed_further_and_gives_no_product(self):
        def follow(url, allow=None, hops=6):
            return {"chain": [SHARE, "https://evil.example/x"], "status": 302, "stopped": "evil.example"}

        result = affiliate.inspect(SHARE, follow=follow, page_title=mock.Mock(side_effect=AssertionError("must not fetch a foreign page")))
        self.assertIsNone(result["product_id"])
        self.assertEqual(result["stopped"], "evil.example")

    def test_a_login_wall_title_is_not_taken_for_a_product_name(self):
        result = self.inspect([SHARE, LONG], title="TikTok - Make Your Day")
        self.assertEqual((result["product_id"], result["title"]), (PID, ""))

    def test_two_different_product_ids_on_the_way_make_it_no_product_at_all(self):
        other = "https://www.tiktok.com/view/product/2222222222222222222?share_creator_id=7000000000000000001"
        result = self.inspect(["https://www.tiktok.com/view/product/" + PID, other], title="Other product")
        self.assertEqual((result["product_id"], result["conflict"]), (None, True))
        self.assertEqual(affiliate.verdict({"product_id": PID}, result, known=[])["verdict"], "invalid")

    def test_one_address_that_names_two_products_is_no_product_either(self):
        result = self.inspect(["https://www.tiktok.com/view/product/%s?product_id=9999999999" % PID])
        self.assertEqual((result["product_id"], result["conflict"]), (None, True))

    def test_the_same_id_on_every_hop_is_one_product(self):
        result = self.inspect(["https://www.tiktok.com/view/product/" + PID, LONG])
        self.assertEqual((result["product_id"], result["conflict"]), (PID, False))

    def test_the_title_is_fetched_with_only_tiktok_hosts_allowed(self):
        seen = {}

        def page_title(url, allow=None):
            seen["allow"] = allow
            return "Bàn phím", url

        def follow(url, allow=None, hops=6):
            return {"chain": [SHARE, LONG], "status": 200, "stopped": ""}

        affiliate.inspect(SHARE, follow=follow, page_title=page_title)
        self.assertTrue(seen["allow"]("www.tiktok.com"))
        self.assertFalse(seen["allow"]("evil.example"))

    def test_every_kind_of_failure_reading_the_page_leaves_the_id_alone_deciding(self):
        import http.client

        for failure in (ValueError("x"), OSError("y"), http.client.BadStatusLine("z"), http.client.IncompleteRead(b"")):
            with self.subTest(failure=type(failure).__name__):

                def page_title(url, allow=None, failure=failure):
                    raise failure

                def follow(url, allow=None, hops=6):
                    return {"chain": [SHARE, LONG], "status": 200, "stopped": ""}

                result = affiliate.inspect(SHARE, follow=follow, page_title=page_title)
                self.assertEqual((result["product_id"], result["title"]), (PID, ""))

    def test_the_status_of_the_last_page_is_kept_and_a_gone_page_is_not_asked_for_its_title(self):
        asked = []

        def follow(url, allow=None, hops=6):
            return {"chain": [SHARE, LONG], "status": 404, "stopped": ""}

        result = affiliate.inspect(SHARE, follow=follow, page_title=lambda url, allow=None: asked.append(url) or ("t", url))
        self.assertEqual((result["status"], asked), (404, []))
        self.assertEqual(affiliate.verdict({"product_id": PID}, result, known=[])["verdict"], "invalid")

    def test_titles_of_walls_and_errors_are_not_product_names(self):
        for title in (
            "Access Denied",
            "Just a moment...",
            "404 Not Found",
            "TikTok Shop",
            "Attention Required! | Cloudflare",
            "Error",
            "Log in",
        ):
            self.assertEqual(self.inspect([SHARE, LONG], title=title)["title"], "", title)
        self.assertEqual(self.inspect([SHARE, LONG], title="Bàn phím MCHOSE ACE68")["title"], "Bàn phím MCHOSE ACE68")

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

    def test_a_title_that_shares_little_with_a_plain_name_is_unknown_not_likely(self):
        identity = {"name": "Samsung Galaxy Buds Pro Case Black"}
        result = affiliate.verdict(identity, found(title="Galaxy phone"), known=[])
        self.assertEqual(result["verdict"], "unknown")
        self.assertEqual(states(result)["Tên sản phẩm"], "warn")

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
        result = affiliate.verdict({"product_id": PID}, found(markers={}, tracked=False, input=LONG.split("?")[0]), known=[])
        self.assertEqual(result["kind"], "plain")
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(states(result)["Dấu hiệu nhà sáng tạo"], "warn")

    def test_a_short_share_link_with_no_visible_marks_is_not_called_plain_because_its_marks_may_be_on_tiktoks_side(self):
        result = affiliate.verdict({"product_id": PID}, found(markers={}, tracked=False), known=[])
        self.assertEqual((result["kind"], result["needs_confirmation"]), ("short", True))
        self.assertIn("phía TikTok", [c for c in result["checks"] if c["label"] == "Dấu hiệu nhà sáng tạo"][0]["detail"])
        long = found(markers={}, tracked=False, input=LONG.split("?")[0])
        self.assertEqual(affiliate.verdict({"product_id": PID}, long, known=[])["kind"], "plain")

    def test_the_first_link_of_an_account_sets_the_mark_and_asks_the_owner_once(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[])
        self.assertTrue(result["needs_confirmation"])
        self.assertIn("mốc", " ".join(c["detail"] for c in result["checks"]))

    def test_a_creator_code_that_differs_from_the_links_already_confirmed_is_warned_about(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[{"share_creator_id": "7999999999999999999"}])
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(states(result)["Mã nhà sáng tạo"], "warn")

    def test_one_shared_value_among_several_is_not_the_same_sharer(self):
        """A campaign tag two people's links share must not make Bob's link look like Alice's."""
        known = [{"share_creator_id": "ALICE", "ug_btm": "b8727,b0"}]
        bob = found(markers={"share_creator_id": "BOB", "ug_btm": "b8727,b0"})
        result = affiliate.verdict({"product_id": PID}, bob, known=known)
        self.assertEqual((result["verdict"], result["needs_confirmation"]), ("exact", True))
        self.assertEqual(states(result)["Mã nhà sáng tạo"], "warn")
        alice = found(markers={"share_creator_id": "ALICE", "ug_btm": "another,tag"})
        self.assertFalse(affiliate.verdict({"product_id": PID}, alice, known=known)["needs_confirmation"])

    def test_every_sharer_mark_of_a_confirmed_link_must_agree_not_just_one_of_them(self):
        known = [{"share_creator_id": "ALICE", "sec_user_id": "MS4wAlice"}]
        mixed = found(markers={"share_creator_id": "ALICE", "sec_user_id": "MS4wBob"})
        self.assertTrue(affiliate.verdict({"product_id": PID}, mixed, known=known)["needs_confirmation"])
        same = found(markers={"share_creator_id": "ALICE", "sec_user_id": "MS4wAlice"})
        self.assertFalse(affiliate.verdict({"product_id": PID}, same, known=known)["needs_confirmation"])

    def test_a_confirmed_link_with_no_sharer_mark_in_it_proves_nothing_about_the_next_one(self):
        known = [{"ug_btm": "b8727,b0"}]
        result = affiliate.verdict({"product_id": PID}, found(markers={"ug_btm": "b8727,b0", "creator_id": "1"}), known=known)
        self.assertTrue(result["needs_confirmation"])

    def test_a_creator_code_that_matches_is_marked_ok(self):
        result = affiliate.verdict({"product_id": PID}, found(), known=[{"share_creator_id": "7000000000000000001"}])
        self.assertEqual(states(result)["Mã nhà sáng tạo"], "ok")


if __name__ == "__main__":
    unittest.main()
