"""v2 Find a trade (JEG-988 commit 3, reworked by JEG-1019): ONE roster assessment table and the natural-fit headline, rendered.

Frozen 2026 inputs and labelled modeled rosters go into the boxes at all four viewports. Checked against
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
  * 390 and 320: no sideways page scroll, the first column sticks.

Two scenarios reach both headline branches: Yahoo as mine and ESPN as theirs has no natural group; the modeled pairing
has a pinned Natural 1a witness (both teams' projections hold), checked before the rendered headline and in all scorings.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the old sentence reappearing, a second assessment
above the results, the headline missing, a "natural fit" headline when there is none, a "no natural fit" headline when
there is one, and table sums that differ from the lineup, and requires each to fail.
"""
from __future__ import annotations

import functools
import json
import re
import unittest
from pathlib import Path
from urllib.request import urlopen

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_render import FINDER_JS, _built_dist, add
from tests.test_v2_modules_render import _serve

ESPN = FIXTURE.with_name("espn-team.txt")
EVAL_FIXTURE = Path(__file__).parent / "fixtures" / "finder_eval"
NATURAL_FIXTURE = json.loads((EVAL_FIXTURE / "scenario.json").read_text(encoding="utf-8"))
NATURAL_SCENARIO = "Modeled Natural 1a pairing (frozen 2026 inputs)"
NATURAL_MUTATION = ('else if (naturalCount) setHeadline("natural",',
                    'else if (false) setHeadline("natural",')


def fixture_page(html):
    """Replace data only: the current engine, finder, configuration and rules still run unchanged."""
    players = (EVAL_FIXTURE / "players.json").read_text(encoding="utf-8")
    html, count = re.subn(r'(<script id="players-data" type="application/json">).*?(</script>)',
                          lambda m: m[1] + players + m[2], html, flags=re.S)
    assert count == 1, f"finder eval fixture: expected one players-data island, found {count}"
    return html


# Prove the named trade clears search and BOTH sides of the current Natural 1a predicate. This is independent of
# the rendered headline: breaking that branch must report the wrong headline, never an unreachable test scenario.
PRECONDITION = """(fx) => {
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder;
  const rows = C.getAllRows(), by = new Map(rows.map(r => [String(r.player_key), r]));
  const problems = [];
  for (const side of ['mine', 'theirs']) for (const p of fx[side]) {
    if (by.get(p.key)?.name !== p.name || rows.filter(r => r.name === p.name).length !== 1)
      problems.push(`not exactly one engine row: ${p.key} ${p.name}`);
  }
  if (problems.length) return {problems};
  const charts = F.CHART_KEYS.filter(k => C.getSourceInfo().some(s => s.key === k && s.available));
  const mine = F.withChartAverage(fx.mine.map(p => by.get(p.key)), charts);
  const theirs = F.withChartAverage(fx.theirs.map(p => by.get(p.key)), charts);
  const byKey = new Map(mine.concat(theirs).map(r => [String(r.player_key), r]));
  const give = fx.witness.give.map(k => byKey.get(k)), receive = fx.witness.receive.map(k => byKey.get(k));
  const shape = C.getRosterShape();
  const ctx = {shape, expected: F.expectedDepth(C.getAdjustmentWeights().allocation, C.getState().teams),
    weights: C.getBenchShareReadout(), ourKey: F.OUR_KEY, marketKey: F.MARKET_KEY, chartKeys: charts};
  const fit = (give, receive) => F.tradeFit({mine: {roster: mine, leaving: give, arriving: receive},
    theirs: {roster: theirs, leaving: receive, arriving: give}}, ctx);
  const witness = fit(give, receive);
  const found = F.findTrades(mine, theirs, {maxSize: 3, chartKeys: charts, limit: 1e7,
    sanity: {shape, mine, theirs, keepMine: true, keepTheirs: true}});
  const judged = F.evaluateCombo(give, receive, found.ctx);
  const groups = F.groupTrades(found.trades, {ourKey: F.OUR_KEY});
  const natural = groups.filter(g => fit(g.best.give, g.best.receive)?.label === 'natural').length;
  if (charts.length < F.MIN_CHARTS) problems.push(`only ${charts.length} charts`);
  if (!Object.values(judged.passes).every(Boolean)) problems.push(`witness fails search: ${JSON.stringify(judged.passes)}`);
  if (!witness?.natural.ok) problems.push(`witness is not Natural 1a: ${JSON.stringify(witness)}`);
  if (!natural) problems.push(`no Natural candidate among ${groups.length} groups`);
  return {problems, natural, witness: witness?.natural};
}"""


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
    expect_natural = SCENARIOS[scenario]
    errors = []
    say = lambda what: errors.append(f"{tag}{scenario}: {what}")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    start = page.evaluate(PAGE)
    if start["headline"] != "Add both rosters to see fit" or start["state"] != "missing":
        say(f"the headline before data reads {start['headline']!r}")
    pick = {side: [p["name"] for p in NATURAL_FIXTURE[side]] for side in ("mine", "theirs")}
    for name in pick["mine"][:3]:
        add(page, "Mine", name)
    for name in pick["theirs"][:2]:
        add(page, "Theirs", name)
    partial = page.evaluate(PAGE)
    if "shows once" not in partial["text"] or partial["assessTables"]:
        say(f"a partial roster reads {partial['text'][:100]!r} with {partial['assessTables']} tables")
    # Name lists append; clear the partial rosters so the fixture is exactly the labelled pairing.
    for side in ("Mine", "Theirs"):
        page.click(f"#v2Find{side}Clear")
    if expect_natural:
        proof = page.evaluate(PRECONDITION, NATURAL_FIXTURE)
        assert not proof["problems"], f"{tag}{scenario}: Natural fixture precondition failed: {proof}"
        for side in ("Mine", "Theirs"):
            page.fill(f"#v2Find{side}Search", "\n".join(pick[side.lower()]))
        actual = page.evaluate("""() => Object.fromEntries(['Mine', 'Theirs'].map(s => [s.toLowerCase(),
          [...document.querySelectorAll(`#v2Find${s}Players li.v2-find-row b`)].map(b => b.textContent)]))""")
        for side in ("mine", "theirs"):
            assert sorted(actual[side]) == sorted(pick[side]), \
                f"{tag}{scenario}: pasted {side} differs from the proven fixture: {actual[side]}"
        # Search knows K/DEF identities; a plain list of names carries no position for unmatched entries.
        for name in ("Kansas City Chiefs", "Harrison Butker"):
            add(page, "Mine", name)
    else:
        page.fill("#v2FindMineSearch", FIXTURE.read_text(encoding="utf-8"))
        page.fill("#v2FindTheirsSearch", ESPN.read_text(encoding="utf-8"))
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


