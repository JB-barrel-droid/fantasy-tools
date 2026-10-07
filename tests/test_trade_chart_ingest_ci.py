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


class UsatSlugPluralTest(unittest.TestCase):
    """Tests for USA Today slug regex accepting both singular and plural forms.

    Week 5+ USA Today articles use "trade-value-charts" (plural) while earlier
    weeks use "trade-value-chart" (singular). Discovery and week extraction
    must accept both forms to avoid silently falling back to stale articles.
    """

    def test_singular_url_extracts_week(self):
        """Test that singular 'trade-value-chart' URLs extract week correctly."""
        url = "https://example.com/fantasy-trade-value-chart-week-4-ros-rankings/article"
        self.assertEqual(pull_usatoday.extract_week_from_url(url), 4)

    def test_plural_url_extracts_week(self):
        """Test that plural 'trade-value-charts' URLs extract week correctly."""
        url = "https://example.com/fantasy-trade-value-charts-week-5-ros-rankings/article"
        self.assertEqual(pull_usatoday.extract_week_from_url(url), 5)

    def test_plural_week_5_discovered_in_sitemap(self):
        """Test that week 5 plural URL is discovered in sitemap."""
        sitemap = """<?xml version="1.0"?>
<urlset>
<url><loc>https://x.com/fantasy-trade-value-charts-week-5-ros-rankings/777/</loc></url>
<url><loc>https://x.com/other-article/</loc></url>
</urlset>"""
        def fake_fetch(url):
            return (200, sitemap)

        url = pull_usatoday.discover_url(week=5, fetch_fn=fake_fetch)
        self.assertIn("week-5", url)
        self.assertIn("charts", url)

    def test_singular_week_4_still_discovered(self):
        """Test that older singular URLs still work for discovery."""
        sitemap = """<?xml version="1.0"?>
<urlset>
<url><loc>https://x.com/fantasy-trade-value-chart-week-4-ros-rankings/666/</loc></url>
</urlset>"""
        def fake_fetch(url):
            return (200, sitemap)

        url = pull_usatoday.discover_url(week=4, fetch_fn=fake_fetch)
        self.assertIn("week-4", url)
        self.assertIn("chart", url)

    def test_broken_singular_only_regex_misses_plural(self):
        """Negative test: singular-only regex fails to discover plural URLs.

        This proves that the fix is necessary: a singular-only regex would
        silently miss week 5+ articles and fall back to stale week-4 data.
        """
        singular_only_re = re.compile(r"trade-value-chart-week-5-ros-rankings")
        plural_url = "https://x.com/fantasy-trade-value-charts-week-5-ros-rankings/777/"
        self.assertIsNone(singular_only_re.search(plural_url),
                         "Singular-only regex must NOT match plural URL (proves the bug)")


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


class UsatSourceBlockedFallbackTests(unittest.TestCase):
    """GAP-USAT-CI-BLOCKED (2026-10-07): usatoday.com 402s CI runners; the
    Supabase relay Edge Function `usatoday-fetch` is tried on a bot-wall
    status, and the week-5 slug ("trade-value-CHARTS-week-5") must be found."""

    BASE = "https://www.usatoday.com/story/sports/fantasy/football/2026/10/06/"
    W5 = BASE + "fantasy-trade-value-charts-week-5-ros-rankings/92125556007/"

    def test_discovery_matches_plural_charts_slug(self):
        body = ("<urlset><url><loc>%s</loc></url></urlset>" % self.W5)
        with_fetch = lambda u: (200, body)  # noqa: E731
        got = pull_usatoday.discover_url(week=5, fetch_fn=with_fetch)
        self.assertEqual(got, self.W5)  # old singular-only match: stale wk4/Failed

    def test_week_from_plural_url(self):
        self.assertEqual(pull_usatoday.extract_week_from_url(self.W5), 5)

    def _patched(self, relay, firecrawl=lambda u: None):
        o = (pull_usatoday.fetch_via_relay, pull_usatoday.fetch_via_firecrawl)
        pull_usatoday.fetch_via_relay, pull_usatoday.fetch_via_firecrawl = relay, firecrawl
        return o

    def _restore(self, o):
        pull_usatoday.fetch_via_relay, pull_usatoday.fetch_via_firecrawl = o

    def test_blocked_direct_falls_back_to_relay(self):
        o = self._patched(lambda u: (200, "<html>ok</html>"))
        try:
            got = pull_usatoday.fetch_article(self.W5, fetch_fn=lambda u: (402, "wall"))
        finally:
            self._restore(o)
        self.assertEqual(got, (200, "<html>ok</html>"))

    def test_direct_200_never_uses_relay(self):
        def boom(u):
            raise AssertionError("relay must not be used on a 200")
        o = self._patched(boom)
        try:
            got = pull_usatoday.fetch_article(self.W5, fetch_fn=lambda u: (200, "direct"))
        finally:
            self._restore(o)
        self.assertEqual(got, (200, "direct"))

    def test_relay_failure_keeps_source_blocked(self):
        # relay unreachable / upstream also blocked -> original 402 surfaces
        for relay in (lambda u: None, lambda u: (402, "wall")):
            o = self._patched(relay)
            try:
                with self.assertRaises(RuntimeError) as cm:
                    pull_usatoday.pull(self.W5, fetch_fn=lambda u, _f=pull_usatoday.fetch_article:
                                       _f(u, fetch_fn=lambda x: (402, "wall")))
            finally:
                self._restore(o)
            self.assertIn("SOURCE_BLOCKED", str(cm.exception))

    def test_relay_and_firecrawl_inert_without_secrets(self):
        env = {k: os.environ.pop(k, None) for k in
               ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "FIRECRAWL_API_KEY")}
        try:
            self.assertIsNone(pull_usatoday.fetch_via_relay("https://www.usatoday.com/x"))
            self.assertIsNone(pull_usatoday.fetch_via_firecrawl("https://www.usatoday.com/x"))
        finally:
            for k, v in env.items():
                if v is not None:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
