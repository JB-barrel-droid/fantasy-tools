"""How values work (the value-logic frame) in the Fieldnotes design (JEG-1140), in a real browser.

Opens the built dashboard at /v2/#writing/how-values and reads the explainer frame (value-logic/):

  * with ?design=fieldnotes the frame mirrors the dashboard's Fieldnotes tokens (panel color equals the parent's surface), light and dark, at 1280 and 390 px, with no sideways scroll and no page errors;
  * every button, field and section link in the frame is at least 44 px tall, and a keyboard focus ring is 3 px;
  * the frame follows a theme switch on the parent without a reload;
  * without the flag the frame is unchanged: no data-design, and the original page color.

Discrimination: test_guard_fails_without_the_rules (no browser) asserts the template contains the
Fieldnotes CSS block and the JS mirror code, and that every selector in that block is scoped to the flag.
Skips with no browser unless RENDER_TESTS_REQUIRED=1 (browser tests only).
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "values-explainer" / "template.html"
ORIGINAL_BG = "rgb(255, 255, 255)"  # the panel before Fieldnotes (light); the frame body is transparent when embedded

ROUTE = "v2/{flag}#writing/how-values"
FRAME = """async () => {
  const f = document.getElementById('v2ValueLogicFrame');
  f.scrollIntoView(); f.removeAttribute('loading'); if (!f.src) f.src = f.dataset.src;
  for (let i = 0; i < 300 && !(f.contentDocument && f.contentDocument.querySelector('nav.index a') && f.contentDocument.querySelector('.seg button')); i++) await new Promise(r => setTimeout(r, 100));
  const d = f.contentDocument, w = f.contentWindow, root = d.documentElement, p = getComputedStyle(document.documentElement);
  const bg = el => getComputedStyle(el).backgroundColor, panel = d.querySelector('.panel');
  const small = [...d.querySelectorAll('nav.index a, .seg button, .srcnav button, select, input[type=search], details.fold summary')]
    .filter(el => { const r = el.getBoundingClientRect(); return r.width && r.height && r.height < 43.5; }).map(el => el.className || el.tagName);
  const tmp = d.createElement('span'); tmp.style.color = p.getPropertyValue('--ddf-surface'); d.body.appendChild(tmp);
  const parentCanvas = getComputedStyle(tmp).color; tmp.remove();
  return {design: root.dataset.design || null, bodyBg: bg(panel), parentCanvas, small,
    overflow: d.documentElement.scrollWidth - w.innerWidth, display: getComputedStyle(d.querySelector('h2')).fontFamily};
}"""


def _frame(page):
    return page.evaluate(FRAME)


class ExplainerFieldnotesRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _render_env.ensure_built()
        cls._cm = browser_on_build()
        try:
            cls.browser, cls.base = cls._cm.__enter__()
        except unittest.SkipTest:
            raise
        cls.root = cls.base.split("v2")[0] if "v2" in cls.base else cls.base

    @classmethod
    def tearDownClass(cls):
        cls._cm.__exit__(None, None, None)

    def open(self, flag, width, scheme="light"):
        ctx = self.browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
        ctx.add_init_script(_render_env.pin_data_week_script())
        page = ctx.new_page()
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(str(e)))
        page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
        page.goto(self.base + flag + "#writing/how-values", wait_until="domcontentloaded")
        page.wait_for_selector("#v2ValueLogicFrame", state="attached", timeout=60000)
        return page

    def test_frame_mirrors_the_tokens_in_both_themes_and_widths(self):
        for scheme in ("light", "dark"):
            for width in (1280, 390):
                with self.subTest(scheme=scheme, width=width):
                    page = self.open("?design=fieldnotes", width, scheme)
                    got = _frame(page)
                    self.assertEqual(got["design"], "fieldnotes")
                    self.assertEqual(got["bodyBg"], got["parentCanvas"])
                    if scheme == "dark":
                        self.assertNotEqual(got["bodyBg"], ORIGINAL_BG)
                    self.assertEqual(got["small"], [])
                    self.assertLessEqual(got["overflow"], 0)
                    self.assertTrue(got["display"].startswith("Fraunces"), got["display"])
                    self.assertEqual(self.errors, [])
                    page.context.close()

    def test_frame_follows_a_theme_switch(self):
        # The frame's MutationObserver re-reads the parent's resolved tokens when data-theme changes.
        # Without the change the frame uses its own fixed CSS variables and its panel colour never
        # matches the parent's dark --ddf-surface.  With the change they are equal.
        page = self.open("?design=fieldnotes", 1280)
        _frame(page)  # wait for the frame to load
        page.evaluate("document.documentElement.dataset.theme = 'dark'")
        page.wait_for_timeout(400)
        result = page.evaluate("""() => {
          const f = document.getElementById('v2ValueLogicFrame');
          const d = f.contentDocument, p = getComputedStyle(document.documentElement);
          const panel = d.querySelector('.panel');
          const framePanelBg = getComputedStyle(panel).backgroundColor;
          // Resolve --ddf-surface from the (now dark) parent into an rgb() string the same way FRAME does.
          const tmp = d.createElement('span');
          tmp.style.color = p.getPropertyValue('--ddf-surface');
          d.body.appendChild(tmp);
          const parentDarkSurface = getComputedStyle(tmp).color;
          tmp.remove();
          return {framePanelBg, parentDarkSurface};
        }""")
        self.assertEqual(result["framePanelBg"], result["parentDarkSurface"])
        page.context.close()

    def test_focus_ring_is_three_pixels(self):
        page = self.open("?design=fieldnotes", 1280)
        _frame(page)
        width = page.evaluate("""() => { const d = document.getElementById('v2ValueLogicFrame').contentDocument;
          const a = d.querySelector('nav.index a'); a.focus(); return getComputedStyle(a).outlineWidth; }""")
        self.assertEqual(width, "3px")
        page.context.close()

    def test_default_frame_is_unchanged(self):
        page = self.open("", 1280)
        got = _frame(page)
        self.assertIsNone(got["design"])
        self.assertEqual(got["bodyBg"], ORIGINAL_BG)
        page.context.close()


class ExplainerGuardTest(unittest.TestCase):
    def test_guard_fails_without_the_rules(self):
        text = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('html[data-design="fieldnotes"]:root {', text)
        self.assertIn('root.dataset.design = "fieldnotes"', text)
        stripped = re.sub(r'html\[data-design="fieldnotes"\][^{]*\{[^}]*\}\n?', "", text)
        self.assertNotIn('html[data-design="fieldnotes"]:root {', stripped)
        # every Fieldnotes rule is scoped to the flag
        for sel in re.findall(r'^([^\n{@/*][^{]*)\{', text[text.index("/* Fieldnotes (JEG-1140)"):text.index("</style>")], re.M):
            self.assertIn('[data-design="fieldnotes"]', sel, sel)


if __name__ == "__main__":
    unittest.main()
