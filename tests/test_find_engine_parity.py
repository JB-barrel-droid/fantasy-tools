"""JEG-1539 (lane find): Trade & Waiver Recommendations and Waivers show the live search's results for a seeded league.

What we guard, at 3 scorings x 10/12 teams x superflex off/on (12 settings), with the seeded 12-team league of
tests.test_team_engine_parity: every offer card on find.html (section, partner, players given and received, your and
their starter change as printed) and every waiver pickup (player added, player dropped, gain as printed) equals an
independent run in the same browser of the live modules on engine rows: TradeValueFinder.findTrades / tradeFit /
groupTrades for each partner (the live league search's pairing) and TradeValueWaivers.evaluateAll (the live Waivers
tab), with the league read straight from sessionStorage, not through DDF.league or find-engine.js.
At one setting the same check also runs with other valuations (DDF (Projection based) for you, Live market for them),
and waivers.html's best adds are checked against the same waiver evaluation.
Discrimination: the check fails when find-engine.js is served with a 0.1 drift on your starter change.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._dist_server import DIST, serve
from tests.test_team_engine_parity import SETTINGS, seed_script, seeded_league

READY = "() => window.DDF && DDF.findPage && /^Searched|^$/.test(document.getElementById('search-status').textContent) && DDF.findPage.state.sig !== '' && !DDF.findPage.state.running"
APPLY = "async ([scoring, teams, sf]) => { await DDF.engine.ready; await DDF.league.ready; DDF.engine.apply({scoring, teams, superflex: sf}); return true; }"
SET = """([id, value]) => { const el = document.getElementById(id); el.value = value; el.dispatchEvent(new Event('change', {bubbles: true})); }"""

# The page's cards, as printed.
READ_PAGE = r"""() => {
  const cards = sel => [...document.querySelectorAll(sel + ' [data-offer]')].map(a => ({
    partner: a.dataset.partner, give: a.dataset.give, receive: a.dataset.receive,
    you: a.querySelector('.gain').textContent.trim(), them: a.querySelector('.mlab span:nth-child(2)').textContent.trim()}));
  const picks = [...document.querySelectorAll('#pickup-cards [data-pickup]')].map(a => ({add: a.dataset.add, drop: a.dataset.drop, gain: a.querySelector('.gain').textContent.trim()}));
  return {natural: cards('#natural-table'), neutral: cards('#all-table'), picks, status: document.getElementById('search-status').textContent};
}"""

# Independent run of the live modules. opts: {your, their, yourLabel, theirLabel, min, pageSize, cap}.
ORACLE = r"""(o) => {
  const F = window.TradeValueFinder, W = window.TradeValueWaivers, C = window.TradeValueCurveControls;
  const finite = v => typeof v === 'number' && isFinite(v);
  const shown = n => Math.abs(n) < 0.05 ? '0.0' : (n > 0 ? '+' : '−') + Math.abs(n).toFixed(1);
  const KEYS = {'DDF': 'ddf_value', 'DDF (Projection based)': 'ddf_value_projections', 'Market': 'chart_avg', 'FantasyCalc': 'fantasycalc'};
  const yourKey = KEYS[o.your], theirKey = KEYS[o.their];
  const league = JSON.parse(sessionStorage.getItem('ddf:pasted'));
  const POS = ['QB', 'RB', 'WR', 'TE'];
  const LISTED = ['cbs', 'usatoday', 'fantasypros', 'fantasycalc', 'espn', 'cbsros', 'razzball'];
  // The engine's priced players (the rows every page reads): QB/RB/WR/TE with a DDF Value or a listed source value.
  const rows = C.getAllRows().filter(r => POS.includes(r.pos) && r.values && (finite(r.values.ddf_value) || LISTED.some(k => finite(r.values[k]) && !(r.estimated || {})[k])));
  const byKey = new Map(rows.map(r => [String(r.player_key), r]));
  const resolve = p => {
    if (p.key && byKey.has(String(p.key))) return byKey.get(String(p.key));
    const hit = F.matchNames([{name: p.name, pos: p.pos || ''}], rows).matched[0];
    return hit || null;
  };
  const teams = league.teams.map((t, i) => {
    const seen = new Set();
    const priced = t.players.map(resolve).filter(r => r && !seen.has(String(r.player_key)) && seen.add(String(r.player_key)));
    return {index: i, name: t.name, rows: priced, specials: t.players.filter(p => !resolve(p) && ['K', 'DEF', 'DST'].includes(p.pos))};
  });
  const me = teams[league.me];
  const info = C.getSourceInfo();
  const available = new Set(info.filter(i => i.available).map(i => i.key));
  const gate = F.CHART_KEYS.filter(k => available.has(k));
  const analyst = ['cbs', 'usatoday', 'fantasypros'].every(k => available.has(k)) ? ['cbs', 'usatoday', 'fantasypros'] : null;
  const shape = C.getRosterShape();
  const expected = F.expectedDepth(C.getAdjustmentWeights().allocation, C.getState().teams);
  const readout = C.getBenchShareReadout ? C.getBenchShareReadout() : null;
  const weights = {overall: readout && finite(readout.overall) ? readout.overall : (C.getBenchShare ? C.getBenchShare() : 0)};
  F.DEPTH_POS.forEach(p => { if (readout && finite(readout[p])) weights[p] = readout[p]; });
  const widen = rs => analyst ? F.withChartAverage(rs, analyst) : rs;
  const groups = [];
  teams.filter(t => t.index !== league.me && t.rows.length).forEach(t => {
    const mine = yourKey === 'chart_avg' ? widen(me.rows) : me.rows, theirs = yourKey === 'chart_avg' ? widen(t.rows) : t.rows;
    const res = F.findTrades(mine, theirs, {ourKey: yourKey, chartKeys: gate, maxSize: 2, limit: Infinity,
      guardrails: {protectedPositions: [], minBackups: {QB: 0, RB: 0, WR: 0, TE: 0}, minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null, shape, mine, theirs, chartKeys: gate, ourKey: yourKey},
      sanity: {shape, mine, theirs, keepMine: true, keepTheirs: true}});
    const mineW = widen(me.rows), theirW = widen(t.rows);
    const wide = new Map(mineW.concat(theirW).map(r => [String(r.player_key), r]));
    const w = list => list.map(r => wide.get(String(r.player_key)) || r);
    const fitCtx = {shape, expected, weights, ourKey: yourKey, marketKey: theirKey, chartKeys: analyst || undefined, z: F.FIT_Z};
    const byCls = {};
    res.trades.forEach(tr => {
      const fit = F.tradeFit({mine: {roster: mineW, leaving: w(tr.give), arriving: w(tr.receive)}, theirs: {roster: theirW, leaving: w(tr.receive), arriving: w(tr.give)}}, fitCtx);
      const cls = fit.label === 'natural' ? 'natural' : fit.them.net >= -fit.them.tau ? 'neutral' : 'force';
      (byCls[cls] = byCls[cls] || []).push({...tr, you: fit.us.starterDelta, them: fit.them.starterDelta});
    });
    Object.keys(byCls).forEach(cls => F.groupTrades(byCls[cls], {ourKey: yourKey}).forEach(g => groups.push({...g, cls, partner: t.name, id: t.index + '|' + cls + '|' + g.key})));
  });
  const order = (a, b) => b.best.you - a.best.you || b.best.edge - a.best.edge || b.best.score - a.best.score || a.partner.localeCompare(b.partner) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0);
  const nat = groups.filter(g => g.cls === 'natural').sort(order), neu = groups.filter(g => g.cls === 'neutral').sort(order);
  const used = {}, per = {natural: 0, neutral: 0}, out = {natural: [], neutral: []};
  nat.concat(neu).forEach(g => {
    const ks = g.best.give.concat(g.best.receive).map(r => String(r.player_key));
    if (ks.some(k => (used[k] || 0) >= o.cap)) return;
    ks.forEach(k => { used[k] = (used[k] || 0) + 1; });
    if (++per[g.cls] <= o.pageSize) out[g.cls].push({partner: g.partner, give: g.best.give.map(r => String(r.player_key)).join(','), receive: g.best.receive.map(r => String(r.player_key)).join(','),
      you: shown(g.best.you), them: 'Them ' + shown(g.best.them) + ' ' + o.theirLabel});
  });
  // Waivers: my roster (with its kicker) against every priced player on no roster, judged in your valuation's view.
  const rostered = new Set([].concat(...teams.map(t => t.rows.map(r => String(r.player_key)))));
  const entries = me.rows.map(r => ({key: String(r.player_key), name: r.name, pos: r.pos, team: r.team || ''}))
    .concat(me.specials.map(p => ({key: 'x:' + p.pos + ':' + p.name, name: p.name, pos: p.pos, team: ''})));
  const cands = rows.filter(r => finite(r.values.ddf_value) && !rostered.has(String(r.player_key)))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value || String(a.player_key).localeCompare(String(b.player_key)))
    .map(r => ({key: String(r.player_key), name: r.name, pos: r.pos, team: r.team || ''}));
  const all = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const view = W.viewFor({'DDF': 'ddf', 'DDF (Projection based)': 'projections', 'Market': 'market', 'FantasyCalc': 'src:fantasycalc'}[o.your], null);
  const wres = W.evaluateAll({shape, weights, expected, chartKeys: analyst, rosterSize: W.rosterSizeOf(shape), byes: window.TradeValueByes ? window.TradeValueByes.byes : null,
    status: W.statusFreshness(window.TradeValueStatus || null, Date.now()), view}, W.rowsFor(entries, all).rows, W.rowsFor(W.dedupe(cands, entries).kept, all).rows);
  const g1 = r => Math.round(r.starterDelta * 10) / 10;
  const picks = wres.results.filter(r => r.starterDelta !== null && g1(r) > 0 && g1(r) >= o.min)
    .sort((a, b) => b.starterDelta - a.starterDelta || (b.totalDelta || 0) - (a.totalDelta || 0) || String(a.name).localeCompare(String(b.name)))
    .map(r => ({add: String(r.candidate.player_key), drop: r.drop ? String(r.drop.player_key) : '', gain: shown(r.starterDelta)}));
  return {natural: out.natural, neutral: out.neutral, picks, groups: groups.length};
}"""

# waivers.html's best adds, as printed.
READ_WAIVERS = r"""() => [...document.querySelectorAll('#adds [data-pickup]')].map(a => ({add: a.dataset.add, drop: a.dataset.drop, gain: a.querySelector('.wa-gain b').textContent.trim()}))"""

VALUATION_CASES = [("DDF", "Market", "Analyst charts"), ("DDF (Projection based)", "FantasyCalc", "Live market (FantasyCalc)")]


def _diff(label, page, want, errors):
    for part in ("natural", "neutral", "picks"):
        if page[part] != want[part]:
            first = next((i for i, (a, b) in enumerate(zip(page[part], want[part])) if a != b), min(len(page[part]), len(want[part])))
            errors.append(f"{label} {part}: page {len(page[part])} vs oracle {len(want[part])}, first difference at {first}: "
                          f"page={page[part][first] if first < len(page[part]) else None} oracle={want[part][first] if first < len(want[part]) else None}")


def _run(overrides=None, settings=None, extra=True):
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    if not (DIST / "find.html").exists():
        raise _render_env.unavailable("dist/find.html is not built")
    errors, sizes = [], []
    league = seeded_league()
    # My team's 2nd and 3rd round picks go back to the available players, so the waiver checks have pickups to compare.
    del league["teams"][league["me"]]["players"][1:3]
    with serve(overrides=overrides) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable())
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        try:
            for i, (scoring, teams, sf) in enumerate(settings or SETTINGS):
                label = f"scoring={scoring} teams={teams} sf={sf}"
                ctx = browser.new_context(viewport={"width": 1440, "height": 900})
                ctx.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                ctx.add_init_script(seed_script(league))
                page = ctx.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.goto(f"{base}/find.html", wait_until="domcontentloaded", timeout=60000)
                page.evaluate(APPLY, [scoring, teams, sf])
                page.wait_for_timeout(300)
                page.wait_for_function(READY, timeout=120000)
                cases = VALUATION_CASES if (extra and i == 0) else VALUATION_CASES[:1]
                for your, their, their_label in cases:
                    if your != "DDF":
                        page.evaluate(SET, ["your-valuation", your])
                        page.evaluate(SET, ["their-valuation", their])
                        page.wait_for_timeout(300)
                        page.wait_for_function(READY, timeout=120000)
                    page.evaluate(SET, ["minimum-gain", "0"])
                    got = page.evaluate(READ_PAGE)
                    want = page.evaluate(ORACLE, {"your": your, "their": their, "theirLabel": their_label, "min": 0, "pageSize": 10, "cap": 20})
                    sizes.append((label, your, len(got["natural"]), len(got["neutral"]), len(got["picks"]), want["groups"]))
                    _diff(f"{label} [{your} / {their}]", got, want, errors)
                if extra and i == 0:
                    wpage = ctx.new_page()
                    wpage.on("pageerror", lambda e: page_errors.append("waivers: " + str(e)))
                    wpage.goto(f"{base}/waivers.html", wait_until="domcontentloaded", timeout=60000)
                    wpage.wait_for_function("() => window.DDF && DDF.waiversPage && DDF.waiversPage.last()", timeout=120000)
                    wpage.evaluate(SET, ["adds-min", "0"])
                    got = wpage.evaluate(READ_WAIVERS)
                    want = wpage.evaluate(ORACLE, {"your": "DDF", "their": "Market", "theirLabel": "Analyst charts", "min": 0, "pageSize": 10, "cap": 20})["picks"]
                    if got != want:
                        errors.append(f"{label} waivers.html best adds: page {got[:3]} vs oracle {want[:3]} ({len(got)} vs {len(want)})")
                    if not want:
                        errors.append(f"{label} waivers: the oracle found no pickups, so the waiver check is vacuous")
                errors.extend(f"{label} page error: {e}" for e in page_errors)
                ctx.close()
        finally:
            browser.close()
    return errors, sizes


def setUpModule():
    _render_env.ensure_built()


class FindPageEngineParityTest(unittest.TestCase):

    def test_all_12_settings_match_the_live_search(self):
        errors, sizes = _run()
        self.assertEqual(errors, [], errors)
        # Not vacuous: offers in both sections and pickups somewhere.
        self.assertTrue(any(n for _, _, n, _, _, _ in sizes), sizes)
        self.assertTrue(any(n for _, _, _, n, _, _ in sizes), sizes)
        self.assertTrue(any(n for _, _, _, _, n, _ in sizes), sizes)

    def test_guard_fails_on_a_small_drift(self):
        path = DIST / "find-engine.js"
        if not path.exists():
            raise _render_env.unavailable("dist/find-engine.js is not built")
        src = path.read_text(encoding="utf-8")
        anchor = "you: fit ? fit.us.starterDelta : null"
        self.assertIn(anchor, src, "drift anchor not found in find-engine.js")
        patched = src.replace(anchor, "you: fit ? fit.us.starterDelta + 0.1 : null", 1)
        errors, _ = _run(overrides={"find-engine.js": patched.encode("utf-8")}, settings=SETTINGS[:1], extra=False)
        self.assertNotEqual(errors, [], "the parity check did not catch a 0.1 drift on your starter change")


if __name__ == "__main__":
    unittest.main()
