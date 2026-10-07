"""Monitoring coverage guards (2026-10-07 audit).

"Working and monitored" means, for every scheduled pipeline: a check row, an
observation recorded on success AND failure, the evaluator flagging a run that
never happens, and the result on the served monitor. These tests pin each link
that can be checked offline; each is negative-tested against the broken state
it names (a mutated workflow, manifest, or summary).

  - config/monitoring_coverage.json is the single list; every workflow file is
    in it (monitored or explicitly unmonitored with a reason);
  - every monitored workflow records through a step that runs `always()`;
  - a pg_cron-owned workflow has no GitHub `schedule:` (one scheduler owner);
  - every check id has a check_config insert in supabase/migrations;
  - the evaluator migration counts a never-observed check as missed;
  - the dispatcher is not executable by anon;
  - the dashboard banner is fail-closed: unreadable, malformed or stale is red.
"""
import json
import re
import subprocess
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipelines import audit_monitoring_coverage as audit
from pipelines import build_monitoring_summary as bms
from pipelines import record_monitor_check as rec

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "config" / "monitoring_coverage.json").read_text())
WORKFLOWS = ROOT / ".github" / "workflows"
MIGRATIONS = ROOT / "supabase" / "migrations"
DASHBOARD = (ROOT / "modules" / "dashboard.html").read_text()
SURFACES = json.loads((ROOT / "modules" / "surfaces.json").read_text())["surfaces"]
STEP_NAME = "Record monitored check"


def has_schedule(text):
    return re.search(r"^\s*schedule:\s*$", text, re.M) is not None


def step_block(text, name):
    m = re.search(rf"^(\s*)-\s+name:\s*{re.escape(name)}\s*$", text, re.M)
    if not m:
        return None
    indent = len(m.group(1))
    rest = text[m.end():].split("\n")
    out = []
    for line in rest:
        if line.strip() and (len(line) - len(line.lstrip())) <= indent and line.lstrip().startswith("-"):
            break
        if line.strip() and (len(line) - len(line.lstrip())) < indent:
            break
        out.append(line)
    return "\n".join(out)


def coverage_problems(manifest, workflow_texts, read=lambda p: (ROOT / p).read_text(), migrations_sql=None):
    """workflow_texts: {filename: text}. Returns a list of problems."""
    problems = []
    listed = {p["workflow"] for p in manifest["pipelines"] if not p.get("workflow_missing_on_main")}
    unmonitored = set(manifest["unmonitored_workflows"])
    for wf in sorted(workflow_texts):
        if wf not in listed and wf not in unmonitored:
            problems.append(f"{wf}: workflow is not in config/monitoring_coverage.json")
    for wf in sorted((listed | unmonitored) - set(workflow_texts)):
        problems.append(f"{wf}: listed in the manifest but not in .github/workflows")
    for p in manifest["pipelines"]:
        wf = p["workflow"]
        if p.get("workflow_missing_on_main"):
            if wf in workflow_texts:
                problems.append(f"{wf}: now exists on main, drop workflow_missing_on_main from the manifest")
            continue
        text = workflow_texts.get(wf, "")
        if p["scheduler"] == "pg_cron" and has_schedule(text):
            problems.append(f"{wf}: has a GitHub schedule but pg_cron {p['pg_cron_job']} owns it")
        if p["scheduler"] == "github_schedule" and not has_schedule(text):
            problems.append(f"{wf}: manifest says GitHub schedule but the workflow has none")
        for r in p["records"]:
            body = read(r["file"]) if r["file"] else ""
            if not r["contains"] or r["contains"] not in body:
                problems.append(f"{wf}: no recording of check {r['check_id']} (expected {r['contains']!r} in {r['file']})")
            if r["file"] == f".github/workflows/{wf}" and "record_monitor_check.py" in body:
                block = step_block(body, STEP_NAME)
                if block is None or "always()" not in block:
                    problems.append(f"{wf}: the record step must run if: always() so a failed run is recorded")
    if migrations_sql is not None:
        ids = [r["check_id"] for p in manifest["pipelines"] for r in p["records"]] + \
              [j["check_id"] for j in manifest["pg_cron_sql_jobs"]]
        for c in ids:
            if f"'{c}'" not in migrations_sql:
                problems.append(f"{c}: no check_config insert in supabase/migrations")
    return problems


def load_workflows():
    return {p.name: p.read_text() for p in WORKFLOWS.glob("*.yml")}


def all_migrations_sql():
    return "\n".join(p.read_text() for p in sorted(MIGRATIONS.glob("*.sql")))


