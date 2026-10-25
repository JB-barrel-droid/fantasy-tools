"""One "my roster" across Find a trade (two-team card and league) and Waivers (JEG-1021, store-api.md), rendered.

  * a roster written through the workspace store shows in the two-team card's "Your roster", on the league's marked team and on Waivers;
  * removing a player in the two-team card removes him from the store and from Waivers;
  * an old Waivers-only list (ddf.v2.myRoster) is taken over once, not kept as a second copy.

Discrimination: test_guard_fails_on_broken_builds serves a build where the two-team card does not write to the store, one where Waivers
keeps its own list, and one where the card ignores the store, and requires each to fail.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page, source


def setUpModule():
    _render_env.ensure_built()


PICK = """() => { const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && ['QB','RB','WR','TE'].includes(r.pos));
  const names = new Map(); rows.forEach(r => names.set(r.name, (names.get(r.name) || 0) + 1));
  return rows.filter(r => names.get(r.name) === 1).sort((a, b) => b.values.ddf_value - a.values.ddf_value).slice(0, 4).map(r => ({key: String(r.player_key), name: r.name, pos: r.pos, team: r.team})); }"""
FIND = "() => [...document.querySelectorAll('#v2FindMinePlayers .v2-find-row b')].map(b => b.textContent)"
WAIV = "() => [...document.querySelectorAll('#v2WaiversMineList li b')].map(b => b.textContent)"
STORE = "() => window.TradeValueWorkspace.store.getMyRoster().map(e => e.name)"


def check(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[shared] ")
    picks = page.evaluate(PICK)
    names = [p["name"] for p in picks]
    page.evaluate("(list) => window.TradeValueWorkspace.store.setMyRoster(list)", picks)
    if sorted(page.evaluate(FIND)) != sorted(names):
        errors.append(f"[shared] the two-team card does not show the store's roster: {page.evaluate(FIND)}")
    if page.evaluate("() => document.querySelectorAll('#v2LgTeams > li[data-mine=true]').length") != 1:
        errors.append("[shared] the league has no marked team after setMyRoster")
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_function("() => document.getElementById('v2WaiversMineList')", timeout=20000)
    page.wait_for_timeout(300)
    if sorted(page.evaluate(WAIV)) != sorted(names):
        errors.append(f"[shared] Waivers does not show the store's roster: {page.evaluate(WAIV)} vs {names}")
    # Removing a player in the two-team card reaches the store and Waivers.
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_selector("#v2FindMinePlayers .v2-find-remove")
    page.locator("#v2FindMinePlayers .v2-find-row").first.locator(".v2-find-remove").click()
    if len(page.evaluate(STORE)) != len(names) - 1:
        errors.append(f"[shared] a removal in the two-team card did not reach the store: {page.evaluate(STORE)}")
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_timeout(400)
    if sorted(page.evaluate(WAIV)) != sorted(page.evaluate(STORE)):
        errors.append(f"[shared] Waivers differs from the store after a removal: {page.evaluate(WAIV)}")
    # A change on the Waivers side is the same list on Find a trade.
    page.evaluate("() => window.TradeValueWorkspace.store.setMyRoster(window.TradeValueWorkspace.store.getMyRoster().slice(0, 1))")
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_timeout(300)
    if len(page.evaluate(FIND)) != 1:
        errors.append(f"[shared] the two-team card did not follow the store: {page.evaluate(FIND)}")
    page.context.close()
    # The old Waivers-only list is taken over once.
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[migrate] ",
                     init_script="try { if (!sessionStorage.getItem('m')) { sessionStorage.setItem('m', '1'); localStorage.setItem('ddf.v2.myRoster', JSON.stringify([]));} } catch (e) {}")
    page.evaluate("(list) => localStorage.setItem('ddf.v2.myRoster', JSON.stringify(list))", picks[:2])
    page.reload(wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=30000)
    page.evaluate("() => { location.hash = '#waivers'; }")
    page.wait_for_timeout(600)
    if sorted(page.evaluate(STORE)) != sorted(names[:2]):
        errors.append(f"[migrate] the old Waivers list was not taken over: {page.evaluate(STORE)}")
    page.context.close()


def run_checks(overrides=None) -> list[str]:
    errors: list[str] = []
    with browser_on_build() as (browser, base):
        check(browser, base, overrides, errors)
    return errors


def caught(overrides):
    from playwright.sync_api import Error as PlaywrightError
    try:
        return run_checks(overrides)
    except PlaywrightError as exc:
        return [f"checks could not finish: {str(exc).splitlines()[0]}"]


class SharedRosterRenderTest(unittest.TestCase):
    def test_one_my_roster(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        finder = source("finder.js")
        waivers = source("waivers.js")
        broken = {
            "the two-team card does not write to the store": {"finder.js": finder.replace("const mineChanged = () => { pushMine();", "const mineChanged = () => {", 1)},
            "Waivers keeps its own list": {"waivers.js": waivers.replace("get: () => WS().getMyRoster(),", "get: () => (window.__own = window.__own || []),", 1).replace("set: list => { WS().setMyRoster(list); },", "set: list => { window.__own = list; },", 1)},
            "the two-team card ignores the store": {"finder.js": finder.replace("const pullMine = () => {", "const pullMine = () => { return;", 1)},
        }
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                key = next(iter(overrides))
                self.assertNotEqual(overrides[key], source(key), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(caught(overrides), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
