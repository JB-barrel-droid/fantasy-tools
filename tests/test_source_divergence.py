"""JEG-460: the source divergence soft check.

Synthetic fixtures only (no data/raw, Supabase or network). Pins: a chart
that runs high against the others is flagged, missing values are never read
as 0, the trailing baseline and the two-week rule, recorded resolutions, the
check never raising into the build, and its wiring into `make sync`.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipelines"))

import check_source_divergence as sd  # noqa: E402

CHARTS = ("usatoday", "fantasycalc", "fantasypros", "cbs")
POS = ("QB", "RB", "WR", "TE")


def base_value(i: int) -> float:
    return 60.0 - i * 1.5  # 30 players, 60 down to 16.5


def fixture(high: str | None = None, factor: float = 1.6, drop: dict | None = None) -> dict:
    """Four charts that agree, except `high`, which prices everyone `factor` times higher."""
    names = [f"player {i}" for i in range(30)]
    sources = {}
    for s in CHARTS:
        combos = {}
        for scoring in sd.SCORINGS:
            vals = {}
            for i, n in enumerate(names):
                if drop and n in drop.get(s, ()):
                    continue
                vals[n] = base_value(i) * (factor if s == high else 1.0) * (1 + 0.02 * ((i + len(s)) % 3 - 1))
            native = {n: v / 0.8 for n, v in vals.items()}
            combos[sd.combo_key(s, scoring)] = {"native": native, "reindexed": vals}
        sources[s] = {"combos": combos}
    return {"built_at": "2026-10-10T00:00:00Z", "player_keys": {n: i + 1 for i, n in enumerate(names)},
            "sources": sources}


def history_week(week: int, high: str | None = None, factor: float = 1.6) -> dict:
    """A past week's natives (keyed by player_key) for the four charts."""
    srcs = {}
    for s in CHARTS:
        nat = {str(i + 1): base_value(i) * (factor if s == high else 1.0) / 0.8 for i in range(30)}
        srcs[s] = {"kind": "published_chart", "natives": {"standard": nat, "half_ppr": nat, "ppr": nat}}
    return {"week": week, "sources": srcs}


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.history = self.tmp / "history"
        self.history.mkdir()
        (self.history / "index.json").write_text(json.dumps({"content_week": 5}))
        self.players = self.tmp / "players.json"
        self.players.write_text(json.dumps({"players": [{"player_key": i + 1, "pos": POS[i % 4]} for i in range(30)]}))
        self.resolutions = self.tmp / "resolutions.json"

    def run_check(self, fx: dict) -> dict:
        path = self.tmp / "fixture.json"
        path.write_text(json.dumps(fx))
        return sd.run(path, self.players, self.history, self.resolutions)


class DivergenceMetricTest(Case):
    def test_a_chart_that_runs_high_is_flagged_and_the_others_are_not(self):
        report = self.run_check(fixture(high="fantasypros"))
        fp = report["sources"]["fantasypros"]
        self.assertIn(fp["status"], ("warn", "investigate"))
        self.assertGreater(fp["bias"], sd.WARN_BIAS)
        self.assertGreater(fp["outlier_rate"], sd.WARN_OUTLIER_RATE)
        for s in ("usatoday", "fantasycalc", "cbs"):
            self.assertEqual("ok", report["sources"][s]["status"], s)
        self.assertEqual(["FantasyPros"], report["summary"]["flagged"])
        self.assertIn("FantasyPros disagrees with the other charts on 100% of players", fp["message"])
        self.assertFalse(report["blocking"])

    def test_agreeing_charts_are_ok(self):
        report = self.run_check(fixture())
        self.assertEqual("ok", report["status"])
        self.assertTrue(all(v["status"] == "ok" for v in report["sources"].values()))

    def test_missing_values_are_never_read_as_zero(self):
        # Two charts drop the same 10 players: those players are priced by only
        # two charts and must not count (as 0 they would make a huge outlier).
        dropped = {f"player {i}" for i in range(10)}
        report = self.run_check(fixture(drop={"usatoday": dropped, "cbs": dropped}))
        fp = report["sources"]["fantasypros"]["combos"]["full_12"]
        self.assertEqual(20, fp["n"])
        self.assertEqual("ok", report["sources"]["fantasypros"]["status"])

    def test_leave_one_out_median(self):
        rows = sd.divergence({"a": {1: 10.0}, "b": {1: 20.0}, "c": {1: 30.0}, "d": {1: 100.0}}, {1: "RB"})
        self.assertEqual(80.0, rows["d"]["bias"])   # median of 10, 20, 30
        self.assertEqual(-20.0, rows["a"]["bias"])  # 10 - median(20, 30, 100)
        self.assertEqual(1, rows["d"]["by_position"]["RB"]["n"])


