"""v2 review polish (JEG-579), rendered: contracts N461-fold-expand, N477-tier-lines-*, P3-rank-alignment, P3-source-ranks.

  * Trade targets: Sell and Buy side by side from 1024 px (stacked at 1000 px), each with its module fold, an
    expanded list capped at about 60vh and scrolling inside its own column;
  * Player values: the # cell is a table cell; at 1440 px each value cell carries "N overall · POS#" and the #
    column a position rank; at 1100 px those sub-labels are hidden;
  * chart tier lines: labelled "Starters", "Bench", "Waiver"; dashed across positions, solid on one position
    ranked by DDF Value; no shading.

Discrimination: test_guard_fails_on_broken_builds serves a v2.css that restores the 1280 px breakpoint, hides the
sub-labels, and a v2.js that always dashes the lines, and requires failures.
"""
from __future__ import annotations

import unittest

from tests import _render_env  # noqa: E402
from tests.test_v2_names_render import _served  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"


def run_checks(js_patch=None, css_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    bodies = {}
    for key, path, patch in (("js", V2_JS, js_patch), ("css", V2_CSS, css_patch)):
        text = path.read_text(encoding="utf-8")
        if patch:
            old, new = patch
            assert old in text, f"patch anchor missing: {old!r}"
            text = text.replace(old, new, 1)
        bodies[key] = text
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        page_errors: list[str] = []

        def open_page(hash_, width, height=900):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=bodies["js"]))
            if css_patch:
                page.route("**/v2/v2.css*", lambda route, *_: route.fulfill(status=200, content_type="text/css", body=bodies["css"]))
            page.goto(base + hash_, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
            page.wait_for_timeout(800)
            return page

        try:
            # Sell / Buy.
            for width, side_by_side in ((1024, True), (1000, False)):
                page = open_page("#trade-targets", width)
                tops = page.evaluate("() => ['v2TSell', 'v2TBuy'].map(id => { const r = document.getElementById(id).getBoundingClientRect(); return [Math.round(r.top), Math.round(r.left)]; })")
                same_row = abs(tops[0][0] - tops[1][0]) < 4
                if same_row != side_by_side:
                    errors.append(f"[{width}px] Sell/Buy tops {tops}, side by side expected {side_by_side}")
                if side_by_side:
                    folds = page.evaluate("() => ['v2TSell', 'v2TBuy'].map(id => Boolean(document.querySelector('#' + id + ' .v2-mod-chevron')))")
                    if folds != [True, True]:
                        errors.append(f"[{width}px] fold per side missing: {folds}")
                    cap = page.evaluate("() => { const w = document.querySelector('#v2TSell .v2-t-desktop'); const s = getComputedStyle(w); return [s.maxHeight, s.overflowY, innerHeight]; }")
                    if cap[1] not in ("auto", "scroll") or abs(float(cap[0][:-2]) - 0.6 * cap[2]) > 2:
                        errors.append(f"[{width}px] expanded list not capped at 60vh with internal scroll: {cap}")
                page.close()
            # Player values.
            page = open_page("#player-values", 1440)
            facts = page.evaluate("""() => { const td = document.querySelector('.v2-table td.rank');
              const vals = [...document.querySelectorAll('.v2-table tbody tr:first-child td.num .v2-srank')].map(n => n.textContent);
              const vis = n => Boolean(n) && getComputedStyle(n).display !== 'none';
              return {display: getComputedStyle(td).display, srank: vals, srankVisible: vis(document.querySelector('.v2-srank')),
                prank: td.querySelector('.v2-prank')?.textContent || '', prankVisible: vis(td.querySelector('.v2-prank'))}; }""")
            if facts["display"] != "table-cell":
                errors.append(f"[values] # cell display {facts['display']}")
            if not facts["srank"] or not all(" overall · " in t for t in facts["srank"]) or not facts["srankVisible"]:
                errors.append(f"[values 1440] value-cell rank sub-labels {facts['srank']} visible={facts['srankVisible']}")
            if not facts["prank"] or not facts["prankVisible"]:
                errors.append(f"[values 1440] # column position rank {facts['prank']!r} visible={facts['prankVisible']}")
            # Tier lines: dashed across positions, solid on one position by DDF Value.
            zone = page.evaluate("""() => ({labels: [...document.querySelectorAll('#v2Chart .zone-label')].map(l => l.textContent),
              dashed: [...document.querySelectorAll('#v2Chart .zone-line')].map(l => getComputedStyle(l).strokeDasharray !== 'none'),
              shaded: Boolean(document.querySelector('#v2Chart .zone-fill, #v2Chart .zone-band'))})""")
            if any(label not in ("Starters", "Bench", "Waiver") for label in zone["labels"]):
                errors.append(f"[chart] zone labels {zone['labels']}")
            if zone["shaded"]:
                errors.append("[chart] tier shading present")
            if zone["dashed"] and not all(zone["dashed"]):
                errors.append(f"[chart] All positions lines should be dashed: {zone['dashed']}")
            page.select_option("#v2Position", "RB")
            page.wait_for_timeout(1200)
            solid = page.evaluate("() => [...document.querySelectorAll('#v2Chart .zone-line')].map(l => getComputedStyle(l).strokeDasharray === 'none')")
            if solid and not all(solid):
                errors.append(f"[chart] one position by DDF Value should have solid lines: {solid}")
            page.close()
            page = open_page("#player-values", 1100)
            hidden = page.evaluate("() => { const n = document.querySelector('.v2-srank'); return !n || getComputedStyle(n).display === 'none'; }")
            if not hidden:
                errors.append("[values 1100] rank sub-labels shown below 1200 px")
            page.close()
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


JS_PATCHES = {
    "lines always dashed": ('class: `zone-line${exact ? "" : " approx"}`', 'class: "zone-line approx"'),
    "label singular": ('name === "Starter" ? "Starters" : name', "name"),
}
CSS_PATCHES = {
    "sub-labels hidden": ("@media (min-width: 1200px) {\n  .v2-srank, .v2-prank { display: block;", "@media (min-width: 9999px) {\n  .v2-srank, .v2-prank { display: block;"),
    "1280 breakpoint": ("@media (min-width: 1024px) {\n  .v2-tlists {", "@media (min-width: 1280px) {\n  .v2-tlists {"),
    "no cap": ("  .v2-tlist .v2-t-desktop { max-height: 60vh; overflow: auto; }", ""),
}


class ReviewPolishRenderTest(unittest.TestCase):
    def test_polish(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        cases = [(n, {"js_patch": p}) for n, p in JS_PATCHES.items() ] \
            + [(n, {"css_patch": p}) for n, p in CSS_PATCHES.items()]
        for name, kwargs in cases:
            with self.subTest(patch=name):
                try:
                    errors = run_checks(**kwargs)
                except Exception as exc:
                    if "unavailable" in type(exc).__name__.lower() or type(exc).__name__ == "SkipTest":
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
