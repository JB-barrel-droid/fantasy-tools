"""JEG-1098: the league-wide trade opportunities list opens on the top 10.

With a 20-team league (well over 100 offers): 10 rows and "Showing 10 of N" on open; "Show 10 more" adds 10; "Show all (N)"
shows every row; "Show top 10 only" returns; the buttons work from the keyboard; changing the sort keeps the count honest.

JEG-885 (Jeremy, 2026-10-25, option B) adds the diversity rule on the same list: at most 2 rows per received core player
in the open list, the rest folded under a "N more for <player>" control that opens in place from the keyboard. The
ticket's acceptance, on the fixture league closest to the review rosters: the first 10 rows cover at least 4 received
players, no two rows are the same trade up to players worth 0.0 on DDF Value and every compared chart, and every player
with rows beyond the cap carries the fold control.

Discrimination: test_guard_fails_on_broken_builds serves league.js opening on 20 rows, with the count line dropped,
and with Show all capped at one more page, and requires the checks to fail on each. CoreCapGuardFailsOnBrokenBuilds
does the same for the cap switched off and for the fold control not drawn.
"""
from __future__ import annotations

import re
import unittest
from collections import Counter

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
    # Keyboard: focus the button and press Enter. A missing button is a failure to report, not a 30 s timeout.
    if not page.is_visible("#v2LgOppsMore"):
        errors.append("no 'Show 10 more' button")
        page.close()
        return errors
    page.focus("#v2LgOppsMore")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    rows, count = page.evaluate(ROWS), page.evaluate(COUNT)
    if rows != 20 or count.strip() != f"Showing 20 of {total}":
        errors.append(f"after Show 10 more by keyboard: {rows} rows, {count!r}")
    if page.evaluate("() => document.activeElement && document.activeElement.id") != "v2LgOppsMore":
        errors.append("focus left Show 10 more after pressing it (a keyboard reader cannot press it again)")
    if not page.is_visible("#v2LgOppsAll"):
        errors.append("'Show all' button gone after Show 10 more")
        page.close()
        return errors
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


# ---------- JEG-885: the top 10 is diverse; the rest of a received player's rows fold under "N more for <player>" ----------
# One row per trade: the received core player is the bold name in the Trade cell, and the trade text is "Send ..., get ...".
CORE_ROWS = """() => [...document.querySelectorAll('#v2LgOppsTable tbody tr.v2-lg-opp')].map(tr => {
  const cell = tr.children[1];
  const trade = cell.textContent.replace('Hide both teams', '').replace('Both teams', '').replace('Hide details', '').replace('Details', '').trim();
  const m = trade.match(/^Send (.*), get (.*)$/);
  return {id: tr.dataset.oppId, core: (cell.querySelector('b') || {}).textContent || '', give: m ? m[1] : '', get: m ? m[2] : '',
    rank: Number((tr.querySelector('[data-cell=rank]') || {}).textContent)}; })"""
FOLD = """() => [...document.querySelectorAll('#v2LgOppsTable .v2-lg-fold-btn')].map(b => ({id: b.id, text: b.textContent, expanded: b.getAttribute('aria-expanded')}))"""
# Every engine row by name: DDF Value and the four compared charts (0.0 on all of them is the throw-in the ticket names).
VALUES = """() => { const by = new Map(); for (const r of window.TradeValueCurveControls.getAllRows()) { const k = r.name; by.set(k, by.has(k) ? null : r.values); } return Object.fromEntries(by); }"""
KEYS = ("ddf_value", "usatoday", "fantasycalc", "fantasypros", "cbs")


def is_zero(values, name):
    """A player worth 0.0 on DDF Value and every compared chart (finder.js isZeroValue), read from the engine rows."""
    v = values.get(name)
    return bool(v) and all(isinstance(v.get(k), (int, float)) and abs(v[k]) < 0.05 for k in KEYS)


def signature(row, values):
    """The give/receive sets, up to players worth 0.0 everywhere. Two rows sharing one are the same trade to a manager."""
    if not row["give"] or not row["get"]:
        return None

    def side(text):
        return frozenset(n.strip() for n in text.split(" + ") if not is_zero(values, n.strip()))

    return (side(row["give"]), side(row["get"]))


