"""Feature contract test (JEG-506): one quick check per line of the feature contract.

The contract is the Google Doc "Data Driven Football: feature contract" (Jeremy,
2026-10-09: the Doc is the source of truth). docs/feature-contract.md mirrors it.
Regenerate the mirror with scripts/sync_feature_contract.py; never edit it by hand.
Every **XX-NN** ID in the mirror must be in CHECKS below: a check function for a live
line, or PENDING("JEG-xxx") for a "to build: JEG-xxx" line (with an optional partial
check of what already exists). A Doc line without a check, a pending line the Doc calls
live, or a check for an ID the Doc dropped fails test_mirror_every_id_has_a_check.
A line's "to build" may sit anywhere in its block (GL-24 has it on a later paragraph).
MF-01 compares the rendered Manifesto word for word with docs/manifesto-mirror.md, the
mirror of Jeremy's Manifesto Doc (same script, --doc manifesto).

A check is a presence-and-basic-behaviour test: the feature is there and does its
basic job. Deeper correctness lives in the other tests/test_v2_* suites.

Changing or removing a check needs Jeremy's yes, recorded in the Doc's decision
log first. A failing check means the code broke the contract, not that the check
is wrong.

How it runs: dist/v2 is built into a temp copy of dist/ and served locally. Each
scenario is one page load (desktop Player values, desktop tabs, phone, engine
failure); the checks read the snapshots those loads return. The freshness file
is replaced with a fixed one so the freshness checks see every status
(current, prior week, unknown, not updating) whatever the live pipeline says.

Discrimination: test_guard_fails_on_broken_builds serves broken v2.js / v2.css /
shell.html through page routes in three grouped runs and requires the named check to
report a real finding for each fault: nav reordered, a Manifesto section dropped and
one Manifesto word changed (MF-01), the week badge dropped from Compare rows (TT-06), Swap hidden (CT-01), "Vegas" in the header (GL-01), the DDF line at the
others' weight (PV-02), Reset leaving Rank by (PV-09), a prior-week status without a
symbol (GL-04), a chip without a warning and a chip claiming all current (GL-05), the
◐ tag removed (GL-03, TT-08), Rank by defaulting to a chart (GL-08) and a 390 px layout
that scrolls sideways (GL-13), and Player values search without its
not-valued list (GL-20, a partial check until the Doc marks it live), and (group 4) the ⓘ hover dropped
(GL-19), the chart group named "as published" (GL-21), Edit league demoted (GL-22), Customize without
Reset (GL-07) and the removed Compare headline lines put back (CT-02). Separately, the pre-fix v2.js from
JEG-506's own commit (raw engine keys in the source list and How values,
"undefined" in the player detail, a prior-week status without a symbol) fails
GL-02, GL-04, GL-05, TT-03 and HV-01.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
MIRROR = ROOT / "docs" / "feature-contract.md"
V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
SHELL = ROOT / "app" / "v2" / "shell.html"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests import _render_env  # noqa: E402
from tests._dist_server import engine_path  # noqa: E402
from tests._holds import pin_holds_in_dist  # noqa: E402


def _fixture_today():
    """The date the built fixture belongs to, so the page's content-week clock
    matches the data it serves (JEG-675, JEG-787)."""
    fixture = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
    return fixture["built_at"][:10]


def setUpModule():
    _render_env.ensure_built()


class PENDING:
    """CHECKS value for an agreed line that is not live yet ("to build: JEG-xxx" in the Doc).

    `partial` is an optional check of the part that already exists (GL-17: Player values
    is live under JEG-483; TT-05: the ⓘ exists, the word is JEG-510). It runs in the
    render test like any live check. Switch the line to a real check when its ticket
    ships and the Doc drops "to build"; test_mirror_every_id_has_a_check fails until then.
    """

    def __init__(self, ticket: str, partial=None):
        self.ticket, self.partial = ticket, partial

    def __repr__(self):
        return f"PENDING({self.ticket!r})"


ID_LINE = re.compile(r"\*\*([A-Z]{2}-\d{2})\*\*")
TO_BUILD = re.compile(r"to build:([^)]*)")


def contract_ids(text: str) -> dict[str, str | None]:
    """{ID: None if live, else the "to build: …" text} for every **XX-NN** ID.

    A line's block runs from its ID to the next ID or heading, so a "to build" on a later
    paragraph of the same line (GL-24: "Share links carry every setting (to build: …)")
    counts. The first "to build" in the block wins."""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = ID_LINE.search(line)
        if m:
            current = m.group(1)
            blocks[current] = [line[m.end():]]
        elif line.startswith("#"):
            current = None
        elif current:
            blocks[current].append(line)
    ids = {}
    for cid, lines in blocks.items():
        build = TO_BUILD.search("\n".join(lines))
        ids[cid] = build.group(1).strip() if build else None
    return ids


def mirror_errors(text: str, checks) -> list[str]:
    ids = contract_ids(text)
    errors = []
    if not ids:
        errors.append("the mirror has no contract IDs")
    for cid, to_build in ids.items():
        check = checks.get(cid)
        if check is None:
            errors.append(f"{cid}: in the contract with no check (add one to CHECKS)")
        elif to_build is not None:
            if not isinstance(check, PENDING):
                errors.append(f"{cid}: the contract says 'to build: {to_build}' but CHECKS has a live check; mark it PENDING")
            elif check.ticket not in to_build:
                errors.append(f"{cid}: pending on {check.ticket}, but the contract says 'to build: {to_build}'")
        elif isinstance(check, PENDING):
            errors.append(f"{cid}: the contract says it is live but its check is {check!r}; switch it on")
        elif not callable(check):
            errors.append(f"{cid}: CHECKS value {check!r} is not a check function")
    for cid in sorted(set(checks) - set(ids)):
        errors.append(f"{cid}: has a check but is not in the contract")
    return errors


def live_checks(checks=None) -> dict:
    """{ID: function} for every check the render test runs: live lines and pending partials."""
    out = {}
    for cid, check in (checks or CHECKS).items():
        fn = check.partial if isinstance(check, PENDING) else check
        if fn:
            out[cid] = fn
    return out


# ---------------------------------------------------------------- serving

def _freshness(kind: str) -> str:
    """The freshness file with fixed statuses. "mixed": USA Today a week behind,
    CBS unconfirmed, FantasyCalc's import failing, the rest current. "prior": only
    USA Today a week behind. "current": all current."""
    doc = json.loads((DIST / "assets" / "reference-freshness.json").read_text(encoding="utf-8"))
    items = []
    for item in doc.get("items", []):
        item = dict(item)
        key = item.get("key", "")
        if key in ("source_import.checked_at", "comparison.built_at"):
            item["freshness_ok"] = True  # pipeline-wide steps; the live file may be stale, the fixture is not
        if key.startswith(("source_import.", "comparison.source.")):
            item["freshness_ok"] = True
            if key.startswith("comparison.source."):
                item["weeks_behind"] = 0
        if kind in ("mixed", "prior") and key == "comparison.source.usatoday":
            item["weeks_behind"] = 1
        if kind == "mixed":
            if key == "comparison.source.cbs":
                continue
            if key == "source_import.fantasycalc":
                item["freshness_ok"] = False
        items.append(item)
    doc["items"] = items
    return json.dumps(doc)


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        # Held-proof fixture (JEG-675, Jeremy 2026-10-16: "Give the tests a fixed,
        # held-proof fixture"): GL-09 needs a projection unheld to offer DDF Value
        # (projections). Chain run 573 (JEG-chain573) held all three projections.
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def translate_path(self, path):
                return engine_path(path) or super().translate_path(path)

        class Server(socketserver.ThreadingTCPServer):
            request_queue_size = 128
            daemon_threads = True

        handler = functools.partial(Handler, directory=str(dist))
        with Server(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/", dist
            finally:
                server.shutdown()


def _fulfill(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


ENGINE_FAILS = """(function fail() {
  var s = document.querySelector('#legacyEngine #curve-status');
  if (s) s.textContent = 'Values unavailable'; else setTimeout(fail, 50);
})();"""

# Fixture: some weeks have no one-source DDF Value at all (Week 5: none of 738 players),
# so GL-03 / TT-08 could never see the "◐ 1 source" tag. Flag every fifth priced player
# (by player_key) as one-source in what the engine's row accessors return, the way the
# freshness file is fixed above. Values are untouched; only the confidence fields change.
# Both fixtures patch the same globals, so one trap per global applies every registered patch.
FIXTURE_TRAPS = """(() => {
  const patches = window.__contractPatches = {};
  for (const name of ['TradeValueCurveControls', 'TradeValueProductData']) {
    patches[name] = [];
    let current;
    Object.defineProperty(window, name, {configurable: true, enumerable: true, get: () => current,
      set: value => { if (value && !value.__contractFixture) { patches[name].forEach(patch => patch(value)); value.__contractFixture = true; }
        current = value; }});
  }
})();"""

LOW_CONFIDENCE_FIXTURE = """(() => {
  const mark = row => {
    if (row && Number(row.player_key) % 5 === 0 && Number.isFinite(row.values && row.values.ddf_value)) {
      row.ddfLowConfidence = true; row.ddfCount = 1;
      row.ddfConfidenceNote = 'Only one source prices this player (contract test fixture)';
    }
    return row;
  };
  window.__contractPatches.TradeValueCurveControls.push(value => {
    for (const name of ['getRows', 'getAllRows']) {
      const original = value[name];
      if (typeof original === 'function') value[name] = (...args) => original.apply(value, args).map(mark);
    }
  });
})();"""

# Fixture (TT-06, Jeremy 2026-10-10): a chart a week behind may not exist in the week's data,
# so USA Today is served one week behind: its source info is stale on the week before the
# reference week, and product-data's freshness says the same. Values are untouched.
STALE_CHART = "usatoday"
WEEK_BEHIND_FIXTURE = """(() => {
  const KEY = '%s';
  // Off when the page checks the all-current case (GL-05): set by Session.all_current().
  try { if (sessionStorage.getItem('contractAllCurrent') === '1') return; } catch (e) {}
  const trap = (name, patch) => window.__contractPatches[name].push(patch);
  const behind = week => Number.isFinite(week) && week > 1 ? week - 1 : null;
  trap('TradeValueCurveControls', C => {
    const original = C.getSourceInfo;
    if (typeof original !== 'function') return;
    C.getSourceInfo = (...args) => original.apply(C, args).map(item => item && item.key === KEY
      ? {...item, stale: true, week: behind(C.getReferenceWeek && C.getReferenceWeek()) || item.week} : item);
  });
  trap('TradeValueProductData', P => {
    const original = P.getSourceFreshness;
    if (typeof original !== 'function') return;
    P.getSourceFreshness = (...args) => {
      const f = original.apply(P, args);
      if (!f) return f;
      const s = (f.series && f.series[KEY]) || {};
      return {...f, series: {...(f.series || {}), [KEY]: {...s, is_older_week: true,
        vintage_week: behind(f.current_content_week) || s.vintage_week}}};
    };
  });
})();""" % STALE_CHART

READY = "() => window.TradeValueV2 && document.getElementById('v2State').hidden"


class Session:
    """One served build and one browser; opens pages with the build's overrides."""

    def __init__(self, browser, base, dist, overrides=None):
        self.browser, self.base, self.dist = browser, base, dist
        self.overrides = overrides or {}

    def open(self, hash_="", width=1440, height=900, freshness="mixed", engine_fails=False, wait=True):
        page = self.browser.new_page(viewport={"width": width, "height": height})
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(_fixture_today())};")
        page.add_init_script(FIXTURE_TRAPS)
        page.add_init_script(LOW_CONFIDENCE_FIXTURE)
        page.add_init_script(WEEK_BEHIND_FIXTURE)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.freshness = {"kind": freshness}
        page.route("**/assets/reference-freshness.json*",
                   lambda route, *_: route.fulfill(status=200, content_type="application/json",
                                                   body=_freshness(page.freshness["kind"])))
        ov = self.overrides
        if "shell" in ov:
            built = (self.dist / "v2" / "index.html").read_text(encoding="utf-8")
            posts = build_v2_page.load_posts()
            # The build places the Research page inside #v2App (JEG-543), so the embedded
            # shell is compose_shell(shell.html, posts), not shell.html itself.
            original = build_v2_page.compose_shell(SHELL.read_text(encoding="utf-8"), posts)
            assert original in built, "the built page no longer embeds shell.html verbatim"
            html = built.replace(original, build_v2_page.compose_shell(ov["shell"], posts), 1)
            page.route(lambda u: urlparse(u).path in ("/v2/", "/v2/index.html"),
                       functools.partial(_fulfill, html, "text/html"))
        if "v2.js" in ov:
            page.route("**/v2/v2.js*", functools.partial(_fulfill, ov["v2.js"], "text/javascript"))
        if "v2.css" in ov:
            page.route("**/v2/v2.css*", functools.partial(_fulfill, ov["v2.css"], "text/css"))
        if "targets.js" in ov:
            page.route("**/v2/targets.js*", functools.partial(_fulfill, ov["targets.js"], "text/javascript"))
        if engine_fails:
            page.route("**/assets/curve-widget.js*", functools.partial(_fulfill, ENGINE_FAILS, "text/javascript"))
        page.goto(self.base + hash_, wait_until="networkidle")
        if wait:
            page.wait_for_function(READY, timeout=60000)
            page.wait_for_timeout(400)
        return page


# ---------------------------------------------------------------- page probes

COMMON = r"""
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const $ = id => document.getElementById(id);
  const fire = (el, v) => { el.value = String(v); el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true})); };
  const C = window.TradeValueCurveControls, V = window.TradeValueV2;
  // JEG-947: a name cell holds its text in a .v2-nm span (phones show "Last, First"); the contract reads the full "First Last" name, and an empty visible name still reads as empty.
  const own = n => { const nm = n && n.querySelector && n.querySelector(':scope > .v2-nm'); return nm ? (nm.textContent.trim() ? (nm.dataset.full || nm.textContent.trim()) : '') : [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('').trim(); };
  const rect = n => { if (!n) return null; const r = n.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; };
  // JEG-1112: a display: contents wrapper (the Example banner inside Compare's header grid) has no box of its own; it is shown when a child is.
  const drawn = n => n.getClientRects().length > 0 || (getComputedStyle(n).display === 'contents' && [...n.children].some(drawn));
  const shown = n => Boolean(n) && !n.hidden && drawn(n);
  const closePop = async () => { const b = document.querySelector('#v2Popover:not([hidden]) .v2-panel-close')
      || [...document.querySelectorAll('#v2Popover:not([hidden]) button')].find(b => /^(Done|Cancel)$/.test(b.textContent.trim()));
    if (b) b.click(); document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); await sleep(250); };
  const visibleText = () => $('v2App').innerText;
  const attrText = root => [...root.querySelectorAll('[title],[aria-label]')]
    .map(n => (n.getAttribute('title') || '') + ' ' + (n.getAttribute('aria-label') || '')).join('\n');
  const sections = () => [...document.querySelectorAll('#v2WritingTabs .v2-subtab')].map(a => ({slug: a.dataset.writing,
    label: a.textContent.trim(), href: a.getAttribute('href'), current: a.getAttribute('aria-current') === 'page'}));
  const tabs = () => [...document.querySelectorAll('.v2-tab')].map(t => ({view: t.dataset.view,
    label: t.querySelector('.v2-tab-full')?.textContent || '', current: t.getAttribute('aria-current') === 'page'}));
  const pagesShown = () => Object.fromEntries(['v2Main', 'v2Targets', 'v2Risers', 'v2Compare', 'v2FindTrade', 'v2How', 'v2Manifesto', 'v2Research', 'v2Audit', 'v2Overrides']
    .map(id => [id, shown($(id))]));
  const readTable = (sel = '#v2Table') => [...document.querySelectorAll(sel + ' tbody tr[data-player-key]')].map(tr => ({
    key: tr.dataset.playerKey, name: own(tr.querySelector('td.player') || tr),
    tier: (tr.querySelector('.player-sub')?.textContent || '').split('·').pop().trim(),
    cells: [...tr.querySelectorAll('td[data-source]')].map(td => ({src: td.dataset.source, text: own(td),
      title: td.title || (td.querySelector('[title]')?.title || ''), vs: td.dataset.vs || null,
      heat: /\bheat-/.test(td.className), lowconf: Boolean(td.querySelector('[data-low-confidence]')),
      lowconfTitle: td.querySelector('[data-low-confidence]')?.title || '',
      lowconfText: (td.querySelector('[data-low-confidence]')?.textContent || '').trim(),
      delta: td.querySelector('.delta') ? {text: td.querySelector('.delta').textContent, title: td.querySelector('.delta').title} : null}))}));
  const addTrade = async () => {
    const rows = C.getRows();
    for (const [input, results, row] of [['v2GiveSearch', 'v2GiveResults', rows[0]], ['v2GetSearch', 'v2GetResults', rows[1]]]) {
      fire($(input), row.name); await sleep(400);
      const hit = [...document.querySelectorAll('#' + results + ' button[data-player-key]')].find(b => b.dataset.playerKey === String(row.player_key));
      if (hit) { hit.click(); await sleep(400); }
    }
  };
  const weekInfo = () => { const fr = window.TradeValueProductData?.getSourceFreshness?.() || null;
    return Object.fromEntries(C.getSourceInfo().map(i => { const s = fr?.series?.[i.key];
      return [i.key, {stale: s && typeof s.is_older_week === 'boolean' ? s.is_older_week : Boolean(i.stale),
        week: i.week || (s && s.vintage_week) || null}]; })); };
  const badgesIn = root => root ? [...root.querySelectorAll('.v2-prior-badge')].map(b => ({key: b.dataset.priorWeek || null,
    text: b.textContent.trim()})) : [];
  const engineFor = keys => { const rows = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
    return Object.fromEntries(keys.map(k => { const r = rows.get(String(k)); return [k, r ? {values: r.values,
      low: Boolean(r.ddfLowConfidence), tier: r.ddfTier || null, pos: r.pos, name: r.name} : null]; })); };
"""

