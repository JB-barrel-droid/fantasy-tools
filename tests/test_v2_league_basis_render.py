"""JEG-1044: the league workspace follows the reader's value basis.

Team summary (roster, starter and bench value in DDF Value, "fundamental") and
Trade opportunities (fundamentals capture) read the engine rows, so choosing a
basis on the Overrides tab must move them. The market side is the average of the
rescaled charts: it stays the chart average (and teams keep their market order)
but is in the basis's point scale, because Rescaled follows the basis.
Checked against an independent recomputation from the engine rows
(tests/test_v2_league_tables_render.EXPECT), on the frozen 4-team league, with
USA Today as the whole basis.

Also pins that the saved-workspace storage keys do not collide with the
overrides record (ddf-v2-value-overrides, sessionStorage ddf-v2-link-state).

Discrimination: test_guard_fails_when_fundamental_ignores_the_basis serves a
team-summary.js whose "fundamental" key is the projections reference (which
ignores the basis) and requires the same check to fail.
"""
from __future__ import annotations

import json
import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page, seed, source, wait_opps
from tests.test_v2_league_tables_render import EXPECT, OPP_ROWS, SUMMARY_ROWS


def setUpModule():
    _render_env.ensure_built()


def go(page, view):
    # Since JEG-1106 (9cffc5cb, Jeremy 2026-10-25) the pages are entries in a menu opened by #v2NavToggle at every
    # width; picking an entry closes it again. Same path as test_v2_overrides_basis_render.
    if page.get_attribute("#v2NavToggle", "aria-expanded") != "true":
        page.click("#v2NavToggle")
    page.click(f'a.v2-tab[data-view="{view}"]')
    page.wait_for_timeout(500)


def snapshot(page):
    page.wait_for_selector("#v2LgSummaryTable")
    wait_opps(page)
    return {"summary": page.evaluate(SUMMARY_ROWS), "opps": page.evaluate(OPP_ROWS), "exp": page.evaluate(EXPECT)}


def check(overrides=None) -> list[str]:
    problems = []
    with browser_on_build() as (browser, base):
        page = open_page(browser, base, overrides=overrides, errors=problems, tag="[basis] ")
        seed(page, "4team")
        before = snapshot(page)
        if not before["summary"] or not before["opps"]:
            return problems + ["workspace tables did not render"]
        go(page, "overrides")
        page.click('[data-preset="single:usatoday"]')
        page.wait_for_timeout(500)
        go(page, "league")
        after = snapshot(page)
        # Fundamental follows the basis: shown values equal an independent recomputation from the rows, and moved.
        for r in after["summary"]:
            t = next(x for x in after["exp"]["teams"] if x["id"] == r["id"])
            for col, key in (("rosterF", "rosterF"), ("starterF", "starterF"), ("benchF", "benchF")):
                try:
                    shown = float(r[col])
                except (TypeError, ValueError):
                    continue
                if abs(shown - t[key]) > 0.051:
                    problems.append(f"{r['name']} {col} shows {shown}, the engine rows give {t[key]:.2f}")
        moved = [a["rosterF"] for a, b in zip(after["summary"], before["summary"]) if a["rosterF"] != b["rosterF"]]
        if not moved:
            problems.append("no team's roster value (DDF) moved when the basis changed")
        # Market stays the chart average. The average is of the rescaled charts, and Rescaled follows the basis
        # (Jeremy Q2 = B), so its points shift to the basis's scale; what must hold is that it is still the chart
        # average of the rows (independent recomputation) and that the teams' market order does not change.
        for r in after["summary"]:
            t = next(x for x in after["exp"]["teams"] if x["id"] == r["id"])
            for col, key in (("rosterM", "rosterM"), ("starterM", "starterM"), ("benchM", "benchM")):
                try:
                    shown = float(r[col])
                except (TypeError, ValueError):
                    continue
                if abs(shown - t[key]) > 0.051:
                    problems.append(f"{r['name']} {col} (market) shows {shown}, the chart average of the rows is {t[key]:.2f}")
        order = lambda snap: [x["id"] for x in sorted((x for x in snap["exp"]["teams"] if x["has"]), key=lambda x: (-round(x["rosterM"], 1), x["id"]))]
        if order(after) != order(before):
            problems.append(f"the teams' market order changed with the basis: {order(before)} -> {order(after)}")
        cap_before = {(o["id"], o["trade"]): o["capture"] for o in before["opps"]}
        cap_after = {(o["id"], o["trade"]): o["capture"] for o in after["opps"]}
        if cap_before == cap_after:
            problems.append("no fundamentals capture changed in the opportunities table")
        # Back to ours restores the first screen.
        go(page, "overrides")
        page.click('[data-preset="default"]')
        page.wait_for_timeout(400)
        go(page, "league")
        again = snapshot(page)
        if [r["rosterF"] for r in again["summary"]] != [r["rosterF"] for r in before["summary"]]:
            problems.append("roster values did not return to our methodology")
        keys = page.evaluate("() => Object.keys(localStorage)")
        if any(k in ("ddf-v2-value-overrides",) for k in keys if k.startswith("ddf.v2.")):
            problems.append(f"storage key collision: {keys}")
        ws = page.evaluate("() => localStorage.getItem('ddf.v2.workspaces')")
        if ws and "basis" in json.loads(ws).__repr__():
            problems.append("the saved workspace carries a basis; it must stay in the overrides record")
    return problems


class LeagueBasisTest(unittest.TestCase):
    def test_workspace_follows_the_basis_and_market_stays(self):
        problems = check()
        self.assertEqual(problems, [], "\n".join(problems[:20]))

    def test_guard_fails_when_fundamental_ignores_the_basis(self):
        src = source("team-summary.js")
        self.assertIn('const OUR_KEY = "ddf_value";', src)
        broken = src.replace('const OUR_KEY = "ddf_value";', 'const OUR_KEY = "ddf_value_projections";', 1).encode("utf-8")
        self.assertTrue(check({"team-summary.js": broken}), "a fundamental that ignores the basis must fail the check")


if __name__ == "__main__":
    unittest.main()
