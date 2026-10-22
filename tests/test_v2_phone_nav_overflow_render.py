"""Phone nav guard (JEG-818): the nav row of seven tabs must not widen the page.

The nav has seven real tabs (Writing, Player values, Trade targets, Risers & fallers, Compare a trade, Find a trade,
Values auditing; JEG-852 added the seventh), and the count is pinned to seven. At 320 px the nowrap row of seven 44 px tabs pushed the document 47 px sideways.
The page must not scroll sideways at 320, 375, 414, 768 or 1440, every tab must
still be on screen inside the viewport, and each tab keeps a 44 px hit area on
phones.

Discrimination: test_guard_fails_on_old_css serves the CSS with the fix removed
and requires the check to fail.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_v2_phone_weight_render import _served

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
WIDTHS = (320, 375, 414, 768, 1440)


def setUpModule():
    _render_env.ensure_built()


NAV = """() => {
  const vw = document.documentElement.clientWidth;
  const tabs = [...document.querySelectorAll('.v2-tabs .v2-tab')].map(t => t.getBoundingClientRect());
  return {
    over: document.documentElement.scrollWidth - vw,
    count: tabs.length,
    offscreen: tabs.filter(r => r.left < -0.5 || r.right > vw + 0.5).length,
    short: tabs.filter(r => r.height < 43.5 || r.width < 43.5).length,
  };
}"""


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {}
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        for width in WIDTHS:
            page = browser.new_page(viewport={"width": width, "height": 812})
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#trade-targets", wait_until="networkidle")
            page.wait_for_timeout(1000)
            out[width] = page.evaluate(NAV)
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, r in result.items():
        if r["count"] != 7:
            errors.append(f"{width}: {r['count']} tabs, want 7")
        if r["over"] > 0:
            errors.append(f"{width}: page scrolls sideways by {r['over']}")
        if r["offscreen"]:
            errors.append(f"{width}: {r['offscreen']} tabs outside the viewport")
        if width < 768 and r["short"]:
            errors.append(f"{width}: {r['short']} tabs under 44px")
    return errors


class PhoneNavOverflowTest(unittest.TestCase):
    def test_nav_never_widens_the_page(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        fix = re.search(r"/\* JEG-818 \(phone\).*?\n\}\n", css, re.S)
        self.assertTrue(fix, "stale mutation anchor")
        errors = _errors(_run(css.replace(fix.group(0), "")))
        self.assertTrue(any("sideways" in e for e in errors), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
