"""trade-chart-ingest.yml (CBS + USA Today, moved off Muse 2026-10-06).

Rules this pins, each negative-tested against a simulated broken state:
  - no GitHub `schedule:` -- Supabase pg_cron `trade-chart-ingest-live` is the
    single scheduler owner (ops-ownership-001);
  - dry mode never writes: the real "Resolve mode" + "Ingest" step scripts are
    executed with a fake python3 that records its argv, and every non-write
    trigger must pass --dry-run; the monitored-check step runs only in write
    mode;
  - a USA Today sitemap outage is a loud failure, never a quiet "article not
    published yet" exit 0 (the 2026-10-06 CI dry run reported "not published
    yet" on a sitemap 404);
  - CBS: a CI runner has no Muse-style local fingerprint state, so a re-run on
    unchanged same-week content must skip the write (DB comparison), not
    re-upsert and bump pulled_at every day.
"""
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import find_step, script_of  # noqa: E402
from tests.test_cbs_usatoday_recurring import (  # noqa: E402
    CBS_URL_W2, USAT_URL_W2, FakeDb, WrapperHarness, _fake_build,
    ingest_cbs, ingest_common, ingest_usat, pull_usatoday,
)

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/trade-chart-ingest.yml").read_text()
MIGRATION = (ROOT / "supabase/migrations/ingest_ci_pg_cron.sql").read_text()
RECORD = "Record the monitored check"
RECORD_IF = "steps.cfg.outputs.mode == 'write'"


def static_problems(text):
    problems = []
    if re.search(r"^\s*schedule:\s*$", text, re.M):
        problems.append("GitHub schedule present: pg_cron must be the only scheduler owner")
    block = find_step(text, RECORD)
    if block is None or RECORD_IF not in block:
        problems.append("monitored check must be recorded only in write mode")
    return problems


def render(script, ctx):
    """Substitute the ${{ ... }} expressions the two steps use."""
    def sub(m):
        return ctx.get(m.group(1).strip(), "")
    return re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", sub, script)


