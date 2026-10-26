"""JEG-957: on the Writing tab the sub-tab row (Manifesto / How values work / Research) is the first
element under the top nav, above every other section, for every sub-tab, at 1440 and 390 px.

Before: #v2Writing sat after #v2League ("Chart settings") and #v2Methods ("On the chart") in the shell, so
"How values work" (the one sub-tab that shows those bars) rendered the sub-tabs below them.

Discrimination: test_guard_fails_on_broken_order serves a shell with the sub-tab row moved back below the
league bar and requires the check to fail.
"""
from __future__ import annotations

import re
import unittest

from playwright.sync_api import Error as PlaywrightError  # noqa: F401

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_expand_render import _built_dist  # noqa: E402

def setUpModule():
    _render_env.ensure_built()


SUBTABS = ("writing/manifesto", "writing/how-values", "writing/research")

# Visible blocks under the top nav, in page order by their top edge; the first must be the sub-tab row.
READ = """() => {
  const app = document.getElementById('v2App');
  const shown = [...app.children].filter(el => !el.hidden && el.getBoundingClientRect().height > 0
    && !el.classList.contains('v2-skip') && !el.classList.contains('v2-sr') && !el.matches('header.v2-nav') && !el.matches('dialog, [role=dialog], .v2-overlay'));
  const rows = shown.map(el => ({id: el.id || el.className, top: el.getBoundingClientRect().top}));
  rows.sort((a, b) => a.top - b.top);
  const tabs = document.getElementById('v2WritingTabs').getBoundingClientRect();
  const wrap = document.getElementById('v2Writing').getBoundingClientRect();
  return {tabsTop: tabs.top, tabsVisible: tabs.height > 0,
          above: rows.filter(r => r.id !== 'v2Writing' && r.top < wrap.top - 0.5).map(r => r.id)};
}"""


def run_checks(mutate=None) -> list[str]:
    from playwright.sync_api import sync_playwright
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 900), (390, 844)):
                for route in SUBTABS:
                    tag = f"[{width}px {route}] "
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                    if mutate is not None:
                        page.route("**/v2/", lambda r: r.fulfill(response=r.fetch(), body=mutate(r.fetch().text())))
                    page.goto(base + "#" + route, wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueV2", timeout=60000)
                    page.wait_for_timeout(500)
                    got = page.evaluate(READ)
                    if not got["tabsVisible"]:
                        errors.append(f"{tag}sub-tab row not visible")
                    elif got["above"]:
                        errors.append(f"{tag}sections above the sub-tab row: {got['above']}")
                    page.close()
        finally:
            browser.close()
    return errors


class WritingSubtabsOrderTest(unittest.TestCase):
    def test_subtabs_first_for_every_writing_subtab(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_order(self):
        def old_order(html):
            block = re.search(r'<div class="v2-wrap v2-writing-nav" id="v2Writing" hidden>.*?\n  </div>\n', html, re.S)
            self.assertIsNotNone(block, "mutation anchor is stale")
            html = html.replace(block.group(0), "", 1)
            anchor = '<div class="v2-wrap v2-state-wrap" id="v2State">'
            self.assertIn(anchor, html, "mutation anchor is stale")
            return html.replace(anchor, block.group(0) + "  " + anchor, 1)
        errors = run_checks(old_order)
        self.assertTrue(any("how-values" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