VALUES_JS = "async () => {" + COMMON + r"""
  const out = {};
  const t0 = readTable();
  out.s0 = {
    tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText($('v2App')),
    showingText: $('v2ShowingText').textContent, legendCount: $('v2ShowingLegend').children.length,
    showingRects: [rect(document.querySelector('.v2-ctx-basis')), rect($('v2ShowingLegend')), rect($('v2EditSources'))],
    customize: $('v2EditSources').textContent.trim(),
    rankBy: $('v2RankBy').value, rankOptions: [...$('v2RankBy').options].map(o => o.value),
    shown: V.shown(), active: C.getActiveSources(),
    legendLinks: [...document.querySelectorAll('#v2ShowingLegend a[data-source-link]')].map(a => [a.dataset.sourceLink, a.getAttribute('href'), a.target]),
    names: {label: document.querySelector('.v2-ctx-basis b').textContent.trim(), info: document.querySelectorAll('.v2-ctx-basis button[data-info=names]').length},
    fit: {ticks: [...V.chart().svg.querySelectorAll('.axis text[text-anchor="end"]')].map(t => Number(t.textContent)),
      values: V.chart().slice.flatMap(r => V.chart().keys.map(k => r.values[k])).filter(v => Number.isFinite(v) && v > 0)},
    zeroPlayers: {hidden: V.view().hiddenZero, listed: V.view().rows.filter(r => !V.view().plotKeys.concat(V.view().vorpKeys)
      .some(k => Number.isFinite(r.values[k]) && r.values[k] > 0)).length},
    zones: {engine: C.getZones(), ranks: V.chart().slice.map(r => r.fullRank),
      lines: [...document.querySelectorAll('#v2Chart .zone-line')].map(l => ({name: l.dataset.zone, x: Number(l.getAttribute('x1'))})),
      labels: [...document.querySelectorAll('#v2Chart .zone-label')].map(l => l.textContent)},
    legendItems: [...document.querySelectorAll('#v2Legend .v2-legend-item')].map(b => ({key: b.dataset.series, pressed: b.getAttribute('aria-pressed'), mark: b.querySelector('.v2-legend-mark')?.textContent || ''})),
    brushFill: ['v2BrushFill', 'v2YBrushFill'].map(id => ({id, tab: $(id).tabIndex, role: $(id).getAttribute('role'), label: $(id).getAttribute('aria-label')})),
    series: [...document.querySelectorAll('#v2Chart svg .series')].map(p => ({cls: p.getAttribute('class'),
      width: parseFloat(getComputedStyle(p).strokeWidth)})),
    toolbar: [...$('v2Toolbar').querySelectorAll('input, select, button')].map(n => n.id),
    table: t0, engine: engineFor(t0.map(r => r.key)),
    lowEngine: C.getRows().filter(r => r.ddfLowConfidence).map(r => String(r.player_key)),
    sticky: {head: getComputedStyle(document.querySelector('#v2Table thead th')).position,
             player: getComputedStyle(document.querySelector('#v2Table tbody td.player')).position},
    // By ID, never by label: "Weights & bench" becomes "Position weights" (JEG-537).
    leagueButtons: {edit: shown($('v2EditLeague')), weights: Boolean($('v2Weights'))},
    leagueName: $('v2LeagueName').textContent,
    chip: {label: $('v2FreshnessLabel').textContent, cls: $('v2Freshness').className},
    weeks: weekInfo(),
    legendBadges: badgesIn($('v2ShowingLegend')),
    headBadges: [...document.querySelectorAll('#v2Table thead th')].map(th => ({key: th.dataset.source || th.dataset.col || null,
      text: th.textContent, badges: badgesIn(th)})).filter(h => h.badges.length || h.key),
    native: Object.fromEntries(C.getActiveSources().map(src => [src,
      Object.fromEntries(t0.map(r => [r.key, C.getNativeRank ? C.getNativeRank(r.key, src) : null]))])),
  };
  // Freshness dialog
  $('v2Freshness').click(); await sleep(300);
  out.fresh = [...document.querySelectorAll('#v2Popover tbody tr')].map(tr => ({src: tr.dataset.source,
    status: tr.dataset.status, text: own(tr.querySelector('td:last-child'))}));
  await closePop();
  // Show follows the table
  fire($('v2Show'), '25'); await sleep(400);
  out.show25 = readTable().length;
  fire($('v2Show'), '100'); await sleep(400);
  // X brush: names on the points, Show goes Custom, the table follows, a chip, Reset zoom
  fire($('v2BrushHi'), 5); await sleep(500);
  out.xbrush = {show: $('v2Show').value, rows: readTable().map(r => r.name), resetShown: shown($('v2ResetZoom')),
    texts: [...document.querySelectorAll('#v2Chart svg text')].map(t => t.textContent),
    chips: [...document.querySelectorAll('#v2FilterChips [data-chip]')].map(b => b.dataset.chip)};
  $('v2ResetZoom').click(); await sleep(400);
  out.zoomReset = {lo: +$('v2BrushLo').value, hi: +$('v2BrushHi').value, min: +$('v2BrushLo').min,
    ylo: +$('v2YBrushLo').value, yhi: +$('v2YBrushHi').value, ymax: +$('v2YBrushHi').max,
    resetShown: shown($('v2ResetZoom')), show: $('v2Show').value};
  // Y brush
  fire($('v2YBrushLo'), 40); await sleep(500);
  const ty = readTable();
  out.ybrush = {show: $('v2Show').value, rows: ty.length,
    rankValues: ty.map(r => parseFloat((r.cells.find(c => c.src === $('v2RankBy').value) || {}).text))};
  $('v2ResetZoom').click(); await sleep(400);
  // Columns menu hides a group
  $('v2Columns').click(); await sleep(300);
  const box = document.querySelector('#v2Popover input[data-group]:not([data-group="ddf"])');
  out.columns = {group: box ? box.dataset.group : null, before: 0, after: 0};
  if (box) {
    const g = box.dataset.group;
    out.columns.before = document.querySelectorAll(`#v2Table thead th[data-group="${g}"]`).length;
    box.click(); await sleep(300);
    out.columns.after = document.querySelectorAll(`#v2Table thead th[data-group="${g}"]`).length;
    box.click(); await sleep(300);
  }
  await closePop();
  // Player detail
  document.querySelector('#v2Table tbody tr[data-player-key]').click(); await sleep(400);
  out.drawer = {shown: shown($('v2Drawer')), text: $('v2Drawer').innerText,
    heads: [...$('v2Drawer').querySelectorAll('thead th')].map(th => th.textContent.trim())};
  // PV-12 (2026-10-23 list layout): default rows are the selected sources; "Show all sources" adds every kind.
  const dAll = $('v2DrawerAll');
  out.drawer.allToggle = dAll ? dAll.checked : null;
  if (dAll) {
    dAll.click(); await sleep(400);
    out.drawer.kindsAll = [...$('v2Drawer').querySelectorAll('.v2-dmatrix tbody tr')].map(tr => ({
      kind: tr.querySelector('td.kind')?.textContent.trim(), num: tr.querySelector('td.num')?.textContent.trim()}));
  }
  document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); await sleep(300);
  if (!$('v2Drawer').hidden) $('v2Drawer').querySelector('button')?.click();
  // Δ Prior week
  $('v2DeltaBtn').click();
  for (let i = 0; i < 60 && !document.querySelector('#v2Table .delta'); i++) await sleep(200);
  out.delta = {pressed: $('v2DeltaBtn').getAttribute('aria-pressed'), table: readTable().slice(0, 15)};
  $('v2DeltaBtn').click(); await sleep(300);
  // Expand chart and table
  $('v2ExpandChart').click(); await sleep(400);
  out.expandChart = {shown: shown($('v2Expand')), svg: Boolean($('v2Expand').querySelector('svg')),
    box: rect($('v2Expand').querySelector('.v2-expand-box')), vw: innerWidth, vh: innerHeight};
  $('v2ExpandClose').click(); await sleep(300);
  $('v2ExpandTable').click(); await sleep(400);
  const sortable = {};
  for (const col of ['pos', 'team', 'tier']) {
    const th = $('v2Expand').querySelector(`thead th[data-col="${col}"]`);
    if (th && th.querySelector('button')) { th.querySelector('button').click(); await sleep(250);
      sortable[col] = $('v2Expand').querySelector(`thead th[data-col="${col}"]`)?.getAttribute('aria-sort') || null; }
    else sortable[col] = null;
  }
  out.expandTable = {shown: shown($('v2Expand')), table: Boolean($('v2Expand').querySelector('table')),
    box: rect($('v2Expand').querySelector('.v2-expand-box')), vh: innerHeight, sortable};
  $('v2ExpandClose').click(); await sleep(300);
  // Filter chip clears one filter
  fire($('v2Position'), 'QB'); await sleep(400);
  const chip = document.querySelector('#v2FilterChips [data-chip]');
  out.chip = {chips: [...document.querySelectorAll('#v2FilterChips [data-chip]')].map(b => b.dataset.chip + ':' + b.textContent)};
  if (chip) { chip.click(); await sleep(400); }
  out.chip.positionAfter = $('v2Position').value;
  out.chip.chipsAfter = document.querySelectorAll('#v2FilterChips [data-chip]').length;
  // Tier follows Rank by
  const other = [...$('v2RankBy').options].map(o => o.value).find(v => v !== 'ddf_value');
  fire($('v2RankBy'), other); await sleep(600);
  out.otherRank = {key: other, value: $('v2RankBy').value, table: readTable()};
  out.otherRank.engine = engineFor(out.otherRank.table.map(r => r.key));
  // Reset restores everything, Rank by included
  fire($('v2Position'), 'RB'); await sleep(300);
  fire($('v2Search'), 'a'); await sleep(600);
  $('v2Reset').click(); await sleep(600);
  out.reset = {rank: $('v2RankBy').value, position: $('v2Position').value, search: $('v2Search').value, show: $('v2Show').value};
  // League edits apply live (JEG-1020): no Apply, no Cancel; Undo changes returns to the opening settings
  const leagueBefore = $('v2LeagueName').textContent;
  const engineTeams = C.getState().teams;
  $('v2EditLeague').click(); await sleep(300);
  const teams = [...document.querySelectorAll('#v2Popover [aria-label="Teams"] button')].find(b => b.getAttribute('aria-pressed') !== 'true');
  const immediateTeams = (teams ? (teams.click(), C.getState().teams) : engineTeams);   // before the debounce
  await sleep(700);
  const liveTeams = C.getState().teams;
  const buttons = [...document.querySelectorAll('#v2Popover button')].map(b => b.textContent.trim());
  const undo = document.querySelector('#v2Popover [data-league-undo]');
  if (undo) undo.click(); else await closePop();
  await sleep(500);
  const afterUndo = C.getState().teams;
  await closePop();
  out.league = {before: leagueBefore, after: $('v2LeagueName').textContent, changed: Boolean(teams),
    engineTeams, immediateTeams, liveTeams, afterTeams: afterUndo,
    hasApply: buttons.includes('Apply'), hasCancel: buttons.includes('Cancel'), hasUndo: Boolean(undo)};
  // Remembered selection: pick another Rank by, then the caller reloads
  const third = [...$('v2RankBy').options].map(o => o.value).filter(v => v !== 'ddf_value').pop();
  fire($('v2RankBy'), third); await sleep(400);
  out.remember = {key: third, stored: (() => { try { return localStorage.getItem('ddf.v2.selection'); } catch (e) { return null; } })()};
  return out;
}"""

RELOAD_JS = "() => {" + COMMON + r"""
  return {rankBy: $('v2RankBy').value, chip: $('v2FreshnessLabel').textContent,
          chipCls: $('v2Freshness').className};
}"""

TARGETS_JS = "async () => {" + COMMON + r"""
  const rows = sel => [...document.querySelectorAll(sel + ' tbody tr[data-player-key]')].map(tr => ({
    key: tr.dataset.playerKey, name: own(tr.querySelector('td.player')),
    ours: parseFloat(own(tr.querySelector('td[data-ours]'))),
    count: tr.querySelector('.t-count')?.textContent || '', countTitle: tr.querySelector('.t-count')?.title || '',
    lowconf: Boolean(tr.querySelector('[data-low-confidence]')),
    charts: [...tr.querySelectorAll('td.t-chart')].map(td => ({chart: td.dataset.chart, text: own(td),
      gap: td.querySelector('.gap')?.textContent || ''})),
    best: tr.querySelector('td[data-best]') ? {chart: tr.querySelector('td[data-best]').dataset.best,
      text: own(tr.querySelector('td[data-best]')), who: tr.querySelector('td[data-best] .t-who')?.textContent || ''} : null}));
  const out = {
    tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText($('v2Targets')),
    h1: $('v2TargetsTitle').textContent.trim(), ours: $('v2TOurs').value, oursOptions: [...$('v2TOurs').options].map(o => o.value),
    sell: rows('#v2TTable'), buy: rows('#v2TBuyTable'),
    sellMore: shown($('v2TSellMore')), buyMore: shown($('v2TBuyMore')),
    rects: [rect($('v2TSell')), rect($('v2TBuy'))],
    heads: [...document.querySelectorAll('#v2TTable thead th[data-chart]')].map(th => ({chart: th.dataset.chart,
      name: th.querySelector('.th-line a[data-source-link]')?.textContent || own(th.querySelector('.th-line')), sub: th.querySelector('.th-sub')?.textContent || '',
      badge: th.querySelector('.v2-prior-badge')?.textContent || null,
      info: Boolean(th.querySelector('button[data-info]'))})),
    weeks: weekInfo(),
    refWeek: C.getReferenceWeek ? C.getReferenceWeek() : null,
    caption: $('v2TChartCaption').textContent, captionInfo: Boolean(document.querySelector('.v2-tcompare button[data-info]')),
    lowEngine: C.getRows().filter(r => r.ddfLowConfidence).map(r => String(r.player_key)),
    divergence: [...document.querySelectorAll('#v2TDivergence .v2-div-chip')].map(c => ({src: c.dataset.divergence, status: c.dataset.status})),
    sourceLinks: [...document.querySelectorAll('#v2TTable thead th[data-chart] a[data-source-link]')].map(a => [a.dataset.sourceLink, a.getAttribute('href'), a.target]),
    mathCells: [...document.querySelectorAll('#v2TTable td.t-chart[data-math-for]')].slice(0, 12).map(td => [td.getAttribute('tabindex'), td.getAttribute('aria-describedby')]),
    weight: {h2: [...document.querySelectorAll('#v2Targets h2')].map(h => h.textContent.trim()),
      sub: document.querySelector('#v2Targets .v2-ttitle p').textContent,
      headline: $('v2WeightHeadline').textContent,
      groups: [...document.querySelectorAll('#v2WeightTable tbody tr[data-group]')].map(tr => ({key: tr.dataset.group,
        n: Number(tr.children[1].textContent), gap: tr.querySelector('td.w-gap').dataset.gap,
        signal: tr.querySelector('.v2-wsignal')?.dataset.signal || null, chip: tr.querySelector('.v2-wsignal')?.textContent || ''}))},
  };
  out.engine = engineFor(out.sell.concat(out.buy).map(r => r.key));
  const btn = document.querySelector('#v2TTable .v2-texpand');
  if (btn) { const key = btn.dataset.expand; btn.click(); await sleep(300);
    const again = document.querySelector(`#v2TTable [data-expand="${CSS.escape(key)}"]`);
    const detail = document.querySelector(`#v2TTable tr.t-detail[data-detail-for="${CSS.escape(key)}"]`);
    out.expand = {expanded: again ? again.getAttribute('aria-expanded') : null, detail: detail ? detail.innerText : ''};
    if (again) { again.click(); await sleep(200); } }
  const info = document.querySelector('.v2-tcompare button[data-info]');
  if (info) { info.click(); await sleep(300); out.info = shown($('v2Popover')) ? $('v2Popover').innerText : ''; await closePop(); }
  // Every row, for TT-08 (JEG-1186: no one-source player may be listed anywhere in Sell / Buy).
  for (const id of ['v2TSellMore', 'v2TBuyMore']) if (shown($(id))) { $(id).click(); await sleep(300); }
  out.sellAll = rows('#v2TTable').length; out.buyAll = rows('#v2TBuyTable').length;
  out.all = rows('#v2TTable').concat(rows('#v2TBuyTable'));
  out.allEngine = engineFor(out.all.map(r => r.key));
  return out;
}"""

