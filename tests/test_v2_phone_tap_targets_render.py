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
4. No two interactive elements overlap (JEG-884): on every tab at 375, 768, 1024, 1280 and 1440 px,
   elementFromPoint at each control's centre and four edge midpoints is that control, a descendant, or
   its own label. Before JEG-884 the module Expand / Collapse buttons sat over the Compare search boxes
   from 1024 px up (at 1280 a click in the box expanded the card), and over the box's top 4 px below that;
   the "On this page" source links' 44 px boxes crossed rows at 375, and the chart legend's crossed rows at
   1280x800. Brush fills and the chart region are checked at their centre only (their edges carry their own
   thumbs and the zoom buttons), and a decorative overlay (an icon) is a dead spot, not a mis-tap.

Discrimination: test_guard_fails_on_old_css serves the CSS with the five JEG-861 / JEG-884 blocks removed
and requires every check to fail.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_v2_phone_weight_render import _served

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
# The four blocks this test guards, by their opening comment (other JEG-861 blocks in v2.css belong to other parts of the ticket).
FIX = re.compile(r"\n/\* (?:JEG-861 \(phone\)|JEG-861: enlarged text|JEG-861: landscape phones|JEG-884 \(JEG-861 part A\))[^\n]*\n(?:[^\n]*\n)*?\}\n")
OVERLAP_WIDTHS = (375, 768, 1024, 1280, 1440)
SEARCH_WIDTHS = (1024, 1280, 1366)
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
OVERLAP = """() => {
  const sel = 'a[href], button, input, select, textarea, summary, [role=button], [role=tab], [tabindex]:not([tabindex="-1"])';
  const out = []; let total = 0;
  const name = e => `${e.tagName.toLowerCase()}#${e.id}.${String(e.className).slice(0, 30)} '${(e.textContent || e.placeholder || e.getAttribute('aria-label') || '').trim().slice(0, 24)}'`;
  for (const el of document.querySelectorAll(sel)) {
    if (el.closest('[hidden], [aria-hidden="true"]')) continue;
    if (el.matches('.has-math, tr, td, .v2-wf-step, .v2-wf-land')) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden' || cs.pointerEvents === 'none') continue;
    const r0 = el.getBoundingClientRect();
    if (r0.width === 0 || r0.height === 0) continue;
    el.scrollIntoView({block: 'center', inline: 'nearest'});
    const r = el.getBoundingClientRect();
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    if (cx < 0 || cy < 0 || cx > innerWidth || cy > innerHeight) continue;
    total++;
    // the centre and the four edge midpoints (2 px in): a control covered along one edge is a mis-tap too
    // Brush fills end in their own range thumbs and the chart region carries the zoom buttons: centre only for those.
    const edges = el.matches('.v2-brush-fill, .v2-ybrush-fill, .v2-chart') ? [] : [[r.left + 2, cy], [r.right - 2, cy], [cx, r.top + 2], [cx, r.bottom - 2]];
    const pts = [[cx, cy]].concat(edges);
    const own = h => !h || h === el || el.contains(h) || (h.tagName === 'LABEL' && h.contains(el));
    for (const [x, y] of pts) {
      if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) continue;
      const hit = document.elementFromPoint(x, y);
      if (own(hit)) continue;
      const other = hit.closest(sel);   // a decorative overlay is a dead spot, not a mis-tap; only another target counts
      if (!other || own(other)) continue;
      out.push(`${name(el)} is under ${name(other)} at ${Math.round(x - r.left)},${Math.round(y - r.top)}`);
      break;
    }
  }
  window.scrollTo(0, 0);
  return {overlaps: out, total};
}"""
SEARCH_HIT = """() => ['v2GiveSearch', 'v2GetSearch'].map(id => { const i = document.getElementById(id); if (!i) return `${id}: missing`;
  i.scrollIntoView({block: 'center'}); const r = i.getBoundingClientRect();
  const h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  return h === i ? null : `${id}: centre hits ${h ? h.tagName + '.' + h.className : 'nothing'}`; }).filter(Boolean)"""

# JEG-884: the suggestion list under a Compare search box is at least 240 px wide (it was 50 px) and its first row sits inside the window.
DROPDOWN = """(id) => { const u = document.getElementById(id); const b = u.querySelector('button');
  if (u.hidden || !b) return [`${id}: no suggestions after typing`];
  const r = u.getBoundingClientRect(), br = b.getBoundingClientRect(), out = [];
  if (r.width < 240) out.push(`${id}: suggestion list is ${Math.round(r.width)}px wide, want 240+`);
  if (r.right > innerWidth) out.push(`${id}: suggestion list runs off the window (${Math.round(r.right)} > ${innerWidth})`);
  if (br.height > 64) out.push(`${id}: first suggestion wraps onto ${Math.round(br.height)}px`);
  return out; }"""


