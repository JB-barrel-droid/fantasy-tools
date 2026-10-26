"""The league workspace on a phone, in the dark, and by keyboard (JEG-1021).

At 390, 360 and 320 px with the 4-team fixture in the workspace:

  * no sideways scroll; the tables become cards; every control is at least 44 px tall;
  * the sort selector sorts the cards, both directions, and equals an independent sort of the numbers shown on the cards;
  * every visible text meets WCAG AA contrast in light and dark, on the league cards at 1366 and 390;
  * the headers are keyboard operable: Enter on a sort button sorts, one tab stop per header, aria-sort on exactly one th;
  * a team folds with the keyboard and Escape inside it.

Discrimination: test_guard_fails_on_broken_builds serves a build with the cards hidden, the sort selector dead, a 30 px control and
the low-contrast tint colour back, and requires the checks to fail.
"""
from __future__ import annotations

import re
import unittest

from tests import _render_env
from tests._league_render import browser_on_build, open_page, seed, source, wait_opps
from tests.test_v2_a11y_render import CONTRAST

BOX = ["#v2LgCard", "#v2LgSummary", "#v2LgOpps"]

SMALL = """() => { const out = []; for (const sel of ['#v2LgCard', '#v2LgSummary', '#v2LgOpps']) { const root = document.querySelector(sel); if (!root || root.hidden) continue;
  root.querySelectorAll('button, select, textarea, input:not([type=file]), summary').forEach(n => { const r = n.getBoundingClientRect(); const cs = getComputedStyle(n);
    if (!r.width || !r.height || cs.visibility === 'hidden' || n.closest('[hidden]') || n.closest('.v2-sr')) return;
    if (n.closest('.v2-lg-more')) return;   // an inline "+N more" inside a sentence
    if (r.height < 43.5) out.push(`${sel} ${n.tagName.toLowerCase()}.${n.className.toString().split(' ')[0]} ${(n.textContent || n.getAttribute('aria-label') || '').trim().slice(0, 24)} ${Math.round(r.width)}x${Math.round(r.height)}`); }); }
  return out; }"""

# The sort the page holds, as column:direction. The fixture's default order can already match the order a card check expects, so the
# cards alone cannot tell a working selector from a dead one (JEG-1090: the 320 px overflow error used to mask exactly that).
ACTIVE_SORT = """(table) => [...document.querySelectorAll(table + ' thead th[aria-sort]')].filter(t => t.getAttribute('aria-sort') !== 'none').map(t => t.dataset.col + ':' + t.getAttribute('aria-sort'))"""

CARDS = """(sel) => [...document.querySelectorAll(sel + ' > li')].map(li => li.innerText)"""


def setUpModule():
    _render_env.ensure_built()


def card_numbers(text, label):
    import re
    m = re.search(label + r":?\s*([-+]?\d+(\.\d+)?)", text)
    return float(m.group(1)) if m else None


