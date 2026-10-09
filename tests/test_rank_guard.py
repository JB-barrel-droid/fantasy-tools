"""Rank guard (JEG-482): a published chart's Indexed order is its own order.

Jeremy, 2026-10-08: "There shouldn't be some secondary correction layer, the
math is clearly off and this finding is a signal that it is." Indexed
(methodology.md, The Three Views #3) is each published chart's native values
times ONE factor, so for every published chart x combo the Indexed order must
equal the native order: zero inversions beyond exact native ties.

  * the saved values (data/fixtures/current) pass pipelines/check_rank_guard.py
    and are exactly native x the combo's one recorded factor;
  * a deliberately reordered fixture fails the guard (CLI exit 1);
  * the browser engine keeps the order at all 12 combos (3 scorings x 8/10/12/
    14 teams) and a superflex roster (TradeValueCurveDiagnostics.indexedOrder,
    recomputed here from the plotted maps), and getNativeRank returns the
    publisher's own rank.

Before the fix the saved Week 5 values had 15,279 inversions across the 12
saved combos (FantasyCalc full PPR: Smith-Njigba #3 natively, #5 Indexed).
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

from check_rank_guard import check_fixture, count_inversions, native_ranks  # noqa: E402
from tests import _render_env  # noqa: E402

FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
GUARD = REPO / "pipelines" / "check_rank_guard.py"
PUBLISHED = ("fantasycalc", "usatoday", "fantasypros", "cbs")


def _fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class TestCountInversions(unittest.TestCase):
    def test_monotone_rescale_has_none(self):
        native = {"a": 10.0, "b": 9.0, "c": 9.0, "d": 1.0}
        self.assertEqual(count_inversions(native, {k: v * 0.0071 for k, v in native.items()})["inversions"], 0)

    def test_swap_and_collapse_count(self):
        native = {"a": 10.0, "b": 9.0, "c": 8.0}
        self.assertEqual(count_inversions(native, {"a": 5.0, "b": 6.0, "c": 1.0})["inversions"], 1)
        # A tie between players the chart ranks apart loses its order.
        self.assertEqual(count_inversions(native, {"a": 5.0, "b": 5.0, "c": 1.0})["inversions"], 1)

    def test_native_ties_have_no_order(self):
        native = {"a": 9.0, "b": 9.0}
        self.assertEqual(count_inversions(native, {"a": 1.0, "b": 2.0})["inversions"], 0)

    def test_native_ranks_share_ties(self):
        self.assertEqual(native_ranks({"a": 3, "b": 2, "c": 2, "d": 1}), {"a": 1, "b": 2, "c": 2, "d": 4})


class TestSavedValues(unittest.TestCase):
    def test_every_published_combo_keeps_native_order(self):
        result = check_fixture(_fixture())
        self.assertEqual(result["status"], "pass", [c for c in result["checks"] if not c["ok"]][:2])
        checked = [c for c in result["checks"] if "skipped" not in c]
        self.assertEqual({c["source"] for c in checked}, set(PUBLISHED))
        self.assertGreaterEqual(len(checked), 12)

    def test_indexed_is_native_times_one_factor(self):
        doc = _fixture()
        for source in PUBLISHED:
            for combo_name, combo in doc["sources"][source]["combos"].items():
                fit = combo["fit"]
                self.assertNotIn("flex_aware_pie", fit, f"{source}/{combo_name}")
                self.assertNotIn("vorp_translation", fit, f"{source}/{combo_name}")
                self.assertNotIn("translation", combo, f"{source}/{combo_name}")
                factor = fit["order_preserving_rescale"]["factor"]
                self.assertGreater(factor, 0)
                for slug, value in combo["reindexed"].items():
                    self.assertAlmostEqual(value, float(combo["native"][slug]) * factor,
                                           delta=1e-9 * max(1.0, value), msg=f"{source}/{combo_name}/{slug}")
                # The pie over the calibrated players (chart-only players,
                # JEG-486, take the factor but are not in it) is the anchor's.
                chart_only = set(combo.get("not_on_espn") or [])
                self.assertAlmostEqual(sum(v for s, v in combo["reindexed"].items() if s not in chart_only),
                                       fit["order_preserving_rescale"]["anchor_total"], places=6)


class TestGuardFailsOnReorderedFixture(unittest.TestCase):
    def _run(self, doc):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "fixture.json"
            out = Path(td) / "rank-guard.json"
            path.write_text(json.dumps(doc), encoding="utf-8")
            proc = subprocess.run([sys.executable, str(GUARD), "--fixture", str(path), "--out", str(out)],
                                  capture_output=True, text=True, cwd=str(REPO))
            return proc.returncode, json.loads(out.read_text(encoding="utf-8"))

    def test_committed_fixture_passes(self):
        code, result = self._run(_fixture())
        self.assertEqual(code, 0)
        self.assertEqual(result["schema"], "rank-guard-v1")
        self.assertEqual(result["totals"]["inversions"], 0)

    def test_swapping_two_players_fails(self):
        doc = copy.deepcopy(_fixture())
        combo = doc["sources"]["fantasycalc"]["combos"]["full_12_qb1"]
        native = combo["native"]
        third, fourth = sorted(combo["reindexed"], key=lambda s: -float(native[s]))[2:4]
        r = combo["reindexed"]
        r[third], r[fourth] = r[fourth], r[third]
        code, result = self._run(doc)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "fail")
        failed = [c for c in result["checks"] if not c["ok"]]
        self.assertEqual([(c["source"], c["combo"], c["inversions"]) for c in failed],
                         [("fantasycalc", "full_12_qb1", 1)])
        self.assertEqual(failed[0]["examples"][0]["higher"], third)

    def test_per_position_scaling_fails(self):
        # The removed layer in miniature: one position scaled up on its own.
        doc = copy.deepcopy(_fixture())
        players = json.loads((REPO / "data/fixtures/current/players.json").read_text(encoding="utf-8"))
        pos_by_key = {p["player_key"]: p["pos"] for p in players["players"]}
        keys = doc["player_keys"]
        combo = doc["sources"]["usatoday"]["combos"]["full_12"]
        for slug in combo["reindexed"]:
            if pos_by_key.get(keys.get(slug)) == "RB":
                combo["reindexed"][slug] *= 1.3
        code, result = self._run(doc)
        self.assertEqual(code, 1)
        self.assertGreater(result["totals"]["inversions"], 0)


SWEEP = [(s, t, None) for s in ("standard", "half_ppr", "ppr") for t in (8, 10, 12, 14)]
SWEEP += [("ppr", 12, {"SUPERFLEX": 1}), ("half_ppr", 10, {"RB": 3, "FLEX": 2, "BENCH": 8})]

READ = """(published) => {
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const c = window.TradeValueCurveControls;
  const out = {indexed: {}, ranks: {}, diag: window.TradeValueCurveDiagnostics.indexedOrder || null};
  published.forEach(key => {
    const m = maps.get(key);
    out.indexed[key] = m ? Object.fromEntries([...m.entries()]) : null;
    out.ranks[key] = c.getNativeRanks(key);
  });
  return out;
}"""


class TestEngineKeepsOrderEverySetting(unittest.TestCase):
    """The browser's Indexed values at the 12 combos, a superflex roster and a
    custom roster: zero inversions against the chart's native order."""

    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        from tests.test_published_league_settings_render import _server
        cls.swept, errors = {}, []
        with _server() as url, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                             executable_path=_render_env.chromium_executable(pw))
            except Exception as exc:
                raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
            try:
                for scoring, teams, roster in SWEEP:
                    page = browser.new_page()
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.goto(url, wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueCurveHarness && window.TradeValueCurveDiagnostics",
                                           timeout=120000)
                    page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; c.setScoring(s); c.setTeams(t); }",
                                  [scoring, teams])
                    for key, value in (roster or {}).items():
                        page.evaluate("""([k, v]) => { const i = document.querySelector(`[data-roster-key="${k}"]`);
                                          i.value = v; i.dispatchEvent(new Event('change')); }""", [key, value])
                    page.locator('#viewModeTabs [data-view-mode="indexed"]').click()
                    cls.swept[(scoring, teams, json.dumps(roster))] = page.evaluate(READ, list(PUBLISHED))
                    page.close()
            finally:
                browser.close()
        cls.errors = errors

    def test_no_page_errors(self):
        self.assertEqual(self.errors, [])

    def test_indexed_order_equals_native_order(self):
        problems = []
        for setting, res in self.swept.items():
            if res["diag"] is None or res["diag"].get("ok") is not True:
                problems.append(f"{setting}: page indexedOrder {res['diag'] and res['diag'].get('sources')}")
            for key in PUBLISHED:
                indexed, ranks = res["indexed"][key], res["ranks"][key]
                if not indexed or not ranks:
                    problems.append(f"{setting} {key}: no Indexed values or native ranks")
                    continue
                # Lower rank number = higher native value; ties share a rank.
                native = {k: -float(r) for k, r in ranks.items() if k in indexed}
                inv = count_inversions(native, {k: indexed[k] for k in native})
                if inv["inversions"]:
                    problems.append(f"{setting} {key}: {inv['inversions']} inversions, first {inv['examples'][:1]}")
        self.assertEqual(problems, [])

    def test_native_rank_is_the_publishers(self):
        doc = _fixture()
        keys = doc["player_keys"]
        combo = doc["sources"]["fantasycalc"]["combos"]["full_12_qb1"]
        expected = native_ranks({keys[s]: float(v) for s, v in combo["native"].items() if s in keys})
        ranks = self.swept[("ppr", 12, "null")]["ranks"]["fantasycalc"]
        top = sorted(expected, key=lambda k: expected[k])[:10]
        self.assertEqual({k: ranks.get(str(k)) for k in top}, {k: expected[k] for k in top})


if __name__ == "__main__":
    unittest.main()
