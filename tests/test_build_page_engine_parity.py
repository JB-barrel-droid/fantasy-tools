"""JEG-1537: build.html shows the engine's numbers for every settings combination.

For 3 scorings x 10/12 teams x superflex off/on (the league arriving the way a shared Compare link brings it:
?scoring=&teams=&roster=), with a two-team league saved in the live League tab's store and a 2-for-1 trade picked
from the two rosters, the test reads the page and compares it to the engine read directly from
TradeValueCurveControls (not through ddf-engine.js or the page script):

- every "Difference by source" row (DDF Value, CBS Sports, FantasyPros, USA Today, Analyst charts = mean of the three
  analyst charts the engine lists, Live market (FantasyCalc)): give, receive and net; a source is shown exactly when
  the engine lists every player in the trade for it;
- the verdict number equals the DDF Value row's net (Muse finding 3: one number for the verdict and its row);
- the roster pickers' DDF and ANALYST cells for both teams;
- the reference chart picker's sums are each chart's published (native, not filled-in) values from getInspection();
- the settings line names the scoring and team count the link carried, and no league setting is saved;
- no page errors.

Discrimination guard: a build-trade.js that nudges every DDF Value by 0.1 must fail the check.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST, serve

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = [(s, t, sf) for s in ("standard", "half_ppr", "ppr") for t in (10, 12) for sf in (False, True)]
SCORING_LABELS = {"standard": "Standard", "half_ppr": "Half PPR", "ppr": "Full PPR"}
READY = "() => document.body.classList.contains('build-live') && document.querySelector('#charts .tc-row') !== null"

TOP_KEYS_JS = """() => window.DDF.engine.ready.then(() => DDF.engine.players().filter(p => p.ddf !== null && p.cbs !== null)
  .sort((a, b) => b.ddf - a.ddf).slice(0, 24).map(p => p.key))"""

SEED_JS = """(keys) => {
  try { localStorage.clear(); sessionStorage.clear(); } catch (e) {}
  if (!keys) return;
  const team = (id, name, list) => ({id, name, entries: list.map(k => ({key: k}))});
  localStorage.setItem('ddf.v2.workspaces', JSON.stringify({v: 1, activeId: 'w', workspaces: [{id: 'w', name: 'Parity League', myTeamId: 'a',
    teams: [team('a', 'Team A', keys.filter((k, i) => i % 2 === 0)), team('b', 'Team B', keys.filter((k, i) => i % 2 === 1))]}]}));
}"""

READ_JS = r"""([give, get]) => {
  const C = window.TradeValueCurveControls;
  const finite = v => typeof v === 'number' && isFinite(v);
  const rows = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const listed = (r, k) => { const v = r.values || {}, e = r.estimated || {}; return finite(v[k]) && !e[k] ? v[k] : null; };
  const analyst = r => { const a = ['cbs', 'usatoday', 'fantasypros'].map(k => listed(r, k)); return a.every(x => x !== null) ? (a[0] + a[1] + a[2]) / 3 : null; };
  const VAL = {'DDF Value': r => finite(r.values.ddf_value) ? r.values.ddf_value : null, 'CBS Sports': r => listed(r, 'cbs'),
    'FantasyPros': r => listed(r, 'fantasypros'), 'USA Today': r => listed(r, 'usatoday'), 'Analyst charts': analyst,
    'Live market (FantasyCalc)': r => listed(r, 'fantasycalc')};
  const sum = (keys, f) => { let t = 0; for (const k of keys) { const v = f(rows.get(String(k))); if (v === null) return null; t += v; } return t; };
  const expected = {};
  Object.keys(VAL).forEach(name => { const g = sum(give, VAL[name]), r = sum(get, VAL[name]); if (g !== null && r !== null) expected[name] = {give: g, recv: r, net: r - g}; });
  const num = t => Number(String(t).replace('−', '-').replace('+', '').trim());
  const page = {};
  document.querySelectorAll('#charts .tc-row').forEach(row => {
    page[row.querySelector('.tc-src strong').textContent] = {give: num(row.querySelector('.tc-c-give').textContent),
      recv: num(row.querySelector('.tc-c-recv').textContent), net: num(row.querySelector('.tc-net b').textContent)};
  });
  const big = document.querySelector('.tc-big');
  const cells = [];
  document.querySelectorAll('#give-picker tr[data-key], #get-picker tr[data-key]').forEach(tr => {
    const r = rows.get(tr.dataset.key), td = tr.querySelectorAll('td');
    const f = v => v === null ? '—' : v.toFixed(2);
    cells.push({key: tr.dataset.key, ddf: td[2].textContent, ddfEng: f(VAL['DDF Value'](r)), an: td[3].textContent, anEng: f(analyst(r))});
  });
  const ins = C.getInspection();
  const pub = (k, keys) => { let t = 0; for (const key of keys) { const p = ins.players[k] && ins.players[k][String(key)]; if (!p || p.estimated || !finite(p.native)) return null; t += p.native; } return t; };
  const charts = ['cbs', 'usatoday', 'fantasypros', 'fantasycalc'].map(k => {
    const e = window.DDFBuild.chartEval(k);
    return {k, pageGive: e.give, pageGet: e.get, engGive: pub(k, give), engGet: pub(k, get)};
  });
  return {expected, page, verdict: big ? Number(big.dataset.tcCount) : null, cells, charts,
    settings: document.getElementById('settings-line').textContent, saved: localStorage.getItem('ddf.v2.league-settings')};
}"""


def _pw():
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright not available: {exc}") from exc
    return sync_playwright, PlaywrightError


def run_parity(overrides=None, settings=SETTINGS):
    sync_playwright, PlaywrightError = _pw()
    errors = []
    with serve(DIST, overrides=overrides) as base, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_render_env.chromium_executable(pw))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium not available: {exc}") from exc
        try:
            boot = browser.new_page()
            boot.add_init_script(f"({SEED_JS})(null)")
            boot.goto(f"{base}/build.html", wait_until="load", timeout=60000)
            keys = boot.evaluate(TOP_KEYS_JS)
            boot.close()
            mine, theirs = keys[0::2], keys[1::2]
            give, get = [mine[2], mine[5]], [theirs[3]]
            for scoring, teams, sf in settings:
                label = f"{scoring}/{teams}/{'SF' if sf else '1QB'}"
                page = browser.new_page(viewport={"width": 1440, "height": 900})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.add_init_script(f"({SEED_JS})({keys!r})".replace("'", '"'))
                roster = f"QB1.RB2.WR3.TE1.FLEX1.SF{1 if sf else 0}.BN6"
                url = (f"{base}/build.html?mode=league&give={give[0]}&give={give[1]}&get={get[0]}"
                       f"&scoring={scoring}&teams={teams}&roster={roster}")
                page.goto(url, wait_until="load", timeout=60000)
                try:
                    page.wait_for_function(READY, timeout=60000)
                except PlaywrightError as exc:
                    errors.append(f"{label}: page never became live: {str(exc).splitlines()[0]}")
                    page.close()
                    continue
                snap = page.evaluate(READ_JS, [give, get])
                exp, got = snap["expected"], snap["page"]
                if len(exp) < 4 or not any(ch["engGive"] is not None and ch["engGet"] is not None for ch in snap["charts"]):
                    errors.append(f"{label}: vacuous check ({len(exp)} sources, charts {snap['charts']})")
                if set(exp) != set(got):
                    errors.append(f"{label}: sources page={sorted(got)} engine={sorted(exp)}")
                for name, e in exp.items():
                    g = got.get(name)
                    if not g:
                        continue
                    for part in ("give", "recv", "net"):
                        if f"{g[part]:.2f}" != f"{e[part]:.2f}":
                            errors.append(f"{label} {name} {part}: page {g[part]:.2f} engine {e[part]:.2f}")
                ddf = exp.get("DDF Value")
                if not ddf or snap["verdict"] is None or abs(snap["verdict"] - ddf["net"]) > 5e-4:
                    errors.append(f"{label}: verdict {snap['verdict']} != DDF Value net {ddf and ddf['net']}")
                if len(snap["cells"]) < len(keys):
                    errors.append(f"{label}: {len(snap['cells'])} roster rows, want {len(keys)}")
                for c in snap["cells"]:
                    if c["ddf"] != c["ddfEng"] or c["an"] != c["anEng"]:
                        errors.append(f"{label} picker {c['key']}: DDF {c['ddf']} vs {c['ddfEng']}, ANALYST {c['an']} vs {c['anEng']}")
                for ch in snap["charts"]:
                    for side in ("Give", "Get"):
                        a, b = ch["page" + side], ch["eng" + side]
                        if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-9):
                            errors.append(f"{label} chart {ch['k']} {side}: page {a} published {b}")
                want = f"{SCORING_LABELS[scoring]} · {teams} teams · {'Superflex' if sf else '1 QB'}"
                if want not in snap["settings"]:
                    errors.append(f"{label}: settings line {snap['settings']!r}, want {want!r}")
                if snap["saved"] is not None:
                    errors.append(f"{label}: the link's league was saved: {snap['saved']}")
                errors.extend(f"{label} page error: {e}" for e in page_errors)
                page.close()
        finally:
            browser.close()
    return errors


def setUpModule():
    _render_env.ensure_built()


class BuildPageEngineParityTest(unittest.TestCase):
    def test_all_12_settings_match_engine(self):
        errors = run_parity()
        self.assertEqual(errors, [], "\n".join(errors[:20]))

    def test_guard_catches_a_wrong_number(self):
        src = (DIST / "build-trade.js").read_text(encoding="utf-8")
        anchor = "r.ddf = finite(r.ddf) ? r.ddf : null;"
        self.assertIn(anchor, src)
        patched = src.replace(anchor, "r.ddf = finite(r.ddf) ? r.ddf + 0.1 : null;", 1)
        errors = run_parity(overrides={"build-trade.js": patched.encode("utf-8")}, settings=SETTINGS[:1])
        self.assertTrue(any("DDF Value" in e or "picker" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
