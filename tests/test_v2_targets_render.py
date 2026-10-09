"""v2 Trade targets, rendered: the tab's numbers are the engine's numbers, and
the review fixes (JEG-456/458/459/461/464) hold.

Builds dist/v2 into a temp copy of the built dist/, loads /v2/#trade-targets
headless (desktop 1440 × 900 and 1366 × 768, narrow desktop 1024 × 768, phone
390 × 844), and checks against window.TradeValueCurveControls.getRows():

Numbers (every rendered row, both lists, after "Show all" opens 25 of each):
  * "Our value" shows the engine's value for the series picked in "Our value"
    (DDF Value by default, JEG-455; then ESPN, CBS rest-of-season and Razzball
    through the picker);
  * with DDF Value, each row's Our value carries "from N sources" with N the
    engine's row.ddfCount, and the tier in the player sub-line is the engine's
    row.ddfTier; with a projection picked there is no source count and the
    tier is the player's rank by that series against the league's roster
    zones (Jeremy, 2026-10-08: the tier follows the selected series);
  * each chart cell shows the engine's value for that chart, and its gap is
    exactly chart − ours with the right sign; a value the engine does not have
    shows — plus a reason, never 0.0;
  * a chart value at or below its waiver line (0) shows "waiver line" and no
    gap, and no buy target comes from one (Jeremy, 2026-10-07);
  * sell rows are ordered largest positive gap first, buy rows most negative
    first; the per-chart run under an opened row (two-column layout) and on a
    phone card carries the same numbers;
  * the picked series survives a round trip to Player values and a reload
    (remembered on this device); the Methods row stays hidden on this tab;
  * simulated engine rows (SIMULATE_ROWS, until the engine ships them and
    because current data has no chart value at 0): a one-source DDF Value
    (ddfLowConfidence) is a target and shows "◐ 1 source" with the engine's
    note as its tooltip; a player with no DDF input is left out and counted
    with the engine's reason; a chart value of 0 shows "waiver line", no gap;
  * an opened row's "#N on <publisher>" is the engine's getNativeRank.

JEG-464: the H1 and subtitle are the decided copy; the nav tab stays "Trade
targets" ("Targets" on phones).
JEG-461: no Sell/Buy toggle; both lists render at once, each with its top 5
and a "Show all N … targets" control (N = the engine's list length) that opens
25, then pages of 25, and "Show top 5" collapses, each list on its own. Side by
side from 1280 px, stacked below (phone cards too). At 1440 × 900 and
1366 × 768 the H1, subtitle and the top 5 of both lists are above the fold, and
the filters sit on one row. Two-column rows show only Player · Our value ·
Largest gap (+ chart); a row's ▾ opens its per-chart values.
JEG-456 (part 1): from 1024 px the table needs no horizontal scroll; Pos, Team
and Tier are in the player sub-line.
JEG-458: every chart column header reads "Wk N · indexed", "Compare against"
has the caption "Indexed to our scale", and an ⓘ beside it and in each chart
column header opens the indexed explanation with a link to How values work:
aria-expanded tracks it, Enter opens it, Esc closes it and returns focus, and it
never opens a player or reorders rows.
JEG-459: the "Include older-week charts" checkbox is gone; with FantasyPros
simulated one week behind, it is still compared and carries a "Wk 4" badge
(accessible name "FantasyPros has not published Week N yet; showing Week 4.")
in its #v2TChart option, column header, Largest-gap attribution, opened rows,
phone cards and footnote; current-week charts carry none.
Everywhere: 44 px hit areas, no page errors, no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves broken copies of
targets.js, v2.js, v2.css and the page (gap sign flipped, missing read as 0,
waiver rule removed, picked series ignored; prior-week chart dropped, badge
removed; "indexed" label removed, aria-expanded never reset; lists open on 25,
no two-column layout; old headline; Pos/Team/Tier columns back with one-line
headers; default reverted to ESPN, tier read from espnRole, source count
missing, pick not remembered, one-source player left out, low-confidence
marker missing, native rank off by one) and requires the checks to fail on each.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests import _render_env  # noqa: E402
from tests._dist_server import engine_path  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


TARGETS_JS = ROOT / "app" / "v2" / "targets.js"
V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
DDF = "ddf_value"
OURS = (DDF, "espn", "cbsros", "razzball")
TIER_LABEL = {"starter": "Starter", "bench": "Bench", "waiver": "Waiver"}
CHART_NAMES = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS Sports"}
SIDES = {"sell": {"table": "v2TTable", "cards": "v2TCards", "more": "v2TSellMore", "less": "v2TSellLess", "section": "v2TSell"},
         "buy": {"table": "v2TBuyTable", "cards": "v2TBuyCards", "more": "v2TBuyMore", "less": "v2TBuyLess", "section": "v2TBuy"}}
H1 = "Where the trade market is wrong this week"
SUBTITLE = ("We check four published trade charts against our values for your league. "
            "Sell the players they overpay for; buy the ones they undervalue.")
INDEXED_TEXT = ("Published charts use their own point scales. We rescale each chart so its total value matches our "
                "ESPN-based scale for your league, which makes the numbers comparable.")
FULL = ((1440, 900), (1366, 768), (1024, 768), (390, 844))

READ = """([side, ours, ids]) => {
  const C = window.TradeValueCurveControls;
  const rows = C.getRows();
  const engine = Object.fromEntries(rows.map(r => [String(r.player_key), r.values]));
  const ddf = Object.fromEntries(rows.map(r => [String(r.player_key), {count: r.ddfCount, tier: r.ddfTier,
    low: Boolean(r.ddfLowConfidence), note: r.ddfConfidenceNote || null}]));
  const order = rows.map(r => String(r.player_key));
  const st = C.getState();
  const text = node => (node ? node.childNodes[0]?.textContent || "" : null);
  const ownText = node => (node ? [...node.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join("") : null);
  const count = node => { const c = node && node.querySelector('.t-count'); return c ? {text: c.textContent, n: c.dataset.ddfCount,
    low: c.hasAttribute('data-low-confidence'), title: c.title} : null; };
  const tierOf = sub => (sub ? sub.textContent.split(' · ').pop() : null);
  const runOf = span => ({value: span.querySelector('.val')?.textContent ?? null, gap: span.querySelector('.gap')?.textContent ?? null,
    native: span.querySelector('.t-native')?.textContent ?? null,
    atWaiver: Boolean(span.querySelector('.at-waiver')), missing: Boolean(span.querySelector('.missing'))});
  const table = [...document.querySelectorAll(`#${ids.table} tbody tr[data-player-key]`)].map(tr => ({
    key: tr.dataset.playerKey,
    ours: ownText(tr.querySelector('[data-ours]')),
    count: count(tr.querySelector('[data-ours]')),
    tier: tierOf(tr.querySelector('.player-sub')),
    best: text(tr.querySelector('td.best')),
    bestChart: tr.querySelector('td.best').dataset.best,
    cells: Object.fromEntries([...tr.querySelectorAll('td[data-chart]')].map(td => [td.dataset.chart, {
      value: text(td), gap: td.querySelector('.gap')?.textContent ?? null,
      atWaiver: Boolean(td.querySelector('.at-waiver')),
      missing: Boolean(td.querySelector('.missing')), why: td.querySelector('.missing .why')?.textContent ?? null}]))
  }));
  const details = [...document.querySelectorAll(`#${ids.table} tr.t-detail`)].map(tr => ({
    key: tr.dataset.detailFor,
    cells: Object.fromEntries([...tr.querySelectorAll('[data-chart]')].map(s => [s.dataset.chart, runOf(s)]))}));
  const cards = [...document.querySelectorAll(`#${ids.cards} li`)].map(li => ({
    key: li.dataset.playerKey,
    ours: ownText(li.querySelector('.ours')),
    count: count(li.querySelector('.ours')),
    tier: tierOf(li.querySelector('.top .v2-meta')),
    cells: Object.fromEntries([...li.querySelectorAll('.vals [data-chart]')].map(s => [s.dataset.chart, runOf(s)]))
  }));
  return {side, ours, engine, ddf, order, position: st.position, teams: st.teams, roster: C.getRosterShape(),
    zonesFor: C.getZonesFor ? C.getZonesFor(ours) : null,
    natives: C.getNativeRanks ? Object.fromEntries(window.TradeValueV2.targets().used.map(k => [k, C.getNativeRanks(k)])) : null,
    probe: window.__probe || null, omittedNoOurs: window.TradeValueV2.targets().omittedNoOurs,
    note: document.getElementById('v2TNote').textContent,
    table, details, cards, used: window.TradeValueV2.targets().used,
    picker: document.getElementById('v2TOurs').value,
    // Every target on this side, not only the rendered page.
    allBest: window.TradeValueV2.targets()[side].map(p => [String(p.row.player_key), (side === 'sell' ? p.bestSell : p.bestBuy).chart]),
    methodsHidden: document.getElementById('v2Methods').hidden,
    overflow: document.documentElement.scrollWidth - window.innerWidth};
}"""

LAYOUT = """(sides) => {
  const q = s => document.querySelector(s);
  const vis = el => Boolean(el) && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const box = el => { const r = el.getBoundingClientRect(); return {top: r.top, bottom: r.bottom, left: r.left, right: r.right}; };
  const t = window.TradeValueV2.targets();
  const side = name => {
    const ids = sides[name];
    const rows = [...document.querySelectorAll(`#${ids.table} tbody tr[data-player-key]`)];
    const cards = [...document.querySelectorAll(`#${ids.cards} li`)];
    const table = q('#' + ids.table);
    const shown = vis(table) ? rows : cards;
    const wrap = table.closest('.v2-table-wrap');
    const more = q('#' + ids.more), less = q('#' + ids.less);
    return {count: t[name].length, rows: rows.length, cards: cards.length,
      fifthBottom: shown.length ? shown[Math.min(4, shown.length - 1)].getBoundingClientRect().bottom : null,
      more: vis(more) ? more.textContent.trim() : null, less: vis(less),
      section: box(q('#' + ids.section)), tableVisible: vis(table), cardsVisible: vis(q('#' + ids.cards)),
      chartCellsVisible: [...table.querySelectorAll('td[data-chart]')].some(vis),
      expandVisible: [...table.querySelectorAll('[data-expand]')].some(vis),
      subVisible: rows.length ? vis(rows[0].querySelector('.player-sub')) : null,
      wrapScroll: wrap && vis(wrap) ? wrap.scrollWidth - wrap.clientWidth : 0};
  };
  const filters = [...q('#v2Targets .v2-tfilters').children].filter(vis).map(box);
  const tab = q('.v2-tab[data-view="targets"]');
  const thSubs = [...document.querySelectorAll('#v2TTable th[data-chart], #v2TBuyTable th[data-chart]')].map(th => ({
    chart: th.dataset.chart, sub: th.querySelector('.th-sub')?.textContent || '',
    info: th.querySelector('button[data-info]') ? {expanded: th.querySelector('button[data-info]').getAttribute('aria-expanded'),
      label: th.querySelector('button[data-info]').getAttribute('aria-label') || ''} : null}));
  const compareInfo = q('#v2Targets .v2-tcompare button[data-info]');
  // Frame 17: every action has a 44 × 44 px hit area (same probe as test_v2_ux_render).
  const bad = [];
  document.querySelectorAll('#v2Targets button, #v2Targets a, #v2Targets select').forEach(n => {
    const b = n.getBoundingClientRect();
    if (!b.width || n.closest('[hidden]') || b.top - 1 < 0 || b.bottom + 1 > innerHeight) return;
    const cx = b.left + b.width / 2, cy = b.top + b.height / 2;
    const owner = n.closest('label') || n;
    const ok = [-21, 21].every(dy => { const e = document.elementFromPoint(cx, cy + dy); return e && (owner === e || owner.contains(e)); });
    if (!ok || b.width < 43) bad.push(`${n.tagName} "${(n.textContent || n.getAttribute('aria-label') || '').trim().slice(0, 24)}" ${Math.round(b.width)}x${Math.round(b.height)}`);
  });
  return {h1: q('#v2TargetsTitle').textContent.trim(), sub: q('#v2Targets .v2-title p').textContent.trim(),
    h1Bottom: q('#v2TargetsTitle').getBoundingClientRect().bottom, subBottom: q('#v2Targets .v2-title p').getBoundingClientRect().bottom,
    tabFull: tab.querySelector('.v2-tab-full').textContent.trim(), tabShort: tab.dataset.short,
    toggles: document.querySelectorAll('#v2Targets button[data-side], #v2Targets [aria-pressed]').length,
    older: Boolean(q('#v2TOlder')) || /older-week charts/i.test(q('#v2Targets').textContent),
    filters, caption: q('#v2TChartCaption')?.textContent.trim() || '',
    compareInfo: compareInfo ? {expanded: compareInfo.getAttribute('aria-expanded'), label: compareInfo.getAttribute('aria-label') || ''} : null,
    thSubs, sell: side('sell'), buy: side('buy'), bad, innerHeight, innerWidth,
    overflow: document.documentElement.scrollWidth - innerWidth};
}"""

# Simulated engine rows (JEG-455 / Jeremy 2026-10-08, and the waiver rule): wraps getRows so that
#  low  - the player with the highest compared chart value has a one-source DDF Value of 0.5
#         (ddfCount 1, ddfLowConfidence, the engine's note) -> a sell target with the marker;
#  none - another player has no DDF input (null, count 0, a reason) -> left out and counted;
#  zero - the top sell target's second chart is at its waiver line (0) -> "waiver line", no gap.
# Current data has no chart value at or below 0 (JEG-482 pure rescale), so "zero" keeps that rule tested.
SIMULATE_ROWS = """() => {
  const C = window.TradeValueCurveControls, V2 = window.TradeValueV2;
  const t = V2.targets();
  const used = t.used;
  const rows = C.getRows();
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const top = t.sell.find(p => used.filter(c => fin(p.row.values[c]) && p.row.values[c] > 0).length >= 2);
  if (!top) return null;
  const zero = {key: String(top.row.player_key), chart: used.find(c => c !== top.bestSell.chart && fin(top.row.values[c]) && top.row.values[c] > 0)};
  let low = null, best = -Infinity;
  rows.forEach(r => { const k = String(r.player_key); if (k === zero.key || !fin(r.values.ddf_value)) return;
    used.forEach(c => { if (fin(r.values[c]) && r.values[c] > best) { best = r.values[c]; low = k; } }); });
  const none = rows.map(r => String(r.player_key)).find(k => k !== zero.key && k !== low
    && fin(rows.find(r => String(r.player_key) === k).values.ddf_value));
  const note = 'Only one source prices this player', reason = 'No source prices this player';
  const real = C.getRows.bind(C);
  C.getRows = () => real().map(r => {
    const k = String(r.player_key);
    if (k === low) return {...r, values: {...r.values, ddf_value: 0.5}, ddfCount: 1, ddfSources: [used[0]],
      ddfLowConfidence: true, ddfConfidenceNote: note};
    if (k === none) return {...r, values: {...r.values, ddf_value: null}, ddfCount: 0, ddfSources: [], ddfTier: null,
      ddfLowConfidence: false, ddfReason: reason};
    if (k === zero.key) return {...r, values: {...r.values, [zero.chart]: 0}};
    return r;
  });
  window.__probe = {low, none, zero, note, reason};
  document.getElementById('v2TPosition').dispatchEvent(new Event('change'));
  return window.__probe;
}"""

# Simulate a chart one week behind: FantasyPros on Week 4 while the content week is N.
SIMULATE_PRIOR = """() => {
  const C = window.TradeValueCurveControls, P = window.TradeValueProductData;
  const info = C.getSourceInfo.bind(C);
  C.getSourceInfo = () => info().map(i => i.key === 'fantasypros' ? {...i, stale: true, week: 4} : i);
  const fresh = P && P.getSourceFreshness ? P.getSourceFreshness.bind(P) : null;
  if (fresh) P.getSourceFreshness = () => { const f = fresh(); if (!f) return f;
    return {...f, series: {...(f.series || {}), fantasypros: {...((f.series || {}).fantasypros || {}), is_older_week: true, vintage_week: 4}}}; };
  const ref = (fresh && fresh() && fresh().current_content_week) || C.getReferenceWeek();
  const select = document.getElementById('v2TPosition');
  select.dispatchEvent(new Event('change'));
  return ref;
}"""

PRIOR = """() => {
  const badges = root => [...root.querySelectorAll('.v2-prior-badge')].map(b => ({chart: b.dataset.priorWeek, text: b.textContent.trim(),
    label: b.getAttribute('aria-label'), title: b.title}));
  const t = window.TradeValueV2.targets();
  return {used: t.used,
    options: [...document.querySelectorAll('#v2TChart option')].map(o => ({value: o.value, text: o.textContent})),
    headers: [...document.querySelectorAll('#v2TTable th[data-chart], #v2TBuyTable th[data-chart]')].map(th => ({chart: th.dataset.chart, badges: badges(th), sub: th.querySelector('.th-sub').textContent})),
    best: [...document.querySelectorAll('#v2TTable td.best, #v2TBuyTable td.best, #v2TCards .big, #v2TBuyCards .big')].map(td => ({chart: td.dataset.best, badges: badges(td)})),
    details: [...document.querySelectorAll('tr.t-detail [data-chart]')].map(s => ({chart: s.dataset.chart, badges: badges(s)})),
    cards: [...document.querySelectorAll('#v2TCards .vals [data-chart], #v2TBuyCards .vals [data-chart]')].map(s => ({chart: s.dataset.chart, badges: badges(s)})),
    foot: badges(document.getElementById('v2TFootnote')), footText: document.getElementById('v2TFootnote').textContent};
}"""


def fmt(value):
    return f"{value:.1f}"


def fmt_gap(gap):
    text = f"{abs(gap):.1f}"
    if text == "0.0":
        return "0.0"
    return ("+" if gap > 0 else "−") + text


def finite(value):
    return isinstance(value, (int, float)) and value == value and abs(value) != float("inf")


def check_run(where, values, our_key, cell):
    """A per-chart run (opened row or phone card) against the engine."""
    for chart, run in cell.items():
        value = values.get(chart)
        if not finite(value):
            if not run["missing"] or run["value"] is not None:
                return [f"{where}/{chart}: engine has no value but shows {run}"]
        elif value <= 0:
            if run["value"] != fmt(value) or run["gap"] is not None or not run["atWaiver"]:
                return [f"{where}/{chart}: chart value {value} is at the waiver line but shows {run}"]
        elif run["value"] != fmt(value) or run["gap"] != fmt_gap(value - values[our_key]):
            return [f"{where}/{chart}: {run} vs engine {value}"]
    return []


def expected_tiers(snapshot) -> dict:
    """Tier per player for the picked series: DDF Value → the engine's ddfTier; a projection → the
    player's rank by that series (engine row order breaks ties) against the league's roster zones."""
    our_key = snapshot["ours"]
    if our_key == DDF:
        return {key: TIER_LABEL.get(d["tier"], "—") for key, d in snapshot["ddf"].items()}
    priced = [k for k in snapshot["order"] if finite((snapshot["engine"].get(k) or {}).get(our_key))]
    priced.sort(key=lambda k: -snapshot["engine"][k][our_key])   # stable: engine order breaks ties
    if snapshot["position"] == "ALL":
        shape = snapshot["roster"]
        slots = sum(shape.get(p, 0) for p in ("QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"))
        starter, bench = snapshot["teams"] * slots + 0.5, snapshot["teams"] * (slots + shape["BENCH"]) + 0.5
    else:
        zones = snapshot["zonesFor"] or {}
        starter, bench = zones.get("starter_to_bench"), zones.get("bench_to_waiver")
    out = {}
    for rank, key in enumerate(priced, 1):
        out[key] = "Starter" if rank < starter else "Bench" if rank < bench else "Waiver"
    return out


def check_ours_extras(where, snapshot, key, shown) -> list[str]:
    """JEG-455: DDF Value's source count (or the one-source marker), and the tier from the picked series."""
    errors = []
    if snapshot["ours"] == DDF:
        d = snapshot["ddf"][key]
        n = d["count"]
        if d["low"]:
            c = shown["count"] or {}
            if not c.get("low") or c.get("text") != f"◐ {n} source" or c.get("title") != d["note"]:
                errors.append(f"{where}: one-source DDF Value shows {shown['count']}, want '◐ {n} source' titled {d['note']!r}")
        else:
            want = f"from {n} source{'' if n == 1 else 's'}"
            if not shown["count"] or shown["count"]["text"] != want or shown["count"]["n"] != str(n) or shown["count"]["low"]:
                errors.append(f"{where}: source count {shown['count']}, engine ddfCount {n} ({want!r})")
    elif shown["count"]:
        errors.append(f"{where}: a source count {shown['count']} shown for {snapshot['ours']}")
    want_tier = snapshot["tiers"].get(key, "—")
    if shown["tier"] != want_tier:
        errors.append(f"{where}: tier {shown['tier']!r}, expected {want_tier!r} from {snapshot['ours']}")
    return errors


def check(snapshot) -> list[str]:
    errors = []
    side = snapshot["side"]
    our_key = snapshot["ours"]
    engine = snapshot["engine"]
    snapshot["tiers"] = expected_tiers(snapshot)
    probe = snapshot["probe"]
    if not probe:
        errors.append("rows were not simulated")
    else:
        listed = {key for key, _ in snapshot["allBest"]}
        if our_key == DDF and side == "sell":
            if probe["low"] not in listed:
                errors.append(f"one-source player {probe['low']} is not a sell target (Jeremy: show it, flagged)")
            if not any(r["key"] == probe["low"] for r in snapshot["table"] + snapshot["cards"]):
                errors.append(f"one-source player {probe['low']} is not rendered in the top rows")
        if our_key == DDF:
            if probe["none"] in listed:
                errors.append(f"player {probe['none']} with no DDF input is listed as a {side} target")
            if snapshot["omittedNoOurs"] < 1 or probe["reason"] not in snapshot["note"]:
                errors.append(f"player with no DDF input not counted with the engine's reason: {snapshot['note']!r}")
        zrows = [r for r in snapshot["table"] if r["key"] == probe["zero"]["key"]]
        if our_key == DDF and side == "sell" and snapshot["table"] and not zrows:
            errors.append(f"the waiver-line probe {probe['zero']} is not rendered")
    if snapshot["picker"] != our_key:
        errors.append(f"picker shows {snapshot['picker']!r}, expected {our_key!r}")
    if not snapshot["methodsHidden"]:
        errors.append("the Methods row must stay hidden on Trade targets")
    if not snapshot["used"]:
        errors.append("no published chart compared")
    if not snapshot["table"]:
        errors.append(f"no {side} rows rendered")
    for key, chart in snapshot["allBest"]:
        value = (engine.get(key) or {}).get(chart)
        if not finite(value) or value <= 0:
            errors.append(f"{key}: {side} target from {chart} at {value!r}, at or below that chart's waiver line")
    best_gaps = []
    for row in snapshot["table"]:
        values = engine.get(row["key"])
        if values is None:
            errors.append(f"row {row['key']} is not an engine row")
            continue
        ours = values.get(our_key)
        if not finite(ours) or row["ours"] != fmt(ours):
            errors.append(f"{row['key']}: ours {row['ours']!r} != engine {our_key} {ours!r}")
            continue
        errors += check_ours_extras(f"row {row['key']}", snapshot, row["key"], row)
        gaps = {}
        for chart, cell in row["cells"].items():
            value = values.get(chart)
            if not finite(value):
                if not cell["missing"] or not cell["why"] or "0.0" in (cell["value"] or ""):
                    errors.append(f"{row['key']}/{chart}: engine has no value but cell shows {cell}")
                continue
            if cell["missing"] or cell["value"] != fmt(value):
                errors.append(f"{row['key']}/{chart}: shows {cell['value']!r}, engine {value!r}")
            if value <= 0:
                # At this chart's waiver line: never a target, no gap.
                if cell["gap"] is not None or not cell["atWaiver"]:
                    errors.append(f"{row['key']}/{chart}: chart value {value} is at the waiver line but shows {cell}")
                continue
            gap = value - ours
            gaps[chart] = gap
            if cell["gap"] != fmt_gap(gap):
                errors.append(f"{row['key']}/{chart}: gap {cell['gap']!r}, expected {fmt_gap(gap)!r} (chart − ours)")
        if not gaps:
            errors.append(f"{row['key']}: listed as {side} target with no chart above its waiver line")
            continue
        pick = max(gaps, key=gaps.get) if side == "sell" else min(gaps, key=gaps.get)
        if (side == "sell" and gaps[pick] <= 0) or (side == "buy" and gaps[pick] >= 0):
            errors.append(f"{row['key']}: listed as {side} target with gaps {gaps}")
            continue
        if row["bestChart"] != pick or row["best"] != fmt_gap(gaps[pick]):
            errors.append(f"{row['key']}: largest gap {row['best']!r} {row['bestChart']} != {fmt_gap(gaps[pick])} {pick}")
        best_gaps.append(gaps[pick])
    ordered = sorted(best_gaps, reverse=(side == "sell"))
    if best_gaps != ordered:
        errors.append(f"{side} rows are not ordered by largest gap")
    natives = snapshot["natives"] or {}
    for detail in snapshot["details"]:
        values = engine.get(detail["key"], {})
        for chart, run in detail["cells"].items():
            rank = (natives.get(chart) or {}).get(detail["key"])
            want = f"#{rank} on {CHART_NAMES[chart]}" if rank is not None else None
            if natives and run["native"] != want:
                errors.append(f"opened row {detail['key']}/{chart}: native rank {run['native']!r}, engine {want!r}")
        if set(detail["cells"]) != set(snapshot["used"]):
            errors.append(f"opened row {detail['key']}: charts {sorted(detail['cells'])} != compared {sorted(snapshot['used'])}")
        errors += check_run(f"opened row {detail['key']}", values, our_key, detail["cells"])
    for card in snapshot["cards"]:
        values = engine.get(card["key"], {})
        if not finite(values.get(our_key)) or card["ours"] != f"Ours {fmt(values[our_key])}":
            errors.append(f"card {card['key']}: {card['ours']!r} vs engine {our_key} {values.get(our_key)!r}")
            continue
        errors += check_ours_extras(f"card {card['key']}", snapshot, card["key"], card)
        errors += check_run(f"card {card['key']}", values, our_key, card["cells"])
    return errors


def check_layout(lay, width, height, expanded=False) -> list[str]:
    """JEG-456/458/461/464 on a freshly loaded tab (both lists collapsed)."""
    errors = []
    if lay["h1"] != H1:
        errors.append(f"H1 is {lay['h1']!r}, expected {H1!r} (JEG-464)")
    if lay["sub"] != SUBTITLE:
        errors.append(f"subtitle is {lay['sub']!r} (JEG-464)")
    if lay["tabFull"] != "Trade targets" or lay["tabShort"] != "Targets":
        errors.append(f"nav tab {lay['tabFull']!r}/{lay['tabShort']!r}, expected Trade targets/Targets")
    if lay["toggles"]:
        errors.append("a Sell/Buy toggle is still on the tab (JEG-461: both lists show at once)")
    if lay["older"]:
        errors.append("the 'Include older-week charts' control is still on the tab (JEG-459)")
    if not lay["caption"].startswith("Indexed to our scale"):
        errors.append(f"Compare against caption is {lay['caption']!r} (JEG-458)")
    if not lay["compareInfo"] or lay["compareInfo"]["expanded"] != "false" or not lay["compareInfo"]["label"]:
        errors.append(f"no closed, labeled ⓘ beside Compare against: {lay['compareInfo']} (JEG-458)")
    if not lay["thSubs"]:
        errors.append("no chart column headers")
    for th in lay["thSubs"]:
        if not th["sub"].endswith("indexed") or "Wk " not in th["sub"]:
            errors.append(f"{th['chart']} header sub-label {th['sub']!r}, expected 'Wk N · indexed' (JEG-458)")
        if not th["info"] or th["info"]["expanded"] != "false" or not th["info"]["label"]:
            errors.append(f"{th['chart']} header has no closed, labeled ⓘ: {th['info']} (JEG-458)")
    errors += [f"hit area under 44 px: {b}" for b in lay["bad"]]
    if lay["overflow"] > 0:
        errors.append(f"horizontal page overflow {lay['overflow']}px")
    for side in ("sell", "buy"):
        s = lay[side]
        want = min(5, s["count"])
        if not s["count"]:
            errors.append(f"{side}: the engine gives no targets (nothing to test)")
            continue
        shown = s["cards"] if width < 768 else s["rows"]
        if not expanded and shown != want:
            errors.append(f"{side}: {shown} shown on load, expected the top {want} (JEG-461)")
        if not expanded and s["count"] > 5 and s["more"] != f"Show all {s['count']} {side} targets ▾":
            errors.append(f"{side}: show-all control reads {s['more']!r}, expected 'Show all {s['count']} {side} targets ▾'")
        if not expanded and s["less"]:
            errors.append(f"{side}: 'Show top 5' is offered while the list is already collapsed")
        if width < 768:
            if not s["cardsVisible"] or s["tableVisible"]:
                errors.append(f"{side}: phone layout must show cards, not the table")
        else:
            if not s["tableVisible"]:
                errors.append(f"{side}: table not visible at {width}px")
            if s["wrapScroll"] > 0:
                errors.append(f"{side}: table scrolls sideways by {s['wrapScroll']}px at {width}px (JEG-456)")
            if not s["subVisible"]:
                errors.append(f"{side}: Pos · Team · Tier sub-line hidden at {width}px (JEG-456)")
            two_col = width >= 1280
            if two_col and (s["chartCellsVisible"] or not s["expandVisible"]):
                errors.append(f"{side}: two-column rows must show the compact column set with a ▾ per row (JEG-461)")
            if not two_col and (not s["chartCellsVisible"] or s["expandVisible"]):
                errors.append(f"{side}: single-column table must show every chart column at {width}px")
    sell, buy = lay["sell"]["section"], lay["buy"]["section"]
    if width >= 1280:
        if not (abs(sell["top"] - buy["top"]) < 2 and sell["right"] <= buy["left"]):
            errors.append(f"lists are not side by side at {width}px: sell {sell} buy {buy} (JEG-461)")
    elif buy["top"] < sell["bottom"]:
        errors.append(f"lists are not stacked (Sell then Buy) at {width}px (JEG-461)")
    if (width, height) in ((1440, 900), (1366, 768)) and not expanded:
        fold = lay["innerHeight"]
        for name, bottom in (("H1", lay["h1Bottom"]), ("subtitle", lay["subBottom"]),
                             ("sell top 5", lay["sell"]["fifthBottom"]), ("buy top 5", lay["buy"]["fifthBottom"])):
            if bottom is None or bottom > fold:
                errors.append(f"{name} ends at {bottom}px, below the {width}×{height} fold (JEG-461)")
        tops = [f["top"] for f in lay["filters"]]
        if tops and max(tops) - min(tops) > 8:
            errors.append(f"filters wrap to more than one row at {width}px: tops {tops} (JEG-461)")
    return errors


def check_prior(prior, ref_week, width) -> list[str]:
    """JEG-459 with FantasyPros simulated on Week 4."""
    errors = []
    label = f"FantasyPros has not published Week {ref_week} yet; showing Week 4."
    if "fantasypros" not in prior["used"]:
        return [f"a chart on an earlier week must still be compared: used {prior['used']} (JEG-459)"]

    def badge_ok(where, badges, chart):
        if chart == "fantasypros":
            if not any(b["chart"] == "fantasypros" and b["text"] == "Wk 4" and b["label"] == label and b["title"] == label for b in badges):
                return [f"{where}: no 'Wk 4' badge labeled {label!r}: {badges}"]
        elif badges:
            return [f"{where}: current-week chart {chart} carries a badge {badges}"]
        return []
    for o in prior["options"]:
        has = "Wk 4" in o["text"]
        if (o["value"] == "fantasypros") != has:
            errors.append(f"#v2TChart option {o['value']!r} reads {o['text']!r}")
    for th in prior["headers"]:
        errors += badge_ok(f"{th['chart']} column header", th["badges"], th["chart"])
        if th["chart"] == "fantasypros" and not th["sub"].endswith("Wk 4 · indexed"):
            errors.append(f"FantasyPros header sub-label {th['sub']!r}")
    fp_best = [b for b in prior["best"] if b["chart"] == "fantasypros"]
    if not fp_best:
        errors.append("no visible target's largest gap is from FantasyPros (attribution badge untested)")
    for b in prior["best"]:
        errors += badge_ok(f"largest gap from {b['chart']}", b["badges"], b["chart"])
    for d in prior["details"]:
        errors += badge_ok(f"opened row {d['chart']}", d["badges"], d["chart"])
    if width < 768:
        if not prior["cards"]:
            errors.append("no phone cards to check")
        for c in prior["cards"]:
            errors += badge_ok(f"card {c['chart']}", c["badges"], c["chart"])
    elif width >= 1280 and not prior["details"]:
        errors.append("no opened row to check")
    errors += badge_ok("footnote", prior["foot"], "fantasypros")
    if label not in prior["footText"]:
        errors.append(f"footnote does not say {label!r}")
    return errors


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist(html_sub=None):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)
        if html_sub is not None:
            page = dist / "v2" / "index.html"
            html = page.read_text(encoding="utf-8")
            if html_sub[0] not in html:
                raise AssertionError(f"html mutation anchor is stale: {html_sub[0]!r}")
            page.write_text(html.replace(html_sub[0], html_sub[1]), encoding="utf-8")

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

            def translate_path(self, path):
                # JEG-453: /classic/ is the build-only engine page (tests that
                # import _built_dist drive the engine's own controls there).
                return engine_path(path) or super().translate_path(path)
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#trade-targets"
            finally:
                server.shutdown()


