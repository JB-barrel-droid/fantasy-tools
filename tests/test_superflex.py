"""Superflex roster spot (JEG332-SUPERFLEX-FLEX, option A, Jeremy 2026-10-08).

A superflex league has a DEDICATED superflex slot (roster key SUPERFLEX, 0 or
1 on the page), filled after the dedicated slots and before FLEX by the best
remaining player with QBs eligible -- without the per-position slot weight
that kept QBs out of a QB-eligible flex.

Checks, each proved against a broken state:

1. Default identity. SUPERFLEX 0 is the default and must reproduce the old
   engine exactly: the server translation with superflex_count=0 equals the
   omitted argument, on every saved published chart x scoring x team count,
   and the browser's superflexCount gives 0 slots for SUPERFLEX:0 and for a
   roster without the key (JEG-539; it used to run the retired
   derivePublishedSetup). Broken state: superflexCount defaulting to 1.
2. Superflex goes to quarterbacks on real projections. On the ESPN per-game
   projections the browser prices with, a 10- or 12-team superflex league
   starts 2 x teams QBs (the value pipeline's league allocation, VP-2.2;
   before JEG-539 the retired projectionRoles) and the server
   translation's superflex slots go to QBs. Broken state: the pipeline's
   superflex seats filled without QBs. (JEG-702, Jeremy 2026-10-16, Q1:
   "Both: point the checks at the live engine and retire the unused code."
   The browser translation port, translationRostered, was retired, and with
   it the Python == JS roster comparison and the slot-weighted mutation of
   that port.)
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
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines.vorp_translation import unified  # noqa: E402
from pipelines.vorp_translation.vorp_via_roster import rostered_for_teams  # noqa: E402
from tests.test_published_league_settings_engine import (  # noqa: E402
    FIXTURE, SAVED_SHAPE, SCORINGS, SOURCES, VALUE_MODEL, browser_inputs, browser_players,
)
from tests import _render_env  # noqa: E402
from tests._week_view import own_week_reads  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


APP = ROOT / "app" / "trade-value-chart"
SF_SHAPE = {**SAVED_SHAPE, "SUPERFLEX": 1}

# Node: the value pipeline's allocation on the ESPN projections, for a given
# value-model.js.
QB_DRIVER = r"""
const VM = require(process.argv[1]);
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const out = input.cases.map(c => {
  // The live engine's league allocation (VP-2.2, vpAllocate) on ESPN's
  // per-game projections, as the widget runs it (curve-widget runPipeline).
  const players = {}, values = {};
  c.players.forEach(p => { players[p[0]] = {pos: p[2], name: p[1]}; values[p[0]] = p[3]; });
  const result = VM.runValuePipeline({
    setting: {teams: c.teams, slots: {QB: c.shape.QB, RB: c.shape.RB, WR: c.shape.WR, TE: c.shape.TE},
      flex: c.shape.FLEX, superflex: VM.superflexCount(c.shape), bench_per_team: c.shape.BENCH,
      bench_share: 0.15, position_shares: null},
    players, sources: {espn: {family: "projection", status: "included", values, label: "ESPN"}},
    included: ["espn"]});
  return {allocation: result.allocation};
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
    """Superflex slots must go to QBs on real ESPN projections (the value
    pipeline's allocation in value-model.js, and the server translation)."""
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
        qb = (js["allocation"] or {}).get("QB") or {}
        if qb.get("starters") != 2 * teams:
            problems.append(f"{tag}: the value pipeline starts {qb.get('starters')} QBs, want {2 * teams}")
        ranked = {pos: [] for pos in ("QB", "RB", "WR", "TE")}
        for key, _name, pos, val in case["players"]:
            ranked[pos].append((str(key), val))
        for rows in ranked.values():
            rows.sort(key=lambda r: -r[1])
        py = rostered_for_teams(teams, 7, 1, ranked=ranked, superflex_count=1)
        if py["QB"]["superflex"] < teams:
            problems.append(f"{tag}: translation superflex slots to QB {py['QB']['superflex']} of {teams}")
    return problems


SF_COUNT_DRIVER = r"""
const VM = require(process.argv[1]);
const shapes = JSON.parse(require("fs").readFileSync(0, "utf8"));
process.stdout.write(JSON.stringify(shapes.map(s => VM.superflexCount(s))));
"""


def identity_problems(model_path=VALUE_MODEL, fixture=None):
    """SUPERFLEX 0 reproduces the default engine exactly (server and browser)."""
    problems = []
    for source in SOURCES:
        for scoring in SCORINGS:
            ranked, key_by_name = unified.load_native_values(
                source, scoring, 12, fixture_path=FIXTURE if fixture is None else fixture)
            keyed = {pos: [(key_by_name[unified.norm_player_name(n)], n, v) for n, v in rows]
                     for pos, rows in ranked.items()}
            for teams in (8, 10, 12, 14):
                if unified.translate_ranked(keyed, teams) != unified.translate_ranked(
                        keyed, teams, superflex_count=0):
                    problems.append(f"py {source}/{scoring}/{teams}t: superflex_count=0 differs")
    # Browser: the widget passes ValueModel.superflexCount(rosterShape) to
    # the value pipeline as setting.superflex (curve-widget pipelineSetting).
    # A roster without the key, and SUPERFLEX:0, must both give 0 superflex
    # slots; SUPERFLEX:1 gives 1. (Before JEG-539 this half ran the retired
    # derivePublishedSetup on every saved chart.)
    probe = [("no key", SAVED_SHAPE, 0), ("SUPERFLEX:0", {**SAVED_SHAPE, "SUPERFLEX": 0}, 0),
             ("SUPERFLEX:1", {**SAVED_SHAPE, "SUPERFLEX": 1}, 1)]
    proc = subprocess.run(["node", "-e", SF_COUNT_DRIVER, str(model_path)],
                          input=json.dumps([shape for _, shape, _ in probe]),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[:2000])
    for (label, _shape, want), got in zip(probe, json.loads(proc.stdout)):
        if got != want:
            problems.append(f"js superflexCount({label}) = {got}, want {want}")
    return problems


def mutated(name, old, new):
    source = VALUE_MODEL.read_text(encoding="utf-8")
    if source.count(old) != 1:
        raise AssertionError(f"mutation anchor for {name} moved")
    path = Path(tempfile.mkdtemp()) / f"value-model-{name}.js"
    path.write_text(source.replace(old, new))
    return path


class SuperflexEngine(unittest.TestCase):
    def test_identity_reads_the_supplied_fixture(self):
        # A missing isolated fixture must fail; silently reading the default
        # would make seeded-hold coverage a second unheld-baseline test.
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                identity_problems(fixture=Path(tmp) / "missing-fixture.json")

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

    def test_qb_guard_catches_no_qb_superflex(self):
        # The value pipeline's superflex seats filled without QBs (the
        # pre-superflex flex rule). Replaced the projectionRoles "surplus"
        # mutation when JEG-539 retired projectionRoles.
        no_qb = mutated(
            "sf-no-qb",
            "var sf = takeBest(POSITION_ORDER,",
            "var sf = takeBest(VP_FLEX_ELIGIBLE,")
        for name, path in (("no-qb", no_qb),):
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


def collect_page(widget_override=None, data_overrides=None):
    from tests.test_published_league_settings_render import _chromium_executable, _server
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {}
    if data_overrides is None:
        server = _server()
    else:
        from tests.test_week_history import _server as history_server
        server = history_server(data_overrides)
    with server as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            page = browser.new_page()
            if data_overrides and "assets/comparison-sources-data.json" in data_overrides:
                from tests.test_week_history import _fixture_today
                today = _fixture_today(json.loads(data_overrides["assets/comparison-sources-data.json"]))
                page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today)};")
            else:
                page.add_init_script(_render_env.pin_data_week_script())
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
            # JEG-1176: a chart lagging the default week view is read in its
            # own week's view, or noted as lagging when no view has its week.
            absent = [k for k in SOURCES if not out["sf1"]["maps"][k]]
            own = own_week_reads(page, absent, lambda keys: page.evaluate(READ, keys), "superflex",
                                 "superflex values not checked in the browser")
            for week, got in own["reads"].items():
                out["sf1"]["maps"].update(got["maps"])
            out["sf1"]["week_fixed_pie"] = {week: got["fixedPie"] for week, got in own["reads"].items()}
            out["sf1"]["lagging"] = own["lagging"]
            out["zero"] = page.evaluate(SET_SF, 0)
            # The classic page's roster input drives the same setter.
            out["has_input"] = page.evaluate("""() => { const i = document.querySelector('[data-roster-key="SUPERFLEX"]');
              if (!i) return false; i.value = 1; i.dispatchEvent(new Event('change'));
              return window.TradeValueCurveControls.getRosterShape().SUPERFLEX === 1; }""")
            out["errors"] = errors
        finally:
            browser.close()
    return out


