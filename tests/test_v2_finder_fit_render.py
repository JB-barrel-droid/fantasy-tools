"""v2 Find a trade v2 (JEG-988), commit 4: natural / market supported / force fit on the groups, rendered.

Two real roster pages (the Yahoo and ESPN team fixtures) go through Find trades at 1440 and 390 wide, with packages of up
to 3. Checked against the finder's own pure functions run in the page:

  * every group card carries a fit line ("Natural fit:", "Market supported:" or "Force fit:") that names both teams' net change in
    their own view (you: DDF Value, they: the trade chart average);
  * the order is natural fits first, then market supported, then force; inside a tier the groups keep the edge ranking; and nothing
    else changes: with every group shown, the set of group edges equals the groups the search finds without the tiering
    (no group added, dropped or re-valued);
  * the thin-roster case: a team whose only RB1 is a star gives him for two RB2s from a deep team. The search lists the
    1-for-2 package, the roster impact shows the thin team's best-lineup starter value rising, and the card says why;
  * no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the tier ordering off, with the fit line not drawn
and with the 1-for-2 package left out of the search, and requires each to fail.
"""
from __future__ import annotations

import functools
import re
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_box_render import FIXTURE, OVER
from tests.test_v2_finder_eval_render import ESPN
from tests.test_v2_finder_render import FINDER_JS, _built_dist, add
from tests.test_v2_modules_render import _serve


def setUpModule():
    _render_env.ensure_built()


# Groups as the search finds them, with no tiering: the edges to compare against, from the page's own pure functions.
BASELINE = """() => {
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder;
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  const names = id => [...document.querySelectorAll(`#${id} li.v2-find-row b`)].map(b => b.textContent).filter(n => byName.has(n));
  const mine = names('v2FindMinePlayers').map(n => byName.get(n)), theirs = names('v2FindTheirsPlayers').map(n => byName.get(n));
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = F.CHART_KEYS.filter(k => avail.has(k));
  const shape = C.getRosterShape();
  const size = Number(document.getElementById('v2FindSize').value);
  const res = F.findTrades(mine, theirs, {chartKeys: charts, maxSize: size, limit: 1e7, sanity: {shape, mine, theirs, keepMine: true, keepTheirs: true}});
  return F.groupTrades(res.trades, {ourKey: res.ourKey}).map(g => g.bestEdge);
}"""
SHOWN = """() => [...document.querySelectorAll('#v2FindList li.v2-find-group')].map(li => ({fit: li.dataset.findFit || null, edge: Number(li.dataset.findEdge),
  line: (li.querySelector('.v2-find-fit') || {}).textContent || '', visible: Boolean(li.querySelector('.v2-find-fit')) && li.querySelector('.v2-find-fit').getBoundingClientRect().height > 0}))"""
# A star RB and two RB2s whose DDF Value sums just above his, with at least three charts saying the thin team breaks even or wins.
THIN = """() => {
  const C = window.TradeValueCurveControls;
  const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
  const charts = ['usatoday', 'fantasycalc', 'fantasypros', 'cbs'].filter(k => avail.has(k));
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && charts.every(k => Number.isFinite(r.values[k])));
  const uniq = rows.filter(r => rows.filter(x => x.name === r.name).length === 1);
  const by = pos => uniq.filter(r => r.pos === pos).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const rbs = by('RB'), wrs = by('WR'), qbs = by('QB'), tes = by('TE');
  for (const s of rbs.slice(0, 14)) for (let i = 0; i < rbs.length; i++) for (let j = i + 1; j < rbs.length; j++) {
    const a = rbs[i], b = rbs[j];
    if (a === s || b === s || a.values.ddf_value < 8 || b.values.ddf_value < 8) continue;
    const dd = a.values.ddf_value + b.values.ddf_value - s.values.ddf_value;
    if (dd <= 0.2 || dd > 4) continue;
    if (charts.filter(k => a.values[k] + b.values[k] - s.values[k] <= 0.05).length < 3) continue;
    const used = new Set([s.name, a.name, b.name]);
    const take = (list, n, from) => list.filter(r => !used.has(r.name)).slice(from, from + n).map(r => { used.add(r.name); return r.name; });
    const thin = [s.name].concat(take(qbs, 2, 6), take(wrs, 4, 8), take(tes, 1, 8));
    const deep = [a.name, b.name].concat(take(rbs, 4, 3), take(wrs, 4, 0), take(qbs, 2, 0), take(tes, 2, 0));
    return {star: s.name, a: a.name, b: b.name, thin, deep};
  }
  return null;
}"""


