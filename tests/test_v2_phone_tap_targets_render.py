"""Phone tap targets, landscape panels and enlarged wide-face text (JEG-861, part A).

Three checks against the built dist/:

1. At 375 x 812, on every tab (and with the Customize and Edit league panels open), every interactive
   element has an effective hit box of at least 44 x 44 px. The effective box counts a centred absolute
   pseudo-element (the .v2-fchip pattern). Exempt: inline links inside prose (WCAG 2.5.8 inline exception),
   tooltip triggers (.has-math cells, table rows with tabindex, waterfall steps), and a checkbox whose label
   is the 44 px target. Before JEG-861 the Compare search inputs were 36 px, the "How to use it" and
   "Every pairing" summaries 32 px, the rank-brush fill 16 px and the Values header ↗ link 39 x 43.
2. At 320 x 812 in a wide fallback face (Verdana or DejaVu Sans) with every font size raised 3 px (a
   user text-size setting), Targets and Player values do not scroll sideways.
3. At 812 x 375 the Customize panel body is at least 200 px tall (it was about 110 px).

Discrimination: test_guard_fails_on_old_css serves the CSS with the three JEG-861 blocks removed and
requires every check to fail.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_v2_phone_weight_render import _served

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
FIX = re.compile(r"\n/\* JEG-861[^\n]*\n(?:[^\n]*\n)*?\}\n")
TABS = ("player-values", "trade-targets", "risers-fallers", "compare-trade", "writing/how-values", "writing/research", "values-auditing", "writing/manifesto")
PANELS = (("player-values", "#v2EditSources"), ("player-values", "#v2EditLeague"))
FAMILIES = ("DejaVu Sans", "Verdana")

HAS_FACE = """(family) => { const c = document.createElement('canvas').getContext('2d'); const t = 'Wide fallback face WMwmi 0123';
  c.font = "40px monospace"; const a = c.measureText(t).width; c.font = `40px '${family}', monospace`; return c.measureText(t).width !== a; }"""

SMALL = """() => {
  const sel = 'a[href], button, input, select, textarea, summary, [role=button], [role=tab], [tabindex]:not([tabindex="-1"]), label';
  const px = v => (v && v.endsWith('px')) ? parseFloat(v) : 0;
  const out = []; const seen = new Set(); let total = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('[hidden], [aria-hidden="true"]')) continue;
    if (el.tagName === 'LABEL' && !el.querySelector('input,select')) continue;
    if (el.tagName === 'INPUT' && (el.type === 'checkbox' || el.type === 'radio') && el.closest('label')) continue;
    if (el.matches('.has-math, tr, td, .v2-wf-step, .v2-wf-land')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.pointerEvents === 'none') continue;
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) continue;
    if (cs.display === 'inline' && el.tagName === 'A' && el.closest('p, li, dd, figcaption, .v2-meta')) continue;
    total++;
    let w = r.width, h = r.height;
    for (const ps of ['::before', '::after']) {
      const p = getComputedStyle(el, ps);
      if ((p.content !== '""' && p.content !== "''") || p.position !== 'absolute') continue;
      if (px(p.height)) h = Math.max(h, px(p.height));
      if (px(p.width)) w = Math.max(w, px(p.width));
    }
    if (w >= 43.5 && h >= 43.5) continue;
    const key = el.id + '|' + el.className + '|' + (el.textContent || el.placeholder || '').trim().slice(0, 20);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(`${el.tagName.toLowerCase()}#${el.id}.${String(el.className).slice(0, 40)} '${(el.textContent || el.placeholder || el.getAttribute('aria-label') || '').trim().slice(0, 20)}' ${Math.round(w)}x${Math.round(h)}`);
  }
  return {small: out, total};
}"""
OVER = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
PLUS = "(n) => { for (const e of document.querySelectorAll('body *')) { const fs = parseFloat(getComputedStyle(e).fontSize); e.style.fontSize = (fs + n) + 'px'; } }"
PANEL_BODY = "() => { const b = document.querySelector('#v2Popover.is-panel .v2-panel-body'); return b ? b.clientHeight : null; }"


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {"small": {}, "over": {}, "panel": None}

    def open_page(browser, width, height, tab, init=None):
        page = browser.new_page(viewport={"width": width, "height": height})
        if init:
            page.add_init_script(init)
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        page.goto(base + "#" + tab, wait_until="networkidle")
        page.wait_for_timeout(1000)
        return page

    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        probe = browser.new_page()
        family = next((f for f in FAMILIES if probe.evaluate(HAS_FACE, f)), None)
        probe.close()
        for tab in TABS:
            page = open_page(browser, 375, 812, tab)
            out["small"][tab] = page.evaluate(SMALL)
            page.close()
        for tab, opener in PANELS:
            page = open_page(browser, 375, 812, tab)
            page.locator(opener).first.click()
            page.wait_for_timeout(500)
            out["small"][f"{tab}+{opener}"] = page.evaluate(SMALL)
            page.close()
        if family is not None:
            init = ("document.addEventListener('DOMContentLoaded',()=>{const s=document.createElement('style');"
                    f"s.textContent=\"*{{font-family:'{family}',sans-serif !important}}\";document.head.appendChild(s)}})")
            for tab in ("trade-targets", "player-values"):
                page = open_page(browser, 320, 812, tab, init)
                page.evaluate(PLUS, 3)
                page.wait_for_timeout(500)
                out["over"][tab] = page.evaluate(OVER)
                page.close()
        page = open_page(browser, 812, 375, "player-values")
        page.locator("#v2EditSources").first.click()
        page.wait_for_timeout(500)
        out["panel"] = page.evaluate(PANEL_BODY)
        page.close()
        browser.close()
    return out


def _errors(result) -> list[str]:
    errors = []
    for tab, r in result["small"].items():
        if r["total"] < 10:
            errors.append(f"{tab}: only {r['total']} controls found, the sweep is not looking at the page")
        if r["small"]:
            errors.append(f"{tab}: {len(r['small'])} controls under 44px: {r['small'][:4]}")
    for tab, over in result["over"].items():
        if over > 0:
            errors.append(f"320 +3px {tab}: page scrolls sideways by {over}")
    if result["panel"] is None or result["panel"] < 200:
        errors.append(f"812x375: Customize panel body only {result['panel']}px")
    return errors


class PhoneTapTargetsTest(unittest.TestCase):
    def test_phone_controls_fit_and_reach_44px(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertEqual(len(FIX.findall(css)), 3, "stale mutation anchor")
        errors = _errors(_run(FIX.sub("\n", css)))
        self.assertTrue(any("under 44px" in e for e in errors), f"old CSS tap targets were not caught: {errors}")
        self.assertTrue(any("scrolls sideways" in e for e in errors), f"old CSS 320 +3px overflow was not caught: {errors}")
        self.assertTrue(any("panel body" in e for e in errors), f"old CSS landscape panel was not caught: {errors}")


if __name__ == "__main__":
    unittest.main()