def check_phone(browser, base, overrides, errors):
    for width in (390, 360, 320):
        tag = f"[{width}px] "
        page = open_page(browser, base, width=width, height=800, overrides=overrides, errors=errors, tag=tag)
        seed(page, "4team")
        wait_opps(page)
        over = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        if over > 0:
            errors.append(f"{tag}sideways scroll by {over}px")
        for table in ("#v2LgSummaryTable", "#v2LgOppsTable"):
            if page.is_visible(table):
                errors.append(f"{tag}{table} still shows as a table on a phone")
        for cards, minimum in (("#v2LgSummaryCards", 4), ("#v2LgOppsCards", 1)):
            if page.locator(f"{cards} > li").count() < minimum or not page.is_visible(f"{cards} > li >> nth=0"):
                errors.append(f"{tag}{cards} has no visible cards")
        small = page.evaluate(SMALL)
        if small:
            errors.append(f"{tag}controls under 44px: {small[:6]}")
        # Sort selector: bench value (DDF), both directions.
        texts = page.evaluate(CARDS, "#v2LgSummaryCards")
        page.select_option("#v2LgSummarySortBy", "benchF")
        sorted_by = page.evaluate(ACTIVE_SORT, "#v2LgSummaryTable")
        if sorted_by != ["benchF:descending"]:
            errors.append(f"{tag}the sort selector did not sort the summary by bench value: {sorted_by}")
        vals = [card_numbers(t, r"bench") for t in page.evaluate(CARDS, "#v2LgSummaryCards")]
        if any(v is None for v in vals) or vals != sorted(vals, reverse=True):
            errors.append(f"{tag}summary cards after sorting by bench value: {vals}")
        page.click("#v2LgSummarySortDir")
        vals2 = [card_numbers(t, r"bench") for t in page.evaluate(CARDS, "#v2LgSummaryCards")]
        if vals2 != sorted(vals2):
            errors.append(f"{tag}summary cards after reversing: {vals2}")
        if page.evaluate(CARDS, "#v2LgSummaryCards") == texts:
            errors.append(f"{tag}the sort selector did not reorder the cards")
        # By team name: the order differs from the rank order whatever today's values are (2026-10-25: bench value order matched the rank
        # order on the rebuilt data, so a dead selector passed the check above).
        clean = lambda texts: [re.sub(r"^#\d+\s*|★\s*| \(partial\)", "", t.split("\n")[0]).strip() for t in texts]
        rank_order = clean(texts)   # the cards as first drawn: the rank order
        # The sort selector's default order is the rank order; it must differ from alphabetical or this check proves nothing.
        page.select_option("#v2LgSummarySortBy", "team")
        names = clean(page.evaluate(CARDS, "#v2LgSummaryCards"))
        if names != sorted(names, key=str.lower) and names != sorted(names, key=str.lower, reverse=True):
            errors.append(f"{tag}summary cards after sorting by team: {names}")
        if names == rank_order:
            errors.append(f"{tag}sorting by team did not reorder the summary cards ({names}); if the fixture's rank order is alphabetical this check proves nothing")
        page.select_option("#v2LgOppsSortBy", "capture")
        sorted_by = page.evaluate(ACTIVE_SORT, "#v2LgOppsTable")
        if sorted_by != ["capture:descending"]:
            errors.append(f"{tag}the sort selector did not sort the opportunities by capture: {sorted_by}")
        caps = [card_numbers(t, r"DDF Value") for t in page.evaluate(CARDS, "#v2LgOppsCards")]
        if any(v is None for v in caps) or caps != sorted(caps, reverse=True):
            errors.append(f"{tag}opportunity cards after sorting by capture: {caps}")
        page.context.close()


def check_contrast(browser, base, overrides, errors):
    for scheme in ("light", "dark"):
        for width in (1366, 390):
            tag = f"[{scheme} {width}px] "
            page = open_page(browser, base, width=width, height=800, overrides=overrides, errors=errors, tag=tag, scheme=scheme)
            seed(page, "4team")
            wait_opps(page)
            if width > 720:
                page.click("#v2LgOppsTable .v2-lg-details-btn >> nth=0")   # an open Details row is text too
            bad = page.evaluate(CONTRAST)
            errors += [f"{tag}low contrast {b}" for b in bad]
            page.context.close()