def _open(browser, url, width, height, targets_js, v2_js, v2_css):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # Only the local build is under test; the web font is not.
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    for pattern, body, kind in (("**/v2/targets.js*", targets_js, "text/javascript"),
                                ("**/v2/v2.js*", v2_js, "text/javascript"), ("**/v2/v2.css*", v2_css, "text/css")):
        if body is not None:
            page.route(pattern, functools.partial(_serve, body, kind))
    page.goto(url, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=40000)
    if not page.evaluate(SIMULATE_ROWS):
        errors.append("no sell target with two charts to simulate rows on")
    page.wait_for_timeout(200)
    return page, errors


def _popover_checks(page, width) -> list[str]:
    """JEG-458: the ⓘ beside Compare against, and one in a column header."""
    errors = []
    probes = [".v2-tcompare button[data-info]"]
    # A chart column header's ⓘ where chart columns show; the Largest gap header's otherwise.
    if width >= 768:
        probes.append("#v2TTable th[data-chart] button[data-info]" if width < 1280 else "#v2TTable th.t-best button[data-info]")
    for n, selector in enumerate(probes):
        button = page.locator(selector).first
        if not button.count():
            errors.append(f"no ⓘ at {selector}")
            continue
        order = page.evaluate("() => [...document.querySelectorAll('#v2TTable tbody tr[data-player-key]')].map(r => r.dataset.playerKey)")
        if n == 0:
            button.click()
        else:
            button.focus()
            page.keyboard.press("Enter")
        state = page.evaluate("""(sel) => { const b = document.querySelector(sel); const pop = document.getElementById('v2Popover');
          const link = pop.querySelector('a[href$="#how-values"]');
          return {open: !pop.hidden, text: pop.textContent, link: Boolean(link), expanded: b.getAttribute('aria-expanded'),
            drawer: !document.getElementById('v2Drawer').hidden,
            order: [...document.querySelectorAll('#v2TTable tbody tr[data-player-key]')].map(r => r.dataset.playerKey)}; }""", selector)
        if not state["open"] or INDEXED_TEXT not in state["text"] or not state["link"]:
            errors.append(f"{selector}: popover open={state['open']} link={state['link']} text={state['text'][:80]!r}")
        if state["expanded"] != "true":
            errors.append(f"{selector}: aria-expanded {state['expanded']!r} while open")
        if state["drawer"] or state["order"] != order:
            errors.append(f"{selector}: opening the ⓘ also opened a player or reordered rows")
        page.keyboard.press("Escape")
        after = page.evaluate("""(sel) => { const b = document.querySelector(sel);
          return {open: !document.getElementById('v2Popover').hidden, expanded: b.getAttribute('aria-expanded'),
            focused: document.activeElement === b, drawer: !document.getElementById('v2Drawer').hidden}; }""", selector)
        if after["open"] or after["expanded"] != "false" or not after["focused"] or after["drawer"]:
            errors.append(f"{selector}: after Esc {after}")
    return errors


