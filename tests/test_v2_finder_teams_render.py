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


def run_checks(overrides=None, viewports=((1366, 768), (390, 844), (375, 667))) -> list[str]:
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
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class FinderTeamsRenderTest(unittest.TestCase):
    def test_team_summary(self):
        self.assertEqual(run_checks(), [])

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
