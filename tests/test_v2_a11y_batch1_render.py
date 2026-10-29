"""A11y batch 1 (JEG-896, JEG-898, JEG-902), rendered.

  * JEG-896 (retired, JEG-1044): the Customize "DDF blend" tab and its arrow-key checks are gone with the tab
    (Jeremy 2026-10-24). The open Customize dialog still names itself in document.title (checked below).
  * JEG-898: document.title names the view, the Writing / Values auditing section and an open modal dialog.
  * JEG-902: computed-style contrast. Rank value cells and the Y-axis toggle >= 4.5:1 in light and dark
    (alpha composited), field / button borders >= 3:1 against the page, nav focus ring >= 3:1 on the nav bar.

Discrimination: test_guard_fails_on_broken_builds serves a v2.js / v2.css with each fix reverted and requires
the matching check to fail.
"""
from __future__ import annotations

import functools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_a11y_render import V2_CSS, V2_JS, _built_dist, _serve  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


HELPERS = r"""
const parse = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[,\/ ]+/).filter(Boolean).map(Number);
  return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b); };
const over = (top, under) => ({r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a),
  b: top.b * top.a + under.b * (1 - top.a), a: 1});
const bgOf = el => { const chain = []; for (let n = el; n && n.nodeType === 1; n = n.parentElement) chain.push(parse(getComputedStyle(n).backgroundColor));
  let acc = {r: 255, g: 255, b: 255, a: 1}; for (const c of chain.reverse()) if (c && c.a > 0) acc = over(c, acc); return acc; };
const ratio = (a, b) => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
"""

TEXT_CONTRAST = "() => {" + HELPERS + r"""
  const out = [];
  document.querySelectorAll('#v2Table td.num.is-rank, #v2AxisZoom').forEach(el => {
    if (!el.getBoundingClientRect().width) return;
    const r = ratio(over(parse(getComputedStyle(el).color), bgOf(el)), bgOf(el));
    if (r < 4.5) out.push(`${el.id || 'rank cell'} ${r.toFixed(2)}<4.5`);
  });
  return out;
}"""

BORDER_CONTRAST = "() => {" + HELPERS + r"""
  const out = [];
  const page = bgOf(document.body);
  document.querySelectorAll('#v2Search, #v2Position, #v2EditSources').forEach(el => {
    if (!el.getBoundingClientRect().width) return;
    const cs = getComputedStyle(el);
    const r = ratio(parse(cs.borderTopColor), page);
    if (r < 3) out.push(`${el.id} border ${r.toFixed(2)}<3`);
  });
  return out;
}"""

# The probe sits in the always-visible top bar. Since JEG-1106 (9cffc5cb, Jeremy 2026-10-25) the tabs live in a menu
# that is closed (display: none) until opened, so a probe next to a tab could not take focus and the check passed
# without measuring anything. A probe that is not focused or does not match :focus-visible is now an error.
FOCUS_RING = "() => {" + HELPERS + r"""
  const bar = document.querySelector('.v2-nav .v2-nav-inner');
  const probe = document.createElement('a'); probe.href = '#'; probe.textContent = 'x';
  bar.appendChild(probe); probe.focus();
  const focused = document.activeElement === probe;
  const cs = getComputedStyle(probe); const matched = probe.matches(':focus-visible');
  const ring = parse(cs.outlineColor); const nav = bgOf(document.querySelector('.v2-nav'));
  probe.remove();
  if (!focused || !matched) return {error: `nav focus probe not measured (focused=${focused}, focus-visible=${matched})`};
  return {ratio: ratio(ring, nav)};
}"""

TITLES = {
    "player-values": "Player values",
    "trade-targets": "Trade targets",
    "risers-fallers": "Risers & fallers",
    "compare-trade": "Compare a trade",
    "writing/manifesto": "Manifesto · Writing",
    "values-auditing": "Values auditing",
}


def run_checks(v2_js=None, v2_css=None, only=("dialog", "titles", "contrast")) -> list[str]:
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
            for scheme in ("light", "dark"):
                page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme=scheme)
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
                if v2_css is not None:
                    page.route("**/v2/v2.css*", functools.partial(_serve, v2_css, "text/css"))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=40000)
                tag = f"[{scheme}] "
                if "contrast" in only:
                    errors += [f"{tag}{e}" for e in page.evaluate(TEXT_CONTRAST)]
                    # The audited 4.06:1 is the hovered row (--v2-hover-rank), the tightest rank-cell background.
                    page.hover("#v2Table tbody tr:nth-child(3) td.is-rank")
                    errors += [f"{tag}hover {e}" for e in page.evaluate(TEXT_CONTRAST)]
                    page.mouse.move(0, 0)
                    errors += [f"{tag}{e}" for e in page.evaluate(BORDER_CONTRAST)]
                    ring = page.evaluate(FOCUS_RING)
                    if "error" in ring:
                        errors.append(f"{tag}{ring['error']}")
                    elif ring["ratio"] < 3:
                        errors.append(f"{tag}nav focus ring {ring['ratio']:.2f}<3")
                    page.click("#v2ExpandChart")
                    page.wait_for_timeout(300)
                    errors += [f"{tag}expanded {e}" for e in page.evaluate(TEXT_CONTRAST)]
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)
                if "dialog" in only and scheme == "light":
                    page.click("#v2EditSources")
                    page.wait_for_selector("#v2Popover")
                    title = page.title()
                    if not title.startswith("Customize values · Player values"):
                        errors.append(f"{tag}dialog title {title!r}")
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(150)
                if "titles" in only and scheme == "light":
                    for route, name in TITLES.items():
                        page.evaluate(f"() => {{ location.hash = '#{route}'; }}")
                        page.wait_for_timeout(400)
                        want = f"{name} · Data Driven Football"
                        if page.title() != want:
                            errors.append(f"{tag}#{route}: title {page.title()!r}, wanted {want!r}")
                page.close()
        finally:
            browser.close()
    return errors


class A11yBatch1Test(unittest.TestCase):
    def test_dialog_titles_contrast(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        broken = {
            "title never set": ({"v2_js": js.replace("document.title = parts", "void parts", 1)}, ("titles",)),
            "rank text reverted": ({"v2_css": css.replace("background: var(--v2-hover-rank); color: var(--v2-action-strong); }", "background: var(--v2-hover-rank); }", 1)}, ("contrast",)),
            "field border reverted": ({"v2_css": css.replace("border: 1px solid var(--v2-field-border); background: var(--v2-surface); border-radius: var(--v2-radius-btn);\n  padding: 10px 14px;",
                                                           "border: 1px solid var(--v2-border); background: var(--v2-surface); border-radius: var(--v2-radius-btn);\n  padding: 10px 14px;", 1)}, ("contrast",)),
            "nav ring reverted": ({"v2_css": css.replace(".v2-nav :focus-visible { outline-color: #fff; }", "", 1)}, ("contrast",)),
        }
        for name, (kwargs, only) in broken.items():
            with self.subTest(mutation=name):
                body = next(iter(kwargs.values()))
                self.assertNotIn(body, (js, css), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(**kwargs, only=only), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
