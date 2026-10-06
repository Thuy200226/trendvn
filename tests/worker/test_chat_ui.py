"""How the chat thread reads: every kind of answer in every state, hostile text escaped, and the one thing the owner can do next."""

import re
import unittest

from tests.support import StoreCase, TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import ui
from trendvn_worker.web.pages import chat_data

NOW = 1_800_000_000.0


def message(mid, kind, body, state="done", role="bot", account="main"):
    return {"id": mid, "role": role, "kind": kind, "state": state, "account": account, "created": NOW - 30, "body": body}


def render(*messages, picked=None):
    data = {"messages": list(messages), "picked": picked or {}, "accounts": {"main": "chu_shop"}, "product": None}
    return ui.chat_thread(data, NOW)


def identity(**fields):
    return {"name": "MCHOSE ACE68", "brand": "MCHOSE", "model": "ACE68", "variant": "", "query": "mchose ace68", "uncertainty": "Cần xem video",
            "queries": {"tiktok": "mchose ace68", "douyin": "迈从 ACE68"}, "warnings": []} | fields  # fmt: skip


def result(**fields):
    return {"source_id": "1234567890", "platform": "tiktok", "title": "MCHOSE ACE68 review", "url": "https://www.tiktok.com/@a/video/1234567890",
            "match": {"level": "candidate", "score": 100, "reason": "Khớp 100%"}} | fields  # fmt: skip


class ThreadTests(unittest.TestCase):
    def test_an_empty_chat_says_what_to_send_and_what_it_cannot_do(self):
        html = render()
        self.assertIn("Gửi cho mình", html)
        self.assertIn("không thể tự lấy link hoa hồng", html)
        self.assertIn('data-busy="0"', html)

    def test_the_owners_words_files_and_account_are_shown_and_escaped(self):
        html = render(
            message(1, "say", {"text": "<img src=x onerror=alert(1)>", "files": [{"name": "a<b>.png", "kind": "image"}]}, role="user")
        )
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn("a&lt;b&gt;.png", html)
        self.assertIn("@chu_shop", html)

    def test_a_running_answer_marks_the_thread_busy_so_the_page_keeps_polling(self):
        html = render(message(1, "product", {}, state="running"))
        self.assertIn('data-busy="1"', html)
        self.assertIn("Đang nhận diện", html)
        self.assertNotIn("data-chat-act", html)

    def test_a_recognised_product_offers_searches_and_a_correction(self):
        html = render(message(2, "product", {"identity": identity(warnings=["Ảnh khác tên bạn nhập"])}))
        self.assertIn("MCHOSE ACE68", html)
        self.assertIn("Ảnh khác tên bạn nhập", html)
        actions = re.findall(r'data-chat-act="(\w+)"', html)
        self.assertEqual(sorted(actions), ["fill", "find", "find"])
        self.assertIn('data-source="douyin"', html)
        self.assertIn('data-id="2"', html)

    def test_a_product_taken_from_a_link_says_so(self):
        html = render(message(2, "product", {"identity": identity(product_id="1729384756102938475"), "from_link": True}))
        self.assertIn("Lấy từ link bạn dán", html)
        self.assertIn("1729384756102938475", html)

    def test_a_failed_answer_shows_its_reason_as_an_alert(self):
        html = render(message(2, "product", {"error": "Gemini quá tải <b>"}, state="error"))
        self.assertIn('role="alert"', html)
        self.assertIn("Gemini quá tải &lt;b&gt;", html)


class VideoTests(unittest.TestCase):
    def videos(self, **body):
        base = {"identity": identity(), "source": "tiktok", "account_username": "chu_shop", "product": 2, "results": [result()], "note": ""}
        return base | body

    def test_each_candidate_needs_the_owners_tick_before_the_pick_button_works(self):
        html = render(message(3, "videos", self.videos()))
        self.assertIn("data-chat-confirm", html)
        self.assertIn('data-chat-act="pick"', html)
        self.assertIn('data-source-id="1234567890"', html)
        self.assertIn('rel="noopener noreferrer"', html)
        self.assertIn("@chu_shop", html)

    def test_a_candidate_of_another_product_cannot_be_picked(self):
        html = render(message(3, "videos", self.videos(results=[result(match={"level": "different", "score": 0, "reason": "Khác model"})])))
        self.assertNotIn('data-chat-act="pick"', html)
        self.assertIn("Khác sản phẩm đã nhận diện", html)

    def test_a_picked_candidate_shows_where_the_download_has_got_to_instead_of_the_button(self):
        picked = {"3": [{"source_id": "1234567890", "platform": "tiktok", "state_label": "Chờ tải video đã chọn", "reason": "Bạn đã chọn"}]}
        html = render(message(3, "videos", self.videos()), picked=picked)
        self.assertIn("Chờ tải video đã chọn", html)
        self.assertNotIn('data-chat-act="pick"', html)

    def test_a_failed_search_offers_a_retry_and_the_owners_own_verification_window(self):
        html = render(message(3, "videos", self.videos(error="TikTok yêu cầu xác minh"), state="error"))
        self.assertIn("TikTok yêu cầu xác minh", html)
        self.assertIn('data-human="true"', html)
        self.assertEqual(len(re.findall(r'data-chat-act="find"', html)), 2)
        self.assertIn('data-id="2"', html)  # the retry asks about the product, not about the failed answer

    def test_a_search_in_both_sources_offers_no_verification_window_because_it_needs_one_source(self):
        html = render(message(3, "videos", self.videos(source="auto", error="x"), state="error"))
        self.assertNotIn("data-human", html)

    def test_a_search_with_no_candidates_says_so_and_a_running_one_says_it_may_take_minutes(self):
        self.assertIn("Không có ứng viên", render(message(3, "videos", self.videos(results=[]))))
        self.assertIn("vài phút", render(message(3, "videos", self.videos(), state="running")))


