"""Superflex roster spot (JEG332-SUPERFLEX-FLEX, option A, Jeremy 2026-10-08).

A superflex league has a DEDICATED superflex slot (roster key SUPERFLEX, 0 or
1 on the page), filled after the dedicated slots and before FLEX by the best
remaining player with QBs eligible -- without the per-position slot weight
that kept QBs out of a QB-eligible flex.

Checks, each proved against a broken state:

1. Default identity. SUPERFLEX 0 is the default and must reproduce the old
   engine exactly: the server translation with superflex_count=0 equals the
   omitted argument, and the browser derivation with SUPERFLEX:0 equals the
   shape without the key, on every saved published chart x scoring x team
   count. Broken state: superflexCount defaulting to 1.
2. Superflex goes to quarterbacks on real projections. On the ESPN per-game
   projections the browser prices with, a 10- or 12-team superflex league
   starts 2 x teams QBs (projectionRoles, the ESPN series' roles) and the
   translation's superflex slots go to QBs (Python and JS). Broken states:
   the superflex slot apportioned by dedicated-slot weight (the old flex
   rule) and the slot ranked on surplus instead of points.
3. The live page accepts the control. setRosterSpot('SUPERFLEX', n) and the
   classic page's Superflex input change the roster, clamp to 0..1, and the
   published charts plot their superflex-overlay natives times one factor
   (VP-6.4; before JEG-508, the anchor-matched derivation).
   Broken state: a widget without the SUPERFLEX roster key (origin/main
   before this change), where the control is missing and setRosterSpot is a
   no-op.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.vorp_translation import unified  # noqa: E402
from pipelines.vorp_translation.vorp_via_roster import rostered_for_teams  # noqa: E402
from tests.test_published_league_settings_engine import (  # noqa: E402
    FIXTURE, SAVED_SHAPE, SCORINGS, SOURCES, VALUE_MODEL, _cases, browser_inputs, browser_players,
    compare_maps, expected_derived, run_js,
)
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


APP = ROOT / "app" / "trade-value-chart"
SF_SHAPE = {**SAVED_SHAPE, "SUPERFLEX": 1}

# Node: projectionRoles lineup + translationRostered superflex counts on the
# ESPN projections, for a given value-model.js.
QB_DRIVER = r"""
const VM = require(process.argv[1]);
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = input.cases.map(c => {
  const pool = c.players.map(p => ({player_key: p[0], name: p[1], pos: p[2]}));
  const ppg = new Map(c.players.map(p => [p[0], p[3]]));
  const counts = VM.allocationCounts({pool, teams: c.teams, shape: c.shape,
    rankOf: p => ppg.get(p.player_key)});
  const ranked = {QB: [], RB: [], WR: [], TE: []};
  c.players.forEach(p => ranked[p[2]].push({key: String(p[0]), value: p[3]}));
  Object.values(ranked).forEach(rows => rows.sort((a, b) => b.value - a.value));
  const roster = VM.translationRostered(c.teams, 6, 1, ranked, {QB: 1, RB: 2, WR: 3, TE: 1},
    ["RB", "WR", "TE"], c.shape.SUPERFLEX || 0);
  return {lineup: counts.lineup, roster};
});
process.stdout.write(JSON.stringify(out));
"""


def espn_players(scoring):
    players = json.loads((ROOT / "data" / "fixtures" / "current" / "players.json").read_text(encoding="utf-8"))["players"]
    out = []
    for p in players:
        val = (p.get("espn_ppg") or {}).get(scoring)
        if p.get("pos") in ("QB", "RB", "WR", "TE") and isinstance(p.get("player_key"), int) \
                and isinstance(val, (int, float)):
            out.append([p["player_key"], p.get("name") or "", p["pos"], float(val)])
    return out


def qb_problems(model_path=VALUE_MODEL):
    """Superflex slots must go to QBs on real ESPN projections (both sides)."""
    cases = [{"scoring": s, "teams": t, "shape": SF_SHAPE, "players": espn_players(s)}
             for s in SCORINGS for t in (10, 12)]
    proc = subprocess.run(["node", "-e", QB_DRIVER, str(model_path)],
                          input=json.dumps({"cases": cases}), capture_output=True, text=True,
                          timeout=300)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[:2000])
    problems = []
    for case, js in zip(cases, json.loads(proc.stdout)):
        tag = f"{case['scoring']}/{case['teams']}t"
        teams = case["teams"]
        if js["lineup"]["QB"] != 2 * teams:
            problems.append(f"{tag}: projectionRoles starts {js['lineup']['QB']} QBs, want {2 * teams}")
        ranked = {pos: [] for pos in ("QB", "RB", "WR", "TE")}
        for key, _name, pos, val in case["players"]:
            ranked[pos].append((str(key), val))
        for rows in ranked.values():
            rows.sort(key=lambda r: -r[1])
        py = rostered_for_teams(teams, 6, 1, ranked=ranked, superflex_count=1)
        if py != js["roster"]:
            problems.append(f"{tag}: translation roster py {py} != js {js['roster']}")
        if js["roster"]["QB"]["superflex"] < teams:
            problems.append(f"{tag}: superflex slots to QB {js['roster']['QB']['superflex']} of {teams}")
    return problems


def identity_problems(model_path=VALUE_MODEL):
    """SUPERFLEX 0 reproduces the default engine exactly (server and browser)."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    problems = []
    for source in SOURCES:
        for scoring in SCORINGS:
            ranked, key_by_name = unified.load_native_values(source, scoring, 12)
            keyed = {pos: [(key_by_name[unified.norm_player_name(n)], n, v) for n, v in rows]
                     for pos, rows in ranked.items()}
            for teams in (8, 10, 12, 14):
                if unified.translate_ranked(keyed, teams) != unified.translate_ranked(
                        keyed, teams, superflex_count=0):
                    problems.append(f"py {source}/{scoring}/{teams}t: superflex_count=0 differs")
    # Browser: SUPERFLEX:0 must plot exactly the server reference for the
    # default roster (saved values at 12 teams, the derivation elsewhere).
    probe = [(s, sc, t, "sf0", {**SAVED_SHAPE, "SUPERFLEX": 0})
             for s in SOURCES for sc in SCORINGS for t in (8, 10, 12, 14)]
    results = run_js(_cases(fixture, pos_of, probe), model_path)
    for (s, sc, t, _label, _shape), r in zip(probe, results):
        tag = f"js {s}/{sc}/{t}t"
        if r.get("error"):
            problems.append(f"{tag}: error {r['error']}")
            continue
        if r["savedSetup"] != (t == 12):
            problems.append(f"{tag}: savedSetup {r['savedSetup']} with SUPERFLEX:0")
        got = {int(k): v for k, v in r["values"].items()}
        diffs, _ = compare_maps(expected_derived(s, sc, t, SAVED_SHAPE, fixture, pos_of), got)
        if diffs:
            problems.append(f"{tag}: SUPERFLEX:0 differs from the default roster: {diffs[:2]}")
    return problems


