"""Identifying the product from the owner's words, links, photos and documents: the words win, a model's failure never loses them."""

import json
from unittest import mock

from tests.support import StoreCase
from tests.worker.test_product_search import file
from trendvn_worker.domain.product_match import match_identity
from trendvn_worker.domain.product_search import validate_input
from trendvn_worker.domain.search_queries import explicit, query_plan
from trendvn_worker.search.identify import identify

GEN = "trendvn_worker.search.identify.generate"
LINK_TEXT = "trendvn_worker.search.fetch.link_text"
FOLLOW = "trendvn_worker.search.fetch.follow"


def answer(**fields):
    base = dict(
        name="KZZI K68 Mechanical Keyboard",
        brand="KZZI",
        model="K68",
        variant="White",
        query="KZZI K68",
        query_zh="KZZI K68 键盘",
        uncertainty="",
    )
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(base | fields)}]}}]}


def photo(text=""):
    return validate_input({"text": text, "files": [file("keyboard.png", b"\x89PNG\r\n\x1a\nphoto")]})


class WordsTests(StoreCase):
    def test_a_short_plain_request_needs_no_model(self):
        with mock.patch(GEN) as ai:
            result = identify(self.s, validate_input({"text": "  Xiaomi Smart Band 9  "}))
        self.assertEqual((result["query"], result["brand"]), ("Xiaomi Smart Band 9", "Xiaomi"))
        self.assertEqual(result["links"], [])
        ai.assert_not_called()

    def test_words_nobody_can_parse_still_become_the_query(self):
        result = identify(self.s, validate_input({"text": "cái ấm đun nước màu hồng"}))
        self.assertEqual(result["query"], "cái ấm đun nước màu hồng")

    def test_the_owners_model_cannot_be_replaced_by_a_photo_guess(self):
        with mock.patch(GEN, return_value=answer()):
            result = identify(self.s, photo("bàn phím mchose ace68"))
        self.assertEqual((result["brand"], result["model"], result["image_conflict"]), ("MCHOSE", "ACE68", True))
        self.assertIn("KZZI", result["warnings"][0])
        self.assertEqual(result["visual_identity"]["model"], "K68")
        self.assertEqual(result["queries"], {"tiktok": "mchose ace68", "douyin": "迈从 ACE68 磁轴键盘"})

    def test_a_photo_that_agrees_with_the_words_adds_its_translation_and_no_warning(self):
        agree = answer(name="MCHOSE ACE68", brand="MCHOSE", model="ACE68", query_zh="迈从 ACE68 键盘")
        with mock.patch(GEN, return_value=agree):
            result = identify(self.s, photo("bàn phím mchose ace68"))
        self.assertEqual((result["image_conflict"], result["warnings"]), (False, []))

    def test_a_picture_is_read_on_its_own_so_the_model_cannot_copy_the_words_and_hide_a_disagreement(self):
        with mock.patch(GEN, return_value=answer()) as ai:
            identify(self.s, photo("bàn phím kzzi k68"))
        sent = json.dumps(ai.call_args.args[2], ensure_ascii=False)
        self.assertNotIn("kzzi k68", sent)
        self.assertNotIn("Reference text", sent)
        long_words = validate_input({"text": "mô tả rất dài " * 20})
        with mock.patch(GEN, return_value=answer()) as ai:
            identify(self.s, long_words)
        self.assertIn("Reference text", json.dumps(ai.call_args.args[2], ensure_ascii=False))  # no files: the words are all there is

    def test_what_a_model_reads_off_a_picture_marks_its_variant_as_a_description_not_a_filter(self):
        with mock.patch(GEN, return_value=answer(variant="Magnetic")):
            result = identify(self.s, photo())
        self.assertTrue(result["variant_soft"])
        with mock.patch(GEN, return_value=answer()):
            owner = identify(self.s, photo("bàn phím mchose ace68 air"))
        self.assertNotIn("variant_soft", owner)  # the owner's own variant stays a hard requirement

    def test_words_that_name_no_brand_or_model_do_not_override_what_the_photo_shows(self):
        with mock.patch(GEN, return_value=answer()):
            result = identify(self.s, photo("tìm cho tôi cái này"))
        self.assertEqual((result["model"], result["query"]), ("K68", "KZZI K68"))

    def test_a_photo_alone_is_read_by_the_model(self):
        with mock.patch(GEN, return_value=answer()) as ai:
            result = identify(self.s, photo())
        self.assertEqual((result["name"], result["model"]), ("KZZI K68 Mechanical Keyboard", "K68"))
        sent = ai.call_args.args[2]
        self.assertTrue(any("inline_data" in p for p in sent))

    def test_a_document_is_sent_as_text_and_a_model_refusal_without_words_is_an_error(self):
        document = validate_input({"text": "", "files": [file("a.txt", b"Samsung S24 specs")]})
        with mock.patch(GEN, side_effect=ValueError("overloaded")), self.assertRaises(ValueError):
            identify(self.s, document)


