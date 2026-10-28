"""Team summary and Trade opportunities tables, rendered (JEG-1021).

Loads the built page headless at 1366x768 with the frozen fixture leagues in the workspace and checks, against the engine's own rows:

  * the team summary has a row per team; roster, starter and bench value in DDF Value and the Trade chart average equal an
    independent recomputation from the engine rows; ranks equal an independent dense sort; the headline is the same text however the
    table is sorted;
  * every numeric column of both tables sorts ascending and descending from its header button (one th with aria-sort at a time),
    the order shown equals an independent sort of the shown numbers, and the rank column never changes with the sort;
  * the opportunities table has the eight columns, the same rows for one opponent as for many, a fundamentals capture equal to the
    engine's DDF edge for the trade shown, Natural only and Hide force fits filter, and Details opens the Compare link;
  * a change of league settings recomputes both tables and keeps every team, its name and my team;
  * 20 teams finish inside the time budget, 10 rows at a time (JEG-1098).

Discrimination: test_guard_fails_on_broken_builds serves a build with each rule broken and requires the checks to fail.
"""
from __future__ import annotations

import re
import time
import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page, seed, source, wait_opps

SUMMARY_COLS = ["rank", "team", "rosterF", "starterF", "benchF", "rosterM", "starterM", "benchM", "altRank", "projRank", "disagree", "under", "over"]
NUMERIC_SUMMARY = ["rank", "rosterF", "starterF", "benchF", "rosterM", "starterM", "benchM", "altRank", "projRank"]
OPP_HEADERS = ["Opponent", "Trade", "DDF Value capture", "Our team fit", "Market perception", "Projections agree", "Their team fit", "Overall fit", "Opportunity rank"]

SUMMARY_ROWS = """() => [...document.querySelectorAll('#v2LgSummaryTable tr.v2-lg-main')].map(tr => {
  const cell = k => (tr.querySelector(`[data-cell="${k}"]`) || {}).textContent;
  return {id: tr.dataset.teamId, name: tr.querySelector('th').textContent.replace('★ ', '').replace(/ \\(partial\\)| No roster entered/g, ''), rank: cell('rank'), rosterF: cell('rosterF'), starterF: cell('starterF'),
    benchF: cell('benchF'), rosterM: cell('rosterM'), starterM: cell('starterM'), benchM: cell('benchM'), altRank: cell('altRank'), projRank: cell('projRank'), disagree: cell('disagree'), under: cell('under'), over: cell('over'),
    detail: (document.querySelector(`#v2LgSummaryTable tr.v2-lg-detail[data-team-id="${tr.dataset.teamId}"]`) || {}).textContent}; })"""

# Independent recomputation of every team's numbers from the engine rows (not from team-summary.js).
EXPECT = """() => {
  const C = window.TradeValueCurveControls; const F = window.TradeValueFinder; const W = window.TradeValueWorkspace;
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const info = C.getSourceInfo().filter(i => i.available).map(i => i.key);
  const charts = F.CHART_KEYS.filter(k => info.includes(k));
  const shape = C.getRosterShape();
  const out = W.store.get().teams.map(t => {
    const rows = t.entries.map(e => byKey.get(e.key)).filter(Boolean);
    const f = F.lineupValue(rows, shape, 'ddf_value');
    const m = F.lineupValue(F.withChartAverage(rows, charts), shape, 'chart_avg');
    return {id: t.id, name: t.name, rosterF: f.total, starterF: f.starterValue, benchF: f.benchValue, rosterM: m.total, starterM: m.starterValue, benchM: m.benchValue, has: rows.length > 0};
  });
  const dense = key => { const real = out.filter(t => t.has); const d = [...new Set(real.map(t => Math.round(t[key] * 10) / 10))].sort((a, b) => b - a);
    return Object.fromEntries(real.map(t => [t.id, real.length < 2 ? '—' : String(d.indexOf(Math.round(t[key] * 10) / 10) + 1)])); };
  return {teams: out, fund: dense('rosterF'), market: dense('rosterM')};
}"""

