"""JEG-1138: Compare a trade in Fieldnotes (?design=fieldnotes), the ticket's done-when through the rendered UI.

At phone (390) and desktop (1280) widths, for every verdict branch (none, win, lose, even, incomplete), each opened as a
shared trade link:
  * the numbers and words are the existing ones: #v2Compare's text equals the unflagged page's for the same trade;
  * the verdict is the Fieldnotes answer: Fraunces on its heading, and a left edge that keeps its meaning (win action,
    lose negative, incomplete warning, none and even ink);
  * no sideways scroll, every visible control in Compare at least 44px tall, and text at least 4.5:1 (3:1 when large);
  * every element the page hides (the hidden attribute) stays hidden as it does without the flag, so "Copy link to
    this trade" can't be copied or focused while the trade is empty or one-sided;
  * by keyboard: Tab reaches "Every pairing" with a 3px focus ring at least 3:1, Enter opens and closes it, Enter on a
    row's "Show players" opens that row's arithmetic and keeps focus on the toggle, and Enter on "Copy link to this
    trade" puts the trade's link on the clipboard; on a phone the verdict bar shows for a linked trade.

Default page: without the flag, Compare's computed styles equal those of a build whose v2.css has the JEG-1138 block
removed. Discrimination: test_guard_fails_without_block serves v2.css without the block and requires the flagged
heading, toggle and share-link checks to fail.

The incomplete branch hides one player's DDF Value the way the engine reports a missing value (tests/
test_v2_compare_render.py, JEG-541), since every chart prices every player in the fixture.
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
START = "/* JEG-1138: Compare a trade in Fieldnotes"
END = "/* JEG-1138 end */"
FLAG = "?design=fieldnotes"
WIDTHS = ((390, 844), (1280, 900))
SERIES = "ddf_value"

# Priced, full-confidence players: win and lose swap the same two sides; even is two players whose DDF Values are
# within the 0.05 that trade.js reads as 0.0; incomplete gives the player whose DDF Value is hidden below.
PICK = """(series) => {
  const rows = window.TradeValueCurveControls.getAllRows()
    .filter(r => Number.isFinite(r.values[series]) && r.values[series] > 5 && !r.ddfLowConfidence)
    .sort((a, b) => b.values[series] - a.values[series]);
  const key = r => String(r.player_key);
  const high = rows[2], low = rows[12];
  let even = null;
  for (let i = 1; i < rows.length && !even; i++) {
    if (Math.abs(rows[i].values[series] - rows[i - 1].values[series]) < 0.04) even = [key(rows[i - 1]), key(rows[i])];
  }
  return {high: key(high), low: key(low), even, missing: key(rows[20])};
}"""

HIDE = """([key, series]) => {
  const C = window.TradeValueCurveControls;
  const patch = r => (!r || String(r.player_key) !== key) ? r
    : {...r, values: {...r.values, [series]: null}, estimated: Object.fromEntries(Object.entries(r.estimated || {}).filter(([k]) => k !== series)),
       missingReasons: {...(r.missingReasons || {}), [series]: 'Simulated in test: no value in this series'}};
  for (const name of ['getAllRows', 'getRows']) { const original = C[name].bind(C); C[name] = (...args) => original(...args).map(patch); }
  if (C.getPlayer) { const original = C.getPlayer.bind(C); C.getPlayer = (...args) => patch(original(...args)); }
}"""

READ = """() => { const card = document.getElementById('v2CVerdict'), h = document.getElementById('v2CVerdictTitle');
  const cs = getComputedStyle(card), hs = getComputedStyle(h);
  return {kind: card.dataset.verdict || 'none', text: document.getElementById('v2Compare').textContent.replace(/\\s+/g, ' ').trim(),
    font: hs.fontFamily, edge: cs.borderLeftColor,
    tokens: Object.fromEntries(['--ddf-action', '--ddf-bad-ink', '--ddf-warn-ink', '--ddf-ink', '--v2-older', '--v2-action', '--v2-negative']
      .map(n => [n, getComputedStyle(document.documentElement).getPropertyValue(n).trim()]))}; }"""

# The same checks as the JEG-1137 league-entry test, on Compare. A link inside a sentence is exempt from the target
# size (WCAG 2.5.8) and visually hidden helpers (.v2-sr) are not controls.
A11Y = """() => {
  const lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const parse = s => { const m = s.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1}; };
  const over = (top, under) => ({r: top.r * top.a + under.r * (1 - top.a), g: top.g * top.a + under.g * (1 - top.a), b: top.b * top.a + under.b * (1 - top.a), a: 1});
  const lum = c => 0.2126 * lin(c.r) + 0.7152 * lin(c.g) + 0.0722 * lin(c.b);
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const backdrop = el => { const layers = [];
    for (let n = el; n; n = n.parentElement) { const c = parse(getComputedStyle(n).backgroundColor); if (c && c.a > 0) { layers.push(c); if (c.a >= 1) break; } }
    let out = {r: 255, g: 255, b: 255, a: 1}; for (let i = layers.length - 1; i >= 0; i--) out = over(layers[i], out); return out; };
  const shown = el => { const r = el.getBoundingClientRect(); if (!r.width || !r.height) return false;
    for (let n = el; n; n = n.parentElement) { const cs = getComputedStyle(n); if (cs.visibility === 'hidden' || cs.display === 'none') return false;
      if (n.classList && n.classList.contains('v2-sr')) return false; }
    return true; };
  const inSentence = el => { const p = el.closest('p'); return Boolean(p) && p.textContent.trim() !== el.textContent.trim(); };
  const out = {overflow: document.documentElement.scrollWidth - window.innerWidth, small: [], text: []};
  for (const el of document.querySelectorAll('#v2Compare :is(button, a[href], input, select, textarea, summary)')) {
    if (!shown(el) || el.disabled || el.type === 'hidden' || inSentence(el)) continue;
    const h = el.getBoundingClientRect().height;
    if (h < 43.5) out.small.push(`${el.tagName.toLowerCase()}#${el.id}.${String(el.className).trim()} "${(el.textContent || '').trim().slice(0, 30)}" ${h.toFixed(1)}px`);
  }
  for (const el of document.querySelectorAll('#v2Compare *')) {
    if (!shown(el) || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    if (el.closest('button:disabled, [aria-disabled="true"]')) continue;
    const cs = getComputedStyle(el), fg = parse(cs.color); if (!fg) continue;
    const bg = backdrop(el), size = parseFloat(cs.fontSize), weight = Number(cs.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const r = ratio(over(fg, bg), bg);
    if (r < (large ? 3 : 4.5)) out.text.push(`${el.tagName.toLowerCase()}#${el.id}.${String(el.className).trim()} "${el.textContent.trim().slice(0, 30)}" ${r.toFixed(2)}:1`);
  }
  return out; }"""

FOCUS = """() => { const el = document.activeElement; if (!el) return null;
  const cs = getComputedStyle(el), lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const rgb = s => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number), lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  let bgc = null; for (let n = el.parentElement; n && !bgc; n = n.parentElement) { const b = getComputedStyle(n).backgroundColor; if (!/rgba\\(.*, 0\\)$/.test(b) && b !== 'transparent') bgc = b; }
  const a = lum(rgb(cs.outlineColor)), b = lum(rgb(bgc || 'rgb(255,255,255)'));
  return {tag: el.tagName.toLowerCase(), id: el.id, cls: String(el.className), text: (el.textContent || '').trim().slice(0, 40),
    style: cs.outlineStyle, width: parseFloat(cs.outlineWidth), contrast: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)}; }"""

# Elements v2.js hides with the hidden attribute that a Fieldnotes display rule would show again.
SHOWN_HIDDEN = """() => [...document.querySelectorAll('#v2Compare [hidden]')]
  .filter(el => getComputedStyle(el).display !== 'none' && !(el.parentElement && el.parentElement.closest('[hidden]')))
  .map(el => `${el.tagName.toLowerCase()}#${el.id}.${String(el.className).trim()}`)"""

STYLE_SNAPSHOT = """() => [...document.querySelectorAll('#v2Compare, #v2Compare *')].map(el => {
  const cs = getComputedStyle(el); return [el.tagName, el.id, String(el.className), [...cs].sort().map(p => p + ':' + cs.getPropertyValue(p)).join(';')]; })"""


def setUpModule():
    _render_env.ensure_built()


def without_block() -> str:
    css = CSS.read_text(encoding="utf-8")
    start, end = css.index(START), css.index(END) + len(END)
    return css[:start] + css[end:]


def open_compare(browser, base, width, height, flag=FLAG, css=None, errors=None):
    ctx = browser.new_context(viewport={"width": width, "height": height}, color_scheme="light")
    ctx.add_init_script(_render_env.pin_data_week_script())
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=base.split("/v2")[0])
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    if css is not None:
        page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
    page.goto(base + flag + "#compare-trade", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.compare() && window.TradeValueCurveControls", timeout=60000)
    page.emulate_media(reduced_motion="reduce")
    return page


def branches(pick) -> list[tuple[str, list[str], list[str]]]:
    return [("none", [], []),
            ("win", [pick["low"]], [pick["high"]]),
            ("lose", [pick["high"]], [pick["low"]]),
            ("even", [pick["even"][0]], [pick["even"][1]]),
            ("incomplete", [pick["missing"]], [pick["high"]])]


def load(page, give, get, kind):
    link = "#compare-trade?give=" + ",".join(give) + "&get=" + ",".join(get) if give or get else "#compare-trade"
    if not give and not get:
        page.evaluate("() => { const b = document.getElementById('v2CClear'); if (b && !b.hidden) b.click(); }")
    page.evaluate("link => { location.hash = link; }", link)
    page.wait_for_function("kind => (document.getElementById('v2CVerdict').dataset.verdict || 'none') === kind", arg=kind, timeout=20000)
    page.wait_for_timeout(150)


def expected_edge(kind) -> str:
    return {"win": "--v2-action", "lose": "--v2-negative", "incomplete": "--v2-older"}.get(kind, "--ddf-ink")


def hex_rgb(value: str) -> str:
    value = value.lstrip("#")
    return "rgb({}, {}, {})".format(*(int(value[i:i + 2], 16) for i in (0, 2, 4)))


def tab_to(page, selector, limit=300):
    page.evaluate("() => { document.activeElement && document.activeElement.blur(); window.scrollTo(0, 0); }")
    for _ in range(limit):
        page.keyboard.press("Tab")
        if page.evaluate("sel => Boolean(document.activeElement && document.activeElement.matches(sel))", selector):
            return page.evaluate(FOCUS)
    return None


class FieldnotesCompareTests(unittest.TestCase):
    maxDiff = None

    def test_every_verdict_branch_and_disclosure(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                with self.subTest(width=width):
                    errors: list[str] = []
                    page = open_compare(browser, base, width, height, errors=errors)
                    plain = open_compare(browser, base, width, height, flag="", errors=errors)
                    self.assertEqual(page.evaluate("() => document.documentElement.dataset.design"), "fieldnotes")
                    pick = page.evaluate(PICK, SERIES)
                    self.assertTrue(pick["even"], "the fixture has no two players with the same DDF Value")
                    for p in (page, plain):
                        p.evaluate(HIDE, [pick["missing"], SERIES])
                    for kind, give, get in branches(pick):
                        tag = f"{width}px {kind}"
                        load(page, give, get, kind)
                        load(plain, give, get, kind)
                        got, want = page.evaluate(READ), plain.evaluate(READ)
                        if got["text"] != want["text"]:
                            errors.append(f"{tag}: Compare's text differs from the unflagged page")
                        if "Fraunces" not in got["font"]:
                            errors.append(f"{tag}: verdict heading is {got['font']!r}, not the display face")
                        edge = got["tokens"][expected_edge(kind)]
                        if got["edge"] != hex_rgb(edge):
                            errors.append(f"{tag}: verdict edge {got['edge']} != {expected_edge(kind)} {edge}")
                        state = page.evaluate(A11Y)
                        if state["overflow"] > 0:
                            errors.append(f"{tag}: page scrolls sideways by {state['overflow']}px")
                        errors += [f"{tag}: control under 44px: {s}" for s in state["small"]]
                        errors += [f"{tag}: low text contrast: {s}" for s in state["text"]]
                        plain_shown = set(plain.evaluate(SHOWN_HIDDEN))
                        errors += [f"{tag}: hidden by the page but shown under the flag: {s}"
                                   for s in page.evaluate(SHOWN_HIDDEN) if s not in plain_shown]

                    # Keyboard, on the win trade: the pairing disclosure, a row's arithmetic and sharing.
                    kind, give, get = branches(pick)[1]
                    load(page, give, get, kind)
                    tag = f"{width}px keyboard"
                    focus = tab_to(page, "#v2CDeal .v2-deal-more > summary")
                    if focus is None:
                        errors.append(f"{tag}: Tab never reaches 'Every pairing'")
                    else:
                        if focus["style"] == "none" or focus["width"] < 3 or focus["contrast"] < 3:
                            errors.append(f"{tag}: focus ring on 'Every pairing' is {focus}")
                        opened = []
                        for _ in range(2):
                            page.keyboard.press("Enter")
                            opened.append(page.evaluate("() => document.querySelector('#v2CDeal .v2-deal-more').open"))
                        if opened != [True, False]:
                            errors.append(f"{tag}: Enter on 'Every pairing' gave open states {opened}, not [True, False]")
                    focus = tab_to(page, "#v2CTable .v2-cexpand")
                    if focus is None:
                        errors.append(f"{tag}: Tab never reaches a row's 'Show players'")
                    else:
                        page.keyboard.press("Enter")
                        page.wait_for_timeout(150)
                        after = page.evaluate("""() => ({rows: document.querySelectorAll('#v2CTable tr.v2-cbreak').length,
                          focused: Boolean(document.activeElement && document.activeElement.matches('#v2CTable .v2-cexpand'))})""")
                        if not after["rows"] or not after["focused"]:
                            errors.append(f"{tag}: Enter on 'Show players' gave {after}")
                    share = "#v2CShare"
                    focus = tab_to(page, share)
                    if focus is None:
                        errors.append(f"{tag}: Tab never reaches {share}")
                    else:
                        page.keyboard.press("Enter")
                        page.wait_for_function("() => !document.getElementById('v2CShareNote').hidden", timeout=5000)
                        clip = page.evaluate("() => navigator.clipboard.readText().catch(() => '')")
                        if "give=" not in clip or "get=" not in clip:
                            errors.append(f"{tag}: Copy link put {clip[:80]!r} on the clipboard")
                    if width < 768:
                        # The bar shows once the verdict card is scrolled away.
                        page.evaluate("() => document.getElementById('v2CConstruction').scrollIntoView()")
                        page.wait_for_timeout(300)
                        bar = page.evaluate("""() => { const w = document.getElementById('v2CVerdictBarWrap'), b = document.getElementById('v2CVerdictBar');
                          return {hidden: w.hidden || getComputedStyle(w).display === 'none', height: b.getBoundingClientRect().height,
                            edge: getComputedStyle(w).borderLeftColor, verdict: w.dataset.verdict}; }""")
                        if bar["hidden"] or bar["height"] < 43.5 or bar["edge"] != hex_rgb(page.evaluate(READ)["tokens"]["--v2-action"]):
                            errors.append(f"{tag}: phone verdict bar on a linked win trade is {bar}")
                    errors += a11y_problems_only(page, tag)
                    page.context.close()
                    plain.context.close()
                    self.assertEqual(errors, [])

    def test_default_page_unchanged(self):
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                snaps = []
                for css in (None, without_block()):
                    page = open_compare(browser, base, width, height, flag="", css=css)
                    pick = page.evaluate(PICK, SERIES)
                    kind, give, get = branches(pick)[1]
                    load(page, give, get, kind)
                    self.assertIsNone(page.evaluate("() => document.documentElement.dataset.design || null"))
                    snaps.append(page.evaluate(STYLE_SNAPSHOT))
                    page.context.close()
                self.assertEqual(len(snaps[0]), len(snaps[1]))
                changed = [a[:3] for a, b in zip(*snaps) if a != b]
                self.assertEqual(changed, [], f"the JEG-1138 block changed the unflagged page at {width}px")

    def test_guard_fails_without_block(self):
        with browser_on_build() as (browser, base):
            for css, should_pass in ((None, True), (without_block(), False)):
                page = open_compare(browser, base, 1280, 900, css=css)
                pick = page.evaluate(PICK, SERIES)
                kind, give, get = branches(pick)[1]
                load(page, give, get, kind)
                font = page.evaluate(READ)["font"]
                small = page.evaluate(A11Y)["small"]
                page.context.close()
                with self.subTest(block=should_pass):
                    self.assertEqual("Fraunces" in font, should_pass, font)
                    self.assertEqual(not any("v2CShare" in s for s in small), should_pass, small)
                    self.assertEqual(not any("v2-cexpand" in s for s in small), should_pass, small)


def a11y_problems_only(page, tag) -> list[str]:
    state = page.evaluate(A11Y)
    return ([f"{tag}: page scrolls sideways by {state['overflow']}px"] if state["overflow"] > 0 else []) \
        + [f"{tag}: control under 44px: {s}" for s in state["small"]]


if __name__ == "__main__":
    unittest.main()
