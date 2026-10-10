"""Feature contract test (JEG-506): one quick check per line of the feature contract.

The contract is the Google Doc "Data Driven Football: feature contract" (Jeremy,
2026-10-09: the Doc is the source of truth). docs/feature-contract.md mirrors it.
Regenerate the mirror with scripts/sync_feature_contract.py; never edit it by hand.
Every **XX-NN** ID in the mirror must be in CHECKS below: a check function for a live
line, or PENDING("JEG-xxx") for a "to build: JEG-xxx" line (with an optional partial
check of what already exists). A Doc line without a check, a pending line the Doc calls
live, or a check for an ID the Doc dropped fails test_mirror_every_id_has_a_check. The
one exception is WORDING_HOLDS (TT-05 until JEG-510 renames "indexed" to "rescaled").

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
report a real finding for each fault: nav reordered and a Manifesto section dropped
(MF-01), Swap hidden (CT-01), "Vegas" in the header (GL-01), the DDF line at the
others' weight (PV-02), Reset leaving Rank by (PV-09), a prior-week status without a
symbol (GL-04), a chip without a warning and a chip claiming all current (GL-05), the
◐ tag removed (GL-03, TT-08), Rank by defaulting to a chart (GL-08) and a 390 px layout
that scrolls sideways (GL-13). Separately, the pre-fix v2.js from
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


# Live lines held as pending for a wording change that is already ticketed. The Doc line
# has no "to build", so without this list the mirror test would demand a real check.
# TT-05 says "rescaled"; the live UI says "indexed" until JEG-510 (GL-21) renames it.
WORDING_HOLDS = {"TT-05": "JEG-510"}

# Parts of live lines that are agreed but not built, so their check skips them. The rest of
# the line is checked. Switch the part on when its ticket ships.
# GL-11: "Edit league is the primary control" ships with JEG-498 (no primary styling yet;
# coordinator, 2026-10-09). Draft-until-Apply is checked now.
SUBPART_HOLDS = {"GL-11": ("Edit league is the primary control", "JEG-498")}

ID_LINE = re.compile(r"\*\*([A-Z]{2}-\d{2})\*\*(.*)")
TO_BUILD = re.compile(r"to build:([^)]*)")


def contract_ids(text: str) -> dict[str, str | None]:
    """{ID: None if live, else the "to build: …" text} for every **XX-NN** line."""
    ids = {}
    for line in text.splitlines():
        m = ID_LINE.search(line)
        if m:
            build = TO_BUILD.search(m.group(2))
            ids[m.group(1)] = build.group(1).strip() if build else None
    return ids


def mirror_errors(text: str, checks, holds=WORDING_HOLDS) -> list[str]:
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
            if holds.get(cid) != check.ticket:
                errors.append(f"{cid}: the contract says it is live but its check is {check!r}; switch it on")
        elif not callable(check):
            errors.append(f"{cid}: CHECKS value {check!r} is not a check function")
    for cid in sorted(set(checks) - set(ids)):
        errors.append(f"{cid}: has a check but is not in the contract")
    for cid in sorted(set(holds) - set(ids)):
        errors.append(f"{cid}: wording hold for a line that is not in the contract")
    for cid, (part, _ticket) in SUBPART_HOLDS.items():
        line = next((l for l in text.splitlines() if f"**{cid}**" in l), "")
        if part not in line:
            errors.append(f"{cid}: held part {part!r} is no longer in the contract line; update SUBPART_HOLDS")
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
LOW_CONFIDENCE_FIXTURE = """(() => {
  const mark = row => {
    if (row && Number(row.player_key) % 5 === 0 && Number.isFinite(row.values && row.values.ddf_value)) {
      row.ddfLowConfidence = true; row.ddfCount = 1;
      row.ddfConfidenceNote = 'Only one source prices this player (contract test fixture)';
    }
    return row;
  };
  let controls;
  Object.defineProperty(window, 'TradeValueCurveControls', {configurable: true, enumerable: true,
    get: () => controls,
    set: value => {
      if (value && !value.__contractFixture) {
        for (const name of ['getRows', 'getAllRows']) {
          const original = value[name];
          if (typeof original === 'function') value[name] = (...args) => original.apply(value, args).map(mark);
        }
        value.__contractFixture = true;
      }
      controls = value;
    }});
})();"""

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
        page.add_init_script(LOW_CONFIDENCE_FIXTURE)
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.freshness = {"kind": freshness}
        page.route("**/assets/reference-freshness.json*",
                   lambda route, *_: route.fulfill(status=200, content_type="application/json",
                                                   body=_freshness(page.freshness["kind"])))
        ov = self.overrides
        if "shell" in ov:
            built = (self.dist / "v2" / "index.html").read_text(encoding="utf-8")
            original = SHELL.read_text(encoding="utf-8")
            assert original in built, "the built page no longer embeds shell.html verbatim"
            html = built.replace(original, ov["shell"], 1)
            page.route(lambda u: urlparse(u).path in ("/v2/", "/v2/index.html"),
                       functools.partial(_fulfill, html, "text/html"))
        if "v2.js" in ov:
            page.route("**/v2/v2.js*", functools.partial(_fulfill, ov["v2.js"], "text/javascript"))
        if "v2.css" in ov:
            page.route("**/v2/v2.css*", functools.partial(_fulfill, ov["v2.css"], "text/css"))
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
  const own = n => [...n.childNodes].filter(c => c.nodeType === 3).map(c => c.textContent).join('').trim();
  const rect = n => { if (!n) return null; const r = n.getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; };
  const shown = n => Boolean(n) && !n.hidden && n.getClientRects().length > 0;
  const closePop = async () => { const b = document.querySelector('#v2Popover:not([hidden]) .v2-panel-close')
      || [...document.querySelectorAll('#v2Popover:not([hidden]) button')].find(b => /^(Done|Cancel)$/.test(b.textContent.trim()));
    if (b) b.click(); document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true})); await sleep(250); };
  const visibleText = () => $('v2App').innerText;
  const attrText = root => [...root.querySelectorAll('[title],[aria-label]')]
    .map(n => (n.getAttribute('title') || '') + ' ' + (n.getAttribute('aria-label') || '')).join('\n');
  const tabs = () => [...document.querySelectorAll('.v2-tab')].map(t => ({view: t.dataset.view,
    label: t.querySelector('.v2-tab-full')?.textContent || '', current: t.getAttribute('aria-current') === 'page'}));
  const pagesShown = () => Object.fromEntries(['v2Main', 'v2Targets', 'v2Risers', 'v2Compare', 'v2How', 'v2Manifesto']
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
    showingRects: [rect(document.querySelector('.v2-showing')), rect($('v2ShowingLegend')), rect($('v2EditSources'))],
    customize: $('v2EditSources').textContent.trim(),
    rankBy: $('v2RankBy').value, rankOptions: [...$('v2RankBy').options].map(o => o.value),
    shown: V.shown(), active: C.getActiveSources(),
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
  // League edits are a draft until Apply
  const leagueBefore = $('v2LeagueName').textContent;
  const engineTeams = C.getState().teams;
  $('v2EditLeague').click(); await sleep(300);
  const teams = [...document.querySelectorAll('#v2Popover [aria-label="Teams"] button')].find(b => b.getAttribute('aria-pressed') !== 'true');
  if (teams) { teams.click(); await sleep(200); }
  const draftTeams = C.getState().teams;
  const buttons = [...document.querySelectorAll('#v2Popover button')].map(b => b.textContent.trim());
  const cancel = [...document.querySelectorAll('#v2Popover button')].find(b => b.textContent.trim() === 'Cancel');
  if (cancel) cancel.click(); else await closePop();
  await sleep(500);
  out.league = {before: leagueBefore, after: $('v2LeagueName').textContent, changed: Boolean(teams),
    engineTeams, draftTeams, afterTeams: C.getState().teams,
    hasApply: buttons.includes('Apply'), hasCancel: Boolean(cancel)};
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
    h1: $('v2TargetsTitle').textContent.trim(), ours: $('v2TOurs').value,
    sell: rows('#v2TTable'), buy: rows('#v2TBuyTable'),
    sellMore: shown($('v2TSellMore')), buyMore: shown($('v2TBuyMore')),
    rects: [rect($('v2TSell')), rect($('v2TBuy'))],
    heads: [...document.querySelectorAll('#v2TTable thead th[data-chart]')].map(th => ({chart: th.dataset.chart,
      name: own(th.querySelector('.th-line')), sub: th.querySelector('.th-sub')?.textContent || '',
      badge: th.querySelector('.v2-prior-badge')?.textContent || null,
      info: Boolean(th.querySelector('button[data-info]'))})),
    weeks: (() => { const fr = window.TradeValueProductData?.getSourceFreshness?.() || null;
      return Object.fromEntries(C.getSourceInfo().map(i => { const s = fr?.series?.[i.key];
        return [i.key, {stale: s && typeof s.is_older_week === 'boolean' ? s.is_older_week : Boolean(i.stale),
          week: i.week || (s && s.vintage_week) || null}]; })); })(),
    refWeek: C.getReferenceWeek ? C.getReferenceWeek() : null,
    caption: $('v2TChartCaption').textContent, captionInfo: Boolean(document.querySelector('.v2-tcompare button[data-info]')),
    lowEngine: C.getRows().filter(r => r.ddfLowConfidence).map(r => String(r.player_key)),
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
  // Every row, for TT-08 (one-source players are included and flagged anywhere in the lists).
  for (const id of ['v2TSellMore', 'v2TBuyMore']) if (shown($(id))) { $(id).click(); await sleep(300); }
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
    noPrior: (V.risers() || {}).noPrior || 0, rise: document.querySelectorAll('#v2RRise li').length};
}"""

