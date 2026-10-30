"""JEG-1137 slice 2b: Fieldnotes navigation, Home and the phone league entry (?design=fieldnotes), through the rendered UI.

With the flag, at phone (390) and desktop (1280) widths:
  * the landing page (no hash) is Home, and the primary navigation shows five destinations (Home, Values, Buy & sell,
    Check a trade, More), with the one on show marked; on a phone it is a bar fixed at the foot of the screen;
  * Values, Buy & sell and Check a trade open their pages and keep the flag;
  * More opens the full page list (above the bar on a phone, not under it), and Escape closes it and returns focus to More;
  * on a phone, league entry first says "Set up your league on desktop." and the paste box follows; on desktop it does not;
  * every primary control is at least 44px tall, text on Home and in the bar is at least 4.5:1 (3:1 when large), the
    keyboard focus ring on the bar is 3px and at least 3:1, and nothing scrolls sideways.

Default page: without the flag #home is an unknown route (it lands on the value chart), the bar and the phone entry
never show, and the nav's and league entry's computed styles equal those of a build whose v2.css has the slice 2b block
removed.

Discrimination: test_guard_fails_without_slice_2b serves v2.css without the slice 2b block and requires the phone bar
and menu-button checks to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
SLICE_2B = "/* JEG-1137 slice 2b:"
SLICE_2B_END = "/* JEG-1137 slice 2b end */"
FLAG = "?design=fieldnotes"
WIDTHS = ((390, 844), (1280, 900))
PRIMARY = ["Home", "Values", "Buy & sell", "Check a trade", "More"]

NAV = """() => { const bar = document.getElementById('v2FnPrimary'), r = bar.getBoundingClientRect(), cs = getComputedStyle(bar);
  const items = [...bar.children].map(el => { const b = el.getBoundingClientRect();
    return {text: el.textContent.trim(), current: el.getAttribute('aria-current'), height: b.height, top: b.top}; });
  const toggle = document.getElementById('v2NavToggle');
  return {shown: !bar.hidden && cs.display !== 'none' && r.height > 0, position: cs.position, bottom: r.bottom, top: r.top,
    innerHeight: window.innerHeight, items, toggleShown: getComputedStyle(toggle).display !== 'none',
    overflow: document.documentElement.scrollWidth - window.innerWidth, hash: location.hash,
    design: document.documentElement.dataset.design || null,
    view: ['v2Home', 'v2Main', 'v2Targets', 'v2Compare', 'v2FindLeague'].filter(id => !document.getElementById(id).hidden)}; }"""

# Text contrast on Home and in the primary bar (same method as the slice 2a league-entry test).
CONTRAST = """(scope) => {
  const lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const parse = s => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const over = (top, under) => ({r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const backdrop = el => { const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let out = {r: 255, g: 255, b: 255, a: 1}; for (let i = layers.length - 1; i >= 0; i--) out = over(layers[i], out); return out; };
  const out = [];
  for (const el of document.querySelectorAll(scope)) {
    const r = el.getBoundingClientRect(); if (!r.width || !r.height) continue;
    if (![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    const cs = getComputedStyle(el), fg = parse(cs.color); if (!fg) continue;
    const bg = backdrop(el), size = parseFloat(cs.fontSize), weight = Number(cs.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const k = ratio(over(fg, bg), bg);
    if (k < (large ? 3 : 4.5)) out.push(`${el.tagName.toLowerCase()} "${el.textContent.trim().slice(0, 30)}" ${k.toFixed(2)}:1`);
  }
  return out; }"""

TARGETS = """(scope) => [...document.querySelectorAll(scope)].filter(el => { const r = el.getBoundingClientRect(); return r.width && r.height; })
  .filter(el => el.getBoundingClientRect().height < 43.5).map(el => `${el.textContent.trim().slice(0, 30)} ${el.getBoundingClientRect().height.toFixed(1)}px`)"""

FOCUS = """() => { const el = document.activeElement; if (!el || !el.closest('#v2FnPrimary')) return null;
  const cs = getComputedStyle(el), lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const rgb = s => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number), lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  let bgc = null; for (let n = el.parentElement; n && !bgc; n = n.parentElement) { const b = getComputedStyle(n).backgroundColor; if (!/rgba\\(.*, 0\\)$/.test(b) && b !== 'transparent') bgc = b; }
  const a = lum(rgb(cs.outlineColor)), b = lum(rgb(bgc || 'rgb(255,255,255)'));
  return {text: el.textContent.trim(), style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), contrast: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)}; }"""

MENU = """() => { const tabs = document.getElementById('v2Tabs'), r = tabs.getBoundingClientRect(), bar = document.getElementById('v2FnPrimary').getBoundingClientRect();
  return {open: getComputedStyle(tabs).display !== 'none' && r.height > 0, bottom: r.bottom, barTop: bar.top,
    expanded: document.getElementById('v2FnMore').getAttribute('aria-expanded'),
    focusInMenu: Boolean(document.activeElement && document.activeElement.closest('#v2Tabs')),
    focus: document.activeElement && document.activeElement.id}; }"""

ENTRY = """() => { const box = document.getElementById('v2LgPhoneEntry'), card = document.getElementById('v2LgCard');
  if (!box) return {present: false};
  return {present: true, shown: getComputedStyle(box).display !== 'none' && box.getBoundingClientRect().height > 0,
    title: (box.querySelector('h2') || {}).textContent || '', before: Boolean(box.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING),
    paste: Boolean(document.getElementById('v2LgLeaguePaste'))}; }"""

STYLE_SNAPSHOT = """() => [...document.querySelectorAll('.v2-nav, .v2-nav *, #v2FindLeague, #v2FindLeague *')].map(el => {
  const cs = getComputedStyle(el); return [el.tagName, el.id, String(el.className), [...cs].sort().map(p => p + ':' + cs.getPropertyValue(p)).join(';')]; })"""


def setUpModule():
    _render_env.ensure_built()


def without_slice_2b() -> str:
    css = CSS.read_text(encoding="utf-8")
    return css[:css.index(SLICE_2B)] + css[css.index(SLICE_2B_END) + len(SLICE_2B_END):]


def open_page(browser, base, width, height, flag=FLAG, hash_="", css=None, errors=None):
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light")
    ctx.add_init_script(_render_env.pin_data_week_script())
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    if css is not None:
        page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
    page.goto(base + flag + hash_, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2LgCard')", timeout=60000)
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=20000)
    return page


def tab_to_bar(page, limit=60):
    for _ in range(limit):
        page.keyboard.press("Tab")
        focus = page.evaluate(FOCUS)
        if focus is not None:
            return focus
    return None


class FieldnotesNavTests(unittest.TestCase):
    maxDiff = None

    def test_home_primary_nav_more_and_phone_entry(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                phone = width < 768
                with self.subTest(width=width):
                    errors: list[str] = []
                    tag = f"{width}px"
                    page = open_page(browser, base, width, height, errors=errors)

                    # Landing: Home, with the five destinations and Home marked.
                    nav = page.evaluate(NAV)
                    if nav["design"] != "fieldnotes":
                        errors.append(f"{tag}: flag not set")
                    if nav["view"] != ["v2Home"]:
                        errors.append(f"{tag}: landing shows {nav['view']}, not Home")
                    if not page.locator("#v2HomeTitle").is_visible() or "Understand the data." not in page.inner_text("#v2HomeTitle"):
                        errors.append(f"{tag}: Home headline missing")
                    if not nav["shown"]:
                        errors.append(f"{tag}: primary navigation not shown")
                    if [i["text"] for i in nav["items"]] != PRIMARY:
                        errors.append(f"{tag}: primary items {[i['text'] for i in nav['items']]}")
                    if [i["text"] for i in nav["items"] if i["current"] == "page"] != ["Home"]:
                        errors.append(f"{tag}: Home is not the marked destination")
                    if nav["toggleShown"]:
                        errors.append(f"{tag}: the old menu button still shows beside More")
                    if phone and (nav["position"] != "fixed" or abs(nav["bottom"] - nav["innerHeight"]) > 1
                                  or len({round(i["top"]) for i in nav["items"]}) != 1):
                        errors.append(f"{tag}: phone bar is not one row fixed at the foot: {nav['position']} bottom {nav['bottom']} of {nav['innerHeight']}")
                    if nav["overflow"] > 0:
                        errors.append(f"{tag}: Home scrolls sideways by {nav['overflow']}px")
                    errors += [f"{tag}: control under 44px: {s}" for s in page.evaluate(TARGETS, "#v2FnPrimary > *, #v2Home .v2-btn")]
                    errors += [f"{tag}: low contrast: {s}" for s in page.evaluate(CONTRAST, "#v2Home *, #v2FnPrimary *")]

                    focus = tab_to_bar(page)
                    if focus is None:
                        errors.append(f"{tag}: Tab never reaches the primary bar")
                    elif focus["style"] == "none" or focus["width"] < 3 or focus["contrast"] < 3:
                        errors.append(f"{tag}: focus ring on {focus['text']!r} is {focus}")

                    # Each destination opens its page and keeps the flag.
                    for label, hash_, view in (("Values", "#player-values", "v2Main"), ("Buy & sell", "#trade-targets", "v2Targets"),
                                               ("Check a trade", "#compare-trade", "v2Compare"), ("Home", "#home", "v2Home")):
                        page.locator("#v2FnPrimary > a", has_text=label).click()
                        page.wait_for_function(f"() => location.hash === '{hash_}' && !document.getElementById('{view}').hidden", timeout=10000)
                        nav = page.evaluate(NAV)
                        marked = [i["text"] for i in nav["items"] if i["current"] == "page"]
                        if nav["view"] != [view] or marked != [label] or nav["design"] != "fieldnotes":
                            errors.append(f"{tag}: {label} shows {nav['view']}, marks {marked}, flag {nav['design']}")
                        if nav["overflow"] > 0:
                            errors.append(f"{tag}: {label} scrolls sideways by {nav['overflow']}px")

                    # More opens the full list; Escape closes it and focus returns to More.
                    page.click("#v2FnMore")
                    menu = page.evaluate(MENU)
                    if not menu["open"] or menu["expanded"] != "true" or not menu["focusInMenu"]:
                        errors.append(f"{tag}: More did not open the page list: {menu}")
                    if phone and menu["bottom"] > menu["barTop"] + 1:
                        errors.append(f"{tag}: the page list runs under the bar ({menu['bottom']} > {menu['barTop']})")
                    page.keyboard.press("Escape")
                    menu = page.evaluate(MENU)
                    if menu["open"] or menu["expanded"] != "false" or menu["focus"] != "v2FnMore":
                        errors.append(f"{tag}: Escape left the list open or focus off More: {menu}")

                    # League entry: on a phone, set up on desktop first, then the paste box.
                    page.evaluate("() => { location.hash = '#find-league'; }")
                    page.wait_for_function("() => !document.getElementById('v2FindLeague').hidden", timeout=10000)
                    entry = page.evaluate(ENTRY)
                    if not entry["present"] or entry["shown"] != phone or not entry["paste"]:
                        errors.append(f"{tag}: phone entry shown={entry.get('shown')} (want {phone}), paste box {entry.get('paste')}")
                    if phone and (entry["title"] != "Set up your league on desktop." or not entry["before"]):
                        errors.append(f"{tag}: phone entry {entry}")
                    if phone:
                        errors += [f"{tag}: low contrast: {s}" for s in page.evaluate(CONTRAST, "#v2LgPhoneEntry *")]
                        errors += [f"{tag}: control under 44px: {s}" for s in page.evaluate(TARGETS, "#v2LgPhoneEntry a")]
                    page.context.close()
                    self.assertEqual(errors, [])

    def test_default_page_unchanged(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                with self.subTest(width=width):
                    page = open_page(browser, base, width, height, flag="", hash_="#home")
                    nav = page.evaluate(NAV)
                    self.assertIsNone(nav["design"])
                    self.assertEqual(nav["hash"], "#player-values", "#home must be an unknown route without the flag")
                    self.assertEqual(nav["view"], ["v2Main"])
                    self.assertFalse(nav["shown"])
                    self.assertTrue(nav["toggleShown"])
                    page.evaluate("() => { location.hash = '#find-league'; }")
                    page.wait_for_function("() => !document.getElementById('v2FindLeague').hidden", timeout=10000)
                    self.assertFalse(page.evaluate(ENTRY)["present"])
                    page.context.close()
            snaps = []
            for css in (None, without_slice_2b()):
                page = open_page(browser, base, 390, 844, flag="", hash_="#find-league", css=css)
                snaps.append(page.evaluate(STYLE_SNAPSHOT))
                page.context.close()
            self.assertEqual(len(snaps[0]), len(snaps[1]))
            changed = [a[:3] for a, b in zip(*snaps) if a != b]
            self.assertEqual(changed, [], "slice 2b changed the unflagged page")

    def test_guard_fails_without_slice_2b(self):
        with browser_on_build() as (browser, base):
            for css, should_pass in ((None, True), (without_slice_2b(), False)):
                page = open_page(browser, base, 390, 844, css=css)
                nav = page.evaluate(NAV)
                page.context.close()
                with self.subTest(slice_2b=should_pass):
                    self.assertEqual(nav["position"] == "fixed" and abs(nav["bottom"] - nav["innerHeight"]) <= 1, should_pass, nav)
                    self.assertEqual(not nav["toggleShown"], should_pass, "menu button")


if __name__ == "__main__":
    unittest.main()