def page_problems(got, fixture=None):
    problems = [f"page error: {e[:200]}" for e in got["errors"]]
    if got["clamp"] != 1:
        problems.append(f"setRosterSpot('SUPERFLEX', 5) left SUPERFLEX={got['clamp']}, want 1 (clamped)")
    if got["zero"] != 0:
        problems.append(f"setRosterSpot('SUPERFLEX', 0) left SUPERFLEX={got['zero']}")
    if got["has_input"] is not True:
        problems.append("no working Superflex roster input on the classic page")
    if got["sf1"]["fixedPie"] is not True:
        problems.append(f"fixedPieIndexed {got['sf1']['fixedPie']} with superflex")
    for week, fixed in sorted((got["sf1"].get("week_fixed_pie") or {}).items()):
        if fixed is not True:
            problems.append(f"fixedPieIndexed {fixed} with superflex in the Week {week} view")
    # JEG-508 (VP-0 "Superflex", VP-6.4): with the slot, each chart's
    # Indexed values are its natives WITH the publisher's superflex overlay
    # times one factor (against blended DDF Value, no longer the ESPN
    # anchor). So every listed player's value / overlay native is one
    # constant, and every overlay player is plotted.
    if fixture is None:
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pos_of = browser_players()
    for source in SOURCES:
        if source in (got["sf1"].get("lagging") or {}):
            continue  # older than every week view: noted on stderr by own_week_reads
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


