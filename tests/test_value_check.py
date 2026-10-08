"""JEG-479: the engine and the Python reference agree, and a disagreement
holds exactly the disagreeing source and the series derived from it.

Jeremy, 2026-10-08: the math lives in two places on purpose (the browser
engine and pipelines/value_reference.py). pipelines/value_check.py diffs them
on every chain run; a disagreement holds that source and its derived series
for the week (validationHold on their fixture sections, the last published
sections kept) and keeps them out of the DDF Value.

1. Reference == engine on the current build, every series, the three views,
   3 scorings x 8/10/12/14 teams, default roster and one superflex slot, plus
   the DDF Value's prior-week pair (headless, the built dist/).
2. Seeded mismatch: an engine that scales FantasyCalc's served values by 5%
   is flagged as FantasyCalc only, and the hold then restores exactly the
   FantasyCalc sections (raw + adjusted), marked validationHold; every other
   section publishes this run's values.
3. Attribution and hold bookkeeping (pure, no browser).
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

WIDGET = REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
TODAY = date.today()


def _playwright_or_skip():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc


class ReferenceMatchesEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _playwright_or_skip()
        _render_env.ensure_built()

    def test_zero_disagreements_on_the_current_build(self):
        settings = ref.settings()
        engine = vc.run_engine(settings, TODAY)
        self.assertEqual(engine["page_errors"], [])
        report = vc.compare(engine["settings"], vc.run_reference(settings, TODAY))
        bad = {k: (a["mismatches"], a["examples"][:2]) for k, a in report["series"].items() if a["mismatches"]}
        print(f"\n[JEG-479 value check] settings={len(settings)} values_compared={report['values_compared']} "
              f"verdict={report['verdict']} max_abs_diff="
              f"{max(a['max_abs_diff'] for a in report['series'].values()):.2e}")
        self.assertEqual(bad, {})
        self.assertEqual(report["verdict"], "agree")
        self.assertGreater(report["values_compared"], 150000)
        # Every page series was compared somewhere.
        for key in (*ref.SERIES_KEYS, ref.COMPOSITE_KEY, "ddf_value_prior"):
            self.assertGreater(report["series"][key]["compared"], 0, key)


SEED_OLD = "    return values;\n  }\n\n  // JEG-242: build a source map from vorp_views"
SEED_NEW = ("    if (key === \"fantasycalc\") values.forEach((v, k) => values.set(k, v * 1.05));\n"
            + SEED_OLD)


class SeededMismatch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _playwright_or_skip()
        _render_env.ensure_built()

    def test_flags_and_holds_exactly_the_seeded_source(self):
        source = (DIST / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertEqual(source.count(SEED_OLD), 1, "seed anchor moved")
        overrides = {"assets/curve-widget.js": source.replace(SEED_OLD, SEED_NEW).encode("utf-8")}
        settings = [{"scoring": "ppr", "teams": 12, "superflex": 0}]
        engine = vc.run_engine(settings, TODAY, overrides=overrides)
        report = vc.compare(engine["settings"], vc.run_reference(settings, TODAY))
        print(f"\n[JEG-479 seeded mismatch] disagreeing={report['disagreeing_sources']} "
              f"series={ {k: a['mismatches'] for k, a in report['series'].items() if a['mismatches']} }")
        self.assertEqual(report["verdict"], "disagree")
        self.assertEqual(report["disagreeing_sources"], ["fantasycalc"])
        self.assertEqual(report["hold"], {"fantasycalc": ["fantasycalc", "fantasycalc_adjusted"]})
        self.assertEqual(report["composite_disagreements"], [])

        # The chain's hold: FantasyCalc and its derived section go back to
        # the last published sections, marked; the others keep this run's.
        fixture = json.loads(ref.FIXTURE.read_text(encoding="utf-8"))
        last_good = copy.deepcopy(fixture)
        for sec in fixture["sources"]:
            last_good["sources"][sec]["_marker"] = "last good"
        held = vc.apply_holds(fixture, last_good, report["hold"], week=5)
        for sec, section in held["sources"].items():
            if sec in ("fantasycalc", "fantasycalc_adjusted"):
                self.assertEqual(section.get("_marker"), "last good", sec)
                self.assertEqual(section["validationHold"]["week"], 5)
                self.assertIn("fantasycalc", section["validationHold"]["reason"])
            else:
                self.assertNotIn("_marker", section, sec)
                self.assertNotIn("validationHold", section, sec)
        # The reference keeps a held series out of the DDF Value.
        inp = ref.Inputs.load()
        inp.fixture = held
        inp.held = {s: "validation hold" for s in ("fantasycalc", "fantasycalc_adjusted")}
        out = ref.compute(inp, settings[0], views=("indexed",))
        self.assertNotIn("fantasycalc_adjusted", out["composite_inputs"])
        self.assertEqual(out["composite_excluded"].get("fantasycalc_adjusted"), "held")


def _rows(values):
    return {"1": dict(values)}


class Attribution(unittest.TestCase):
    def _report(self, eng_vals, ref_vals):
        engine = {"x": {"views": {"indexed": _rows(eng_vals), "vorp": {}, "adj": {}}}}
        reference = {"x": {"views": {"indexed": _rows(ref_vals), "vorp": {}, "adj": {}},
                           "composite_inputs": []}}
        return vc.compare(engine, reference)

    def test_derived_series_disagreement_holds_its_root(self):
        r = self._report({"fantasycalc_adjusted": 10.0, "espn": 5.0}, {"fantasycalc_adjusted": 10.2, "espn": 5.0})
        self.assertEqual(r["disagreeing_sources"], ["fantasycalc"])
        self.assertEqual(r["hold"]["fantasycalc"], ["fantasycalc", "fantasycalc_adjusted"])

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
        r = self._report({"ddf_value": 10.0, "espn_vorp": 1.0}, {"ddf_value": 11.0, "espn_vorp": 2.0})
        self.assertEqual(r["disagreeing_sources"], ["espn"])
        self.assertEqual(r["composite_disagreements"], [])

    def test_source_derived_map_covers_every_page_series(self):
        self.assertEqual(sorted(vc.ROOT_OF), sorted(ref.SERIES_KEYS))
        for root, d in vc.SOURCE_DERIVED.items():
            self.assertIn(root, d["sections"])

    def test_chain_status_lists_the_hold(self):
        report = {"verdict": "disagree", "disagreeing_sources": ["usatoday"],
                  "hold": {"usatoday": ["usatoday", "usatoday_adjusted"]}, "values_compared": 3}
        status = vc.update_chain_status({"status": "green", "held": [], "held_detail": {}}, report, 5)
        self.assertEqual(status["held"], ["usatoday"])
        self.assertEqual(status["status"], "published_with_holds")
        self.assertEqual(status["held_detail"]["usatoday"]["held_series"], ["usatoday", "usatoday_adjusted"])
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


if __name__ == "__main__":
    unittest.main()