COMPARE_JS = "async () => {" + COMMON + r"""
  const side = id => [...document.querySelectorAll('#' + id + ' li[data-player-key]')].map(li => ({key: li.dataset.playerKey,
    example: li.classList.contains('is-example'), tier: (li.querySelector('.v2-meta')?.textContent || '').split('·').pop().trim()}));
  const snap = () => ({example: shown($('v2CExample')), eyebrow: $('v2CVerdictEyebrow').textContent,
    title: $('v2CVerdictTitle').textContent, verdict: $('v2CVerdictText').textContent, hash: location.hash,
    share: shown($('v2CShare')), swap: shown($('v2CSwap')), clear: shown($('v2CClear')),
    give: side('v2GivePlayers'), get: side('v2GetPlayers'),
    giveSearch: shown($('v2GiveSearch')), getSearch: shown($('v2GetSearch'))});
  const out = {tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText($('v2Compare')), shownKey: $('v2CShown').value};
  out.example = snap();
  out.rows = [...document.querySelectorAll('#v2CTable tbody tr[data-source]')].map(tr => { const wf = tr.querySelector('.v2-wf');
    return {src: tr.dataset.source, name: own(tr.querySelector('td.player')), give: parseFloat(tr.querySelector('[data-col="give"]')?.textContent),
      receive: parseFloat(tr.querySelector('[data-col="receive"]')?.textContent), lo: wf ? wf.dataset.lo : null, hi: wf ? wf.dataset.hi : null,
      steps: wf ? [...wf.querySelectorAll('.v2-wf-step')].map(s => ({side: s.dataset.side, value: s.dataset.value})) : []}; });
  out.engine = engineFor(out.example.give.concat(out.example.get).map(p => p.key));
  out.shownOptions = [...$('v2CShown').options].map(o => [o.value, o.textContent]);
  // DDF Value hidden: the verdict follows the picked series and names it.
  const before = V.shown();
  V.setShown(before.filter(k => k !== 'ddf_value')); await sleep(500);
  const other = [...$('v2CShown').options].map(o => o.value).find(v => v !== 'ddf_value');
  fire($('v2CShown'), other); await sleep(400);
  out.otherShown = {key: other, label: [...$('v2CShown').options].find(o => o.value === other)?.textContent || '', title: $('v2CVerdictTitle').textContent};
  V.setShown(before); await sleep(500);
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
  const share = C.getBenchShare();
  return {tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText(how),
    cards: [...how.querySelectorAll('[data-view-method]')].map(li => ({method: li.dataset.viewMethod,
      title: li.querySelector('h2')?.textContent || '', items: [...li.querySelectorAll('.v2-how-sources li')].map(x => x.textContent.trim())})),
    outside: clone.textContent, bench: $('v2HowBench').textContent, benchNote: $('v2HowBenchNote').hidden ? '' : $('v2HowBenchNote').textContent,
    share, used: C.getBenchShareUsed ? C.getBenchShareUsed(share) : null,
    activeKeys: C.getActiveSources()};
}"""