class CoverageManifestTest(unittest.TestCase):
    def test_real_repo_is_fully_covered(self):
        self.assertEqual([], coverage_problems(MANIFEST, load_workflows(), migrations_sql=all_migrations_sql()))

    def test_unlisted_workflow_is_caught(self):
        wfs = load_workflows()
        wfs["brand-new-job.yml"] = "name: x\non:\n  workflow_dispatch:\n"
        self.assertTrue(any("brand-new-job.yml" in p and "not in config" in p
                            for p in coverage_problems(MANIFEST, wfs)))

    def test_record_step_that_only_runs_on_success_is_caught(self):
        wfs = load_workflows()
        wfs["rebuild-chain.yml"] = wfs["rebuild-chain.yml"].replace(
            "if: always() && github.ref == 'refs/heads/main' && (github.event_name == 'workflow_dispatch' || github.event_name == 'schedule')",
            "if: success() && github.ref == 'refs/heads/main'", 1)
        mutated = coverage_problems(
            MANIFEST, wfs,
            read=lambda p: wfs[Path(p).name] if p.startswith(".github/") else (ROOT / p).read_text())
        self.assertTrue(any("rebuild-chain.yml" in p and "always()" in p for p in mutated), mutated)

    def test_workflow_that_never_records_is_caught(self):
        wfs = load_workflows()
        wfs["espn-supabase-sync.yml"] = wfs["espn-supabase-sync.yml"].replace("--check-id espn_supabase_sync", "--check-id some_other_check", 1)
        mutated = coverage_problems(
            MANIFEST, wfs,
            read=lambda p: wfs[Path(p).name] if p.startswith(".github/") else (ROOT / p).read_text())
        self.assertTrue(any("espn_supabase_sync" in p for p in mutated), mutated)

    def test_double_scheduler_owner_is_caught(self):
        wfs = load_workflows()
        wfs["live-page-synthetic.yml"] = wfs["live-page-synthetic.yml"].replace(
            "on:\n  workflow_dispatch:", 'on:\n  schedule:\n    - cron: "0 6 * * *"\n  workflow_dispatch:', 1)
        self.assertTrue(any("live-page-synthetic.yml" in p and "GitHub schedule" in p
                            for p in coverage_problems(MANIFEST, wfs)))

    def test_check_without_a_migration_row_is_caught(self):
        sql = all_migrations_sql().replace("'rebuild_chain'", "'renamed'")
        self.assertTrue(any("rebuild_chain" in p for p in coverage_problems(MANIFEST, load_workflows(), migrations_sql=sql)))

    def test_razzball_gap_is_declared_not_hidden(self):
        raz = [p for p in MANIFEST["pipelines"] if p["workflow"] == "razzball-supabase-sync.yml"][0]
        self.assertTrue(raz["workflow_missing_on_main"] and raz.get("gap"))
        self.assertNotIn("razzball-supabase-sync.yml", load_workflows())


class MigrationTest(unittest.TestCase):
    SQL = (MIGRATIONS / "monitoring_coverage_20261007.sql").read_text()

    def test_dispatcher_is_not_executable_by_anon(self):
        self.assertRegex(self.SQL, r"revoke execute on function public\.dispatch_gha_workflow\(text, jsonb\)\s+from public, anon, authenticated")

    def test_evaluator_counts_never_observed_checks_as_missed(self):
        self.assertIn("coalesce(v_created, p_now) + make_interval(secs => p_cadence_seconds)", self.SQL)
        # the pre-fix line made a never-observed check 'unknown' forever
        self.assertNotRegex(self.SQL, r"if v_latest_obs\.run_at is null then\s*v_expected_next := p_now;")

    def test_summary_is_service_role_only(self):
        self.assertIn("revoke execute on function public.monitoring_summary() from public, anon, authenticated;", self.SQL)
        self.assertIn("grant execute on function public.monitoring_summary() to service_role;", self.SQL)


class RecorderTest(unittest.TestCase):
    def test_failure_is_recorded_as_not_ok(self):
        p = rec.build_payload("rebuild_chain", "rebuild-chain.yml", "failure")
        self.assertIs(p["p_ok"], False)
        self.assertEqual("WORKFLOW_FAILED", p["p_error_code"])

    def test_success_is_recorded_ok(self):
        self.assertIs(rec.build_payload("c", "w.yml", "success")["p_ok"], True)

    def test_cancelled_and_skipped_record_nothing(self):
        self.assertIsNone(rec.build_payload("c", "w.yml", "cancelled"))
        self.assertIsNone(rec.build_payload("c", "w.yml", "skipped"))

    def test_guard_catches_a_recorder_that_reports_failure_as_ok(self):
        saved = dict(rec.OUTCOMES)
        try:
            rec.OUTCOMES["failure"] = True  # the broken state: a red run recorded green
            self.assertIs(rec.build_payload("c", "w.yml", "failure")["p_ok"], True)
        finally:
            rec.OUTCOMES.clear()
            rec.OUTCOMES.update(saved)
        self.assertIs(rec.build_payload("c", "w.yml", "failure")["p_ok"], False)


def good_summary(now=None, overall="green"):
    now = now or datetime.now(timezone.utc)
    return {"schema": bms.SCHEMA, "generated_at": now.isoformat(), "overall": overall,
            "headline": "x", "counts": {}, "cron_jobs": [],
            "checks": [{"check_id": "a", "status": "green"}]}


