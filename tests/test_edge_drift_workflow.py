"""JEG-1049: .github/workflows/edge-drift-check.yml runs the edge drift checker daily and on demand, read-only.

Pins the triggers (schedule + workflow_dispatch), that the job can only read (contents: read, no secrets,
no deploy or Supabase CLI), and runs the step's real script against unreachable local endpoints: the run
must keep the checker's exit 2 and write a "Could not compare" summary, never a healthy one.

Run: python3 -m unittest tests.test_edge_drift_workflow (also a line of make test-unit-modules).
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github/workflows/edge-drift-check.yml"
STEP = "Compare deployed edge functions with main"


def load():
    text = WORKFLOW_PATH.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    # PyYAML reads the bare key `on` as True.
    triggers = doc.get("on", doc.get(True))
    return text, doc, triggers


class EdgeDriftWorkflowTests(unittest.TestCase):
    def test_runs_daily_and_on_demand(self):
        _, _, triggers = load()
        self.assertIn("workflow_dispatch", triggers)
        crons = [entry["cron"] for entry in triggers["schedule"]]
        self.assertEqual(len(crons), 1)
        self.assertEqual(len(crons[0].split()), 5)
        self.assertTrue(crons[0].endswith("* * *"), f"expected a daily cron, got {crons[0]}")
        self.assertEqual(set(triggers), {"schedule", "workflow_dispatch"})

    def test_job_is_read_only(self):
        text, doc, _ = load()
        self.assertEqual(doc["permissions"], {"contents": "read"})
        for job in doc["jobs"].values():
            self.assertNotIn("permissions", job)
        self.assertNotIn("secrets.", text)
        for forbidden in ("supabase ", "functions deploy", "git push", "SUPABASE_ACCESS_TOKEN", "SERVICE_ROLE"):
            self.assertNotIn(forbidden, text)
        run = self.step_script(doc)
        self.assertIn("tools/edge_drift_check.mjs", run)

    @unittest.skipIf(shutil.which("node") is None or shutil.which("bash") is None, "node or bash not installed")
    def test_unreachable_endpoints_keep_exit_2_and_say_so(self):
        _, doc, _ = load()
        run = self.step_script(doc)
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / "summary.md"
            env = dict(os.environ,
                       GITHUB_STEP_SUMMARY=str(summary),
                       # Port 9 (discard) is closed on a normal host: both sides are unreachable.
                       EDGE_MCP_URL="http://127.0.0.1:9/mcp",
                       EDGE_GET_VALUES_URL="http://127.0.0.1:9/get-values")
            out = subprocess.run(["bash", "-e", "-c", run], cwd=ROOT, env=env,
                                 capture_output=True, text=True, timeout=180)
            self.assertEqual(out.returncode, 2, out.stdout + out.stderr)
            text = summary.read_text(encoding="utf-8")
        self.assertIn("Could not compare", text)
        self.assertIn("(exit 2)", text)
        self.assertNotIn("In sync", text)
        self.assertIn("EDGE CHECK ERROR", text)
        # cwd is the repo root; the script must not leave its log behind there.
        self.assertFalse((ROOT / "drift.log").exists(), "step left drift.log in the checkout")

    @staticmethod
    def step_script(doc):
        for job in doc["jobs"].values():
            for step in job["steps"]:
                if step.get("name") == STEP:
                    return step["run"]
        raise AssertionError(f"step {STEP!r} not found")


if __name__ == "__main__":
    unittest.main()