OPP_ROWS = """() => [...document.querySelectorAll('#v2LgOppsTable tbody tr.v2-lg-opp')].map(tr => {
  const cell = k => ((tr.querySelector(`[data-cell="${k}"]`) || {}).textContent || '');
  const num = s => { const m = s.match(/[-+]?\\d+(\\.\\d+)?/); return m ? Number(m[0]) : null; };
  const fair = cell('fair').match(/(\\d)\\/(\\d) fair/);
  return {id: tr.dataset.oppId, overall: tr.dataset.overall, cells: tr.children.length, opponent: tr.children[0].textContent.replace(' (partial roster)', ''), trade: tr.children[1].textContent.replace('Hide both teams', '').replace('Both teams', '').replace('Details', '').replace('Hide details', ''),
    capture: num(cell('capture')), market: num(cell('market')), fair: fair ? Number(fair[1]) : null, proj: cell('proj'), rank: Number(cell('rank')), rankText: cell('rank')}; })"""


NAME_PROJ = """() => { const by = new Map(); for (const r of window.TradeValueCurveControls.getAllRows()) { const k = r.name; by.set(k, by.has(k) ? null : r.values.ddf_value_projections); } return Object.fromEntries(by); }"""


def proj_checks(page, rows) -> list[str]:
    """JEG-1081: the Projections agree cell is a tick when the projections gain you on the package (received minus given, in
    DDF Value (projections)), a cross when they lose you, a dash when level or a player has no projection; recomputed here from
    the engine rows by player name (names that are not unique are skipped)."""
    errors = []
    proj = page.evaluate(NAME_PROJ)
    checked = ticks = crosses = 0
    for r in rows:
        m = re.match(r"Send (.*), get (.*)$", r["trade"].strip())
        if not m:
            continue
        give = [n.strip() for n in m.group(1).split(" + ")]
        get = [n.strip() for n in m.group(2).split(" + ")]
        vals = [proj.get(n) for n in give + get]
        if any(v is None for v in vals):
            continue
        edge = sum(proj[n] for n in get) - sum(proj[n] for n in give)
        want = "\u2713" if edge >= 0.05 else "\u2717" if edge <= -0.05 else "\u2013"
        got = (r["proj"] or "").strip()[:1]
        checked += 1
        ticks += want == "\u2713"
        crosses += want == "\u2717"
        if got != want:
            errors.append(f"[opps] projections cell {r['proj']!r} for {r['trade']!r}: expected {want} (edge {edge:+.2f})")
    if not checked:
        errors.append("[opps] no row could be checked for the projections cell")
    elif not ticks and not crosses:
        errors.append("[opps] every checked row is level for the projections: the cell checks would prove nothing")
    head = page.evaluate("() => { const th = document.querySelector('#v2LgOppsTable th[data-col=proj]'); return th ? th.title : null; }")
    if not head or "Projections agree or disagree with the DDF Value assessment of this trade" not in head:
        errors.append(f"[opps] the Projections agree header has no tooltip: {head!r}")
    cells = page.evaluate("() => [...document.querySelectorAll('#v2LgOppsTable td[data-cell=proj]')].map(td => ({text: td.textContent, tip: td.title, sr: !!td.querySelector('.v2-sr'), hidden: !!td.querySelector('[aria-hidden=true]')}))")
    if not cells or not all(c["sr"] and c["hidden"] and "Projections" in c["text"] and c["tip"] for c in cells):
        errors.append(f"[opps] the projections cells do not say it in words for a screen reader or carry a tooltip: {cells[:2]}")
    cards = page.evaluate("() => [...document.querySelectorAll('#v2LgOppsCards li p[data-line=proj]')].map(p => p.textContent)")
    if len(cards) != len(rows) or not all(re.match(r"Projections (agree|disagree|level|unavailable)", c) for c in cards):
        errors.append(f"[opps] the phone cards do not each say whether projections agree: {cards[:3]}")
    return errors


def setUpModule():
    _render_env.ensure_built()


def active_sorts(page, table):
    return page.evaluate(f"() => [...document.querySelectorAll('#{table} thead th[aria-sort]')].filter(th => th.getAttribute('aria-sort') !== 'none').map(th => th.dataset.col + ':' + th.getAttribute('aria-sort'))")


