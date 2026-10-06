"""Regressions for explicit product names, Chinese queries, source selection and OAuth callbacks."""

import json
from unittest import mock

from tests.support import StoreCase
from tests.worker.test_product_search import file
from trendvn_worker.domain.product_search import match_identity, validate_input
from trendvn_worker.domain.search_queries import explicit, query_plan
from trendvn_worker.search.identify import identify
from trendvn_worker.tasks import Tasks, StepLog


class IdentityRecoveryTests(StoreCase):
    def test_user_model_cannot_be_replaced_by_photo_guess(self):
        guess = dict(
            name="KZZI K68 Mechanical Keyboard",
            brand="KZZI",
            model="K68",
            variant="White",
            query="KZZI K68",
            query_zh="KZZI K68 键盘",
            uncertainty="",
        )
        response = {"candidates": [{"content": {"parts": [{"text": json.dumps(guess)}]}}]}
        reference = validate_input({"text": "bàn phím mchose ace68", "files": [file("keyboard.png", b"\x89PNG\r\n\x1a\nphoto")]})
        with mock.patch("trendvn_worker.search.identify.generate", return_value=response):
            result = identify(self.s, reference)
        self.assertEqual(result["brand"], "MCHOSE")
        self.assertEqual(result["model"], "ACE68")
        self.assertTrue(result["image_conflict"])
        self.assertIn("KZZI", result["warnings"][0])
        self.assertEqual(result["queries"], {"tiktok": "mchose ace68", "douyin": "迈从 ACE68 磁轴键盘"})

    def test_ai_unavailable_still_searches_explicit_product(self):
        reference = validate_input({"text": "bàn phím mchose ace68", "files": [file("keyboard.pdf", b"%PDF-photo")]})
        with mock.patch("trendvn_worker.search.identify.generate", side_effect=ValueError("overloaded")):
            result = identify(self.s, reference)
        self.assertEqual(result["model"], "ACE68")
        self.assertIn("Chưa đọc được", result["warnings"][0])
        reference["text"] = ""
        with mock.patch("trendvn_worker.search.identify.generate", side_effect=ValueError("overloaded")), self.assertRaises(ValueError):
            identify(self.s, reference)

    def test_translation_cannot_change_model_or_omit_variant(self):
        identity = explicit("MCHOSE ACE68 Air keyboard")
        identity["query_zh"] = "迈从 K68 键盘"
        query = query_plan(identity)["douyin"]
        self.assertIn("ACE68", query)
        self.assertIn("Air", query)
        self.assertNotIn("K68", query)

    def test_chinese_brand_and_keyboard_keywords_match(self):
        identity = explicit("bàn phím mchose ace68")
        result = match_identity(identity, "迈从ACE68磁轴键盘体验")
        self.assertEqual(result["score"], 100)
        for title in ("迈从 ACE68 Air 键盘", "MCHOSE ACE68 Turbo", "MCHOSE ACE68 V2", "KZZI K68", "MCHOSE ACE60"):
            with self.subTest(title=title):
                self.assertEqual(match_identity(identity, title)["level"], "different")

    def test_retry_is_new_session_and_does_not_recall_ai(self):
        sid = self.s.search_create("main", {}, "videos")
        self.s.search_update(sid, "error", identity=explicit("KZZI K68"), error="captcha")
        new = self.s.search_retry(sid, "bàn phím mchose ace68", "douyin")
        self.assertNotEqual(new, sid)
        self.assertEqual(self.s.search_get(sid)["identity"]["query"], "KZZI K68")
        tasks = Tasks.__new__(Tasks)
        tasks.store, tasks.token = self.s, "test"
        tid = self.s.task_create("search", new)
        with (
            mock.patch("trendvn_worker.tasks.call_agent", return_value={"items": []}) as agent,
            mock.patch("trendvn_worker.search.identify.generate") as ai,
        ):
            self.assertTrue(tasks._search_step(StepLog(self.s, tid), "search", new))
        ai.assert_not_called()
        self.assertEqual(agent.call_args.args[1]["queries"]["douyin"], "迈从 ACE68 磁轴键盘")

    def test_sources_with_same_id_are_not_ambiguous_or_wrong_country(self):
        sid = self.s.search_create("main", {}, "videos")
        items = [
            {"source_id": "1234567890", "platform": p, "title": "MCHOSE ACE68", "match": {"level": "candidate"}, "url": url}
            for p, url in (
                ("douyin", "https://www.douyin.com/video/1234567890"),
                ("tiktok", "https://www.tiktok.com/@creator/video/1234567890"),
            )
        ]
        self.s.search_update(sid, "done", results=items)
        with self.assertRaises(ValueError):
            self.s.search_select(sid, "1234567890", True)
        jid = self.s.search_select(sid, "1234567890", True, "douyin")
        with self.s.connect() as db:
            self.assertEqual(db.execute("SELECT country FROM jobs WHERE id=?", (jid,)).fetchone()[0], "CN")
        self.assertEqual(self.s.search_media_ready(jid)["item"]["platform"], "douyin")
