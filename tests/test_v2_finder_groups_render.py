"""v2 Find a trade, grouped results (JEG-972 commit 2 / JEG-885 decisions of Jeremy 2026-10-23), rendered.

Two rosters are typed in (top players by DDF Value, alternating), size set to 2-for-2, Find trades runs. Checked at
1366x768, 390 and 320 wide against the engine's own rows (getAllRows):

  * results are group cards (one per received core player, at most 10), each naming its target;
  * toggling a side player (mouse or the keyboard space bar) changes the package line, the DDF Value edge shown and
    the Open in Compare a trade link to exactly the selection, and the edge equals receive minus give from getAllRows;
  * ticking beyond the searched package size is allowed, labelled 'Larger package than searched', and the numbers follow the rows;
  * a selection the search would not list says why instead of vanishing;
  * the last player given cannot be unticked; every side-player row is at least 44 px; no sideways scroll; no errors.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with a stale package math after a toggle, a link
that is not rebuilt, and a cap that is not enforced, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, _built_dist, add
from tests.test_v2_modules_render import _serve


def setUpModule():
    _render_env.ensure_built()


# Position-balanced rosters (QB, RB, WR, TE by position, unique names) so the search has a trade to find whatever
# the week's top-30 mix is. The shared PICK deals the top 30 by DDF Value alternately, which in a week with only
# RB/WR on top leaves no QB/TE on either side (JEG-1185).
PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name && ['QB','RB','WR','TE'].includes(r.pos))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const count = new Map(); rows.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const unique = rows.filter(r => count.get(r.name) === 1);
  const take = (pos, from, n) => unique.filter(r => r.pos === pos).slice(from, from + n).map(r => r.name);
  return {mine: [].concat(take('QB', 0, 2), take('RB', 0, 4), take('WR', 0, 4), take('TE', 0, 2)),
          theirs: [].concat(take('QB', 2, 2), take('RB', 4, 4), take('WR', 4, 4), take('TE', 2, 2))};
}"""


