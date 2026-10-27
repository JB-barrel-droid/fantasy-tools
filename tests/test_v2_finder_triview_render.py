"""JEG-1081 PR 3: the three views in Find a trade's roster assessment, roster impact and score chips, rendered.

Yahoo and ESPN team fixtures go through the page at 1440, 1366x768 and 390 wide. Checked:

  * assessment table: DDF Value, Trade chart average and DDF Value (projections) column groups exist at every width; at 1366
    and 1440 all three are visible and the "Show projections" button is not; at 390 the projections group is hidden, the
    button shows, and pressing it reveals the group (aria-expanded flips);
  * the breakpoints hold at 1023/1024 (projections group) and 767/768 (impact secondary line); the team headings' colspans equal
    the visible cell count, so the headings stay over their own columns (JEG-1081 review);
  * the projections group is consistent within itself: its starters cells and its bench subtotal add to its total (to 0.2);
  * score chips: one number each (DDF Value and Trade chart average) and the same three-line tooltip
    ("DDF Value: x / Projections: y / Market: z") equal to the row's values;
  * roster impact: a secondary line "Starters +a DDF Value (+b projections, +c market). Bench ..." per team; at 390 it is hidden
    until "Show other views" is pressed;
  * no page errors and no sideways page scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves a v2.css that never hides the projections group on a phone, a
finder.js without the projections column group, and one without the chip tooltip, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_eval_render import ESPN
from tests.test_v2_finder_render import FINDER_JS, _built_dist
from tests.test_v2_modules_render import _serve

CSS = FINDER_JS.parent / "v2.css"


def setUpModule():
    _render_env.ensure_built()


STATE = """() => {
  const vis = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const th = [...document.querySelectorAll('#v2FindAssess thead th.v2-find-proj-col')];
  const toggle = document.querySelector('#v2FindAssess .v2-find-proj-toggle');
  const heads = [...document.querySelectorAll('#v2FindAssess thead tr:nth-child(2) th')].map(t => t.textContent.trim());
  return {heads, projTh: th.length, projVisible: th.some(vis), toggle: !!toggle, toggleVisible: vis(toggle),
    expanded: toggle ? toggle.getAttribute('aria-expanded') : null};
}"""
CELLS = """() => {
  const C = window.TradeValueCurveControls;
  const cell = document.querySelector('#v2FindAssess tbody tr[data-row="total"] td[data-cell="projections-total"]');
  const num = sel => [...document.querySelectorAll(sel)].map(td => parseFloat(td.textContent)).filter(Number.isFinite);
  const sum = a => a.reduce((x, y) => x + y, 0);
  // first team: the first projections-starters cell of each position row, then its bench total and total
  const rows = [...document.querySelectorAll('#v2FindAssess tbody tr[data-pos]')];
  const starters = sum(rows.map(r => parseFloat(r.querySelector('td[data-cell="projections-starters"]').textContent)));
  const bench = sum(rows.map(r => parseFloat(r.querySelector('td[data-cell="projections-bench"]').textContent)));
  const tot = document.querySelector('#v2FindAssess tbody tr[data-row="total"] td[data-cell="projections-total"]');
  // headings: team th colspans vs visible cells in the first body row after Position and Expected
  const vis = el => el.getClientRects().length > 0;
  const spans = [...document.querySelectorAll('#v2FindAssess th.v2-find-assess-team')].map(t => t.colSpan);
  const cells = [...rows[0].children].filter(vis).length - 2;
  return {total: cell ? cell.textContent.trim() : null, n: document.querySelectorAll('#v2FindAssess td[data-cell^="projections-"]').length,
    starters, bench, totalNum: tot ? parseFloat(tot.textContent) : null, spans, cells};
}"""
CHIPS = """() => [...document.querySelectorAll('#v2FindMinePlayers li.v2-find-row')].slice(0, 6).map(li => {
  const byName = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r]));
  const name = li.querySelector('b').textContent;
  const row = byName.get(name);
  const chips = [...li.querySelectorAll('.v2-find-chip')];
  return {name, n: chips.length, titles: chips.map(c => c.title), values: row ? {ddf: row.values.ddf_value, proj: row.values.ddf_value_projections} : null};
}).filter(x => x.values)"""
IMPACT = """() => {
  const vis = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
  const li = document.querySelector('#v2FindList li.v2-find-group');
  if (!li) return null;
  const sec = [...li.querySelectorAll('.v2-find-impact-secondary')];
  const more = li.querySelector('.v2-find-impact-more');
  return {n: sec.length, text: sec.map(p => p.textContent), visible: sec.some(vis), more: !!more, moreVisible: vis(more)};
}"""


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.TradeValueFinder", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    page.fill("#v2FindMineSearch", FIXTURE.read_text(encoding="utf-8"))
    page.fill("#v2FindTheirsSearch", ESPN.read_text(encoding="utf-8"))
    page.wait_for_timeout(400)
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(1200)
    st = page.evaluate(STATE)
    if st["heads"].count("DDF Value") != 2 or st["heads"].count("Trade chart average") != 2 or st["heads"].count("DDF Value (projections)") != 2:
        say(f"assessment column groups: {st['heads']}")
    if not st["projTh"]:
        say("no projections column group in the assessment")
    wide = width >= 1024
    pre = page.evaluate(CELLS)
    if sum(pre["spans"]) != pre["cells"]:
        say(f"team headings span {pre['spans']} but {pre['cells']} cells are visible in a row (projections group {'shown' if wide else 'hidden'}): the headings sit over the wrong columns")
    if wide and (not st["projVisible"] or st["toggleVisible"]):
        say(f"desktop: projections visible {st['projVisible']}, toggle visible {st['toggleVisible']}")
    if not wide:
        if st["projVisible"] or not st["toggleVisible"]:
            say(f"phone: projections visible {st['projVisible']} (want hidden), toggle visible {st['toggleVisible']} (want shown)")
        page.click("#v2FindAssess .v2-find-proj-toggle")
        after = page.evaluate(STATE)
        if not after["projVisible"] or after["expanded"] != "true":
            say(f"phone: Show projections did not reveal the group: visible {after['projVisible']} expanded {after['expanded']}")
    cells = page.evaluate(CELLS)
    if not cells["n"] or not cells["total"] or cells["total"] == "n/a":
        say(f"projections total cell: {cells}")
    elif abs(cells["starters"] + cells["bench"] - cells["totalNum"]) > 0.2 * max(1, len(cells["spans"])) * 2:
        say(f"projections group does not add up: starters {cells['starters']} + bench {cells['bench']} vs total {cells['totalNum']} (first team's cells only counted per row, rounding allowed)")
    if sum(cells["spans"]) != cells["cells"]:
        say(f"team headings span {cells['spans']} but {cells['cells']} cells are visible in a row (after Show projections): the headings sit over the wrong columns")
    for chip in page.evaluate(CHIPS):
        lines = chip["titles"][0].split("\n") if chip["titles"] else []
        want = [f"DDF Value: {chip['values']['ddf']:.1f}"]
        if chip["n"] != 2 or len(lines) != 3 or lines[0] != want[0] or lines[1] != (f"Projections: {chip['values']['proj']:.1f}" if chip["values"]["proj"] is not None else "Projections: no value") or not lines[2].startswith("Market: "):
            say(f"chip tooltip for {chip['name']}: chips {chip['n']} titles {chip['titles'][:1]}")
        if len(set(chip["titles"])) != 1:
            say(f"the two chips of {chip['name']} carry different tooltips")
    imp = page.evaluate(IMPACT)
    if imp is None:
        say("no group listed to read the impact from")
    else:
        if imp["n"] != 2 or not all(t.startswith("Starters ") and " DDF Value" in t and "projections" in t and "Bench " in t for t in imp["text"]):
            say(f"impact secondary lines: {imp}")
        impact_wide = width >= 768
        if impact_wide and not imp["visible"]:
            say("the secondary impact line is not visible at 768 and up")
        if not impact_wide:
            if imp["visible"] or not imp["moreVisible"]:
                say(f"phone: secondary visible {imp['visible']}, expand button visible {imp['moreVisible']}")
            page.click("#v2FindList li.v2-find-group .v2-find-impact-more")
            if not page.evaluate(IMPACT)["visible"]:
                say("phone: Show other views did not reveal the secondary line")
    # JEG-1081 PR 7: the view tooltips are the spec's sentences; a fit line says in words what its label means.
    tips = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#v2FindAssess thead tr:nth-child(2) th[title]')].slice(0, 3).map(th => [th.textContent.trim(), th.title]))")
    want = {"DDF Value": "Our methodology: the four trade charts (FantasyCalc, USA Today, FantasyPros, CBS), adjusted for your league's position weights.",
            "Trade chart average": "What the market pays: the same four trade charts, uniformly rescaled (no position weighting). The common language for trade proposals.",
            "DDF Value (projections)": "The alternate: ESPN, CBS rest-of-season and Razzball projections, averaged for your league. Independent of the trade market."}
    if tips != want:
        say(f"assessment tooltips {tips}")
    fit_tips = page.evaluate("() => [...document.querySelectorAll('#v2FindList .v2-find-fit')].map(p => [p.dataset.fitVariant, p.title])")
    if not fit_tips or any(not v or not t or not t.startswith(v.split('-')[0].capitalize()) for v, t in fit_tips):
        say(f"fit line tooltips {fit_tips[:3]}")
    # Under a basis of the reader's own, DDF Value says so and the market says its point scale follows (spec 5b).
    page.evaluate("() => { window.TradeValueCurveControls.setBasis({mode: 'single', source: 'fantasycalc'}, false); document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'basis', notes: []}})); }")
    page.wait_for_timeout(800)
    basis = page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#v2FindAssess thead tr:nth-child(2) th[title]')].slice(0, 3).map(th => [th.textContent.trim(), th.title]))")
    heads = list(basis)
    if not heads or heads[0] != "DDF Value (FantasyCalc)" or "not our methodology" not in basis.get("DDF Value (FantasyCalc)", "") \
            or "Rescaled to FantasyCalc's point scale." not in basis.get("Trade chart average", ""):
        say(f"under a FantasyCalc basis the assessment says {basis}")
    page.evaluate("() => { window.TradeValueCurveControls.setBasis(null, false); document.dispatchEvent(new CustomEvent('ddf:league-settings-changed', {detail: {reason: 'basis', notes: []}})); }")
    page.wait_for_timeout(500)
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow")
    return errors


VIEWPORTS = ((1440, 900), (1366, 768), (1024, 768), (1023, 768), (768, 1024), (767, 1024), (390, 844))


def run_checks(overrides=None, viewports=VIEWPORTS) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        try:
            for width, height in viewports:
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


def broken(overrides, viewports) -> bool:
    try:
        return bool(run_checks(overrides, viewports=viewports))
    except Exception:
        return True


class FinderTriViewRenderTest(unittest.TestCase):
    def test_views(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        cases = {
            "projections never hidden on a phone": ({"v2.css": (css.replace(".v2-find-table-wrap:not([data-show-proj=\"1\"]) .v2-find-proj-col { display: none; }", ""), "text/css")}, ((390, 844),), ".v2-find-table-wrap:not([data-show-proj=\"1\"]) .v2-find-proj-col { display: none; }" in css),
            "no projections column group": ({"finder.js": (js.replace('{id: "projections", label: "DDF Value (projections)", key: PROJECTIONS_KEY, cls: "v2-find-proj-col"}', '{id: "projections", label: "DDF Value (projections)", key: PROJECTIONS_KEY, cls: "v2-find-proj-col"}'.replace('label: "DDF Value (projections)"', 'label: "x"')), "text/javascript")}, ((1440, 900),), True),
            "headings hardcoded to 8": ({"finder.js": (js.replace('(wide && wide.matches) || wrap.dataset.showProj === "1" ? "8" : "6"', '"8"'), "text/javascript")}, ((390, 844),), '(wide && wide.matches) || wrap.dataset.showProj === "1" ? "8" : "6"' in js),
            "toggle does not flip aria-expanded": ({"finder.js": (js.replace('toggle.setAttribute("aria-expanded", String(on));\n      toggle.textContent = on ? "Hide projections"', 'toggle.textContent = on ? "Hide projections"'), "text/javascript")}, ((390, 844),), 'toggle.setAttribute("aria-expanded", String(on));\n      toggle.textContent = on ? "Hide projections"' in js),
            "projections hidden only under 600px": ({"v2.css": (css.replace("@media (max-width: 1023px) {\n  .v2-find-proj-toggle", "@media (max-width: 600px) {\n  .v2-find-proj-toggle"), "text/css")}, ((1023, 768),), "@media (max-width: 1023px) {\n  .v2-find-proj-toggle" in css),
            "impact secondary hidden only under 700px": ({"v2.css": (css.replace("@media (max-width: 767px) {\n  .v2-find-impact-more", "@media (max-width: 700px) {\n  .v2-find-impact-more"), "text/css")}, ((767, 1024),), "@media (max-width: 767px) {\n  .v2-find-impact-more" in css),
            "basis header unchanged": ({"finder.js": (js.replace('label: custom ? `DDF Value (${basis.label})` : "DDF Value"', 'label: "DDF Value"'), "text/javascript")}, ((1440, 900),), 'label: custom ? `DDF Value (${basis.label})` : "DDF Value"' in js),
            "market tooltip without the rescaling": ({"finder.js": (js.replace("return `${VIEW_TIPS.market} Rescaled to ${name}'s point scale.`;", "return VIEW_TIPS.market;"), "text/javascript")}, ((1440, 900),), "return `${VIEW_TIPS.market} Rescaled to ${name}'s point scale.`;" in js),
            "fit line without its tooltip": ({"finder.js": (js.replace("fitLine.title = fitTip(fit.variant);", ""), "text/javascript")}, ((1440, 900),), "fitLine.title = fitTip(fit.variant);" in js),
            "chip tooltip is the old label": ({"finder.js": (js.replace('"data-kind": kind, title: tip,', '"data-kind": kind, title: label,'), "text/javascript")}, ((1440, 900),), '"data-kind": kind, title: tip,' in js),
            "no secondary impact line": ({"finder.js": (js.replace('"data-line": "secondary"', '"data-line": "secondary", hidden: ""'), "text/javascript")}, ((1440, 900),), '"data-line": "secondary"' in js),
        }
        for name, (overrides, viewports, anchored) in cases.items():
            with self.subTest(name):
                self.assertTrue(anchored, f"stale anchor for {name!r}")
                self.assertTrue(broken(overrides, viewports), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
