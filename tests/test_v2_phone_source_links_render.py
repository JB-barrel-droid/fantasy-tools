"""Phone tap-target guard for source links on Targets (JEG-817).

Every source link on the Targets page (header chips, the per-card USAT / FP
links, the explainer line) must be at least 44 x 44 px on a phone, and the
extra hit area must not push the page sideways.

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


def setUpModule():
    _render_env.ensure_built()


LINKS = """() => {
  const small = [];
  const shown = [...document.querySelectorAll('a.v2-srclink')].filter(a => a.getBoundingClientRect().width > 0);
  shown.forEach(a => {
    const r = a.getBoundingClientRect();
    if (r.height < 43.5 || r.width < 43.5) small.push(`${a.textContent.trim().slice(0, 14)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  });
  return {small, total: shown.length, over: document.documentElement.scrollWidth - document.documentElement.clientWidth};
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
        for width in (320, 375, 414):
            page = browser.new_page(viewport={"width": width, "height": 812})
            page.add_init_script(_render_env.pin_data_week_script())
            if css is not None:
                page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
            page.goto(base + "#trade-targets", wait_until="networkidle")
            page.wait_for_timeout(1200)
            out[width] = page.evaluate(LINKS)
            page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for width, r in result.items():
        if r["total"] < 4:
            errors.append(f"{width}: only {r['total']} source links found, the check is not looking at the cards")
        if r["small"]:
            errors.append(f"{width}: {len(r['small'])} source links under 44px, e.g. {r['small'][:3]}")
        # Sideways scroll is JEG-818's check (the 7-tab nav row at 320); here only the links' own extra width counts.
        if r["over"] > 0 and width != 320:
            errors.append(f"{width}: page scrolls sideways by {r['over']}")
    return errors


class PhoneSourceLinksTest(unittest.TestCase):
    def test_source_links_have_44px_targets(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        fix = re.search(r"/\* JEG-817 \(phone\).*?\n\}\n", css, re.S)
        self.assertTrue(fix, "stale mutation anchor")
        errors = _errors(_run(css.replace(fix.group(0), "")))
        self.assertTrue(any("under 44px" in e for e in errors), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
