"""v2 player search, rendered: forgiving name matching in the page's own search boxes (JEG-812).

Loads the built page headless and types "Amon Ra", "JaMarr", "Ja’Marr" (curly apostrophe) and the typo
"Mcafrey" into the Compare a trade search box (first result must be the right player) and the Player values
search (the table must list him). Players are looked up in the engine's rows, so a fixture without one of them
skips that query rather than failing.

Discrimination: test_guard_fails_on_broken_builds serves namesearch.js with the spaces-ignored match and with the
typo fallback removed, and requires failures.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_deal_read_render import _served, ROOT

SEARCH_JS = ROOT / "app" / "v2" / "namesearch.js"
QUERIES = (("Amon Ra", "St. Brown"), ("JaMarr", "Marr"), ("Ja’Marr", "Marr"), ("Mcafrey", "McCaffrey"))
NAMES = "() => window.TradeValueCurveControls.getAllRows().map(r => r.name)"
TYPE = """([id, text]) => { const el = document.getElementById(id); el.value = text; el.dispatchEvent(new Event('input', {bubbles: true})); }"""
COMPARE_FIRST = "() => { const b = document.querySelector('#v2GiveResults li button b'); return b ? b.textContent : null; }"
TABLE_TEXT = "() => document.getElementById('v2Main').innerText"


def run_checks(patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    body = None
    if patch:
        body = SEARCH_JS.read_text(encoding="utf-8")
        for old, new in patch:
            assert old in body, f"patch anchor missing: {old!r}"
            body = body.replace(old, new, 1)
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
            if body:
                page.route("**/v2/namesearch.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=body))
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            page.wait_for_timeout(500)
            names = page.evaluate(NAMES)
            checked = 0
            for query, fragment in QUERIES:
                want = next((n for n in names if fragment.lower() in n.lower()), None)
                if want is None:
                    continue
                checked += 1
                page.evaluate(TYPE, ["v2GiveSearch", query])
                page.wait_for_timeout(250)
                first = page.evaluate(COMPARE_FIRST)
                if first is None or fragment.lower() not in first.lower():
                    errors.append(f"[compare] {query!r}: first result {first!r}, want a name containing {fragment!r}")
                page.evaluate(TYPE, ["v2GiveSearch", ""])
            page.evaluate("() => { location.hash = '#player-values'; }")
            page.wait_for_timeout(500)
            for query, fragment in QUERIES:
                want = next((n for n in names if fragment.lower() in n.lower()), None)
                if want is None:
                    continue
                page.evaluate(TYPE, ["v2Search", query])
                page.wait_for_timeout(500)
                text = page.evaluate(TABLE_TEXT)
                if want not in text:
                    errors.append(f"[player values] {query!r}: {want!r} not listed")
            if not checked:
                errors.append("no query could be checked: none of the test players is in the built data")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


NO_FUZZY = ("const allowedEdits = length => (length >= 7 ? 2 : length >= 4 ? 1 : 0);", "const allowedEdits = length => 0;")
NO_SQUASH = ("return qs && ns.includes(qs) ? 4 : null;", "return null;")
PATCHES = {
    "typo fallback removed": [NO_FUZZY],
    "spaces-ignored match and typo fallback removed (plain contains, as before)": [NO_SQUASH, NO_FUZZY],
}


class NameSearchRenderTest(unittest.TestCase):
    def test_search(self):
        _render_env.ensure_built()
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        _render_env.ensure_built()
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