class SuperflexPageGuard(unittest.TestCase):
    """Exercise the page checker without letting a hold mask a broken map."""

    def setUp(self):
        self.fixture = {"player_keys": {"a": 1, "b": 2}, "sources": {
            source: {"combos": {"full_12": {
                "native": {"a": 10, "b": 5}, "native_superflex": {"a": 20},
                "reindexed": {"a": 40, "b": 10},
            }}} for source in SOURCES}}
        self.got = {"errors": [], "clamp": 1, "zero": 0, "has_input": True,
                    "sf1": {"fixedPie": True, "maps": {
                        source: {"1": 40, "2": 10} for source in SOURCES}}}
        positions = patch(__name__ + ".browser_players", return_value={1: "QB", 2: "RB"})
        positions.start()
        self.addCleanup(positions.stop)

    def test_supplied_fixture_checks_its_own_superflex_natives(self):
        self.assertEqual(page_problems(self.got, self.fixture), [])
        self.fixture["sources"]["cbs"]["combos"]["full_12"]["native_superflex"]["a"] = 21
        self.assertTrue(any("superflex cbs: Indexed is not one factor" in p
                            for p in page_problems(self.got, self.fixture)))

    def test_holds_do_not_exempt_missing_or_corrupt_pipeline_maps(self):
        # sourceMaps is the pipeline harness, not the visible curves. A red
        # hold excludes a chart from display and DDF, but its priced rows
        # remain available here and still need the original numeric checks.
        for source in SOURCES:
            for hold in ({"reason": "chain hold"}, {"hold_level": "red"},
                         {"hold_level": "amber"}):
                with self.subTest(source=source, hold=hold):
                    self.fixture["sources"][source]["validationHold"] = hold
                    self.got["sf1"]["maps"][source] = {"1": 40, "2": 10}
                    self.assertEqual(page_problems(self.got, self.fixture), [])
                    self.got["sf1"]["maps"][source] = {"1": 40}
                    self.assertTrue(any(f"superflex {source}: listed players not plotted" in p
                                        for p in page_problems(self.got, self.fixture)))
                    self.got["sf1"]["maps"][source] = {"1": 41, "2": 10}
                    self.assertTrue(any(f"superflex {source}: Indexed is not one factor" in p
                                        for p in page_problems(self.got, self.fixture)))
                    self.got["sf1"]["maps"][source] = {"1": 40, "2": 10}
                    del self.fixture["sources"][source]["validationHold"]


class SuperflexPage(unittest.TestCase):
    def test_live_page_superflex_control(self):
        problems = page_problems(collect_page())
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_page_guard_catches_missing_roster_key(self):
        # The pre-change widget: no SUPERFLEX roster key, so setRosterSpot
        # ignores it and the classic page has no Superflex input.
        widget = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        broken = widget.replace("FLEX:1, SUPERFLEX:0, BENCH:7", "FLEX:1, BENCH:7").replace(
            '      ["SUPERFLEX", "Superflex"],\n', "")
        self.assertNotEqual(broken, widget)
        self.assertNotIn('["SUPERFLEX", "Superflex"]', broken)
        problems = page_problems(collect_page(broken))
        print(f"\n[SUPERFLEX negative] no roster key: {len(problems)} problems, e.g. {problems[:1]}")
        self.assertGreater(len(problems), 0)


if __name__ == "__main__":
    unittest.main()
