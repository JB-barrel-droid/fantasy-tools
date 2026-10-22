"""v2 Compare a trade: no stale verdict when a side is empty or the trade changes (JEG-808).

Live bug: adding Mahomes to "You give" only left the example's "Should you propose or accept? Yes /
Will they accept? Likely" visible above "No verdict yet". The headline box was never emptied and its
`hidden` attribute lost to `.v2-cheads { display: flex }`.

Loads the built page headless, starts from the example trade (headlines shown), then opens a give-only
trade and a get-only trade, and requires: no headline text in the DOM, the headline box not rendered, and
"No verdict yet" as the verdict. A complete trade then shows headlines again, and removing a side clears
them again.
Discrimination: test_guard_fails_on_broken_builds serves v2.js without the clearing and v2.css without the
`[hidden]` rule, and requires failures on each.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_deal_read_render import _served, V2_JS, ROOT

V2_CSS = ROOT / "app" / "v2" / "v2.css"
KEYS = ("() => window.TradeValueCurveControls.getAllRows().filter(r => Number.isFinite(r.values.ddf_value))"
        ".sort((a, b) => b.values.ddf_value - a.values.ddf_value).slice(0, 2).map(r => String(r.player_key))")
READ = """() => {
  const box = document.getElementById('v2CHeads');
  const lines = [...box.querySelectorAll('.v2-chead')].map(p => p.textContent.trim());
  return {rendered: box.getBoundingClientRect().height > 0, lines,
    title: document.getElementById('v2CVerdictTitle').textContent.trim(),
    card: document.getElementById('v2CVerdict').innerText};
}"""


def run_checks(js_patch=None, css_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    bodies = {}
    for name, path, patch in (("js", V2_JS, js_patch), ("css", V2_CSS, css_patch)):
        text = path.read_text(encoding="utf-8")
        if patch:
            assert patch[0] in text, f"patch anchor missing: {patch[0]!r}"
            text = text.replace(patch[0], patch[1], 1)
        bodies[name] = text if patch else None
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
            if bodies["js"]:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=bodies["js"]))
            if bodies["css"]:
                page.route("**/v2/v2.css*", lambda route, *_: route.fulfill(status=200, content_type="text/css", body=bodies["css"]))
            page.goto(base + "#compare-trade", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=60000)
            page.wait_for_timeout(500)
            a, b = page.evaluate(KEYS)

            def at(hash_):
                page.evaluate("h => { location.hash = h; }", hash_)
                page.wait_for_timeout(600)
                return page.evaluate(READ)

            snap = page.evaluate(READ)
            if not snap["rendered"] or not all(snap["lines"]):
                errors.append(f"example trade should show both headlines, got {snap['lines']} rendered={snap['rendered']}")
            for tag, hash_ in (("give only", f"#compare-trade?give={a}"), ("get only", f"#compare-trade?get={b}")):
                snap = at(hash_)
                if snap["rendered"]:
                    errors.append(f"[{tag}] headline box is still rendered")
                if any(snap["lines"]):
                    errors.append(f"[{tag}] stale headline text {snap['lines']}")
                if "Should you propose" in snap["card"] or "Will they accept" in snap["card"]:
                    errors.append(f"[{tag}] stale verdict visible: {snap['card'][:120]!r}")
                if snap["title"] != "No verdict yet":
                    errors.append(f"[{tag}] title {snap['title']!r}, want 'No verdict yet'")
            snap = at(f"#compare-trade?give={a}&get={b}")
            if not snap["rendered"] or not all(snap["lines"]):
                errors.append(f"[complete] expected headlines, got {snap['lines']} rendered={snap['rendered']}")
            snap = at(f"#compare-trade?give={a}")
            if snap["rendered"] or any(snap["lines"]):
                errors.append(f"[complete then remove a side] stale headlines {snap['lines']} rendered={snap['rendered']}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "no clearing in JS": ((".v2-chead\").forEach(p => { p.replaceChildren();", ".v2-nothing\").forEach(p => { p.replaceChildren();"), None),
    "no [hidden] rule in CSS": (None, (".v2-cheads[hidden] { display: none; }\n", "")),
}


class CompareEmptySideRenderTest(unittest.TestCase):
    def test_no_stale_verdict(self):
        _render_env.ensure_built()
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        _render_env.ensure_built()
        for name, (js, css) in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(js, css), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
