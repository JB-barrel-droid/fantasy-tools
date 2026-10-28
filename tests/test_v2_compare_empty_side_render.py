"""v2 Compare a trade: no stale verdict when a side is empty or the trade changes (JEG-808, JEG-823, JEG-1112).

Live bug (JEG-808): adding Mahomes to "You give" only left the example's answer lines visible above "No verdict
yet". JEG-1112 (Jeremy, 2026-10-26, option D) removed those two "Should you propose or accept?" / "Will they accept?"
lines from the verdict card, so the same guard now covers what is left of it: the verdict title and text, its
waterfall and the Deal read.

Loads the built page headless, starts from the example trade (verdict, waterfall and Deal read shown), then opens a
give-only trade and a get-only trade, and requires: "No verdict yet" as the verdict with its "add a player" text, no
waterfall, no Deal read box and no Deal read text left in the DOM. A complete trade then shows them again, and removing
a side clears them again.
Discrimination: test_guard_fails_on_broken_builds serves v2.js without the verdict text reset and without the Deal read
clearing and hide, and requires failures on each.
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
  const rendered = id => document.getElementById(id).getBoundingClientRect().height > 0;
  return {title: document.getElementById('v2CVerdictTitle').textContent.trim(),
    text: document.getElementById('v2CVerdictText').textContent.trim(),
    fall: rendered('v2CVerdictFall'), deal: rendered('v2CDeal'),
    dealText: (document.getElementById('v2CDealRead').textContent + document.getElementById('v2CDealText').textContent).trim(),
    card: document.getElementById('v2CVerdict').innerText};
}"""
EMPTY_TEXT = "Add a player to both sides."


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

            def shown(tag, snap):
                found = []
                if snap["title"] == "No verdict yet" or not snap["text"] or snap["text"].startswith(EMPTY_TEXT):
                    found.append(f"[{tag}] expected a verdict, got {snap['title']!r} / {snap['text'][:60]!r}")
                if not snap["fall"]:
                    found.append(f"[{tag}] expected the verdict waterfall")
                if not snap["deal"] or not snap["dealText"]:
                    found.append(f"[{tag}] expected the Deal read, got rendered={snap['deal']} text={snap['dealText'][:60]!r}")
                return found

            # JEG-1190: Compare opens empty; the sample loads on Try a sample trade.
            page.click("#v2CTryExample")
            page.wait_for_timeout(400)
            errors += shown("example", page.evaluate(READ))
            for tag, hash_ in (("give only", f"#compare-trade?give={a}"), ("get only", f"#compare-trade?get={b}")):
                snap = at(hash_)
                if snap["title"] != "No verdict yet":
                    errors.append(f"[{tag}] title {snap['title']!r}, want 'No verdict yet'")
                if not snap["text"].startswith(EMPTY_TEXT):
                    errors.append(f"[{tag}] stale verdict text {snap['text'][:80]!r}")
                if snap["fall"]:
                    errors.append(f"[{tag}] verdict waterfall is still rendered")
                if snap["deal"] or snap["dealText"]:
                    errors.append(f"[{tag}] Deal read still there: rendered={snap['deal']} text={snap['dealText'][:60]!r}")
                if "Should you propose" in snap["card"] or "Will they accept" in snap["card"]:
                    errors.append(f"[{tag}] the removed answer lines are back: {snap['card'][:120]!r}")
            errors += shown("complete", at(f"#compare-trade?give={a}&get={b}"))
            snap = at(f"#compare-trade?give={a}")
            if snap["title"] != "No verdict yet" or snap["deal"] or snap["dealText"] or snap["fall"]:
                errors.append(f"[complete then remove a side] stale verdict: {snap['title']!r} deal={snap['deal']} fall={snap['fall']}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "verdict text never reset": (('$("v2CVerdictText").textContent = copy.text;', 'if (copy.kind !== "none") $("v2CVerdictText").textContent = copy.text;'), None),
    "deal read not cleared in JS": (('$("v2CDealRead").textContent = "";\n      $("v2CDealText").textContent = "";', ""), None),
    "deal read not hidden": (("box.hidden = !deal;", "box.hidden = false;"), None),
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
