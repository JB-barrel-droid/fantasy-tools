"""v2 Find a trade, roster impact on each group card (JEG-972 commit 3), rendered. Display only.

Two rosters typed in, 2-for-2, Find trades. On each of the first group cards, for You and They, in DDF Value and in
the Trade chart average, the card shows the best starting lineup before and after and the change. Checked at 1366x768,
390 and 320 wide against an independent greedy lineup computed in the page from getAllRows:

  * "You" is the roster that gives the package and receives the target; "They" the reverse (sides not swapped);
  * the market view is the mean of the available compared charts, not DDF Value;
  * toggling a side player recomputes both teams' numbers;
  * "Show lineup details" opens slot tables (before, after, change, starters and bench); closed by default;
  * the roster assessment table for both teams sits above the groups;
  * no sideways scroll, no page errors.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the two teams' packages swapped, the market view
reading DDF Value, and the numbers not updating after a toggle, and requires each to fail.
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


EXPECT = """(i) => {
  const C = window.TradeValueCurveControls;
  const shape = C.getRosterShape();
  const rows = C.getAllRows();
  const byName = new Map(rows.map(r => [r.name, r]));
  const avail = new Set(C.getSourceInfo().filter(s => s.available).map(s => s.key));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => avail.has(k));
  const mean = r => { const v = charts.map(k => r.values[k]); return v.every(Number.isFinite) ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const val = (r, view) => (view === 'ddf' ? r.values.ddf_value : mean(r));
  const best = (team, view) => {
    const v = team.filter(r => Number.isFinite(val(r, view))).sort((a, b) => val(b, view) - val(a, view) || String(a.player_key).localeCompare(String(b.player_key)));
    const used = new Set(); let total = 0;
    const take = (n, pos) => { for (let k = 0; k < n; k++) { const r = v.find(x => !used.has(x) && pos.includes(x.pos)); if (r) { used.add(r); total += val(r, view); } } };
    ['QB', 'RB', 'WR', 'TE'].forEach(p => take(shape[p] || 0, [p])); take(shape.FLEX || 0, ['RB', 'WR', 'TE']); take(shape.SUPERFLEX || 0, ['QB', 'RB', 'WR', 'TE']);
    return total;
  };
  const names = id => [...document.querySelectorAll(`#${id} li b`)].map(b => byName.get(b.textContent)).filter(Boolean);
  const mine = names('v2FindMinePlayers'); const theirs = names('v2FindTheirsPlayers');
  const li = document.querySelectorAll('#v2FindList > li')[i];
  if (!li) return null;
  const [give, get] = li.querySelector('b').textContent.replace('You give ', '').split('; you receive ').map(s => s.split(' + ').map(n => byName.get(n)));
  const swap = (team, out, inn) => team.filter(r => !out.includes(r)).concat(inn);
  const res = {};
  for (const view of charts.length >= 3 ? ['ddf', 'market'] : ['ddf']) {
    res[view] = {you: [best(mine, view), best(swap(mine, give, get), view)], they: [best(theirs, view), best(swap(theirs, get, give), view)]};
  }
  const valued = (team, view) => team.filter(r => Number.isFinite(val(r, view)));
  // JEG-1081 added a third, DDF Value (projections) group to the table; this check reads the DDF Value and Trade chart average cells.
  const own = row => [...document.querySelectorAll(`#v2FindAssess tbody tr${row} td[data-cell]`)].filter(td => /^(ddf|market)-/.test(td.dataset.cell)).map(td => Number(td.textContent));
  const cells = own('[data-pos]');
  const totals = own('[data-row=total]');
  const table = cells.length === 32 && totals.length === 4 ? Object.fromEntries(['ddf', 'market'].map((view, v) => [view, Object.fromEntries([['you', mine], ['they', theirs]].map(([who, team], t) => {
    const at = k => [0, 1, 2, 3].map(pos => cells[pos * 8 + t * 4 + (v * 2) + k]).reduce((n, x) => n + x, 0);
    return [who, {starters: at(0), bench: at(1), total: totals[t * 2 + v], indTotal: valued(team, view).reduce((n, r) => n + val(r, view), 0)}];
  }))])) : null;
  const lines = [...li.querySelectorAll('.v2-find-impact-line')].map(p => p.textContent);
  return {expect: res, table, lines, tables: li.querySelectorAll('.v2-find-lineup').length, detailsOpen: li.querySelector('.v2-find-impact-details').open,
    need: [...li.querySelectorAll('.v2-find-need')].map(p => p.textContent), teams: document.querySelectorAll('#v2FindAssess tbody tr').length,
    boxes: li.querySelectorAll('input[type=checkbox]:not(:disabled)').length};
}"""

# Extra unique players for the short side, so both rosters have the starting slots and the assessment table is shown.
MORE = """(taken) => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name && !taken.includes(r.name)).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const counts = new Map(); C.getAllRows().forEach(r => counts.set(r.name, (counts.get(r.name) || 0) + 1));
  return rows.filter(r => counts.get(r.name) === 1).slice(30, 36).map(r => r.name);
}"""

import re


def close(a, b):
    return abs(a - b) < 0.06


def verify(card, tag, label) -> list[str]:
    errors = []
    names = {"You": "you", "They": "they"}
    for line in card["lines"]:
        who = "You" if line.startswith("You") else "They"
        for view, name in (("ddf", "DDF Value"), ("market", "Trade chart average")):
            m = re.search(re.escape(name) + r" ([\d.]+) → ([\d.]+) \(([+\-\u2212\d.]+)\)", line)
            if view not in card["expect"]:
                continue
            if not m:
                errors.append(tag + f"{label}: {who} line lacks {name}: {line!r}")
                continue
            # The page's number formatter prints a negative delta with U+2212 (the minus sign), not a hyphen.
            b, a, d = (float(x.replace("\u2212", "-")) for x in m.groups())
            wb, wa = card["expect"][view][names[who]]
            if not (close(b, wb) and close(a, wa) and close(d, wa - wb)):
                errors.append(tag + f"{label}: {who} {name} shows {b} → {a} ({d}); the rows say {wb:.1f} → {wa:.1f}")
    errors += verify_table(card, tag, label)
    if len(card["lines"]) != 2:
        errors.append(tag + f"{label}: expected a You line and a They line, got {card['lines']}")
    return errors


def verify_table(card, tag, label) -> list[str]:
    """The assessment table's starter / bench / total cells equal the independent lineup computation AND the 'before' number the
    group card's impact line shows for the same team and view (they must be one number)."""
    errors = []
    table = card["table"]
    if table is None:
        return [tag + f"{label}: the assessment table is missing or incomplete (needs both rosters at the starting slots)"]
    for view, name in (("ddf", "DDF Value"), ("market", "Trade chart average")):
        if view not in card["expect"]:
            continue
        for who, prefix in (("you", "You"), ("they", "They")):
            t = table[view][who]
            want_start = card["expect"][view][who][0]
            line = next((l for l in card["lines"] if l.startswith(prefix)), "")
            m = re.search(re.escape(name) + r" ([\d.]+) → ", line)
            if not close_cells(t["starters"], want_start):
                errors.append(tag + f"{label}: table {who} {view} starters {t['starters']:.1f}, independent {want_start:.1f}")
            if not m or not close_cells(t["starters"], float(m.group(1))):
                errors.append(tag + f"{label}: table {who} {view} starters {t['starters']:.1f} differ from the impact line {line[:90]!r}")
            if not close_cells(t["total"], t["indTotal"]) or not close_cells(t["starters"] + t["bench"], t["indTotal"]):
                errors.append(tag + f"{label}: table {who} {view} total {t['total']:.1f} / starters + bench {t['starters'] + t['bench']:.1f}, independent total {t['indTotal']:.1f}")
    return errors


