"""An agent job that runs past its limit is reported (not killed), /health says what holds the browser, and the lock is freed when it ends."""

import http.client
import json
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from tests.support import StoreCase  # noqa: F401  (puts the source folders on sys.path and keeps the agent log out of data/)
from trendvn_agent import server

TOKEN = "t" * 40


class Agent:
    """The real Handler on a real socket, with the routes replaced."""

    def __init__(self, routes, limits):
        self.patches = [
            mock.patch.object(server, "TOKEN", TOKEN),
            mock.patch.object(server, "ROUTES", routes),
            mock.patch.object(server, "JOB_SECONDS", limits),
        ]
        for patch in self.patches:
            patch.start()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.port = self.httpd.server_address[1]

    def call(self, method, path):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=b"{}" if method == "POST" else None, headers={"Authorization": "Bearer " + TOKEN})
        response = conn.getresponse()
        data = json.loads(response.read())
        conn.close()
        return response.status, data

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        for patch in self.patches:
            patch.stop()


class DeadlineTests(unittest.TestCase):
    def setUp(self):
        self.release = threading.Event()
        self.alerts = []

        def slow(payload):
            self.release.wait(5)
            return {"done": True}

        self.agent = Agent({"/api/slow": slow}, {"/api/slow": 0.2})
        alerts = mock.patch.object(server, "worker", lambda path, payload=None, timeout=900: self.alerts.append((path, payload)) or {})
        alerts.start()
        self.addCleanup(alerts.stop)
        self.addCleanup(self.agent.stop)

    def run_slow(self):
        result = []
        thread = threading.Thread(target=lambda: result.append(self.agent.call("POST", "/api/slow")))
        thread.start()
        return thread, result

    def test_a_job_over_its_limit_is_reported_once_and_keeps_running(self):
        thread, result = self.run_slow()
        time.sleep(0.6)
        self.assertEqual(len(self.alerts), 1)
        path, payload = self.alerts[0]
        self.assertEqual((path, payload["step"]), ("/api/alert", "agent /api/slow"))
        self.assertTrue(thread.is_alive())  # reported, not killed
        self.release.set()
        thread.join(5)
        self.assertEqual(result[0], (200, {"done": True}))

    def test_a_job_that_ends_in_time_sends_no_alert_and_frees_the_browser(self):
        self.release.set()
        self.assertEqual(self.agent.call("POST", "/api/slow")[0], 200)
        time.sleep(0.5)
        self.assertEqual(self.alerts, [])
        self.assertEqual(self.agent.call("GET", "/health")[1]["busy"], False)

    def test_health_names_the_job_that_holds_the_browser_and_a_second_call_is_refused(self):
        thread, _ = self.run_slow()
        time.sleep(0.15)
        status, health = self.agent.call("GET", "/health")
        self.assertEqual((status, health["busy"], health["job"]), (200, True, "/api/slow"))
        self.assertEqual(self.agent.call("POST", "/api/slow")[0], 409)
        self.release.set()
        thread.join(5)

    def test_a_failing_alert_never_breaks_the_job(self):
        self.release.set()
        with mock.patch.object(server, "worker", side_effect=OSError("worker down")):
            server.overdue("/api/slow")  # must not raise on the timer thread


if __name__ == "__main__":
    unittest.main()