MANIFESTO_JS = "() => {" + COMMON + r"""
  const mf = $('v2Manifesto');
  return {tabs: tabs(), pages: pagesShown(), text: visibleText(), attrs: attrText(mf),
    h1: mf.querySelector('h1')?.textContent.trim() || '', h2: [...mf.querySelectorAll('article h2')].map(h => h.textContent.trim()),
    links: mf.querySelectorAll('a').length};
}"""

PHONE_JS = "async (hash) => {" + COMMON + r"""
  location.hash = hash; await sleep(700);
  const page = Object.entries(pagesShown()).find(([, on]) => on);
  const out = {hash, page: page ? page[0] : null, height: page ? $(page[0]).getBoundingClientRect().height : 0,
    overflow: document.documentElement.scrollWidth - innerWidth, nav: shown(document.querySelector('.v2-tabs'))};
  if (hash === '#compare-trade') {
    await addTrade();
    scrollTo(0, document.documentElement.scrollHeight); await sleep(500);
    const card = $('v2CVerdict').getBoundingClientRect();
    out.bar = {shown: shown($('v2CVerdictBar')), rect: rect($('v2CVerdictBar')), vh: innerHeight, cardOff: card.bottom < 0 || card.top > innerHeight};
    scrollTo(0, 0);
  }
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


def scenario_tabs(s: Session) -> dict:
    page = s.open("")
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
        page.evaluate("() => { location.hash = '#how-values'; }")
        page.wait_for_timeout(600)
        out["how"] = page.evaluate(HOW_JS)
        page.evaluate("() => { location.hash = '#manifesto'; }")
        page.wait_for_timeout(400)
        out["manifesto"] = page.evaluate(MANIFESTO_JS)
        out["errors"] = page.errors
        return out
    finally:
        page.close()


def scenario_phone(s: Session) -> dict:
    page = s.open("#trade-targets", width=390, height=844)
    try:
        out = {"tabs": [page.evaluate(PHONE_JS, h) for h in
                        ("#manifesto", "#player-values", "#trade-targets", "#risers-fallers", "#compare-trade", "#how-values")]}
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


SCENARIOS = {"values": scenario_values, "tabs": scenario_tabs, "phone": scenario_phone, "failure": scenario_failure}


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
        for m in re.finditer(r"VORP", text):
            if text[m.start():m.start() + len("VORP vs waivers")] != "VORP vs waivers":
                errors.append(f"{tab}: 'VORP' not as 'VORP vs waivers': {text[max(0, m.start() - 20):m.start() + 30]!r}")
                break
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
    want = {"usatoday": "prior", "cbs": "unknown", "fantasycalc": "stuck"}
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
    if "all sources current" not in v["reload"]["chip"]:
        errors.append(f"chip with every source confirmed says {v['reload']['chip']!r}")
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
    # "Edit league is the primary control" is SUBPART_HOLDS["GL-11"] (JEG-498): no primary
    # styling exists yet, so only presence (by ID) and draft-until-Apply are checked now.
    buttons = v["s0"]["leagueButtons"]
    if not (buttons["edit"] and buttons["weights"]):
        errors.append(f"league controls missing: #v2EditLeague shown {buttons['edit']}, #v2Weights present {buttons['weights']}")
    lg = v["league"]
    if not (lg["changed"] and lg["hasApply"] and lg["hasCancel"]):
        errors.append(f"Edit league dialog: changed {lg['changed']}, Apply {lg['hasApply']}, Cancel {lg['hasCancel']}")
    if lg["after"] != lg["before"]:
        errors.append(f"a cancelled league edit applied: {lg['before']!r} -> {lg['after']!r}")
    if lg["draftTeams"] != lg["engineTeams"] or lg["afterTeams"] != lg["engineTeams"]:
        errors.append(f"a league draft reached the engine before Apply: teams {lg['engineTeams']} -> "
                      f"{lg['draftTeams']} (draft) -> {lg['afterTeams']} (cancelled)")
    return errors


def gl12(S):
    h = S["tabs"]["how"]
    used = [x for x in (h["used"] or {}).values() if isinstance(x, (int, float))]
    share = h["share"]
    lo, hi = (min(used), max(used)) if used else (share, share)
    want = f"{lo * 100:.1f}%" if f"{lo * 100:.1f}" == f"{hi * 100:.1f}" else f"{lo * 100:.1f}–{hi * 100:.1f}%"
    errors = []
    if h["bench"] != want:
        errors.append(f"How values bench share {h['bench']!r}, engine priced {want}")
    if any(abs(x - share) > 5e-4 for x in used) and not h["benchNote"]:
        errors.append("the engine priced a different bench share and no floor note shows")
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


def mf01(S):
    m = S["tabs"]["manifesto"]
    t = S["tabs"]["targets"]
    errors = []
    first = m["tabs"][0] if m["tabs"] else {}
    if (first.get("view"), first.get("label")) != ("manifesto", "Manifesto"):
        errors.append(f"first tab is {first}, want Manifesto")
    if not m["pages"]["v2Manifesto"] or m["h1"] != "Fantasy Football Manifesto" or len(m["h2"]) != 12:
        errors.append(f"Manifesto: shown {m['pages']['v2Manifesto']}, h1 {m['h1']!r}, {len(m['h2'])} sections")
    if m["links"]:
        errors.append(f"Manifesto has {m['links']} links; the text is verbatim, with none")
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
    for head in ("Our value", "Published chart", "VORP vs waivers"):
        if head not in d["heads"]:
            errors.append(f"player detail has no {head!r} column")
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


def gl17_values(S):
    # GL-17 is live for Player values (JEG-483); the other pages are JEG-500.
    v = S["values"]
    errors = []
    if not (v["expandChart"]["shown"] and v["expandChart"]["svg"]):
        errors.append("Player values: the chart does not expand")
    if not (v["expandTable"]["shown"] and v["expandTable"]["table"]):
        errors.append("Player values: the table does not expand")
    return errors


def tt01(S):
    h = S["tabs"]["targets"]["h1"]
    return [] if h == "Where the trade market is wrong this week" else [f"headline {h!r}"]


def tt02(S):
    t = S["tabs"]["targets"]
    errors = []
    for side in ("sell", "buy"):
        n = len(t[side])
        if n != 5 or not t[f"{side}More"]:
            errors.append(f"{side}: {n} rows, Show all {t[f'{side}More']}")
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


def tt04(S):
    t = S["tabs"]["targets"]
    errors = []
    names = {h["chart"]: h["name"] for h in t["heads"]}
    for r in t["sell"] + t["buy"]:
        if not r["best"] or not r["best"]["who"] or r["best"]["who"] != names.get(r["best"]["chart"]):
            errors.append(f"{r['name']}: largest gap does not name its chart ({r['best']})")
    ex = t.get("expand") or {}
    if ex.get("expanded") != "true" or not all(n in ex.get("detail", "") for n in names.values()):
        errors.append("an expanded row does not show every chart")
    return errors


def tt05_partial(S):
    # TT-05 is held for JEG-510: the live UI says "indexed" until GL-21 renames it "rescaled".
    # Until then, check what exists: a scale word on every chart header and the ⓘ that explains it.
    t = S["tabs"]["targets"]
    errors = []
    for h in t["heads"]:
        if not re.search(r"rescaled|indexed", h["sub"]) or not h["info"]:
            errors.append(f"{h['chart']}: header {h['sub']!r}, ⓘ {h['info']}")
    if not t["captionInfo"] or "scale" not in (t.get("info") or "").lower():
        errors.append("the Compare against ⓘ does not explain the rescaling")
    return errors


def tt06(S):
    t = S["tabs"]["targets"]
    errors = []
    for h in t["heads"]:
        info = t["weeks"].get(h["chart"]) or {}
        if not re.search(r"Wk \d+", h["sub"]):
            errors.append(f"{h['chart']}: no week in {h['sub']!r}")
        if info.get("stale"):
            want = f"Wk {info['week']}" if info.get("week") else "Earlier week"
            if not h["badge"] or h["badge"].strip() != want:
                errors.append(f"{h['chart']} is a week behind: badge {h['badge']!r}, want {want!r}")
        elif h["badge"]:
            errors.append(f"{h['chart']} is current but shows a prior-week badge {h['badge']!r}")
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
    t = S["tabs"]["targets"]
    errors = []
    for r in t["all"]:
        low = (t["allEngine"].get(r["key"]) or {}).get("low", False)
        if low != r["lowconf"]:
            errors.append(f"{r['name']}: one-source {low}, flagged {r['lowconf']}")
    if not any((t["allEngine"].get(r["key"]) or {}).get("low") for r in t["all"]):
        errors.append("no one-source player in the Sell / Buy lists to check (LOW_CONFIDENCE_FIXTURE not applied?)")
    return errors[:5]


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
    if not all(f"{p}=" in a["hash"] for p in ("give", "get", "scoring", "roster", "bench")):
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
    "GL-07": PENDING("JEG-498"), "GL-08": gl08, "GL-09": PENDING("JEG-497"), "GL-10": gl10,
    "GL-11": gl11, "GL-12": gl12, "GL-13": gl13, "GL-14": gl14, "GL-15": gl15, "GL-16": gl16,
    "GL-17": PENDING("JEG-500", partial=gl17_values), "GL-18": PENDING("JEG-500"),
    "GL-19": PENDING("JEG-501"), "GL-20": PENDING("JEG-502"), "GL-21": PENDING("JEG-510"),
    "MF-01": mf01,
    "PV-01": pv01, "PV-02": pv02, "PV-03": pv03, "PV-04": PENDING("JEG-503"), "PV-05": pv05,
    "PV-06": PENDING("JEG-503"), "PV-07": PENDING("JEG-503"), "PV-08": pv08, "PV-09": pv09,
    "PV-10": pv10, "PV-11": pv11, "PV-12": pv12, "PV-13": pv13, "PV-14": pv14, "PV-15": pv15,
    "PV-16": pv16, "PV-17": pv17,
    "TT-01": tt01, "TT-02": tt02, "TT-03": tt03, "TT-04": tt04,
    # Wording hold (WORDING_HOLDS): "rescaled" lands with JEG-510; the ⓘ is checked meanwhile.
    "TT-05": PENDING("JEG-510", partial=tt05_partial),
    "TT-06": tt06, "TT-07": tt07, "TT-08": tt08, "TT-09": PENDING("JEG-504"),
    "RF-01": rf01,
    "CT-01": ct01, "CT-02": PENDING("JEG-505"), "CT-03": ct03, "CT-04": ct04, "CT-05": ct05,
    "CT-06": ct06, "CT-07": ct07,
    "HV-01": hv01,
}

# The scenarios each check reads (a broken-build run loads only what its checks need).
NEEDS = {cid: ("values", "tabs") for cid in live_checks(CHECKS)}
NEEDS.update({"GL-13": ("phone",), "CT-06": ("phone",), "GL-14": ("failure",),
              "GL-05": ("values",), "GL-10": ("values",), "GL-11": ("values",),
              "PV-02": ("values",), "PV-09": ("values",), "MF-01": ("tabs",), "CT-01": ("tabs",),
              "GL-04": ("values", "tabs")})


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
        # A wording hold is the only way a live line may stay pending.
        self.assertTrue(any(e.startswith("TT-05") for e in mirror_errors(text, CHECKS, holds={})))
        # A checked ID leaves the Doc.
        dropped = "\n".join(l for l in text.splitlines() if "**TT-07**" not in l)
        self.assertTrue(any(e.startswith("TT-07") for e in mirror_errors(dropped, CHECKS)))

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
        manifesto_tab = ('        <a class="v2-tab" href="v2/#manifesto" data-view="manifesto" data-short="Manifesto">'
                         '<span class="v2-tab-full">Manifesto</span></a>\n')
        values_tab = ('        <a class="v2-tab" href="v2/#player-values" data-view="values" data-short="Values">'
                      '<span class="v2-tab-full">Player values</span></a>\n')
        broken_shell = cut(cut(shell, manifesto_tab), values_tab, values_tab + manifesto_tab)
        # Swap never shows (removing the node would crash startup, which is a different failure).
        broken_shell = cut(broken_shell, 'id="v2CSwap" hidden>', 'id="v2CSwap" hidden style="display:none !important">')
        broken_shell = cut(broken_shell, 'href="v2/#trade-targets">Data Driven Football</a>',
                           'href="v2/#trade-targets">Data Driven Football · Vegas lines</a>')
        results, _ = run_contract(["MF-01", "CT-01", "GL-01"], {"shell": broken_shell})
        caught(results, "MF-01", "Manifesto moved after Player values")
        caught(results, "CT-01", "Swap removed")
        caught(results, "GL-01", '"Vegas" in the header')

        # Group 2 (v2.js + v2.css): Reset keeps Rank by, prior-week status without a symbol,
        # the DDF line at the others' weight, the ◐ tag removed.
        broken_js = cut(js, '    if (view && view.infoByKey[DDF_KEY] && C.getRankSource() !== DDF_KEY) C.setLockOrder(DDF_KEY);\n')
        broken_js = cut(broken_js, 'prior: "⚠ ", ')
        broken_js = cut(broken_js, '`⚠ ${behind} source', '`${behind} source')
        broken_js = cut(broken_js, "const isLowConfidence = (row, key) => key === DDF_KEY &&",
                        "const isLowConfidence = (row, key) => false &&")
        broken_css = cut(css, ".v2-chart .series.is-ddf { stroke-width: 3.5; }", ".v2-chart .series.is-ddf { stroke-width: 2; }")
        results, _ = run_contract(["PV-02", "PV-09", "GL-04", "GL-05", "GL-03", "TT-08"],
                                  {"v2.js": broken_js, "v2.css": broken_css})
        caught(results, "PV-02", "the DDF line at the others' weight")
        caught(results, "PV-09", "Reset leaving Rank by")
        caught(results, "GL-04", "a prior-week status shown without a symbol")
        caught(results, "GL-05", "a prior-week chip shown without a warning")
        caught(results, "GL-03", "the ◐ 1 source tag removed (Player values)")
        caught(results, "TT-08", "the ◐ 1 source tag removed (Trade targets)")

        # Group 3: Rank by defaults to a chart (the first active source), the chip claims every source is current, the
        # 390 px layout scrolls sideways, a Manifesto section dropped.
        broken_js = cut(js, "const rank = saved && saved.rank ? saved.rank : (hasDdf ? DDF_KEY : null);",
                        'const rank = saved && saved.rank ? saved.rank : (hasDdf ? C.getActiveSources()[0] : null);')
        broken_js = cut(broken_js, '$("v2FreshnessLabel").textContent = stuck ?', '$("v2FreshnessLabel").textContent = false ?')
        broken_js = cut(broken_js, '`${weekText}${freshNotes.join(" · ") || "all sources current"}`',
                        '`${weekText}all sources current`')
        broken_css = css + "\n@media (max-width: 500px) { .v2-wrap { min-width: 480px; } }\n"
        section = re.search(r'    <section class="v2-mf-sec" aria-labelledby="v2M1">.*?</section>\n', shell, re.S)
        self.assertIsNotNone(section, "stale mutation anchor: Manifesto section 1")
        broken_shell = cut(shell, section.group(0))
        results, _ = run_contract(["GL-08", "GL-05", "GL-13", "MF-01"],
                                  {"v2.js": broken_js, "v2.css": broken_css, "shell": broken_shell})
        caught(results, "GL-08", "Rank by defaulting to a chart, not DDF Value")
        caught(results, "GL-05", "a chip claiming every source is current")
        caught(results, "GL-13", "the 390 px layout scrolling sideways")
        caught(results, "MF-01", "a Manifesto section dropped")


if __name__ == "__main__":
    unittest.main()