RISERS_JS = "async () => {" + COMMON + r"""
  const sel = $('v2RSeries');
  const top = [...document.querySelectorAll('#v2RRise li[data-player-key]')].slice(0, 3).map(li => ({key: li.dataset.playerKey,
    before: li.querySelector('[data-col="before"]')?.textContent || '', now: li.querySelector('[data-col="now"]')?.textContent || '',
    delta: li.querySelector('[data-col="delta"]')?.textContent || ''}));
  const prior = await C.getPriorWeek(sel.value);
  const engineTop = top.map(r => ({before: prior?.values?.[r.key] ?? null,
    now: prior?.currentValues ? (prior.currentValues[r.key] ?? null) : (C.getAllRows().find(x => String(x.player_key) === r.key)?.values?.[sel.value] ?? null)}));
  return {top, engineTop,tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText($('v2Risers')),
    series: sel.value, groups: [...sel.querySelectorAll('optgroup')].map(g => g.label),
    firstGroupKeys: sel.querySelector('optgroup') ? [...sel.querySelector('optgroup').querySelectorAll('option')].map(o => o.value) : [],
    meta: $('v2RMeta').textContent, note: shown($('v2RNote')) ? $('v2RNote').textContent : '',
    noPrior: (V.risers() || {}).noPrior || 0, rise: document.querySelectorAll('#v2RRise li').length,
    disagree: {h2: $('v2RDisagreeTitle').textContent, meta: $('v2RDisagreeMeta').textContent,
      heads: [$('v2RMktTitle').textContent, $('v2RProjTitle').textContent],
      n: document.querySelectorAll('#v2RMkt li[data-player-key], #v2RProj li[data-player-key]').length,
      reads: [...document.querySelectorAll('#v2RMkt [data-col=read], #v2RProj [data-col=read]')].map(n => n.textContent)}};
}"""

COMPARE_JS = "async () => {" + COMMON + r"""
  const side = id => [...document.querySelectorAll('#' + id + ' li[data-player-key]')].map(li => ({key: li.dataset.playerKey,
    example: li.classList.contains('is-example'), tier: (li.querySelector('.v2-meta')?.textContent || '').split('·').pop().trim()}));
  const snap = () => ({example: shown($('v2CExample')), eyebrow: $('v2CVerdictEyebrow').textContent,
    title: $('v2CVerdictTitle').textContent, verdict: $('v2CVerdictText').textContent, hash: location.hash,
    share: shown($('v2CShare')), swap: shown($('v2CSwap')), clear: shown($('v2CClear')),
    give: side('v2GivePlayers'), get: side('v2GetPlayers'),
    giveSearch: shown($('v2GiveSearch')), getSearch: shown($('v2GetSearch')),
    deal: {shown: shown($('v2CDeal')), cells: document.querySelectorAll('#v2CDealGrid td').length,
      current: document.querySelectorAll('#v2CDealGrid td[aria-current]').length, nets: document.querySelectorAll('#v2CDealNets li').length,
      read: $('v2CDealRead').textContent, text: $('v2CDealText').textContent, split: /The sources split/.test($('v2Compare').innerText)}});
  const out = {tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText($('v2Compare')), shownKey: $('v2CShown').value};
  out.example = snap();
  out.weeks = weekInfo();
  out.rows = [...document.querySelectorAll('#v2CTable tbody tr[data-source]')].map(tr => { const wf = tr.querySelector('.v2-wf');
    return {src: tr.dataset.source, badges: badgesIn(tr), name: own(tr.querySelector('td.player')) || (tr.querySelector('td.player a[data-source-link]')?.textContent || '').trim(), give: parseFloat(tr.querySelector('[data-col="give"]')?.textContent),
      receive: parseFloat(tr.querySelector('[data-col="receive"]')?.textContent), lo: wf ? wf.dataset.lo : null, hi: wf ? wf.dataset.hi : null,
      steps: wf ? [...wf.querySelectorAll('.v2-wf-step')].map(s => ({side: s.dataset.side, value: s.dataset.value})) : []}; });
  out.engine = engineFor(out.example.give.concat(out.example.get).map(p => p.key));
  out.shownOptions = [...$('v2CShown').options].map(o => [o.value, o.textContent]);
  // DDF Value hidden: the verdict follows the picked series and names it.
  // JEG-498: Compare reads its own Customize list, not the Player values one.
  const before = V.pageKeys('compare');
  V.setPageKeys('compare', before.filter(k => k !== 'ddf_value')); await sleep(500);
  const other = [...$('v2CShown').options].map(o => o.value).find(v => v !== 'ddf_value');
  fire($('v2CShown'), other); await sleep(400);
  out.otherShown = {key: other, label: [...$('v2CShown').options].find(o => o.value === other)?.textContent || '', title: $('v2CVerdictTitle').textContent};
  V.setPageKeys('compare', before); await sleep(500);
  fire($('v2CShown'), 'ddf_value'); await sleep(400);
  // Add a player of our own to each side: the example leaves, and the link carries the league settings.
  await addTrade();
  out.added = snap();
  if (shown($('v2CSwap'))) { $('v2CSwap').click(); await sleep(400); }
  out.swapped = snap();
  if (shown($('v2CClear'))) { $('v2CClear').click(); await sleep(400); }
  out.cleared = snap();
  return out;
}"""

HOW_JS = "() => {" + COMMON + r"""
  const how = $('v2How');
  const clone = how.cloneNode(true);
  clone.querySelectorAll('.v2-how-league').forEach(n => n.remove());
  return {tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText(how),
    cards: [...how.querySelectorAll('[data-view-method]')].map(li => ({method: li.dataset.viewMethod,
      title: li.querySelector('h2')?.textContent || '', items: [...li.querySelectorAll('.v2-how-sources li')].map(x => x.textContent.trim())})),
    outside: clone.textContent, bench: $('v2HowBench').textContent, benchNote: $('v2HowBenchNote').hidden ? '' : $('v2HowBenchNote').textContent,
    primaries: [...how.querySelectorAll('#v2HowNames [data-primary]')].map(li => li.querySelector('b').textContent), edge: how.innerText.includes('Where the edge comes from'),
    readout: C.getBenchShareReadout(), slider: Boolean(document.getElementById('v2BenchSlider')),
    activeKeys: C.getActiveSources()};
}"""

MANIFESTO_JS = "() => {" + COMMON + r"""
  const mf = $('v2Manifesto');
  return {tabs: tabs(), sections: sections(), hash: location.hash, pages: pagesShown(), text: visibleText(), attrs: attrText(mf),
    h1: mf.querySelector('h1')?.textContent.trim() || '', h2: [...mf.querySelectorAll('article h2')].map(h => h.textContent.trim()),
    links: mf.querySelectorAll('a').length,
    controls: mf.querySelectorAll('a, button, input, select, textarea, [contenteditable]').length,
    words: [...(mf.querySelector('article') || mf).children].filter(n => !n.classList.contains('v2-mf-eyebrow'))
      .map(n => n.innerText).join('\n')};
}"""

PHONE_JS = "async (hash) => {" + COMMON + r"""
  location.hash = hash; await sleep(700);
  const page = Object.entries(pagesShown()).find(([, on]) => on);
  const out = {hash, page: page ? page[0] : null, height: page ? $(page[0]).getBoundingClientRect().height : 0,
    overflow: document.documentElement.scrollWidth - innerWidth, nav: false};
  // JEG-953: on phones the tabs live in the hamburger menu; the nav is usable when the button opens a menu with every tab.
  const toggle = $('v2NavToggle');
  if (shown(toggle)) {
    toggle.click(); await sleep(100);
    out.nav = [...document.querySelectorAll('.v2-tabs .v2-tab')].filter(shown).length === document.querySelectorAll('.v2-tabs .v2-tab').length && document.querySelectorAll('.v2-tabs .v2-tab').length >= 8 && toggle.getAttribute('aria-expanded') === 'true';
    toggle.click(); await sleep(100);
  }
  if (hash === '#compare-trade') {
    await addTrade();
    scrollTo(0, document.documentElement.scrollHeight); await sleep(500);
    const card = $('v2CVerdict').getBoundingClientRect();
    out.bar = {shown: shown($('v2CVerdictBar')), rect: rect($('v2CVerdictBar')), vh: innerHeight, cardOff: card.bottom < 0 || card.top > innerHeight};
    scrollTo(0, 0);
  }
  return out;
}"""

GL20_JS = "async () => {" + COMMON + r"""
  // A player no source prices, from the engine's own search (practice squad first).
  const all = C.searchPlayers('a', {limit: 5000}).concat(C.searchPlayers('e', {limit: 5000}));
  const pick = all.find(r => r.universe_only && r.roster_status === 'practice_squad') || all.find(r => r.universe_only);
  if (!pick) return {pick: null};
  const key = String(pick.player_key);
  const read = id => { const box = $(id);
    const li = box && !box.hidden ? box.querySelector(`li[data-player-key="${key}"]`) : null;
    return li ? li.innerText : null; };
  const out = {pick: {key, name: pick.name, reason: pick.unpriced_reason, ddf: pick.values ? pick.values.ddf_value : null}};
  location.hash = '#player-values'; await sleep(900);
  fire($('v2Search'), pick.name); await sleep(700);
  out.pv = read('v2Unpriced');
  out.pvInTable = Boolean(document.querySelector(`#v2Table tr[data-player-key="${key}"]`));
  fire($('v2Search'), ''); await sleep(400);
  location.hash = '#trade-targets'; await sleep(900);
  fire($('v2TSearch'), pick.name); await sleep(700);
  out.tt = read('v2TUnpriced');
  fire($('v2TSearch'), ''); await sleep(300);
  location.hash = '#risers-fallers'; await sleep(1200);
  fire($('v2RSearch'), pick.name); await sleep(900);
  out.rf = read('v2RUnpriced');
  fire($('v2RSearch'), ''); await sleep(300);
  location.hash = '#compare-trade'; await sleep(1000);
  fire($('v2GiveSearch'), pick.name); await sleep(500);
  const b = document.querySelector(`#v2GiveResults button[data-player-key="${key}"]`);
  out.ct = b ? {text: b.innerText, disabled: b.disabled} : null;
  fire($('v2GiveSearch'), ''); await sleep(200);
  return out;
}"""

FAILURE_JS = "() => {" + COMMON + r"""
  const card = document.querySelector('#v2State .v2-state');
  return {state: card ? card.dataset.state : null, title: $('v2StateTitle').textContent,
    retry: shown($('v2StateRetry')), pages: pagesShown(), text: visibleText()};
}"""


# ---------------------------------------------------------------- scenarios

def scenario_values(s: Session) -> dict:
    page = s.open("#player-values")
    try:
        snap = page.evaluate(VALUES_JS)
        for kind in ("prior", "current"):
            page.freshness["kind"] = kind
            if kind == "current":   # every source current: no simulated week-behind chart either
                page.evaluate("() => { try { sessionStorage.setItem('contractAllCurrent', '1'); } catch (e) {} }")
            page.reload(wait_until="networkidle")
            page.wait_for_function(READY, timeout=60000)
            page.wait_for_timeout(600)
            snap[f"reload_{kind}"] = page.evaluate(RELOAD_JS)
        snap["reload"] = snap["reload_current"]
        page.evaluate("() => { try { localStorage.clear(); } catch (e) {} }")
        snap["errors"] = page.errors
        return snap
    finally:
        page.close()


# Every card on screen on a data tab, and the controls modules.js gave it (GL-17, GL-18).
LEAGUE_PANEL_JS = """() => { const pop = document.getElementById('v2Popover');
  const adv = pop.querySelector('details.v2-padv');
  return {eyebrows: [...pop.querySelectorAll(':scope .v2-eyebrow')].filter(h => !h.closest('details')).map(h => h.textContent),
    steps: [...pop.querySelectorAll('.v2-pstep > span')].map(n => n.textContent),
    stepperAria: [...pop.querySelectorAll('[aria-label]')].map(n => n.getAttribute('aria-label')),
    shape: window.TradeValueCurveControls.getRosterShape(), teams: window.TradeValueCurveControls.getState().teams,
    rosterLine: document.getElementById('v2RosterLine').textContent,
    tierHead: (document.querySelector('#v2Table thead th[data-col="tier"]') || {}).textContent || null,
    espnTier: document.body.textContent.includes('ESPN Tier'),
    advanced: adv ? {open: adv.open, last: [...adv.parentElement.children].pop() === adv,
      eyebrows: [...adv.querySelectorAll('.v2-eyebrow')].map(h => h.textContent)} : null}; }"""

MODULES_JS = """() => [...document.querySelectorAll('main:not([hidden]) section.v2-card')]
  .filter(c => c.offsetParent !== null && !c.classList.contains('v2-state') && !c.classList.contains('v2-skel'))
  .map(c => { const h = c.querySelector('h2'); const chev = c.querySelector(':scope > .v2-mod-ctl .v2-mod-chevron');
    const exp = c.querySelector(':scope > .v2-mod-ctl .v2-mod-expand');
    return {title: h ? h.textContent.trim() : c.className, chevron: Boolean(chev),
      aria: chev ? chev.getAttribute('aria-expanded') : null, expand: Boolean(exp),
      h: chev ? chev.getBoundingClientRect().height : 0}; })"""


