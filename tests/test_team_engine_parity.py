"""JEG-1539 (lane team): team, explore and partners show the engine's numbers for a seeded league.

What we guard, at 3 scorings x 10/12 teams x superflex off/on (12 settings), against an independent read in the same
browser (TradeValueCurveControls rows, TradeValueFinder.lineupValue / withChartAverage / matchNames, and the published
tier rules recomputed here, not through DDF.league):
- team.html: starter and roster totals, per-position tier labels (league per-slot medians, 125% cap, 110% / 90%),
  every league-table cell and its rank tier (thirds of the team count);
- explore.html: every player's DDF and Analyst charts value, and the heading count equals the number of toggles;
- partners.html: every partner's starter DDF / Analyst values (Details toggle) and its DDF edge / Analyst premium / Live market premium
  tags (15% edge rule); my team and waivers are never a partner.
Discrimination: the same check fails when ddf-league.js is served with a 0.1 drift on one team's starter value.
Nav: with only ddf:pasted, the workspace pages show the post-league nav; with nothing set they show Get started.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST, serve

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = [(s, t, sf) for s in ("standard", "half_ppr", "ppr") for t in (10, 12) for sf in (False, True)]
PAGES = ("team.html", "explore.html", "partners.html")


def seeded_league() -> dict:
    """12 teams snake-drafted from the frozen player table: even picks by key, odd picks by name only, plus a kicker."""
    rows = [r.split("|") for r in json.loads((ROOT / "app/next/players-table-1.json").read_text())]
    rows = [r for r in rows if len(r) > 3 and r[1] in ("QB", "RB", "WR", "TE") and r[3]][:180]
    teams = [{"name": "My Squad" if i == 0 else f"Team {i + 1:02d}", "players": [], "unmatched": []} for i in range(12)]
    for n, r in enumerate(rows):
        rnd, pos = divmod(n, 12)
        i = pos if rnd % 2 == 0 else 11 - pos
        teams[i]["players"].append({"name": r[0], "key": r[3] if n % 2 == 0 else None, "pos": r[1], "team": r[2]})
    for t in teams:
        t["players"].append({"name": "Some Kicker", "key": None, "pos": "K"})
    return {"v": 1, "source": "paste", "site": "espn", "me": 0, "teams": teams}


def seed_script(league: dict | None) -> str:
    body = f"sessionStorage.setItem('ddf:pasted', {json.dumps(json.dumps(league))});" if league else ""
    return ("(function(){ try { if (sessionStorage.getItem('t-seeded')) return; localStorage.clear(); sessionStorage.clear();"
            f" sessionStorage.setItem('t-seeded','1'); {body} }} catch(_){{}} }})()")


READY = "() => window.DDF && DDF.league && DDF.league.current && DDF.league.current() !== null"
APPLY = "([scoring, teams, sf]) => { DDF.engine.apply({scoring, teams, superflex: sf}); return DDF.engine.settings(); }"

# Independent oracle: engine rows + finder module + the published rules, recomputed here.
ORACLE = r"""(league) => {
  const F = window.TradeValueFinder, C = window.TradeValueCurveControls;
  const fx = v => (typeof v === 'number' && isFinite(v)) ? v.toFixed(1) : '—';
  const POS = ['QB', 'RB', 'WR', 'TE'];
  const rows = C.getAllRows().filter(r => POS.includes(r.pos));
  const byKey = new Map(rows.map(r => [String(r.player_key), r]));
  const shape = C.getRosterShape();
  const teams = league.teams.map((t, i) => {
    const got = [];
    t.players.forEach(e => {
      let r = e.key ? byKey.get(String(e.key)) : null;
      if (!r && e.name) r = F.matchNames([{name: e.name, pos: e.pos || ''}], rows).matched[0] || null;
      if (r && !got.includes(r)) got.push(r);
    });
    const L = F.lineupValue(got, shape, 'ddf_value');
    const A = F.lineupValue(F.withChartAverage(got, ['cbs', 'usatoday', 'fantasypros']), shape, F.MARKET_KEY);
    const V = F.lineupValue(got, shape, 'fantasycalc');
    return {i, name: t.name, rows: got, L, A, V};
  }).filter(t => t.rows.length);
  const med = vals => { const s = vals.slice().sort((a, b) => a - b), m = s.length >> 1; return s.length ? (s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2) : null; };
  const SLOTS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX'];
  const medians = {};
  SLOTS.forEach(p => { medians[p] = []; for (let k = 0; k < (shape[p] || 0); k++) { const v = teams.map(t => t.L.slots[p][k]).filter(Boolean).map(r => r.values.ddf_value); medians[p].push(v.length ? med(v) : null); } });
  const tierOf = r => r >= 1.10 ? 'strong' : r >= 0.90 ? 'average' : 'weak';
  const mine = teams.find(t => t.i === league.me);
  const posTiers = {};
  SLOTS.forEach(p => {
    let score = 0, ms = 0;
    medians[p].forEach((m, k) => { if (m === null) return; const r = mine.L.slots[p][k]; const v = r ? r.values.ddf_value : 0; score += Math.min(v, 1.25 * m); ms += m; });
    if (ms > 0) posTiers[p] = tierOf(score / ms);
  });
  const n = teams.length, a = Math.round(n / 3), b = Math.round(2 * n / 3);
  const cols = {starter: t => t.L.starterValue, analystStarter: t => t.A.starterValue, roster: t => t.L.total, analystRoster: t => t.A.total};
  const table = {};
  teams.forEach(t => {
    table[t.name] = {};
    Object.keys(cols).forEach(c => {
      const rank = 1 + teams.filter(o => cols[c](o) > cols[c](t)).length;
      table[t.name][c] = [fx(cols[c](t)), rank <= a ? 'Strong' : rank <= b ? 'Average' : 'Weak'];
    });
  });
  const avg = new Map(F.withChartAverage(mine.rows, ['cbs', 'usatoday', 'fantasypros']).map(r => [String(r.player_key), r.values[F.MARKET_KEY]]));
  const explore = {};
  mine.rows.forEach(r => { explore[String(r.player_key)] = [fx(r.values.ddf_value), fx(avg.get(String(r.player_key)))]; });
  const partners = {};
  teams.filter(t => t !== mine).forEach(t => {
    const d = t.L.starterValue, an = t.A.starterValue, lv = t.V.starterValue, tags = [];
    // An incomplete chart lineup (a starter the charts do not list) is not judged and shows no chart total.
    const aOk = t.A.unvalued.length === 0, lOk = t.V.unvalued.length === 0;
    if (aOk && an > 0 && d / an >= 1.15) tags.push('DDF edge');
    if (aOk && an > 0 && d / an < 1) tags.push('Analyst premium');
    if (lOk && lv > 0 && d / lv < 1) tags.push('Live market premium');
    partners[t.name] = {ddf: fx(d), analyst: aOk ? fx(an) : '—', tags};
  });
  return {starter: fx(mine.L.starterValue), roster: fx(mine.L.total), posTiers, table, explore, partners};
}"""

READ_TEAM = r"""() => {
  const num = el => el ? el.textContent.trim() : '';
  const posTiers = {};
  document.querySelectorAll('#pos-grid tr[data-pos]').forEach(tr => { posTiers[tr.dataset.pos] = tr.dataset.tier; });
  const table = {};
  document.querySelectorAll('#league-rows tr[data-team]').forEach(tr => {
    const td = [...tr.cells];
    const name = td[0].childNodes[0].textContent.trim();
    const cell = c => [c.querySelector('.cell > span').textContent.replace('*', '').trim(), c.querySelector('.tier').textContent.trim()];
    table[name] = {starter: cell(td[1]), analystStarter: cell(td[2]), roster: cell(td[3]), analystRoster: cell(td[4])};
  });
  return {starter: num(document.getElementById('val-starter')), roster: num(document.getElementById('val-roster')), posTiers, table};
}"""

READ_EXPLORE = r"""() => {
  const explore = {};
  document.querySelectorAll('#roster-rows tr.prow').forEach(tr => {
    explore[tr.dataset.key] = [tr.querySelector('td.ddf').textContent.trim(), tr.querySelector('td.mkt').childNodes[0].textContent.trim()];
  });
  return {explore, heading: Number(document.getElementById('trade-n').textContent), toggles: document.querySelectorAll('#roster-rows input[type=checkbox]').length,
    total: Number(document.getElementById('sel-total').textContent)};
}"""

READ_PARTNERS = r"""() => {
  const partners = {};
  // JEG-1560: the values sit in each partner's Details toggle; the old tag keys ride on data-tags (labels renamed).
  const NAMES = {edge: 'DDF edge', analyst: 'Analyst premium', live: 'Live market premium'};
  document.querySelectorAll('#team-list .pt-row').forEach(r => {
    partners[r.querySelector('.tn').textContent.trim()] = {ddf: r.querySelector('[data-v=ddf]').textContent.trim(),
      analyst: r.querySelector('[data-v=analyst]').textContent.trim(), tags: (r.dataset.tags || '').split(' ').filter(Boolean).map(k => NAMES[k])};
  });
  return {partners, waiversRow: !!document.querySelector('#team-list [data-waivers]')};
}"""


def _browser(pw):
    try:
        return pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Chromium not available: {exc}") from exc


def _open(browser, base, page_name, league):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(lambda u: not u.startswith(base), lambda route: route.abort())
    page.add_init_script(seed_script(league))
    page.goto(f"{base}/{page_name}", wait_until="networkidle", timeout=60000)
    return page, errors


def run_parity(overrides=None, settings=None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    if not all((DIST / p).exists() for p in PAGES + ("ddf-league.js",)):
        raise _render_env.unavailable("dist workspace pages are not built")
    league = seeded_league()
    errors: list[str] = []
    with serve(DIST, overrides) as base, sync_playwright() as pw:
        browser = _browser(pw)
        try:
            for page_name in PAGES:
                page, page_errors = _open(browser, base, page_name, league)
                page.wait_for_function(READY, timeout=30000)
                for scoring, teams, sf in settings or SETTINGS:
                    label = f"{page_name} {scoring}/{teams}/{'sf' if sf else 'no-sf'}"
                    page.evaluate(APPLY, [scoring, teams, sf])
                    want = page.evaluate(ORACLE, league)
                    if page_name == "team.html":
                        got = page.evaluate(READ_TEAM)
                        for k in ("starter", "roster", "posTiers", "table"):
                            if got[k] != want[k]:
                                errors.append(f"{label}: {k} page={got[k]} engine={want[k]}")
                    elif page_name == "explore.html":
                        got = page.evaluate(READ_EXPLORE)
                        if got["explore"] != want["explore"]:
                            diff = {k: (got["explore"].get(k), v) for k, v in want["explore"].items() if got["explore"].get(k) != v}
                            errors.append(f"{label}: explore rows differ {dict(list(diff.items())[:5])} (page {len(got['explore'])}, engine {len(want['explore'])})")
                        if not (got["heading"] == got["toggles"] == got["total"] == len(want["explore"])):
                            errors.append(f"{label}: heading {got['heading']} toggles {got['toggles']} total {got['total']}")
                    else:
                        got = page.evaluate(READ_PARTNERS)
                        if got["partners"] != want["partners"]:
                            diff = {k: (got["partners"].get(k), v) for k, v in want["partners"].items() if got["partners"].get(k) != v}
                            errors.append(f"{label}: partners differ {dict(list(diff.items())[:3])}")
                        if "My Squad" in got["partners"] or got["waiversRow"]:
                            errors.append(f"{label}: my team or waivers listed as a partner")
                errors.extend(f"{page_name}: page error {e}" for e in page_errors)
                page.close()
        finally:
            browser.close()
    return errors


NAV = r"""() => ({gs: !!document.querySelector('.ddf-gs'), chip: !!document.querySelector('.ddf-chipwrap'),
  team: !!document.querySelector('header nav[aria-label="Main navigation"] > a[href="team.html"]'), league: document.documentElement.getAttribute('data-league')})"""


class TeamEngineParityTest(unittest.TestCase):
    def test_all_12_settings_match_engine(self):
        errors = run_parity()
        self.assertEqual(errors, [], "\n".join(errors[:20]))

    def test_guard_fails_on_small_drift(self):
        src = (DIST / "ddf-league.js").read_text() if (DIST / "ddf-league.js").exists() else None
        if src is None:
            raise _render_env.unavailable("dist/ddf-league.js not built")
        needle = "starterValue: L.starterValue, benchValue"
        self.assertIn(needle, src)
        drifted = src.replace(needle, "starterValue: L.starterValue + (team && team.index === 3 ? 0.1 : 0), benchValue")
        errors = run_parity({"ddf-league.js": drifted.encode()}, settings=[("ppr", 12, False)])
        self.assertTrue(any("table" in e or "partners" in e for e in errors), f"drift not caught: {errors[:5]}")

    def test_nav_follows_pasted_league(self):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
        league = seeded_league()
        with serve(DIST) as base, sync_playwright() as pw:
            browser = _browser(pw)
            try:
                for page_name in PAGES:
                    page, _ = _open(browser, base, page_name, league)
                    page.wait_for_function(READY, timeout=30000)
                    page.wait_for_function("() => document.documentElement.getAttribute('data-league') === 'loaded'", timeout=5000)
                    nav = page.evaluate(NAV)
                    self.assertEqual((nav["gs"], nav["chip"], nav["team"]), (False, True, True), f"{page_name} with ddf:pasted: {nav}")
                    page.close()
                    page, _ = _open(browser, base, page_name, None)
                    page.wait_for_function("() => window.DDF && DDF.league && DDF.league.ready", timeout=30000)
                    page.evaluate("() => DDF.league.ready")
                    nav = page.evaluate(NAV)
                    self.assertEqual((nav["gs"], nav["chip"]), (True, False), f"{page_name} with no league: {nav}")
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
