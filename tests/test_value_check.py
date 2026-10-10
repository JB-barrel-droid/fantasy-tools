"""JEG-479 / JEG-508: the engine and the Python reference agree, and a
disagreement holds exactly the disagreeing source and the series derived
from it.

Jeremy, 2026-10-08: the math lives in two places on purpose (the browser
engine and pipelines/value_reference.py). pipelines/value_check.py diffs them
on every chain run; a disagreement holds that source and its derived series
for the week (validationHold on their fixture sections, the last published
sections kept) and keeps them out of the DDF Value.

Since JEG-508 both sides implement the source-neutral value pipeline
(docs/methodology.md "Value Pipeline", VP-0..VP-12). The live-engine tests
below need an engine that reports TradeValueCurveDiagnostics.valuePipeline
version "value-pipeline/2". On a build whose engine source does not declare
that version at all (the engine PR has not landed) they skip; an engine that
declares it but does not report it fails.

1. Reference == engine on the current build: every series in every tab, the
   estimated flags, the three DDF versions (current and prior week), the
   included set, ddfWeights, source weights, allocation and pie; 3 scorings x
   8/10/12/14 teams, default roster and one superflex slot.
2. Seeded mismatch: an engine dump whose FantasyCalc values are 5% high is
   flagged as FantasyCalc only, and the hold then restores exactly the
   FantasyCalc section, marked validationHold; every other section publishes
   this run's values. The reference keeps a held source out of the DDF Value.
3. A held source and an unpublished chart: the engine and the reference
   agree and both leave them out of the included set.
4. Attribution, reporting and hold bookkeeping (pure, no browser).
"""
from __future__ import annotations

import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
import value_check as vc  # noqa: E402
import value_reference as ref  # noqa: E402

TODAY = date.today()
ENGINE_FILES = ("assets/curve-widget.js", "assets/value-model.js")


def _playwright_or_skip():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc


def _pipeline_engine_or_skip():
    """Skip when the built engine source predates the JEG-508 pipeline."""
    _playwright_or_skip()
    _render_env.ensure_built()
    text = ""
    for rel in ENGINE_FILES:
        f = DIST / rel
        if f.exists():
            text += f.read_text(encoding="utf-8")
    if ref.PIPELINE_VERSION not in text:
        raise unittest.SkipTest(f"the built engine does not implement {ref.PIPELINE_VERSION} yet "
                                "(JEG-508 engine change not landed); nothing to compare")


def _assert_engine_reports_pipeline(tc: unittest.TestCase, engine_settings: dict):
    tc.assertEqual(vc.engine_pipeline_version(engine_settings), ref.PIPELINE_VERSION,
                   "the engine declares the value pipeline but TradeValueCurveDiagnostics.valuePipeline "
                   "does not report it at every setting")


class ReferenceMatchesEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pipeline_engine_or_skip()

    def test_zero_disagreements_on_the_current_build(self):
        settings = ref.settings()
        engine = vc.run_engine(settings, TODAY)
        self.assertEqual(engine["page_errors"], [])
        _assert_engine_reports_pipeline(self, engine["settings"])
        report = vc.compare(engine["settings"], vc.run_reference(settings, TODAY))
        bad = {k: (a["mismatches"], a["examples"][:2]) for k, a in report["series"].items() if a["mismatches"]}
        print(f"\n[JEG-508 value check] settings={len(settings)} values_compared={report['values_compared']} "
              f"verdict={report['verdict']} max_abs_diff="
              f"{max(a['max_abs_diff'] for a in report['series'].values()):.2e}")
        self.assertEqual(bad, {})
        self.assertEqual(report["verdict"], "agree")
        self.assertGreater(report["values_compared"], 150000)
        # Every page series and every league-level check was compared.
        for key in (*ref.SERIES_KEYS, *ref.DDF_VERSIONS, *(f"{v}_prior" for v in ref.DDF_VERSIONS),
                    "ddf_inputs", "ddf_weights", "allocation", "pie", *(f"{s}_weights" for s in ref.SOURCES)):
            self.assertGreater(report["series"][key]["compared"], 0, key)


class SeededMismatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _pipeline_engine_or_skip()

    def test_flags_and_holds_exactly_the_seeded_source(self):
        settings = [{"scoring": "ppr", "teams": 12, "superflex": 0}]
        engine = vc.run_engine(settings, TODAY)
        _assert_engine_reports_pipeline(self, engine["settings"])
        seeded = copy.deepcopy(engine["settings"])
        for entry in seeded.values():
            for rows in entry["views"].values():
                for row in rows.values():
                    if isinstance(row.get("fantasycalc"), (int, float)):
                        row["fantasycalc"] *= 1.05
        report = vc.compare(seeded, vc.run_reference(settings, TODAY))
        print(f"\n[JEG-508 seeded mismatch] disagreeing={report['disagreeing_sources']} "
              f"series={ {k: a['mismatches'] for k, a in report['series'].items() if a['mismatches']} }")
        self.assertEqual(report["verdict"], "disagree")
        self.assertEqual(report["disagreeing_sources"], ["fantasycalc"])
        self.assertEqual(report["hold"], {"fantasycalc": ["fantasycalc"]})
        self.assertEqual(report["composite_disagreements"], [])
        self.assertEqual(report["sources"]["fantasycalc"]["settings"], ["ppr/12/sf0"])

        # The chain's hold: FantasyCalc goes back to the last published
        # section; the others keep this run's.
        fixture = json.loads(ref.FIXTURE.read_text(encoding="utf-8"))
        last_good = copy.deepcopy(fixture)
        for sec in fixture["sources"]:
            last_good["sources"][sec]["_marker"] = "last good"
        held = vc.apply_holds(fixture, last_good, report["hold"], week=5)
        for sec, section in held["sources"].items():
            if sec == "fantasycalc":
                self.assertEqual(section.get("_marker"), "last good", sec)
                self.assertEqual(section["validationHold"]["week"], 5)
                self.assertIn("fantasycalc", section["validationHold"]["reason"])
            else:
                self.assertNotIn("_marker", section, sec)
                self.assertNotIn("validationHold", section, sec)
        # The reference keeps a held source out of the DDF Value (VP-1).
        inp = ref.Inputs.load()
        inp.fixture = held
        out = ref.compute(inp, settings[0], views=("indexed",))
        self.assertNotIn("fantasycalc", out["composite_inputs"])
        self.assertTrue(out["composite_excluded"].get("fantasycalc", "").startswith("held:"))


