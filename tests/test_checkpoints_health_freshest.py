"""Checkpoint builder must use the freshest valid health input, not a hardcoded path.

2026-10-03: build_checkpoints() read only the gitignored
output/source-import-health.json. A rebuild from a clean worktree (no runtime
file) silently produced "unk" for 30 per-source checkpoints even though a
fresh committed dist copy existed -- the same hardcoded-fallback class as the
2026-10-01 sync_dashboard_artifacts.py fix. The builder now resolves via
import_health_source() (freshest valid of output/, dist/modules/, fixture).
These tests prove the wiring: with REPO pointed at a sandbox, the builder's
exact selection call must return the freshest valid candidate.
"""
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import build_pipeline_checkpoints as bpc  # noqa: E402
from sync_dashboard_artifacts import import_health_source  # noqa: E402


def _health(checked_at):
    return {
        "schema": "trade-value-import-health-v1",
        "checked_at": checked_at,
        "nfl_week": 4,
        "sources": {},
    }


class CheckpointsHealthFreshestTest(unittest.TestCase):
    def _sandbox(self, candidates):
        tmp = Path(tempfile.mkdtemp())
        for rel, checked_at in candidates:
            p = tmp / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(_health(checked_at)))
        return tmp

    def test_builder_selection_prefers_freshest_committed_copy(self):
        tmp = self._sandbox([
            ("dist/modules/source-import-health.json", "2026-10-03T14:37:27Z"),
            ("data/fixtures/current/source-import-health.json", "2026-10-03T09:12:50Z"),
        ])
        old_repo = bpc.REPO
        bpc.REPO = tmp
        try:
            # The exact call build_checkpoints() makes.
            chosen = import_health_source(bpc.REPO)
        finally:
            bpc.REPO = old_repo
        self.assertEqual(chosen, tmp / "dist/modules/source-import-health.json")

    def test_builder_selection_prefers_runtime_when_freshest(self):
        tmp = self._sandbox([
            ("output/source-import-health.json", "2026-10-03T15:00:00Z"),
            ("dist/modules/source-import-health.json", "2026-10-03T14:37:27Z"),
        ])
        old_repo = bpc.REPO
        bpc.REPO = tmp
        try:
            chosen = import_health_source(bpc.REPO)
        finally:
            bpc.REPO = old_repo
        self.assertEqual(chosen, tmp / "output/source-import-health.json")

    def test_invalid_candidates_are_skipped(self):
        tmp = Path(tempfile.mkdtemp())
        bad = tmp / "dist" / "modules" / "source-import-health.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text(json.dumps({"schema": "wrong-schema", "checked_at": "2026-10-03T15:00:00Z"}))
        good = tmp / "data" / "fixtures" / "current" / "source-import-health.json"
        good.parent.mkdir(parents=True, exist_ok=True)
        good.write_text(json.dumps(_health("2026-10-03T09:12:50Z")))
        old_repo = bpc.REPO
        bpc.REPO = tmp
        try:
            chosen = import_health_source(bpc.REPO)
        finally:
            bpc.REPO = old_repo
        self.assertEqual(chosen, good)


def _rz_date_str(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def _rz_leg(vintage_date):
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "inputs": {
            "razzball_snapshot_date": vintage_date,
            "razzball_snapshot_rows": 701,
        },
    }


def _rz_fixture(vintage):
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "sources": {"razzball": {"combos": {"full_12_qb1": 1}, "vintage": vintage}},
        "source_validation": {"razzball": "live"},
    }


class RazzballC5FreshnessTest(unittest.TestCase):
    """JEG-307 added a Razzball c5 gate driven by the vintage_date /
    age_days freshness entry, but razzball_health_from_fixture() -- the ONLY
    health record razzball uses (it never joins source-import-health) -- was
    never updated to emit those fields. Result: c5 was permanently `unk`
    with a misleading "no snapshot under data/raw/sources/razzball/" reason
    even when the snapshot existed.

    These tests prove the synthesizer feeds the gate, the gate yields honest
    age-based verdicts (not the permanent unk), and the unk branch names the
    unparseable vintage instead of claiming a missing snapshot.
    """

    def _synth(self, vintage_date):
        with patch.object(
            bpc, "newest_razzball_leg",
            return_value=("data/ddf-two-tier/x/ddf_leg_razzball.json", _rz_leg(vintage_date)),
        ):
            return bpc.razzball_health_from_fixture(_rz_fixture(vintage_date))

    def test_synthesizer_emits_vintage_date_and_age_days(self):
        vd = _rz_date_str(4)
        h = self._synth(vd)
        self.assertEqual(h["vintage_date"], vd)
        self.assertIsNotNone(h["age_days"])
        self.assertAlmostEqual(h["age_days"], 4.0, delta=1.0)

    def test_c5_is_warn_not_unk_for_4d_snapshot(self):
        h = self._synth(_rz_date_str(4))
        v = bpc.razzball_c5_verdict(h)
        self.assertEqual(v["status"], "warn")
        self.assertIn("warn window", v["reason"])

    def test_c5_ok_within_2d(self):
        self.assertEqual(bpc.razzball_c5_verdict(self._synth(_rz_date_str(1)))["status"], "ok")

    def test_c5_bad_after_6d(self):
        self.assertEqual(bpc.razzball_c5_verdict(self._synth(_rz_date_str(8)))["status"], "bad")

    def test_c5_unk_is_honest_about_unparseable_vintage(self):
        h = self._synth("rest of season")
        v = bpc.razzball_c5_verdict(h)
        self.assertEqual(v["status"], "unk")
        self.assertIn("rest of season", v["reason"])
        self.assertNotIn("no snapshot", v["reason"].lower())

    def test_broken_state_would_unk(self):
        """Discrimination proof: a record WITHOUT the freshness fields (the
        pre-fix synthesizer output) still hits the unk branch, so this suite
        would have caught the dead gate."""
        v = bpc.razzball_c5_verdict({"content_vintage": "2026-10-01"})
        self.assertEqual(v["status"], "unk")