class FallbackTests(StoreCase):
    """Whatever goes wrong with the model, the owner's own words still find the product."""

    def test_every_kind_of_model_failure_falls_back_to_the_words(self):
        failures = [
            {"side_effect": ValueError("overloaded")},
            {"return_value": {"candidates": [{"content": {"parts": [{"text": "not json at all"}]}}]}},
            {"return_value": {"candidates": []}},
            {"return_value": answer(name="x" * 600)},
            {"return_value": answer(query=7)},
        ]
        for failure in failures:
            with self.subTest(failure=list(failure)[0]), mock.patch(GEN, **failure):
                result = identify(self.s, photo("bàn phím mchose ace68"))
            self.assertEqual(result["model"], "ACE68")
            self.assertIn("Chưa đọc được", result["warnings"][0])

    def test_whatever_a_model_does_wrong_the_words_still_find_the_product_and_nothing_crashes(self):
        failures = [
            {"return_value": {"candidates": [{"content": None}]}},
            {"return_value": {"candidates": {}}},
            {"return_value": {"candidates": [{"content": {"parts": [{"text": 5}]}}]}},
            {"return_value": {"candidates": [{"content": {"parts": "x"}}]}},
            {"return_value": []},
            {"side_effect": TimeoutError("slow")},
            {"side_effect": ConnectionResetError("dropped")},
            {"side_effect": KeyError("x")},
        ]
        for failure in failures:
            with self.subTest(failure=str(failure)[:60]), mock.patch(GEN, **failure):
                result = identify(self.s, photo("bàn phím mchose ace68"))
            self.assertEqual(result["model"], "ACE68")
            self.assertIn("Chưa đọc được", result["warnings"][0])
            with mock.patch(GEN, **failure), self.assertRaises(ValueError):
                identify(self.s, photo())  # no words to fall back to: an error the owner can read, not a crash

    def test_words_that_name_nothing_are_no_fallback_when_the_model_fails(self):
        with mock.patch(GEN, side_effect=ValueError("overloaded")), self.assertRaises(ValueError):
            identify(self.s, photo("tìm cho tôi cái này"))

    def test_a_pasted_share_link_loses_its_query_before_a_page_goes_to_the_model(self):
        url = "https://example.com/p?share_creator_id=7&u_code=abc"
        with mock.patch(LINK_TEXT, return_value=("Band 9 page", url)), mock.patch(GEN, return_value=answer(query="Band 9")) as ai:
            identify(self.s, validate_input({"text": "tìm " + url}))
        sent = json.dumps(ai.call_args.args[2])
        self.assertIn("https://example.com/p", sent)
        self.assertNotIn("share_creator_id", sent)

    def test_every_way_a_page_can_fail_to_load_is_a_warning_not_an_abort(self):
        import http.client

        for failure in (
            ValueError("x"),
            OSError("y"),
            http.client.BadStatusLine("z"),
            http.client.IncompleteRead(b""),
            http.client.LineTooLong("l"),
        ):
            with self.subTest(failure=type(failure).__name__), mock.patch(LINK_TEXT, side_effect=failure):
                result = identify(self.s, validate_input({"text": "samsung galaxy s24 https://shop.example/p"}))
            self.assertEqual(result["model"], "S24")
            self.assertTrue(result["warnings"])

    def test_without_words_a_malformed_answer_is_an_error_worded_for_the_owner(self):
        with mock.patch(GEN, return_value={"candidates": [{"content": {"parts": [{"text": "[1, 2]"}]}}]}):
            with self.assertRaises(ValueError) as caught:
                identify(self.s, photo())
        self.assertIn("không", str(caught.exception).lower())

    def test_a_model_that_gives_no_query_is_an_error(self):
        with mock.patch(GEN, return_value=answer(query="")), self.assertRaises(ValueError):
            identify(self.s, photo())


