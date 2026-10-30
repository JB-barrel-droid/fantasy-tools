"""JEG-1380 (correction for #1012, JEG-1178): Find a trade re-runs its results when the viewed week changes.

During a week transition the page can show either week. Find a trade re-runs its listed trades only on the
`ddf:league-settings-changed` event, and before this fix neither a week change from the selector nor the week of a
`wk=` link sent it. The page then showed the new week's values while the listed trades and their edges were still the
old week's. Weekly values are never blended with ROS; the finder only has to reprice from the week the page shows.

Both checks run the 57% transition from tests/test_week_selector_render.py (default Week NEWER, Week OLDER on offer):
1. Selector: run Find a trade, pick the other week; every listed edge must equal the new week's DDF Value sums,
   and the finder's note names the week.
2. Link: open #find-trade?mine=..&theirs=..&size=3&wk=OLDER in a fresh tab; the edges must be Week OLDER's.

A guard checks that the two weeks really price the picked players differently, so the check can fail at all.
Both checks fail on main before the fix: the edges stay on the previous week's values.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env  # noqa: F401
from tests.test_v2_finder_render import PICK, READ, add
from tests.test_week_history import _fixture_today
from tests.test_week_selector_render import (BEFORE_NOON, NEWER, OLDER, READY, SCENARIOS, launch, open_page,
                                             pick_week, served_dist, sync_playwright, transition_index)

ENGINE_WEEK = "() => window.TradeValueCurveControls.getWeekState().week"
KEYS = """names => {
  const byName = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r]));
  return names.map(n => String(byName.get(n).player_key));
}"""
DDF = """names => {
  const byName = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r]));
  return names.map(n => (byName.get(n) && byName.get(n).values ? byName.get(n).values.ddf_value : null));
}"""
NOTE = "() => (document.getElementById('v2FindSettingsNote') || {}).textContent || ''"


def setUpModule():
    _render_env.ensure_built()


def edge_errors(tag, got, week, engine_week) -> list[str]:
    """Every listed trade's shown edge must be the DDF Value sum at the week the page shows."""
    errors = []
    if engine_week != week:
        errors.append(f"{tag}: page shows Week {engine_week}, expected Week {week}")
    if not got["items"]:
        errors.append(f"{tag}: no trades listed: {got['out'][:200]!r}")
    for item in got["items"]:
        if abs(item["edge"] - item["shownEdge"]) > 1e-6:
            errors.append(f"{tag}: listed edge {item['shownEdge']:.3f} is not Week {week}'s {item['edge']:.3f}: "
                          f"{item['give']} -> {item['get']}")
    return errors


def open_finder(page):
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)


def week_checks() -> list[str]:
    errors: list[str] = []
    spec = SCENARIOS["57%"]
    with sync_playwright() as playwright:
        browser = launch(playwright)
        try:
            with served_dist({"assets/history/index.json": transition_index(spec["lagging"])}) as (base, _dist):
                page = open_page(browser, base, 1366, 768)
                if page.evaluate(ENGINE_WEEK) != NEWER:
                    return [f"the 57% scenario should open on Week {NEWER}, got Week {page.evaluate(ENGINE_WEEK)}"]
                open_finder(page)
                pick = page.evaluate(PICK)
                names = pick["mine"] + pick["theirs"]
                newer_values = page.evaluate(DDF, names)
                for name in pick["mine"]:
                    add(page, "Mine", name)
                for name in pick["theirs"]:
                    add(page, "Theirs", name)
                page.select_option("#v2FindSize", "3")
                page.click("#v2FindGo")
                page.wait_for_timeout(400)
                errors += edge_errors(f"Week {NEWER} before any change", page.evaluate(READ), NEWER, page.evaluate(ENGINE_WEEK))

                # 1. The selector moves the page to the older week; the listed trades must follow.
                pick_week(page, OLDER)
                page.wait_for_timeout(600)
                older_values = page.evaluate(DDF, names)
                moved = sum(abs(a - b) for a, b in zip(newer_values, older_values) if a is not None and b is not None)
                if moved < 0.5:
                    errors.append(f"guard: the picked players price almost the same in both weeks (total move {moved:.2f}); "
                                  "the check cannot fail")
                errors += edge_errors(f"selector to Week {OLDER}", page.evaluate(READ), OLDER, page.evaluate(ENGINE_WEEK))
                note = page.evaluate(NOTE)
                if f"Week {OLDER}" not in note:
                    errors.append(f"selector to Week {OLDER}: the finder note does not name the week: {note!r}")
                pick_week(page, NEWER)
                page.wait_for_timeout(600)
                errors += edge_errors(f"selector back to Week {NEWER}", page.evaluate(READ), NEWER, page.evaluate(ENGINE_WEEK))
                mine_keys = page.evaluate(KEYS, pick["mine"])
                theirs_keys = page.evaluate(KEYS, pick["theirs"])
                page.close()

                # 2. A wk= link that carries rosters, opened in a fresh tab with no session memory.
                link = (base + f"#find-trade?mine={','.join(mine_keys)}&theirs={','.join(theirs_keys)}"
                        f"&size=3&wk={OLDER}")
                fresh = browser.new_context(viewport={"width": 1366, "height": 768}).new_page()
                fresh.add_init_script(f"window.TRADE_VALUE_TODAY = {json.dumps(_fixture_today())};"
                                      f"window.TRADE_VALUE_NOW = {json.dumps(BEFORE_NOON)};")
                fresh.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                fresh.goto(link, wait_until="networkidle", timeout=120000)
                fresh.wait_for_function(READY, timeout=60000)
                fresh.wait_for_timeout(800)
                errors += edge_errors(f"wk={OLDER} link with rosters", fresh.evaluate(READ), OLDER, fresh.evaluate(ENGINE_WEEK))
                fresh.close()
        finally:
            browser.close()
    return errors


class FinderWeekChangeRenderTest(unittest.TestCase):
    def test_find_a_trade_follows_the_viewed_week(self):
        self.assertEqual(week_checks(), [])


if __name__ == "__main__":
    unittest.main()
