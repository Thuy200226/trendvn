"""How the chat thread reads: every kind of answer in every state, hostile text escaped, and the one thing the owner can do next."""

import re
import unittest

from tests.support import StoreCase, TZ, at  # noqa: F401  (also puts the source folders on sys.path)
from trendvn_worker import ui
from trendvn_worker.ui.tabs.search import chat_side
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
        self.assertNotIn('data-chat-act="confirm"', html)

    def test_a_recognised_product_offers_searches_and_a_correction(self):
        html = render(message(2, "product", {"identity": identity(warnings=["Ảnh khác tên bạn nhập"])}))
        self.assertIn("MCHOSE ACE68", html)
        self.assertIn("Ảnh khác tên bạn nhập", html)
        actions = re.findall(r'data-chat-act="(\w+)"', html)
        self.assertEqual(sorted(actions), ["delete_history", "fill", "find", "find", "find", "find"])
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

    def test_old_result_cards_recheck_a_stored_match_without_another_platform_search(self):
        html = render(message(3, "videos", self.videos(results=[result(title="迈从ACE75 对比 ACE68")])))
        self.assertNotIn('data-chat-act="pick"', html)
        self.assertIn("model khác cùng dòng", html)

    def test_a_picked_candidate_shows_where_the_download_has_got_to_instead_of_the_button(self):
        picked = {"3": [{"source_id": "1234567890", "platform": "tiktok", "state_label": "Chờ tải video đã chọn", "reason": "Bạn đã chọn"}]}
        html = render(message(3, "videos", self.videos()), picked=picked)
        self.assertIn("Chờ tải video đã chọn", html)
        self.assertNotIn('data-chat-act="pick"', html)

    def test_polling_tracks_a_download_task_and_stops_after_failure_or_completion(self):
        job = {"source_id": "1234567890", "platform": "tiktok", "state_label": "Chờ tải", "reason": "", "downloading": True}
        self.assertIn('data-busy="1"', render(message(3, "videos", self.videos()), picked={"3": [job]}))
        self.assertIn('data-busy="0"', render(message(3, "videos", self.videos()), picked={"3": [dict(job, downloading=False)]}))

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
            self.assertNotIn('data-chat-act="confirm"', html)
            self.assertNotIn("data-copy", html)

    def test_a_plain_link_that_was_kept_says_it_carries_no_commission_mark(self):
        link = self.link("exact", saved=True)
        link["body"]["verdict"]["kind"] = "plain"
        self.assertIn("link thường", render(link))

    def test_the_confirm_button_says_what_the_owner_is_vouching_for_by_kind_of_link(self):
        for kind, words in (
            ("affiliate", "link hoa hồng của tôi"),
            ("short", "sao chép link này từ Showcase"),
            ("plain", "không có dấu hiệu hoa hồng"),
        ):
            link = self.link("exact")
            link["body"]["verdict"]["kind"] = kind
            self.assertIn(words, render(link), kind)

    def test_a_link_that_turned_out_to_be_a_video_says_so_and_offers_nothing_to_confirm(self):
        html = render(
            message(4, "link", {"url": "https://vt.tiktok.com/ZSv/", "video": "https://www.tiktok.com/@a/video/1234567890", "product": 5})
        )
        self.assertIn("một <b>video</b>", html)
        self.assertNotIn('data-chat-act="confirm"', html)

    def test_the_composer_tells_the_owner_what_goes_to_google(self):
        from trendvn_worker.ui.tabs import search

        class View:
            csrf = "x"
            d = {"accounts": [{"id": "main", "username": "u", "enabled": True}]}

        self.assertIn("Gemini (Google)", search.composer(View()))

    def test_a_running_or_failed_check_shows_neither_verdict_nor_buttons(self):
        self.assertIn("Đang kiểm tra link", render(message(4, "link", {"url": "x"}, state="running")))
        html = render(message(4, "link", {"url": "x", "error": "Chỉ nhận đường dẫn https của TikTok"}, state="error"))
        self.assertIn("Chỉ nhận đường dẫn", html)
        self.assertNotIn('data-chat-act="confirm"', html)