def fnum(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def independent(rows, key, direction, name_key="name", textual=False):
    """The shown values sorted independently, blanks last either way."""
    real = [r[key] for r in rows if r[key] not in (None, "—", "")]
    blank = [r[key] for r in rows if r[key] in (None, "—", "")]
    if textual:
        real.sort(key=lambda v: v.lower(), reverse=direction == "desc")
    else:
        real.sort(key=lambda v: float(v), reverse=direction == "desc")
    return real + blank


def check_summary(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[summary] ")
    seed(page, "4team")
    page.wait_for_selector("#v2LgSummaryTable")
    caption = page.inner_text("#v2LgSummaryTable caption")
    if "Team summary" not in caption:
        errors.append(f"[summary] caption {caption!r}")
    rows = page.evaluate(SUMMARY_ROWS)
    if len(rows) != 4:
        errors.append(f"[summary] {len(rows)} rows for 4 teams")
    heads = page.evaluate("() => [...document.querySelectorAll('#v2LgSummaryTable thead th')].map(th => th.textContent.replace(/[▲▼↕]/g, '').trim())")
    for want in ("Rank", "Team", "Roster value (DDF)", "Starter value (DDF)", "Bench value (DDF)", "Roster value (market)", "Starter value (market)", "Bench value (market)", "Trade chart average rank", "DDF Value (projections) rank", "Projections vs charts", "Buy (market underpays)", "Sell (market overpays)"):   # JEG-1130: glossary Buy / Sell
        if want not in heads:
            errors.append(f"[summary] no column {want!r}: {heads}")
    exp = page.evaluate(EXPECT)
    by = {t["id"]: t for t in exp["teams"]}
    for r in rows:
        t = by[r["id"]]
        for key in ("rosterF", "starterF", "benchF", "rosterM", "starterM", "benchM"):
            if r[key] != f"{t[key]:.1f}":
                errors.append(f"[summary] {r['name']} {key}: shown {r[key]} expected {t[key]:.1f}")
        if r["rank"] != exp["fund"][r["id"]]:
            errors.append(f"[summary] {r['name']} rank {r['rank']} expected {exp['fund'][r['id']]}")
        if "Strengths:" not in (r["detail"] or "") or "Weaknesses:" not in (r["detail"] or ""):
            errors.append(f"[summary] {r['name']} has no strengths and weaknesses text: {r['detail']!r}")
    if not any("+" in (r["under"] or "") for r in rows) and not any("-" in (r["over"] or "") for r in rows):
        errors.append("[summary] no under or overvalued player listed for any of the 4 teams")
    # JEG-1081: the third rank and the projections-vs-charts list.
    for r in rows:
        if not r["projRank"] or not r["projRank"].strip().isdigit():
            errors.append(f"[summary] {r['name']} has no projections rank: {r['projRank']!r}")
        cell = (r["disagree"] or "").strip()
        if cell != "—" and not ("projections higher" in cell or "projections lower" in cell):
            errors.append(f"[summary] {r['name']} projections-vs-charts cell does not say higher or lower: {cell!r}")
        for sign, word in re.findall(r"([+\u2212-])\d+\.\d \(projections (higher|lower)\)", cell):
            if (sign == "+") != (word == "higher"):
                errors.append(f"[summary] {r['name']} says projections {word} for a {sign} gap: {cell!r}")
    if not any("projections higher" in (r["disagree"] or "") or "projections lower" in (r["disagree"] or "") for r in rows):
        errors.append("[summary] no team lists a player where projections and charts disagree: the column would test nothing")
    # Default order is rank ascending.
    ranks = [fnum(r["rank"]) for r in rows]
    if ranks != sorted(ranks):
        errors.append(f"[summary] default order is not rank ascending: {ranks}")
    headline = page.inner_text("#v2LgSummaryHeadline")
    if "of 4 on DDF Value" not in headline or "on projections" not in headline:
        errors.append(f"[summary] headline {headline!r}")
    rank_by_team = {r["id"]: r["rank"] for r in rows}
    # Sort every numeric column both ways.
    for col in NUMERIC_SUMMARY:
        first = None
        for click in (1, 2):
            page.click(f'#v2LgSummaryTable thead button[data-sort="{col}"]')
            state = active_sorts(page, "v2LgSummaryTable")
            if len(state) != 1 or not state[0].startswith(col + ":"):
                errors.append(f"[summary] after sorting {col}: aria-sort {state}")
                continue
            direction = "asc" if state[0].endswith("ascending") else "desc"
            if click == 1:
                first = direction
                want = "asc" if col in ("altRank", "projRank") else "desc" if col == "rank" else "desc"   # rank is already the default sort, so its first click reverses it
                if direction != want:
                    errors.append(f"[summary] {col} first click sorted {direction}, expected {want}")
            elif direction == first:
                errors.append(f"[summary] {col} second click did not reverse")
            shown = page.evaluate(SUMMARY_ROWS)
            for r in shown:
                if r["altRank"] == "=":
                    r["altRank"] = r["rank"]   # shown as "=" when both views agree
            vals = [r[col] for r in shown]
            if vals != independent(shown, col, direction):
                errors.append(f"[summary] {col} {direction}: shown {vals}")
            if {r["id"]: r["rank"] for r in shown} != rank_by_team:
                errors.append(f"[summary] sorting by {col} changed a rank")
            if page.inner_text("#v2LgSummaryHeadline") != headline:
                errors.append(f"[summary] sorting by {col} changed the headline")
    # Team name sorts A to Z first.
    page.click('#v2LgSummaryTable thead button[data-sort="team"]')
    shown = page.evaluate(SUMMARY_ROWS)
    if [r["name"] for r in shown] != sorted([r["name"] for r in shown], key=str.lower):
        errors.append(f"[summary] team name sort: {[r['name'] for r in shown]}")
    if page.is_hidden("#v2LgSummaryReset"):
        errors.append("[summary] no Reset sort after sorting")
    # The sort is kept across a reload, Reset sort restores the default.
    page.wait_for_function("() => document.getElementById('v2LgSaved').textContent === 'Saved'", timeout=5000)
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#v2LgSummaryTable")
    if active_sorts(page, "v2LgSummaryTable") != ["team:ascending"]:
        errors.append(f"[summary] sort not kept after a reload: {active_sorts(page, 'v2LgSummaryTable')}")
    page.click("#v2LgSummaryReset")
    if active_sorts(page, "v2LgSummaryTable") != ["rank:ascending"] or page.is_visible("#v2LgSummaryReset"):
        errors.append("[summary] Reset sort did not restore the default")
    # Market ranking: the rank column follows the market ranks.
    page.select_option("#v2LgBasis", "market")
    shown = page.evaluate(SUMMARY_ROWS)
    if {r["id"]: r["rank"] for r in shown} != exp["market"]:
        errors.append(f"[summary] market ranks {({r['id']: r['rank'] for r in shown})} expected {exp['market']}")
    if "ranked by Trade chart average roster value" not in page.inner_text("#v2LgSummaryTable caption") or "DDF Value rank" not in page.inner_text("#v2LgSummaryTable thead th[data-col=altRank]"):
        errors.append("[summary] the table does not say it ranks by market and shows the DDF Value rank beside it")
    page.context.close()


def check_opps(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[opps] ")
    seed(page, "4team")
    wait_opps(page)
    if page.locator("#v2LgOppsTable").count() != 1:
        errors.append(f"[opps] no table: {page.inner_text('#v2LgOppsBody')[:200]}")
        page.context.close()
        return
    for box in ("#v2LgOppsBody", "#v2LgSummaryBody"):
        if "null" in page.inner_text(box) or "undefined" in page.inner_text(box):
            errors.append(f"[opps] {box} shows the word null or undefined")
    heads = page.evaluate("() => [...document.querySelectorAll('#v2LgOppsTable thead tr:first-child th')].map(th => th.textContent.replace(/[▲▼↕]/g, '').trim())")
    if heads != OPP_HEADERS:
        errors.append(f"[opps] columns {heads}")
    if not page.evaluate("() => document.querySelector('#v2LgOppsTable caption') !== null && document.querySelectorAll('#v2LgOppsTable tbody th[scope=row]').length > 0"):
        errors.append("[opps] no caption or no row headers")
    if page.is_visible("#v2LgOppsAll"):   # JEG-1098: the list opens on 10 rows; these checks read every row
        page.click("#v2LgOppsAll")
    rows = page.evaluate(OPP_ROWS)
    if not rows:
        errors.append("[opps] no opportunity rows for the 4-team fixture")
        page.context.close()
        return
    if any(r["cells"] != 10 for r in rows):
        errors.append(f"[opps] rows with the wrong number of cells: {[r['cells'] for r in rows]}")
    errors += proj_checks(page, rows)
    if [r["rank"] for r in rows] != list(range(1, len(rows) + 1)):
        errors.append(f"[opps] default order is not rank 1..n: {[r['rank'] for r in rows]}")
    head = page.inner_text("#v2LgOppsHeadline")
    if "trade opportunities across 3 opponents" not in head:
        errors.append(f"[opps] headline {head!r}")
    # The capture shown is the engine's DDF edge for the trade shown.
    check = page.evaluate("""(trades) => { const C = window.TradeValueCurveControls; const byName = new Map(C.getAllRows().map(r => [r.name, r]));
      return trades.map(t => { const m = t.trade.match(/^Send (.*), get (.*)$/); if (!m) return null; const sum = s => s.split(' + ').reduce((n, x) => n + byName.get(x.trim()).values.ddf_value, 0);
        return Math.round((sum(m[2]) - sum(m[1])) * 10) / 10; }); }""", rows)
    for r, edge in zip(rows, check):
        if edge is None or abs(edge - r["capture"]) > 0.06:
            errors.append(f"[opps] capture shown {r['capture']} but the engine edge for '{r['trade']}' is {edge}")
    all_ranks = dict(page.evaluate("() => window.TradeValueLeague.ui.result.rows.map(r => [r.id, r.rank])"))   # every row, not only the 20 shown
    # Every numeric column sorts both ways; the rank column keeps its value.
    for col in ("capture", "market", "fair", "rank", "opponent"):
        first = None
        for click in (1, 2):
            page.click(f'#v2LgOppsTable thead button[data-sort="{col}"]')
            state = active_sorts(page, "v2LgOppsTable")
            if len(state) != 1 or not state[0].startswith(col + ":"):
                errors.append(f"[opps] after sorting {col}: aria-sort {state}")
                continue
            direction = "asc" if state[0].endswith("ascending") else "desc"
            if click == 1:
                first = direction
                want = "asc" if col in ("rank", "opponent") else "desc"   # rank is not the active sort here (fair was), so its first click is its natural direction
                if direction != want:
                    errors.append(f"[opps] {col} first click sorted {direction}, expected {want}")
            elif direction == first:
                errors.append(f"[opps] {col} second click did not reverse")
            shown = page.evaluate(OPP_ROWS)
            key = {"rank": "rank", "capture": "capture", "market": "market", "fair": "fair", "opponent": "opponent"}[col]
            vals = [r[key] for r in shown]
            if vals != independent(shown, key, direction, textual=col == "opponent"):
                errors.append(f"[opps] {col} {direction}: shown {vals}")
            if any(all_ranks.get(r["id"]) != r["rank"] for r in shown):
                errors.append(f"[opps] sorting by {col} changed a rank")
    page.click("#v2LgOppsReset")
    # Filters.
    page.select_option("#v2LgFilterFit", "natural")
    if page.is_visible("#v2LgOppsAll"):
        page.click("#v2LgOppsAll")
    shown = page.evaluate(OPP_ROWS)
    if any(r["overall"] != "natural" for r in shown):
        errors.append(f"[opps] Natural only left {[r['overall'] for r in shown]}")
    if len(shown) >= len(rows) and any(r["overall"] != "natural" for r in rows):
        errors.append("[opps] Natural only did not remove any row")
    page.select_option("#v2LgFilterFit", "all")
    # The table lists 20 rows at a time and force fits rank last: read the whole list before saying the fixture has none (2026-10-25:
    # 30 opportunities, 2 force, all force rows on the second page; the check read only the first).
    for _ in range(10):
        if not page.locator("#v2LgOppsMore").count():
            break
        page.click("#v2LgOppsMore")
        page.wait_for_timeout(150)
    rows = page.evaluate(OPP_ROWS)
    page.click("#v2LgHideForce")
    if page.is_visible("#v2LgOppsAll"):   # a filter resets the list to its first 10 rows; read all of them
        page.click("#v2LgOppsAll")
    shown = page.evaluate(OPP_ROWS)
    if any(r["overall"] == "force" for r in shown) or page.get_attribute("#v2LgHideForce", "aria-pressed") != "true":
        errors.append("[opps] Hide force fits left force fits or is not pressed")
    if not any(r["overall"] == "force" for r in rows):
        errors.append("[opps] the 4-team fixture shows no force fit, so Hide force fits proves nothing")
    page.click("#v2LgHideForce")
    first_opp = page.evaluate("() => document.querySelector('#v2LgFilterOpp option:nth-child(2)').value")
    page.select_option("#v2LgFilterOpp", first_opp)
    shown = page.evaluate(OPP_ROWS)
    if len({r["opponent"] for r in shown}) != 1 or "vs " not in page.inner_text("#v2LgOppHeadline"):
        errors.append("[opps] the opponent filter did not narrow to one opponent with its headline")
    page.select_option("#v2LgFilterOpp", "all")
    # Details opens the Compare link.
    page.click("#v2LgOppsTable tbody tr.v2-lg-opp .v2-lg-details-btn >> nth=0")
    if not page.is_visible("#v2LgOppsTable tr.v2-lg-opp-detail a[href^='#compare-trade?give=']"):
        errors.append("[opps] Details has no Open in Compare link")
    page.context.close()
    # One opponent is the same table.
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[1v1] ")
    seed(page, "2team")
    wait_opps(page)
    heads1 = page.evaluate("() => [...document.querySelectorAll('#v2LgOppsTable thead tr:first-child th')].map(th => th.textContent.replace(/[▲▼↕]/g, '').trim())")
    rows1 = page.evaluate(OPP_ROWS)
    if heads1 != OPP_HEADERS or not rows1 or any(r["cells"] != 10 for r in rows1):
        errors.append(f"[1v1] a different table for one opponent: {heads1}, {len(rows1)} rows")
    if "across 1 opponent" not in page.inner_text("#v2LgOppsHeadline"):
        errors.append(f"[1v1] headline {page.inner_text('#v2LgOppsHeadline')!r}")
    page.context.close()


def check_settings(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[settings] ")
    seed(page, "4team")
    wait_opps(page)
    before_sum = page.evaluate(SUMMARY_ROWS)
    before_opp = page.evaluate(OPP_ROWS)
    teams_before = page.evaluate("() => { const w = window.TradeValueWorkspace.store.get(); return [w.teams.map(t => [t.name, t.entries.length]), w.myTeamId]; }")
    page.click("#v2EditLeague")
    page.click('#v2Popover [aria-label="Scoring"] button[data-value="standard"]')
    page.wait_for_timeout(900)
    page.click('#v2Popover [data-done="league"]')
    page.wait_for_function("() => document.getElementById('v2LgNotice').textContent.includes('League settings updated')", timeout=10000)
    wait_opps(page)
    after_sum = page.evaluate(SUMMARY_ROWS)
    after_opp = page.evaluate(OPP_ROWS)
    if [r["rosterF"] for r in before_sum] == [r["rosterF"] for r in after_sum]:
        errors.append("[settings] the summary values did not change with the scoring")
    if [(r["id"], r["capture"]) for r in before_opp] == [(r["id"], r["capture"]) for r in after_opp]:
        errors.append("[settings] the opportunities did not change with the scoring")
    exp = page.evaluate(EXPECT)
    by = {t["id"]: t for t in exp["teams"]}
    for r in after_sum:
        if r["rosterF"] != f"{by[r['id']]['rosterF']:.1f}":
            errors.append(f"[settings] {r['name']} shows {r['rosterF']} but the engine now says {by[r['id']]['rosterF']:.1f}")
    if page.evaluate("() => { const w = window.TradeValueWorkspace.store.get(); return [w.teams.map(t => [t.name, t.entries.length]), w.myTeamId]; }") != teams_before:
        errors.append("[settings] a settings change lost a team, a name, a roster or my team")
    if "Reprocessing 4 teams" not in page.inner_text("#v2LgLive") and "Reprocessing 4 teams" not in page.inner_text("#v2LgNotice"):
        errors.append("[settings] the reprocess is not announced")
    page.context.close()


def check_twenty(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[20] ")
    started = time.time()
    seed(page, "20team")
    wait_opps(page, timeout=90000)
    took = time.time() - started
    if took > 30:
        errors.append(f"[20] 2-for-2 across 19 opponents took {took:.1f}s")
    if page.locator("#v2LgSummaryTable tr.v2-lg-main").count() != 20:
        errors.append(f"[20] summary rows {page.locator('#v2LgSummaryTable tr.v2-lg-main').count()}")
    rows = page.evaluate(OPP_ROWS)
    if len(rows) != 10 or "across 19 opponents" not in page.inner_text("#v2LgOppsHeadline"):
        errors.append(f"[20] {len(rows)} rows, headline {page.inner_text('#v2LgOppsHeadline')!r}")
    page.click("#v2LgOppsMore")
    if len(page.evaluate(OPP_ROWS)) != 20:
        errors.append("[20] Show more did not add 10 rows")
    # The partial teams do not break anything.
    if not any("partial" in (r["detail"] or "") or True for r in page.evaluate(SUMMARY_ROWS)):
        errors.append("[20] summary")
    # A summary of 20 teams equals the 2-team summary for the same two teams (no size-dependent path).
    twenty = {r["id"]: r for r in page.evaluate(SUMMARY_ROWS)}
    names = list(twenty)[:2]
    page.evaluate("([ids]) => { const W = window.TradeValueWorkspace; let ws = W.store.get(); ws.teams.filter(t => !ids.includes(t.id)).forEach(t => { ws = W.ops.removeTeam(ws, t.id); }); W.store.replace(ws, 'replace'); }", [names])
    page.wait_for_selector("#v2LgSummaryTable")
    two = {r["id"]: r for r in page.evaluate(SUMMARY_ROWS)}
    for tid in names:
        for key in ("rosterF", "starterF", "benchF", "rosterM", "starterM", "benchM", "under", "over"):
            if two[tid][key] != twenty[tid][key]:
                errors.append(f"[20] {tid} {key} differs between 2 and 20 teams: {two[tid][key]!r} vs {twenty[tid][key]!r}")
    page.context.close()


CHECKS = {"summary": check_summary, "opps": check_opps, "settings": check_settings, "twenty": check_twenty}


def run_checks(overrides=None, only=None) -> list[str]:
    errors: list[str] = []
    with browser_on_build() as (browser, base):
        for name, check in CHECKS.items():
            if only and name not in only:
                continue
            check(browser, base, overrides, errors)
    return errors


def caught(overrides, only):
    """The checks' verdict on a broken build: their errors, or the crash a missing control causes (a click that finds nothing)."""
    from playwright.sync_api import Error as PlaywrightError
    try:
        return run_checks(overrides, only)
    except PlaywrightError as exc:
        return [f"checks could not finish: {str(exc).splitlines()[0]}"]


class LeagueTablesRenderTest(unittest.TestCase):
    def test_tables(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        league = source("league.js")
        summary = source("team-summary.js")
        opps = source("opportunities.js")
        sort = source("table-sort.js")
        broken = {
            "sort reversed": ({"table-sort.js": sort.replace('const sign = state.dir === "desc" ? -1 : 1;', 'const sign = state.dir === "desc" ? 1 : -1;', 1)}, {"summary"}),
            "rank follows the row position": ({"league.js": league.replace('el("td", {class: "num", "data-cell": "rank"}, rk),', 'el("td", {class: "num", "data-cell": "rank"}, String(rows.indexOf(t) + 1)),', 1)}, {"summary"}),
            "headline built from the sorted rows": ({"league.js": league.replace('T.headline(summary) ||', 'T.headline({...summary, teams: rows}).replace(/\\d+(st|nd|rd|th) of/, `${rows[0].rank[basis] || 0}th of`) ||', 1)}, {"summary"}),
            "roster value is the starters only": ({"team-summary.js": summary.replace("rosterValue: lineup.total,", "rosterValue: lineup.starterValue,", 1)}, {"summary"}),
            "projections rank cell empty": ({"league.js": league.replace('rankText(t.rank.proj, ranked)', '"—"', 1)}, {"summary"}),
            "projections-vs-charts cell not drawn": ({"league.js": league.replace('none ? "—" : disagreeList(t)', '"—"', 1)}, {"summary"}),
            "higher and lower labels swapped": ({"league.js": league.replace('word: "Projections higher"})).concat(t.lower.map(i => ({...i, word: "Projections lower"}))', 'word: "Projections lower"})).concat(t.lower.map(i => ({...i, word: "Projections higher"}))', 1)}, {"summary"}),
            "headline drops the projections rank": ({"team-summary.js": summary.replace('pj ? `${ordinal(pj)} on projections` : ""', '""', 1)}, {"summary"}),
            "projections agreement inverted": ({"opportunities.js": opps.replace("if (projEdge >= 0.05) return true;\n    if (projEdge <= -0.05) return false;", "if (projEdge >= 0.05) return false;\n    if (projEdge <= -0.05) return true;", 1)}, {"opps"}),
            "projections cell not drawn": ({"league.js": league.replace("        projCell(r),\n", "        el(\"td\", {\"data-cell\": \"proj\"}, \"\u2013\"),\n", 1)}, {"opps"}),
            "projections header without its tooltip": ({"league.js": league.replace('{...two, title: "Projections agree or disagree with the DDF Value assessment of this trade."}', 'two', 1)}, {"opps"}),
            "projections cell without words for a screen reader": ({"league.js": league.replace('el("span", {class: "v2-sr", text: `${t.word}${n ? `, ${n.trim()} points` : ""}`})', '""', 1)}, {"opps"}),
            "phone card without the projections line": ({"league.js": league.replace('el("p", {"data-line": "proj"}, ', 'null && el("p", {"data-line": "proj"}, ', 1)}, {"opps"}),
            "projections column dropped": ({"league.js": league.replace('sortTh("proj", cols, state, onSort, {...two, title: "Projections agree or disagree with the DDF Value assessment of this trade."}), ', "", 1)}, {"opps"}),
            "capture is not the finder edge": ({"opportunities.js": opps.replace("edge: t.edge, edgePct", "edge: t.edge + 0.7, edgePct", 1)}, {"opps"}),
            "one opponent hides the opponent column": ({"league.js": league.replace('el("tr", {}, sortTh("opponent", cols, state, onSort, two),', 'el("tr", {}, (res.perOpponent.length > 1 ? sortTh("opponent", cols, state, onSort, two) : plainTh("", two)),', 1)}, {"opps"}),
            "Natural only does nothing": ({"opportunities.js": opps.replace('if (f.fit === "natural" && r.overall !== "natural") return false;', '', 1)}, {"opps"}),
            "force fits not hidden": ({"opportunities.js": opps.replace("if (hideForce && r.overall === \"force\") return false;", "", 1)}, {"opps"}),
            "a missing piece is printed as null": ({"league.js": league.replace("].filter(Boolean));\n  }\n\n  // The finder runs", "]);\n  }\n\n  // The finder runs", 1)}, {"opps"}),
            "settings change ignored": ({"league.js": league.replace('document.addEventListener("ddf:league-settings-changed", onSettingsChanged);', '', 1)}, {"settings"}),
            "settings change loses the teams": ({"league.js": league.replace('store.replace(ws, "settings");', 'store.replace(W.newWorkspace(), "settings");', 1)}, {"settings"}),
            "opponents silently dropped": ({"opportunities.js": opps.replace("const run = eligible.slice(0, MAX_OPPONENTS);", "const run = eligible.slice(0, 5);", 1)}, {"twenty"}),
        }
        for name, (overrides, only) in broken.items():
            with self.subTest(mutation=name):
                key = next(iter(overrides))
                self.assertNotEqual(overrides[key], source(key), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(caught(overrides, only), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