def _c10_csd(monday_week, designation, combos=True, src="usatoday",
             built_at="2026-10-03T22:00:42.323533+00:00"):
    """Minimal comparison-sources-data.json shape for C10 verdict tests."""
    section = {"week_designated": designation}
    if combos:
        section["combos"] = {"full_12": {}}
    return {
        "built_at": built_at,
        "value_weeks": {"monday": monday_week},
        "sources": {src: section},
    }


class C10RenderedRolloverTest(unittest.TestCase):
    """2026-10-06: c10_rendered compared served week labels against the
    calendar content week. At the week rollover (Tue 00:00 CT) the calendar
    says N while the fixture is still week N-1 until the daily 08:00 CT
    refresh bakes week N -- healthy production honestly serving the
    week-(N-1) fixture flagged `bad` "Production output WRONG" on every
    source (observed 2026-10-06 00:07 CDT: 7 sources bad).

    The verdict now compares the served output against the COMMITTED fixture
    (what the deploy pipeline publishes). A one-week calendar lead over the
    fixture is `warn` (awaiting the scheduled rebuild); served bytes/labels
    that differ from the fixture are still `bad`. These tests pin that
    contract; on the pre-fix builder they fail (no c10_rendered_verdict
    exists -- the rollover logic was inline and always bad).
    """

    def _verdict(self, src, live, fixture, expected_week, js_text=None,
                 same_bytes=True):
        sha = "abc123def456"
        return bpc.c10_rendered_verdict(
            src, live, fixture, sha, sha if same_bytes else "deadbeef0000",
            expected_week, js_text)

    def test_rollover_one_week_is_warn_not_bad(self):
        """live == fixture at week 4, calendar rolled to 5 -> warn, never
        the pre-fix `bad` "WRONG"."""
        live = fixture = _c10_csd(4, "Week 4")
        status, reason = self._verdict("usatoday", live, fixture, 5)
        self.assertEqual(status, "warn")
        self.assertIn("awaiting", reason)
        self.assertNotIn("WRONG", reason)

    def test_rollover_rest_of_season_source_is_warn(self):
        live = fixture = _c10_csd(4, "rest of season", src="espn")
        status, _ = self._verdict("espn", live, fixture, 5)
        self.assertEqual(status, "warn")

    def test_served_label_differs_from_fixture_is_bad(self):
        live = _c10_csd(4, "Week 4")
        fixture = _c10_csd(5, "Week 5")
        status, reason = self._verdict("usatoday", live, fixture, 5)
        self.assertEqual(status, "bad")
        self.assertIn("WRONG", reason)

    def test_cdn_byte_drift_is_bad(self):
        live = fixture = _c10_csd(5, "Week 5")
        status, reason = self._verdict("usatoday", live, fixture, 5,
                                       same_bytes=False)
        self.assertEqual(status, "bad")
        self.assertIn("WRONG", reason)

    def test_missing_combos_is_bad(self):
        live = _c10_csd(5, "Week 5", combos=False)
        fixture = _c10_csd(5, "Week 5")
        status, reason = self._verdict("usatoday", live, fixture, 5)
        self.assertEqual(status, "bad")
        self.assertIn("no combos", reason)

    def test_two_week_lag_stays_bad(self):
        """Fixture two weeks behind the calendar is genuinely stale (the
        original "Week 2 when expecting Week 4" alarm), not rollover lag."""
        live = fixture = _c10_csd(3, "Week 3")
        status, reason = self._verdict("usatoday", live, fixture, 5)
        self.assertEqual(status, "bad")
        self.assertIn("stale", reason)
        self.assertNotIn("WRONG", reason)

    def test_current_week_is_ok(self):
        live = fixture = _c10_csd(5, "Week 5")
        status, reason = self._verdict("usatoday", live, fixture, 5)
        self.assertEqual(status, "ok")
        self.assertIn("Week 5", reason)

    def test_js_labels_baselined_to_fixture_week(self):
        """Hardcoded "(Week N)" labels are judged against the fixture week.
        Stale labels (behind the fixture) are still bad."""
        live = fixture = _c10_csd(5, "Week 5")
        js_ok = 'USA Today (Week 5) label here'
        status, reason = self._verdict("usatoday", live, fixture, 5,
                                       js_text=js_ok)
        self.assertEqual(status, "ok")
        self.assertNotIn("skipped", reason)
        js_stale = 'USA Today (Week 2) label here'
        status, reason = self._verdict("usatoday", live, fixture, 5,
                                       js_text=js_stale)
        self.assertEqual(status, "bad")
        self.assertIn("stale hardcoded labels", reason)

    def test_js_labels_correct_during_rollover(self):
        """Fixture-week labels are not flagged stale just because the
        calendar rolled ahead of the fixture (rollover warn takes
        precedence)."""
        live = fixture = _c10_csd(4, "Week 4")
        js_ok = 'USA Today (Week 4) label here'
        status, _ = self._verdict("usatoday", live, fixture, 5, js_text=js_ok)
        self.assertEqual(status, "warn")

    def test_unreadable_fixture_is_unk(self):
        live = _c10_csd(4, "Week 4")
        status, _ = self._verdict("usatoday", live, {}, 5)
        self.assertEqual(status, "unk")


if __name__ == "__main__":
    unittest.main()
