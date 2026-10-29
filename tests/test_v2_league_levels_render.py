"""The page's two bench levels against the Python reference, in a browser (JEG-1188, Codex review of #1105).

Browser parity. The built page (served the way pipelines/value_check.py serves it) runs
TradeValueCurveControls.getLeagueLevel with the USO and Charlotte rosters from
tests/fixtures/league_levels at both levels. pipelines/value_reference.py computes the same
settings on the same inputs and the same pinned day. Required, exactly as value_check does:
  * with no league, every player's DDF Value agrees (value_check's own gate, rechecked here so a
    data skew between the page and the reference fails loudly instead of reading as a level bug);
  * at each level, every player's DDF Value agrees within value_check's tolerance;
  * per position, starters, bench, held, reserve, replacement and the bench basis are equal;
  * getAllRows (what Compare a trade and the pair finder read) is unchanged after the levels run.

Rendered states (league page, the frozen USO rosters as 12 teams):
  * no league: no level block and no "null" text;
  * every team loaded, his team chosen: the basis note and three separate counts (bench seats in the
    settings, active depth beyond starters, players beyond starters above the best free agent), each
    count equal to the page's own level counts;
  * no team chosen: the note and the counts, no sell list;
  * one team missing: the standard-bench note naming why, no counts, no sell list.

Needs Chromium (Playwright). Skips locally without it; CI sets RENDER_TESTS_REQUIRED.
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build, open_page

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import roster_convention as rc  # noqa: E402
import value_check as vc  # noqa: E402
import value_reference as ref  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "league_levels"
POSITIONS = ("QB", "RB", "WR", "TE")
SETTING = {"scoring": "half_ppr", "teams": 12, "superflex": 0}
COUNT_FIELDS = (("starters", "starters"), ("bench", "bench"), ("held", "held"), ("reserve", "reserve"),
                ("replacement", "replacement"), ("bench_basis", "benchBasis"))


def league(name: str):
    fx = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    players = [p for t in fx["league"]["teams"] for p in t["players"] if p.get("key")]
    rostered = sorted({p["key"] for p in players})
    reserve = sorted({p["key"] for p in players if rc.is_reserve_slot(p.get("slot"))})
    return fx, rostered, reserve


# Same resets as value_check's ENGINE_JS, then the rows with no league, at each level, and again after.
PAGE_LEVELS = """async ({rostered, reserve, scoring, teams}) => {
  const c = window.TradeValueCurveControls;
  const tab = document.querySelector('#viewModeTabs [data-view-mode="indexed"]');
  if (tab) tab.click();
  c.setScoring(scoring, false); c.setTeams(teams, false); c.setRosterSpot('SUPERFLEX', 0, false); c.setRosterSpot('QB', 1, false);
  const d = typeof c.getLineupSettingsDefaults === 'function' ? c.getLineupSettingsDefaults() : null;
  if (d && typeof c.setLineupSettings === 'function') c.setLineupSettings({...d, benchShareOverride: null, contentWeek: null}, false);
  if (typeof c.setBasis === 'function') c.setBasis({mode: 'default'}, false);
  const values = rows => Object.fromEntries(rows.map(r => [String(r.player_key), r.values.ddf_value]));
  const weights = () => JSON.stringify(c.getAdjustmentWeights());
  const out = {none: values(c.getAllRows()), weightsBefore: weights(), levels: {}};
  for (const level of ['ddf', 'market']) {
    const g = c.getLeagueLevel({rostered, reserve, level});
    out.levels[level] = {values: values(g.rows), counts: g.counts};
  }
  out.after = values(c.getAllRows());
  out.weightsAfter = weights();
  return out;
}"""


def value_mismatches(page: dict, reference: dict, tol: float = vc.TOL) -> list[str]:
    bad = []
    for key in sorted(set(page) | set(reference)):
        a, b = page.get(key), reference.get(key)
        if (a is None) != (b is None) or (a is not None and abs(a - b) > tol):
            bad.append(f"{key}: page {a}, reference {b}")
    return bad


def count_mismatches(page: dict, reference: dict) -> list[str]:
    bad = []
    for pos in POSITIONS:
        for ref_key, page_key in COUNT_FIELDS:
            a, b = (page.get(pos) or {}).get(page_key), (reference.get(pos) or {}).get(ref_key)
            if a != b:
                bad.append(f"{pos} {ref_key}: page {a}, reference {b}")
    return bad


def run_page(args_by_league: dict, today: str) -> dict:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
    from tests._dist_server import DIST, serve
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(p))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            with serve(DIST) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(today)};")
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=90000)
                out = {name: page.evaluate(PAGE_LEVELS, args) for name, args in args_by_league.items()}
                out["_errors"] = errors
                return out
        finally:
            browser.close()


def setUpModule():
    _render_env.ensure_built()


class TestBrowserParity(unittest.TestCase):
    def test_levels_match_the_python_reference(self):
        try:
            import playwright  # noqa: F401
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        from tests.test_week_history import _fixture_today
        today = _fixture_today()
        leagues = {name: league(name) for name in ("uso", "charlotte")}
        args = {name: {"rostered": r, "reserve": s, **{k: SETTING[k] for k in ("scoring", "teams")}}
                for name, (_, r, s) in leagues.items()}
        page = run_page(args, today)
        self.assertEqual(page["_errors"], [])
        inp = ref.Inputs.load(ref.FIXTURE, ref.PLAYERS, today=date.fromisoformat(today))
        hist = ref.History(ref.HISTORY)
        div = ref.load_divergence_exclusions(week=ref.freshness(inp)["current_week"])
        rows = lambda r: {str(k): v.get("ddf_value") for k, v in r["views"]["indexed"].items()}
        base = ref.compute(inp, SETTING, hist=hist, divergence_exclusions=div)
        for name, (_, rostered, reserve) in leagues.items():
            got = page[name]
            with self.subTest(league=name, level="none"):
                self.assertEqual(value_mismatches(got["none"], rows(base))[:5], [],
                                 "page and reference disagree with no league (value_check's own gate); fix that first")
            with self.subTest(league=name, check="Compare and pair finder rows unchanged"):
                self.assertEqual(value_mismatches(got["after"], got["none"], tol=0.0)[:5], [])
                self.assertEqual(got["weightsAfter"], got["weightsBefore"])
            for level in ("ddf", "market"):
                r = ref.compute(inp, {**SETTING, "league_rostered": rostered, "league_reserve": reserve,
                                      "bench_level": level}, hist=hist, divergence_exclusions=div)
                with self.subTest(league=name, level=level):
                    self.assertEqual(value_mismatches(got["levels"][level]["values"], rows(r))[:5], [])
                    self.assertEqual(count_mismatches(got["levels"][level]["counts"], r["pipeline"]["allocation"]), [])


SEED = """([teams, mine]) => {
  const W = window.TradeValueWorkspace, C = window.TradeValueCurveControls;
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  let ws = W.newWorkspace({name: 'Levels'});
  teams.forEach(t => { ws = W.ops.addTeam(ws, 'Team ' + t.id, {entries: t.players.filter(p => p.key).map(p => {
    const row = byKey.get(p.key);
    return {key: p.key, name: row ? row.name : p.name, pos: p.pos, slot: p.slot};
  })}); });
  const i = teams.findIndex(t => t.id === mine);
  if (i >= 0) ws = W.ops.setMyTeam(ws, ws.teams[i].id);
  W.store.replace(ws, 'replace');
  return ws.teams.length;
}"""

STATE = """() => {
  const L = window.TradeValueLeague, C = window.TradeValueCurveControls, text = id => { const n = document.getElementById(id); return n ? n.textContent : null; };
  return {block: !!document.getElementById('v2LgSell'), note: text('v2LgLevelsNote'),
    seats: text('v2LgCountSeats'), depth: text('v2LgCountDepth'), above: text('v2LgCountAbove'),
    sells: document.querySelectorAll('#v2LgSellList li').length,
    nullText: /\\bnull\\b/.test((document.getElementById('v2LgSummary') || {}).textContent || ''),
    teams: C.getState().teams, bench: C.getRosterShape().BENCH};
}"""

LEVEL_COUNTS = """([rostered, reserve]) => {
  const C = window.TradeValueCurveControls;
  return Object.fromEntries(['ddf', 'market'].map(level => [level, C.getLeagueLevel({rostered, reserve, level}).counts]));
}"""


def settle(page):
    page.wait_for_timeout(400)
    page.wait_for_function("() => window.TradeValueLeague && !window.TradeValueLeague.ui.running && !window.TradeValueLeague.ui.timer", timeout=600000)
    page.wait_for_timeout(200)


def pos_counts(counts: dict) -> str:
    return ", ".join(f"{pos} {counts[pos]['bench']}" for pos in POSITIONS)


class TestRenderedStates(unittest.TestCase):
    def test_states(self):
        fx, rostered, reserve = league("uso")
        teams = fx["league"]["teams"]
        problems = []
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=problems, tag="[levels] ")
            settle(page)
            empty = page.evaluate(STATE)
            self.assertFalse(empty["block"], "no league: no level block")
            self.assertFalse(empty["nullText"])

            page.evaluate(SEED, [teams, fx["mine"]])
            settle(page)
            full = page.evaluate(STATE)
            counts = page.evaluate(LEVEL_COUNTS, [rostered, reserve])
            self.assertEqual(full["teams"], len(teams))
            self.assertTrue(full["note"] and full["note"].startswith("Priced with your league's rosters"), full["note"])
            seats = int(full["bench"])
            self.assertEqual(full["seats"], f"Bench seats in your settings: {len(teams) * seats} ({seats} per team).")
            self.assertEqual(full["depth"], f"Active players beyond the starters, league-wide: {pos_counts(counts['market'])}.")
            self.assertEqual(full["above"], f"Players beyond the starters who beat the best free agent: {pos_counts(counts['ddf'])}.")
            self.assertTrue(all(counts["market"][p]["benchBasis"] == "rostered_depth" and counts["ddf"][p]["benchBasis"] == "above_replacement" for p in POSITIONS))
            self.assertFalse(full["nullText"])

            page.evaluate(SEED, [teams, None])
            settle(page)
            no_team = page.evaluate(STATE)
            self.assertTrue(no_team["block"] and no_team["depth"] and no_team["above"])
            self.assertEqual(no_team["sells"], 0)
            self.assertFalse(no_team["nullText"])

            page.evaluate(SEED, [teams[1:], fx["mine"]])
            settle(page)
            partial = page.evaluate(STATE)
            self.assertTrue(partial["note"] and partial["note"].startswith("Priced with the standard bench"), partial["note"])
            self.assertIn("not every team is loaded", partial["note"])
            self.assertIsNone(partial["depth"])
            self.assertEqual(partial["sells"], 0)
            self.assertFalse(partial["nullText"])
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()
