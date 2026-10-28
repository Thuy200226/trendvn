"""The generated n8n workflows: every step that continues on error reports to the worker, and n8n waits longer than the agent's own limits."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services" / "agent" / "src"))
from trendvn_agent.limits import JOB_SECONDS, N8N_MARGIN_SECONDS  # noqa: E402

WORKFLOWS = ROOT / "n8n" / "workflows"
SCHEDULED = ("trendvn01daily", "trendvn02publish", "trendvn03daily")


def load(wid):
    return json.loads((WORKFLOWS / (wid + ".json")).read_text())


def http_nodes(workflow):
    return [n for n in workflow["nodes"] if n["type"].endswith("httpRequest")]


class ErrorReportingTests(unittest.TestCase):
    def test_every_scheduled_step_has_an_error_output_that_reaches_an_alert_node(self):
        for wid in SCHEDULED:
            workflow = load(wid)
            by_name = {n["name"]: n for n in workflow["nodes"]}
            steps = [n for n in http_nodes(workflow) if n.get("onError") == "continueErrorOutput"]
            self.assertTrue(steps, wid)
            for step in steps:
                outputs = workflow["connections"][step["name"]]["main"]
                self.assertEqual(len(outputs), 2, "%s: %s has no error output wired" % (wid, step["name"]))
                alerts = [by_name[c["node"]] for c in outputs[1] if by_name[c["node"]]["parameters"]["url"].endswith("/api/alert")]
                self.assertEqual(len(alerts), 1, "%s: %s does not report its failure" % (wid, step["name"]))

    def test_an_alert_node_cannot_break_the_workflow_it_reports_on(self):
        for wid in SCHEDULED:
            for node in http_nodes(load(wid)):
                if node["parameters"]["url"].endswith("/api/alert"):
                    self.assertEqual(node["onError"], "continueRegularOutput")

    def test_a_failed_step_still_lets_the_next_one_run(self):
        """As before the change: a failing session check must not stop the collection."""
        workflow = load("trendvn01daily")
        steps = [n for n in workflow["nodes"] if n.get("onError") == "continueErrorOutput"]
        for step, following in zip(steps, steps[1:]):
            error_targets = {c["node"] for c in workflow["connections"][step["name"]]["main"][1]}
            self.assertIn(following["name"], error_targets, step["name"])

    def test_n8n_waits_longer_than_the_agent_allows_a_job(self):
        for wid in SCHEDULED:
            for node in http_nodes(load(wid)):
                url = node["parameters"]["url"]
                for path, seconds in JOB_SECONDS.items():
                    if url.endswith(path):
                        self.assertGreaterEqual(node["parameters"]["options"]["timeout"], (seconds + N8N_MARGIN_SECONDS) * 1000, url)


if __name__ == "__main__":
    unittest.main()