class HeldAndUnpublishedInputs(unittest.TestCase):
    """VP-1 on the live engine: a held source (validationHold on its
    section) and a chart that has not published the current week are not in
    the included set, in either week; both are still shown; the reference
    agrees with the engine value for value."""

    @classmethod
    def setUpClass(cls):
        _pipeline_engine_or_skip()

    def test_held_and_unpublished_inputs_agree_and_are_left_out(self):
        import tempfile
        fixture = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
        fixture["sources"]["fantasycalc"]["validationHold"] = {
            "reason": "engine and Python reference disagree on fantasycalc", "week": 5,
            "root": "fantasycalc", "kept_week": 5}
        fixture["sources"]["usatoday"]["week_designated"] = "Week 1"
        fixture["sources"]["usatoday"]["content_vintage"] = "Week 1"
        body = json.dumps(fixture).encode("utf-8")
        settings = [{"scoring": "ppr", "teams": 12, "superflex": 0},
                    {"scoring": "half_ppr", "teams": 10, "superflex": 1}]
        engine = vc.run_engine(settings, TODAY, overrides={"assets/comparison-sources-data.json": body})
        _assert_engine_reports_pipeline(self, engine["settings"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixture.json"
            path.write_bytes(body)
            reference = vc.run_reference(settings, TODAY, fixture=path)
        report = vc.compare(engine["settings"], reference)
        bad = {k: a["examples"][:2] for k, a in report["series"].items() if a["mismatches"]}
        self.assertEqual(bad, {})
        for sid, r in reference.items():
            self.assertNotIn("fantasycalc", r["composite_inputs"], sid)
            self.assertNotIn("usatoday", r["composite_inputs"], sid)
            self.assertTrue(r["composite_excluded"]["fantasycalc"].startswith("held:"), sid)
            self.assertTrue(r["composite_excluded"]["usatoday"].startswith("not yet published"), sid)
            # Still shown (VP-1.4): both charts have values on the rows.
            rows = r["views"]["adj"]
            self.assertTrue(any(v.get("fantasycalc") for v in rows.values()), sid)
            self.assertTrue(any(v.get("usatoday") for v in rows.values()), sid)


def _rows(values):
    return {"1": dict(values)}


class Attribution(unittest.TestCase):
    def _report(self, eng_vals, ref_vals, view="indexed"):
        views_e = {v: {} for v in ref.VIEWS}
        views_r = {v: {} for v in ref.VIEWS}
        views_e[view], views_r[view] = _rows(eng_vals), _rows(ref_vals)
        engine = {"x": {"views": views_e}}
        reference = {"x": {"views": views_r, "composite_inputs": []}}
        return vc.compare(engine, reference)

    def test_derived_series_disagreement_holds_its_root(self):
        # JEG-508 VP-11 retired the *_adjusted series; a projection's VORP vs
        # waivers series is now the derived series that holds its root.
        r = self._report({"espn_vorp": 10.0, "cbs": 5.0}, {"espn_vorp": 10.2, "cbs": 5.0}, view="vorp")
        self.assertEqual(r["disagreeing_sources"], ["espn"])
        self.assertEqual(r["hold"]["espn"], ["espn"])

    def test_within_tolerance_agrees_and_presence_does_not(self):
        r = self._report({"cbsros": 10.0, "razzball": 3.0}, {"cbsros": 10.0 + vc.TOL * 0.99, "razzball": None})
        self.assertEqual(r["disagreeing_sources"], ["razzball"])
        self.assertEqual(r["sources"]["cbsros"]["status"], "agree")

    def test_ddf_only_disagreement_holds_nothing(self):
        r = self._report({"ddf_value": 10.0}, {"ddf_value": 11.0})
        self.assertEqual(r["disagreeing_sources"], [])
        self.assertEqual(r["composite_disagreements"], ["ddf_value"])
        self.assertEqual(r["verdict"], "disagree")

    def test_ddf_disagreement_explained_by_an_input(self):
        r = self._report({"ddf_value": 10.0, "espn_vorp": 1.0}, {"ddf_value": 11.0, "espn_vorp": 2.0}, view="vorp")
        self.assertEqual(r["disagreeing_sources"], ["espn"])
        self.assertEqual(r["composite_disagreements"], [])

    def test_a_series_not_drawn_in_a_tab_is_not_compared(self):
        # VP-11: projections are not drawn in the VORP vs waivers tab.
        r = self._report({"espn": 1.0}, {"espn": 9.0}, view="vorp")
        self.assertEqual(r["verdict"], "agree")
        self.assertEqual(r["series"]["espn"]["compared"], 0)

    def test_source_derived_map_covers_every_page_series(self):
        self.assertEqual(sorted(vc.ROOT_OF), sorted(ref.SERIES_KEYS))
        for root, d in vc.SOURCE_DERIVED.items():
            self.assertEqual(d["sections"], [root])
        self.assertFalse([k for k in vc.ROOT_OF if k.endswith("_adjusted")])

    def test_chain_status_lists_the_hold(self):
        report = {"verdict": "disagree", "disagreeing_sources": ["usatoday"],
                  "hold": {"usatoday": ["usatoday"]}, "values_compared": 3}
        status = vc.update_chain_status({"status": "green", "held": [], "held_detail": {}}, report, 5)
        self.assertEqual(status["held"], ["usatoday"])
        self.assertEqual(status["status"], "published_with_holds")
        # JEG-508 VP-11: usatoday_adjusted is retired; the chart is its own series.
        self.assertEqual(status["held_detail"]["usatoday"]["held_series"], ["usatoday"])
        # record_chain_holds reads amber/red from hold_severity.
        self.assertEqual(status["held_detail"]["usatoday"]["hold_severity"], "amber")

    def test_hold_is_released_once_the_root_agrees(self):
        fixture = {"sources": {
            "cbs": {"validationHold": {"reason": "x", "week": 4, "root": "cbs"}},
            "cbs_adjusted": {"validationHold": {"reason": "x", "week": 4, "root": "cbs"}},
            "espn": {"validationHold": {"reason": "x", "week": 4, "root": "espn"}}}}
        self.assertEqual(vc.release_holds(fixture, ["espn"]), ["cbs", "cbs_adjusted"])
        self.assertNotIn("validationHold", fixture["sources"]["cbs"])
        self.assertIn("validationHold", fixture["sources"]["espn"])

    def test_chain_runs_the_check_before_the_deploy_gate(self):
        wf = (REPO / ".github" / "workflows" / "rebuild-chain.yml").read_text(encoding="utf-8")
        chain = wf.index("python3 pipelines/rebuild_comparison_chain.py --nfl-week")
        compare = wf.index("python3 pipelines/value_check.py compare")
        hold = wf.index("python3 pipelines/value_check.py hold")
        validate = wf.index("make validate > output/post-rebuild-validate.log")
        self.assertLess(chain, compare)
        self.assertLess(compare, hold)
        self.assertLess(hold, validate)
        self.assertIn("cp output/value-check.json dist/modules/value-check.json", wf)

    def test_hold_without_a_published_section_keeps_this_run_marked(self):
        fixture = {"sources": {"razzball": {"v": 2}, "espn": {"v": 2}}}
        held = vc.apply_holds(fixture, {"sources": {"espn": {"v": 1}}}, {"razzball": ["razzball"]}, 5)
        self.assertEqual(held["sources"]["razzball"]["v"], 2)
        self.assertIn("validationHold", held["sources"]["razzball"])
        self.assertNotIn("validationHold", held["sources"]["espn"])


def _pipe(**over):
    base = {"version": ref.PIPELINE_VERSION, "pie": 2688.0, "included": ["cbs", "espn"],
            "ddfWeights": {g: 0.125 for g in ref.GROUPS},
            "allocation": {p: {"dedicated": 12, "superflex": 0, "flex": 4, "bench": 18, "starters": 16,
                               "rostered": 34} for p in ref.POSITIONS},
            "sources": {"cbs": {"weights": {g: 0.125 for g in ref.GROUPS}},
                        "espn": {"weights": {g: 0.125 for g in ref.GROUPS}}}}
    return json.loads(json.dumps({**base, **over}))


class PipelineDiagnostics(unittest.TestCase):
    """VP-12 beyond the row values: estimated flags, weights, allocation, pie,
    and the per-setting / worst-example reporting."""

    def _cmp(self, e_extra, r_extra, sids=("ppr/12/sf0",)):
        engine, reference = {}, {}
        for sid in sids:
            engine[sid] = {"views": {v: {} for v in ref.VIEWS}, "pipeline": _pipe(), **e_extra}
            reference[sid] = {"views": {v: {} for v in ref.VIEWS}, "pipeline": _pipe(),
                              "composite_inputs": ["cbs", "espn"], "estimated": {}, **r_extra}
        return vc.compare(engine, reference)

    def test_agreeing_diagnostics(self):
        r = self._cmp({}, {})
        self.assertEqual(r["verdict"], "agree")
        for key in ("pie", "ddf_weights", "allocation", "ddf_inputs", "cbs_weights", "espn_weights"):
            self.assertGreater(r["series"][key]["compared"], 0, key)

    def test_estimated_flag_disagreement_holds_that_chart(self):
        r = self._cmp({"estimated": {"7": ["cbs"]}}, {"estimated": {"7": {"cbs": "peers"}, "8": {"cbs": "curve"}}})
        self.assertEqual(r["disagreeing_sources"], ["cbs"])
        self.assertEqual(r["series"]["cbs_estimated"]["mismatches"], 1)
        self.assertEqual(r["series"]["cbs_estimated"]["examples"][0]["player_key"], 8)

    def test_weights_use_1e4(self):
        w_ok = {g: 0.125 + 0.9e-4 for g in ref.GROUPS}
        w_bad = {g: 0.125 + 2e-4 for g in ref.GROUPS}
        ok = self._cmp({"pipeline": _pipe(sources={"cbs": {"weights": w_ok}, "espn": {"weights": w_ok}})}, {})
        self.assertEqual(ok["verdict"], "agree")
        bad = self._cmp({"pipeline": _pipe(sources={"cbs": {"weights": w_bad},
                                                    "espn": {"weights": {g: 0.125 for g in ref.GROUPS}}})}, {})
        self.assertEqual(bad["disagreeing_sources"], ["cbs"])

    def test_league_level_disagreements_hold_no_source(self):
        alloc = _pipe()["allocation"]
        alloc["RB"]["flex"] = 5
        r = self._cmp({"pipeline": _pipe(allocation=alloc, pie=2240.0)}, {})
        self.assertEqual(r["disagreeing_sources"], [])
        self.assertEqual(r["composite_disagreements"], ["allocation", "pie"])
        self.assertEqual(r["verdict"], "disagree")

    def test_missing_engine_diagnostics_is_a_disagreement(self):
        r = self._cmp({"pipeline": None}, {})
        self.assertEqual(r["composite_disagreements"], ["pie"])

    def test_report_is_per_setting_and_lists_the_worst(self):
        sids = ("ppr/12/sf0", "standard/8/sf1")
        engine = {sid: {"views": {"indexed": {"1": {"cbs": 10.0}, "2": {"cbs": 4.0}}, "vorp": {}, "adj": {}}}
                  for sid in sids}
        engine["standard/8/sf1"]["views"]["indexed"]["2"]["cbs"] = 6.0
        reference = {sid: {"views": {"indexed": {"1": {"cbs": 10.1}, "2": {"cbs": 4.0}}, "vorp": {}, "adj": {}},
                           "composite_inputs": []} for sid in sids}
        r = vc.compare(engine, reference)
        self.assertEqual(r["by_setting"]["ppr/12/sf0"]["mismatches"], 1)
        self.assertEqual(r["by_setting"]["standard/8/sf1"]["mismatches"], 2)
        self.assertEqual(r["sources"]["cbs"]["settings"], sorted(sids))
        self.assertEqual(r["series"]["cbs"]["by_view"]["indexed"]["mismatches"], 3)
        # Worst first: the 2.0 miss leads.
        self.assertEqual((r["worst"][0]["setting"], r["worst"][0]["player_key"]), ("standard/8/sf1", 2))
        self.assertAlmostEqual(r["series"]["cbs"]["examples"][0]["diff"], 2.0)
        md = vc.summary_md(r)
        self.assertIn("standard/8/sf1", md)
        self.assertIn("Worst examples", md)

    def test_incomparable_engine_holds_and_releases_nothing(self):
        self.assertIsNone(vc.engine_pipeline_version({"a": {}, "b": {"pipeline": {"version": "x"}}}))
        self.assertEqual(vc.engine_pipeline_version({"a": {"pipeline": {"version": ref.PIPELINE_VERSION}}}),
                         ref.PIPELINE_VERSION)
        r = vc.incomparable(None)
        self.assertEqual(r["verdict"], "incomparable")
        self.assertEqual((r["hold"], r["disagreeing_sources"], r["sources"]), ({}, [], {}))
        import tempfile
        from argparse import Namespace
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.json"
            path.write_text(json.dumps(r), encoding="utf-8")
            with mock.patch.object(vc, "release_holds") as rel, mock.patch.object(vc, "apply_holds") as app:
                self.assertEqual(vc.cmd_hold(Namespace(report=str(path), week=5)), 0)
                rel.assert_not_called()
                app.assert_not_called()


if __name__ == "__main__":
    unittest.main()