class LinkTests(unittest.TestCase):
    def link(self, verdict, saved=False, **fields):
        found = {"input": "https://vt.tiktok.com/ZSabc123/", "product_id": "1729384756102938475", "title": "Bàn phím"}
        checks = [
            {"label": "Mã sản phẩm", "state": "ok", "detail": "Mã trùng"},
            {"label": "Mã nhà sáng tạo", "state": "warn", "detail": "Khác <b>"},
        ]
        result = {"verdict": verdict, "summary": "Tóm tắt", "kind": "affiliate", "needs_confirmation": True, "checks": checks}
        return message(4, "link", {"url": found["input"], "found": found, "verdict": result, "saved": saved} | fields)

    def test_the_verdict_its_summary_and_every_check_are_shown(self):
        html = render(self.link("exact"))
        self.assertIn("Đúng sản phẩm", html)
        self.assertIn("Tóm tắt", html)
        self.assertIn("Mã nhà sáng tạo", html)
        self.assertIn("Khác &lt;b&gt;", html)
        self.assertIn('class="warn"', html)

    def test_an_unsaved_link_asks_the_owner_to_say_it_is_theirs_and_explains_why(self):
        html = render(self.link("exact"))
        self.assertIn('data-chat-act="confirm"', html)
        self.assertIn("không tự biết link này có phải của bạn", html)

    def test_a_saved_link_can_be_copied_and_an_unsaved_one_cannot(self):
        saved = render(self.link("exact", saved=True))
        self.assertIn("data-copy", saved)
        self.assertIn('value="https://vt.tiktok.com/ZSabc123/"', saved)
        self.assertNotIn('data-chat-act="confirm"', saved)
        self.assertNotIn("data-copy", render(self.link("exact")))

    def test_a_link_of_another_product_or_an_invalid_one_offers_nothing_to_confirm_or_copy(self):
        for verdict, label in (("different", "Sản phẩm khác"), ("invalid", "Không hợp lệ")):
            html = render(self.link(verdict))
            self.assertIn(label, html)
            self.assertNotIn("data-chat-act", html)
            self.assertNotIn("data-copy", html)

    def test_a_plain_link_that_was_kept_says_it_carries_no_commission_mark(self):
        link = self.link("exact", saved=True)
        link["body"]["verdict"]["kind"] = "plain"
        self.assertIn("link thường", render(link))

    def test_a_running_or_failed_check_shows_neither_verdict_nor_buttons(self):
        self.assertIn("Đang kiểm tra link", render(message(4, "link", {"url": "x"}, state="running")))
        html = render(message(4, "link", {"url": "x", "error": "Chỉ nhận đường dẫn https của TikTok"}, state="error"))
        self.assertIn("Chỉ nhận đường dẫn", html)
        self.assertNotIn("data-chat-act", html)


class PageTests(StoreCase):
    def page(self):
        data = self.s.dashboard_data()
        data.update(notify_channels=[], voice_sample=False, ready=[], tasks=[], chat=chat_data(self.s))
        return ui.render(data, "CSRFX")

    def test_the_search_tab_is_in_the_navigation_and_holds_the_composer(self):
        html = self.page()
        self.assertIn('data-go="search"', html)
        self.assertIn('<section data-tab="search" id="search"', html)
        self.assertIn("data-chat-form", html)
        self.assertIn('data-csrf="CSRFX"', html)
        self.assertNotIn("data-search-form", html)

    def test_the_page_shows_what_the_chat_holds_and_the_picked_videos_of_each_search(self):
        self.s.chat_ask("main", {"text": "mchose ace68"}, "product", {})
        body = {
            "identity": identity(),
            "source": "tiktok",
            "account_username": self.s.account("main")["username"],
            "results": [result(match={"level": "candidate", "score": 90, "reason": "x"})],
        }
        mid = self.s.chat_add("bot", "videos", body, account="main")
        self.s.videos_select(mid, "1234567890", True)
        html = self.page()
        self.assertIn("mchose ace68", html)
        self.assertIn("Chờ tải video đã chọn", html)
        self.assertEqual(chat_data(self.s)["product"], None)

    def test_the_chat_without_any_account_asks_for_one_instead_of_offering_a_form(self):
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET enabled=0")
        self.assertIn("Chưa có tài khoản nào đang bật", self.page())


if __name__ == "__main__":
    unittest.main()
