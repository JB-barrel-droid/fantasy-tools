"""JEG-1535: values.html shows the engine's numbers for every settings combination.

What we guard: every table row's DDF, CBS and Live market (FantasyCalc) cells
equal the corresponding engine row values to one decimal; the set of players on
the page equals the engine's QB/RB/WR/TE rows that have a finite ddf_value; the
Customize chip text reflects the active scoring and team count.

Also: the Buy / Sell tab's first 5 Buy rows show the right DDF and Charts values
(Charts = mean of listed indexed charts).

Discrimination guard: the check must fail when the page is served a modified
values-chart.js that inflates one DDF cell by 0.1, so the guard is not vacuous.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import re
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env
from tests._dist_server import DIST


ROOT = Path(__file__).resolve().parents[1]

SETTINGS = [
    ("standard", 10, False),
    ("standard", 10, True),
    ("standard", 12, False),
    ("standard", 12, True),
    ("half_ppr",  10, False),
    ("half_ppr",  10, True),
    ("half_ppr",  12, False),
    ("half_ppr",  12, True),
    ("ppr",       10, False),
    ("ppr",       10, True),
    ("ppr",       12, False),
    ("ppr",       12, True),
]

READY_EXPR = (
    "() => document.body.classList.contains('values-live') "
    "&& document.querySelector('#rows tr') !== null"
)

# Apply settings via the page's Customize controls and dispatch change events.
SET_CONTROLS_JS = """([scoring, teams, sf]) => {
  function fire(el) { el.dispatchEvent(new Event('change', {bubbles: true})); }
  const sel = id => document.getElementById(id);
  const sc = sel('set-scoring'); if (sc && sc.value !== scoring) { sc.value = scoring; fire(sc); }
  const st = sel('set-teams'); if (st && st.value !== String(teams)) { st.value = String(teams); fire(st); }
  const ss = sel('set-sf'); if (ss && ss.checked !== sf) { ss.checked = sf; fire(ss); }
}"""

# Click the "All" player-count button.
CLICK_ALL_JS = """() => {
  const b = document.querySelector('[data-count="All"]');
  if (b) b.click();
}"""

# Enable the FantasyCalc column.
ENABLE_FC_JS = """() => {
  const cb = document.getElementById('fantasycalc');
  if (cb && !cb.checked) {
    cb.checked = true;
    // values-chart.js listens for 'input', not 'change', on this checkbox.
    cb.dispatchEvent(new Event('input', {bubbles: true}));
  }
}"""

# Full snapshot: compare each visible table row against the engine.
# Uses DDFValues.D (exposed by values-chart.js) which mirrors the engine records.
READ_TABLE_JS = """() => {
  const C = window.TradeValueCurveControls;
  if (!C) return {error: 'no TradeValueCurveControls'};
  const DVals = window.DDFValues;
  if (!DVals || !DVals.D) return {error: 'no DDFValues.D'};
  const D = DVals.D;

  const finite = v => typeof v === 'number' && isFinite(v);
  const positions = new Set(['QB', 'RB', 'WR', 'TE']);
  const fx = v => v === null || v === undefined ? '—' : v.toFixed(1);

  /* ---- engine map: player_key -> {ddf, cbs, fc} ---- */
  const engineMap = {};
  C.getAllRows().forEach(row => {
    if (!positions.has(row.pos)) return;
    const v = row.values || {}, est = row.estimated || {};
    const ddf = finite(v.ddf_value) ? v.ddf_value : null;
    if (ddf === null) return;
    engineMap[String(row.player_key)] = {
      ddf,
      cbs: finite(v.cbs) && !est.cbs ? v.cbs : null,
      fc:  finite(v.fantasycalc) && !est.fantasycalc ? v.fantasycalc : null,
    };
  });

  /* ---- DDFValues.D: name -> record (for table row lookup) ---- */
  const nameMap = new Map(D.map(r => [r.n, r]));

  /* ---- column positions from header ---- */
  const thKeys = [...document.querySelectorAll('#head th')].map(th => {
    const b = th.querySelector('[data-key]'); return b ? b.dataset.key : null;
  });
  const ci = k => thKeys.indexOf(k);
  const colDdf = ci('ddf'), colCbs = ci('cbs'), colFc = ci('fc');

  /* ---- iterate visible table rows ---- */
  const rows = [];
  document.querySelectorAll('#rows tr[data-i]').forEach(tr => {
    const cells = [...tr.querySelectorAll('td')];
    /* player name from aria-label: "PlayerName, details on focus" or "PlayerName, your override, details on focus" */
    const rawLabel = tr.getAttribute('aria-label') || '';
    const name = rawLabel.replace(/(, your override)?, details on focus$/, '');
    const rec = nameMap.get(name);
    if (!rec) return;
    const key = String(rec.key);
    const eng = engineMap[key];
    if (!eng) return;

    /* cell text */
    const ddfText = colDdf >= 0 && cells[colDdf] ? cells[colDdf].textContent.trim() : '';
    const cbsText = colCbs >= 0 && cells[colCbs] ? cells[colCbs].textContent.trim() : '';
    const fcText  = colFc  >= 0 && cells[colFc]  ? cells[colFc].textContent.trim()  : '';

    rows.push({
      key, name,
      ddf_page: ddfText, ddf_eng: fx(eng.ddf),
      cbs_page: cbsText, cbs_eng: fx(eng.cbs),
      fc_page:  fcText,  fc_eng:  fx(eng.fc),
    });
  });

  /* ---- player-set comparison ---- */
  const engineKeys = new Set(Object.keys(engineMap));
  const pageKeys   = new Set(D.filter(r => positions.has(r.pos) && r.ddf !== null).map(r => String(r.key)));

  /* ---- chip text ---- */
  const scoringChip = document.getElementById('vchip-scoring');
  const teamsChip   = document.getElementById('vchip-teams');

  return {
    rows,
    engineKeys: [...engineKeys],
    pageKeys:   [...pageKeys],
    chipScoring: scoringChip && !scoringChip.hidden ? scoringChip.textContent.trim() : '',
    chipTeams:   teamsChip   && !teamsChip.hidden   ? teamsChip.textContent.trim()   : '',
  };
}"""

# Read first 5 Buy rows from the Buy / Sell tab.
READ_BUYSELL_JS = """() => {
  /* activate the Buy/Sell tab */
  const tab = document.getElementById('tab-bs');
  if (tab && tab.getAttribute('aria-selected') !== 'true') tab.click();

  const E = window.DDF && window.DDF.engine;
  if (!E) return {error: 'no DDF.engine'};
  const finite = v => typeof v === 'number' && isFinite(v);
  const CHART_KEYS = ['cbs', 'usat', 'fp', 'fc'];

  const bsRows = document.querySelectorAll('#bs-buy .bs-row');
  const result = [];
  for (let i = 0; i < Math.min(5, bsRows.length); i++) {
    const row = bsRows[i];
    const key = row.dataset.k;
    const ddfEl = row.querySelector('.bs-ddf');
    const mktEl = row.querySelector('.bs-mkt');
    /* Charts cell text includes the src count badge (e.g. "32.14 3/4"); strip it */
    const ddfText = ddfEl ? ddfEl.textContent.trim() : '';
    const mktRaw  = mktEl ? mktEl.textContent.trim() : '';
    const mktText = mktRaw.replace(/[ \t]*\d+\/4[ \t]*$/, '').trim();

    const eng = E.player(key);
    if (!eng) { result.push({key, ddfText, mktText, engDdf: null, engCharts: null}); continue; }

    let sum = 0, cnt = 0;
    CHART_KEYS.forEach(k => { const v = eng[k]; if (finite(v)) { sum += v; cnt++; } });
    const engCharts = cnt > 0 ? sum / cnt : null;
    result.push({key, ddfText, mktText, engDdf: finite(eng.ddf) ? eng.ddf : null, engCharts});
  }
  return {bsRows: result};
}"""


@contextlib.contextmanager
def _serve(overrides=None):
    overrides = overrides or {}

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def do_GET(self):
            rel = self.path.split('?')[0].lstrip('/')
            for key, body in overrides.items():
                if rel == key or rel.endswith('/' + key):
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/javascript')
                    self.send_header('Content-Length', str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            super().do_GET()

    handler = functools.partial(Handler, directory=str(DIST))
    with socketserver.ThreadingTCPServer(('127.0.0.1', 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f'http://127.0.0.1:{server.server_address[1]}'
        finally:
            server.shutdown()


SCORING_LABELS = {
    'standard': 'standard',
    'half_ppr': 'half',
    'ppr': 'ppr',
}


def _run_parity(overrides=None, settings=None):
    """Open values.html, check each setting combo. Returns list of error strings."""
    try:
        from playwright.sync_api import sync_playwright, Error as PlaywrightError
    except Exception as exc:
        raise _render_env.unavailable(f'Playwright not available: {exc}') from exc

    if not (DIST / 'values.html').exists():
        raise _render_env.unavailable('dist/values.html is not built')

    settings = settings or SETTINGS
    errors = []

    with _serve(overrides) as base_url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(
                args=_render_env.HERMETIC_ARGS,
                executable_path=_render_env.chromium_executable(),
            )
        except PlaywrightError as exc:
            raise _render_env.unavailable(f'Chromium not available: {exc}') from exc

        try:
            for scoring, teams, sf in settings:
                label = f'scoring={scoring} teams={teams} sf={sf}'
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                page_errors = []
                page.on('pageerror', lambda e: page_errors.append(str(e)))
                page.route(
                    lambda u: not (u.startswith('http://127.0.0.1') or u.startswith('http://localhost')),
                    lambda route: route.abort(),
                )
                # Clear storage to avoid settings bleed between iterations
                page.add_init_script(
                    '(function(){ try { localStorage.clear(); sessionStorage.clear(); } catch(_){} })()'
                )
                page.goto(f'{base_url}/values.html', wait_until='networkidle', timeout=60000)

                try:
                    page.wait_for_function(READY_EXPR, timeout=20000)
                except PlaywrightError as exc:
                    errors.append(f'{label}: page never became live: {exc}'.splitlines()[0])
                    page.close()
                    continue

                # Click "All" to show every player in the table
                page.evaluate(CLICK_ALL_JS)
                try:
                    page.wait_for_function(READY_EXPR, timeout=10000)
                except PlaywrightError:
                    pass

                # Apply settings via Customize controls
                page.evaluate(SET_CONTROLS_JS, [scoring, teams, sf])
                try:
                    page.wait_for_timeout(600)
                    page.wait_for_function(READY_EXPR, timeout=10000)
                except PlaywrightError:
                    pass

                # Enable the FantasyCalc column and wait for it to appear in the header.
                page.evaluate(ENABLE_FC_JS)
                try:
                    page.wait_for_selector(
                        '#head th button[data-key="fc"]', timeout=5000)
                except PlaywrightError:
                    pass

                snap = page.evaluate(READ_TABLE_JS)
                if isinstance(snap, dict) and snap.get('error'):
                    errors.append(f'{label}: {snap["error"]}')
                    page.close()
                    continue

                # Player-set check
                engine_keys = set(snap.get('engineKeys', []))
                page_keys   = set(snap.get('pageKeys', []))
                only_eng  = engine_keys - page_keys
                only_page = page_keys - engine_keys
                if only_eng:
                    errors.append(f'{label}: {len(only_eng)} engine-only players (e.g. {sorted(only_eng)[:3]})')
                if only_page:
                    errors.append(f'{label}: {len(only_page)} page-only players (e.g. {sorted(only_page)[:3]})')

                # Chip text check
                chip_scoring = snap.get('chipScoring', '')
                chip_teams   = snap.get('chipTeams', '')
                score_lbl = SCORING_LABELS.get(scoring, scoring)
                if score_lbl.lower() not in chip_scoring.lower():
                    errors.append(f'{label}: scoring chip {chip_scoring!r} does not reflect {scoring!r}')
                if str(teams) not in chip_teams:
                    errors.append(f'{label}: teams chip {chip_teams!r} does not contain {teams}')

                # Cell-by-cell check
                cell_errs = []
                for row in snap.get('rows', []):
                    if row['ddf_page'] != row['ddf_eng']:
                        cell_errs.append(
                            f'{row["key"]} DDF page={row["ddf_page"]!r} eng={row["ddf_eng"]!r}')
                    if row['cbs_page'] != row['cbs_eng']:
                        cell_errs.append(
                            f'{row["key"]} CBS page={row["cbs_page"]!r} eng={row["cbs_eng"]!r}')
                    if row['fc_page'] != row['fc_eng']:
                        cell_errs.append(
                            f'{row["key"]} FC page={row["fc_page"]!r} eng={row["fc_eng"]!r}')

                if cell_errs:
                    sample = cell_errs[:5]
                    if len(cell_errs) > 5:
                        sample.append(f'... {len(cell_errs) - 5} more')
                    errors.append(f'{label}: cell mismatches: {sample}')

                # Buy/Sell check
                bs = page.evaluate(READ_BUYSELL_JS)
                if isinstance(bs, dict) and bs.get('error'):
                    errors.append(f'{label} buy-sell: {bs["error"]}')
                else:
                    for r in bs.get('bsRows', []):
                        if r['engDdf'] is not None:
                            want_ddf = f'{r["engDdf"]:.2f}'
                            if r['ddfText'] != want_ddf:
                                errors.append(
                                    f'{label} buy {r["key"]} DDF page={r["ddfText"]!r} eng={want_ddf!r}')
                        if r['engCharts'] is not None:
                            want_mkt = f'{r["engCharts"]:.2f}'
                            if r['mktText'] != want_mkt:
                                errors.append(
                                    f'{label} buy {r["key"]} Charts page={r["mktText"]!r} eng={want_mkt!r}')

                for pe in page_errors:
                    errors.append(f'{label} page-error: {pe}')
                page.close()
        finally:
            browser.close()

    return errors


def setUpModule():
    _render_env.ensure_built()


class ValuesPageEngineParityTest(unittest.TestCase):

    def test_all_12_settings_match_engine(self):
        errors = _run_parity()
        self.assertEqual(errors, [], errors)

    def test_guard_fails_on_stale_value(self):
        """Serve a modified values-chart.js that adds 0.1 to every loaded ddf,
        then confirm the parity check catches it (the guard is not vacuous)."""
        chart_js_path = DIST / 'values-chart.js'
        if not chart_js_path.exists():
            # Try versioned file
            candidates = list(DIST.glob('values-chart.js*'))
            if not candidates:
                raise _render_env.unavailable('dist/values-chart.js not built')
            chart_js_path = candidates[0]

        src = chart_js_path.read_text(encoding='utf-8')

        # Inject inside load() right after the D.push loop so the inflation
        # persists across every load() call (including those triggered by
        # E().on()).  The anchor is the unique end of the push-forEach in load().
        ANCHOR = "chg:null,was:null}))"
        if ANCHOR not in src:
            self.skipTest('injection anchor not found in values-chart.js')

        patched = src.replace(
            ANCHOR,
            ANCHOR + ";D.forEach(p=>{if(p.ddf!==null)p.ddf=+(p.ddf+0.1).toFixed(1)})",
            1,
        )

        # The server handler strips query params when matching override keys,
        # so use just the path portion (without ?v=...).
        override_key = 'values-chart.js'

        errors = _run_parity(
            overrides={override_key: patched.encode('utf-8')},
            settings=SETTINGS[:1],   # one combo is sufficient for discrimination
        )
        self.assertNotEqual(errors, [],
                            'parity check did not catch the +0.1 stale-value injection')


if __name__ == '__main__':
    unittest.main()
