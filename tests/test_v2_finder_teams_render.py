"""v2 Find a trade, the team value summary (JEG-890), rendered on the Find a trade page.

Both rosters are typed in with the card's own player search; the summary card must show without pressing Find trades
(it reads the rosters, not the results). Checked at 1366x768 and at 375 / 390 wide, against an independent computation
in the page from getAllRows:

  * two team blocks (mine, theirs), rows Starters / Bench / Total and QB / RB / WR / TE, columns DDF Value and the
    Trade chart average; the DDF column equals the sum of the listed players' DDF Value and the best DDF lineup;
  * "Show each chart" opens the per-chart columns, each equal to the sum of the listed players' value in that chart;
  * a held chart (the pinned fixture holds CBS) is named "CBS Sports not compared" and is never a column;
  * on a phone the card stacks (one team block, then the other) and nothing scrolls sideways;
  * changing the league scoring rebuilds the card from the new rows.

JEG-1246 (correction of the review at 7d84cdb9), the same card at 1366x768 and 390 wide:

  * with 0, 1 and 2 usable trade charts (the engine's other charts reported unavailable) the card renders with no page
    error: the Trade chart average column reads "n/a" in every row, a note says there are not enough charts, the
    per-chart columns are exactly the usable charts (none with 0, "No trade chart is compared this week."), each
    dropped chart is named "not compared", and the DDF column still equals the listed players' sum (failing before:
    tsTable read the absent average's cells and threw);
  * a listed starter whose DDF Value is missing (the engine rows report none for him) keeps his identity: a "No DDF
    Value" row appears for that team, DDF shows "—" there (never 0), Starters and Bench carry a "*", a note names him,
    and in the Trade chart average and every chart column Starters + Bench + No DDF Value = Total.

JEG-1246 phone layout (Codex's Mac review 8e0720c5): with "Show each chart" open and a partial Total (a player one chart
does not price), every cell's content stays inside its cell at 390 and 375 wide, with the word "incomplete" shown (no
clipping, no truncation, no sideways scroll), with the compared charts and again with all four charts as columns.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the two teams' numbers swapped, the held chart
left unnamed, and the card not rebuilt on a league change, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add
from tests.test_v2_modules_render import _serve


def setUpModule():
    _render_env.ensure_built()


CARD = """() => {
  const box = document.getElementById('v2FindTeamSummary');
  if (!box || box.hidden) return null;
  const grid = box.querySelector('.v2-find-ts-grid');
  const blocks = [...grid.querySelectorAll('.v2-find-ts-team[data-team]')];
  const cell = (team, row, series) => {
    const td = box.querySelector(`.v2-find-ts-team[data-team=${team}] tr[data-row=${row}] td[data-series='${series}']`);
    return td ? td.textContent.trim() : null;
  };
  return {
    teams: blocks.map(b => b.dataset.team),
    ddf: Object.fromEntries(['mine', 'theirs'].map(t => [t, Object.fromEntries(
      ['starters', 'bench', 'total', 'QB', 'RB', 'WR', 'TE'].map(r => [r, cell(t, r, 'ddf')]))])),
    marketTotal: {mine: cell('mine', 'total', 'market'), theirs: cell('theirs', 'total', 'market')},
    held: [...box.querySelectorAll('[data-note=held]')].map(li => li.textContent),
    incomplete: [...box.querySelectorAll('[data-note=incomplete]')].map(li => li.textContent),
    chartCells: [...box.querySelectorAll('.v2-find-ts-charts .v2-find-ts-team')].flatMap(t =>
      [...t.querySelectorAll('tr[data-row]')].map(tr => ({team: t.dataset.team, row: tr.dataset.row,
        series: [...tr.querySelectorAll('td[data-series]')].map(td => ({id: td.dataset.series, text: td.textContent.trim()}))}))),
    detailsOpen: Boolean(box.querySelector('.v2-find-ts-charts[open]')),
    chartColumns: [...box.querySelectorAll('.v2-find-ts-charts thead th[data-series]')].map(th => th.dataset.series),
    tops: blocks.map(b => Math.round(b.getBoundingClientRect().top)),
    lefts: blocks.map(b => Math.round(b.getBoundingClientRect().left)),
    text: box.textContent
  };
}"""

# The independent reading: the listed players' DDF Value sums and best DDF lineup, and the per-chart sums.
INDEP = """(side) => {
  const C = window.TradeValueCurveControls;
  const shape = C.getRosterShape();
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  const names = [...document.querySelectorAll(`#v2Find${side}Players li b`)].map(b => byName.get(b.textContent)).filter(Boolean);
  const fin = v => typeof v === 'number' && Number.isFinite(v);
  const chartKeys = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'];
  const avail = new Set((C.getSourceInfo ? C.getSourceInfo() : []).filter(s => s.available).map(s => s.key));
  const charts = chartKeys.filter(k => avail.has(k));
  const total = names.reduce((n, r) => n + (fin(r.values.ddf_value) ? r.values.ddf_value : 0), 0);
  const v = names.filter(r => fin(r.values.ddf_value)).sort((a, b) => b.values.ddf_value - a.values.ddf_value || String(a.player_key).localeCompare(String(b.player_key)));
  const used = new Set(); let starters = 0;
  const take = (n, pos) => { for (let k = 0; k < n; k++) { const r = v.find(x => !used.has(x) && pos.includes(x.pos)); if (r) { used.add(r); starters += r.values.ddf_value; } } };
  ['QB', 'RB', 'WR', 'TE'].forEach(p => take(shape[p] || 0, [p])); take(shape.FLEX || 0, ['RB', 'WR', 'TE']); take(shape.SUPERFLEX || 0, ['QB', 'RB', 'WR', 'TE']);
  const mean = r => { const vals = charts.map(k => r.values[k]); return charts.length >= 3 && vals.every(fin) ? vals.reduce((a, b) => a + b, 0) / vals.length : null; };
  return {total, starters, bench: total - starters, charts,
    perChart: Object.fromEntries(charts.map(k => [k, names.reduce((n, r) => n + (fin(r.values[k]) ? r.values[k] : 0), 0)])),
    marketTotal: names.reduce((n, r) => n + (fin(mean(r)) ? mean(r) : 0), 0), count: names.length,
    heldNames: chartKeys.filter(k => !avail.has(k)).map(k => ({usatoday: 'USA Today', fantasycalc: 'FantasyCalc', fantasypros: 'FantasyPros', cbs: 'CBS Sports'}[k]))};
}"""


def close(a, b):
    return abs(a - b) < 0.3   # a hand of players each rounded to 0.1


def check_positions(card, tag) -> list[str]:
    """QB + RB + WR + TE equal the Total in the DDF column."""
    errors = []
    pos = sum(number(card["ddf"]["mine"][p]) or 0 for p in ["QB", "RB", "WR", "TE"])
    total = number(card["ddf"]["mine"]["total"])
    if total is None or not close(pos, total):
        errors.append(tag + f"QB+RB+WR+TE {pos:.1f} != Total {card['ddf']['mine']['total']!r} in DDF Value")
    return errors


def number(text):
    """The numeric part of a cell ("182.0 incomplete" -> 182.0); None when the cell is a dash."""
    t = (text or "").replace("incomplete", "").replace("*", "").strip()
    if not t or t == "—" or t == "n/a":
        return None
    return float(t)


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    page.wait_for_timeout(300)

    card = page.evaluate(CARD)
    if not card:
        return [tag + "the team value summary is not shown with both rosters in"]
    if card["teams"] != ["mine", "theirs"]:
        errors.append(tag + f"team blocks {card['teams']}, want mine then theirs")

    mine = page.evaluate(INDEP, "Mine")
    theirs = page.evaluate(INDEP, "Theirs")
    if not mine["count"] or not theirs["count"]:
        return [tag + f"a roster is empty ({mine['count']}/{theirs['count']}): the check proves nothing"]

    for who, indep in (("mine", mine), ("theirs", theirs)):
        total = number(card["ddf"][who]["total"])
        starters = number(card["ddf"][who]["starters"])
        bench = number(card["ddf"][who]["bench"])
        if total is None or not close(total, indep["total"]):
            errors.append(tag + f"{who} DDF total {card['ddf'][who]['total']!r}, the listed players sum to {indep['total']:.1f}")
        if starters is None or not close(starters, indep["starters"]):
            errors.append(tag + f"{who} DDF starters {card['ddf'][who]['starters']!r}, the best DDF lineup is {indep['starters']:.1f}")
        if starters is not None and bench is not None and not close(starters + bench, indep["total"]):
            errors.append(tag + f"{who} starters + bench != total")
        mkt = number(card["marketTotal"][who])
        if mkt is not None and not close(mkt, indep["marketTotal"]):
            errors.append(tag + f"{who} Trade chart average total {card['marketTotal'][who]!r}, the mean of the charts sums to {indep['marketTotal']:.1f}")
    errors += check_positions(card, tag)

    # The held chart is named, and the compared charts are the columns (never the held one).
    for name in mine["heldNames"] + theirs["heldNames"]:
        if f"{name} not compared" not in card["text"]:
            errors.append(tag + f"the held chart {name} is not named 'not compared'")
    if mine["heldNames"] and not card["held"]:
        errors.append(tag + f"held chart(s) {mine['heldNames']} are not named on the card")
    if mine["charts"] and card["chartColumns"] and sorted(set(card["chartColumns"])) != sorted(mine["charts"]):
        errors.append(tag + f"per-chart columns {sorted(set(card['chartColumns']))}, want {mine['charts']}")

    # "Show each chart" opens the per-chart columns; each Total equals the listed players' sum for that chart.
    page.click("#v2FindTeamSummary .v2-find-ts-charts summary")
    page.wait_for_timeout(150)
    card = page.evaluate(CARD)
    if not card["detailsOpen"]:
        errors.append(tag + "Show each chart did not open the per-chart columns")
    for who, indep in (("mine", mine), ("theirs", theirs)):
        for row in card["chartCells"]:
            if row["team"] != who or row["row"] != "total":
                continue
            for cellv in row["series"]:
                want = indep["perChart"].get(cellv["id"])
                got = number(cellv["text"])
                if want is None or got is None or not close(got, want):
                    errors.append(tag + f"{who} chart {cellv['id']} total {cellv['text']!r}, want {want}")
    page.click("#v2FindTeamSummary .v2-find-ts-charts summary")
    page.wait_for_timeout(100)

    # Phone: the card stacks and the page never scrolls sideways.
    if width <= 479:
        if card["tops"][1] <= card["tops"][0]:
            errors.append(tag + f"the team blocks do not stack on a phone (tops {card['tops']})")
    if page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "the page scrolls sideways with the team summary shown")

    # Changing the league scoring rebuilds the card from the new rows.
    page.evaluate("""() => { window.TradeValueCurveControls.setScoring('standard');
      document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'settings', notes: []}})); }""")
    page.wait_for_timeout(700)
    after = page.evaluate(CARD)
    if not after:
        errors.append(tag + "the team summary disappeared after a league scoring change")
    else:
        mine2 = page.evaluate(INDEP, "Mine")
        got = number(after["ddf"]["mine"]["total"])
        if mine2["count"] and (got is None or not close(got, mine2["total"])):
            errors.append(tag + f"after a league change the DDF total is {after['ddf']['mine']['total']!r}, the new rows sum to {mine2['total']:.1f}")
    return errors


CSS = FINDER_JS.parent / "v2.css"
# The JEG-1246 wrap rules; removing them restores the 1e1bbb5 behaviour Codex saw clip.
PHONE_FIX = """.v2-find-ts-table td.num .v2-find-ts-incomplete { display: inline-flex; flex-wrap: wrap; justify-content: flex-end; align-items: baseline; column-gap: 0.25em; max-width: 100%; }
.v2-find-ts-table td.num .v2-find-ts-incomplete > .v2-find-ts-inc { min-width: 0; white-space: normal; overflow-wrap: anywhere; }
"""

PHONE_MEDIA = """@media (max-width: 479px) {
  .v2-find-ts-team { flex: 1 1 100%; }
  .v2-find-ts-table th, .v2-find-ts-table td { padding: 3px 4px; }
  .v2-find-ts-table th.v2-find-ts-row { width: 30%; }
}"""

CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
CHART_NAMES = {"usatoday": "USA Today", "fantasycalc": "FantasyCalc", "fantasypros": "FantasyPros", "cbs": "CBS Sports"}

# Report only the first n usable charts as available (the rest as held), the way a thin week would.
LIMIT_CHARTS = """(n) => {
  const C = window.TradeValueCurveControls;
  const orig = C.getSourceInfo;
  const keys = %s;
  C.getSourceInfo = (...args) => { let k = 0; return orig(...args).map(i => {
    if (!i.available || !keys.includes(i.key)) return i;
    if (k < n) { k += 1; return i; }
    return {...i, available: false};
  }); };
  return C.getSourceInfo().filter(i => i.available && keys.includes(i.key)).map(i => i.key);
}""" % CHART_KEYS

# The engine rows with one player's DDF Value removed (every chart value kept).
DROP_DDF = """(name) => {
  const C = window.TradeValueCurveControls;
  const orig = C.getAllRows;
  C.getAllRows = (...args) => orig(...args).map(r => (r.name === name ? {...r, values: {...r.values, ddf_value: null}} : r));
  document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'settings', notes: []}}));
}"""

GRID = """(team) => {
  const box = document.getElementById('v2FindTeamSummary');
  if (!box || box.hidden) return null;
  const out = {};
  box.querySelectorAll(`.v2-find-ts-team[data-team=${team}]`).forEach(t => t.querySelectorAll('tr[data-row]').forEach(tr => {
    tr.querySelectorAll('td[data-series]').forEach(td => {
      (out[td.dataset.series] = out[td.dataset.series] || {})[tr.dataset.row] = {text: td.textContent.trim(), unplaced: Boolean(td.querySelector('[data-unplaced]'))};
    });
  }));
  return {cells: out, notes: [...box.querySelectorAll('.v2-find-ts-notes li')].map(li => ({kind: li.dataset.note, text: li.textContent})),
    chartColumns: [...new Set([...box.querySelectorAll('.v2-find-ts-charts thead th[data-series]')].map(th => th.dataset.series))],
    text: box.textContent};
}"""


# One listed player of theirs without a value in one compared chart (DDF and the other charts kept).
DROP_CHART = """([name, key]) => {
  const C = window.TradeValueCurveControls;
  const orig = C.getAllRows;
  C.getAllRows = (...args) => orig(...args).map(r => (r.name === name ? {...r, values: {...r.values, [key]: null}} : r));
  document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'settings', notes: []}}));
}"""

# Every summary cell whose content spills past its own box, and every incomplete warning not shown inside its cell.
OVERFLOW = """() => {
  const box = document.getElementById('v2FindTeamSummary');
  const out = {spill: [], outside: [], wraps: []};
  box.querySelectorAll('td.v2-find-ts-cell').forEach(td => {
    const tr = td.closest('tr'); const team = td.closest('[data-team]');
    const where = `${team && team.dataset.team}/${tr.dataset.row}/${td.dataset.series}`;
    if (td.scrollWidth - td.clientWidth > 1) out.spill.push(`${where} by ${td.scrollWidth - td.clientWidth}px`);
    const cell = td.getBoundingClientRect();
    td.querySelectorAll('.v2-find-ts-incomplete, .v2-find-ts-inc').forEach(n => {
      const r = n.getBoundingClientRect();
      if (r.width < 1 || r.right > cell.right + 1 || r.left < cell.left - 1) out.outside.push(`${where} (${Math.round(r.left)}-${Math.round(r.right)} vs ${Math.round(cell.left)}-${Math.round(cell.right)})`);
    });
  });
  box.querySelectorAll('.v2-find-table-wrap').forEach(w => { if (w.scrollWidth - w.clientWidth > 1) out.wraps.push(w.scrollWidth - w.clientWidth); });
  return out;
}"""


def open_finder(page):
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)


def add_rosters(page):
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    page.wait_for_timeout(300)
    return pick


def check_few_charts(page, tag, width, n) -> list[str]:
    """0, 1 or 2 usable charts: no crash, an honest n/a average, the usable charts only, the rest named."""
    tag = tag + f"[{n} usable charts] "
    errors = []
    open_finder(page)
    kept = page.evaluate(LIMIT_CHARTS, n)
    if len(kept) != n:
        return [tag + f"the fixture has {len(kept)} usable charts after limiting to {n}: the check proves nothing"]
    add_rosters(page)
    grid = page.evaluate(GRID, "mine")
    if not grid:
        return [tag + "the team value summary is not shown with both rosters in"]
    market = grid["cells"].get("market", {})
    if not market or any(c["text"] != "n/a" for c in market.values()):
        errors.append(tag + f"Trade chart average cells {market}, want 'n/a' in every row")
    if not any(note["kind"] == "market" for note in grid["notes"]):
        errors.append(tag + "no note says the Trade chart average has too few charts")
    if sorted(grid["chartColumns"]) != sorted(kept):
        errors.append(tag + f"per-chart columns {grid['chartColumns']}, want the usable charts {kept}")
    if n == 0 and "No trade chart is compared this week." not in grid["text"]:
        errors.append(tag + "no note says no trade chart is compared")
    for key in CHART_KEYS:
        if key not in kept and f"{CHART_NAMES[key]} not compared" not in grid["text"]:
            errors.append(tag + f"{CHART_NAMES[key]} is not named 'not compared'")
    indep = page.evaluate(INDEP, "Mine")
    total = number(grid["cells"].get("ddf", {}).get("total", {}).get("text"))
    if total is None or not close(total, indep["total"]):
        errors.append(tag + f"DDF total {total}, the listed players sum to {indep['total']:.1f}")
    for key in kept:
        got = number(grid["cells"].get(key, {}).get("total", {}).get("text"))
        if got is None or not close(got, indep["perChart"][key]):
            errors.append(tag + f"{key} total {got}, want {indep['perChart'][key]:.1f}")
    if page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "the page scrolls sideways")
    return errors


def check_unplaced(page, tag, width) -> list[str]:
    """A listed starter with no DDF Value but chart values: kept in a No DDF Value row, the splits reconcile."""
    tag = tag + "[no DDF Value] "
    errors = []
    open_finder(page)
    pick = add_rosters(page)
    name = pick["mine"][0]   # the best DDF player: a sure starter before his DDF Value goes
    page.evaluate(DROP_DDF, name)
    page.wait_for_timeout(700)
    grid = page.evaluate(GRID, "mine")
    if not grid:
        return [tag + "the team value summary is not shown"]
    ddf = grid["cells"].get("ddf", {})
    if "unplaced" not in ddf:
        return [tag + f"no No DDF Value row for {name} (rows {list(ddf)})"]
    if number(ddf["unplaced"]["text"]) is not None or "incomplete" not in ddf["unplaced"]["text"]:
        errors.append(tag + f"DDF No DDF Value cell {ddf['unplaced']['text']!r}, want a dash marked incomplete (never 0)")
    if not (ddf["starters"]["unplaced"] and ddf["bench"]["unplaced"]):
        errors.append(tag + "DDF Starters / Bench do not carry the '*' for the unplaced player")
    if not any(note["kind"] == "unplaced" and name in note["text"] for note in grid["notes"]):
        errors.append(tag + f"no note names {name} as having no DDF Value")
    checked = 0
    for sid, cells in grid["cells"].items():
        if sid == "ddf" or cells.get("total", {}).get("text") in (None, "n/a"):
            continue
        parts = [number(cells[r]["text"]) for r in ("starters", "bench", "unplaced")]
        total = number(cells["total"]["text"])
        if None in parts or total is None:
            continue   # a chart that misses someone in these rows is marked incomplete; the sum is checked on the rest
        checked += 1
        if not close(sum(parts), total):
            errors.append(tag + f"{sid}: Starters + Bench + No DDF Value {sum(parts):.1f} != Total {total:.1f}")
    if not checked:
        errors.append(tag + "no market or chart column to reconcile: the check proves nothing")
    if page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "the page scrolls sideways")
    return errors


def check_phone_partial_total(page, tag, width, four=False) -> list[str]:
    """A partial Total in Show each chart stays inside its cell on a phone, the warning word shown."""
    tag = tag + ("[partial total, four charts] " if four else "[partial total] ")
    errors = []
    open_finder(page)
    if four:
        page.evaluate("""() => { const C = window.TradeValueCurveControls; const orig = C.getSourceInfo;
          C.getSourceInfo = (...args) => orig(...args).map(i => (%s.includes(i.key) ? {...i, available: true} : i)); }""" % CHART_KEYS)
    pick = add_rosters(page)
    page.evaluate(DROP_CHART, [pick["theirs"][0], "fantasypros"])
    page.wait_for_timeout(700)
    page.click("#v2FindTeamSummary .v2-find-ts-charts summary")
    page.wait_for_timeout(200)
    grid = page.evaluate(GRID, "theirs")
    if not grid:
        return [tag + "the team value summary is not shown"]
    fp = grid["cells"].get("fantasypros", {}).get("total", {}).get("text") or ""
    if "incomplete" not in fp or number(fp) is None:
        errors.append(tag + f"their FantasyPros Total {fp!r}, want a partial number marked incomplete (the check needs that state)")
    if four and len(grid["chartColumns"]) != 4:
        errors.append(tag + f"chart columns {grid['chartColumns']}, want all four for the stress case")
    out = page.evaluate(OVERFLOW)
    if out["spill"]:
        errors.append(tag + f"cell content spills past its cell: {out['spill'][:4]}")
    if out["outside"]:
        errors.append(tag + f"an incomplete warning is not inside its cell: {out['outside'][:4]}")
    if out["wraps"]:
        errors.append(tag + f"a per-chart table scrolls sideways by {out['wraps']}px")
    if page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "the page scrolls sideways")
    return errors


def run_checks(overrides=None, viewports=((1366, 768), (390, 844), (375, 667)), checker=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in viewports:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page.add_init_script(_render_env.pin_data_week_script())
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    ctype = "text/css" if name.endswith(".css") else "text/javascript"
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#find-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                errors += (checker or check)(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


PHONE_AND_DESKTOP = ((1366, 768), (390, 844))


def few_charts_checker(n):
    return lambda page, tag, width: check_few_charts(page, tag, width, n)


class FinderTeamsRenderTest(unittest.TestCase):
    def test_team_summary(self):
        self.assertEqual(run_checks(), [])

    def test_few_usable_charts(self):
        for n in (0, 1, 2):
            with self.subTest(usable_charts=n):
                self.assertEqual(run_checks(viewports=PHONE_AND_DESKTOP, checker=few_charts_checker(n)), [])

    def test_player_without_ddf_value(self):
        self.assertEqual(run_checks(viewports=PHONE_AND_DESKTOP, checker=check_unplaced), [])

    def test_phone_partial_total_fits(self):
        phones = ((390, 844), (375, 667))
        self.assertEqual(run_checks(viewports=phones, checker=check_phone_partial_total), [])
        self.assertEqual(run_checks(viewports=phones, checker=lambda page, tag, width: check_phone_partial_total(page, tag, width, four=True)), [])

    def test_phone_guard_fails_on_the_old_css(self):
        """JEG-1246: the 1e1bbb5 stylesheet (no wrap for the warning) clips the partial Total at 390 and is caught."""
        css = CSS.read_text(encoding="utf-8")
        old = css.replace(PHONE_FIX, "", 1).replace(PHONE_MEDIA, "@media (max-width: 479px) { .v2-find-ts-team { flex: 1 1 100%; } }", 1)
        self.assertEqual(len(css) - len(old), len(PHONE_FIX) + len(PHONE_MEDIA) - 66, "the phone fix anchors in v2.css are stale")
        errors = run_checks({"v2.css": old}, viewports=((390, 844),), checker=check_phone_partial_total)
        self.assertNotEqual(errors, [], "the clipped partial Total is not caught")

    def test_correction_guards_fail_on_broken_builds(self):
        """JEG-1246: the 7d84cdb9 crash and a dropped No DDF Value partition are each caught."""
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "the average's cells read before the unavailable guard": (js.replace(
                'if (series.available === false || !series.cells) return el("span", {class: "v2-find-ts-num is-unavailable"',
                'if (series.cells[name] && series.available === false) return el("span", {class: "v2-find-ts-num is-unavailable"', 1),
                few_charts_checker(2)),
            "the unplaced player dropped from the split": (js.replace("unplaced: picked.unvalued, total:", "unplaced: [], total:", 1), check_unplaced),
            "the No DDF Value row never listed": (js.replace(
                'rows: SUMMARY_ROWS.filter(name => name !== "unplaced" || unplaced.length)', 'rows: SUMMARY_ROWS.filter(name => name !== "unplaced")', 1), check_unplaced),
        }
        for name, (body, checker) in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                try:
                    errors = run_checks({"finder.js": body}, viewports=((1366, 768),), checker=checker)
                except Exception as exc:
                    errors = [str(exc)[:80]]
                self.assertNotEqual(errors, [], f"not caught: {name}")

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "the two teams' numbers swapped": js.replace(
                'el("div", {class: "v2-find-ts-grid"}, tsBlock(mine, "Your team", ["ddf", "market"], "mine"), tsBlock(theirs, "Their team", ["ddf", "market"], "theirs"))',
                'el("div", {class: "v2-find-ts-grid"}, tsBlock(theirs, "Your team", ["ddf", "market"], "mine"), tsBlock(mine, "Their team", ["ddf", "market"], "theirs"))', 1),
            "the held chart left unnamed": js.replace('if (held.length) notes.append(el("li", {"data-note": "held",', 'if (false) notes.append(el("li", {"data-note": "held",', 1),
            "the card not rebuilt on a league change": js.replace("const say = reprocessRosters(asks);\n    renderBoth();", "const say = reprocessRosters(asks);", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                try:
                    errors = run_checks({"finder.js": body}, viewports=((1366, 768),))
                except Exception as exc:
                    errors = [str(exc)[:80]]
                self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
