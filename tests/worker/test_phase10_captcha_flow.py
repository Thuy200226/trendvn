"""Tests for Phase X: Douyin Captcha resolution, non-blocking chat user flow and smooth UI recovery."""

import unittest
from unittest import mock

from trendvn_worker.tasks import AgentError, TaskBusy, Tasks
from trendvn_worker.web.chat_forms import find


class DummyStore:
    def __init__(self):
        self._running = []
        self._chat = {
            101: {
                "id": 101,
                "kind": "product",
                "state": "done",
                "hidden": False,
                "account": "main",
                "body": {
                    "identity": {
                        "name": "Bàn phím cơ",
                        "query": "Bàn phím cơ",
                        "queries": {"douyin": "机械键盘 测评 开箱"},
                    },
                    "discovery": {"topic": "entertainment", "category": "electronics", "sales": True, "source": "auto"},
                },
            }
        }
        self._accounts = {"main": {"username": "bubituean"}}

    def tasks_running(self):
        return self._running

    def tasks_reap(self):
        pass

    def chat_recover(self):
        pass

    def delete_post_recover(self):
        pass

    def task_create(self, kind, job_id):
        return f"task-{kind}-1"

    def chat_get(self, mid):
        return self._chat[mid]

    def account(self, acc):
        return self._accounts.get(acc)

    def chat_find(self, account, body):
        return 102, True, None

    def chat_find_refused(self, mid, previous):
        pass


class Phase10CaptchaFlowTests(unittest.TestCase):
    def test_identify_not_blocked_by_collect_browser_task(self):
        """When an automatic background collection task ('collect') is running,
        user submitting a chat product message ('identify') MUST NOT be blocked by TaskBusy."""
        import threading

        store = DummyStore()
        store._running = [{"kind": "collect", "job_id": None}]
        tasks = Tasks(store, "http://127.0.0.1:5682", "token", threading.Lock())

        with mock.patch("threading.Thread.start"):
            # 'identify' must start smoothly without raising TaskBusy
            tid = tasks.start("identify", "101")
            self.assertEqual(tid, "task-identify-1")

    def test_search_download_uses_browser(self):
        """Browser tasks like search_download are still properly guarded when another browser task runs."""
        import threading

        store = DummyStore()
        store._running = [{"kind": "collect", "job_id": None}]
        tasks = Tasks(store, "http://127.0.0.1:5682", "token", threading.Lock())

        with self.assertRaises(TaskBusy):
            tasks.start("search_download", "a" * 32)

    def test_human_flag_parsed_correctly_from_string_and_bool(self):
        """UI buttons send human as string 'true' or bool True; both must be parsed as human=True."""
        store = DummyStore()
        app = mock.Mock()
        app.store = store
        app.tasks = mock.Mock()

        # Test with string "true"
        payload_str = {"id": 101, "source": "douyin", "human": "true", "account": "main"}
        find(app, payload_str)
        app.tasks.start.assert_called_with("search_human", "102")

        # Test with boolean True
        app.tasks.reset_mock()
        payload_bool = {"id": 101, "source": "douyin", "human": True, "account": "main"}
        find(app, payload_bool)
        app.tasks.start.assert_called_with("search_human", "102")

        # Test with human omitted / false
        app.tasks.reset_mock()
        payload_none = {"id": 101, "source": "douyin", "account": "main"}
        find(app, payload_none)
        app.tasks.start.assert_called_with("search", "102")

    def test_agent_clean_error_message_no_500_prefix(self):
        """Captcha/Wall errors from agent must not be prefixed with raw 'Agent báo lỗi 500:'."""
        from urllib.error import HTTPError
        import io
        from trendvn_worker.tasks import call_agent

        # Simulate agent returning 500 with captcha message
        error_body = io.BytesIO(b'{"error": "douyin: Douyin y\\u00eau c\\u1ea7u x\\u00e1c nh\\u1eadn CAPTCHA."}')
        http_err = HTTPError("http://127.0.0.1:5682/api/search", 500, "Internal Server Error", {}, error_body)

        with mock.patch("urllib.request.urlopen", side_effect=http_err):
            with self.assertRaises(AgentError) as ctx:
                call_agent("/api/search", {}, "token")
            err_msg = str(ctx.exception)
            self.assertNotIn("Agent báo lỗi 500", err_msg)
            self.assertIn("Douyin yêu cầu xác nhận CAPTCHA", err_msg)

    def test_douyin_search_fallback_urls_contain_jingxuan(self):
        """Douyin search must include fallback to jingxuan/search."""
        from trendvn_agent.search_douyin import search
        import inspect

        source = inspect.getsource(search)
        self.assertIn("https://www.douyin.com/jingxuan/search/", source)
        self.assertIn("https://www.douyin.com/search/", source)


if __name__ == "__main__":
    unittest.main()