class SignInTests(unittest.TestCase):
    ROSTER = [{"id": "main", "username": "chu_shop"}, {"id": "pets", "username": "pets_shop"}]

    def side(self, channels=None, saved=None):
        data = {"messages": [], "picked": {}, "accounts": {}, "roster": self.ROSTER, "channels": channels or {}, "saved": saved or {}}
        return chat_side(data, NOW)

    def test_every_account_gets_a_row_per_channel_with_what_is_known_and_a_way_to_sign_in_or_check(self):
        html = self.side(
            {
                "main": {
                    "douyin": {"state": "wall", "who": "", "at": NOW - 120},
                    "tiktok": {"state": "ok", "who": "chu_shop", "at": NOW - 7200},
                }
            }
        )
        for words in ("@chu_shop", "@pets_shop", "Đòi xác minh", "Sẵn sàng", "2 phút trước", "2 giờ trước", "Chưa kiểm"):
            self.assertIn(words, html)
        logins = re.findall(r'data-chat-act="login" data-channel="(\w+)" data-account="(\w+)"', html)
        self.assertEqual(
            sorted(logins),
            [(channel, account) for channel in ("douyin", "instagram", "kuaishou", "tiktok") for account in ("main", "pets")],
        )
        self.assertEqual(len(re.findall(r'data-chat-act="check"', html)), 8)

    def test_identical_buttons_are_told_apart_for_a_screen_reader(self):
        html = self.side({}, {"main": [{"title": "Bàn phím", "url": "https://vt.tiktok.com/ZS/", "product_id": "1729384756102938475"}]})
        labels = re.findall(r'aria-label="([^"]+)"', html)
        for words in (
            "Đăng nhập Douyin cho @chu_shop",
            "Đăng nhập TikTok cho @pets_shop",
            "Kiểm tra đăng nhập Douyin của @chu_shop",
            "Xóa link đã lưu: Bàn phím",
        ):
            self.assertIn(words, labels)
        buttons = re.findall(r'<button[^>]*data-chat-act="(?:login|check)"[^>]*>', html)
        self.assertEqual(len(buttons), len({b for b in buttons}))  # no two sign-in buttons are alike

    def test_the_side_says_who_does_the_signing_in_and_what_is_kept(self):
        html = self.side()
        self.assertIn("hệ thống không nhập mật khẩu hộ", html)
        self.assertIn("Cửa sổ đăng nhập mở trên máy chạy TrendVN", html)

    def test_saved_links_can_be_copied_and_forgotten_with_a_question_first(self):
        saved = {"main": [{"title": "Bàn phím <b>", "url": "https://vt.tiktok.com/ZSabc/", "product_id": "1729384756102938475"}]}
        html = self.side(saved=saved)
        self.assertIn("data-copy", html)
        self.assertIn('value="https://vt.tiktok.com/ZSabc/"', html)
        self.assertIn("Bàn phím &lt;b&gt;", html)
        self.assertIn('data-chat-act="forget" data-account="main" data-product-id="1729384756102938475" data-ask=', html)
        self.assertIn("Chưa có link nào", self.side())

    def test_clearing_the_history_asks_first_and_says_what_stays(self):
        html = self.side()
        self.assertRegex(html, r'data-chat-act="clear" data-ask="[^"]*vẫn giữ')

    def test_with_no_enabled_account_there_is_nothing_to_sign_in_and_it_says_so(self):
        data = {"messages": [], "picked": {}, "accounts": {}, "roster": [], "channels": {}, "saved": {}}
        self.assertIn("Chưa có tài khoản nào đang bật", chat_side(data, NOW))

    def test_the_fragment_the_page_polls_carries_both_the_thread_and_the_side(self):
        from trendvn_worker.ui.tabs.search import chat_fragment

        data = {"messages": [], "picked": {}, "accounts": {}, "roster": self.ROSTER, "channels": {}, "saved": {}}
        html = chat_fragment(data, NOW)
        self.assertLess(html.index('id="chat-thread"'), html.index('id="chat-side"'))


