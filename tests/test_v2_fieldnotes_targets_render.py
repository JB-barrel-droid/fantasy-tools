"""JEG-1139: Trade targets in Fieldnotes (?design=fieldnotes), the ticket's done-when through the rendered UI.

At phone (390) and desktop (1280) widths, on the live fixture's targets:
  * the computed results are unchanged: #v2Targets' text equals the unflagged page's, with the lists closed and after
    "Show more" opens the sell list;
  * the two checks and the sell and buy list headings are in the display face;
  * no sideways scroll, every visible control in Trade targets at least 44px tall, and text at least 4.5:1 (3:1 when
    large), with the lists closed and opened;
  * by keyboard: Tab reaches "Show more" with a 3px focus ring at least 3:1, and Enter opens the full sell list, then
    "Show top 5" closes it; Enter on a weight group's toggle opens its players and keeps focus on the toggle; Enter on
    "How to use it" opens and closes it. At 1280, Enter on a row's per-chart toggle opens that row's detail. At 390, a
    tap on a target card opens that player's details.

Default page: without the flag, Trade targets' computed styles equal those of a build whose v2.css has neither the
JEG-1138 nor the JEG-1139 block (the targets page reuses JEG-1138's shared lists).
Discrimination: test_guard_fails_without_blocks requires the heading check to fail without the JEG-1139 block, and the
"How to use it" target-size check to fail at 1280 without the JEG-1138 shared lists.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build
from tests.test_v2_modules_render import _serve
from tests.test_v2_fieldnotes_compare_render import A11Y, tab_to

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
BLOCKS = {"1138": ("/* JEG-1138: Compare a trade in Fieldnotes", "/* JEG-1138 end */"),
          "1139": ("/* JEG-1139: Trade targets in Fieldnotes", "/* JEG-1139 end */")}
FLAG = "?design=fieldnotes"
WIDTHS = ((390, 844), (1280, 900))

TARGETS_A11Y = A11Y.replace("#v2Compare", "#v2Targets")

READ = """() => ({text: document.getElementById('v2Targets').textContent.replace(/\\s+/g, ' ').trim(),
  fonts: [...document.querySelectorAll('#v2Targets .v2-tcheck h2, #v2Targets .v2-weight > h2, #v2Targets .v2-tlist-head h2')]
    .map(h => getComputedStyle(h).fontFamily),
  sell: document.querySelectorAll(window.innerWidth >= 768 ? '#v2TTable tbody tr:not(.t-detail)' : '#v2TCards > li').length})"""

STYLE_SNAPSHOT = """() => [...document.querySelectorAll('#v2Targets, #v2Targets *')].map(el => {
  const cs = getComputedStyle(el); return [el.tagName, el.id, String(el.className), [...cs].sort().map(p => p + ':' + cs.getPropertyValue(p)).join(';')]; })"""


def setUpModule():
    _render_env.ensure_built()


def without(*names) -> str:
    css = CSS.read_text(encoding="utf-8")
    for name in names:
        start, end = BLOCKS[name]
        a, b = css.index(start), css.index(end) + len(end)
        css = css[:a] + css[b:]
    return css


def open_targets(browser, base, width, height, flag=FLAG, css=None, errors=None):
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light", has_touch=width < 768)
    ctx.add_init_script(_render_env.pin_data_week_script())
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    if css is not None:
        page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
    page.goto(base + flag + "#trade-targets", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls", timeout=60000)
    page.wait_for_function("() => document.querySelector('#v2TTable tbody tr, #v2TCards > li')", timeout=30000)
    page.emulate_media(reduced_motion="reduce")
    return page


def problems(page, tag) -> list[str]:
    state = page.evaluate(TARGETS_A11Y)
    return ([f"{tag}: page scrolls sideways by {state['overflow']}px"] if state["overflow"] > 0 else []) \
        + [f"{tag}: control under 44px: {s}" for s in state["small"]] \
        + [f"{tag}: low text contrast: {s}" for s in state["text"]]


def ring(focus, what, tag) -> list[str]:
    if focus is None:
        return [f"{tag}: Tab never reaches {what}"]
    if focus["style"] == "none" or focus["width"] < 3 or focus["contrast"] < 3:
        return [f"{tag}: focus ring on {what} is {focus}"]
    return []


class FieldnotesTargetsTests(unittest.TestCase):
    maxDiff = None

    def test_targets_and_details(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                with self.subTest(width=width):
                    errors: list[str] = []
                    tag = f"{width}px"
                    page = open_targets(browser, base, width, height, errors=errors)
                    plain = open_targets(browser, base, width, height, flag="", errors=errors)
                    self.assertEqual(page.evaluate("() => document.documentElement.dataset.design"), "fieldnotes")
                    got, want = page.evaluate(READ), plain.evaluate(READ)
                    if got["text"] != want["text"]:
                        errors.append(f"{tag}: Trade targets' text differs from the unflagged page")
                    if len(got["fonts"]) != 4 or not all("Fraunces" in f for f in got["fonts"]):
                        errors.append(f"{tag}: headings are {got['fonts']}, not the display face")
                    errors += problems(page, f"{tag} closed")

                    # Show more / Show top 5, by keyboard.
                    closed = got["sell"]
                    errors += ring(tab_to(page, "#v2TSellMore"), "Show more", tag)
                    page.keyboard.press("Enter")
                    page.wait_for_function(f"() => ({READ})().sell > {closed}", timeout=5000)
                    plain.click("#v2TSellMore")
                    plain.wait_for_function(f"() => ({READ})().sell > {closed}", timeout=5000)
                    if page.evaluate(READ)["text"] != plain.evaluate(READ)["text"]:
                        errors.append(f"{tag}: the opened sell list differs from the unflagged page")
                    errors += problems(page, f"{tag} opened")
                    if tab_to(page, "#v2TSellLess") is None:
                        errors.append(f"{tag}: Tab never reaches Show top 5")
                    else:
                        page.keyboard.press("Enter")
                        page.wait_for_function(f"() => ({READ})().sell === {closed}", timeout=5000)

                    # Row detail: per-chart toggle at 1280, a tap on a card at 390.
                    if width >= 768:
                        focus = tab_to(page, "#v2TTable .v2-texpand")
                        errors += ring(focus, "a row's per-chart toggle", tag)
                        if focus is not None:
                            page.keyboard.press("Enter")
                            page.wait_for_timeout(150)
                            after = page.evaluate("""() => ({rows: document.querySelectorAll('#v2TTable tr.t-detail').length,
                              focused: Boolean(document.activeElement && document.activeElement.matches('#v2TTable .v2-texpand[aria-expanded="true"]'))})""")
                            if not after["rows"] or not after["focused"]:
                                errors.append(f"{tag}: Enter on a row's per-chart toggle gave {after}")
                    else:
                        page.locator("#v2TCards > li").first.tap()
                        page.wait_for_function("() => !document.getElementById('v2Drawer').hidden", timeout=5000)
                        page.keyboard.press("Escape")
                        page.wait_for_function("() => document.getElementById('v2Drawer').hidden", timeout=5000)

                    # Weight groups and "How to use it", by keyboard.
                    focus = tab_to(page, "#v2WeightTable [data-weight-expand]")
                    errors += ring(focus, "a weight group's toggle", tag)
                    if focus is not None:
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(150)
                        after = page.evaluate("""() => ({rows: document.querySelectorAll('#v2WeightTable tr.w-detail').length,
                          focused: Boolean(document.activeElement && document.activeElement.matches('#v2WeightTable [data-weight-expand]'))})""")
                        if not after["rows"] or not after["focused"]:
                            errors.append(f"{tag}: Enter on a weight group's toggle gave {after}")
                    focus = tab_to(page, "#v2Weight .v2-weight-how > summary")
                    errors += ring(focus, "How to use it", tag)
                    if focus is not None:
                        opened = []
                        for _ in range(2):
                            page.keyboard.press("Enter")
                            opened.append(page.evaluate("() => document.querySelector('#v2Weight .v2-weight-how').open"))
                        if opened != [True, False]:
                            errors.append(f"{tag}: Enter on 'How to use it' gave open states {opened}, not [True, False]")
                    errors += problems(page, f"{tag} details")
                    page.context.close()
                    plain.context.close()
                    self.assertEqual(errors, [])

    def test_default_page_unchanged(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                snaps = []
                for css in (None, without("1138", "1139")):
                    page = open_targets(browser, base, width, height, flag="", css=css)
                    self.assertIsNone(page.evaluate("() => document.documentElement.dataset.design || null"))
                    snaps.append(page.evaluate(STYLE_SNAPSHOT))
                    page.context.close()
                self.assertEqual(len(snaps[0]), len(snaps[1]))
                changed = [a[:3] for a, b in zip(*snaps) if a != b]
                self.assertEqual(changed, [], f"the Fieldnotes blocks changed the unflagged page at {width}px")

    def test_guard_fails_without_blocks(self):
        with browser_on_build() as (browser, base):
            for css, heading_ok, summary_ok in ((None, True, True), (without("1139"), False, True), (without("1138"), True, False)):
                page = open_targets(browser, base, 1280, 900, css=css)
                fonts = page.evaluate(READ)["fonts"]
                small = page.evaluate(TARGETS_A11Y)["small"]
                page.context.close()
                with self.subTest(heading=heading_ok, summary=summary_ok):
                    self.assertEqual(all("Fraunces" in f for f in fonts), heading_ok, fonts)
                    self.assertEqual(not any("How to use it" in s for s in small), summary_ok, small)


if __name__ == "__main__":
    unittest.main()
