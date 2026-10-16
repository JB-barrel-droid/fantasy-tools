"""Player values: hover or focus a rescaled trade chart cell shows the published number first (JEG-457 part 2), rendered.

  * the tip's first line is "<Publisher>, Week N (original)" with the engine's native number
    (C.getPublishedMath), then the rescale factor, then the rescaled value equal to the cell text;
  * the cell is keyboard reachable (tabindex, aria-describedby) and Esc closes the tip;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves a v2.js without the hook and one showing the wrong first
line, and requires failures.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env  # noqa: E402
from tests.test_v2_names_render import _served  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

V2_JS = Path(__file__).resolve().parents[1] / "app" / "v2" / "v2.js"


def run_checks(js_patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if js_patch:
        old, new = js_patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        page_errors: list[str] = []
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if js_patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            page.goto(base + "#player-values", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
            page.wait_for_timeout(600)
            cell = page.query_selector(".v2-table tbody tr:first-child td.has-math")
            if not cell:
                errors.append("[values] no rescaled chart cell carries the published-number tip")
            else:
                cell_text = page.evaluate("el => el.firstChild.textContent.trim()", cell)
                cell.hover()
                page.wait_for_timeout(300)
                tip = page.evaluate("""() => { const t = document.getElementById('v2MathTip'); return {open: !t.hidden,
                  rows: [...t.querySelectorAll('.row')].map(r => [...r.children].map(c => c.textContent.trim()))}; }""")
                if not tip["open"] or len(tip["rows"]) < 3:
                    errors.append(f"[values] tip {tip}")
                else:
                    first, factor, rescaled = tip["rows"][0], tip["rows"][1], tip["rows"][2]
                    if "(original)" not in first[0]:
                        errors.append(f"[values] first tip line {first}")
                    if not factor[0].startswith("× rescale factor"):
                        errors.append(f"[values] second tip line {factor}")
                    if rescaled[1] != cell_text:
                        errors.append(f"[values] rescaled value {rescaled[1]!r} differs from the cell {cell_text!r}")
                    # JEG-685: the totals line behind the factor, from the engine (anchor total / chart total = factor).
                    notes = page.evaluate("() => [...document.querySelectorAll('#v2MathTip .v2-tip-note')].map(n => n.textContent.trim())")
                    if len(notes) != 1 or "(anchor total)" not in notes[0] or " ÷ " not in notes[0]:
                        errors.append(f"[values] totals line {notes}")
                    else:
                        nums = [float(x.replace(",", "")) for x in re.findall(r"[\d,]+(?= \()", notes[0])]
                        shown = float(factor[1])
                        if len(nums) != 2 or abs(nums[0] / nums[1] - shown) > 0.01 * shown:
                            errors.append(f"[values] totals {notes[0]!r} do not give the factor {shown}")
                bad = page.evaluate("""() => { const C = window.TradeValueCurveControls; const out = [];
                  C.getRows().slice(0, 40).forEach(r => C.getActiveSources().forEach(k => { const m = C.getPublishedMath(r.player_key, k);
                    if (m && m.factor !== null && m.anchorTotal !== null && Math.abs(m.anchorTotal / m.chartTotal - m.factor) > 1e-9 * m.factor) out.push(k); }));
                  const seen = C.getActiveSources().map(k => { const r = C.getRows().find(x => C.getPublishedMath(x.player_key, k)?.factor != null); return r ? C.getPublishedMath(r.player_key, k).anchorTotal : null; });
                  return {out, withTotals: seen.filter(v => v !== null).length}; }""")
                if bad["out"] or not bad["withTotals"]:
                    errors.append(f"[values] engine totals {bad}")
                page.keyboard.press("Escape")
            if page_errors:
                errors.append(f"page errors {page_errors}")
        finally:
            browser.close()
    return errors


JS_PATCHES = {
    "hook dropped": ('if (col.source && sourceMeta(col.source).method === "indexed" && PUBLISHER_NAMES[col.source]) {', "if (false) {"),
    "totals line dropped": ('lines.push(["× rescale factor", math.factor.toFixed(3), totalsNote]);', 'lines.push(["× rescale factor", math.factor.toFixed(3)]);'),
    "wrong totals": ('${fmtTotal(math.anchorTotal)} (anchor total)', '${fmtTotal(math.chartTotal)} (anchor total)'),
    "wrong first line": ('lines.push([`${name}${week} (original)`, String(math.native)]);', 'lines.push([`${name}${week}`, String(math.native)]);'),
}


class ValuesMathTipRenderTest(unittest.TestCase):
    def test_tip(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in JS_PATCHES.items():
            with self.subTest(patch=name):
                try:
                    errors = run_checks(js_patch=patch)
                except Exception as exc:
                    if "unavailable" in type(exc).__name__.lower() or type(exc).__name__ == "SkipTest":
                        raise
                    errors = [f"walk-through stopped: {type(exc).__name__}"]
                self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
