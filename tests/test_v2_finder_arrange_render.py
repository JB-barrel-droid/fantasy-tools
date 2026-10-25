"""v2 Find a trade, arranging the two rosters (JEG-854), rendered.

A pasted-in matchup can land its two teams on the wrong sides, so fixing the assignment must be one tap. On the
Find a trade tab, with two rosters typed in and results showing, this checks (1440 and 375 wide):

  * Swap teams exchanges Your roster and Their roster wholesale, and the shown results are recomputed from the
    new assignment: every listed trade gives only players now on Your roster and receives only players now on
    Their roster (a stale list would still name the old sides);
  * the Move control on a row sends that player to the other roster; ticking several rows and choosing
    "Move N selected to the other team" sends them all; results are recomputed again;
  * Undo puts back the rosters before the last swap or move and the results with them;
  * Swap, Undo, Move, Move selected and the row tick boxes are at least 44 px, and Swap works from the keyboard;
  * no page errors, no sideways scroll.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the swap not exchanging, the results not
recomputed after a swap, and Undo doing nothing, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, PICK, add
from tests.test_v2_modules_render import _built_dist, _serve


def setUpModule():
    _render_env.ensure_built()


STATE = """() => {
  const names = id => [...document.querySelectorAll(`#${id} li b`)].map(b => b.textContent);
  const out = document.getElementById('v2FindOut');
  const items = [...document.querySelectorAll('#v2FindList li')].map(li => {
    const [give, get] = li.querySelector('b').textContent.replace('You give ', '').split('; you receive ').map(s => s.split(' + '));
    return {give, get};
  });
  return {mine: names('v2FindMinePlayers'), theirs: names('v2FindTheirsPlayers'), items, outShown: !out.hidden && out.childElementCount > 0,
    outText: out.textContent.trim().slice(0, 120)};
}"""

SIZES = """() => {
  const small = [];
  const check = (what, node) => { const b = node.getBoundingClientRect(); if (b.width < 43.5 || b.height < 43.5) small.push(`${what} ${Math.round(b.width)}x${Math.round(b.height)}`); };
  ['v2FindSwap', 'v2FindUndo', 'v2FindMineMoveSel', 'v2FindTheirsMoveSel'].forEach(id => check(id, document.getElementById(id)));
  const row = document.querySelector('#v2FindMinePlayers li');
  check('move', row.querySelector('.v2-find-move'));
  check('remove', row.querySelector('.v2-find-remove'));
  check('tick', row.querySelector('.v2-find-tick'));
  return small;
}"""


def stale(tag, state, label):
    """Errors when a listed trade does not give from Your roster and receive from Their roster."""
    errors = []
    for item in state["items"]:
        if not set(item["give"]) <= set(state["mine"]) or not set(item["get"]) <= set(state["theirs"]):
            errors.append(tag + f"{label}: result names players on the wrong side: {item}")
            break
    return errors


def check(page, tag) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(300)
    first = page.evaluate(STATE)
    if not first["outShown"]:
        return [tag + "no result to start from"]
    page.click("#v2FindEdit")   # JEG-972: Find folds the roster input away; reopen it to arrange the teams
    if page.evaluate("() => document.getElementById('v2FindUndo').disabled") is not True:
        errors.append(tag + "Undo is enabled before anything was changed")
    small = page.evaluate(SIZES)
    if small:
        errors.append(tag + f"controls under 44 px: {small}")

    # Swap, from the keyboard.
    page.focus("#v2FindSwap")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    swapped = page.evaluate(STATE)
    if sorted(swapped["mine"]) != sorted(first["theirs"]) or sorted(swapped["theirs"]) != sorted(first["mine"]):
        errors.append(tag + "Swap teams did not exchange the rosters")
    if not swapped["outShown"]:
        errors.append(tag + "results disappeared after a swap instead of being recomputed")
    errors += stale(tag, swapped, "after swap")

    page.click("#v2FindUndo")
    page.wait_for_timeout(300)
    back = page.evaluate(STATE)
    if sorted(back["mine"]) != sorted(first["mine"]) or sorted(back["theirs"]) != sorted(first["theirs"]):
        errors.append(tag + "Undo did not restore the rosters after a swap")
    if back["items"] != first["items"]:
        errors.append(tag + "Undo did not restore the results after a swap")
    if page.evaluate("() => document.getElementById('v2FindUndo').disabled") is not True:
        errors.append(tag + "Undo stays enabled with nothing left to undo")

    # Move one player with the row control.
    mover = first["mine"][0]
    page.click("#v2FindMinePlayers li >> nth=0 >> button.v2-find-move")
    page.wait_for_timeout(300)
    moved = page.evaluate(STATE)
    if mover in moved["mine"] or mover not in moved["theirs"]:
        errors.append(tag + f"Move did not send {mover} to the other team")
    if not moved["outShown"]:
        errors.append(tag + "results disappeared after a move")
    errors += stale(tag, moved, "after move")
    page.click("#v2FindUndo")
    page.wait_for_timeout(200)
    if page.evaluate(STATE)["mine"] != first["mine"]:
        errors.append(tag + "Undo did not put the moved player back")

    # Move several with the tick boxes.
    page.check("#v2FindTheirsPlayers li >> nth=0 >> input.v2-find-pick")
    page.check("#v2FindTheirsPlayers li >> nth=1 >> input.v2-find-pick")
    label = page.text_content("#v2FindTheirsMoveSel")
    if "2 selected" not in label:
        errors.append(tag + f"the move-selected button does not count the ticked rows: {label!r}")
    two = first["theirs"][:2]
    page.click("#v2FindTheirsMoveSel")
    page.wait_for_timeout(300)
    multi = page.evaluate(STATE)
    if not all(n in multi["mine"] and n not in multi["theirs"] for n in two):
        errors.append(tag + f"Move selected did not send {two} to the other team")
    errors += stale(tag, multi, "after move selected")
    if page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "horizontal overflow")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (375, 812))) -> list[str]:
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
                errors += check(page, f"[{width}px] ")
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class FinderArrangeRenderTest(unittest.TestCase):
    def test_swap_move_undo(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "swap does not exchange": js.replace("[S.mine, S.theirs] = [S.theirs, S.mine];", "[S.mine, S.theirs] = [S.mine, S.theirs];", 1),
            "results not recomputed after a swap": js.replace("    if (had) run();\n", "", 1),
            "undo does nothing": js.replace("  function undoArrange() {\n    if (!S.undo) return;", "  function undoArrange() {\n    return;", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks({"finder.js": body}, viewports=((1440, 900),)), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