def scenario_tabs(s: Session) -> dict:
    page = s.open("#trade-targets")   # JEG-1106: an empty hash now lands on the value chart; this scenario starts on Trade targets
    try:
        page.wait_for_function("() => window.TradeValueV2.targets()", timeout=40000)
        page.wait_for_timeout(300)
        out = {"targets": page.evaluate(TARGETS_JS)}
        page.evaluate("() => { location.hash = '#risers-fallers'; }")
        page.wait_for_function("() => document.querySelectorAll('#v2RRise li').length || !document.getElementById('v2RRiseEmpty').hidden", timeout=40000)
        page.wait_for_timeout(300)
        out["risers"] = page.evaluate(RISERS_JS)
        page.evaluate("() => { location.hash = '#compare-trade'; }")
        page.wait_for_function("() => window.TradeValueV2.compare() && document.querySelectorAll('#v2CTable tbody tr[data-source]').length", timeout=40000)
        page.wait_for_timeout(300)
        out["compare"] = page.evaluate(COMPARE_JS)
        page.evaluate("() => { location.hash = '#writing/how-values'; }")
        page.wait_for_timeout(600)
        out["how"] = page.evaluate(HOW_JS)
        page.evaluate("() => { location.hash = '#writing/manifesto'; }")
        page.wait_for_timeout(400)
        out["manifesto"] = page.evaluate(MANIFESTO_JS)
        out["gl20"] = page.evaluate(GL20_JS)
        out["modules"] = {}
        for tab in ("#player-values", "#trade-targets", "#risers-fallers", "#compare-trade", "#find-trade"):
            page.evaluate("h => { location.hash = h; }", tab)
            page.wait_for_timeout(500)
            out["modules"][tab] = page.evaluate(MODULES_JS)
        page.evaluate("() => { location.hash = '#player-values'; }")
        page.wait_for_timeout(400)
        page.click("#v2EditLeague")
        page.wait_for_timeout(300)
        out["leaguePanel"] = page.evaluate(LEAGUE_PANEL_JS)
        page.keyboard.press("Escape")
        out["errors"] = page.errors
        return out
    finally:
        page.close()


def scenario_phone(s: Session) -> dict:
    page = s.open("#trade-targets", width=390, height=844)
    try:
        out = {"tabs": [page.evaluate(PHONE_JS, h) for h in
                        ("#writing/manifesto", "#player-values", "#trade-targets", "#risers-fallers", "#compare-trade", "#find-trade", "#writing/how-values", "#values-auditing")]}
        out["errors"] = page.errors
        return out
    finally:
        page.close()


def scenario_failure(s: Session) -> dict:
    page = s.open("#player-values", engine_fails=True, wait=False)
    try:
        page.wait_for_function("() => document.querySelector('#v2State .v2-state')?.dataset.state !== 'loading'", timeout=40000)
        page.wait_for_timeout(300)
        out = page.evaluate(FAILURE_JS)
        out["errors"] = page.errors
        return out
    finally:
        page.close()


# Shipped-but-pending lines (GL-07, GL-19, GL-21, GL-22): the Doc still says "to build" for
# these, so they stay PENDING with a partial check that runs like a live one. The probes read
# Customize on each data page, the league buttons, the text of every page and whether Compare's verdict card has headline lines (CT-02).
CUSTOMIZE_JS = "async () => {" + COMMON + r"""
  const out = {league: {edit: shown($('v2EditLeague')), weights: shown($('v2Weights'))}};
  const edit = $('v2EditLeague'), weights = $('v2Weights');
  out.league.editPrimary = edit.classList.contains('v2-btn-primary');
  out.league.weightsPrimary = weights.classList.contains('v2-btn-primary');
  out.league.editLabel = edit.textContent.trim(); out.league.weightsLabel = weights.textContent.trim();
  out.league.editFirst = Boolean(edit.compareDocumentPosition(weights) & Node.DOCUMENT_POSITION_FOLLOWING);
  const text = visibleText() + ' ' + attrText($('v2App'));
  out.text = {asPublished: (text.match(/as published/gi) || []).length, indexed: (text.match(/\bindexed\b/gi) || []).length};
  $('v2EditSources').click(); await sleep(400);
  const pop = $('v2Popover');
  const pub = pop.querySelector('.v2-cgroup[data-group="pub"]');
  const checked = () => [...pop.querySelectorAll('input[data-series]:checked')].map(i => i.dataset.series);
  out.groups = [...pop.querySelectorAll('.v2-cgroup[data-group]')].map(g => ({id: g.dataset.group, title: g.querySelector('h3').textContent.trim(),
    call: (g.querySelector('.v2-call') || {}).textContent || '', meta: (g.querySelector(':scope > .v2-meta') || {}).textContent || ''}));
  out.footer = [...pop.querySelectorAll('button')].map(b => b.textContent.trim()).filter(t => /^(Reset to default|Done|Cancel)$/.test(t));
  out.versions = [...pop.querySelectorAll('input[data-series^="ddf_value"]')].map(i => i.dataset.series);
  out.checked = checked();
  const call = pub ? pub.querySelector('.v2-call') : null;
  if (call) {
    const grp = () => $('v2Popover').querySelector('.v2-cgroup[data-group="pub"]');   // the panel re-renders on a click
    const inGroup = () => [...grp().querySelectorAll('input[data-series]')].filter(i => i.checked).length;
    const total = grp().querySelectorAll('input[data-series]:not(:disabled)').length;
    const callBtn = () => grp().querySelector('.v2-call');
    callBtn().click(); await sleep(200); const first = inGroup(); const word1 = callBtn().textContent.trim();
    callBtn().click(); await sleep(200);
    out.selectAll = {total, first, word1, second: inGroup(), word2: callBtn().textContent.trim()};
  }
  const cancel = [...pop.querySelectorAll('button')].find(b => b.textContent.trim() === 'Cancel');
  if (cancel) cancel.click(); await sleep(250);
  out.cancelled = $('v2Popover').hidden;
  return out;
}"""

HEADLINES_JS = "() => {" + COMMON + r"""
  const card = $('v2CVerdict');
  return {box: Boolean($('v2CHeads')), lines: card.querySelectorAll('[data-line]').length, text: card.innerText.replace(/\s+/g, ' ').trim()};
}"""


def scenario_shipped(s: Session) -> dict:
    out = {"customize": {}}
    for tab in ("#player-values", "#trade-targets", "#risers-fallers", "#compare-trade"):
        page = s.open(tab)
        try:
            out["customize"][tab] = page.evaluate(CUSTOMIZE_JS)
            if tab == "#compare-trade":
                out["headlines"] = page.evaluate(HEADLINES_JS)
            out.setdefault("errors", []).extend(page.errors)
        finally:
            page.close()
    page = s.open("#player-values")
    try:
        info = page.locator("button.v2-info[data-info]:visible").first
        opened = "() => { const p = document.getElementById('v2Popover'); return !p.hidden && p.innerText.trim().length > 0; }"
        hov = {}
        info.hover()
        page.wait_for_timeout(700)
        hov["hover"] = page.evaluate(opened)
        page.mouse.move(2, 2)
        page.wait_for_timeout(700)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        info.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(400)
        hov["keyboard"] = page.evaluate(opened)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        info.click()
        page.wait_for_timeout(400)
        hov["click"] = page.evaluate(opened)
        out["info"] = hov
        out.setdefault("errors", []).extend(page.errors)
    finally:
        page.close()
    return out


SCENARIOS = {"values": scenario_values, "tabs": scenario_tabs, "phone": scenario_phone, "failure": scenario_failure,
             "shipped": scenario_shipped}


# ---------------------------------------------------------------- checks
# Each check takes the scenario snapshots {name: snapshot} and returns a list of errors.

SYM = re.compile(r"^\s*[^\w\s]")       # a status starts with a symbol, then a word
RAW_KEY = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")   # an engine key such as fantasycalc_adj_values
TIERS = {"Starter": 0, "Bench": 1, "Waiver": 2}


def _num(text):
    m = re.search(r"[−-]?\d+(?:\.\d+)?", str(text or "").replace("−", "-"))
    return float(m.group(0).replace("−", "-")) if m else None


def _texts(S):
    t = S["tabs"]
    v = S["values"]["s0"]
    return {"Player values": v["text"] + "\n" + v["attrs"], "Trade targets": t["targets"]["text"] + "\n" + t["targets"]["attrs"],
            "Risers & fallers": t["risers"]["text"] + "\n" + t["risers"]["attrs"],
            "Compare a trade": t["compare"]["text"] + "\n" + t["compare"]["attrs"],
            "How values work": t["how"]["text"] + "\n" + t["how"]["attrs"],
            "Manifesto": t["manifesto"]["text"], "Player detail": S["values"]["drawer"]["text"]}


def gl01(S):
    errors = []
    for tab, text in _texts(S).items():
        if tab != "Player detail" and "Data Driven Football" not in text:
            errors.append(f"{tab}: no 'Data Driven Football'")
        if re.search(r"vegas", text, re.I):
            errors.append(f"{tab}: says Vegas")
        # JEG-861 (2026-10-22): no "VORP" anywhere in user-facing text; the term is "Value above waivers".
        m = re.search(r"vorp", text, re.I)
        if m:
            errors.append(f"{tab}: says VORP: {text[max(0, m.start() - 20):m.start() + 30]!r}")
    return errors


def gl02(S):
    errors = []
    v = S["values"]["s0"]
    # Engine values equal the engine (Player values table, first 40 rows, every shown series).
    for row in v["table"][:40]:
        eng = v["engine"].get(row["key"])
        if not eng:
            errors.append(f"table row {row['key']} has no engine row")
            continue
        for cell in row["cells"]:
            ev = eng["values"].get(cell["src"])
            shown_v = _num(cell["text"])
            if ev is None:
                continue
            if shown_v is None or abs(shown_v - round(ev, 1)) > 0.051:
                errors.append(f"{row['name']} {cell['src']}: shows {cell['text']!r}, engine {ev:.2f}")
    # One engine value per other tab: Trade targets "Our value", Risers & fallers before / now.
    t = S["tabs"]["targets"]
    for row in (t["sell"] + t["buy"])[:3]:
        ev = ((t["engine"].get(row["key"]) or {}).get("values") or {}).get(t["ours"])
        if ev is None or abs(row["ours"] - round(ev, 1)) > 0.051:
            errors.append(f"targets {row['name']}: Our value {row['ours']}, engine {ev}")
    r = S["tabs"]["risers"]
    if not r["top"]:
        errors.append("Risers & fallers: no risers to compare with the engine")
    for shown_r, eng_r in zip(r["top"], r["engineTop"]):
        for col in ("before", "now"):
            sv, ev = _num(shown_r[col]), eng_r[col]
            if ev is None or sv is None or abs(sv - round(ev, 1)) > 0.051:
                errors.append(f"risers {shown_r['key']} {col}: shows {shown_r[col]!r}, engine {ev}")
        d = _num(shown_r["delta"])
        if None not in (d, eng_r["before"], eng_r["now"]) and abs(d - (eng_r["now"] - eng_r["before"])) > 0.11:
            errors.append(f"risers {shown_r['key']}: change {shown_r['delta']!r}, engine {eng_r['now'] - eng_r['before']:.2f}")
    # Front-end values against an independent calculation: Trade targets gaps, Compare nets, Δ.
    for row in S["tabs"]["targets"]["sell"] + S["tabs"]["targets"]["buy"]:
        for c in row["charts"]:
            cv, gap = _num(c["text"]), _num(c["gap"])
            if cv is not None and gap is not None and abs((cv - row["ours"]) - gap) > 0.11:
                errors.append(f"targets {row['name']} {c['chart']}: gap {c['gap']} but {cv} − {row['ours']}")
    comp = S["tabs"]["compare"]
    eng = comp["engine"]
    for r in comp["rows"]:
        give = sum((eng[p["key"]] or {"values": {}})["values"].get(r["src"]) or 0 for p in comp["example"]["give"])
        get = sum((eng[p["key"]] or {"values": {}})["values"].get(r["src"]) or 0 for p in comp["example"]["get"])
        if abs(give - r["give"]) > 0.11 or abs(get - r["receive"]) > 0.11:
            errors.append(f"compare {r['src']}: give/receive {r['give']}/{r['receive']}, engine sums {give:.1f}/{get:.1f}")
    for row in S["values"]["delta"]["table"]:
        for c in row["cells"]:
            if c["delta"]:
                now, prior, d = _num(c["text"]), _num(c["delta"]["title"].split(":")[-1]), _num(c["delta"]["text"])
                if None not in (now, prior, d) and abs((now - prior) - d) > 0.11:
                    errors.append(f"Δ {row['name']} {c['src']}: {c['delta']['text']} but {now} − {prior}")
    for tab, text in _texts(S).items():
        for bad in ("undefined", "NaN"):
            if re.search(rf"\b{bad}\b", text):
                errors.append(f"{tab}: shows {bad!r}")
    return errors


def gl03(S):
    errors = []
    v = S["values"]["s0"]
    for row in v["table"]:
        eng = v["engine"].get(row["key"]) or {"values": {}, "low": False}
        for c in row["cells"]:
            ev = eng["values"].get(c["src"])
            if c["text"].startswith("—"):
                if ev is not None:
                    errors.append(f"{row['name']} {c['src']}: '—' but the engine has {ev}")
                if not c["title"]:
                    errors.append(f"{row['name']} {c['src']}: '—' without a reason")
            elif ev is None:
                errors.append(f"{row['name']} {c['src']}: shows {c['text']!r} for an engine null")
            elif ev == 0 and c["text"] != "0.0":
                errors.append(f"{row['name']} {c['src']}: engine 0 shown as {c['text']!r}")
            if c["src"] == "ddf_value" and eng["low"] != c["lowconf"]:
                errors.append(f"{row['name']}: one-source DDF Value {eng['low']} but tag {c['lowconf']}")
            if c["lowconf"] and not c["lowconfTitle"]:
                errors.append(f"{row['name']}: '◐ 1 source' without a tooltip")
            if c["lowconf"] and c["lowconfText"] != "◐ 1 source":
                errors.append(f"{row['name']}: one-source tag reads {c['lowconfText']!r}, want '◐ 1 source'")
    if not any((v["engine"].get(r["key"]) or {}).get("low") for r in v["table"]):
        errors.append("no one-source DDF Value in the table to check (LOW_CONFIDENCE_FIXTURE not applied?)")
    return errors


def gl04(S):
    errors = []
    v = S["values"]
    if not v["fresh"]:
        errors.append("freshness dialog has no rows")
    for r in v["fresh"]:
        if not SYM.match(r["text"]) or not re.search(r"[A-Za-z]", r["text"]):
            errors.append(f"freshness {r['src']} ({r['status']}): {r['text']!r} has no symbol + word")
    chip = v["s0"]["chip"]["label"]
    if "current" not in chip.lower() and not re.search(r"[⚠?✓]", chip):
        errors.append(f"freshness chip {chip!r}: a warning without a symbol")
    for row in v["s0"]["table"][:20]:
        for c in row["cells"]:
            if c["heat"] and not re.search(r"above|below|level", c["title"]):
                errors.append(f"{row['name']} {c['src']}: heat tint without words")
    for side in ("sell", "buy"):
        if not S["tabs"]["targets"]["text"]:
            break
    t = S["tabs"]["targets"]["text"]
    if "▲" not in t or "Sell" not in t or "▼" not in t or "Buy" not in t:
        errors.append("Trade targets: Sell / Buy headings lose their symbol or word")
    return errors


def gl05(S):
    errors = []
    v = S["values"]
    want = {"usatoday": "prior", "cbs": "held", "fantasycalc": "stuck"}
    got = {r["src"]: r for r in v["fresh"]}
    for src, status in want.items():
        r = got.get(src)
        if not r:
            errors.append(f"freshness: no row for {src}")
        elif r["status"] != status or "Current" in r["text"]:
            errors.append(f"freshness {src}: {r['status']} {r['text']!r}, want {status} with a warning")
    if not any(r["status"] == "current" and "Current" in r["text"] for r in v["fresh"]):
        errors.append("freshness: no confirmed source says Current")
    chip = v["s0"]["chip"]["label"]
    if "current" in chip.lower() or "⚠" not in chip:
        errors.append(f"chip with sources behind / unknown / failing says {chip!r}")
    prior = v["reload_prior"]["chip"]
    if "current" in prior.lower() or "⚠" not in prior:
        errors.append(f"chip with one source a week behind says {prior!r}")
    # JEG-721: CBS is held in the pinned fixture, so even when every source's pipeline
    # freshness is green the chip must say "held", not "all sources current".
    reload_chip = v["reload"]["chip"]
    if "all sources current" in reload_chip:
        errors.append(f"chip claims 'all sources current' but CBS is held: {reload_chip!r}")
    if "held" not in reload_chip.lower():
        errors.append(f"chip with a held source does not mention it: {reload_chip!r}")
    return errors


