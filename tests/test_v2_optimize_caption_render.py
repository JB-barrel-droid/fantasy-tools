"""JEG-1023: the Optimize for control in Edit league carries a plain-text
"not reviewed" caption (Jeremy, 2026-10-24: the playoffs option is unreviewed).

Checks, at 1440, 390 and 320 wide: the caption is present, the Playoffs button
points at it with aria-describedby, it does not overflow the panel or the page,
and the segmented buttons stay at least 44 px tall.

Discrimination: test_guard_fails_on_broken_builds serves v2.js without the
caption, without the association, and with a fixed-width caption, and requires
failure.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_v2_share_render import V2_JS, _built_dist, _serve
from tests.test_published_league_settings_render import _chromium_executable


def setUpModule():
    _render_env.ensure_built()


PROBE = """() => {
  const cap = document.getElementById('v2OptimizeNotReviewed');
  const btn = document.querySelector('.v2-pseg button[data-value="playoffs"]');
  const seg = btn && btn.closest('.v2-pseg');
  const doc = document.documentElement;
  const r = cap && cap.getBoundingClientRect();
  const panel = cap && (cap.closest('[role=dialog], .v2-panel, aside') || cap.parentElement);
  const pr = panel && panel.getBoundingClientRect();
  return {
    text: cap ? cap.textContent : null,
    describedby: btn ? btn.getAttribute('aria-describedby') : null,
    capVisible: !!(r && r.width > 0 && r.height > 0),
    capRight: r ? r.right : null, capLeft: r ? r.left : null,
    panelRight: pr ? pr.right : null, panelLeft: pr ? pr.left : null,
    capScroll: cap ? cap.scrollWidth - cap.clientWidth : null,
    pageOverflow: doc.scrollWidth - doc.clientWidth,
    minButton: seg ? Math.min(...[...seg.querySelectorAll('button')].map(b => b.getBoundingClientRect().height)) : null,
    after: !!(seg && seg.nextElementSibling === cap),
  };
}"""


def run_checks(v2_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 1000), (390, 800), (320, 700)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page.errors = []
                page.on("pageerror", lambda e: page.errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js))
                page.goto(base + "#compare-trade", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare()", timeout=30000)
                page.click("#v2EditLeague")
                page.wait_for_timeout(300)
                s = page.evaluate(PROBE)
                tag = f"@{width}"
                if not s["text"] or "not reviewed" not in s["text"].lower():
                    errors.append(f"{tag} caption text missing: {s['text']!r}")
                if s["describedby"] != "v2OptimizeNotReviewed":
                    errors.append(f"{tag} Playoffs button not associated: {s['describedby']!r}")
                if not s["capVisible"]:
                    errors.append(f"{tag} caption not visible")
                if not s["after"]:
                    errors.append(f"{tag} caption is not next to the Optimize for control")
                if s["capVisible"] and (s["capRight"] > s["panelRight"] + 0.5 or s["capLeft"] < s["panelLeft"] - 0.5 or s["capScroll"] > 0):
                    errors.append(f"{tag} caption overflows its panel: {s}")
                if s["pageOverflow"] > 0:
                    errors.append(f"{tag} page overflows horizontally by {s['pageOverflow']}")
                if s["minButton"] is None or s["minButton"] < 43.5:
                    errors.append(f"{tag} Optimize for buttons shorter than 44 px: {s['minButton']}")
                if page.errors:
                    errors.append(f"{tag} page errors {page.errors}")
                page.close()
        finally:
            browser.close()
    return errors


class OptimizeCaptionRenderTest(unittest.TestCase):
    def test_caption_present_associated_fits(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        broken = {
            "no caption": js.replace('content.appendChild(optimizeCaption);', "", 1),
            "not associated": js.replace('playoffsButton.setAttribute("aria-describedby", optimizeCaption.id)', "void 0", 1),
            "caption overflows": js.replace('optimizeCaption.id = "v2OptimizeNotReviewed";', 'optimizeCaption.id = "v2OptimizeNotReviewed"; optimizeCaption.style.cssText = "white-space:nowrap;width:700px";', 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(body), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