def orientation(page, tag, swap) -> list[str]:
    """Yahoo as mine and ESPN as theirs has no natural group on current data; the swap lists groups of at least two different fits,
    which is what makes the tier-order assertion test something."""
    errors = []
    tag = f"{tag}{'ESPN mine / Yahoo theirs: ' if swap else 'Yahoo mine / ESPN theirs: '}"
    say = lambda what: errors.append(tag + what)
    if swap:
        if page.locator("#v2FindInput").is_hidden():
            page.click("#v2FindEdit")
        for side in ("Mine", "Theirs"):
            page.click(f"#v2Find{side}Clear")
    page.fill("#v2FindMineSearch", (ESPN if swap else FIXTURE).read_text(encoding="utf-8"))
    page.fill("#v2FindTheirsSearch", (FIXTURE if swap else ESPN).read_text(encoding="utf-8"))
    page.wait_for_timeout(400)
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(1200)
    more = page.locator("#v2FindMoreGroups")
    if more.count():
        more.click()
        page.wait_for_timeout(300)
    shown = page.evaluate(SHOWN)
    base = page.evaluate(BASELINE)
    if not shown:
        say("no groups listed")
        return errors
    kinds = {g["fit"] for g in shown}
    if swap and len(kinds & {"natural", "market", "force"}) < 2:
        say(f"the swapped rosters must list groups of at least two different fits so the tier order is exercised, got {sorted(map(str, kinds))}: the guard would test nothing")
    if not all(g["visible"] for g in shown):
        say("a group's fit line is not visible")
    if any(g["fit"] is None or not re.match(r"^(Natural fit|Market supported|Force fit)(?: · [A-Za-z -]+ viability)?:", g["line"]) for g in shown):
        say(f"a group has no fit line: {[g['line'][:30] for g in shown if g['fit'] is None][:3]}")
    for g in shown:
        if g["fit"] == "natural" and ("DDF Value" not in g["line"] or "trade chart average" not in g["line"]):
            say(f"a natural line does not name both views: {g['line'][:140]}")
        if g["fit"] == "market" and "trade charts favor them" not in g["line"]:
            say(f"a market supported line does not say the charts favor them: {g['line'][:140]}")
    tiers = [{"natural": 0, "market": 1, "force": 2}[g["fit"]] for g in shown if g["fit"]]
    if tiers != sorted(tiers):
        say(f"tiers are not natural, market supported, force in order: {[g['fit'] for g in shown]}")
    for tier in (0, 1, 2):
        edges = [g["edge"] for g, t in zip(shown, tiers) if t == tier]
        if edges != sorted(edges, reverse=True):
            say(f"tier {tier} is not in edge order: {[round(e, 2) for e in edges]}")
    # The finder lists at most two groups per received player and folds the rest into a "N more for <player>" note, so
    # the shown groups are a subset of the search's groups (none added, none re-valued) and every missing group is
    # counted in those notes (none lost silently).
    base_left = [round(e, 6) for e in base]
    added = []
    for g in shown:
        edge = round(g["edge"], 6)
        if edge in base_left:
            base_left.remove(edge)
        else:
            added.append(round(g["edge"], 2))
    if added:
        say(f"shown group edges {added} are not in the search's groups: values changed or groups invented")
    folded = sum(int(n) for n in re.findall(r"(\d+) more for ", page.locator("#v2FindOut").inner_text()))
    if len(base_left) != folded:
        say(f"{len(base_left)} groups are in the search but not listed, and the notes fold {folded}: groups lost or miscounted")
    return errors


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste && window.TradeValueFinder", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    errors += orientation(page, tag, False)
    errors += orientation(page, tag, True)
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow")
    if width > 390:
        errors += thin_case(page, tag)
    return errors