def _paging_checks(page, width) -> list[str]:
    """JEG-461: Show all → 25, Show more → 50, Show top 5 → 5; each list on its own."""
    count = """(ids) => { const t = document.getElementById(ids.table); const vis = getComputedStyle(t.closest('.v2-table-wrap')).display !== 'none';
      return vis ? document.querySelectorAll(`#${ids.table} tbody tr[data-player-key]`).length : document.querySelectorAll(`#${ids.cards} li`).length; }"""
    total = page.evaluate("() => window.TradeValueV2.targets().sell.length")
    buy_total = page.evaluate("() => window.TradeValueV2.targets().buy.length")
    if total <= 5:
        return [f"only {total} sell targets: paging untested"]
    if not page.is_visible("#v2TSellMore"):
        return ["no Show all control on the sell list"]
    page.click("#v2TSellMore")
    errors = []
    if page.evaluate(count, SIDES["sell"]) != min(25, total) or page.evaluate(count, SIDES["buy"]) != min(5, buy_total):
        errors.append("Show all on Sell must open 25 sell targets and leave Buy at 5")
    if total > 25:
        more = page.text_content("#v2TSellMore").strip() if page.is_visible("#v2TSellMore") else None
        if more != f"Show more (25 of {total}) ▾":
            return errors + [f"after Show all the control reads {more!r}"]
        page.click("#v2TSellMore")
        if page.evaluate(count, SIDES["sell"]) != min(50, total):
            errors.append("Show more must add 25")
    if not page.is_visible("#v2TSellLess"):
        return errors + ["no Show top 5 control on an opened list"]
    page.click("#v2TSellLess")
    if page.evaluate(count, SIDES["sell"]) != 5:
        errors.append("Show top 5 must collapse the sell list to 5")
    if page.is_visible("#v2TSellLess"):
        errors.append("Show top 5 still offered after collapsing")
    return errors


