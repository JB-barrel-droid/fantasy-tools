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
WEEK_STATE = "() => window.TradeValueCurveControls.getWeekState?.() || null"
SET_WEEK = "(w) => window.TradeValueCurveControls.setWeek(w)"


def lagging_week(state, key):
    """JEG-1175 / JEG-1176: the week a chart left out of the page's week view
    still serves, when it is lagging (a week before the view's); else None.

    During a transition each source serves its own week and the view leaves a
    lagging one out (no carry-forward, Jeremy 2026-10-27), so its order is
    checked in its own week's view, not reported as missing.

    The view's missing_sources names only the charts that feed DDF Value; a
    chart on a red review hold is hidden from it (JEG-569) and so is in
    neither list, yet the page still leaves it out of a newer view. So the
    test is "not in the view's sources and serving an older week"."""
    if not state:
        return None
    week = state.get("week")
    view = (state.get("views") or {}).get(str(week)) or {}
    served = (state.get("servedWeeks") or {}).get(key)
    if key in (view.get("sources") or []):
        return None
    if not isinstance(served, int) or not isinstance(week, int) or served >= week:
        return None
    return served


def read_setting(page, published):
    """Indexed values and native ranks for each published chart at the page's
    current setting. A lagging chart is read in its own week's view (setWeek),
    then the page goes back to its default view. Returns the READ shape plus
    `weeks` (key -> the view week it was read in) and `lagging` (key -> its
    served week, for a chart outside the view whose week has no view)."""
    res = page.evaluate(READ, list(published))
    state = page.evaluate(WEEK_STATE)
    res["weeks"] = {key: (state or {}).get("week") for key in published}
    res["lagging"], res["week_diag"] = {}, {}
    absent = [key for key in published if not (res["indexed"][key] and res["ranks"][key])]
    by_week = {}
    for key in absent:
        week = lagging_week(state, key)
        if week is not None:
            by_week.setdefault(week, []).append(key)
    for week, keys in sorted(by_week.items()):
        if week not in ((state or {}).get("weeks") or []):
            # Older than any view the page offers: lagging, not a failure
            # (stale is a warning, JEG-1176 rule 6), but said out loud so a
            # chart that stops updating does not leave the guard unseen.
            res["lagging"].update({key: week for key in keys})
            print(f"rank guard: {', '.join(keys)} still on Week {week}, older than every week view "
                  f"{(state or {}).get('weeks')}; order not checked in the browser", file=sys.stderr)
            continue
        page.evaluate(SET_WEEK, week)
        got = page.evaluate(READ, keys)
        res["week_diag"][week] = got["diag"]
        for key in keys:
            res["indexed"][key], res["ranks"][key] = got["indexed"][key], got["ranks"][key]
            res["weeks"][key] = week
    if by_week:
        page.evaluate(SET_WEEK, None)
    return res


def order_problems(swept, published=PUBLISHED):
    """Every Indexed-vs-native inversion, missing chart and failed page check
    across the swept settings ([] is a pass)."""
    problems = []
    for setting, res in swept.items():
        diags = [("", res["diag"])] + [(f" week {w}", d) for w, d in sorted(res.get("week_diag", {}).items())]
        for label, diag in diags:
            if diag is None or diag.get("ok") is not True:
                problems.append(f"{setting}{label}: page indexedOrder {diag and diag.get('sources')}")
        for key in published:
            if key in res.get("lagging", {}):
                continue
            indexed, ranks = res["indexed"][key], res["ranks"][key]
            if not indexed or not ranks:
                problems.append(f"{setting} {key}: no Indexed values or native ranks")
                continue
            # Lower rank number = higher native value; ties share a rank.
            native = {k: -float(r) for k, r in ranks.items() if k in indexed}
            inv = count_inversions(native, {k: indexed[k] for k in native})
            if inv["inversions"]:
                problems.append(f"{setting} {key}: {inv['inversions']} inversions, first {inv['examples'][:1]}")
    return problems


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
                    page.add_init_script(_render_env.pin_data_week_script())
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
                    cls.swept[(scoring, teams, json.dumps(roster))] = read_setting(page, PUBLISHED)
                    page.close()
            finally:
                browser.close()
        cls.errors = errors

    def test_no_page_errors(self):
        self.assertEqual(self.errors, [])

    def test_indexed_order_equals_native_order(self):
        self.assertEqual(order_problems(self.swept), [])

    def test_native_rank_is_the_publishers(self):
        doc = _fixture()
        keys = doc["player_keys"]
        combo = doc["sources"]["fantasycalc"]["combos"]["full_12_qb1"]
        expected = native_ranks({keys[s]: float(v) for s, v in combo["native"].items() if s in keys})
        ranks = self.swept[("ppr", 12, "null")]["ranks"]["fantasycalc"]
        top = sorted(expected, key=lambda k: expected[k])[:10]
        self.assertEqual({k: ranks.get(str(k)) for k in top}, {k: expected[k] for k in top})