class LoginCardTests(unittest.TestCase):
    def login(self, state="running", mode="login", **fields):
        return message(7, "login", {"channel": "douyin", "account_username": "chu_shop", "mode": mode} | fields, state=state)

    def test_while_the_window_is_open_the_card_says_where_it_is_and_that_nothing_is_typed_for_the_owner(self):
        html = render(self.login())
        for words in ("Đăng nhập Douyin", "@chu_shop", "máy chạy TrendVN", "không nhập mật khẩu thay bạn", "10 phút"):
            self.assertIn(words, html)
        self.assertIn('data-busy="1"', html)

    def test_a_finished_sign_in_says_it_worked_and_a_failed_one_offers_to_try_again(self):
        self.assertIn("Đã đăng nhập", render(self.login("done", ok=True)))
        failed = render(self.login("error", error="Chưa thấy đăng nhập Douyin trong thời gian chờ"))
        self.assertIn("Chưa thấy đăng nhập Douyin", failed)
        self.assertIn('data-chat-act="login" data-channel="douyin" data-account="main"', failed)

    def test_a_cookie_check_does_not_claim_more_than_it_knows(self):
        html = render(self.login("done", mode="check", ok=True))
        self.assertIn("Hồ sơ có phiên đăng nhập Douyin", html)
        self.assertIn("Chưa kiểm đúng tài khoản", html)
        self.assertNotIn("✓ Đã đăng nhập", html)
        self.assertIn("Đã đăng nhập: tìm kiếm trên Douyin dùng được", render(self.login("done", ok=True)))  # a real sign-in does

    def test_a_failed_check_is_titled_a_check_not_a_sign_in(self):
        html = render(self.login("error", mode="check", error="Agent bận"))
        self.assertIn("<h4>Kiểm tra Douyin", html)
        self.assertNotIn("<h4>Đăng nhập Douyin", html)

    def test_a_check_that_found_nobody_signed_in_offers_the_window(self):
        html = render(self.login("done", mode="check", ok=False))
        self.assertIn("Chưa đăng nhập", html)
        self.assertIn('data-chat-act="login"', html)
        self.assertIn("Đang đọc phiên đã lưu", render(self.login(mode="check")))

    def test_a_failed_search_offers_to_sign_in_to_the_channels_it_used(self):
        body = {
            "identity": identity(),
            "source": "auto",
            "account_username": "chu_shop",
            "product": 2,
            "results": [],
            "error": "Douyin đòi xác minh",
        }
        html = render(message(3, "videos", body, state="error"))
        self.assertIn("Đăng nhập TikTok", html)
        self.assertIn("Đăng nhập Douyin", html)
        single = render(message(3, "videos", body | {"source": "douyin"}, state="error"))
        self.assertNotIn("Đăng nhập TikTok", single)
        self.assertIn("Đăng nhập Douyin", single)


class PageTests(StoreCase):
    def page(self):
        data = self.s.dashboard_data()
        data.update(notify_channels=[], voice_sample=False, ready=[], tasks=[], chat=chat_data(self.s))
        return ui.render(data, "CSRFX")

    def test_the_search_tab_is_in_the_navigation_and_holds_the_composer(self):
        html = self.page()
        self.assertNotIn('data-go="search"', html)
        self.assertIn('data-go="queue"', html)
        self.assertIn('<section data-tab="queue" id="queue"', html)
        self.assertIn('<div id="search"', html)
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

    def test_the_page_carries_the_sign_ins_saved_links_and_history_beside_the_chat(self):
        self.s.channel_report("main", "douyin", "wall")
        self.s.commission_save(
            "main",
            {
                "input": "https://vt.tiktok.com/ZSabc/",
                "product_id": "1729384756102938475",
                "title": "Bàn phím",
                "markers": {},
                "tracked": False,
            },
        )
        html = self.page()
        self.assertIn('class="chat-layout" data-chat', html)
        self.assertIn("Đòi xác minh", html)
        self.assertIn('value="https://vt.tiktok.com/ZSabc/"', html)
        self.assertIn('data-chat-act="clear"', html)
        self.assertLess(html.index('id="chat-thread"'), html.index('id="chat-side"'))

    def test_the_chat_without_any_account_asks_for_one_instead_of_offering_a_form(self):
        with self.s.transaction() as db:
            db.execute("UPDATE accounts SET enabled=0")
        self.assertIn("Chưa có tài khoản nào đang bật", self.page())


if __name__ == "__main__":
    unittest.main()
