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


class ServedWeekTest(Case):
    """JEG-1314: a source-week is labelled by the week the source is served as.

    Mirrors the JEG-1172 run (e2c191c): content_week had flipped to 8 while
    every chart was still served as week 7, and FantasyPros' week 7 article
    was filed as "week 8" and escalated against week 7 (its own inputs)."""

    FP_W7 = "sha256:" + "7" * 64

    def write_index(self, content_week: int, served_week: int, fp_fingerprint: str | None = None):
        served = {s: {"week": served_week, "label_week": served_week,
                      "fingerprint": fp_fingerprint if s == "fantasypros" else f"sha256:{s}"} for s in CHARTS}
        (self.history / "index.json").write_text(json.dumps(
            {"content_week": content_week, "fixture_built_at": fixture()["built_at"], "served": served}))

    def write_week(self, week: int, high: str | None = None, fp_fingerprint: str | None = None):
        doc = history_week(week, high=high)
        if fp_fingerprint:
            doc["sources"]["fantasypros"]["fingerprint"] = fp_fingerprint
        (self.history / f"week-{week}.json").write_text(json.dumps(doc))

    def test_a_still_served_week_keeps_its_own_label_after_the_flip(self):
        self.write_index(content_week=8, served_week=7, fp_fingerprint=self.FP_W7)
        for w in (5, 6):
            self.write_week(w)
        self.write_week(7, high="fantasypros", fp_fingerprint=self.FP_W7)
        self.resolutions.write_text(json.dumps({"resolutions": [
            {"source": "fantasypros", "week": 7, "resolution": "accepted", "issue": "JEG-796", "note": "opinion"}]}))
        report = self.run_check(fixture(high="fantasypros"))
        fp = report["sources"]["fantasypros"]
        self.assertEqual(8, report["week"])
        self.assertEqual(7, fp["week"])
        self.assertEqual("history_index", fp["week_basis"])
        # Week 7 is the served week itself, never its own prior week.
        self.assertEqual([6, 5], [p["week"] for p in fp["combos"]["full_12"]["prior_weeks"]])
        self.assertFalse(any("also warned in week 7" in r for r in fp["reasons"]), fp["reasons"])
        self.assertEqual("reviewed", fp["status"])
        self.assertEqual("JEG-796", fp["resolution"]["issue"])

    def test_a_saved_week_with_the_served_inputs_never_escalates(self):
        # A mislabelled save: week 7 holds the very inputs served as week 8.
        self.write_index(content_week=8, served_week=8, fp_fingerprint=self.FP_W7)
        self.write_week(6)
        self.write_week(7, high="fantasypros", fp_fingerprint=self.FP_W7)
        fp = self.run_check(fixture(high="fantasypros"))["sources"]["fantasypros"]
        self.assertEqual(8, fp["week"])
        self.assertIn(fp["status"], ("warn", "investigate"))  # still flagged on its own numbers
        self.assertFalse(any("also warned" in r for r in fp["reasons"]), fp["reasons"])
        self.assertEqual([6], [p["week"] for p in fp["combos"]["full_12"]["prior_weeks"]])

    def test_without_served_weeks_the_content_week_labels_every_source(self):
        report = self.run_check(fixture(high="fantasypros"))
        self.assertEqual({5}, {v["week"] for v in report["sources"].values()})
        self.assertEqual({"content_week"}, {v["week_basis"] for v in report["sources"].values()})

    def test_a_fingerprinted_resolution_applies_only_to_those_inputs(self):
        entry = {"source": "fantasypros", "week": 8, "resolution": "accepted", "issue": "JEG-1172",
                 "inputs_fingerprint": self.FP_W7, "note": "week label mix-up"}
        self.resolutions.write_text(json.dumps({"resolutions": [entry]}))
        self.write_index(content_week=8, served_week=8, fp_fingerprint="sha256:" + "8" * 64)
        fp = self.run_check(fixture(high="fantasypros"))["sources"]["fantasypros"]
        self.assertIn(fp["status"], ("warn", "investigate"))
        self.assertIsNone(fp["resolution"])
        self.write_index(content_week=8, served_week=8, fp_fingerprint=self.FP_W7)
        fp = self.run_check(fixture(high="fantasypros"))["sources"]["fantasypros"]
        self.assertEqual("reviewed", fp["status"])

    def test_exclude_cannot_be_scoped_to_inputs(self):
        self.resolutions.write_text(json.dumps({"resolutions": [
            {"source": "cbs", "week": 8, "resolution": "exclude", "inputs_fingerprint": self.FP_W7, "note": "x"}]}))
        resolutions, problems = sd.load_resolutions(self.resolutions)
        self.assertEqual({}, resolutions)
        self.assertEqual(1, len(problems))

    def test_exclude_is_keyed_by_the_content_week_like_value_reference(self):
        # JEG-1337: during the flip (served 7, content 8) the report hides the
        # same sources DDF Value does: value_reference keys exclude by content week.
        import value_reference as vr
        self.write_index(content_week=8, served_week=7, fp_fingerprint=self.FP_W7)
        for w in (5, 6):
            self.write_week(w)
        self.resolutions.write_text(json.dumps({"resolutions": [
            {"source": "fantasypros", "week": 7, "resolution": "exclude", "issue": "JEG-1", "note": "served week"},
            {"source": "cbs", "week": 8, "resolution": "exclude", "issue": "JEG-2", "note": "content week"},
        ]}))
        report = self.run_check(fixture(high="fantasypros"))
        expected = vr.load_divergence_exclusions(self.resolutions, week=8)
        self.assertEqual({"cbs"}, expected)
        self.assertEqual(expected, set(report["summary"]["excluded"]))
        self.assertEqual(7, report["sources"]["cbs"]["week"])
        self.assertIn(report["sources"]["fantasypros"]["status"], ("warn", "investigate"))
        self.assertTrue(any(p.startswith("fantasypros/week 7: exclude applies by the content week")
                            for p in report["summary"]["resolution_problems"]),
                        report["summary"]["resolution_problems"])

    def test_the_week_8_record_is_scoped_to_the_week_7_article(self):
        # JEG-1172: the flagged inputs are frozen week 7's FantasyPros entry.
        resolutions, _ = sd.load_resolutions(sd.RESOLUTIONS)
        entry = resolutions[("fantasypros", 8)]
        self.assertEqual("JEG-1172", entry["issue"])
        week7 = json.loads((REPO / "data" / "history" / "week-7.json").read_text(encoding="utf-8"))
        self.assertEqual(week7["sources"]["fantasypros"]["fingerprint"], entry["inputs_fingerprint"])

    def test_the_chain_publishes_the_report_it_rebuilt(self):
        # The committed copy only moved on a hand-run sync before JEG-1314;
        # divergence-issues.yml reads it.
        chain = (REPO / ".github" / "workflows" / "rebuild-chain.yml").read_text(encoding="utf-8")
        success = chain.split('if [ "$CHAIN_OUTCOME" = "success" ]; then', 1)[1].split("          else", 1)[0]
        self.assertIn("git add dist/modules/source-divergence.json", success)
        issues = (REPO / ".github" / "workflows" / "divergence-issues.yml").read_text(encoding="utf-8")
        self.assertIn("dist/modules/source-divergence.json", issues)


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
