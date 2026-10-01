"""Regression: C9 Pages-deploy check must not red on a healthy in-flight deploy.

On 2026-10-01 ~08:38 UTC the checkpoint builder reported
"Last Pages deploy: in_progress/None. Deploy may have failed." (bad) while
the in-progress run was the routine 03:37 CDT 30-min health push's deploy --
healthy, not failed. The old logic judged runs[0] alone, so every push cycle
would false-red the monitor while its deploy was in flight.

The verdict is now judged from the most recent COMPLETED run; an
in_progress/queued latest run only annotates the reason. These tests prove
the new semantics AND prove they discriminate: test_old_logic_flags_inflight
replicates the pre-fix branch inline and asserts it returns bad for the same
fixture the new code calls ok -- so the suite would have caught the bug.
"""

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
sys.path.insert(0, str(PIPELINES))

import build_pipeline_checkpoints as bpc  # noqa: E402


def _iso(minutes_ago):
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _run(status, conclusion, minutes_ago):
    return {"id": 1, "status": status, "conclusion": conclusion,
            "updated_at": _iso(minutes_ago)}


def _old_logic(runs):
    """The pre-fix branch, verbatim semantics: judged runs[0] alone."""
    if runs:
        last_run = runs[0]
        run_status = last_run.get("status")
        run_conclusion = last_run.get("conclusion")
        run_updated = last_run.get("updated_at")
        if run_status != "completed" or run_conclusion != "success":
            return {"timestamp": run_updated, "status": "bad",
                    "reason": f"Last Pages deploy: {run_status}/{run_conclusion}. Deploy may have failed."}
    return {"status": "ok"}


class PagesDeployVerdictTest(unittest.TestCase):
    def inflight_fixture(self):
        # Exact 2026-10-01 shape: routine health-push deploy in flight,
        # previous completed deploy succeeded 30 min earlier.
        return [_run("in_progress", None, 1), _run("completed", "success", 30)]

    def test_inflight_deploy_with_healthy_history_is_ok(self):
        v = bpc.evaluate_pages_deploy(self.inflight_fixture())
        self.assertEqual("ok", v["status"], v["reason"])
        self.assertIn("in progress", v["reason"].lower())

    def test_old_logic_flags_inflight(self):
        # Discrimination proof: the pre-fix branch calls the same healthy
        # fixture bad, so this suite fails against the broken state.
        v = _old_logic(self.inflight_fixture())
        self.assertEqual("bad", v["status"])

    def test_inflight_after_failed_deploy_stays_bad(self):
        runs = [_run("in_progress", None, 1), _run("completed", "failure", 30)]
        v = bpc.evaluate_pages_deploy(runs)
        self.assertEqual("bad", v["status"], v["reason"])

    def test_completed_failure_is_bad(self):
        v = bpc.evaluate_pages_deploy([_run("completed", "failure", 10)])
        self.assertEqual("bad", v["status"], v["reason"])

    def test_completed_success_is_ok(self):
        v = bpc.evaluate_pages_deploy([_run("completed", "success", 60)])
        self.assertEqual("ok", v["status"], v["reason"])

    def test_stale_success_warns(self):
        v = bpc.evaluate_pages_deploy([_run("completed", "success", 3 * 24 * 60)])
        self.assertEqual("warn", v["status"], v["reason"])

    def test_no_runs_is_unk(self):
        v = bpc.evaluate_pages_deploy([])
        self.assertEqual("unk", v["status"])

    def test_inflight_only_is_unk_not_bad(self):
        # No completed run to judge: honest "unknown", never a failure claim.
        v = bpc.evaluate_pages_deploy([_run("in_progress", None, 1)])
        self.assertEqual("unk", v["status"], v["reason"])


if __name__ == "__main__":
    unittest.main()
