"""JEG-1137 slice 3: the AI-connection panel (JEG-1266) on the Fieldnotes Home, through the built page.

With ?design=fieldnotes, at phone (390) and desktop (1280) widths:
  * Home carries #v2AiPanel with the corrected copy-pack heading, the "Connect the tool" link to the connect guide, setup
    state "available", and a share state of "ready" or "missing", never "unknown" once the page has loaded;
  * the panel's controls are at least 44px tall, nothing scrolls sideways, and no script error fires;
  * Copy link is reachable by keyboard, and with a stubbed clipboard Enter reports "Copied the link.".

Default page (no flag): mountAiPanel() is gated on fieldnotes(), so the panel is never mounted; #v2AiPanel has
zero children. test_default_page_never_shows_panel asserts child count 0, not only that the element is not visible.

Discrimination: test_guard_fails_without_panel_module opens the flagged page with window.TradeValueAiConnectionPanel
stubbed to null via a Playwright init-script. It asserts the child count is 0 (the panel was not mounted) and then
re-opens without the stub and asserts the child count is non-zero (the real module mounted it), confirming the check
fails before and passes after.
"""
from __future__ import annotations

import unittest

from tests import _render_env
from tests._league_render import browser_on_build
from tests.test_v2_fieldnotes_nav_render import FLAG, WIDTHS, open_page

GUIDE = "https://jb-barrel-droid.github.io/fantasy-tools/connect/"
PANEL = """() => { const p = document.getElementById('v2AiPanel'); if (!p) return {present: false};
  const r = p.getBoundingClientRect(), connect = p.querySelector('#aipConnect');
  const small = [...p.querySelectorAll('a, button')].filter(e => e.getBoundingClientRect().width && e.getBoundingClientRect().height < 44)
    .map(e => e.textContent.trim() + ' ' + Math.round(e.getBoundingClientRect().height));
  return {present: true, shown: r.height > 0, heading: (p.querySelector('h2') || {}).textContent || '',
    connectHref: connect && connect.getAttribute('href'), connectText: connect && connect.textContent.trim(),
    setup: (p.querySelector('[data-setup]') || {}).dataset && p.querySelector('[data-setup]').dataset.setup,
    share: (p.querySelector('[data-share]') || {}).dataset && p.querySelector('[data-share]').dataset.share,
    childCount: p.children.length,
    small, overflow: document.documentElement.scrollWidth - window.innerWidth}; }"""

# Stubs window.TradeValueAiConnectionPanel to null before any page script runs.
_STUB_NULL_PANEL = (
    "Object.defineProperty(window, 'TradeValueAiConnectionPanel',"
    " {get: () => null, configurable: true});"
)


def setUpModule():
    _render_env.ensure_built()


def _open_raw(browser, base, width, height, flag=FLAG, extra_init=None):
    """Open a page with an optional extra init-script; returns (ctx, page)."""
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light")
    ctx.add_init_script(_render_env.pin_data_week_script())
    if extra_init:
        ctx.add_init_script(extra_init)
    page = ctx.new_page()
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    page.goto(base + flag, wait_until="networkidle")
    page.wait_for_function(
        "() => window.TradeValueV2 && window.TradeValueV2.view()",
        timeout=60000,
    )
    return ctx, page


class FieldnotesAiPanelTests(unittest.TestCase):
    maxDiff = None

    def test_panel_on_home(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                with self.subTest(width=width):
                    errors: list[str] = []
                    tag = f"{width}px"
                    page = open_page(browser, base, width, height, errors=errors)
                    page.wait_for_function("() => document.querySelector('#v2AiPanel [data-share]')", timeout=10000)
                    got = page.evaluate(PANEL)
                    if not got["shown"]:
                        errors.append(f"{tag}: panel not visible on Home")
                    if got["heading"] != "Find your best trade in Claude or ChatGPT":
                        errors.append(f"{tag}: heading {got['heading']!r}")
                    if got["connectHref"] != GUIDE or got["connectText"] != "Connect the tool":
                        errors.append(f"{tag}: connect link {got['connectText']!r} -> {got['connectHref']!r}")
                    if got["setup"] != "available":
                        errors.append(f"{tag}: setup state {got['setup']!r}")
                    if got["share"] not in ("ready", "missing"):
                        errors.append(f"{tag}: share state {got['share']!r}")
                    if got["small"]:
                        errors.append(f"{tag}: controls under 44px: {got['small']}")
                    if got["overflow"] > 0:
                        errors.append(f"{tag}: scrolls sideways by {got['overflow']}px")
                    self.assertEqual(errors, [])
                    page.context.close()

    def test_copy_link_by_keyboard(self):
        with browser_on_build() as (browser, base):
            errors: list[str] = []
            page = open_page(browser, base, 1280, 900, errors=errors)
            page.evaluate("() => { navigator.clipboard.writeText = () => Promise.resolve(); }")
            page.wait_for_function("() => document.querySelector('#v2AiPanel [data-share]')", timeout=10000)
            button = page.locator("#v2AiPanel button", has_text="Copy link")
            if button.count() == 0 or page.evaluate("() => document.querySelector('#v2AiPanel [data-share]').dataset.share") != "ready":
                # No link to copy yet (no league, no trade): the panel must say so rather than offer a dead button.
                self.assertEqual(page.evaluate("() => document.querySelector('#v2AiPanel [data-share]').dataset.share"), "missing")
            else:
                button.focus()
                page.keyboard.press("Enter")
                page.wait_for_function("() => document.querySelector('#v2AiPanel').innerText.includes('Copied the link.')", timeout=5000)
            self.assertEqual(errors, [])

    def test_default_page_never_shows_panel(self):
        """Without ?design=fieldnotes, mountAiPanel() is gated off. #v2AiPanel must have zero children."""
        with browser_on_build() as (browser, base):
            ctx, page = _open_raw(browser, base, 1280, 900, flag="")
            try:
                self.assertFalse(
                    page.locator("#v2AiPanel").is_visible(),
                    "#v2AiPanel is visible on the default page",
                )
                child_count = page.evaluate("() => document.getElementById('v2AiPanel').children.length")
                self.assertEqual(
                    child_count,
                    0,
                    f"#v2AiPanel has {child_count} children on the default page (panel was mounted without the flag)",
                )
            finally:
                ctx.close()

    def test_guard_fails_without_panel_module(self):
        """Panel child count is 0 when the module is stubbed to null (fail-before), non-zero with the real module (pass-after)."""
        with browser_on_build() as (browser, base):
            # --- fail-before: module stubbed to null ---
            ctx_stub, page_stub = _open_raw(browser, base, 1280, 900, extra_init=_STUB_NULL_PANEL)
            try:
                count_without = page_stub.evaluate("() => document.getElementById('v2AiPanel').children.length")
            finally:
                ctx_stub.close()

            # --- pass-after: real module present ---
            ctx_real, page_real = _open_raw(browser, base, 1280, 900)
            try:
                page_real.wait_for_function("() => document.querySelector('#v2AiPanel [data-share]')", timeout=10000)
                count_with = page_real.evaluate("() => document.getElementById('v2AiPanel').children.length")
            finally:
                ctx_real.close()

            self.assertEqual(count_without, 0, "panel was mounted even with module stubbed to null")
            self.assertGreater(count_with, 0, "panel was not mounted with the real module present")


if __name__ == "__main__":
    unittest.main()