def mutated(name, old, new):
    source = VALUE_MODEL.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(f"mutation anchor for {name} moved")
    path = Path(tempfile.mkdtemp()) / f"value-model-{name}.js"
    path.write_text(source.replace(old, new))
    return path


class SuperflexEngine(unittest.TestCase):
    def test_superflex_zero_is_the_default_engine(self):
        problems = identity_problems()
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_identity_guard_catches_a_superflex_default(self):
        broken = mutated("sf-default-1", "return n > 0 ? n : 0;", "return n > 0 ? n : 1;")
        problems = identity_problems(broken)
        print(f"\n[SUPERFLEX negative] default-1: {len(problems)} problems")
        self.assertGreater(len(problems), 0)

    def test_superflex_slot_goes_to_quarterbacks(self):
        problems = qb_problems()
        self.assertEqual(problems, [], "\n".join(problems))

    def test_qb_guard_catches_slot_weighting_and_surplus(self):
        # The old flex rule: superflex seats apportioned by dedicated-slot
        # weight (QB 1 of 7), so QBs get ~1/7 of them.
        slot_weighted = mutated(
            "sf-slot-weighted",
            "    if (!ranked) {\n      var w = {};\n      POSITION_ORDER.forEach(function (pos) { w[pos] = slots[pos] || 0; });",
            "    if (true) {\n      var w = {};\n      POSITION_ORDER.forEach(function (pos) { w[pos] = slots[pos] || 0; });")
        # The pre-2026-10-08 projectionRoles rule: superflex ranked on surplus.
        on_surplus = mutated(
            "sf-surplus",
            "remaining(SUPERFLEX_ELIGIBLE, rankOf)",
            "remaining(SUPERFLEX_ELIGIBLE, surplus)")
        for name, path in (("slot-weighted", slot_weighted), ("surplus", on_surplus)):
            problems = qb_problems(path)
            print(f"\n[SUPERFLEX negative] {name}: {len(problems)} problems, e.g. {problems[:1]}")
            self.assertGreater(len(problems), 0, f"{name} was NOT caught")


