"""JEG-1137 slice 3: the AI-connection panel (JEG-1266) on the Fieldnotes Home, through the built page.

With ?design=fieldnotes, at phone (390) and desktop (1280) widths:
  * Home carries #v2AiPanel with the corrected copy-pack heading, the "Connect the tool" link to the connect guide, setup
    state "available", and a share state of "ready" or "missing", never "unknown" once the page has loaded;
  * the panel's controls are at least 44px tall, nothing scrolls sideways, and no script error fires;
  * Copy link is reachable by keyboard, and with a stubbed clipboard Enter reports "Copied the link.".

Default page: the panel exists in the shell but Home is hidden, so it never shows without the flag.
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
    small, overflow: document.documentElement.scrollWidth - window.innerWidth}; }"""


def setUpModule():
    _render_env.ensure_built()


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
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, 1280, 900, flag="")
            self.assertFalse(page.locator("#v2AiPanel").is_visible())


if __name__ == "__main__":
    unittest.main()