def close_cells(a, b):
    return abs(a - b) < 0.3   # up to eight cells each rounded to 0.1


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"] + page.evaluate(MORE, pick["mine"] + pick["theirs"]):
        add(page, "Theirs", name)
    page.select_option("#v2FindSize", "2")
    page.click("#v2FindGo")
    page.wait_for_timeout(500)
    count = page.evaluate("() => document.querySelectorAll('#v2FindList > li').length")
    if not count:
        return [tag + "no group to read"]
    for i in range(min(count, 3)):
        card = page.evaluate(EXPECT, i)
        errors += verify(card, tag, f"group {i}")
        if i == 0:
            if card["detailsOpen"]:
                errors.append(tag + "lineup details are open by default")
            if card["teams"] < 6:
                errors.append(tag + "no assessment table (QB, RB, WR, TE, bench, total) above the groups")
            if "market" not in card["expect"]:
                errors.append(tag + "market view missing (fewer than 3 charts?): the check proves less")
            if len(card["need"]) != 2:
                errors.append(tag + f"expected one position-need line per team: {card['need']}")
    # details: open, tables
    page.click("#v2FindList > li >> nth=0 >> summary")
    card = page.evaluate(EXPECT, 0)
    if not card["detailsOpen"] or card["tables"] < 4:
        errors.append(tag + f"Show lineup details did not open the slot tables ({card['tables']} tables)")
    if width <= 390 and page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "horizontal overflow with the lineup tables open")
    # toggle: numbers follow the selection
    for i in range(min(count, 4)):
        box = page.locator(f"#v2FindList > li >> nth={i} >> input[type=checkbox]:not(:disabled) >> nth=0")
        if not box.count():
            continue
        before = page.evaluate(EXPECT, i)["lines"]
        box.focus()
        page.keyboard.press("Space")
        after = page.evaluate(EXPECT, i)
        errors += verify(after, tag, f"group {i} after a toggle")
        if after["lines"] == before:
            errors.append(tag + f"group {i}: impact numbers did not change after toggling a player")
        break
    else:
        errors.append(tag + "no group had a toggleable player: the toggle check proved nothing")
    return errors


def run_checks(overrides=None, viewports=((1366, 768), (390, 844), (320, 640))) -> list[str]:
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


class FinderImpactRenderTest(unittest.TestCase):
    def test_roster_impact(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "the two teams' packages swapped": js.replace('const leaving = pickRows(who === "mine" ? giveRows : recvRows);', 'const leaving = pickRows(who === "mine" ? recvRows : giveRows);', 1),
            "market view reads DDF Value": js.replace('const viewKey = (view, ourKey) => (view === "ddf" ? ourKey : CHART_AVG_KEY);', "const viewKey = (view, ourKey) => ourKey;", 1),
            "table total differs from the lineup": js.replace('money(part.lineup.total)) : el("td"', 'money(part.lineup.starterValue)) : el("td"', 1),
            "table starters read the bench": js.replace("cell(money(posSum(part.lineup.starters, pos, v.key))", "cell(money(posSum(part.lineup.bench, pos, v.key))", 1),
            "numbers not updated after a toggle": js.replace("if (impact) impact.update(giveRows, recvRows);", "if (impact && !impact.done) { impact.done = true; impact.update(giveRows, recvRows); }", 1),
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