# ---------------------------------------------------------------- live page
SET_SF = """(n) => { const c = window.TradeValueCurveControls;
  c.setScoring('ppr'); c.setTeams(12); c.setRosterSpot('SUPERFLEX', n);
  return c.getRosterShape().SUPERFLEX; }"""
READ = """(keys) => {
  const maps = window.TradeValueCurveHarness.sourceMaps();
  const out = {fixedPie: (window.TradeValueCurveDiagnostics || {}).fixedPieIndexed, maps: {}};
  keys.forEach(k => { out.maps[k] = Object.fromEntries([...(maps.get(k) || new Map()).entries()]); });
  return out;
}"""


def collect_page(widget_override=None):
    from tests.test_published_league_settings_render import _chromium_executable, _server
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {}
    with _server() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            page = browser.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            if widget_override is not None:
                page.route("**/assets/curve-widget.js*", lambda route: route.fulfill(
                    status=200, content_type="text/javascript", body=widget_override))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueCurveHarness && window.TradeValueCurveDiagnostics",
                                   timeout=20000)
            out["clamp"] = page.evaluate(SET_SF, 5)
            out["sf1"] = page.evaluate(READ, list(SOURCES) + ["espn"])
            out["zero"] = page.evaluate(SET_SF, 0)
            # The classic page's roster input drives the same setter.
            out["has_input"] = page.evaluate("""() => { const i = document.querySelector('[data-roster-key="SUPERFLEX"]');
              if (!i) return false; i.value = 1; i.dispatchEvent(new Event('change'));
              return window.TradeValueCurveControls.getRosterShape().SUPERFLEX === 1; }""")
            out["errors"] = errors
        finally:
            browser.close()
    return out


def page_problems(got):
    problems = [f"page error: {e[:200]}" for e in got["errors"]]
    if got["clamp"] != 1:
        problems.append(f"setRosterSpot('SUPERFLEX', 5) left SUPERFLEX={got['clamp']}, want 1 (clamped)")
    if got["zero"] != 0:
        problems.append(f"setRosterSpot('SUPERFLEX', 0) left SUPERFLEX={got['zero']}")
    if got["has_input"] is not True:
        problems.append("no working Superflex roster input on the classic page")
    if got["sf1"]["fixedPie"] is not True:
        problems.append(f"fixedPieIndexed {got['sf1']['fixedPie']} with superflex")
    # JEG-508 (VP-0 "Superflex", VP-6.4): with the slot, each chart's
    # Indexed values are its natives WITH the publisher's superflex overlay
    # times one factor (against blended DDF Value, no longer the ESPN
    # anchor). So every listed player's value / overlay native is one
    # constant, and every overlay player is plotted.
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    for source in SOURCES:
        values = {int(k): v for k, v in got["sf1"]["maps"][source].items()}
        native, _saved, _ = browser_inputs(fixture, pos_of, source, "ppr", superflex=True)
        native = {k: v for k, v in native if v > 0}
        missing = sorted(set(native) - set(values))
        if missing:
            problems.append(f"superflex {source}: listed players not plotted {missing[:5]}")
        ratios = [values[k] / v for k, v in native.items() if k in values]
        if not ratios or max(ratios) - min(ratios) > 1e-9 * max(ratios):
            problems.append(f"superflex {source}: Indexed is not one factor on the superflex natives "
                            f"(ratios {min(ratios or [0]):.6f}..{max(ratios or [0]):.6f})")
    return problems


class SuperflexPage(unittest.TestCase):
    def test_live_page_superflex_control(self):
        problems = page_problems(collect_page())
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_page_guard_catches_missing_roster_key(self):
        # The pre-change widget: no SUPERFLEX roster key, so setRosterSpot
        # ignores it and the classic page has no Superflex input.
        widget = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        broken = widget.replace("FLEX:1, SUPERFLEX:0, BENCH:6", "FLEX:1, BENCH:6").replace(
            '      ["SUPERFLEX", "Superflex"],\n', "")
        self.assertNotEqual(broken, widget)
        self.assertNotIn('["SUPERFLEX", "Superflex"]', broken)
        problems = page_problems(collect_page(broken))
        print(f"\n[SUPERFLEX negative] no roster key: {len(problems)} problems, e.g. {problems[:1]}")
        self.assertGreater(len(problems), 0)


if __name__ == "__main__":
    unittest.main()