def thin_case(page, tag) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    case = page.evaluate(THIN)
    if not case:
        say("no star RB and two RB2s in the data for the thin-roster case")
        return errors
    if page.locator("#v2FindInput").is_hidden():
        page.click("#v2FindEdit")
    for side in ("Mine", "Theirs"):
        page.click(f"#v2Find{side}Clear")
    for name in case["thin"]:
        add(page, "Mine", name)
    for name in case["deep"]:
        add(page, "Theirs", name)
    page.select_option("#v2FindSize", "2")
    page.click("#v2FindGo")
    page.wait_for_timeout(1200)
    listed = page.evaluate("""([star, a, b]) => {
      const F = window.TradeValueFinder, C = window.TradeValueCurveControls;
      const byName = new Map(C.getAllRows().map(r => [r.name, r]));
      const names = id => [...document.querySelectorAll(`#${id} li.v2-find-row b`)].map(x => x.textContent).filter(n => byName.has(n));
      const mine = names('v2FindMinePlayers').map(n => byName.get(n)), theirs = names('v2FindTheirsPlayers').map(n => byName.get(n));
      const avail = new Set(C.getSourceInfo().filter(i => i.available).map(i => i.key));
      const res = F.findTrades(mine, theirs, {chartKeys: F.CHART_KEYS.filter(k => avail.has(k)), maxSize: 2, limit: 1e7});
      return res.trades.some(t => t.give.length === 1 && t.give[0].name === star && t.receive.length === 2 && t.receive.some(r => r.name === a) && t.receive.some(r => r.name === b));
    }""", [case["star"], case["a"], case["b"]])
    if not listed:
        say(f"the search does not generate the 1-for-2 package {case['star']} for {case['a']} + {case['b']}")
        return errors
    if page.locator("#v2FindMoreGroups").count():
        page.click("#v2FindMoreGroups")
        page.wait_for_timeout(300)
    # The group whose core is the better RB2: tick exactly the star on your side and both RB2s on theirs, then read the card.
    card = page.locator(f"li.v2-find-group:has(.v2-find-target-name:text-is('{case['a']}'))").first
    if not card.count():
        say(f"no group for the target {case['a']}")
        return errors
    for box in card.locator("fieldset:has(legend:text-is('You give')) input[type=checkbox]").all():
        label = box.get_attribute("aria-label") or ""
        want = case["star"] in label
        if want and not box.is_checked():
            box.check()
        elif not want and box.is_checked() and not box.is_disabled():
            box.uncheck()
    for box in card.locator("fieldset:has(legend:has-text('You also receive')) input[type=checkbox]").all():
        label = box.get_attribute("aria-label") or ""
        want = case["b"] in label
        if want and not box.is_checked():
            box.check()
        elif not want and box.is_checked():
            box.uncheck()
    page.wait_for_timeout(300)
    label = card.locator(".v2-find-trade").text_content()
    if label != f"You give {case['star']}; you receive {case['a']} + {case['b']}":
        say(f"the card reads {label!r}, not the 1-for-2 package")
        return errors
    impact = card.locator(".v2-find-impact-line").first.text_content()
    m = re.search(r"DDF Value ([0-9.]+) → ([0-9.]+) \(([+-][0-9.]+)\)", impact)
    if not m or float(m.group(3)) <= 0 or float(m.group(2)) <= float(m.group(1)):
        say(f"the thin team's starter value does not rise in the impact lines: {impact!r}")
    fit = card.locator(".v2-find-fit").text_content()
    if not re.match(r"^(Natural fit|Market supported|Force fit)(?: · [A-Za-z -]+ viability)?:", fit) or "DDF Value" not in fit:
        say(f"the 1-for-2 card has no fit reading: {fit[:120]!r}")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844), (320, 640))) -> list[str]:
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
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


def broken(overrides) -> bool:
    try:
        return bool(run_checks(overrides, viewports=((1440, 900),)))
    except Exception:
        return True


class FinderFitRenderTest(unittest.TestCase):
    def test_fit(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        cases = {
            "tier ordering off": ("if (fitCtx) groups = tierGroups(", "if (false) groups = tierGroups("),
            "fit line not drawn": ("fitLine.hidden = !fit;", "fitLine.hidden = true;"),
            "tier order reversed": ("a.t - b.t || a.i - b.i", "b.t - a.t || a.i - b.i"),
            "folded groups not counted in the note": ("folded.set(ck, (folded.get(ck) || 0) + 1);", "void 0;"),
            "two-player packages not searched": ("const mineSubs = subsets(mineP.rows.length, maxSize)", "const mineSubs = subsets(mineP.rows.length, 1)"),
        }
        for name, (old, new) in cases.items():
            with self.subTest(name):
                self.assertIn(old, js, f"stale anchor for {name!r}")
                self.assertTrue(broken({"finder.js": js.replace(old, new, 1)}), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