# The old ESPN/Yahoo positive case drifted: Yahoo has only one RB after overlaps are removed. Keep the negative
# branch, but use a modeled pairing with a proven witness for the positive branch (JEG-1352 / Natural 1a JEG-1324).
SCENARIOS = {"Yahoo mine, ESPN theirs": False, NATURAL_SCENARIO: True}
VIEWPORTS = ((1366, 768), (1440, 900), (390, 844), (320, 640))


def run_checks(mutate=None, viewports=VIEWPORTS, scenarios=SCENARIOS, scoring="ppr") -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    base_js = FINDER_JS.read_text(encoding="utf-8")
    if mutate:
        old, new = mutate
        assert old in base_js, f"stale mutation anchor {old!r}"
        base_js = base_js.replace(old, new, 1)
    with _built_dist() as base, sync_playwright() as playwright:
        with urlopen(base) as response:
            html = fixture_page(response.read().decode("utf-8"))
        comparison = (EVAL_FIXTURE / "comparison.json").read_text(encoding="utf-8")
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            for name in scenarios:
                for width, height in viewports:
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page_errors = []
                    page.on("pageerror", lambda e: page_errors.append(str(e)))
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    page.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(NATURAL_FIXTURE['fixture']['today'])};")
                    page.route(base, functools.partial(_serve, html, "text/html"))
                    page.route("**/assets/comparison-sources-data.json*", functools.partial(_serve, comparison, "application/json"))
                    # Historical comparisons are outside this fixture; never borrow them from a moving weekly build.
                    page.route("**/assets/history/index.json*", functools.partial(_serve,
                        '{"schema":"week-history-index/1","season":2026,"weeks":{},"served":{}}', "application/json"))
                    page.route("**/v2/finder.js*", functools.partial(_serve, base_js, "text/javascript"))
                    page.goto(base + "#find-trade", wait_until="networkidle")
                    page.wait_for_function("window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()")
                    page.evaluate("s => window.TradeValueCurveControls.setScoring(s)", scoring)
                    errors += check(page, f"[{scoring} {width}x{height}] ", width, height, name)
                    if page_errors:
                        errors.append(f"[{width}] page errors {page_errors}")
                    page.close()
        finally:
            browser.close()
    return errors


def broken(mutation) -> bool:
    # A stale anchor, broken fixture or browser outage is a test error, never evidence that a mutant was caught.
    return bool(run_checks(mutation, viewports=((1366, 768),)))


class FinderAssessmentRenderTest(unittest.TestCase):
    def test_assessment_and_headline(self):
        self.assertEqual(run_checks(), [])

    def test_natural_fixture_all_scorings(self):
        for scoring in ("standard", "half_ppr"):
            with self.subTest(scoring=scoring):
                self.assertEqual(run_checks(viewports=((1366, 768),), scenarios=(NATURAL_SCENARIO,), scoring=scoring), [])

    def test_natural_headline_mutation_reports_wrong_headline(self):
        errors = run_checks(NATURAL_MUTATION, viewports=((1366, 768),), scenarios=(NATURAL_SCENARIO,))
        self.assertTrue(any("natural groups listed but the headline reads" in e for e in errors), errors)
        self.assertFalse(any("branch under test is not reached" in e for e in errors), errors)

    def test_guard_fails_on_broken_builds(self):
        cases = {
            "the old sentence reappears": ("box.append(assessmentTable(a, b));", 'box.append(assessmentTable(a, b), el("p", {text: "Based on fundamentals, your roster is balanced by position."}));'),
            "a second assessment above the results": ("    out.append(list, tail);", '    out.append($("v2FindAssess").cloneNode(true)); out.append(list, tail);'),
            "headline missing": ('    const box = $("v2FindFit");\n    if (!box) return;\n    const h = fitHeadline', '    const box = $("v2FindFit");\n    if (box) return;\n    const h = fitHeadline'),
            "natural headline when there is none": ('else setHeadline("none");', 'else setHeadline("natural", {count: 1});'),
            "table bench cells read the starters": ("cell(money(posSum(part.lineup.bench, pos, v.key))", "cell(money(posSum(part.lineup.starters, pos, v.key))"),
            "table total differs from the lineup": ('money(part.lineup.total)) : el("td"', 'money(part.lineup.starterValue)) : el("td"'),
        }
        for name, mutation in cases.items():
            with self.subTest(name):
                self.assertTrue(broken(mutation), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
