"""Stale cookies, public user data and navigation cannot masquerade as a Douyin owner session."""

import json
from unittest import TestCase, mock

from trendvn_agent.douyin_session import Session, SELF_PATH
from trendvn_agent.search_douyin import query_response, resume_query
from trendvn_agent.search_capture import Capture


def page():
    p = mock.Mock(url="https://www.douyin.com/")
    p.is_closed.return_value = False
    p.title.return_value = "抖音精选"
    p.locator.return_value.count.return_value = 0
    p.get_by_text.return_value.count.return_value = 0
    return p


def response(data, path=SELF_PATH, host="www.douyin.com"):
    return mock.Mock(url="https://" + host + path, status=200, body=mock.Mock(return_value=json.dumps(data).encode()))


class DouyinSessionTests(TestCase):
    def test_cookie_and_public_profile_are_not_authenticated_owner_evidence(self):
        p = page()
        s = Session(p)
        for path in ("/aweme/v1/web/query/user/", "/aweme/v1/web/user/profile/other/", "/aweme/v1/web/search/item/"):
            s.observe(response({"status_code": 0, "user": {"uid": "123", "sec_uid": "public"}}, path))
        self.assertEqual(s.state(p), "unknown")
        self.assertFalse(s.proven)

    def test_owner_response_authenticates_and_guest_login_overrides_old_proof(self):
        p = page()
        s = Session(p)
        s.observe(response({"status_code": 0, "user": {"uid": "123", "sec_uid": "owner", "unique_id": "owner-name"}}))
        self.assertEqual((s.state(p), s.who), ("ok", "owner-name"))
        p.get_by_text.return_value.count.return_value = 1
        p.get_by_text.return_value.nth.return_value.is_visible.return_value = True
        self.assertEqual(s.state(p), "out")
        p.get_by_text.return_value.count.return_value = 0
        self.assertEqual(s.state(p), "unknown")

    def test_wall_does_not_forget_authenticated_owner_but_blocks_ready(self):
        p = page()
        s = Session(p)
        s.observe(response({"status_code": 0, "user": {"uid": "123", "sec_uid": "owner"}}))
        p.title.return_value = "验证码中间页"
        self.assertEqual(s.state(p), "wall")
        self.assertTrue(s.proven)
        p.title.return_value = "抖音"
        self.assertEqual(s.state(p), "ok")
        p.url = "chrome-error://chromewebdata/"
        self.assertEqual(s.state(p), "unknown")

    def test_foreign_host_invalid_status_or_empty_identity_cannot_prove_a_session(self):
        for data, host in (
            ({"status_code": 1, "user": {"uid": "123", "sec_uid": "owner"}}, "www.douyin.com"),
            ({"status_code": 0, "user": {}}, "www.douyin.com"),
            ({"status_code": 0, "user": {"uid": "123", "sec_uid": "owner"}}, "www.douyin.com.evil.com"),
        ):
            s = Session(page())
            s.observe(response(data, host=host))
            self.assertFalse(s.proven)

    def test_exact_keyword_response_accepts_post_and_rejects_recommendations_or_other_queries(self):
        for suffix, posted, wanted in (
            ("?keyword=ACE68", None, True),
            ("", "keyword=ACE68", True),
            ("", '{"keyword":"ACE68"}', True),
            ("?keyword=ACE75", "keyword=ACE68", False),
            ("?keyword=ACE68&keyword=ACE75", None, False),
            ("", "keyword=ACE75", False),
        ):
            r = mock.Mock(url="https://www.douyin.com/aweme/v1/web/search/item/" + suffix)
            r.request.post_data = posted
            self.assertEqual(query_response(r, "ACE68"), wanted)
        r.url = "https://www.douyin.com/aweme/v1/web/aweme/post/?keyword=ACE68"
        self.assertFalse(query_response(r, "ACE68"))

    def test_login_on_same_query_replays_it_once_after_owner_completes(self):
        url = "https://www.douyin.com/search/ACE68?type=video"
        p = mock.Mock(url=url)
        resume = resume_query(url, Capture((), None), reload_same=True)
        self.assertFalse(resume(p, False))
        self.assertTrue(resume(p, True))
        self.assertFalse(resume(p, True))
        p.goto.assert_called_once_with(url, wait_until="domcontentloaded", timeout=45000)

    def test_negative_self_or_wrong_schema_revokes_previous_proof(self):
        for bad in ({"status_code": 8, "user": None}, {"status_code": False, "user": {"uid": ["123"], "sec_uid": {"id": "abc"}}}):
            s = Session(page())
            s.observe(response({"status_code": 0, "user": {"uid": "123", "sec_uid": "owner"}}))
            self.assertTrue(s.proven)
            s.observe(response(bad))
            self.assertFalse(s.proven)
            self.assertEqual(s.who, "")

    def test_http_denial_revokes_old_proof_instead_of_using_a_cached_account(self):
        s = Session(page())
        good = response({"status_code": 0, "user": {"uid": "123", "sec_uid": "owner"}})
        s.observe(good)
        good.status = 401
        s.observe(good)
        self.assertFalse(s.proven)