def collect(targets_js=None, v2_js=None, v2_css=None, html_sub=None, viewports=FULL, numbers=True, layout=True):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    found = {"table": False, "cards": False}
    with _built_dist(html_sub) as url, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                tag = f"[{width}x{height}] "
                page, page_errors = _open(browser, url, width, height, targets_js, v2_js, v2_css)
                if layout:
                    errors += [tag + e for e in check_layout(page.evaluate(LAYOUT, SIDES), width, height)]
                    errors += [tag + e for e in _popover_checks(page, width)]
                    errors += [tag + e for e in _paging_checks(page, width)]
                full_numbers = numbers and width in (1440, 390)
                for ours in (OURS if full_numbers else (DDF,) if numbers else ()):
                    if ours != DDF:
                        page.select_option("#v2TOurs", ours)
                        # The pick must survive a trip to Player values and back.
                        page.evaluate("() => { location.hash = '#player-values'; }")
                        page.wait_for_function("() => !document.getElementById('v2Main').hidden")
                        page.evaluate("() => { location.hash = '#trade-targets'; }")
                        page.wait_for_function("() => !document.getElementById('v2Targets').hidden")
                    for side, ids in SIDES.items():
                        if page.is_visible(f"#{ids['more']}"):
                            page.click(f"#{ids['more']}")   # 25 rows to check, not 5
                        if width >= 1280:
                            for i in range(2):   # open two rows' per-chart values
                                toggle = page.locator(f"#{ids['table']} tr[data-player-key] [data-expand][aria-expanded=false]").nth(0)
                                if toggle.count():
                                    toggle.click()
                        snap = page.evaluate(READ, [side, ours, ids])
                        found["table"] |= bool(snap["table"]) and width >= 768
                        found["cards"] |= bool(snap["cards"]) and width < 768
                        errors += [tag + f"{ours} {side} " + e for e in check(snap)]
                        if width >= 1280 and not snap["details"]:
                            errors.append(tag + f"{ours} {side}: ▾ did not open a row's per-chart values")
                        if width < 768 and snap["overflow"] > 0:
                            errors.append(tag + f"horizontal overflow {snap['overflow']}px")
                if full_numbers:
                    # Remembered on this device: the last pick (Razzball) is back after a reload.
                    page.reload(wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets()", timeout=40000)
                    picked = page.evaluate("() => [document.getElementById('v2TOurs').value, window.TradeValueV2.targets().ours]")
                    if picked != [OURS[-1], OURS[-1]]:
                        errors.append(tag + f"Our value after a reload is {picked}, expected {OURS[-1]!r} (remembered)")
                if layout and width in (1440, 390):
                    ref_week = page.evaluate(SIMULATE_PRIOR)
                    page.wait_for_timeout(200)
                    if width >= 1280:
                        for ids in SIDES.values():
                            toggle = page.locator(f"#{ids['table']} tr[data-player-key] [data-expand]").first
                            if toggle.count():
                                toggle.click()
                    for ids in SIDES.values():
                        if page.is_visible(f"#{ids['more']}"):
                            page.click(f"#{ids['more']}")
                    errors += [tag + e for e in check_prior(page.evaluate(PRIOR), ref_week, width)]
                if page_errors:
                    errors.append(tag + f"page errors: {page_errors}")
                page.close()
        finally:
            browser.close()
    if numbers and not found["table"] and any(w >= 768 for w, _ in viewports):
        errors.append("no table rows were checked")
    if numbers and not found["cards"] and any(w < 768 for w, _ in viewports):
        errors.append("no phone cards were checked")
    return errors


class TradeTargetsRenderTest(unittest.TestCase):
    def test_rendered_numbers_and_layout(self):
        self.assertEqual(collect(), [])

    def test_guard_fails_on_broken_builds(self):
        # Anchors are written with \n; a Windows checkout may have \r\n.
        targets, v2, css = (path.read_text(encoding="utf-8").replace("\r\n", "\n") for path in (TARGETS_JS, V2_JS, V2_CSS))
        desk = ((1440, 900),)
        numbers_only = {"viewports": desk, "layout": False}
        broken = {
            "sign flipped": ({"targets_js": (targets, "const gap = value - ours;", "const gap = ours - value;")}, numbers_only),
            "missing read as zero": ({"targets_js": (targets, "const value = row.values[chart];",
                                                     "const value = row.values[chart] ?? 0;")}, numbers_only),
            "waiver rule removed": ({"targets_js": (targets, "if (value <= 0) {", "if (false) {")}, numbers_only),
            "picked series ignored": ({"targets_js": (targets, "const ourKey = (opts && opts.ours) || OUR_KEY;",
                                                      "const ourKey = OUR_KEY;")}, numbers_only),
            # JEG-459
            "prior-week chart dropped": ({"targets_js": (targets, "      else used.push(key);",
                                                         "      else if (!item.stale) used.push(key);")}, {"viewports": desk, "numbers": False}),
            "prior-week badge removed": ({"v2_js": (v2, "    if (!item || !item.stale) return null;\n    const name",
                                                    "    return null;\n    const name")}, {"viewports": desk, "numbers": False}),
            # JEG-458
            "indexed label removed": ({"v2_js": (v2, '`${week.textContent ? " · " : ""}indexed`', '""')}, {"viewports": desk, "numbers": False}),
            "aria-expanded never reset": ({"v2_js": (v2, 'if (popoverAnchor && popoverAnchor.getAttribute("aria-expanded") === "true") popoverAnchor.setAttribute("aria-expanded", "false");',
                                                     "")}, {"viewports": desk, "numbers": False}),
            # JEG-461
            "lists open on 25": ({"v2_js": (v2, "const TARGETS_TOP = 5;", "const TARGETS_TOP = 25;")}, {"viewports": ((1366, 768),), "numbers": False}),
            "no two-column layout": ({"v2_css": (css, "  .v2-tlists { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }\n", "")},
                                     {"viewports": ((1366, 768),), "numbers": False}),
            # JEG-464
            "old headline": ({"html_sub": (f">{H1}<", ">Sell high. Buy low.<")}, {"viewports": ((390, 844),), "numbers": False}),
            # JEG-456
            # The pre-fix table: Pos / Team / Tier columns back, and one-line headers.
            "Pos/Team/Tier columns and one-line headers": (
                {"v2_js": (v2, '    head("Player", "player");\n',
                           '    head("Player", "player"); head("Pos", "col-meta"); head("Team", "col-meta"); head("Tier", "col-meta");\n',
                           '      const ours = td("num is-rank");\n',
                           '      td("col-meta", p.row.pos); td("col-meta", p.row.team || "FA"); td("col-meta", tierLabel(p.row.ddfTier));\n'
                           '      const ours = td("num is-rank");\n'),
                 "v2_css": (css, ".v2-ttable th { vertical-align: bottom; white-space: normal; line-height: 1.25; }",
                            ".v2-ttable th { vertical-align: bottom; white-space: nowrap; line-height: 1.25; }")},
                {"viewports": ((1024, 768),), "numbers": False}),
            # JEG-455 / tier ruling
            "default reverted to ESPN": ({"targets_js": (targets, "const OUR_KEY = OUR_KEYS[0];", "const OUR_KEY = OUR_KEYS[1];")}, numbers_only),
            "tier read from espnRole": ({"v2_js": (v2, "const tierText = (row, key, scope) => tierLabel(tierFor(row, key, scope));",
                                                   "const tierText = row => tierLabel(row.espnRole);")}, numbers_only),
            "source count missing": ({"v2_js": (v2, "      if (count) cell.appendChild(count);\n", "")}, numbers_only),
            "pick not remembered": ({"v2_js": (v2, "      saveTargetsOurs(T.ours);\n", "")}, numbers_only),
            "one-source player left out": ({"targets_js": (targets, "      if (!finite(ours)) {",
                                                           "      if (!finite(ours) || row.ddfLowConfidence) {")}, numbers_only),
            "low-confidence marker missing": ({"v2_js": (v2, "    if (isLowConfidence(row, DDF_KEY)) {\n      const node = lowConfidenceNode(row);",
                                                         "    if (false) {\n      const node = lowConfidenceNode(row);")}, numbers_only),
            "native rank off by one": ({"v2_js": (v2, "native.textContent = `#${rank} on", "native.textContent = `#${rank + 1} on")}, numbers_only),
        }
        for name, (mutation, opts) in broken.items():
            with self.subTest(mutation=name):
                kwargs = {}
                for key, value in mutation.items():
                    if key == "html_sub":
                        kwargs[key] = value
                        continue
                    source, pairs = value[0], value[1:]
                    for old, new in zip(pairs[::2], pairs[1::2]):
                        self.assertEqual(source.count(old), 1, f"mutation anchor for {name!r} is stale: {old!r}")
                        source = source.replace(old, new, 1)
                    kwargs[key] = source
                self.assertNotEqual(collect(**kwargs, **opts), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
