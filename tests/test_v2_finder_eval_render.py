"""v2 Find a trade (JEG-988 commit 3, reworked by JEG-1019): ONE roster assessment table and the natural-fit headline, rendered.

Two real roster pages (the Yahoo and ESPN team fixtures) go into the boxes at 1366x768, 1440 and 390 wide. Checked against
the engine's own allocation and rows, computed here independently of finder.js:

  * a partial roster shows no table, only when it will appear;
  * with both rosters in there is exactly ONE assessment on the page: one table (caption, th scope, no tab stops), no
    "Based on ..." sentences, no per-roster evaluation under either roster and none above the results;
  * the table's rows are QB, RB, WR, TE, a bench subtotal and a total; per team the counted players, expected range,
    over / under flag (DDF Value, plus the market flag when it differs) and the starter and bench value by position in
    DDF Value and the Trade chart average equal the independent computation (best lineup, then bench = the rest); the
    total cell equals the independent sum of every valued player, i.e. what the roster-impact block starts from;
  * DEF and K appear as a "Not evaluated" note line, outside every count and sum;
  * the headline sits directly under the Find controls and above the table: "Add both rosters to see fit" before data,
    "Press Find trades to see fit" with both rosters, then "Natural fit found: N group(s)" with a jump link to the first
    natural group when the listed groups include natural ones (N = the listed natural groups), else "No natural fit
    between these rosters: ...". It is on screen without scrolling at 1366x768 and 390 after Find;
  * the groups, their order and their fit labels are the same as before (see the PR: compared with origin/main);
  * 390 and 320: no sideways page scroll, the first column sticks.

Two scenarios reach both headline branches: Yahoo as mine and ESPN as theirs has no natural group, the swap has natural ones.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the old sentence reappearing, a second assessment
above the results, the headline missing, a "natural fit" headline when there is none, a "no natural fit" headline when
there is one, and table sums that differ from the lineup, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add
from tests.test_v2_modules_render import _serve

ESPN = FIXTURE.with_name("espn-team.txt")


def setUpModule():
    _render_env.ensure_built()


# What the table must say, from the engine, independent of finder.js.
WANT = """(side) => {
  const C = window.TradeValueCurveControls;
  const teams = C.getState().teams;
  const alloc = Object.fromEntries(C.getAdjustmentWeights().allocation.map(a => [a.pos, a]));
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => avail.has(k));
  const shape = C.getRosterShape();
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  const names = [...document.querySelectorAll(`#v2Find${side}Players li.v2-find-row b`)].map(b => b.textContent).filter(n => byName.has(n));
  const rows = names.map(n => byName.get(n));
  const avg = r => { const vals = charts.map(k => r.values[k]); return vals.every(v => typeof v === 'number' && Number.isFinite(v)) ? vals.reduce((a, b) => a + b, 0) / vals.length : null; };
  const views = {ddf: r => r.values.ddf_value, market: avg};
  const usable = v => typeof v === 'number' && Number.isFinite(v) && v >= 0.05;
  const finite = v => typeof v === 'number' && Number.isFinite(v);
  const POS = ['QB', 'RB', 'WR', 'TE'];
  const out = {};
  for (const pos of POS) {
    const x = alloc[pos].rostered / teams, lo = Math.floor(x + 1e-9), hi = Math.ceil(x - 1e-9);
    const word = n => (n < lo ? 'Under' : n > hi + 1 ? 'Over' : 'OK');
    const f = rows.filter(r => r.pos === pos && usable(views.ddf(r))).length, m = rows.filter(r => r.pos === pos && usable(avg(r))).length;
    const flag = word(f) + (word(m) !== word(f) ? ` (market: ${word(m).toLowerCase()})` : '');
    out[pos] = {range: lo === hi ? String(lo) : `${lo}-${hi}`, count: String(f), flag};
    for (const [id, val] of Object.entries(views)) {
      const valued = rows.filter(r => finite(val(r))).sort((a, b) => val(b) - val(a) || String(a.player_key).localeCompare(String(b.player_key)));
      const used = new Set(); const startersBy = {QB: 0, RB: 0, WR: 0, TE: 0};
      const take = (n, allowed) => { for (let k = 0; k < n; k++) { const r = valued.find(v => !used.has(v) && allowed.includes(v.pos)); if (r) { used.add(r); startersBy[r.pos] += val(r); } } };
      POS.forEach(p => take(shape[p] || 0, [p])); take(shape.FLEX || 0, ['RB', 'WR', 'TE']); take(shape.SUPERFLEX || 0, ['QB', 'RB', 'WR', 'TE']);
      const all = valued.filter(r => r.pos === pos).reduce((n, r) => n + val(r), 0);
      out[pos][id] = {starters: startersBy[pos], bench: all - startersBy[pos]};
    }
  }
  out.total = {};
  for (const [id, val] of Object.entries(views)) out.total[id] = rows.filter(r => finite(val(r))).reduce((n, r) => n + val(r), 0);
  return out;
}"""
TABLE = """() => [...document.querySelectorAll('#v2FindAssess tbody tr')].map(tr => [...tr.children].map(c => c.textContent))"""
PAGE = """() => {
  const q = s => document.querySelectorAll(s).length;
  const box = document.getElementById('v2FindFit'); const r = box.getBoundingClientRect();
  const assess = document.getElementById('v2FindAssess');
  const controls = document.getElementById('v2FindGo').getBoundingClientRect();
  const first = document.querySelector('#v2FindAssess tbody th.v2-find-pos');
  return {tables: q('table.v2-find-assess-table'), assessTables: q('#v2FindAssess table'), basedOn: document.body.innerText.includes('Based on fundamentals') || document.body.innerText.includes('Based on market pricing'),
    oldEval: q('.v2-find-eval') + q('#v2FindMineEval') + q('#v2FindTheirsEval') + q('#v2FindTeams'),
    caption: Boolean(document.querySelector('#v2FindAssess caption')), thNoScope: q('#v2FindAssess th:not([scope])'), tabbable: q('#v2FindAssess table [tabindex], #v2FindAssess table a, #v2FindAssess table button, #v2FindAssess table input'),
    text: assess.textContent, headline: box.textContent, state: box.dataset.state, link: box.querySelector('a') ? box.querySelector('a').getAttribute('href') : null,
    headTop: r.top, headBottom: r.bottom, headAfterControls: r.top >= controls.bottom - 1, headBeforeAssess: r.bottom <= assess.getBoundingClientRect().top + 1,
    sticky: first ? getComputedStyle(first).position : null, ids: q('[id=v2FindAssess]')};
}"""
GROUPS = """() => { const more = document.getElementById('v2FindMoreGroups'); if (more) more.click();
  return [...document.querySelectorAll('#v2FindList > li')].map(li => ({fit: li.dataset.findFit, id: li.id})); }"""
NATURAL_WORD = "Natural fit found: "
NONE_TEXT = "No natural fit between these rosters: "


# Cells per team in the assessment rows (JEG-1081): Counted, Flag, then Starters and Bench for each of DDF Value, Trade
# chart average and DDF Value (projections). The Total row has one cell per view instead of two.
TEAM_COLS = 8
TOTAL_COLS = 5


def num(text):
    return float(text)


def check(page, tag, width, height, scenario) -> list[str]:
    swap, expect_natural = SCENARIOS[scenario]
    errors = []
    say = lambda what: errors.append(f"{tag}{scenario}: {what}")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    start = page.evaluate(PAGE)
    if start["headline"] != "Add both rosters to see fit" or start["state"] != "missing":
        say(f"the headline before data reads {start['headline']!r}")
    pick = page.evaluate(PICK)
    for name in pick["mine"][:3]:
        add(page, "Mine", name)
    for name in pick["theirs"][:2]:
        add(page, "Theirs", name)
    partial = page.evaluate(PAGE)
    if "shows once" not in partial["text"] or partial["assessTables"]:
        say(f"a partial roster reads {partial['text'][:100]!r} with {partial['assessTables']} tables")
    page.fill("#v2FindMineSearch", (ESPN if swap else FIXTURE).read_text(encoding="utf-8"))
    page.fill("#v2FindTheirsSearch", (FIXTURE if swap else ESPN).read_text(encoding="utf-8"))
    page.wait_for_timeout(500)
    state = page.evaluate(PAGE)
    if state["headline"] != "Press Find trades to see fit":
        say(f"the headline with both rosters in reads {state['headline']!r}")
    if state["tables"] != 1 or state["assessTables"] != 1 or state["ids"] != 1:
        say(f"{state['tables']} assessment tables ({state['assessTables']} in the section)")
    if state["basedOn"] or state["oldEval"]:
        say("the per-roster evaluation text is still on the page")
    if not state["caption"] or state["thNoScope"] or state["tabbable"]:
        say(f"table structure: caption {state['caption']}, headers without scope {state['thNoScope']}, tab stops {state['tabbable']}")
    if state["sticky"] != "sticky":
        say(f"the first column is {state['sticky']}, not sticky")
    table = page.evaluate(TABLE)
    labels = [row[0] for row in table]
    if labels != ["QB", "RB", "WR", "TE", "Bench subtotal", "Total"]:
        say(f"table rows are {labels}")
    else:
        wants = {"Mine": page.evaluate(WANT, "Mine"), "Theirs": page.evaluate(WANT, "Theirs")}
        for t, side in enumerate(("Mine", "Theirs")):
            want = wants[side]
            off = 2 + TEAM_COLS * t
            for row in table[:4]:
                w = want[row[0]]
                got = row[off:off + TEAM_COLS]
                if row[1] != w["range"] or got[0] != w["count"] or got[1] != w["flag"]:
                    say(f"{side} {row[0]}: table says {row[1]} / {got[0]} / {got[1]}, engine says {w['range']} / {w['count']} / {w['flag']}")
                for (i, view, part) in ((2, "ddf", "starters"), (3, "ddf", "bench"), (4, "market", "starters"), (5, "market", "bench")):
                    if abs(num(got[i]) - w[view][part]) > 0.06:
                        say(f"{side} {row[0]} {view} {part}: table {got[i]}, independent {w[view][part]:.2f}")
            # Bench subtotal and total, per team: cells are [count, flag, "", bench, "", bench, "", bench] and
            # [count, flag, total, total, total]: the total is one cell spanning each view's starters and bench columns.
            bench = table[4][off:off + TEAM_COLS]
            total = table[5][2 + TOTAL_COLS * t:2 + TOTAL_COLS * t + TOTAL_COLS]
            for view, bi, ti in (("ddf", 3, 2), ("market", 5, 3)):
                bench_want = sum(want[p][view]["bench"] for p in ("QB", "RB", "WR", "TE"))
                if abs(num(bench[bi]) - bench_want) > 0.06 or abs(num(total[ti]) - want["total"][view]) > 0.06:
                    say(f"{side} {view}: bench subtotal {bench[bi]} / total {total[ti]}, independent {bench_want:.2f} / {want['total'][view]:.2f}")
    text = state["text"]
    if "Not evaluated" not in text or "DEF" not in text:
        say("the kicker and defense are not named as not evaluated")
    for need in ("biggest imbalance", "DDF Value"):
        if need not in text:
            say(f"the biggest-imbalance line lacks {need!r}")
    if state["headAfterControls"] is False or state["headBeforeAssess"] is False:
        say("the headline is not between the Find controls and the table")
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(1200)
    groups = page.evaluate(GROUPS)
    page.wait_for_timeout(200)
    after = page.evaluate(PAGE)
    natural = [g for g in groups if g["fit"] == "natural"]
    if bool(natural) != expect_natural:
        say(f"this scenario is meant to have {'natural groups' if expect_natural else 'no natural group'}, it has {len(natural)} of {len(groups)}: the branch under test is not reached")
    if not groups:
        say("no groups listed")
    elif natural:
        want_text = f"{NATURAL_WORD}{len(natural)} group{'s' if len(natural) != 1 else ''}"
        if not after["headline"].startswith(want_text) or after["state"] != "natural":
            say(f"{len(natural)} natural groups listed but the headline reads {after['headline']!r}")
        if after["link"] != "#v2FindFirstNatural" or groups[0]["id"] != "v2FindFirstNatural" or groups[0]["fit"] != "natural":
            say("the jump link does not lead to the first natural group")
        else:
            page.click("#v2FindFit a")
            if page.evaluate("() => document.activeElement && document.activeElement.id") != "v2FindFirstNatural":
                say("the jump link does not focus the first natural group")
    else:
        if not after["headline"].startswith(NONE_TEXT) or "market supported or force fits" not in after["headline"] or after["state"] != "none":
            say(f"no natural group is listed but the headline reads {after['headline']!r}")
        if after["link"]:
            say("a jump link is offered with no natural group")
    if after["tables"] != 1 or after["basedOn"] or after["oldEval"]:
        say(f"after Find: {after['tables']} assessment tables, old evaluation {after['oldEval']}, sentences {after['basedOn']}")
    if after["headBottom"] > height or after["headTop"] < -2:
        say(f"the headline is off screen after Find (top {after['headTop']:.0f}, bottom {after['headBottom']:.0f}, viewport {height})")
    if page.evaluate(OVER) > 0:
        say("horizontal overflow")
    if not page.locator("#v2FindMineClear").is_visible():
        page.click("#v2FindEdit")
    page.click("#v2FindMineClear")
    page.wait_for_timeout(300)
    if page.evaluate(PAGE)["state"] != "missing":
        say("the headline did not return to 'Add both rosters' after Clear")
    return errors


# (ESPN and Yahoo swapped, natural groups expected): Yahoo vs ESPN has none of 7 groups natural, ESPN vs Yahoo has 8 of 11.
SCENARIOS = {"Yahoo mine, ESPN theirs": (False, False), "ESPN mine, Yahoo theirs": (True, True)}
VIEWPORTS = ((1366, 768), (1440, 900), (390, 844), (320, 640))


def run_checks(mutate=None, viewports=VIEWPORTS, scenarios=SCENARIOS) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    base_js = FINDER_JS.read_text(encoding="utf-8")
    with _built_dist() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            for name in scenarios:
                js = base_js
                for old, new in ([mutate] if mutate else []):
                    if old not in js:
                        errors.append(f"stale mutation anchor {old!r}")
                    js = js.replace(old, new, 1)
                for width, height in viewports:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page_errors = []
                    page.on("pageerror", lambda e: page_errors.append(str(e)))
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    page.route("**/v2/finder.js*", functools.partial(_serve, js, "text/javascript"))
                    page.goto(base + "#find-trade", wait_until="networkidle")
                    errors += check(page, f"[{width}x{height}] ", width, height, name)
                    if page_errors:
                        errors.append(f"[{width}] page errors {page_errors}")
                    page.close()
        finally:
            browser.close()
    return errors


def broken(mutation) -> bool:
    try:
        return bool(run_checks(mutation, viewports=((1366, 768),)))
    except Exception:
        return True


class FinderAssessmentRenderTest(unittest.TestCase):
    def test_assessment_and_headline(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        cases = {
            "the old sentence reappears": ("box.append(assessmentTable(a, b));", 'box.append(assessmentTable(a, b), el("p", {text: "Based on fundamentals, your roster is balanced by position."}));'),
            "a second assessment above the results": ("    out.append(list);", '    out.append($("v2FindAssess").cloneNode(true)); out.append(list);'),
            "headline missing": ('    const box = $("v2FindFit");\n    if (!box) return;\n    const h = fitHeadline', '    const box = $("v2FindFit");\n    if (box) return;\n    const h = fitHeadline'),
            "natural headline when there is none": ('else setHeadline("none");', 'else setHeadline("natural", {count: 1});'),
            "no-natural headline when there is one": ('else if (naturalCount) setHeadline("natural", {count: naturalCount});', 'else if (false) setHeadline("natural", {count: naturalCount});'),
            "table bench cells read the starters": ("cell(money(posSum(part.lineup.bench, pos, v.key))", "cell(money(posSum(part.lineup.starters, pos, v.key))"),
            "table total differs from the lineup": ('money(part.lineup.total)) : el("td"', 'money(part.lineup.starterValue)) : el("td"'),
        }
        for name, mutation in cases.items():
            with self.subTest(name):
                self.assertTrue(broken(mutation), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