def gl06(S):
    v = S["values"]["s0"]
    rects = v["showingRects"]
    if None in rects or v["legendCount"] < 1 or v["customize"] != "Customize":
        return [f"Showing bar parts missing: rects {rects}, legend {v['legendCount']}, button {v['customize']!r}"]
    mids = [r["y"] + r["h"] / 2 for r in rects]
    if max(mids) - min(mids) > 14:
        return [f"Showing bar is not one line at 1440: centres {mids}"]
    return []


def gl08(S):
    errors = []
    v, t = S["values"]["s0"], S["tabs"]
    for where, value in (("Player values Rank by", v["rankBy"]), ("Trade targets Our value", t["targets"]["ours"]),
                         ("Risers & fallers", t["risers"]["series"]), ("Compare a trade", t["compare"]["shownKey"])):
        if value != "ddf_value":
            errors.append(f"{where} defaults to {value!r}, not DDF Value")
    tiers_by_ddf = all(r["tier"] in TIERS for r in v["table"][:10])
    if not tiers_by_ddf:
        errors.append("Player values rows show no tier under DDF Value")
    return errors


def gl09(S):
    """GL-09 (JEG-542): the two pickable DDF Value versions are offered everywhere; blended is on, the other off.
    JEG-1073: ddf_value_charts is hidden from all pickers (sameAs ddf_value), so DDF Value and the projections alternate are pickable."""
    versions = ["ddf_value", "ddf_value_projections"]   # JEG-1073: ddf_value_charts hidden (sameAs ddf_value)
    v, t = S["values"]["s0"], S["tabs"]
    errors = []
    on = [k for k in versions if k in v["shown"]]
    if on != ["ddf_value"]:
        errors.append(f"DDF Value versions shown by default {on}, want only the blended one")
    for where, options in (("Rank by", v["rankOptions"]), ("Risers & fallers", t["risers"]["firstGroupKeys"]),
                           ("Compare's Player values shown", [o[0] for o in t["compare"]["shownOptions"]]),
                           ("Trade targets' Our value", t["targets"]["oursOptions"])):
        missing = [k for k in versions if k not in options]
        if missing:
            errors.append(f"{where} does not offer {missing}")
    # ddf_value_charts must NOT appear in pickers (it's the hidden duplicate).
    for where, options in (("Rank by", v["rankOptions"]),
                           ("Trade targets' Our value", t["targets"]["oursOptions"])):
        if "ddf_value_charts" in options:
            errors.append(f"{where} still shows ddf_value_charts (should be hidden via sameAs)")
    return errors


def gl10(S):
    v = S["values"]
    errors = []
    if not v["remember"]["stored"]:
        errors.append("the selection is not saved on this device")
    if v["reload"]["rankBy"] != v["remember"]["key"]:
        errors.append(f"after a reload Rank by is {v['reload']['rankBy']!r}, chose {v['remember']['key']!r}")
    return errors


def gl11(S):
    v = S["values"]
    errors = []
    # GL-11 (v1.2) was draft-until-Apply; JEG-1020 (Jeremy, 2026-10-24) replaced it: settings apply as they change.
    # Buttons are found by ID, never by label ("Weights & bench" becomes "Position weights").
    if not v["s0"]["leagueButtons"]["edit"]:
        errors.append("no Edit league control (#v2EditLeague)")
    lg = v["league"]
    if not (lg["changed"] and lg["hasUndo"]) or lg["hasApply"] or lg["hasCancel"]:
        errors.append(f"Edit league dialog: changed {lg['changed']}, Undo {lg['hasUndo']}, Apply {lg['hasApply']}, Cancel {lg['hasCancel']}")
    if lg["immediateTeams"] != lg["engineTeams"]:
        errors.append(f"a league tap reached the engine inside the input handler (no debounce): {lg['engineTeams']} -> {lg['immediateTeams']}")
    if lg["liveTeams"] == lg["engineTeams"]:
        errors.append(f"a league change did not apply on its own: teams stayed {lg['liveTeams']}")
    if lg["afterTeams"] != lg["engineTeams"] or lg["after"] != lg["before"]:
        errors.append(f"Undo changes did not return the league: teams {lg['engineTeams']} -> {lg['liveTeams']} -> {lg['afterTeams']}; {lg['before']!r} -> {lg['after']!r}")
    return errors


def gl12(S):
    """The bench share shown is the engine's own readout (or the reader's override): no math in v2."""
    h = S["tabs"]["how"]
    r = h["readout"]
    want = (f"{r['overrideValue'] * 100:.1f}% (your override)" if r["override"]
            else " · ".join(f"{p} {r[p] * 100:.1f}%" for p in ("QB", "RB", "WR", "TE")))
    return [] if h["bench"] == want else [f"How values bench share {h['bench']!r}, engine readout {want!r}"]


def gl23(S):
    h = S["tabs"]["how"]
    r = h["readout"]
    errors = []
    if h["slider"]:
        errors.append("a bench-share slider is on the page with the override off")
    if r["override"] or r["method"] != "expected-starts":
        errors.append(f"default readout: override {r['override']}, method {r['method']!r}")
    return errors


def gl28(S):
    """Default league 12 teams / 1-2-2-1-1 / 1 K / 1 DEF / 7 bench; K and DEF steppers; the column is headed Tier."""
    p = S["tabs"]["leaguePanel"]
    errors = []
    want = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0, "K": 1, "DST": 1, "BENCH": 7}
    if p["shape"] != want or p["teams"] != 12:
        errors.append(f"default league is {p['shape']} with {p['teams']} teams, want {want} and 12")
    for aria in ("Fewer K", "More K", "Fewer DEF", "More DEF"):
        if aria not in p["stepperAria"]:
            errors.append(f"Edit league has no {aria!r} stepper")
    # The column is folded into the player's sub-line on a narrow table, so a missing head is not a failure.
    if p["tierHead"] is not None and p["tierHead"].strip() != "Tier":
        errors.append(f"the tier column is headed {p['tierHead']!r}, want 'Tier'")
    if p["espnTier"]:
        errors.append("the page still says 'ESPN Tier'")
    return errors


def gl24(S):
    p = S["tabs"]["leaguePanel"]
    errors = []
    for label in ("Last regular-season week", "First playoff week", "Last playoff week"):
        if label not in p["steps"]:
            errors.append(f"Your league has no {label!r} control: {p['steps']}")
    if "Optimize for" not in p["eyebrows"]:
        errors.append(f"no Optimize for: {p['eyebrows']}")
    adv = p["advanced"]
    if not adv or adv["open"] or not adv["last"] or adv["eyebrows"] != ["Injury history", "Projection confidence", "Bench-share override"]:
        errors.append(f"Advanced should be collapsed, last, with the three settings: {adv}")
    return errors


def gl13(S):
    errors = []
    for r in S["phone"]["tabs"]:
        if r["overflow"] > 0:
            errors.append(f"390 px {r['hash']}: scrolls sideways by {r['overflow']} px")
        if not r["page"] or r["height"] < 200 or not r["nav"]:
            errors.append(f"390 px {r['hash']}: tab not usable ({r['page']}, {r['height']:.0f} px, nav {r['nav']})")
    return errors


def gl14(S):
    f = S["failure"]
    errors = []
    if f["state"] != "failed" or not f["retry"]:
        errors.append(f"engine failure: state {f['state']!r}, retry {f['retry']}")
    if any(f["pages"].values()):
        errors.append(f"engine failure still shows a tab: {f['pages']}")
    if re.search(r"\d+\.\d", f["text"]):
        errors.append("engine failure page shows a number")
    return errors


def gl15(S):
    errors = []
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    core = makefile.split("test-core:", 1)[-1].split("\n\n", 1)[0]
    if "tests.test_rank_guard" not in core:
        errors.append("the rank guard is not in make test-core (the deploy gate)")
    v = S["values"]["s0"]
    for src, ranks in v["native"].items():
        if src == "ddf_value" or not any(r is not None for r in ranks.values()):
            continue
        rows = [(_num(c["text"]), ranks.get(row["key"])) for row in v["table"] for c in row["cells"] if c["src"] == src]
        rows = [(val, rank) for val, rank in rows if val is not None and rank is not None]
        rows.sort(key=lambda x: (-x[0], x[1]))
        rows = rows[:25]   # the chart's own top 25 among the shown rows
        bad = [(a, b) for a, b in zip(rows, rows[1:]) if a[0] > b[0] + 0.05 and a[1] > b[1]]
        if bad:
            errors.append(f"{src}: rescaled values out of the publisher's order, e.g. {bad[0]}")
    return errors


def _monotone(tiers):
    seq = [TIERS[t] for t in tiers if t in TIERS]
    return len(seq) > 5 and all(a <= b for a, b in zip(seq, seq[1:]))


def gl16(S):
    v = S["values"]
    errors = []
    ddf = v["s0"]["table"]
    if not _monotone([r["tier"] for r in ddf]):
        errors.append("under DDF Value, tiers are not in rank order")
    for r in ddf[:60]:
        want = (v["s0"]["engine"].get(r["key"]) or {}).get("tier")
        if want and r["tier"].lower() != want.lower():
            errors.append(f"{r['name']}: tier {r['tier']!r}, DDF tier {want!r}")
            break
    other = v["otherRank"]
    if other["value"] != other["key"]:
        errors.append(f"Rank by did not switch to {other['key']}")
    elif not _monotone([r["tier"] for r in other["table"]]):
        errors.append(f"ranked by {other['key']}, tiers are not in that series' order")
    elif {r["key"]: r["tier"] for r in ddf} == {r["key"]: r["tier"] for r in other["table"] if r["key"] in {d["key"] for d in ddf}}:
        errors.append(f"tiers did not change with Rank by ({other['key']})")
    return errors


def gl20(S):
    g = S["tabs"]["gl20"]
    p = g.get("pick")
    if not p:
        return ["the engine's search has no player that no source prices"]
    errors = []
    for tab, text in (("Player values", g["pv"]), ("Trade targets", g["tt"]), ("Risers & fallers", g["rf"]),
                      ("Compare a trade", (g["ct"] or {}).get("text"))):
        if not text:
            errors.append(f"{tab}: searching {p['name']!r} does not show him")
        elif "0.0" not in text or (p["reason"] or "") not in text:
            errors.append(f"{tab}: {p['name']} shown without 0.0 and his reason: {text!r}")
    if g["pvInTable"]:
        errors.append(f"{p['name']} (no value) appears in the Player values table")
    if g["ct"] and not g["ct"]["disabled"]:
        errors.append(f"{p['name']} (no value) can be added to a trade")
    return errors


MANIFESTO_MIRROR = ROOT / "docs" / "manifesto-mirror.md"


def manifesto_words(mirror: str) -> list[str]:
    """The Manifesto Doc's words: the mirror body without Markdown marks (#, **, list dashes)."""
    body = mirror.split("-->", 1)[1] if mirror.startswith("<!--") else mirror
    body = re.sub(r"^\s*- ", " ", body, flags=re.M)
    return body.replace("*", "").replace("#", " ").split()


def mf01(S):
    m = S["tabs"]["manifesto"]
    t = S["tabs"]["targets"]
    errors = []
    first = m["sections"][0] if m["sections"] else {}
    if (first.get("slug"), first.get("label")) != ("manifesto", "Manifesto"):
        errors.append(f"first Writing section is {first}, want Manifesto")
    if [x["view"] for x in m["tabs"] if x["current"]] != ["writing"] or [x["slug"] for x in m["sections"] if x["current"]] != ["manifesto"]:
        errors.append(f"#writing/manifesto: current tab/section wrong: {m['tabs']} {m['sections']}")
    if not m["pages"]["v2Manifesto"] or m["h1"] != "Fantasy Football Manifesto" or len(m["h2"]) != 12:
        errors.append(f"Manifesto: shown {m['pages']['v2Manifesto']}, h1 {m['h1']!r}, {len(m['h2'])} sections")
    if m["controls"]:
        errors.append(f"Manifesto has {m['controls']} links or controls; it is plain text")
    want, got = manifesto_words(MANIFESTO_MIRROR.read_text(encoding="utf-8")), m["words"].split()
    if want != got:
        i = next((k for k, (a, b) in enumerate(zip(want, got)) if a != b), min(len(want), len(got)))
        errors.append(f"Manifesto text differs from docs/manifesto-mirror.md at word {i}: "
                      f"Doc {' '.join(want[max(0, i - 3):i + 4])!r}, page {' '.join(got[max(0, i - 3):i + 4])!r}"
                      f" ({len(want)} vs {len(got)} words)")
    if [x["view"] for x in t["tabs"] if x["current"]] != ["targets"] or not t["pages"]["v2Targets"]:
        errors.append("the landing tab is not Trade targets")
    return errors


def pv01(S):
    v = S["values"]["s0"]
    errors = []
    if v["rankBy"] != "ddf_value" or not v["shown"] or v["shown"][0] != "ddf_value":
        errors.append(f"default: Rank by {v['rankBy']!r}, shown {v['shown']}")
    charts = [k for k in v["shown"][1:] if "_" not in k and k not in ("espn", "cbsros", "razzball")]
    if not charts or len(charts) != len(v["shown"]) - 1:
        errors.append(f"default series beside DDF Value are not the rescaled charts: {v['shown'][1:]}")
    if not v["showingText"].startswith("DDF Value"):
        errors.append(f"Showing says {v['showingText']!r}")
    return errors


def pv02(S):
    series = S["values"]["s0"]["series"]
    if len(series) < 2:
        return [f"chart has {len(series)} series"]
    ddf = [s for s in series if "is-ddf" in s["cls"]]
    if not ddf:
        return ["no DDF Value line on the chart"]
    errors = []
    if "is-ddf" not in series[-1]["cls"]:
        errors.append("the DDF Value line is not drawn on top")
    if ddf[0]["width"] <= max(s["width"] for s in series if "is-ddf" not in s["cls"]):
        errors.append(f"the DDF Value line ({ddf[0]['width']}px) is not heavier than the others")
    return errors


def pv03(S):
    x = S["values"]["xbrush"]
    texts = " ".join(x["texts"])
    named = [n for n in x["rows"] if any(part[:6] in texts for part in n.split()[-1:])]
    return [] if len(x["rows"]) and len(named) >= max(1, len(x["rows"]) - 1) else [f"zoomed to {x['rows']}, chart labels {x['texts']}"]


def pv04(S):
    z = S["values"]["s0"]["zones"]
    errors = []
    in_view = [n for n in ("starter_to_bench", "bench_to_waiver") if z["ranks"] and z["ranks"][0] < z["engine"][n] < z["ranks"][-1]]
    if sorted(line["name"] for line in z["lines"]) != sorted(in_view):
        errors.append(f"break lines {[line['name'] for line in z['lines']]}, engine zones {z['engine']} over ranks {z['ranks'][:1]}..{z['ranks'][-1:]}")
    if not z["labels"] or any(label not in ("Starters", "Bench", "Waiver") for label in z["labels"]):
        errors.append(f"zone labels {z['labels']}")
    return errors


def pv06(S):
    bad = [f for f in S["values"]["s0"]["brushFill"] if f["tab"] != 0 or f["role"] != "group" or "whole" not in (f["label"] or "")]
    return [f"brush fill is not a keyboard-reachable whole-range handle: {bad}"] if bad else []


def pv07(S):
    items = S["values"]["s0"]["legendItems"]
    bad = [i for i in items if i["pressed"] not in ("true", "false") or not i["mark"]]
    return [f"legend entries without a pressed state and symbol: {bad}"] if bad or not items else []


def pv05(S):
    v = S["values"]
    errors = []
    if v["xbrush"]["show"] != "custom" or not 0 < len(v["xbrush"]["rows"]) <= 5:
        errors.append(f"X brush to rank 5: Show {v['xbrush']['show']!r}, {len(v['xbrush']['rows'])} rows")
    y = v["ybrush"]
    if y["show"] != "custom" or not y["rows"] or any(val is None or val < 40 - 0.05 for val in y["rankValues"]):
        errors.append(f"Y brush from 40: Show {y['show']!r}, values {y['rankValues'][:5]}")
    return errors


def pv08(S):
    want = ["v2Search", "v2Position", "v2Show", "v2RankBy", "v2DeltaBtn", "v2More", "v2Reset"]
    got = [i for i in S["values"]["s0"]["toolbar"] if i in want]
    return [] if got == want else [f"toolbar order {got}"]