def _with_linked_reviews(route):
    """JEG-1116: the Reviewed chip is a link (the tap target JEG-1048 sized) only when its entry carries a public page.
    The baked data has none today, so every chip renders as a plain span and the sweep never sees one. Serve the real
    file with every source marked reviewed and linked, so the sweep always has the link chips to measure."""
    doc = json.loads(route.fetch().text())
    doc["source_divergence"] = {key: {"status": "reviewed", "message": "Checked by hand this week.", "resolution_issue": "https://example.com/review"}
                                for key in (doc.get("source_divergence") or {"usatoday": 0, "fantasycalc": 0, "fantasypros": 0, "cbs": 0, "espn": 0})}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(doc))


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out = {"small": {}, "over": {}, "panel": None, "overlap": {}, "search": {}}

    def open_page(browser, width, height, tab, init=None, menu=False):
        page = browser.new_page(viewport={"width": width, "height": height})
        if init:
            page.add_init_script(init)
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        page.route("**/assets/reference-freshness.json*", _with_linked_reviews)
        page.goto(base + "#" + tab, wait_until="networkidle")
        page.wait_for_timeout(1000)
        if menu:
            # JEG-1048: below 768 px the tab row lives in the hamburger menu (#864). Open it so its six tabs are swept for
            # size and overlap; with it shut a Writing page has 8-9 controls and the "is the sweep looking" floor fires.
            toggle = page.locator("#v2NavToggle")
            if toggle.is_visible() and width < 768:   # JEG-1106: the button shows at every width; wider screens get a floating panel, not a bar menu
                toggle.click()
                page.wait_for_timeout(300)
        return page

    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        probe = browser.new_page()
        family = next((f for f in FAMILIES if probe.evaluate(HAS_FACE, f)), None)
        probe.close()
        for tab in TABS:
            page = open_page(browser, 375, 812, tab, menu=True)
            out["small"][tab] = page.evaluate(SMALL)
            page.close()
        for tab, opener in PANELS:
            page = open_page(browser, 375, 812, tab)
            _render_env.open_phone_context(page)  # JEG-1134: on a phone the context row opens first
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
        for width in OVERLAP_WIDTHS:
            for tab in TABS:
                page = open_page(browser, width, 812 if width < 768 else 800, tab, menu=True)
                out["overlap"][(width, tab)] = page.evaluate(OVERLAP)
                page.close()
        for width in SEARCH_WIDTHS:
            page = open_page(browser, width, 800, "compare-trade")
            out["search"][width] = page.evaluate(SEARCH_HIT)
            for field, results in (("v2GiveSearch", "v2GiveResults"), ("v2GetSearch", "v2GetResults")):
                page.focus("#" + field)
                page.keyboard.type("Breece")
                page.wait_for_timeout(400)
                out["search"][width] += page.evaluate(DROPDOWN, results)
                page.fill("#" + field, "")
            page.close()
            continue
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
    for (width, tab), r in result["overlap"].items():
        if r["total"] < 10:
            errors.append(f"{width} {tab}: only {r['total']} controls found, the overlap sweep is not looking at the page")
        if r["overlaps"]:
            errors.append(f"{width} {tab}: {len(r['overlaps'])} controls overlap another target: {r['overlaps'][:3]}")
    for width, misses in result["search"].items():
        for miss in misses:
            errors.append(f"{width} compare-trade: {miss}")
    return errors


class PhoneTapTargetsTest(unittest.TestCase):
    def test_phone_controls_fit_and_reach_44px(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertEqual(len(FIX.findall(css)), 5, "stale mutation anchor")
        errors = _errors(_run(FIX.sub("\n", css)))
        self.assertTrue(any("under 44px" in e for e in errors), f"old CSS tap targets were not caught: {errors}")
        self.assertTrue(any("scrolls sideways" in e for e in errors), f"old CSS 320 +3px overflow was not caught: {errors}")
        self.assertTrue(any("panel body" in e for e in errors), f"old CSS landscape panel was not caught: {errors}")
        self.assertTrue(any("overlap another target" in e for e in errors), f"old CSS Expand-over-search overlap was not caught: {errors}")
        self.assertTrue(any("centre hits" in e for e in errors), f"old CSS search hit test was not caught: {errors}")

    def test_guard_fails_without_jeg1048_fixes(self):
        """JEG-1048: the Reviewed chip's 44 px pseudo-element holds a check."""
        css = CSS.read_text(encoding="utf-8")
        chip = "  a.v2-div-chip::after { content: \"\"; position: absolute; left: 50%; top: 50%; width: max(100%, 44px); height: 44px; transform: translate(-50%, -50%); }\n"
        self.assertIn(chip, css, "stale mutation anchor")
        errors = _errors(_run(css.replace(chip, "")))
        self.assertTrue(any("under 44px" in e and "Reviewed" in e for e in errors), f"small Reviewed chip was not caught: {errors}")


if __name__ == "__main__":
    unittest.main()