def core_checks(browser, base, overrides=None):
    errors = []
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[corecap] ")
    seed(page, "20team")
    wait_opps(page, timeout=90000)
    rows = page.evaluate(CORE_ROWS)
    values = page.evaluate(VALUES)
    if len(rows) != 10:
        errors.append(f"the list opens on {len(rows)} rows, not 10")
    if any(not r["core"] for r in rows):
        errors.append(f"a row names no received core player: {rows[:2]}")
    counts = Counter(r["core"] for r in rows)
    if len(counts) < 4:
        errors.append(f"the first 10 rows cover only {len(counts)} received player(s): {dict(counts)}")
    over = {core: n for core, n in counts.items() if n > 2}
    if over:
        errors.append(f"more than 2 rows for one received player: {over}")
    sigs = [signature(r, values) for r in rows]
    if any(s is None for s in sigs):
        errors.append(f"a trade cell does not read as 'Send ..., get ...': {rows[:2]}")
    else:
        dupes = [s for s, n in Counter(sigs).items() if n > 1]
        if dupes:
            errors.append(f"{len(dupes)} trade(s) listed twice, up to players worth 0.0: {dupes[:2]}")
    if [r["rank"] for r in rows] != sorted(r["rank"] for r in rows):
        errors.append(f"the rows are not in rank order: {[r['rank'] for r in rows]}")
    # The fold: "N more for <player>", opening that player's remaining rows in place, by keyboard.
    folds = page.evaluate(FOLD)
    if not folds:
        errors.append("no 'N more for <player>' control on a list where a received player has more than 2 rows")
        page.close()
        return errors
    if any(not re.fullmatch(r"\d+ more for .+", f["text"]) for f in folds):
        errors.append(f"a fold control does not read 'N more for <player>': {[f['text'] for f in folds]}")
    if any(f["expanded"] != "false" for f in folds):
        errors.append("a fold control opens on its own")
    fold = folds[0]
    player = fold["text"].split(" more for ", 1)[1]
    before_count = page.evaluate(COUNT)
    page.focus(f"#{fold['id']}")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    after = page.evaluate(CORE_ROWS)
    revealed = [r for r in after if r["id"] not in {x["id"] for x in rows}]
    if not revealed:
        errors.append(f"pressing {fold['text']!r} by keyboard revealed no rows")
    elif any(r["core"] != player for r in revealed):
        errors.append(f"{fold['text']!r} revealed rows for {sorted({r['core'] for r in revealed})}")
    now = page.evaluate(FOLD)
    mine = next((f for f in now if f["id"] == fold["id"]), None)
    if not mine or mine["expanded"] != "true" or not mine["text"].startswith("Hide "):
        errors.append(f"the open control does not offer to hide the rest: {mine}")
    if page.evaluate("() => document.activeElement && document.activeElement.id") != fold["id"]:
        errors.append("focus left the fold control after opening it (a keyboard reader cannot close it again)")
    if page.evaluate(COUNT) == before_count:
        errors.append(f"the count line did not move when the fold opened: {page.evaluate(COUNT)!r}")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    if page.evaluate(ROWS) != len(rows):
        errors.append("pressing the fold control again did not close it")
    page.close()
    return errors


class LeagueCoreCapRenderTest(unittest.TestCase):
    def test_top_ten_is_diverse_and_folds(self):
        with browser_on_build() as (browser, base):
            self.assertEqual(core_checks(browser, base), [])

    def test_guard_fails_on_broken_builds(self):
        league = source("league.js")
        broken = {
            "cap off": league.replace("O.capPerCore(sorted, coreKey, O.CAP_PER_CORE)", "{list: sorted, folds: new Map()}"),
            "no fold control": league.replace("if (capped.folds.has(key) && foldAt.get(key) === i) {", "if (false) {"),
        }
        with browser_on_build() as (browser, base):
            for name, body in broken.items():
                with self.subTest(mutation=name):
                    self.assertNotEqual(body, league, f"mutation anchor for {name!r} is stale")
                    self.assertNotEqual(core_checks(browser, base, {"league.js": body}), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