def pv09(S):
    r = S["values"]["reset"]
    want = {"rank": "ddf_value", "position": "ALL", "search": "", "show": "100"}
    return [] if r == want else [f"after Reset {r}, want {want}"]


def pv10(S):
    v = S["values"]
    errors = []
    if v["show25"] != 25:
        errors.append(f"Show Top 25 gives {v['show25']} rows")
    if v["s0"]["sticky"] != {"head": "sticky", "player": "sticky"}:
        errors.append(f"pinned header / Player column: {v['s0']['sticky']}")
    c = v["columns"]
    if not c["group"] or not c["before"] or c["after"]:
        errors.append(f"Columns menu did not hide a group: {c}")
    return errors


def pv11(S):
    errors = []
    v = S["values"]["s0"]
    tinted = 0
    for row in v["table"][:30]:
        rank = next((_num(c["text"]) for c in row["cells"] if c["src"] == v["rankBy"]), None)
        for c in row["cells"]:
            if c["src"] == v["rankBy"] or c["vs"] is None:
                continue
            val = _num(c["text"])
            want = "above" if c["vs"] == "above" else "below" if c["vs"] == "below" else "level"
            if want not in c["title"]:
                errors.append(f"{row['name']} {c['src']}: tooltip does not name the direction")
            if c["vs"] in ("above", "below"):
                tinted += c["heat"]
                if rank is not None and val is not None and (val > rank) != (c["vs"] == "above"):
                    errors.append(f"{row['name']} {c['src']}: {val} marked {c['vs']} the ranking value {rank}")
    if not tinted:
        errors.append("no heat tint on any value")
    return errors[:5]


def pv12(S):
    d = S["values"]["drawer"]
    errors = []
    if not d["shown"]:
        errors.append("clicking a row did not open the player detail")
    # Jeremy 2026-10-23: the detail is a list of the selected sources (source/week, kind, number); the old
    # publisher-by-method grid left blank cells and is gone. "Show all sources" lists every kind.
    for head in ("Source / week", "Kind", "Value"):
        if head not in d["heads"]:
            errors.append(f"player detail has no {head!r} column")
    if d.get("allToggle") is not False:
        errors.append("'Show all sources' is missing or not off by default")
    kinds = {r["kind"] for r in d.get("kindsAll") or []}
    for kind in ("DDF Value", "Market", "Value above waivers"):
        if kind not in kinds:
            errors.append(f"'Show all sources' lists no {kind!r} row")
    for r in d.get("kindsAll") or []:
        if not r["num"]:
            errors.append(f"player detail lists a {r['kind']!r} row with no number")
    if RAW_KEY.search(d["text"]):
        errors.append(f"player detail shows an engine key: {RAW_KEY.search(d['text']).group(0)}")
    return errors


def pv13(S):
    d = S["values"]["delta"]
    if d["pressed"] != "true":
        return ["Δ Prior week did not turn on"]
    deltas = [c for r in d["table"] for c in r["cells"] if c["delta"]]
    if not any(c["src"] == "ddf_value" for c in deltas):
        return ["Δ Prior week shows no change for DDF Value"]
    return []


def pv14(S):
    e = S["values"]["expandChart"]
    if not (e["shown"] and e["svg"]) or e["box"]["w"] < 0.9 * e["vw"] or e["box"]["h"] < 0.85 * e["vh"]:
        return [f"expanded chart: {e}"]
    return []


def pv15(S):
    e = S["values"]["expandTable"]
    errors = []
    if not (e["shown"] and e["table"]) or e["box"]["h"] < 0.85 * e["vh"]:
        errors.append(f"expanded table: {e['shown']}, {e['box']}")
    unsorted = [c for c, s in e["sortable"].items() if not s or s == "none"]
    if unsorted:
        errors.append(f"expanded table cannot sort by {unsorted}")
    return errors


def pv16(S):
    v = S["values"]
    errors = []
    if not v["xbrush"]["resetShown"]:
        errors.append("no Reset zoom while zoomed")
    z = v["zoomReset"]
    if z["resetShown"] or z["lo"] != z["min"] or z["ylo"] != 0 or z["yhi"] != z["ymax"]:
        errors.append(f"Reset zoom left the brushes at {z}")
    return errors


def gl27(S):
    """Source names link to the publisher's page (addresses from the data file), in a new tab."""
    data = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))["sources"]
    want = {k: (v.get("url") or v.get("source_url")) for k, v in data.items() if (v.get("url") or v.get("source_url"))}
    errors = []
    links = S["values"]["s0"]["legendLinks"] + S["tabs"]["targets"]["sourceLinks"]
    if not links:
        errors.append("no source links on the Showing legend or Trade targets heads")
    for pub, href, target in links:
        base = want.get(pub)
        norm = lambda u: re.sub(r"/(QB|RB|WR|TE)/", "/QB/", re.sub(r"-(qb|rb|wr|te)-", "-qb-", u or ""))
        if norm(href) != norm(base) or target != "_blank":
            errors.append(f"{pub}: link {href!r} (target {target!r}), the data file says {base!r}")
    return errors


def tt12(S):
    cells = S["tabs"]["targets"]["mathCells"]
    # JEG-899: inside a row or card list the cell is tabindex -1 (one tab stop per row list; ArrowRight from the
    # row, or a pointer, focuses it). Still focusable, so the contract is "0 or -1", never absent.
    bad = [c for c in cells if c[0] not in ("0", "-1") or c[1] != "v2MathTip"]
    return [f"chart values must be focusable and describedby the math tip: {bad[:3]}"] if bad or not cells else []


def gl26(S):
    n = S["values"]["s0"]["names"]
    errors = []
    if n["label"] != "On the chart:" or n["info"] != 1:
        errors.append(f"the header row reads {n['label']!r} with {n['info']} definition buttons, want 'On the chart:' and one")
    return errors


def hv02(S):
    h = S["tabs"]["how"]
    errors = []
    if h["primaries"] != ["DDF Value", "Trade chart average"] or not h["edge"]:
        errors.append(f"How values work leads with {h['primaries']}, edge section {h['edge']}")
    if "Data Driven Adjustments" in h["outside"] or re.search(r"\bDDA\b", h["outside"]):
        errors.append("How values work still says Data Driven Adjustments / DDA")
    return errors


def pv18(S):
    f = S["values"]["s0"]["fit"]
    if not f["values"] or not f["ticks"]:
        return [f"no axis to read: {f}"]
    lo, hi = min(f["values"]), max(f["values"])
    errors = []
    if f["ticks"][0] > lo or f["ticks"][-1] < hi:
        errors.append(f"the Y axis {f['ticks'][0]}..{f['ticks'][-1]} does not cover the visible points {lo:.1f}..{hi:.1f}")
    if f["ticks"][-1] - hi > (hi - lo) * 0.5 + 10 or lo - f["ticks"][0] > (hi - lo) * 0.5 + 10:
        errors.append(f"the Y axis {f['ticks'][0]}..{f['ticks'][-1]} is much wider than the visible points {lo:.1f}..{hi:.1f}")
    return errors


def pv19(S):
    z = S["values"]["s0"]["zeroPlayers"]
    errors = []
    if z["listed"]:
        errors.append(f"{z['listed']} listed players are 0 on every shown series")
    if not z["hidden"]:
        errors.append("no all-zero players are hidden (and noted)")
    return errors


def pv20(S):
    opts = S["values"]["s0"]["rankOptions"]
    missing = [k for k in ("espn", "cbsros") if k not in opts]
    return [f"Rank by does not offer {missing}: {opts}"] if missing else []


def pv17(S):
    v = S["values"]
    c = v["chip"]
    errors = []
    if "ranks" not in v["xbrush"]["chips"]:
        errors.append(f"no chip for the rank brush: {v['xbrush']['chips']}")
    if not any(ch.startswith("position") for ch in c["chips"]):
        errors.append(f"no chip for Position QB: {c['chips']}")
    if c["positionAfter"] != "ALL" or c["chipsAfter"]:
        errors.append(f"clearing the chip left Position {c['positionAfter']!r}, {c['chipsAfter']} chips")
    return errors


def gl17(S):
    # Player values' chart and table open full screen (JEG-483); every other card spans its row (JEG-500).
    v = S["values"]
    errors = []
    if not (v["expandChart"]["shown"] and v["expandChart"]["svg"]):
        errors.append("Player values: the chart does not expand")
    if not (v["expandTable"]["shown"] and v["expandTable"]["table"]):
        errors.append("Player values: the table does not expand")
    for tab, cards in S["tabs"]["modules"].items():
        if not cards:
            errors.append(f"{tab}: no cards found")
        errors += [f"{tab}: {c['title']!r} has no expand control" for c in cards if not c["expand"]]
    return errors


def gl18(S):
    # Every card has a 44 px chevron that announces its state; the collapsed summary and the
    # remembered state are in tests/test_v2_modules_render.py.
    errors = []
    for tab, cards in S["tabs"]["modules"].items():
        for c in cards:
            if not c["chevron"]:
                errors.append(f"{tab}: {c['title']!r} has no collapse chevron")
            elif c["aria"] not in ("true", "false") or c["h"] < 44:
                errors.append(f"{tab}: {c['title']!r} chevron aria-expanded {c['aria']!r}, {c['h']:.0f} px tall")
    return errors


def tt01(S):
    h = S["tabs"]["targets"]["h1"]
    return [] if h == "Trade targets" else [f"headline {h!r}"]


def tt02(S):
    t = S["tabs"]["targets"]
    errors = []
    # JEG-1073: DDF Value is the Adjusted chart average, so "ours" and the market consensus come from the same charts and
    # the gap lists are shorter than they were against projections; a side can have 5 or fewer targets. The rule is the
    # cap of five with a Show all control exactly when more exist, not a minimum list length.
    for side in ("sell", "buy"):
        n, total = len(t[side]), t[f"{side}All"]
        if n != min(5, total) or t[f"{side}More"] != (total > 5):
            errors.append(f"{side}: {n} rows of {total}, Show all {t[f'{side}More']}")
    a, b = t["rects"]
    if not (a and b and abs(a["y"] - b["y"]) < 4 and a["x"] + a["w"] <= b["x"] + 1):
        errors.append(f"Sell and Buy are not side by side at 1440: {a} {b}")
    return errors


def tt03(S):
    t = S["tabs"]["targets"]
    errors = []
    if t["ours"] != "ddf_value":
        errors.append(f"Our value defaults to {t['ours']!r}")
    for r in t["sell"] + t["buy"]:
        if not re.search(r"\d+ sources?", r["count"]):
            errors.append(f"{r['name']}: no source count")
        if RAW_KEY.search(r["countTitle"]):
            errors.append(f"{r['name']}: source list shows an engine key ({RAW_KEY.search(r['countTitle']).group(0)})")
            break
    return errors


def gl25(S):
    """The chips on Trade targets equal the published source_divergence for the compared charts."""
    doc = json.loads((DIST / "assets" / "reference-freshness.json").read_text(encoding="utf-8")).get("source_divergence") or {}
    used = {h["chart"] for h in S["tabs"]["targets"]["heads"]}
    want = {k: v["status"] for k, v in doc.items() if k in used and v.get("status") in ("warn", "investigate", "reviewed")}
    got = {c["src"]: c["status"] for c in S["tabs"]["targets"]["divergence"]}
    return [] if got == want else [f"divergence chips {got}, published {want}"]


def tt10(S):
    w = S["tabs"]["targets"]["weight"]
    errors = []
    for heading in ("1. Potential mispricing", "2. Potential positional weight inflation"):
        if heading not in w["h2"]:
            errors.append(f"missing numbered heading {heading!r}: {w['h2']}")
    for name in ("potential mispricing", "potential positional weight inflation"):
        if name not in w["sub"]:
            errors.append(f"the subtitle does not name {name!r}")
    return errors


def tt11(S):
    w = S["tabs"]["targets"]["weight"]
    errors = []
    keys = [g["key"] for g in w["groups"]]
    if keys != [k for pos in ("QB", "RB", "WR", "TE") for k in (pos, f"{pos}|starter", f"{pos}|bench")]:
        errors.append(f"weight groups {keys}")
    for g in w["groups"]:
        if g["gap"] == "":
            if g["signal"] or g["n"] >= 3:
                errors.append(f"{g['key']}: no number with {g['n']} players, signal {g['signal']}")
            continue
        gap = float(g["gap"])
        want = "sell" if gap >= 0.10 else "buy" if gap <= -0.10 else "fair"
        if g["signal"] != want or not g["chip"].strip() or g["chip"].strip()[0] not in "▲▼●":
            errors.append(f"{g['key']}: gap {gap:.3f} should read {want}, chip {g['chip']!r}")
    sizes = {g["key"]: g["n"] for g in w["groups"]}
    for key in sizes:
        label = key.replace("|starter", " starters").replace("|bench", " bench")
        if label in w["headline"] and sizes[key] < 8:
            errors.append(f"the headline names {label} with {sizes[key]} players")
    return errors


def rs01(S):
    errors = []
    views = [t["view"] for t in S["tabs"]["targets"]["tabs"]]
    # JEG-1106: the menu lists the three Writing sections as entries of the "Our approach" group (all routes are Writing
    # routes: none is a view of its own), where the old top bar had one Writing tab.
    labels = [t["label"] for t in S["tabs"]["targets"]["tabs"] if t["view"] == "writing"]
    if any(v in views for v in ("manifesto", "how", "research")) or labels != ["Methodology", "Research", "Manifesto"]:
        errors.append(f"Methodology, Research and Manifesto should be the Writing entries of the Our approach group, not views of their own: {views} {labels}")
    sections = S["tabs"]["manifesto"]["sections"]
    want = [("manifesto", "#writing/manifesto"), ("how-values", "#writing/how-values"), ("research", "#writing/research")]
    if [(x["slug"], x["href"]) for x in sections] != want:
        errors.append(f"Writing sections should be Manifesto, How values work, Research in that order: {sections}")
    return errors


def rs02(S):
    return []   # process rule (a post is approved as a Google Doc before it publishes): nothing on the page to read


def rs03(S):
    return []   # no live widget ships with the framework yet; pinned when the first widget post lands


def tt04(S):
    t = S["tabs"]["targets"]
    errors = []
    names = {h["chart"]: h["name"] for h in t["heads"]}
    # Jeremy 2026-10-16 (JEG-677): the row's gap is the market consensus of the indexed charts, with
    # "N of M charts agree" and one dot per chart, instead of naming the single chart with the largest gap.
    for r in t["sell"] + t["buy"]:
        best = r["best"] or {}
        m = re.match(r"(\d+) of (\d+) charts agree", best.get("who") or "")
        if best.get("chart") != "consensus" or not m:
            errors.append(f"{r['name']}: gap is not the market consensus with 'N of M charts agree' ({best})")
            continue
        agree, of = int(m.group(1)), int(m.group(2))
        if of < 2 or agree * 2 <= of:
            errors.append(f"{r['name']}: listed with {agree} of {of} charts agreeing (needs 2+ charts and a majority)")
        if best["who"].count("\u25cf") != of:
            errors.append(f"{r['name']}: {best['who'].count(chr(0x25cf))} dots for {of} charts")
    ex = t.get("expand") or {}
    if ex.get("expanded") != "true" or not all(n in ex.get("detail", "") for n in names.values()):
        errors.append("an expanded row does not show every chart")
    return errors


def tt05_partial(S):
    # TT-05 shipped with JEG-510 (the Doc still says "to build"): every chart header says "rescaled"
    # and carries the ⓘ that explains it.
    t = S["tabs"]["targets"]
    errors = []
    for h in t["heads"]:
        if not re.search(r"rescaled", h["sub"], re.I) or not h["info"]:
            errors.append(f"{h['chart']}: header {h['sub']!r}, ⓘ {h['info']}")
    if not t["captionInfo"] or "scale" not in (t.get("info") or "").lower():
        errors.append("the Compare against ⓘ does not explain the rescaling")
    return errors


