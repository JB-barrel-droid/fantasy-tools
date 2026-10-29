"""The league workspace on a phone, in the dark, and by keyboard (JEG-1021).

At 390, 360 and 320 px with the 4-team fixture in the workspace:

  * no sideways scroll; the tables become cards; every control is at least 44 px tall;
  * the opportunities filter row shrinks its "Overall fit:" select (#v2LgFilterFit) instead of running past the edge;
  * the sort selector sorts the cards, both directions, and equals an independent sort of the numbers shown on the cards;
  * every visible text meets WCAG AA contrast in light and dark, on the league cards at 1366 and 390;
  * the headers are keyboard operable: Enter on a sort button sorts, one tab stop per header, aria-sort on exactly one th;
  * a team folds with the keyboard and Escape inside it;
  * each trade card shows one line per table column in the table's order, value first, so Our fit and Their fit each have a line (JEG-1232).

Discrimination: test_guard_fails_on_broken_builds serves a build with the cards hidden, the sort selector dead, a 30 px control and
the low-contrast tint colour back, both fits back on one line, and requires the checks to fail.
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

# JEG-1154: the "Overall fit:" select is as wide as its longest option ("Natural and market supported"), which is wider than a 320 px phone.
# The row must shrink it rather than run the page sideways, so the failure names the select instead of only reporting a pixel count.
FIT_FILTER_OVERFLOW = """() => {
  const w = document.documentElement.clientWidth;
  const sel = document.querySelector('#v2LgFilterFit');
  if (!sel) return ['#v2LgFilterFit is not on the page'];
  const out = [];
  const field = sel.closest('.v2-field') || sel;
  for (const [name, node] of [['#v2LgFilterFit', sel], ['the #v2LgFilterFit label', field]]) {
    const r = node.getBoundingClientRect();
    if (r.width && r.right > w + 0.5) out.push(`${name} runs to ${Math.round(r.right)}px on a ${w}px phone`);
  }
  if (document.documentElement.scrollWidth > w) out.push(`the page is ${document.documentElement.scrollWidth - w}px wider than a ${w}px phone with #v2LgFilterFit on it`);
  return out;
}"""


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
        # The column's first direction is ascending (table-sort nextState), so the cards must come out A to Z, not merely ordered.
        if names != sorted(names, key=str.lower):
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


# JEG-1232: the trade card lines below the heading, as (data-line, text). Jeremy picked a fixed order, value first (Oct 29), matching the
# table's columns: trade, DDF Value, projections, Our fit, Market, Their fit.
CARD_LINES = """() => [...document.querySelectorAll('#v2LgOppsCards > li')].map(li => [...li.children].filter(n => n.tagName === 'P').map(p => [p.dataset.line || '', p.innerText.trim()]))"""
CARD_ORDER = ["trade", "capture", "proj", "ours", "market", "theirs"]


def check_card_lines(browser, base, overrides, errors):
    page = open_page(browser, base, width=390, height=800, overrides=overrides, errors=errors, tag="[390px lines] ")
    seed(page, "4team")
    wait_opps(page)
    cards = page.evaluate(CARD_LINES)
    if not cards:
        errors.append("[390px lines] no trade cards to check")
    for i, lines in enumerate(cards):
        ids = [k for k, _ in lines][:len(CARD_ORDER)]
        if ids != CARD_ORDER:
            errors.append(f"[390px lines] card {i + 1} line order {ids}, expected {CARD_ORDER}")
        text = dict(lines)
        if not text.get("ours", "").startswith("Our fit:") or "Their fit" in text.get("ours", ""):
            errors.append(f"[390px lines] card {i + 1} Our fit line: {text.get('ours')!r}")
        if not text.get("theirs", "").startswith("Their fit:"):
            errors.append(f"[390px lines] card {i + 1} Their fit line: {text.get('theirs')!r}")
    page.context.close()


def check_fit_filter(browser, base, overrides, errors):
    """JEG-1154: the opportunities filter row fits a 320 px phone, select named."""
    page = open_page(browser, base, width=320, height=800, overrides=overrides, errors=errors, tag="[320px fit] ")
    seed(page, "4team")
    wait_opps(page)
    errors += [f"[320px fit] {b}" for b in page.evaluate(FIT_FILTER_OVERFLOW)]
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


CHECKS = {"phone": check_phone, "card-lines": check_card_lines, "fit-filter": check_fit_filter, "contrast": check_contrast, "keyboard": check_keyboard}


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
            "the sort selector is dead": ({"league.js": league.replace('sel.addEventListener("change", () => onSort(S.nextState({col: null}, sel.value, columns)));', '', 1)}, {"phone"}, "sort selector"),
            "the fit filter is wider than a 320 px phone": ({"v2.css": css.replace("  .v2-lg-filters .v2-field { min-width: 0; max-width: 100%; flex: 1 1 100%; }\n  .v2-lg-filters .v2-field select { min-width: 0; max-width: 100%; }\n", "", 1)}, {"fit-filter"}),
            "a 30px control": ({"v2.css": css.replace(".v2-lg-toggle { min-width: 44px; min-height: 44px;", ".v2-lg-toggle { min-width: 30px; min-height: 30px;", 1)}, {"phone"}),
            "low contrast tint": ({"v2.css": css.replace(".v2-lg-sort.is-active { color: var(--v2-action-strong); }", ".v2-lg-sort.is-active { color: #9FD8BE; }", 1)}, {"contrast"}),
            "aria-sort on the button": ({"league.js": league.replace('const th = el("th", {scope: "col", "aria-sort": S.ariaSort(state, id), "data-col": id, ...(attrs || {})});', 'const th = el("th", {scope: "col", "data-col": id, ...(attrs || {})});', 1)}, {"keyboard"}),
            "both fits on one line again": ({"league.js": league.replace('el("p", {"data-line": "ours"}, `Our fit: ${r.ours ? `${r.ours.label} · ${ourFitDetail(r)}` : "—"}`),', 'el("p", {"data-line": "ours"}, `Our fit: ${r.ours ? `${r.ours.label} · ${ourFitDetail(r)}` : "—"} · Their fit: ${r.theirs ? r.theirs.detail : "—"}`),', 1).replace('el("p", {"data-line": "theirs"}, `Their fit: ${r.theirs ? r.theirs.detail : "—"}`),', '', 1)}, {"card-lines"}, "Our fit line"),
            "Escape does not fold": ({"league.js": league.replace('if (event.key === "Escape" && !comp.collapsed', 'if (false && !comp.collapsed', 1)}, {"keyboard"}),
        }
        for name, (overrides, only, *rest) in broken.items():
            names_it = rest[0] if rest else None   # a phrase the error must carry, so the named bug is caught by the check that names it, not by unrelated noise
            with self.subTest(mutation=name):
                key = next(iter(overrides))
                self.assertNotEqual(overrides[key], source(key), f"mutation anchor for {name!r} is stale")
                found = caught(overrides, only)
                self.assertNotEqual(found, [], f"not caught: {name}")
                if names_it:
                    self.assertTrue(any(names_it in e for e in found), f"caught, but not by the check that names it: {name} -> {found[:3]}")


if __name__ == "__main__":
    unittest.main()
