"""JEG-1098: the league-wide trade opportunities list opens on the top 10.

With a 20-team league (well over 100 offers): 10 rows and "Showing 10 of N" on open; "Show 10 more" adds 10; "Show all (N)"
shows every row; "Show top 10 only" returns; the buttons work from the keyboard; changing the sort keeps the count honest.

Discrimination: test_guard_fails_on_broken_builds serves league.js opening on 20 rows, with the count line dropped,
and with Show all capped at one more page, and requires the checks to fail on each.
"""
from __future__ import annotations

import re
import unittest

from tests._league_render import browser_on_build, open_page, seed, source, wait_opps

ROWS = "() => document.querySelectorAll('#v2LgOppsTable tbody tr.v2-lg-opp').length"
COUNT = "() => (document.getElementById('v2LgOppsCount') || {}).textContent || ''"


def check(browser, base, overrides=None):
    errors = []
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[top10] ")
    seed(page, "20team")
    wait_opps(page, timeout=90000)
    rows, count = page.evaluate(ROWS), page.evaluate(COUNT)
    m = re.fullmatch(r"Showing (\d+) of (\d+)", count.strip())
    total = int(m.group(2)) if m else 0
    if rows != 10 or not m or int(m.group(1)) != 10 or total < 30:
        errors.append(f"open state: {rows} rows, count {count!r}")
    if not page.is_visible("#v2LgOppsAll") or f"Show all ({total})" not in page.inner_text("#v2LgOppsAll"):
        errors.append(f"no 'Show all ({total})' button")
    # Keyboard: focus the button and press Enter.
    page.focus("#v2LgOppsMore")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    rows, count = page.evaluate(ROWS), page.evaluate(COUNT)
    if rows != 20 or count.strip() != f"Showing 20 of {total}":
        errors.append(f"after Show 10 more by keyboard: {rows} rows, {count!r}")
    if page.evaluate("() => document.activeElement && document.activeElement.id") != "v2LgOppsMore":
        errors.append("focus left Show 10 more after pressing it (a keyboard reader cannot press it again)")
    page.focus("#v2LgOppsAll")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    rows, count = page.evaluate(ROWS), page.evaluate(COUNT)
    if rows != total or count.strip() != f"Showing {total} of {total}" or page.is_visible("#v2LgOppsMore"):
        errors.append(f"after Show all: {rows} rows, {count!r}")
    page.click("#v2LgOppsLess")
    if page.evaluate(ROWS) != 10:
        errors.append("Show top 10 only did not return to 10 rows")
    # A filter that leaves few rows: no buttons, an honest count.
    page.select_option("#v2LgFilterFit", "natural")
    page.wait_for_timeout(300)
    rows, count = page.evaluate(ROWS), page.evaluate(COUNT)
    natural = str(page.evaluate("() => window.TradeValueLeague.ui.result.rows.filter(r => r.overall === 'natural').length"))
    counted = re.search(r"of (\d+)$", count.strip())
    if rows > 10 or (rows and (counted is None or counted.group(1) != natural)):
        errors.append(f"filtered count wrong: {rows} rows, {count!r}")
    page.close()
    return errors


def run_checks(overrides=None):
    with browser_on_build() as (browser, base):
        return check(browser, base, overrides)


class LeagueTop10RenderTest(unittest.TestCase):
    def test_top_ten_and_expand(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        league = source("league.js")
        broken = {
            "opens on 20": league.replace("const PAGE = 10;", "const PAGE = 20;", 1),
            "count line dropped": league.replace("const count = sorted.length ? el(", "const count = false ? el(", 1),
            "show all capped": league.replace("button(`Show all (${sorted.length})`, {class: \"v2-btn\", id: \"v2LgOppsAll\"}, () => reveal(remaining))",
                                              "button(`Show all (${sorted.length})`, {class: \"v2-btn\", id: \"v2LgOppsAll\"}, () => reveal(PAGE))", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, league, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks({"league.js": body}), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
