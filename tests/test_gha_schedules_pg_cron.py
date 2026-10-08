"""GAP-GHA-SCHEDULES (JEG-437): pages.yml and sleeper-identity-refresh.yml are
scheduled by Supabase pg_cron, not GitHub. (weekly-dashboard-load.yml was the
third; the producers lane made it manual-only on 2026-10-08.)

Pins, per workflow: no GitHub `schedule:` (a second scheduler fires twice and
GitHub's cron is the one that skips), `workflow_dispatch:` present (pg_cron can
only dispatch what accepts it), a pg_cron job in supabase/migrations that
dispatches exactly that workflow on the expected cron, and the manifest naming
that job. Each rule is negative-tested against a mutated copy of the real file.
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATION = (ROOT / "supabase/migrations/gha_schedules_pg_cron.sql").read_text(encoding="utf-8")
MANIFEST = json.loads((ROOT / "config/monitoring_coverage.json").read_text(encoding="utf-8"))

EXPECTED = {
    "pages.yml": ("pages-deploy-live", "30 11 * * *"),
    "sleeper-identity-refresh.yml": ("sleeper-identity-refresh-live", "17 9 * * 2,4"),
}


def workflow_text(name):
    return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")


def problems(workflows, migration, manifest):
    out = []
    pipes = {p["workflow"]: p for p in manifest["pipelines"]}
    for wf, (job, cron) in EXPECTED.items():
        text = workflows[wf]
        if re.search(r"^\s*schedule:\s*$", text, re.M):
            out.append(f"{wf}: still has a GitHub schedule: (pg_cron {job} owns it)")
        if not re.search(r"^\s*workflow_dispatch:", text, re.M):
            out.append(f"{wf}: no workflow_dispatch: trigger, pg_cron cannot dispatch it")
        pat = (rf"cron\.schedule\(\s*'{re.escape(job)}',\s*'{re.escape(cron)}',\s*"
               rf"\$\$SELECT public\.dispatch_gha_workflow\('{re.escape(wf)}'")
        if not re.search(pat, migration):
            out.append(f"{wf}: migration does not schedule {job} at '{cron}' dispatching {wf}")
        p = pipes.get(wf, {})
        if p.get("scheduler") != "pg_cron" or p.get("pg_cron_job") != job:
            out.append(f"{wf}: manifest does not name pg_cron job {job}")
    return out


def real_workflows():
    return {wf: workflow_text(wf) for wf in EXPECTED}


class GhaSchedulesTest(unittest.TestCase):
    def test_real_repo_is_clean(self):
        self.assertEqual([], problems(real_workflows(), MIGRATION, MANIFEST))

    def test_a_github_schedule_is_caught(self):
        for wf in EXPECTED:
            wfs = real_workflows()
            wfs[wf] = wfs[wf].replace("on:\n", 'on:\n  schedule:\n    - cron: "0 1 * * *"\n', 1)
            self.assertTrue(any(wf in p and "GitHub schedule" in p
                                for p in problems(wfs, MIGRATION, MANIFEST)), wf)

    def test_missing_workflow_dispatch_is_caught(self):
        wfs = real_workflows()
        wfs["pages.yml"] = wfs["pages.yml"].replace("workflow_dispatch:", "xworkflow_dispatch:")
        self.assertTrue(any("no workflow_dispatch" in p for p in problems(wfs, MIGRATION, MANIFEST)))

    def test_missing_or_wrong_cron_job_is_caught(self):
        for job, cron in EXPECTED.values():
            mutated = MIGRATION.replace(f"'{job}'", "'other-job'")
            self.assertTrue(any(job in p for p in problems(real_workflows(), mutated, MANIFEST)), job)
            mutated = MIGRATION.replace(f"'{cron}'", "'0 0 * * *'")
            self.assertTrue(any(cron in p for p in problems(real_workflows(), mutated, MANIFEST)), cron)

    def test_manifest_naming_another_scheduler_is_caught(self):
        m = json.loads(json.dumps(MANIFEST))
        for p in m["pipelines"]:
            if p["workflow"] == "pages.yml":
                p["scheduler"], p["pg_cron_job"] = "github_schedule", None
        self.assertTrue(any("manifest does not name" in p
                            for p in problems(real_workflows(), MIGRATION, m)))


if __name__ == "__main__":
    unittest.main()
