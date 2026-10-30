"""JEG-1281: league entry on the default site (no ?design=fieldnotes), Find a trade: league-wide.

At 320, 390 and 1280 px, light and dark, a new visitor with empty storage sees:
  * every league paste box (a text input, textarea or select in .v2-find-import-body, and a .v2-find-paste textarea)
    with an edge at least 3:1 against the card behind it, as the finder search box has (WCAG 1.4.11, JEG-902);
  * the league card's "Your league" heading beside its ▸: the arrow's centre on the heading's line, and the heading
    starting less than 32px to the right of that centre;
  * no page errors. Requests that would leave 127.0.0.1 (the page's web-font stylesheet) are blocked.

Discrimination: test_checks_fail_without_fix serves v2.css without the JEG-1281 block and requires every paste box
and the heading check to fail at each width and theme.

Fieldnotes: with ?design=fieldnotes the league section's computed styles are the same with and without the block
(JEG-1137 owns the flagged styles).
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
BLOCK = "/* JEG-1281:"
FLAG = "?design=fieldnotes"
VIEWS = tuple((width, height, scheme) for width, height in ((320, 720), (390, 844), (1280, 900)) for scheme in ("light", "dark"))
FIELDS = {".v2-find-import-body textarea#v2LgLeaguePaste", ".v2-find-import-body input", ".v2-find-import-body select",
          ".v2-find-paste textarea"}

# No page renders a .v2-find-paste box, or a text input or select in a paste body, today; one of each is mounted
# beside the league paste box so their rules are measured on the same card, then removed.
EDGES = """() => {
  const lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const parse = s => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const over = (top, under) => ({r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const backdrop = el => { const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let out = {r: 255, g: 255, b: 255, a: 1}; for (let i = layers.length - 1; i >= 0; i--) out = over(layers[i], out); return out; };
  const box = document.getElementById('v2LgImport');
  box.insertAdjacentHTML('beforeend', '<div class="v2-find-import-body" data-probe><input type="text" aria-label="probe">'
    + '<select aria-label="probe"><option>probe</option></select></div><div class="v2-find-paste" data-probe><textarea aria-label="probe"></textarea></div>');
  const out = [];
  for (const el of document.querySelectorAll('#v2FindLeague :is(.v2-find-import-body :is(input[type="text"], textarea, select), .v2-find-paste textarea)')) {
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const cs = getComputedStyle(el), edge = parse(cs.borderTopColor);
    out.push({field: `${el.closest('.v2-find-paste') ? '.v2-find-paste' : '.v2-find-import-body'} ${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`,
      style: cs.borderTopStyle, width: parseFloat(cs.borderTopWidth), ratio: ratio(over(edge, backdrop(el.parentElement)), backdrop(el.parentElement))});
  }
  box.querySelectorAll('[data-probe]').forEach(n => n.remove());
  return out; }"""

STYLE_SNAPSHOT = """() => [...document.querySelectorAll('#v2FindLeague, #v2FindLeague *')].map(el => {
  const cs = getComputedStyle(el); return [el.tagName, el.id, String(el.className), [...cs].sort().map(p => p + ':' + cs.getPropertyValue(p)).join(';')]; })"""


def setUpModule():
    _render_env.ensure_built()


def without_fix() -> str:
    css = CSS.read_text(encoding="utf-8")
    start = css.index(BLOCK)
    return css[:start] + css[css.index("\n\n", start):]


def open_league(browser, base, width, height, scheme="light", flag="", css=None, errors=None):
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme)
    ctx.add_init_script(_render_env.pin_data_week_script())
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    if css is not None:
        page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
    page.goto(base + flag + "#find-league", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls && document.getElementById('v2LgCard')", timeout=60000)
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=20000)
    return page


def _node(node, node_id):
    if node.get("nodeId") == node_id:
        return node
    for child in node.get("children", []):
        found = _node(child, node_id)
        if found:
            return found
    return None


def _box(cdp, node_id):
    quad = cdp.send("DOM.getBoxModel", {"nodeId": node_id})["model"]["border"]
    xs, ys = quad[0::2], quad[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def heading_beside_arrow(page):
    """(gap, on_line): px from the ▸'s centre to the heading's left edge, and whether that centre is on the heading's
    line. The ▸ is the summary's ::before, so its box comes from the DevTools protocol. The open card rotates it 90
    degrees about its centre, which turns its line-tall box sideways but leaves the centre where it was."""
    cdp = page.context.new_cdp_session(page)
    try:
        root = cdp.send("DOM.getDocument", {"depth": -1})["root"]
        summary = cdp.send("DOM.querySelector", {"nodeId": root["nodeId"], "selector": "#v2LgCard > summary"})["nodeId"]
        title = cdp.send("DOM.querySelector", {"nodeId": root["nodeId"], "selector": "#v2LgTitle"})["nodeId"]
        before = next(p["nodeId"] for p in _node(root, summary).get("pseudoElements", []) if p["pseudoType"] == "before")
        arrow, heading = _box(cdp, before), _box(cdp, title)
    finally:
        cdp.detach()
    return heading[0] - (arrow[0] + arrow[2]) / 2, heading[1] <= (arrow[1] + arrow[3]) / 2 <= heading[3]


def edge_problems(edges, tag) -> list[str]:
    out = [f"{tag}: paste boxes measured {sorted(e['field'] for e in edges)}, expected {sorted(FIELDS)}"] if {e["field"] for e in edges} != FIELDS else []
    return out + [f"{tag}: {e['field']} edge is {e['style']} {e['width']}px at {e['ratio']:.2f}:1, below 3:1"
                  for e in edges if e["style"] == "none" or e["width"] < 1 or e["ratio"] < 3]


def heading_problems(gap, on_line, tag) -> list[str]:
    out = [] if on_line else [f"{tag}: the ▸ is not on the \"Your league\" heading's line"]
    return out + ([] if 0 < gap < 32 else [f"{tag}: the heading starts {gap:.0f}px from its ▸'s centre"])


class DefaultLeagueEntryTests(unittest.TestCase):
    maxDiff = None

    def test_paste_box_edges_and_card_heading(self):
        with browser_on_build() as (browser, base):
            for width, height, scheme in VIEWS:
                with self.subTest(width=width, scheme=scheme):
                    errors: list[str] = []
                    tag = f"{width}px {scheme}"
                    page = open_league(browser, base, width, height, scheme, errors=errors)
                    self.assertIsNone(page.evaluate("() => document.documentElement.dataset.design || null"))
                    errors += edge_problems(page.evaluate(EDGES), tag)
                    errors += heading_problems(*heading_beside_arrow(page), tag)
                    page.context.close()
                    self.assertEqual(errors, [])

    def test_checks_fail_without_fix(self):
        css = without_fix()
        with browser_on_build() as (browser, base):
            for width, height, scheme in VIEWS:
                with self.subTest(width=width, scheme=scheme):
                    page = open_league(browser, base, width, height, scheme, css=css)
                    edges = page.evaluate(EDGES)
                    gap, on_line = heading_beside_arrow(page)
                    page.context.close()
                    self.assertEqual({e["field"] for e in edges}, FIELDS)
                    self.assertEqual([e["field"] for e in edges if e["ratio"] >= 3], [], "a paste box passes without the fix")
                    self.assertTrue(heading_problems(gap, on_line, ""), f"heading passes without the fix: {gap:.0f}px, on line {on_line}")

    def test_fieldnotes_unchanged(self):
        with browser_on_build() as (browser, base):
            for width, height, scheme in ((1280, 900, "light"), (320, 720, "dark")):
                with self.subTest(width=width, scheme=scheme):
                    snaps = []
                    for css in (None, without_fix()):
                        page = open_league(browser, base, width, height, scheme, flag=FLAG, css=css)
                        self.assertEqual(page.evaluate("() => document.documentElement.dataset.design"), "fieldnotes")
                        snaps.append(page.evaluate(STYLE_SNAPSHOT))
                        page.context.close()
                    self.assertEqual(len(snaps[0]), len(snaps[1]))
                    self.assertEqual([a[:3] for a, b in zip(*snaps) if a != b], [], "JEG-1281 changed the Fieldnotes page")


if __name__ == "__main__":
    unittest.main()