def ingest_argv(text, ref_name, inputs=None, source="cbs"):
    """Run the real Resolve-mode then Ingest scripts; return the argv the
    ingest script was invoked with (None if it was not invoked)."""
    inputs = inputs or {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out = td / "out.txt"
        out.write_text("")
        ctx = {"matrix.source": source}
        for k in ("mode", "source", "week"):
            ctx[f"github.event.inputs.{k}"] = inputs.get(k, "")
        env = {"PATH": f"{td / 'bin'}:/usr/bin:/bin", "HOME": str(td),
               "GITHUB_REF_NAME": ref_name, "GITHUB_OUTPUT": str(out)}
        cfg = script_of(find_step(text, "Resolve mode"))
        r = subprocess.run(["bash", "-e", "-c", render(cfg, ctx)], cwd=td, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        outs = dict(line.split("=", 1) for line in out.read_text().split() if "=" in line)
        if outs.get("run") != "true":
            return None
        ctx["steps.cfg.outputs.mode"] = outs["mode"]
        (td / "bin").mkdir()
        fake = td / "bin" / "python3"
        fake.write_text(f'#!/bin/bash\necho "$@" > {td}/argv\necho "[fake] ok"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        r = subprocess.run(["bash", "-e", "-c", render(script_of(find_step(text, "Ingest")), ctx)],
                           cwd=td, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr + r.stdout
        return (td / "argv").read_text().split()


DRY_TRIGGERS = [
    ("ingest/dry-7", {}),
    ("main", {"mode": "dry"}),
    ("main", {}),               # dispatch with no inputs
    ("main", {"mode": "WRITE"}),  # anything but the exact word stays dry
]


class WorkflowTest(unittest.TestCase):
    def test_real_workflow(self):
        self.assertEqual([], static_problems(WORKFLOW))
        for ref, inputs in DRY_TRIGGERS:
            argv = ingest_argv(WORKFLOW, ref, inputs)
            self.assertIn("--dry-run", argv, (ref, inputs))
        for ref, inputs in (("ingest/write-1", {}), ("main", {"mode": "write"})):
            argv = ingest_argv(WORKFLOW, ref, inputs)
            self.assertNotIn("--dry-run", argv, (ref, inputs))
            self.assertEqual(argv[0], "ops/watchdog/ingest_cbs.py")
        self.assertEqual(["ops/watchdog/ingest_cbs.py", "--dry-run", "--week", "5"],
                         ingest_argv(WORKFLOW, "main", {"week": "5"}))
        self.assertIsNone(ingest_argv(WORKFLOW, "main", {"source": "usatoday"}, source="cbs"))

    def test_a_github_schedule_is_caught(self):
        mutated = WORKFLOW.replace("on:\n  workflow_dispatch:",
                                   'on:\n  schedule:\n    - cron: "7 12 * * *"\n  workflow_dispatch:', 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertTrue(any("schedule" in p for p in static_problems(mutated)))

    def test_dropping_the_dry_run_flag_is_caught(self):
        mutated = WORKFLOW.replace('|| args="--dry-run"', '|| args=""', 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertNotIn("--dry-run", ingest_argv(mutated, "ingest/dry-7"))

    def test_write_by_default_is_caught(self):
        mutated = WORKFLOW.replace("mode=dry\n", "mode=write\n", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertNotIn("--dry-run", ingest_argv(mutated, "main", {}))

    def test_recording_in_dry_mode_is_caught(self):
        mutated = WORKFLOW.replace(" && " + RECORD_IF, "", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertIn("monitored check must be recorded only in write mode", static_problems(mutated))

    def test_migration_dispatches_this_workflow_in_write_mode(self):
        self.assertIn("'trade-chart-ingest-live'", MIGRATION)
        self.assertIn("'7 12 * * *'", MIGRATION)
        self.assertIn("dispatch_gha_workflow('trade-chart-ingest.yml', '{\"mode\": \"write\"}'::jsonb)", MIGRATION)
        # The workflow records "<matrix.source>_trade_chart_ingest"; each
        # matrix source must have its check_config row in the migration.
        self.assertIn('"p_check_id": "${{ matrix.source }}_trade_chart_ingest"', WORKFLOW)
        self.assertIn("source: [cbs, usatoday]", WORKFLOW)
        for source in ("cbs", "usatoday"):
            self.assertIn(f"'{source}_trade_chart_ingest'", MIGRATION)


class UsatSitemapOutageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def _run_with_sitemap_404(self):
        def discover(week):
            # The real discovery path, with the sitemap fetch returning 404.
            return pull_usatoday.discover_url(week, fetch_fn=lambda u: (404, "<html>nf</html>"))
        h = WrapperHarness(self, ingest_usat, USAT_URL_W2,
                           ("std", "half", "full"), "usatoday", "as_published")
        return h, h.run(week=2, tmp=self.tmp, discover_fn=discover)

    def test_sitemap_outage_is_loud(self):
        with self.assertRaises(ingest_common.IngestError) as ctx:
            self._run_with_sitemap_404()
        self.assertIn("discovery source unavailable", str(ctx.exception))

    def test_broken_state_quiet_skip_is_caught(self):
        # Simulated regression: sitemap failures treated as "not published".
        orig = pull_usatoday.SitemapUnavailable.quiet
        pull_usatoday.SitemapUnavailable.quiet = True
        try:
            _h, res = self._run_with_sitemap_404()
        finally:
            pull_usatoday.SitemapUnavailable.quiet = orig
        self.assertEqual(res["status"], "not_published")  # what the guard above rejects

    def test_missing_article_is_still_a_quiet_skip(self):
        sitemap = '<?xml version="1.0"?><urlset><url><loc>https://x/other</loc></url></urlset>'
        h = WrapperHarness(self, ingest_usat, USAT_URL_W2,
                           ("std", "half", "full"), "usatoday", "as_published")
        res = h.run(week=2, tmp=self.tmp,
                    discover_fn=lambda w: pull_usatoday.discover_url(w, fetch_fn=lambda u: (200, sitemap)))
        self.assertEqual(res["status"], "not_published")

    def test_bot_wall_is_named(self):
        with self.assertRaises(RuntimeError) as ctx:
            pull_usatoday.pull(USAT_URL_W2, fetch_fn=lambda u: (402, "Access Restricted"))
        self.assertIn("SOURCE_BLOCKED", str(ctx.exception))


class CbsStatelessRerunTest(unittest.TestCase):
    SCORINGS = ("standard", "half_ppr", "ppr")

    def _harness_with_db_week(self, mutate=None):
        h = WrapperHarness(self, ingest_cbs, CBS_URL_W2, self.SCORINGS, "cbs", "as_published")
        clean, _, _, _ = _fake_build(self.SCORINGS)("p", 2, None)
        native = {(r["player_key"], r["scoring"]): r["native_value"] for r in clean}
        if mutate:
            mutate(native)
        h.fakedb.set_native("cbs", "as_published", 2026, 2, native)
        for s in self.SCORINGS:
            h.fakedb.set("cbs", "as_published", s, 2026, 2, 2)
        return h

    def test_unchanged_week_in_db_skips_write_on_fresh_runner(self):
        h = self._harness_with_db_week()
        res = h.run(week=2, tmp=Path(tempfile.mkdtemp()))  # empty state dir = CI runner
        self.assertEqual(res["status"], "same_week_unchanged")
        self.assertEqual(h.saved, [])

    def test_changed_week_still_writes(self):
        def bump(native):
            k = next(iter(native))
            native[k] += 1.0
        h = self._harness_with_db_week(bump)
        res = h.run(week=2, tmp=Path(tempfile.mkdtemp()))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(h.saved), 1)

    def test_broken_state_without_guard_rewrites(self):
        # Simulated regression: guard removed -> a stateless re-run re-writes.
        orig = ingest_cbs.CFG.pop("pre_write_guard")
        try:
            h = self._harness_with_db_week()
            res = h.run(week=2, tmp=Path(tempfile.mkdtemp()))
        finally:
            ingest_cbs.CFG["pre_write_guard"] = orig
        self.assertEqual(res["status"], "ok")
        self.assertEqual(len(h.saved), 1)  # what the guard above prevents


if __name__ == "__main__":
    unittest.main()