class TestEngineKeepsOrderInTransition(unittest.TestCase):
    """JEG-1175: chain runs since 2026-10-26 failed post-rebuild validation
    here ("cbs: no Indexed values or native ranks", earlier usatoday) because
    the lagging charts serve Week 7 while the view is Week 8, and the guard
    read every chart in the default view only. Replays the transition from
    committed data (test_week_history.transition_overrides: CBS and USA Today
    one week behind the rest) and checks each lagging chart's order in its own
    week's view."""

    # The overrides rewrite the 12-team combos; ppr/12 is the setting whose
    # transition view test_week_history pins.
    SETTINGS = [("ppr", 12)]
    # Charts also put on a red review hold in the replay (see the subclass).
    HELD = ()

    @classmethod
    def _overrides(cls, W):
        overrides = W.transition_overrides()
        if cls.HELD:
            doc = json.loads(overrides[W.FIXTURE_ASSET])
            for key in cls.HELD:
                doc["sources"][key]["promotionHold"] = {"reason": "review hold (rank guard sentinel)",
                                                        "hold_level": "red"}
            overrides[W.FIXTURE_ASSET] = json.dumps(doc, separators=(",", ":"))
        return overrides

    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        from tests import test_week_history as W
        if not (W.DIST / "assets" / "history" / "index.json").exists():
            raise _render_env.unavailable("dist/ is not built with history")
        cls.overrides = cls._overrides(W)
        cls.lagging = ("cbs", "usatoday")
        cls.swept, cls.states, errors = {}, {}, []
        with W._server(cls.overrides) as url, sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                             executable_path=_render_env.chromium_executable(pw))
            except Exception as exc:
                raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
            try:
                for scoring, teams in cls.SETTINGS:
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    page.add_init_script(_render_env.pin_data_week_script())
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    page.goto(url, wait_until="networkidle", timeout=120000)
                    page.wait_for_function(W.READY + " && !!window.TradeValueCurveHarness", timeout=120000)
                    page.evaluate("([s, t]) => { const c = window.TradeValueCurveControls; c.setScoring(s); c.setTeams(t); }",
                                  [scoring, teams])
                    page.locator('#viewModeTabs [data-view-mode="indexed"]').click()
                    cls.states[(scoring, teams)] = page.evaluate(WEEK_STATE)
                    cls.swept[(scoring, teams, "null")] = read_setting(page, PUBLISHED)
                    page.close()
            finally:
                browser.close()
        cls.errors = errors

    def test_no_page_errors(self):
        self.assertEqual(self.errors, [])

    def test_the_replay_is_a_transition(self):
        # Guards the sentinel itself: the lagging charts serve the week before
        # the default view and are out of it, so the old guard would have
        # reported them missing. (Out of the view's sources, not necessarily
        # in its missing_sources: a chart on a red hold is in neither.)
        for setting, state in self.states.items():
            week = state["week"]
            view = state["views"][str(week)]
            self.assertIn(week - 1, state["weeks"], (setting, state))
            self.assertEqual({k: state["servedWeeks"].get(k) for k in self.lagging},
                             {k: week - 1 for k in self.lagging}, (setting, state))
            self.assertEqual(set(self.lagging) & set(view["sources"]), set(), (setting, state))

    def test_lagging_charts_keep_order_in_their_own_week(self):
        self.assertEqual(order_problems(self.swept), [])
        for setting, res in self.swept.items():
            default = self.states[setting[:2]]["week"]
            self.assertEqual({k: res["weeks"][k] for k in self.lagging}, {k: default - 1 for k in self.lagging},
                             setting)
            self.assertEqual(res["lagging"], {}, setting)

    def test_a_reordered_lagging_chart_still_fails(self):
        # Mutation: swap two players' Indexed values in a lagging chart's
        # own-week read; the guard must still name it.
        setting = ("ppr", 12, "null")
        res = copy.deepcopy(self.swept[setting])
        ranks, indexed = res["ranks"]["cbs"], res["indexed"]["cbs"]
        ordered = sorted((k for k in ranks if k in indexed), key=lambda k: float(ranks[k]))
        # The first pair the chart ranks apart (swapping a native tie is no inversion).
        first, second = next((a, b) for a, b in zip(ordered, ordered[1:]) if float(ranks[a]) != float(ranks[b]))
        indexed[first], indexed[second] = indexed[second], indexed[first]
        problems = order_problems({setting: res})
        self.assertTrue([p for p in problems if " cbs: " in p and "inversions" in p], problems)