class SummaryBuilderTest(unittest.TestCase):
    def test_unreachable_supabase_is_red_never_green(self):
        def boom():
            raise OSError("proxy 403")
        snap = bms.build(boom)
        self.assertEqual("red", snap["overall"])
        self.assertIn("proxy 403", snap["read_error"])

    def test_malformed_summary_is_red(self):
        for bad in (None, [], {"schema": "other"}, dict(good_summary(), checks=[]), dict(good_summary(), overall="blue")):
            self.assertEqual("red", bms.build(lambda b=bad: b)["overall"], bad)

    def test_valid_summary_passes_through_unchanged(self):
        s = good_summary(overall="yellow")
        self.assertEqual(s, bms.build(lambda: s))


class CoverageAuditTest(unittest.TestCase):
    def summary(self):
        checks, jobs = audit.manifest_sets(MANIFEST)
        return {"checks": [{"check_id": c} for c in checks],
                "cron_jobs": [{"jobname": j, "active": True} for j in jobs]}

    def test_full_coverage_has_no_gaps(self):
        self.assertEqual([], audit.audit(MANIFEST, self.summary()))

    def test_unmapped_cron_job_is_caught(self):
        s = self.summary()
        s["cron_jobs"].append({"jobname": "some-new-job", "active": True})
        self.assertTrue(any("some-new-job" in g for g in audit.audit(MANIFEST, s)))

    def test_missing_check_row_is_caught(self):
        s = self.summary()
        s["checks"] = [c for c in s["checks"] if c["check_id"] != "rebuild_chain"]
        self.assertTrue(any("rebuild_chain" in g for g in audit.audit(MANIFEST, s)))

    def test_unmanifested_check_row_is_caught(self):
        s = self.summary()
        s["checks"].append({"check_id": "orphan"})
        self.assertTrue(any("orphan" in g for g in audit.audit(MANIFEST, s)))


def run_node(js):
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=30)
    if out.returncode != 0:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


def banner_overalls(fn_source, cases, now_ms):
    js = fn_source + "\nconst cases = " + json.dumps(cases) + ";\n" \
         "console.log(JSON.stringify(cases.map(c => sysEvaluate(c, " + str(now_ms) + ").overall)));"
    return run_node(js)


def banner_source(html=DASHBOARD):
    m = re.search(r"// SYS-STATUS-BEGIN\n(.*?)// SYS-STATUS-END", html, re.S)
    assert m, "banner function markers missing"
    return m.group(1)


class BannerFailClosedTest(unittest.TestCase):
    NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)

    def cases(self):
        now = self.NOW
        fresh = good_summary(now - timedelta(minutes=10), "green")
        return [
            ("fresh green", fresh, "green"),
            ("fresh yellow", good_summary(now - timedelta(minutes=10), "yellow"), "yellow"),
            ("fresh red", good_summary(now - timedelta(minutes=10), "red"), "red"),
            ("stale green", good_summary(now - timedelta(minutes=90), "green"), "red"),
            ("future timestamp", good_summary(now + timedelta(minutes=30), "green"), "red"),
            ("null", None, "red"),
            ("read error", {"read_error": "HTTP 404"}, "red"),
            ("empty checks", dict(fresh, checks=[]), "red"),
            ("wrong schema", dict(fresh, schema="x"), "red"),
            ("bad overall", dict(fresh, overall="ok"), "red"),
            ("bad timestamp", dict(fresh, generated_at="soon"), "red"),
        ]

    def test_every_unreadable_or_stale_input_is_red(self):
        cases = self.cases()
        got = banner_overalls(banner_source(), [c[1] for c in cases], int(self.NOW.timestamp() * 1000))
        for (name, _, want), have in zip(cases, got):
            self.assertEqual(want, have, name)

    def test_guard_catches_a_banner_that_paints_stale_data_green(self):
        mutated = banner_source().replace("if(age > SYS_STALE_MIN)", "if(false)", 1)
        self.assertNotEqual(banner_source(), mutated)
        cases = self.cases()
        got = banner_overalls(mutated, [c[1] for c in cases], int(self.NOW.timestamp() * 1000))
        stale = [i for i, c in enumerate(cases) if c[0] == "stale green"][0]
        self.assertEqual("green", got[stale], "mutation should have produced the false green this guard exists to catch")
        self.assertNotEqual([c[2] for c in cases], got)

    def test_dashboard_reads_the_published_summary(self):
        self.assertIn('fetch("monitoring-summary.json"', DASHBOARD)
        self.assertIn("Is everything working?", DASHBOARD)

    def test_summary_surface_is_registered(self):
        s = [x for x in SURFACES if x["id"] == "monitoring-summary"]
        self.assertEqual(1, len(s))
        self.assertTrue(s[0]["required"])
        self.assertEqual("modules/monitoring-summary.json", s[0]["url"])


if __name__ == "__main__":
    unittest.main()