def check_keyboard(browser, base, overrides, errors):
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[keys] ")
    seed(page, "4team")
    wait_opps(page)
    # One tab stop per header: no th holds two buttons.
    multi = page.evaluate("() => [...document.querySelectorAll('#v2LgSummaryTable thead th, #v2LgOppsTable thead th')].filter(th => th.querySelectorAll('button').length > 1).length")
    if multi:
        errors.append(f"[keys] {multi} headers hold more than one button")
    for table in ("v2LgSummaryTable", "v2LgOppsTable"):
        if page.evaluate(f"() => document.querySelectorAll('#{table} thead th[aria-sort]').length") != page.evaluate(f"() => document.querySelectorAll('#{table} thead th:has(button[data-sort])').length"):
            errors.append(f"[keys] {table}: a sortable header has no aria-sort")
        if page.evaluate(f"() => document.querySelectorAll('#{table} thead button[aria-sort]').length"):
            errors.append(f"[keys] {table}: aria-sort is on a button, where it is not valid")
    page.focus('#v2LgSummaryTable thead button[data-sort="rosterF"]')
    page.keyboard.press("Enter")
    state = page.evaluate("() => [...document.querySelectorAll('#v2LgSummaryTable thead th[aria-sort]')].filter(t => t.getAttribute('aria-sort') !== 'none').map(t => t.dataset.col + ':' + t.getAttribute('aria-sort'))")
    if state != ["rosterF:descending"]:
        errors.append(f"[keys] Enter on a sort button: {state}")
    page.keyboard.press("Space")
    state = page.evaluate("() => [...document.querySelectorAll('#v2LgSummaryTable thead th[aria-sort]')].filter(t => t.getAttribute('aria-sort') !== 'none').map(t => t.dataset.col + ':' + t.getAttribute('aria-sort'))")
    if state != ["rosterF:ascending"]:
        errors.append(f"[keys] Space on a sort button: {state}")
    if "Sorted by" not in page.inner_text("#v2LgLive"):
        errors.append("[keys] the sort is not announced")
    # A team folds from the keyboard and Escape inside it.
    toggle = page.locator("#v2LgTeams > li >> nth=0").locator(".v2-lg-toggle")
    if toggle.get_attribute("aria-expanded") != "true":
        toggle.focus()
        page.keyboard.press("Enter")
    page.locator("#v2LgTeams > li >> nth=0").locator("textarea").focus()
    page.keyboard.press("Escape")
    if toggle.get_attribute("aria-expanded") != "false":
        errors.append("[keys] Escape inside a team did not fold it")
    page.context.close()


CHECKS = {"phone": check_phone, "contrast": check_contrast, "keyboard": check_keyboard}


def run_checks(overrides=None, only=None) -> list[str]:
    errors: list[str] = []
    with browser_on_build() as (browser, base):
        for name, check in CHECKS.items():
            if only and name not in only:
                continue
            check(browser, base, overrides, errors)
    return errors


def caught(overrides, only):
    """The checks' verdict on a broken build: their errors, or the crash a missing control causes (a click that finds nothing)."""
    from playwright.sync_api import Error as PlaywrightError
    try:
        return run_checks(overrides, only)
    except PlaywrightError as exc:
        return [f"checks could not finish: {str(exc).splitlines()[0]}"]


class LeaguePhoneRenderTest(unittest.TestCase):
    def test_phone_contrast_keyboard(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = source("v2.css")
        league = source("league.js")
        broken = {
            "the cards are never shown": ({"v2.css": css.replace("  .v2-lg-tablewrap { display: none; }\n  .v2-lg-cards { display: grid; }", "  .v2-lg-cards { display: none; }", 1)}, {"phone"}),
            "the sort selector is dead": ({"league.js": league.replace('sel.addEventListener("change", () => onSort(S.nextState({col: null}, sel.value, columns)));', '', 1)}, {"phone"}),
            "a 30px control": ({"v2.css": css.replace(".v2-lg-toggle { min-width: 44px; min-height: 44px;", ".v2-lg-toggle { min-width: 30px; min-height: 30px;", 1)}, {"phone"}),
            "low contrast tint": ({"v2.css": css.replace(".v2-lg-sort.is-active { color: var(--v2-action-strong); }", ".v2-lg-sort.is-active { color: #9FD8BE; }", 1)}, {"contrast"}),
            "aria-sort on the button": ({"league.js": league.replace('const th = el("th", {scope: "col", "aria-sort": S.ariaSort(state, id), "data-col": id, ...(attrs || {})});', 'const th = el("th", {scope: "col", "data-col": id, ...(attrs || {})});', 1)}, {"keyboard"}),
            "Escape does not fold": ({"league.js": league.replace('if (event.key === "Escape" && !comp.collapsed', 'if (false && !comp.collapsed', 1)}, {"keyboard"}),
        }
        for name, (overrides, only) in broken.items():
            with self.subTest(mutation=name):
                key = next(iter(overrides))
                self.assertNotEqual(overrides[key], source(key), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(caught(overrides, only), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
