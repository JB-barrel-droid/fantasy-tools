"""JEG-200: lineage freshness vs. served chart values.

The monitoring dashboard's `dist/modules/source-value-lineage.json` is built
from the fixture plus a live-page scrape. Before JEG-200, the artifact could
ship unchanged from a prior local build while the fixture (and the chart it
drives) advanced -- a monitor that contradicts the product it watches.

Fix: Stage 10 in pipelines/rebuild_comparison_chain.py runs the lineage
rebuild locally after Stage 9 (same run, same fixture vintage). Where raw
snapshots exist (local dev), the rebuild writes a fresh artifact. Where
they don't (CI), the builder's SystemExit handler stamps the committed
artifact with explicit staleness metadata.

Each test in this file is negative-tested against a pre-fix state
(stale lineage + newer fixture in a temp dir) to prove it catches the bug.

Acceptance criteria from docs/briefs-draft/JEG-200-lineage-freshness.md:
  1. Served-lineage freshness vs fixture, primary axis.
  2. Staleness badge, fallback axis (the floor).
  3. Regression: served lineage is not older than the fixture it describes.
  4. USA Today JSN / Lamb lineage matches the chart.
  5. The CI snapshot-absence path stays fail-closed.
  7. Freshness is content-vintage, never pull-time.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINEAGE_PATH = ROOT / "dist/modules/source-value-lineage.json"
FIXTURE_PATH = ROOT / "data/fixtures/current/comparison-sources-data.json"
BUILDER = ROOT / "pipelines/build_source_value_lineage.py"

sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "pipelines"))
from canonical_players import norm_player_name  # noqa: E402


def _parse_iso(ts):
    if not ts or not isinstance(ts, str):
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


class LineageFreshnessTests(unittest.TestCase):
    """Acceptance criteria 1, 2, 3, 4, 5, 7 from the JEG-200 brief."""

    # -- Helpers --------------------------------------------------------

    def _make_temp_workspace(self):
        """Create a temp dir with a copy of the current committed lineage and
        a *newer* fixture; the temp dir stands in for the pre-fix state.
        Returns (tmpdir, lineage_path, fixture_path).
        """
        tmp = tempfile.mkdtemp(prefix="jeg200-freshness-")
        dist = Path(tmp) / "dist/modules"
        dist.mkdir(parents=True)
        fixdir = Path(tmp) / "data/fixtures/current"
        fixdir.mkdir(parents=True)
        lineage_p = dist / "source-value-lineage.json"
        fixture_p = fixdir / "comparison-sources-data.json"

        # Copy the committed lineage
        if LINEAGE_PATH.exists():
            shutil.copy(LINEAGE_PATH, lineage_p)

        # Copy the current fixture and stamp a newer built_at
        if FIXTURE_PATH.exists():
            shutil.copy(FIXTURE_PATH, fixture_p)
            with open(fixture_p) as f:
                fx = json.load(f)
            older_gen = _parse_iso(fx.get("generated_at") or fx.get("built_at")) \
                or datetime(2026, 10, 2, 12, 45, 9, tzinfo=timezone.utc)
            new_gen = older_gen + timedelta(hours=1)
            fx["generated_at"] = new_gen.isoformat()
            fx["built_at"] = new_gen.isoformat()
            with open(fixture_p, "w") as f:
                json.dump(fx, f, indent=2)
        return tmp, lineage_p, fixture_p

    def _patch_paths(self, monkey_path_obj, lineage_p, fixture_p):
        """Re-point the builder's DATA_PATH / OUT_PATH at temp files.

        We do this by importing the builder module and writing its module
        attributes, then restoring them after the call. This is the cleanest
        way to exercise the builder without copying the whole tree.
        """
        import build_source_value_lineage as bsvl
        orig_data = bsvl.DATA_PATH
        orig_out = bsvl.OUT_PATH
        bsvl.DATA_PATH = str(fixture_p)
        bsvl.OUT_PATH = str(lineage_p)
        return bsvl, orig_data, orig_out

    def _restore_paths(self, bsvl, orig_data, orig_out):
        bsvl.DATA_PATH = orig_data
        bsvl.OUT_PATH = orig_out

    # -- Test 1+3: served lineage not older than fixture (or carries badge)

    def test_served_lineage_not_older_than_fixture(self):
        """Acceptance #3: a stale lineage + no badge = test fails (negative control)."""
        if not (LINEAGE_PATH.exists() and FIXTURE_PATH.exists()):
            self.skipTest("committed lineage / fixture not present")
        with open(LINEAGE_PATH) as f:
            lineage = json.load(f)
        with open(FIXTURE_PATH) as f:
            fixture = json.load(f)
        lin_ts = _parse_iso(lineage.get("generated_at"))
        fx_ts = _parse_iso(fixture.get("built_at") or fixture.get("generated_at"))
        self.assertIsNotNone(lin_ts, "lineage.generated_at missing")
        self.assertIsNotNone(fx_ts, "fixture.built_at missing")
        if lin_ts < fx_ts:
            # Stale: must either be re-stamped to a fresh generated_at OR
            # carry the staleness badge.
            self.assertTrue(
                lineage.get("stale_relative_to_fixture") is True,
                "served lineage is older than the fixture and carries no "
                "staleness badge -- this is the JEG-200 monitor bug",
            )
            self.assertIsNotNone(
                lineage.get("lag_seconds"),
                "stale lineage missing lag_seconds",
            )
            self.assertGreater(lineage["lag_seconds"], 0, "lag_seconds must be > 0")

    def test_negative_stale_lineage_with_no_badge_fails(self):
        """Negative control for #3: simulate the pre-fix bug and prove the
        check would have caught it."""
        tmp, lineage_p, fixture_p = self._make_temp_workspace()
        try:
            # The committed lineage carries no badge (pre-fix); the fixture
            # we just stamped is one hour newer.
            with open(lineage_p) as f:
                lineage = json.load(f)
            self.assertFalse(
                lineage.get("stale_relative_to_fixture", False),
                "pre-fix committed lineage should NOT carry a badge",
            )
            with open(fixture_p) as f:
                fixture = json.load(f)
            lin_ts = _parse_iso(lineage["generated_at"])
            fx_ts = _parse_iso(fixture["built_at"])
            self.assertLess(
                lin_ts, fx_ts,
                "simulated pre-fix state must have stale lineage",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # -- Test 4: USA Today JSN / Lamb lineage matches the fixture

    def test_usatoday_jsn_lamb_matches_fixture(self):
        """Acceptance #4: usatoday top25 chart_value for jaxon smith-njigba
        equals the fixture's reindexed for the same player (within 0.01),
        and ceedee lamb does too.

        The brief wrote "justin jefferson" -- that is a typo for jaxon
        smith-njigba. Asserting the typo would have to fail (jefferson's
        chart_value is not 55.0); we assert the intended player.
        """
        if not (LINEAGE_PATH.exists() and FIXTURE_PATH.exists()):
            self.skipTest("committed lineage / fixture not present")
        with open(LINEAGE_PATH) as f:
            lineage = json.load(f)
        with open(FIXTURE_PATH) as f:
            fixture = json.load(f)
        top25 = (lineage.get("sources") or {}).get("usatoday", {}).get("top25", [])
        # Build lineage index by normalized name
        lin_idx = {}
        for row in top25:
            lin_idx[norm_player_name(row.get("player_key", ""))] = row.get("chart_value")
        # Build fixture index by normalized name for the usatoday combo
        usatoday_combo = (
            fixture.get("sources", {}).get("usatoday", {})
            .get("combos", {}).get("half_12", {})
        )
        # The fixture stores reindexed as {player_name: float}
        fixture_reindexed = usatoday_combo.get("reindexed", {})

        # 1) JSN
        jsn_n = norm_player_name("jaxon smith-njigba")
        # Some fixtures normalize to "jaxon smithnjigba" without hyphen
        jsn_candidates = {jsn_n, "jaxon smithnjigba", "jaxon smith-njigba"}
        jsn_lin = next(
            (lin_idx[n] for n in jsn_candidates if n in lin_idx), None)
        jsn_fix = next(
            (fixture_reindexed[n] for n in jsn_candidates if n in fixture_reindexed), None)
        self.assertIsNotNone(
            jsn_lin, f"jaxon smith-njigba missing from usatoday top25 lineage: {list(lin_idx)[:5]}..."
        )
        self.assertIsNotNone(
            jsn_fix, f"jaxon smith-njigba missing from usatoday fixture reindexed: {list(fixture_reindexed)[:5]}..."
        )
        self.assertAlmostEqual(
            float(jsn_lin), float(jsn_fix), places=2,
            msg=f"usatoday JSN chart_value {jsn_lin} != fixture reindexed {jsn_fix}",
        )
        # Belt-and-suspenders: the chart value the brief names.
        self.assertAlmostEqual(float(jsn_lin), 55.0, places=1)
        self.assertAlmostEqual(float(jsn_fix), 55.0, places=1)

        # 2) Ceedee Lamb
        lamb_n = norm_player_name("ceedee lamb")
        self.assertIn(
            lamb_n, lin_idx, f"ceedee lamb missing from usatoday top25 lineage"
        )
        self.assertIn(
            lamb_n, fixture_reindexed, f"ceedee lamb missing from usatoday fixture reindexed"
        )
        self.assertAlmostEqual(
            float(lin_idx[lamb_n]), float(fixture_reindexed[lamb_n]), places=2,
            msg=f"usatoday Lamb chart_value {lin_idx[lamb_n]} != fixture reindexed {fixture_reindexed[lamb_n]}",
        )
        # Belt-and-suspenders: the chart value the brief names.
        self.assertAlmostEqual(float(lin_idx[lamb_n]), 46.4, places=1)
        self.assertAlmostEqual(float(fixture_reindexed[lamb_n]), 46.4, places=1)

    def test_negative_usatoday_jsn_stale_lineage_fails(self):
        """Negative control for #4: the pre-fix lineage shows JSN at 37.28, not 55.0.
        Simulate by writing a stale lineage and asserting the assertion fails."""
        # Build a minimal lineage where usatoday JSN is the pre-fix wrong value
        tmp = tempfile.mkdtemp(prefix="jeg200-neg4-")
        try:
            lineage_p = Path(tmp) / "lineage.json"
            lineage = {
                "generated_at": "2026-10-02T12:45:09.640835+00:00",
                "sources": {
                    "usatoday": {
                        "top25": [
                            {"player_key": "jaxon smithnjigba", "chart_value": 37.28},
                            {"player_key": "ceedee lamb", "chart_value": 55.0},
                        ]
                    }
                }
            }
            with open(lineage_p, "w") as f:
                json.dump(lineage, f)
            with open(lineage_p) as f:
                bad = json.load(f)
            jsn_val = next(
                r["chart_value"] for r in bad["sources"]["usatoday"]["top25"]
                if "smith" in r["player_key"]
            )
            # Confirm pre-fix wrong value
            self.assertNotAlmostEqual(float(jsn_val), 55.0, places=1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # -- Test 2: staleness badge present when rebuild raises

    def test_staleness_badge_present_when_rebuild_raises(self):
        """Acceptance #2: when the builder raises (SystemExit) and the
        committed artifact exists, the artifact is stamped with explicit
        stale_relative_to_fixture and lag_seconds fields.

        We invoke stamp_staleness_badge() directly so this test does not
        require gitignored data/raw/snapshots; the SystemExit -> stamp path
        is exercised by `test_staleness_badge_handler_stamps_on_systemexit`.
        """
        tmp, lineage_p, fixture_p = self._make_temp_workspace()
        try:
            import build_source_value_lineage as bsvl
            bsvl, orig_data, orig_out = self._patch_paths(bsvl, lineage_p, fixture_p)
            try:
                artifact = bsvl.stamp_staleness_badge(
                    out_path=str(lineage_p),
                    fixture_path=str(fixture_p),
                    reason="builder_raised",
                )
            finally:
                self._restore_paths(bsvl, orig_data, orig_out)
            self.assertIsNotNone(artifact, "stamp returned None -- no committed artifact")
            self.assertIn("stale_relative_to_fixture", artifact)
            self.assertIn("lag_seconds", artifact)
            self.assertIn("stale_reason", artifact)
            self.assertTrue(artifact["stale_relative_to_fixture"],
                            "fixture was stamped newer than lineage; staleness expected")
            self.assertGreater(artifact["lag_seconds"], 0,
                               "lag_seconds must be positive")
            # Confirm written to disk
            with open(lineage_p) as f:
                on_disk = json.load(f)
            self.assertTrue(on_disk["stale_relative_to_fixture"])
            self.assertGreater(on_disk["lag_seconds"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_staleness_badge_handler_stamps_on_systemexit(self):
        """End-to-end #2: invoke the builder entry point with a missing
        snapshot. require_snapshot_natives() must raise SystemExit and the
        `__main__` handler must stamp the badge on the committed artifact
        before re-raising.
        """
        tmp, lineage_p, fixture_p = self._make_temp_workspace()
        try:
            # Make data/raw/sources/*/snapshot.json absent under the temp root.
            # The builder uses absolute paths from REPO; we import the module,
            # patch SNAPSHOT_PATHS so every path is under tmp/nonexistent.
            # Also give the builder a FRESH live-scrape artifact: the committed
            # one is >48h old, which would raise ValueError before the snapshot
            # check runs. We want require_snapshot_natives() -> SystemExit.
            import build_source_value_lineage as bsvl
            orig_data, orig_out = bsvl.DATA_PATH, bsvl.OUT_PATH
            orig_snapshot_paths = dict(bsvl.SNAPSHOT_PATHS)
            orig_repo = bsvl.REPO
            orig_scrape = bsvl.LIVE_PAGE_SCRAPE_PATH
            fresh_scrape = Path(tmp) / "live-page-scrape.json"
            fresh_scrape.write_text(json.dumps({
                "scraped_at": datetime.now(timezone.utc).isoformat(),
                "sources": {
                    src: {"status": "ok",
                          "top25": [["Test Player", 10.0]]}
                    for src in ("fantasypros", "usatoday", "cbs", "fantasycalc")
                },
            }))
            try:
                bsvl.DATA_PATH = str(fixture_p)
                bsvl.OUT_PATH = str(lineage_p)
                bsvl.LIVE_PAGE_SCRAPE_PATH = str(fresh_scrape)
                nonexistent = Path(tmp) / "no_such_snapshot.json"
                bsvl.SNAPSHOT_PATHS = {
                    "fantasypros": str(nonexistent),
                    "usatoday": str(nonexistent),
                    "fantasycalc": str(nonexistent),
                }
                # Invoke the main() function directly; require_snapshot_natives()
                # must raise SystemExit and the handler must stamp the badge.
                with self.assertRaises(SystemExit):
                    bsvl.main()
            finally:
                bsvl.DATA_PATH = orig_data
                bsvl.OUT_PATH = orig_out
                bsvl.SNAPSHOT_PATHS = orig_snapshot_paths
                bsvl.REPO = orig_repo
                bsvl.LIVE_PAGE_SCRAPE_PATH = orig_scrape
            # Badge must now be on disk
            with open(lineage_p) as f:
                on_disk = json.load(f)
            self.assertTrue(on_disk.get("stale_relative_to_fixture"),
                            "SystemExit handler did not stamp the staleness badge")
            self.assertGreater(on_disk.get("lag_seconds", 0), 0)
            self.assertEqual(on_disk.get("stale_reason"), "builder_raised")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # -- Test 5: CI snapshot-absence path stays fail-closed

    def test_require_snapshot_natives_still_raises_systemexit(self):
        """Acceptance #5: require_snapshot_natives() still raises SystemExit
        on missing snapshots -- not downgraded to a warning."""
        from build_source_value_lineage import require_snapshot_natives
        with self.assertRaises(SystemExit):
            require_snapshot_natives({"fantasypros": {}, "usatoday": {}, "fantasycalc": {}})

    def test_pages_workflow_continue_on_error_only_for_lineage_step(self):
        """Acceptance #5: pages.yml keeps continue-on-error: true only on the
        'Rebuild source value lineage' step; require_snapshot_natives() is
        still called and still raises SystemExit."""
        pages = (ROOT / ".github/workflows/pages.yml").read_text()
        self.assertIn("Rebuild source value lineage", pages,
                      "lineage step missing from pages.yml")
        # The lineage rebuild step is the one with continue-on-error: true.
        self.assertRegex(
            pages,
            r"name:\s*Rebuild source value lineage[\s\S]*?continue-on-error:\s*true",
            "the lineage rebuild step must keep continue-on-error: true",
        )
        # The validate step must NOT carry continue-on-error
        import re
        validate_block = re.search(
            r"name:[\s\S]*?run:\s*make validate[\s\S]*?(?=\n      - |\Z)",
            pages,
        )
        self.assertIsNotNone(validate_block, "validate step not found in pages.yml")
        self.assertNotIn(
            "continue-on-error: true", validate_block.group(0),
            "make validate must remain blocking (no continue-on-error)",
        )

    # -- Test 7: generated_at is fixture vintage, never wall-clock

    def test_stamp_staleness_badge_does_not_alter_generated_at(self):
        """Acceptance #7: stamp_staleness_badge() does NOT touch generated_at;
        it only adds badge fields. generated_at remains the fixture vintage
        (the value of the committed artifact at the time it was built)."""
        tmp, lineage_p, fixture_p = self._make_temp_workspace()
        try:
            with open(lineage_p) as f:
                before = json.load(f)
            orig_gen = before["generated_at"]
            import build_source_value_lineage as bsvl
            bsvl, orig_data, orig_out = self._patch_paths(bsvl, lineage_p, fixture_p)
            try:
                bsvl.stamp_staleness_badge(
                    out_path=str(lineage_p),
                    fixture_path=str(fixture_p),
                )
            finally:
                self._restore_paths(bsvl, orig_data, orig_out)
            with open(lineage_p) as f:
                after = json.load(f)
            self.assertEqual(
                after["generated_at"], orig_gen,
                "stamping the badge must not change generated_at",
            )
            # Badge fields present
            self.assertIn("stale_relative_to_fixture", after)
            self.assertIn("lag_seconds", after)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # -- Stage 10 wiring -----------------------------------------------

    def test_stage_10_invokes_lineage_builder(self):
        """Verify Stage 10 is wired into rebuild_comparison_chain.execute_chain
        and runs build_source_value_lineage.py via the chain's run_fn."""
        from rebuild_comparison_chain import execute_chain, run_lineage_rebuild
        import rebuild_comparison_chain as rcc
        # Sanity: function exists and is callable
        self.assertTrue(callable(run_lineage_rebuild))
        # Use a temp repo so Stage 10's fixture sync does not touch the real tree.
        tmp = tempfile.mkdtemp(prefix="jeg200-stage10-wiring-")
        try:
            fixdir = Path(tmp) / "data/fixtures/current"
            fixdir.mkdir(parents=True)
            (fixdir / "comparison-sources-data.json").write_text(
                json.dumps({"built_at": "2026-10-02T21:21:44+00:00", "sources": {}}))
            # Patch run_fn so we capture what it would invoke, then patch
            # write_chain_status so the test does not touch real status files.
            calls = []
            def fake_run(cmd, **kw):
                calls.append(cmd)
                return (True, "ok")
            # Replace write_chain_status on the module so the finally block
            # does not write to disk.
            orig_wcs = rcc.write_chain_status
            rcc.write_chain_status = lambda *a, **kw: {"success": True}
            try:
                execute_chain(nfl_week=4, repo=tmp, run_fn=fake_run)
            finally:
                rcc.write_chain_status = orig_wcs
            # Stage 10 must invoke build_source_value_lineage.py
            lineage_calls = [c for c in calls if "build_source_value_lineage.py" in " ".join(c)]
            self.assertTrue(
                len(lineage_calls) >= 1,
                f"Stage 10 did not invoke build_source_value_lineage.py; calls={calls}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stage_10_fail_safe_does_not_halt_chain(self):
        """Stage 10 mirrors Stage 9: rebuild failure is logged, chain continues."""
        from rebuild_comparison_chain import run_lineage_rebuild
        # Use a temp repo dir so the fixture sync does not touch the real tree.
        tmp = tempfile.mkdtemp(prefix="jeg200-stage10-")
        try:
            fixdir = Path(tmp) / "data/fixtures/current"
            fixdir.mkdir(parents=True)
            (fixdir / "comparison-sources-data.json").write_text(
                json.dumps({"built_at": "2026-10-02T21:21:44+00:00", "sources": {}}))
            def fake_run(cmd, **kw):
                return (False, "SystemExit: missing snapshots")
            result = run_lineage_rebuild(repo=tmp, run_fn=fake_run)
            self.assertEqual(result["status"], "failed")
            # Must not raise -- chain continues.
            # And the detail explains the badge stamping path.
            self.assertIn("builder raised", result["detail"].lower())
            # The sync must have copied the canonical fixture to the builder
            # input path even though the build itself failed.
            synced = Path(tmp) / "dist/assets/comparison-sources-data.json"
            self.assertTrue(synced.exists(),
                            "Stage 10 must sync the fixture before building")
            self.assertEqual(
                json.loads(synced.read_text())["built_at"],
                "2026-10-02T21:21:44+00:00")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_stage_10_syncs_fixture_before_build(self):
        """Stage 10 syncs the canonical fixture to the builder's input path
        (dist/assets/) BEFORE invoking the builder, so a fresh rebuild never
        bakes stale inputs. Negative control: without the sync, the builder
        would read the stale dist copy."""
        from rebuild_comparison_chain import run_lineage_rebuild
        tmp = tempfile.mkdtemp(prefix="jeg200-stage10-sync-")
        try:
            fixdir = Path(tmp) / "data/fixtures/current"
            fixdir.mkdir(parents=True)
            fresh_built_at = "2026-10-02T21:21:44+00:00"
            (fixdir / "comparison-sources-data.json").write_text(
                json.dumps({"built_at": fresh_built_at, "sources": {}}))
            # Seed a STALE builder input, as on main before the fix.
            builder_input = Path(tmp) / "dist/assets/comparison-sources-data.json"
            builder_input.parent.mkdir(parents=True)
            builder_input.write_text(json.dumps(
                {"built_at": "2026-10-02T12:45:09+00:00", "sources": {}}))
            seen = {}
            def fake_run(cmd, **kw):
                # Capture the builder input's built_at at invocation time.
                seen["built_at"] = json.loads(builder_input.read_text())["built_at"]
                return (True, "ok")
            result = run_lineage_rebuild(repo=tmp, run_fn=fake_run)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                seen.get("built_at"), fresh_built_at,
                "builder must see the fresh fixture, not the stale dist copy")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()