class BaselineAndResolutionTest(Case):
    def test_warned_last_week_too_escalates_to_investigate(self):
        for w in (3, 4):
            (self.history / f"week-{w}.json").write_text(json.dumps(history_week(w, high="fantasypros")))
        report = self.run_check(fixture(high="fantasypros"))
        fp = report["sources"]["fantasypros"]
        self.assertEqual("investigate", fp["status"])
        self.assertTrue(any("also warned in week 4" in r for r in fp["reasons"]))
        self.assertEqual(1.0, fp["usual_outlier_rate"])
        self.assertIn("(usually 100%)", fp["message"])

    def test_a_jump_over_the_sources_own_baseline_warns_below_the_ceiling(self):
        # 20% high: under the fixed ceilings' bias for low values, but far
        # above an agreeing baseline (0% outliers in weeks 3 and 4).
        for w in (3, 4):
            (self.history / f"week-{w}.json").write_text(json.dumps(history_week(w)))
        report = self.run_check(fixture(high="cbs", factor=1.4))
        cbs = report["sources"]["cbs"]
        self.assertIn(cbs["status"], ("warn", "investigate"))
        self.assertTrue(any("vs usual 0%" in r for r in cbs["reasons"]), cbs["reasons"])

    def test_a_recorded_resolution_marks_the_source_week_reviewed(self):
        self.resolutions.write_text(json.dumps({"resolutions": [
            {"source": "fantasypros", "week": 5, "resolution": "accepted", "issue": "JEG-999", "note": "genuine opinion"},
            {"source": "cbs", "week": 5, "resolution": "exclude"},
        ]}))
        report = self.run_check(fixture(high="fantasypros"))
        fp = report["sources"]["fantasypros"]
        self.assertEqual("reviewed", fp["status"])
        self.assertIn(fp["computed_status"], ("warn", "investigate"))
        self.assertEqual([], report["summary"]["flagged"])
        self.assertEqual(["FantasyPros"], report["summary"]["reviewed"])
        self.assertEqual("JEG-999", sd.freshness_summary(report)["fantasypros"]["resolution_issue"])
        self.assertEqual(1, len(report["summary"]["resolution_problems"]))

    def test_the_checked_in_resolutions_file_is_valid(self):
        _, problems = sd.load_resolutions(sd.RESOLUTIONS)
        self.assertEqual([], problems)


class SoftCheckTest(Case):
    def test_an_error_is_reported_never_raised(self):
        out = self.tmp / "out.json"
        report = sd.run_soft(out, fixture_path=self.tmp / "missing.json", players_path=self.players,
                             history_dir=self.history, resolutions_path=self.resolutions)
        self.assertEqual("error", report["status"])
        self.assertEqual("error", json.loads(out.read_text())["status"])

    def test_cli_exits_zero_when_sources_are_flagged(self):
        path = self.tmp / "fixture.json"
        path.write_text(json.dumps(fixture(high="fantasypros")))
        self.assertEqual(0, sd.main(["--fixture", str(path), "--out", str(self.tmp / "o.json"),
                                     "--players", str(self.players), "--history", str(self.history)]))

    def test_make_sync_runs_the_check_and_publishes_it(self):
        sync = (REPO / "pipelines" / "sync_dashboard_artifacts.py").read_text()
        self.assertIn("run_soft as run_source_divergence", sync)
        self.assertIn('freshness["source_divergence"]', sync)
        spec = json.loads((REPO / "modules" / "surfaces.json").read_text())
        surface = next(s for s in spec["surfaces"] if s["id"] == "source-divergence")
        self.assertEqual("modules/source-divergence.json", surface["url"])
        self.assertEqual("summary.flagged", surface["warn_path"])
        self.assertIsNone(surface.get("min_count"))  # an error report must not fail the gate


if __name__ == "__main__":
    unittest.main()
