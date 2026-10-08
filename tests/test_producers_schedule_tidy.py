"""Producers lane, 2026-10-08: the three paused pg_cron jobs.

- fantasycalc-drift.yml and weekly-dashboard-load.yml are manual-only: no
  GitHub schedule, no pg_cron job, and no step that records a monitored check
  whose check_config row the migration deletes (a record against a missing row
  is a 409 and fails the run -- seen on fantasycalc-weekly-save 2026-10-06).
- player-trace-rebuild.yml is re-enabled daily through pg_cron only.
Each rule is negative-tested against a simulated broken state.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WF = ROOT / ".github" / "workflows"
SQL = (ROOT / "supabase/migrations/producers_schedule_tidy_20261008.sql").read_text()
MANIFEST = json.loads((ROOT / "config/monitoring_coverage.json").read_text())

RETIRED = {
    "fantasycalc-drift.yml": ("trigger-fantasycalc-drift-live", "fantasycalc_native_drift"),
    "weekly-dashboard-load.yml": ("weekly-dashboard-load-live", "weekly_dashboard_load"),
}


def retired_problems(name, text, sql, manifest):
    job, check = RETIRED[name]
    out = []
    if re.search(r"^\s*schedule:\s*$", text, re.M):
        out.append(f"{name}: still has a GitHub schedule")
    if re.search(r'"p_check_id":\s*"%s"|--check-id %s\b' % (check, check), text):
        out.append(f"{name}: still records retired check {check}")
    if f"jobname = '{job}'" not in sql or "cron.unschedule" not in sql:
        out.append(f"migration does not unschedule {job}")
    if not re.search(r"delete from monitoring\.check_config\s+where check_id in \([^)]*'%s'" % check, sql):
        out.append(f"migration leaves check row {check}")
    listed = {r["check_id"] for p in manifest["pipelines"] for r in p["records"]}
    if check in listed:
        out.append(f"manifest still lists {check}")
    if name not in manifest["unmonitored_workflows"]:
        out.append(f"manifest does not explain manual-only {name}")
    return out


def trace_problems(text, sql):
    out = []
    if re.search(r"^\s*schedule:\s*$", text, re.M):
        out.append("player-trace: GitHub schedule alongside pg_cron")
    if not re.search(r"cron\.alter_job\(jobid, schedule := '47 12 \* \* \*', active := true\)\s+"
                     r"from cron\.job where jobname = 'trigger-player-trace-live'", sql):
        out.append("player-trace pg_cron job not re-enabled daily")
    if "--check-id player_trace_rebuild" not in text:
        out.append("player-trace no longer records its check")
    return out


class RetiredJobsTest(unittest.TestCase):
    def test_real_state_is_clean(self):
        for name in RETIRED:
            self.assertEqual(retired_problems(name, (WF / name).read_text(), SQL, MANIFEST), [])
        self.assertEqual(trace_problems((WF / "player-trace-rebuild.yml").read_text(), SQL), [])

    def test_schedule_left_in_is_caught(self):
        text = (WF / "weekly-dashboard-load.yml").read_text().replace(
            "on:\n  workflow_dispatch:", "on:\n  schedule:\n    - cron: '7 16 * * *'\n  workflow_dispatch:", 1)
        self.assertIn("weekly-dashboard-load.yml: still has a GitHub schedule",
                      retired_problems("weekly-dashboard-load.yml", text, SQL, MANIFEST))

    def test_record_step_left_in_is_caught(self):
        text = (WF / "fantasycalc-drift.yml").read_text() + (
            '\n          sbclient.rpc("monitoring_record_observation", {"p_check_id": "fantasycalc_native_drift"})\n')
        self.assertTrue(any("records retired check" in p for p in
                            retired_problems("fantasycalc-drift.yml", text, SQL, MANIFEST)))

    def test_check_row_left_is_caught(self):
        sql = SQL.replace("delete from monitoring.check_config", "-- (kept)")
        self.assertTrue(any("leaves check row" in p for p in
                            retired_problems("fantasycalc-drift.yml", (WF / "fantasycalc-drift.yml").read_text(), sql, MANIFEST)))

    def test_trace_left_paused_is_caught(self):
        sql = SQL.replace("active := true", "active := false")
        self.assertIn("player-trace pg_cron job not re-enabled daily",
                      trace_problems((WF / "player-trace-rebuild.yml").read_text(), sql))


if __name__ == "__main__":
    unittest.main()