PAGES = ("#player-values", "#trade-targets", "#risers-fallers", "#compare-trade")
# JEG-850 (Jeremy, 2026-10-22): the Chart lines tab's groups, in the plain copy of the review (customize-ux-review.md 2.3).
GROUPS_SHIPPED = {"ddf": "DDF Value", "pub": "Published trade charts", "proj": "Projection-based values",
                  "vorp": "Raw value above waivers (advanced)"}


def gl07_partial(S):
    # GL-07 shipped with JEG-498 (the Doc still says "to build"). Known drift: the Doc also lists
    # "Trade charts (adjusted)"; v2 dropped that group (GAP-508-V2-CONTRACT), so it is not required here.
    errors = []
    defaults = set()
    for tab in PAGES:
        c = S["shipped"]["customize"][tab]
        got = {g["id"]: g for g in c["groups"]}
        for gid, title in GROUPS_SHIPPED.items():
            g = got.get(gid)
            if not g or g["title"] != title:
                errors.append(f"{tab}: Customize group {gid!r} is {g and g['title']!r}, want {title!r}")
            elif not re.match(r"Select (all|none)$", g["call"].strip()):
                errors.append(f"{tab}: group {title!r} has no Select all / none ({g['call']!r})")
        # JEG-1073: ddf_value_charts is hidden from pickers (sameAs ddf_value: DDF Value is the Adjusted chart average);
        # the pickable versions are DDF Value and the projections alternate.
        if c["versions"] != ["ddf_value", "ddf_value_projections"]:
            errors.append(f"{tab}: DDF Value versions in Customize {c['versions']}, want 2 (ddf_value_charts hidden)")
        for b in ("Reset to default", "Done", "Cancel"):
            if b not in c["footer"]:
                errors.append(f"{tab}: Customize has no {b!r} button")
        sa = c.get("selectAll")
        if not sa or sa["first"] == sa["second"]:
            errors.append(f"{tab}: the Trade charts Select all / none changes nothing ({sa})")
        if not c["cancelled"]:
            errors.append(f"{tab}: Cancel does not close Customize")
        defaults.add(tuple(c["checked"]))
    if len(defaults) < 2:
        errors.append("every page has the same default series; each page should set its own")
    return errors


def gl19_partial(S):
    info = S["shipped"]["info"]
    return [f"ⓘ does not open on {how}" for how in ("hover", "keyboard", "click") if not info.get(how)]


def gl21_partial(S):
    errors = []
    for tab in PAGES:
        c = S["shipped"]["customize"][tab]
        if c["text"]["asPublished"] or c["text"]["indexed"]:
            errors.append(f"{tab}: 'as published' x{c['text']['asPublished']} / 'indexed' x{c['text']['indexed']} in visible text")
        pub = next((g for g in c["groups"] if g["id"] == "pub"), None)
        meta = (pub or {}).get("meta", "")
        if not pub or pub["title"] != "Published trade charts":
            errors.append(f"{tab}: the chart group is not named 'Published trade charts'")
        elif not re.search(r"adjusted to your league's scale", meta):
            errors.append(f"{tab}: the chart group's meaning line is {meta!r}")
    return errors


def gl22_partial(S):
    # JEG-1119 (Jeremy's scope, 2026-10-26): Position weights moved to the context row's overflow menu, so the two are
    # no longer shown together; Edit league must still be the one primary, labelled control on every page.
    errors = []
    for tab in PAGES:
        lg = S["shipped"]["customize"][tab]["league"]
        if not lg["edit"]:
            errors.append(f"{tab}: no Edit league button")
            continue
        if lg["editLabel"] != "Edit league" or not lg["editPrimary"]:
            errors.append(f"{tab}: Edit league reads {lg['editLabel']!r}, primary={lg['editPrimary']}")
        if not lg["weights"]:
            continue
        if lg["weightsLabel"] != "Position weights" or lg["weightsPrimary"]:
            errors.append(f"{tab}: Position weights reads {lg['weightsLabel']!r}, primary={lg['weightsPrimary']}")
        if not lg["editFirst"]:
            errors.append(f"{tab}: Position weights sits before Edit league")
    return errors


def ct02(S):
    """JEG-1112 (Jeremy, 2026-10-26, option D): the verdict card has no "Should you propose or accept?" / "Will they
    accept?" lines. They repeated the Deal read and pushed the give / receive / verdict block past the fold at 1366x768."""
    h = S["shipped"]["headlines"]
    errors = []
    if h["box"] or h["lines"]:
        errors.append(f"the verdict card still has the propose / accept headline lines (box {h['box']}, {h['lines']} lines)")
    for phrase in ("Should you propose or accept?", "Will they accept?", "Our value:", "Charts agree:"):
        if phrase in h["text"]:
            errors.append(f"the verdict card still says {phrase!r}: {h['text'][:160]!r}")
    return errors


def _badge_errors(where, keys, badges_for, weeks):
    """Each stale chart among `keys` carries "Week N" (its week) in `where`; a current one carries none."""
    errors = []
    for key in keys:
        info = weeks.get(key) or {}
        texts = [b["text"] for b in badges_for(key)]
        if info.get("stale"):
            want = f"Week {info['week']}" if info.get("week") else "Earlier week"
            if want not in texts:
                errors.append(f"{where}: {key} is a week behind but shows {texts or 'no badge'}, want {want!r}")
        elif texts:
            errors.append(f"{where}: {key} is current but shows {texts}")
    return errors


def tt06(S):
    """A chart a week behind shows "Week N" on Trade targets, Player values (legend and table
    headers) and Compare rows. WEEK_BEHIND_FIXTURE puts STALE_CHART a week behind."""
    errors = []
    t, v, c = S["tabs"]["targets"], S["values"]["s0"], S["tabs"]["compare"]
    if not (t["weeks"].get(STALE_CHART) or {}).get("stale"):
        errors.append(f"{STALE_CHART} is not a week behind (WEEK_BEHIND_FIXTURE not applied?)")
    heads = {h["chart"]: h for h in t["heads"]}
    for key, h in heads.items():
        if not re.search(r"Week \d+", h["sub"]):
            errors.append(f"Trade targets {key}: no week in {h['sub']!r}")
    errors += _badge_errors("Trade targets header", heads, lambda k: [{"text": heads[k]["badge"].strip()}] if heads[k]["badge"] else [], t["weeks"])
    charts = [k for k in v["active"] if k in v["weeks"]]
    errors += _badge_errors("Player values legend", charts, lambda k: [b for b in v["legendBadges"] if b["key"] == k], v["weeks"])
    errors += _badge_errors("Player values table header", charts,
                            lambda k: [b for h in v["headBadges"] for b in h["badges"] if b["key"] == k], v["weeks"])
    rows = {r["src"]: r for r in c["rows"]}
    errors += _badge_errors("Compare row", [k for k in rows if k in c["weeks"]], lambda k: rows[k]["badges"], c["weeks"])
    for where, keys in (("Trade targets", heads), ("Player values", charts), ("Compare", rows)):
        if STALE_CHART not in keys:
            errors.append(f"{where}: {STALE_CHART} is not shown, so the week badge was not checked there")
    return errors


def tt07(S):
    t = S["tabs"]["targets"]
    errors = []
    for r in t["sell"] + t["buy"]:
        if r["best"]:
            c = next((c for c in r["charts"] if c["chart"] == r["best"]["chart"]), None)
            if c and (_num(c["text"]) or 0) <= 0:
                errors.append(f"{r['name']}: a target against a chart value of {c['text']}")
    return errors


def tt08(S):
    # JEG-1186 (Jeremy, 2026-10-27: "Suppress"; replaces 2026-10-09 "included and flagged ◐ 1 source"): a player whose
    # DDF Value rests on one source gets no Sell or Buy call, and the notes say how many were left off and why.
    # LOW_CONFIDENCE_FIXTURE marks every fifth priced player one-source, so some would-be targets are always left off.
    t = S["tabs"]["targets"]
    errors = []
    listed = [r["name"] for r in t["all"] if (t["allEngine"].get(r["key"]) or {}).get("low")]
    if listed:
        errors.append(f"one-source players listed in Sell / Buy: {listed[:5]}")
    if not re.search(r"\d+ players? left off Buy and Sell: only 1 source backs (his|their) DDF Value", t["text"]):
        errors.append("no 'left off Buy and Sell: only 1 source' note (LOW_CONFIDENCE_FIXTURE not applied?)")
    return errors[:5]


def rf02(S):
    d = S["tabs"]["risers"]["disagree"]
    errors = []
    if d["h2"] != "Where DDF Value and the projections disagree" or d["heads"] != ["DDF Value moved, projections didn't", "Projections moved, DDF Value didn't"]:
        errors.append(f"disagreement section headings {d['h2']!r} {d['heads']}")
    if d["meta"].startswith("No comparison yet") and d["n"]:
        errors.append(f"no comparison but {d['n']} players listed")
    allowed = {"Buying in without the production: sell", "Panic the projections don't share: buy",
               "Market hasn't caught up: buy", "Market hasn't reacted: sell"}
    bad = [r for r in d["reads"] if r not in allowed]
    if bad:
        errors.append(f"reads outside the four rules: {bad}")
    return errors


def rf01(S):
    r = S["tabs"]["risers"]
    errors = []
    if r["series"] != "ddf_value" or not r["groups"] or r["groups"][0] != "DDF Value" or len(r["groups"]) < 2:
        errors.append(f"Movement picker: {r['series']!r}, groups {r['groups']}")
    if r["noPrior"] and f"{r['noPrior']} player" not in r["note"]:
        errors.append(f"{r['noPrior']} players could not be compared and the page does not say so")
    if not re.search(r"\d+ of \d+ sources", r["meta"]):
        errors.append(f"no count of what was compared: {r['meta']!r}")
    return errors


def ct01(S):
    c = S["tabs"]["compare"]
    errors = []
    if not (c["example"]["giveSearch"] and c["example"]["getSearch"]):
        errors.append("no Give / Receive pickers")
    a = c["added"]
    if not a["give"] or not a["get"] or any(p["example"] for p in a["give"] + a["get"]):
        errors.append(f"adding players from the Give / Receive searches: {a['give']} / {a['get']}")
    if not (a["swap"] and a["clear"] and a["share"]):
        errors.append(f"with a trade: Swap {a['swap']}, Clear {a['clear']}, Share {a['share']}")
    # JEG-537: the bench share is computed from the settings, so the link no longer carries bench=
    # (only an override travels, as bso).
    if not all(f"{p}=" in a["hash"] for p in ("give", "get", "scoring", "roster")) or "bench=" in a["hash"]:
        errors.append(f"the trade link does not carry the league settings: {a['hash']!r}")
    s = c["swapped"]
    if [p["key"] for p in s["get"]] != [p["key"] for p in a["give"]]:
        errors.append("Swap did not move Give to Receive")
    if any(not p["example"] for p in c["cleared"]["give"] + c["cleared"]["get"]):
        errors.append("Clear left players on the trade")
    return errors


def ct03(S):
    c = S["tabs"]["compare"]
    errors = []
    if not c["example"]["title"].startswith(("▲ DDF Value", "▼ DDF Value", "= DDF Value", "DDF Value")) and "DDF Value" not in c["example"]["title"]:
        errors.append(f"verdict is not by DDF Value: {c['example']['title']!r}")
    ddf = next((r for r in c["rows"] if r["src"] == "ddf_value"), None)
    if ddf:
        sign = (ddf["receive"] - ddf["give"]) > 0
        for r in c["rows"]:
            if r["src"] != "ddf_value" and ((r["receive"] - r["give"]) > 0) != sign and r["name"].split()[0] not in c["example"]["verdict"]:
                errors.append(f"{r['name']} sees the trade the other way and the verdict does not name it")
    o = c["otherShown"]
    name = re.sub(r"^[^\w]+", "", o["label"]).split(" chart")[0].split(" (")[0].strip()
    if name not in o["title"]:
        errors.append(f"with {name} picked the verdict says {o['title']!r}")
    return errors


def ct04(S):
    c = S["tabs"]["compare"]
    errors = []
    if len(c["rows"]) < 2:
        errors.append(f"{len(c['rows'])} waterfall rows")
    if len({(r["lo"], r["hi"]) for r in c["rows"]}) != 1:
        errors.append("waterfalls are not on one shared scale")
    for r in c["rows"]:
        for st in r["steps"]:
            v = _num(st["value"])
            if v is None or (st["side"] == "give" and v > 0) or (st["side"] == "receive" and v < 0):
                errors.append(f"{r['src']}: a {st['side']} step of {st['value']}")
                break
    return errors


def ct08(S):
    """The deal read is always on a ready trade: nine cells, three nets, one outlined cell unless a net is missing."""
    d = S["tabs"]["compare"]["added"]["deal"]
    errors = []
    if not d["shown"] or d["cells"] != 9 or d["nets"] != 3:
        errors.append(f"deal read: shown {d['shown']}, {d['cells']} cells, {d['nets']} nets")
    if d["current"] > 1 or (d["current"] == 0) != bool(not d["read"]):
        errors.append(f"deal read: {d['current']} outlined cells with read {d['read']!r} ({d['text']!r})")
    if d["split"]:
        errors.append("the old 'The sources split.' copy is still on the page")
    return errors


def ct05(S):
    e = S["tabs"]["compare"]["example"]
    errors = []
    if not e["example"] or "Example" not in e["eyebrow"] or not e["give"] or not e["get"]:
        errors.append(f"no example trade before a player is added: {e['eyebrow']!r}")
    if "give=" in e["hash"] or "get=" in e["hash"] or e["share"]:
        errors.append(f"the example goes into the link: {e['hash']!r}, share {e['share']}")
    if S["tabs"]["compare"]["added"]["example"]:
        errors.append("the example stays after a player is added")
    return errors


def ct06(S):
    r = next(x for x in S["phone"]["tabs"] if x["hash"] == "#compare-trade")
    b = r.get("bar") or {}
    if not b.get("cardOff"):
        return ["could not scroll the verdict card off screen at 390 px"]
    if not b.get("shown") or b["rect"]["y"] < 0 or b["rect"]["y"] + b["rect"]["h"] > b["vh"] + 1:
        return [f"verdict bar not on screen at 390 px: {b}"]
    return []


def ct07(S):
    v = S["values"]["s0"]
    errors = []
    if not _monotone([r["tier"] for r in v["table"]]):
        errors.append("All positions: tiers are not one cut across positions")
    tiers = {r["key"]: r["tier"] for r in v["table"]}
    for p in S["tabs"]["compare"]["example"]["give"] + S["tabs"]["compare"]["example"]["get"]:
        if p["key"] in tiers and p["tier"] != tiers[p["key"]]:
            errors.append(f"player {p['key']}: Compare tier {p['tier']!r}, Player values {tiers[p['key']]!r}")
    return errors


def hv01(S):
    h = S["tabs"]["how"]
    errors = []
    methods = [c["method"] for c in h["cards"]]
    if methods != ["dda", "indexed", "vorp"]:
        errors.append(f"views explained: {methods}")
    for c in h["cards"]:
        if not c["items"]:
            errors.append(f"{c['method']}: lists no series")
        for item in c["items"]:
            if RAW_KEY.search(item):
                errors.append(f"{c['method']}: lists an engine key {item!r}")
    if re.search(r"\d+\.\d|\d+%", h["outside"]):
        errors.append("How values shows a number outside the league card")
    return errors


