"""v2 Compare: no stale deal-read card when a side is empty, no Clear button on example (JEG-823).

Live bug: after adding a player to one side, the Deal read card kept the example's stale text
("A fair trade: Your call" with "+1.0 Even"). The card was hidden via the `hidden` attribute, but
its children kept stale text (a defense-in-depth risk if the hidden attribute is ever overridden,
as happened with the headline box in JEG-808). The Clear trade button was a no-op while the
example was showing because TR.give and TR.receive were already empty.

Loads the built page headless, starts from the example trade (deal read shown), then opens a
give-only trade and requires: no stale deal text in the DOM, the card not rendered, and the clear
and swap buttons hidden on the example. Also checks the suggestion list opens below the search
input (not above it).

Discrimination: test_guard_fails_on_broken_builds serves v2.js without the clearing and requires
failures.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_deal_read_render import _served, V2_JS, ROOT

KEYS = ("() => window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values.ddf_value))"
        ".sort((a, b) => b.values.ddf_value - a.values.ddf_value).slice(0, 2).map(r => String(r.player_key))")

READ = """() => {
  const deal = document.getElementById('v2CDeal');
  const dealRead = document.getElementById('v2CDealRead');
  const dealText = document.getElementById('v2CDealText');
  const nets = document.getElementById('v2CDealNets');
  const clear = document.getElementById('v2CClear');
  const swap = document.getElementById('v2CSwap');
  const example = document.getElementById('v2CExample');
  return {
    dealHidden: deal.hidden,
    dealRendered: deal.getBoundingClientRect().height > 0,
    dealReadText: dealRead.textContent,
    dealTextContent: dealText.textContent,
    netsChildCount: nets.childElementCount,
    clearHidden: clear.hidden,
    swapHidden: swap.hidden,
    exampleShown: !example.hidden
  };
}"""

SEARCH_POS = """(inputId) => {
  const input = document.getElementById(inputId);
  const inputRect = input.getBoundingClientRect();
  input.value = 'a';
  input.dispatchEvent(new Event('input', {bubbles: true}));
  const wrap = input.closest('.v2-trade-search-wrap');
  const results = wrap ? wrap.querySelector('.v2-trade-results') : null;
  if (!results || results.hidden) return {inputBottom: inputRect.bottom, listTop: null, listHidden: true};
  const listRect = results.getBoundingClientRect();
  input.value = '';
  input.dispatchEvent(new Event('input', {bubbles: true}));
  return {inputBottom: inputRect.bottom, listTop: listRect.top, listHidden: false};
}"""


def run_checks(js_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js_body = None
    if js_patch:
        text = V2_JS.read_text(encoding="utf-8")
        assert js_patch[0] in text, f"patch anchor missing: {js_patch[0]!r}"
        text = text.replace(js_patch[0], js_patch[1], 1)
        js_body = text
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_body:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js_body))
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            page.wait_for_timeout(500)
            a, b = page.evaluate(KEYS)

            def at(hash_):
                page.evaluate("h => { location.hash = h; }", hash_)
                page.wait_for_timeout(600)
                return page.evaluate(READ)

            # 1. JEG-1190: the page opens empty (no example, no deal read, nothing to clear or swap); Try a sample
            # trade loads the sample as a real trade, with its deal read and with Clear and Swap.
            snap = at("#compare-trade")
            if snap["exampleShown"]:
                errors.append("an example is shown on the empty page")
            if snap["dealRendered"] or snap["dealReadText"]:
                errors.append("the empty page shows a deal read")
            if not snap["clearHidden"] or not snap["swapHidden"]:
                errors.append("Clear or Swap is shown on the empty page")
            page.click("#v2CTryExample")
            page.wait_for_timeout(600)
            snap = page.evaluate(READ)
            if not snap["exampleShown"]:
                errors.append("Try a sample trade did not load the sample marked Example")
            if snap["dealHidden"]:
                errors.append("the sample trade should show a deal read")
            if snap["clearHidden"] or snap["swapHidden"]:
                errors.append("Clear and Swap should work on the sample trade")

            # 2. One-sided trade (give only): deal read hidden AND empty
            snap = at(f"#compare-trade?give={a}")
            if snap["dealRendered"]:
                errors.append("[give only] deal read card is still rendered")
            if snap["dealReadText"]:
                errors.append(f"[give only] stale deal read text: {snap['dealReadText']!r}")
            if snap["dealTextContent"]:
                errors.append(f"[give only] stale deal text content: {snap['dealTextContent']!r}")
            if snap["netsChildCount"] > 0:
                errors.append(f"[give only] stale nets: {snap['netsChildCount']} children")

            # 3. One-sided (get only): same checks
            snap = at(f"#compare-trade?get={b}")
            if snap["dealRendered"]:
                errors.append("[get only] deal read card is still rendered")
            if snap["dealReadText"]:
                errors.append(f"[get only] stale deal read text: {snap['dealReadText']!r}")

            # 4. Complete trade: deal read should be back
            snap = at(f"#compare-trade?give={a}&get={b}")
            if snap["dealHidden"]:
                errors.append("[complete] deal read should be visible")

            # 5. Remove a side: deal read clears
            snap = at(f"#compare-trade?give={a}")
            if snap["dealReadText"]:
                errors.append(f"[complete then remove] stale deal read: {snap['dealReadText']!r}")

            # 6. Suggestion list: check positioning on the give search
            search_snap = page.evaluate(SEARCH_POS, "v2GiveSearch")
            if not search_snap["listHidden"] and search_snap["listTop"] is not None:
                if search_snap["listTop"] < search_snap["inputBottom"] - 2:
                    errors.append(f"suggestion list opens above input: listTop={search_snap['listTop']:.0f} < inputBottom={search_snap['inputBottom']:.0f}")

            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "deal read clearing removed (JEG-823)": (
        '$("v2CDealRead").textContent = "";\n      $("v2CDealText").textContent = "";\n      $("v2CDealNets").replaceChildren();\n      $("v2CDealGrid").replaceChildren();\n      $("v2CDealProduction").textContent = "";',
        '/* clearing disabled for mutation test */',
    ),
}


class DealReadEmptySideRenderTest(unittest.TestCase):
    def test_no_stale_deal_read(self):
        _render_env.ensure_built()
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        _render_env.ensure_built()
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