class TestEngineKeepsOrderWithHeldLaggingChart(TestEngineKeepsOrderInTransition):
    """Chain run 40612356639 (after #1016): CBS was a week behind AND on a red
    review hold. A red hold hides a chart from DDF Value (JEG-569), so the
    page's missing_sources did not name it and the guard reported it missing.
    Same replay with CBS also red-held: it must still be read in its own week."""

    HELD = ("cbs",)

    def test_the_held_chart_is_hidden_from_the_view_lists(self):
        # Guards the sentinel: the replay reproduces the chain's state.
        for setting, state in self.states.items():
            view = state["views"][str(state["week"])]
            self.assertNotIn("cbs", view["missing_sources"], (setting, state))


class TestLaggingWeek(unittest.TestCase):
    STATE = {"week": 8, "weeks": [8, 7],
             "servedWeeks": {"cbs": 7, "espn": 8, "old": 6, "gone": None, "held": 7, "ahead": 9},
             "views": {"8": {"sources": ["espn"], "missing_sources": ["cbs", "old", "gone"]},
                       "7": {"sources": ["cbs", "espn"], "missing_sources": []}}}

    def test_only_a_source_left_out_for_an_older_week_is_lagging(self):
        self.assertEqual(lagging_week(self.STATE, "cbs"), 7)
        self.assertEqual(lagging_week(self.STATE, "old"), 6)
        self.assertIsNone(lagging_week(self.STATE, "espn"))   # in the view
        self.assertIsNone(lagging_week(self.STATE, "gone"))   # no served week: a real gap
        self.assertIsNone(lagging_week(self.STATE, "ahead"))  # a later week is not lagging
        self.assertIsNone(lagging_week(None, "cbs"))

    def test_a_held_chart_on_an_older_week_is_lagging(self):
        # Chain run 40612356639: CBS on a red review hold, kept on Week 7,
        # is hidden from DDF Value, so the Week 8 view's missing_sources does
        # not name it; it is still lagging, not missing.
        self.assertEqual(lagging_week(self.STATE, "held"), 7)

    def test_a_chart_missing_from_its_own_view_fails(self):
        swept = {("ppr", 12, "null"): {"diag": {"ok": True}, "week_diag": {}, "lagging": {},
                                       "indexed": {k: None for k in PUBLISHED}, "ranks": {k: None for k in PUBLISHED},
                                       "weeks": {}}}
        problems = order_problems(swept)
        self.assertEqual(len(problems), len(PUBLISHED), problems)

    def test_a_lagging_chart_older_than_every_view_is_not_a_failure(self):
        swept = {("ppr", 12, "null"): {"diag": {"ok": True}, "week_diag": {}, "lagging": {"cbs": 6},
                                       "indexed": {k: ({"1": 2.0} if k != "cbs" else None) for k in PUBLISHED},
                                       "ranks": {k: ({"1": 1} if k != "cbs" else None) for k in PUBLISHED},
                                       "weeks": {}}}
        self.assertEqual(order_problems(swept), [])


if __name__ == "__main__":
    unittest.main()