class QueryTests(StoreCase):
    def test_translation_cannot_change_the_model_or_drop_the_variant(self):
        identity = explicit("MCHOSE ACE68 Air keyboard")
        identity["query_zh"] = "迈从 K68 键盘"
        query = query_plan(identity)["douyin"]
        self.assertIn("ACE68", query)
        self.assertIn("Air", query)
        self.assertNotIn("K68", query)

    def test_chinese_brand_and_category_words_match_and_other_models_do_not(self):
        identity = explicit("bàn phím mchose ace68")
        self.assertEqual(match_identity(identity, "迈从ACE68磁轴键盘体验")["score"], 100)
        for title in ("迈从 ACE68 Air 键盘", "MCHOSE ACE68 Turbo", "MCHOSE ACE68 V2", "KZZI K68", "MCHOSE ACE60"):
            with self.subTest(title=title):
                self.assertEqual(match_identity(identity, title)["level"], "different")

    def test_specifications_are_not_part_of_the_model_and_long_model_codes_are_read_whole(self):
        for words, model in (
            ("iPhone 15 Pro Max 256GB", "IPHONE 15"),
            ("Galaxy S24 5G 128GB", "S24"),
            ("Sony WH-1000XM4 tai nghe", "WH-1000XM4"),
        ):
            self.assertEqual(explicit(words)["model"], model, words)
        self.assertEqual(explicit("tai nghe jbl tune 760")["brand"], "JBL")
        self.assertEqual(explicit("Sony WH-1000XM4")["brand"], "Sony")

    def test_a_brand_with_no_hint_gets_a_plain_chinese_query_not_another_products_wording(self):
        plan = query_plan(explicit("Xiaomi Band 9 bàn phím"))
        self.assertNotIn("磁轴", plan["douyin"])


class LinkTests(StoreCase):
    VIDEO = "https://www.tiktok.com/@creator/video/1234567890"

    def test_a_video_link_alone_is_a_direct_candidate_without_model_or_fetch(self):
        with mock.patch(GEN) as ai, mock.patch(LINK_TEXT) as page:
            result = identify(self.s, validate_input({"text": self.VIDEO + "?is_from_webapp=1&sender_device=pc"}))
        self.assertEqual(result["links"], [self.VIDEO])
        self.assertEqual(result["query"], "Video theo đường dẫn")
        ai.assert_not_called()
        page.assert_not_called()

    def test_a_short_link_that_leads_to_a_video_is_followed_by_redirects_only(self):
        trail = {"chain": ["https://vm.tiktok.com/test/", self.VIDEO + "?x=1"], "status": 200, "stopped": ""}
        with mock.patch(FOLLOW, return_value=trail), mock.patch(LINK_TEXT) as page:
            result = identify(self.s, validate_input({"text": "https://vm.tiktok.com/test/"}))
        self.assertEqual(result["links"], [self.VIDEO])
        page.assert_not_called()

    def test_a_douyin_video_link_is_a_direct_candidate(self):
        result = identify(self.s, validate_input({"text": "https://www.douyin.com/video/7234567890123456789"}))
        self.assertEqual(result["links"], ["https://www.douyin.com/video/7234567890123456789"])

    def test_words_next_to_a_video_link_still_describe_the_product_and_the_video_rides_along(self):
        result = identify(self.s, validate_input({"text": "mchose ace68 " + self.VIDEO}))
        self.assertEqual((result["model"], result["links"]), ("ACE68", [self.VIDEO]))
        self.assertNotIn("https", result["query"])

    def test_a_link_nobody_can_read_never_invents_a_product(self):
        with mock.patch(LINK_TEXT, side_effect=ValueError("unavailable")), self.assertRaises(ValueError):
            identify(self.s, validate_input({"text": "https://example.com/p"}))

    def test_a_readable_page_goes_to_the_model_as_data_beside_the_words(self):
        with (
            mock.patch(LINK_TEXT, return_value=("Band 9 page", "https://example.com/p")),
            mock.patch(GEN, return_value=answer(query="Band 9")) as ai,
        ):
            result = identify(self.s, validate_input({"text": "tìm cái này https://example.com/p"}))
        self.assertEqual(result["query"], "Band 9")
        self.assertIn("Band 9 page", json.dumps(ai.call_args.args[2]))
        self.assertIn("tìm cái này", json.dumps(ai.call_args.args[2], ensure_ascii=False))
        self.assertEqual(result["links"], [])