# Every contract ID: a check function, or PENDING(ticket) for an agreed line not live yet.
CHECKS = {
    "GL-01": gl01, "GL-02": gl02, "GL-03": gl03, "GL-04": gl04, "GL-05": gl05, "GL-06": gl06,
    "GL-07": PENDING("JEG-498", partial=gl07_partial), "GL-08": gl08, "GL-09": PENDING("JEG-497", partial=gl09), "GL-10": gl10,
    "GL-11": gl11, "GL-12": gl12, "GL-13": gl13, "GL-14": gl14, "GL-15": gl15, "GL-16": gl16,
    "GL-17": gl17, "GL-18": gl18,
    "GL-19": PENDING("JEG-501", partial=gl19_partial), "GL-20": PENDING("JEG-502", partial=gl20), "GL-21": PENDING("JEG-510", partial=gl21_partial),
    "GL-22": PENDING("JEG-498", partial=gl22_partial), "GL-23": gl23, "GL-24": gl24, "GL-25": gl25, "GL-26": gl26, "GL-27": gl27, "GL-28": gl28,
    "MF-01": mf01,
    "PV-01": pv01, "PV-02": pv02, "PV-03": pv03, "PV-04": pv04, "PV-05": pv05,
    "PV-06": pv06, "PV-07": pv07, "PV-08": pv08, "PV-09": pv09,
    "PV-10": pv10, "PV-11": pv11, "PV-12": pv12, "PV-13": pv13, "PV-14": pv14, "PV-15": pv15,
    "PV-16": pv16, "PV-17": pv17, "PV-18": pv18, "PV-19": pv19, "PV-20": pv20,
    "TT-01": tt01, "TT-02": tt02, "TT-03": tt03, "TT-04": tt04,
    "TT-10": tt10, "TT-11": tt11, "TT-12": tt12, "RS-01": rs01, "RS-02": rs02, "RS-03": rs03,
    # "rescaled" lands with JEG-510; the ⓘ and the scale word are checked meanwhile.
    "TT-05": PENDING("JEG-510", partial=tt05_partial),
    "TT-06": tt06, "TT-07": tt07, "TT-08": tt08, "TT-09": PENDING("JEG-504"),
    "RF-01": rf01, "RF-02": rf02,
    "CT-01": ct01, "CT-02": ct02, "CT-03": ct03, "CT-04": ct04, "CT-05": ct05,
    "CT-06": ct06, "CT-07": ct07, "CT-08": ct08,
    "HV-01": hv01, "HV-02": hv02,
}

# The scenarios each check reads (a broken-build run loads only what its checks need).
NEEDS = {cid: ("values", "tabs") for cid in live_checks(CHECKS)}
NEEDS.update({"GL-13": ("phone",), "CT-06": ("phone",), "GL-14": ("failure",),
              "GL-05": ("values",), "GL-10": ("values",), "GL-11": ("values",),
              "PV-02": ("values",), "PV-09": ("values",), "MF-01": ("tabs",), "CT-01": ("tabs",), "GL-20": ("tabs",),
              "GL-04": ("values", "tabs")})
NEEDS.update({cid: ("shipped",) for cid in ("GL-07", "GL-19", "GL-21", "GL-22", "CT-02")})


def run_contract(ids=None, overrides=None):
    """Load the scenarios the checks need and run them: ({id: errors}, page errors)."""
    run = live_checks(CHECKS)
    ids = list(ids or run)
    needed = sorted({name for cid in ids for name in NEEDS[cid]})
    from playwright.sync_api import sync_playwright
    with _served() as (base, dist), sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS,
                                             executable_path=_render_env.chromium_executable(playwright))
        try:
            session = Session(browser, base, dist, overrides)
            snaps = {name: SCENARIOS[name](session) for name in needed}
        finally:
            browser.close()
    results = {}
    for cid in ids:
        try:
            results[cid] = run[cid](snaps)
        except Exception as error:   # a check that cannot read its feature fails, it never passes
            results[cid] = [f"check could not run: {type(error).__name__}: {error}"]
    page_errors = [f"{name}: {e}" for name, snap in snaps.items() for e in snap.get("errors", [])
                   if name != "failure"]
    return results, page_errors


def _playwright_or_skip():
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")


class ContractMirrorTest(unittest.TestCase):
    def test_mirror_every_id_has_a_check(self):
        errors = mirror_errors(MIRROR.read_text(encoding="utf-8"), CHECKS)
        self.assertEqual(errors, [], "\n".join(errors))

    def test_mirror_check_catches_gaps(self):
        text = MIRROR.read_text(encoding="utf-8")
        added = text + "\n- **PV-99** A new line nobody wrote a check for.\n"
        self.assertTrue(any(e.startswith("PV-99") for e in mirror_errors(added, CHECKS)))
        # A pending line goes live in the Doc: its PENDING must become a real check.
        shipped = text.replace("*(to build: JEG-510)*", "")
        self.assertTrue(any(e.startswith("GL-21") for e in mirror_errors(shipped, CHECKS)))
        # A live line becomes "to build": its check must be marked pending.
        reopened = text.replace("**TT-07** A chart value", "**TT-07** *(to build: JEG-999)* A chart value")
        self.assertTrue(any(e.startswith("TT-07") for e in mirror_errors(reopened, CHECKS)))
        # A pending line names a different ticket than the Doc.
        wrong = {**CHECKS, "GL-07": PENDING("JEG-1")}
        self.assertTrue(any(e.startswith("GL-07") for e in mirror_errors(text, wrong)))
        # A live line may not stay pending.
        live_tt05 = text.replace("(GL-21) *(to build: JEG-510)*", "(GL-21)")
        self.assertTrue(any(e.startswith("TT-05") for e in mirror_errors(live_tt05, CHECKS)))
        # "to build" on a later paragraph of the line's block still counts.
        later = "  - **GL-99** Edit league includes:\n\n  - a bullet;\n\nShare links carry every setting *(to build: JEG-537)*.\n"
        self.assertEqual(contract_ids(later).get("GL-99"), "JEG-537")
        # A checked ID leaves the Doc.
        dropped = "\n".join(l for l in text.splitlines() if "**TT-07**" not in l)
        self.assertTrue(any(e.startswith("TT-07") for e in mirror_errors(dropped, CHECKS)))

    def test_manifesto_mirror_is_sync_output(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import sync_feature_contract as sync
        text = MANIFESTO_MIRROR.read_text(encoding="utf-8")
        self.assertIn(sync.DOCS["manifesto"]["url"], text.split("-->", 1)[0])
        body = sync.strip_header(text)
        self.assertEqual(sync.tidy_export(body), body)
        self.assertGreater(len(manifesto_words(text)), 1000)

    def test_mirror_is_sync_output(self):
        # The mirror is what scripts/sync_feature_contract.py writes: its header, and a body
        # the formatter leaves unchanged.
        sys.path.insert(0, str(ROOT / "scripts"))
        import sync_feature_contract as sync
        text = MIRROR.read_text(encoding="utf-8")
        self.assertIn(sync.DOC_URL, text.split("-->", 1)[0])
        self.assertIn("never edit this file to change the contract", text.split("-->", 1)[0])
        body = sync.strip_header(text)
        self.assertEqual(sync.tidy_export(body), body)


class ContractRenderTest(unittest.TestCase):
    def test_every_live_contract_line(self):
        _playwright_or_skip()
        results, page_errors = run_contract()
        self.assertEqual(page_errors, [], "\n".join(page_errors))
        failed = {cid: errs for cid, errs in results.items() if errs}
        report = "\n".join(f"{cid}: {e}" for cid, errs in failed.items() for e in errs[:4])
        self.assertEqual(failed, {}, "contract lines broken:\n" + report)

    def test_guard_fails_on_broken_builds(self):
        """Each broken build must fail the check for the line it breaks, with a real finding
        (a check that crashed is not evidence). Builds are grouped so one run serves several
        faults; a group only loads the scenarios its checks read."""
        _playwright_or_skip()
        shell = SHELL.read_text(encoding="utf-8")
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")

        def cut(text, old, new=""):
            self.assertEqual(text.count(old), 1, f"stale mutation anchor: {old[:80]!r}")
            return text.replace(old, new)

        def caught(results, cid, fault):
            real = [e for e in results[cid] if not e.startswith("check could not run")]
            self.assertTrue(real, f"{cid} did not catch: {fault} (got {results[cid]})")

        # Group 1 (shell): the nav reordered, Swap never shown, "Vegas" in the header.
        manifesto_tab = '      <a class="v2-subtab" href="#writing/manifesto" data-writing="manifesto">Manifesto</a>\n'
        how_tab = '      <a class="v2-subtab" href="#writing/how-values" data-writing="how-values">How values work</a>\n'
        broken_shell = cut(cut(shell, manifesto_tab), how_tab, how_tab + manifesto_tab)
        # Swap never shows (removing the node would crash startup, which is a different failure).
        broken_shell = cut(broken_shell, 'id="v2CSwap" hidden>', 'id="v2CSwap" hidden style="display:none !important">')
        broken_shell = cut(broken_shell, 'href="v2/#player-values">Data Driven Football</a>',
                           'href="v2/#player-values">Data Driven Football · Vegas lines</a>')
        results, _ = run_contract(["MF-01", "RS-01", "CT-01", "GL-01"], {"shell": broken_shell})
        caught(results, "MF-01", "Manifesto moved after How values work in Writing")
        caught(results, "RS-01", "Writing sections out of order")
        caught(results, "CT-01", "Swap removed")
        caught(results, "GL-01", '"Vegas" in the header')

        # JEG-947: a name cell with no visible name, with and without data-full (the helper PV-03 reads through must not hide it).
        for fault, old, new_text in (
            ("name cells with no text and no data-full", "    span.dataset.full = row.name;\n    span.dataset.pos = row.pos || \"\";\n    span.title = row.name;\n    span.textContent = phoneName(row.name, row.pos);\n",
             "    span.dataset.pos = row.pos || \"\";\n"),
            ("name cells with data-full but an empty visible name", "    span.textContent = phoneName(row.name, row.pos);\n", "    span.textContent = \"\";\n"),
        ):
            results, _ = run_contract(["PV-03"], {"v2.js": cut(js, old, new_text)})
            caught(results, "PV-03", fault)

        # Group 2 (v2.js + v2.css): Reset keeps Rank by, prior-week status without a symbol,
        # the DDF line at the others' weight, the ◐ tag removed.
        broken_js = cut(js, '    if (view && view.infoByKey[DDF_KEY] && C.getRankSource() !== DDF_KEY) C.setLockOrder(DDF_KEY);\n')
        broken_js = cut(broken_js, 'prior: "⚠ ", ')
        broken_js = cut(broken_js, '    renderUnpriced("v2Unpriced", state.search);\n')
        broken_js = cut(broken_js, '`⚠ ${behind} source', '`${behind} source')
        broken_js = cut(broken_js, "const flagged = key === DDF_KEY ? Boolean(row && row.ddfLowConfidence) : Boolean(entry && entry.lowConfidence);",
                        "const flagged = false;")
        broken_js = cut(broken_js, 'if (item?.stale) sub.append(weekBadge(key), document.createTextNode(" older week"));',
                        'if (false) sub.append(weekBadge(key), document.createTextNode(" older week"));')
        broken_css = cut(css, ".v2-chart .series.is-ddf { stroke-width: 3.5; }", ".v2-chart .series.is-ddf { stroke-width: 2; }")
        # JEG-1186: TT-08 now pins the suppression, so its mutation lets a one-source player back into Sell / Buy.
        targets_js = (SHELL.parent / "targets.js").read_text(encoding="utf-8")
        broken_targets = cut(targets_js, "return n !== null && n < MIN_DDF_SOURCES;", "return false;")
        results, _ = run_contract(["PV-02", "PV-09", "GL-04", "GL-05", "GL-03", "TT-08", "GL-20", "TT-06"],
                                  {"v2.js": broken_js, "v2.css": broken_css, "targets.js": broken_targets})
        caught(results, "PV-02", "the DDF line at the others' weight")
        caught(results, "PV-09", "Reset leaving Rank by")
        caught(results, "GL-04", "a prior-week status shown without a symbol")
        caught(results, "GL-05", "a prior-week chip shown without a warning")
        caught(results, "GL-03", "the ◐ 1 source tag removed (Player values)")
        caught(results, "TT-08", "a one-source player back in Sell / Buy (Trade targets)")
        caught(results, "GL-20", "Player values search not listing players with no value")
        caught(results, "TT-06", "the week badge dropped from Compare rows")

        # PV-12 (list layout): "Show all sources" on by default; the kind label dropped from every row.
        for fault, old, new_text in (
            ("'Show all sources' on by default", "let drawerAllSources = false;", "let drawerAllSources = true;"),
            ("the kind column left empty", "      kind.textContent = label;\n", "      kind.textContent = \"\";\n"),
        ):
            results, _ = run_contract(["PV-12"], {"v2.js": cut(js, old, new_text)})
            caught(results, "PV-12", fault)

        # Group 3: Rank by defaults to a chart (the first active source), the chip claims every source is current
        # (JEG-721: removing the held-source detection makes the chip lie), the 390 px layout scrolls sideways,
        # a Manifesto section dropped.
        broken_js = cut(js, "const rank = saved && saved.rank ? ddfPickKey(saved.rank) : (hasDdf ? DDF_KEY : null);",
                        'const rank = saved && saved.rank ? ddfPickKey(saved.rank) : (hasDdf ? C.getActiveSources()[0] : null);')
        # JEG-806: the ternary is now multi-line; the anchor is just the assignment start.
        broken_js = cut(broken_js, '$("v2FreshnessLabel").textContent = stuck\n', '$("v2FreshnessLabel").textContent = false\n')
        broken_js = cut(broken_js, '`${weekText}${freshNotes.join(" · ") || "all sources current"}`;\n',
                        '`${weekText}all sources current`;\n')
        broken_css = css + "\n@media (max-width: 500px) { .v2-wrap { min-width: 480px; } }\n"
        section = re.search(r'    <section class="v2-mf-sec" aria-labelledby="v2M1">.*?</section>\n', shell, re.S)
        self.assertIsNotNone(section, "stale mutation anchor: Manifesto section 1")
        broken_shell = cut(shell, section.group(0))
        results, _ = run_contract(["MF-01"], {"shell": cut(shell, "<p>That is part of the game, but it is not the game.</p>",
                                                            "<p>That is part of the game, but it is not the sport.</p>")})
        caught(results, "MF-01", "one Manifesto word changed")
        results, _ = run_contract(["GL-08", "GL-05", "GL-13", "MF-01"],
                                  {"v2.js": broken_js, "v2.css": broken_css, "shell": broken_shell})
        caught(results, "GL-08", "Rank by defaulting to a chart, not DDF Value")
        caught(results, "GL-05", "a chip claiming every source is current")
        caught(results, "GL-13", "the 390 px layout scrolling sideways")
        caught(results, "MF-01", "a Manifesto section dropped")
        # JEG-953: with the hamburger button hidden, a phone has no way to reach the tabs.
        results, _ = run_contract(["GL-13"], {"v2.css": css + "\n.v2-nav .v2-nav-toggle { display: none !important; }\n"})
        caught(results, "GL-13", "the phone hamburger button hidden (tabs unreachable)")


        # Group 4 (shipped lines the Doc still marks "to build"): ⓘ hover dropped, the chart group back to
        # "as published", Edit league demoted, Customize without Reset, the removed Compare headline lines back.
        broken_js = cut(js, "openTimer = setTimeout(() => { if (!popOpenForButton()) showInfo(true); }, 200);", "void 0;")
        broken_js = cut(broken_js, '{id: "pub", title: "Published trade charts"',
                        '{id: "pub", title: "Trade charts (as published)"')
        broken_js = cut(broken_js, 'reset.textContent = "Reset to default";', 'reset.textContent = "Back";')
        broken_shell = cut(shell, 'class="v2-btn v2-btn-primary v2-btn-sm" id="v2EditLeague"', 'class="v2-btn v2-btn-adjust v2-btn-sm" id="v2EditLeague"')
        # JEG-1112: the propose / accept lines put back into the verdict card (the pre-JEG-1112 markup).
        broken_shell = cut(broken_shell, '        <div aria-live="polite">\n          <h2 id="v2CVerdictTitle">',
                           '        <div class="v2-cheads" id="v2CHeads"><p class="v2-chead" data-line="propose">Should you propose or accept? Yes</p></div>\n'
                           '        <div aria-live="polite">\n          <h2 id="v2CVerdictTitle">')
        results, _ = run_contract(["GL-19", "GL-21", "GL-22", "GL-07", "CT-02"], {"v2.js": broken_js, "shell": broken_shell})
        caught(results, "GL-19", "ⓘ no longer opening on hover")
        caught(results, "GL-21", "the chart group named 'as published'")
        caught(results, "GL-22", "Edit league no longer the primary control")
        caught(results, "GL-07", "Customize without Reset to default")
        caught(results, "CT-02", "the propose / accept headline lines back in the verdict card")


if __name__ == "__main__":
    unittest.main()