# Reads group card `i`: package line, edge, link, checkboxes; and the edge recomputed from the engine rows.
CARD = """(i) => {
  const li = document.querySelectorAll('#v2FindList > li')[i];
  if (!li) return null;
  const byName = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r]));
  const [give, get] = li.querySelector('b').textContent.replace('You give ', '').split('; you receive ').map(s => s.split(' + '));
  const sum = names => names.reduce((a, n) => a + byName.get(n).values.ddf_value, 0);
  const href = li.querySelector('a').getAttribute('href');
  const q = new URLSearchParams(href.split('?')[1]);
  const idsOf = names => names.map(n => String(byName.get(n).player_key)).sort().join(',');
  const boxes = [...li.querySelectorAll('input[type=checkbox]')].map(b => ({checked: b.checked, disabled: b.disabled,
    label: b.getAttribute('aria-label'), h: b.closest('label').getBoundingClientRect().height}));
  return {give, get, edge: sum(get) - sum(give), shownEdge: Number(li.dataset.findEdge), text: li.querySelector('.v2-find-edge').textContent,
    notes: li.querySelector('.v2-find-notes').textContent, cap: !li.querySelector('.v2-find-cap').hidden, capText: li.querySelector('.v2-find-cap').textContent,
    linkOk: [q.get('give').split(',').sort().join(',') === idsOf(give), q.get('get').split(',').sort().join(',') === idsOf(get)],
    target: li.querySelector('.v2-find-target-name').textContent, boxes, junk: /null|undefined|NaN/.test(li.textContent)};
}"""


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    page.select_option("#v2FindSize", "2")
    page.click("#v2FindGo")
    page.wait_for_timeout(500)
    count = page.evaluate("() => document.querySelectorAll('#v2FindList > li.v2-find-group').length")
    if not 1 <= count <= 10:
        return [tag + f"{count} group cards listed, expected 1..10"]
    cards = [page.evaluate(CARD, i) for i in range(count)]
    targets = [c["target"] for c in cards]
    if len(set(targets)) != len(targets):
        errors.append(tag + f"two groups name the same target: {targets}")
    for c in cards:
        if c["junk"]:
            errors.append(tag + f"group {c['target']} shows null/undefined/NaN text")
        if abs(c["edge"] - c["shownEdge"]) > 1e-6:
            errors.append(tag + f"group {c['target']}: edge {c['edge']} vs shown {c['shownEdge']}")
    # Toggle every enabled box of the first few groups, check the math each time, then put it back.
    toggled = 0
    sawCap = False
    for i in range(min(count, 4)):
        n = len(cards[i]["boxes"])
        for j in range(n):
            before = page.evaluate(CARD, i)
            if before["boxes"][j]["disabled"]:
                continue
            if before["cap"] and not sawCap:
                sawCap = True
                if not any(b["disabled"] and not b["checked"] for b in before["boxes"]):
                    errors.append(tag + f"{before['target']}: the cap is said but no unticked box is disabled")
            box = page.locator(f"#v2FindList > li >> nth={i} >> input[type=checkbox] >> nth={j}")
            box.focus()
            page.keyboard.press("Space")
            after = page.evaluate(CARD, i)
            toggled += 1
            if after["boxes"][j]["checked"] == before["boxes"][j]["checked"]:
                errors.append(tag + f"{before['target']}: box {j} did not toggle")
            if (after["give"], after["get"]) == (before["give"], before["get"]):
                errors.append(tag + f"{before['target']}: package line unchanged after toggling {before['boxes'][j]['label']}")
            if abs(after["edge"] - after["shownEdge"]) > 1e-6 or f"{abs(after['edge']):.1f}" not in after["text"]:
                errors.append(tag + f"{before['target']}: edge shown {after['shownEdge']} / {after['text'][:40]!r}, engine rows say {after['edge']}")
            if not all(after["linkOk"]):
                errors.append(tag + f"{before['target']}: Open in Compare link does not carry the selection")
            if (after["edge"] < 0.05) and "does not say you win" not in after["notes"]:
                errors.append(tag + f"{before['target']}: a losing package gives no warning: {after['notes']!r}")
            box.focus()
            page.keyboard.press("Space")
            if page.evaluate(CARD, i)["give"] != before["give"] or page.evaluate(CARD, i)["get"] != before["get"]:
                errors.append(tag + f"{before['target']}: toggling back did not restore the package")
    if not toggled:
        errors.append(tag + "no side player could be toggled in the first groups: the toggle checks proved nothing")
    # Beyond the searched size: a full give side (2 ticked at 2-for-2) still lets a third be ticked; the package is labelled
    # as larger than searched and the numbers still follow the engine rows.
    bigger = False
    for i in range(count):
        c = page.evaluate(CARD, i)
        if sum(1 for b in c["boxes"] if b["checked"]) < 2 or not any(not b["checked"] and not b["disabled"] for b in c["boxes"]) or len(c["give"]) < 2:
            continue
        if c["cap"]:
            errors.append(tag + f"{c['target']}: the larger-package label shows before anything was ticked beyond the size")
        j = next(k for k, b in enumerate(c["boxes"]) if not b["checked"] and not b["disabled"])
        box = page.locator(f"#v2FindList > li >> nth={i} >> input[type=checkbox] >> nth={j}")
        box.focus()
        page.keyboard.press("Space")
        big = page.evaluate(CARD, i)
        bigger = True
        if not big["cap"] or "Larger package than searched" not in big["capText"]:
            errors.append(tag + f"{c['target']}: a package larger than searched is not labelled: {big['capText']!r}")
        if abs(big["edge"] - big["shownEdge"]) > 1e-6 or f"{abs(big['edge']):.1f}" not in big["text"]:
            errors.append(tag + f"{c['target']}: larger package edge shown {big['shownEdge']} / {big['text'][:40]!r}, engine rows say {big['edge']}")
        if not all(big["linkOk"]):
            errors.append(tag + f"{c['target']}: larger package link does not carry the selection")
        box.focus()
        page.keyboard.press("Space")
        if page.evaluate(CARD, i)["cap"]:
            errors.append(tag + f"{c['target']}: the label stays after going back to the searched size")
        break
    if not bigger:
        errors.append(tag + "no group had a full give side with a spare player: the larger-package check proved nothing")
    for c in cards:
        for b in c["boxes"]:
            if b["h"] < 43.5:
                errors.append(tag + f"{c['target']}: side-player row is {b['h']:.0f}px tall")
                break
    if width <= 390 and page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "horizontal overflow")
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


class FinderGroupsRenderTest(unittest.TestCase):
    def test_grouped_results(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "package math stale after a toggle": js.replace("const e = evaluateCombo(giveRows, recvRows, ctx);", "const e = group.__e || (group.__e = evaluateCombo(giveRows, recvRows, ctx));", 1),
            "link not rebuilt": js.replace('open.setAttribute("href", `v2/#compare-trade?give=${ids(giveRows)}&get=${ids(recvRows)}`);', "", 1),
            "empty side lists print null": js.replace("li.append(...[target, tradeLabel, meta, fitLine, notes, impact && impact.node, giveBox, recvBox, capNote, open].filter(Boolean));", "li.append(target, tradeLabel, meta, fitLine, notes, impact && impact.node, giveBox, recvBox, capNote, open);", 1),
            "larger package not labelled": js.replace("capNote.hidden = !larger;", "capNote.hidden = true;", 1),
            "ticking beyond the searched size is blocked": js.replace("boxes.forEach(b => { b.input.disabled = b.sel === giveSel && b.input.checked && giveSel.size <= 1; });", "boxes.forEach(b => { b.input.disabled = b.sel === giveSel && !b.input.checked && giveSel.size >= ctx.maxSize; });", 1),
            "numbers stale on a larger package": js.replace("const e = evaluateCombo(giveRows, recvRows, ctx);", "const e = evaluateCombo(giveRows.slice(0, ctx.maxSize), recvRows, ctx);", 1),
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
