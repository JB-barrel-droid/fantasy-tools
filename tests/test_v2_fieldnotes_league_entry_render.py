"""JEG-1137: league entry in Fieldnotes (?design=fieldnotes), the ticket's done-when through the rendered UI.

At phone (390) and desktop (1280) widths, a new visitor with empty storage:
  * pastes a real whole-league rosters page (the Yahoo fixture) into the one paste box, and the page reports the team
    count and each team's matched players;
  * opens the folded league card by its summary and presses one team's star, which marks it as theirs;
  * reloads, and the same teams, rosters and marked team come back from this browser's storage, still in Fieldnotes.
At each step: no sideways scroll, every visible control in the league section at least 44px tall, text at least
4.5:1 (3:1 when large), the paste box's edge at least 3:1, and a keyboard focus ring of 3px that is at least 3:1.

Default page: without the flag, the league section's computed styles equal those of a build whose v2.css has the
slice 2a block removed.

Discrimination: test_guard_fails_without_slice_2a serves v2.css without the slice 2a block and requires the flagged
paste-box edge and card-heading checks to fail.
"""
from __future__ import annotations

import functools
import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
PASTE = ROOT / "tests" / "fixtures" / "league_paste" / "yahoo-league-rosters.txt"
TEAMS = ROOT / "tests" / "fixtures" / "league_paste" / "teams.json"
SLICE_2A = "/* JEG-1137 slice 2a:"
SLICE_2A_END = "/* JEG-1137 slice 2a end */"
FLAG = "?design=fieldnotes"
WIDTHS = ((390, 844), (1280, 900))
MINE = 2   # the team the visitor marks as theirs

STORE = """() => { const w = window.TradeValueWorkspace.store.get();
  return {teams: w.teams.map(t => ({name: t.name, keys: t.entries.map(e => e.key)})),
    mine: (w.teams.find(t => t.id === w.myTeamId) || {}).name || null}; }"""

PARSED = """() => { const box = document.getElementById('v2LgParsed');
  return {hidden: !box || box.hidden, head: ((box && box.querySelector('h3')) || {}).textContent || '',
    teams: box ? [...box.querySelectorAll('#v2LgParsedTeams > li')].map(li => ({name: li.dataset.team, count: Number(li.dataset.count)})) : []}; }"""

# Contrast and target-size checks on what is visible in league entry: the page title, notices and the league card, not
# the team summary or trade opportunity tables below it (their own lanes). A link inside a sentence is exempt from the
# target size (WCAG 2.5.8), a checkbox's target is its label, and visually hidden helpers (.v2-sr) are not controls.
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
  const entry = el => el.closest('#v2FindLeague') && !el.closest('#v2LgSummary, #v2LgOpps');
  const inSentence = el => { const p = el.closest('p'); return Boolean(p) && p.textContent.trim() !== el.textContent.trim(); };
  const target = el => (el.matches('input[type=checkbox], input[type=radio]')
    && (el.closest('label') || (el.id && document.querySelector(`label[for="${el.id}"]`)))) || el;
  const out = {overflow: document.documentElement.scrollWidth - window.innerWidth, small: [], text: [], edge: null};
  for (const el of document.querySelectorAll('#v2FindLeague :is(button, a[href], input, select, textarea, summary)')) {
    if (!entry(el) || !shown(el) || el.disabled || el.type === 'hidden' || inSentence(el)) continue;
    const h = target(el).getBoundingClientRect().height;
    if (h < 43.5) out.small.push(`${el.tagName.toLowerCase()}#${el.id}.${String(el.className).trim()} "${(el.textContent || '').trim().slice(0, 30)}" ${h.toFixed(1)}px`);
  }
  for (const el of document.querySelectorAll('#v2FindLeague *')) {
    if (!entry(el) || !shown(el) || ![...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) continue;
    if (el.closest('button:disabled, [aria-disabled="true"]')) continue;
    const cs = getComputedStyle(el), fg = parse(cs.color); if (!fg) continue;
    const bg = backdrop(el), size = parseFloat(cs.fontSize), weight = Number(cs.fontWeight) || 400;
    const large = size >= 24 || (size >= 18.66 && weight >= 700);
    const r = ratio(over(fg, bg), bg);
    if (r < (large ? 3 : 4.5)) out.text.push(`${el.tagName.toLowerCase()}#${el.id}.${String(el.className).trim()} "${el.textContent.trim().slice(0, 30)}" ${r.toFixed(2)}:1`);
  }
  const box = document.getElementById('v2LgLeaguePaste');
  if (box && shown(box)) { const cs = getComputedStyle(box); out.edge = ratio(parse(cs.borderTopColor), backdrop(box.parentElement)); }
  return out; }"""

HEADING = """() => { const s = document.querySelector('#v2LgCard > summary'), h = document.getElementById('v2LgTitle');
  return h.getBoundingClientRect().left - s.getBoundingClientRect().left; }"""

FOCUS = """() => { const el = document.activeElement; if (!el || !el.closest('#v2LgCard')) return null;
  const cs = getComputedStyle(el), lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4); };
  const rgb = s => (s.match(/[\\d.]+/g) || []).slice(0, 3).map(Number), lum = c => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
  let bgc = null; for (let n = el.parentElement; n && !bgc; n = n.parentElement) { const b = getComputedStyle(n).backgroundColor; if (!/rgba\\(.*, 0\\)$/.test(b) && b !== 'transparent') bgc = b; }
  const a = lum(rgb(cs.outlineColor)), b = lum(rgb(bgc || 'rgb(255,255,255)'));
  return {tag: el.tagName.toLowerCase(), id: el.id, style: cs.outlineStyle, width: parseFloat(cs.outlineWidth),
    contrast: (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)}; }"""

STYLE_SNAPSHOT = """() => [...document.querySelectorAll('#v2FindLeague, #v2FindLeague *')].map(el => {
  const cs = getComputedStyle(el); return [el.tagName, el.id, String(el.className), [...cs].sort().map(p => p + ':' + cs.getPropertyValue(p)).join(';')]; })"""


def setUpModule():
    _render_env.ensure_built()


def without_slice_2a() -> str:
    css = CSS.read_text(encoding="utf-8")
    return css[:css.index(SLICE_2A)] + css[css.index(SLICE_2A_END):]


def open_league(browser, base, width, height, flag=FLAG, css=None, context=None, errors=None):
    ctx = context or browser.new_context(viewport={"width": width, "height": height}, color_scheme="light")
    if context is None:
        ctx.add_init_script(_render_env.pin_data_week_script())
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"page error: {e}") if errors is not None else None)
    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
    if css is not None:
        page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
    page.goto(base + flag + "#find-league", wait_until="networkidle")
    wait_ready(page)
    return page


def wait_ready(page):
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && window.TradeValueCurveControls && document.getElementById('v2LgCard')", timeout=60000)
    page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=20000)


def tab_to_card(page, limit=120):
    for _ in range(limit):
        page.keyboard.press("Tab")
        focus = page.evaluate(FOCUS)
        if focus is not None:
            return focus
    return None


def a11y_problems(state, tag) -> list[str]:
    out = []
    if state["overflow"] > 0:
        out.append(f"{tag}: page scrolls sideways by {state['overflow']}px")
    out += [f"{tag}: control under 44px: {s}" for s in state["small"]]
    out += [f"{tag}: low text contrast: {s}" for s in state["text"]]
    if state["edge"] is not None and state["edge"] < 3:
        out.append(f"{tag}: paste box edge is {state['edge']:.2f}:1, below 3:1")
    return out


class FieldnotesLeagueEntryTests(unittest.TestCase):
    maxDiff = None

    def test_new_visitor_pastes_marks_team_and_returns_after_reload(self):
        text = PASTE.read_text(encoding="utf-8")
        expected = {name: len(players) for name, players in json.loads(TEAMS.read_text(encoding="utf-8")).items()}
        stored_names = [name[:40] for name in expected]   # the workspace keeps names to 40 characters (MAX_NAME)
        with browser_on_build() as (browser, base):
            for width, height in WIDTHS:
                with self.subTest(width=width):
                    errors: list[str] = []
                    page = open_league(browser, base, width, height, errors=errors)
                    tag = f"{width}px"
                    self.assertEqual(page.evaluate("() => document.documentElement.dataset.design"), "fieldnotes")
                    self.assertEqual(page.evaluate(STORE)["teams"], [], "a new visitor starts with no teams")
                    errors += a11y_problems(page.evaluate(A11Y), f"{tag} empty")
                    focus = tab_to_card(page)
                    if focus is None:
                        errors.append(f"{tag}: Tab never reaches the league card")
                    elif focus["style"] == "none" or focus["width"] < 3 or focus["contrast"] < 3:
                        errors.append(f"{tag}: focus ring on {focus['tag']}#{focus['id']} is {focus}")

                    # Paste: the page says what it read, with the real match counts.
                    page.fill("#v2LgLeaguePaste", text)
                    page.wait_for_function(f"() => window.TradeValueWorkspace.store.get().teams.length === {len(expected)}", timeout=20000)
                    page.wait_for_function("() => !document.getElementById('v2LgParsed').hidden", timeout=20000)
                    parsed = page.evaluate(PARSED)
                    if f"{len(expected)} teams" not in parsed["head"]:
                        errors.append(f"{tag}: summary does not say {len(expected)} teams: {parsed['head']!r}")
                    got = {t["name"]: t["count"] for t in parsed["teams"]}
                    if list(got) != list(expected):
                        errors.append(f"{tag}: teams read {list(got)} != {list(expected)}")
                    short = {n: (got.get(n), c) for n, c in expected.items() if not got.get(n) or got[n] < c - 2}
                    if short:
                        errors.append(f"{tag}: matched players far below the pasted rosters (got, pasted): {short}")
                    saved = [t["name"] for t in page.evaluate(STORE)["teams"]]
                    if saved != stored_names:
                        errors.append(f"{tag}: teams saved {saved} != {stored_names}")
                    errors += a11y_problems(page.evaluate(A11Y), f"{tag} pasted")

                    # Select a team the way a reader does: open the folded card by its summary, press the team's star.
                    if not page.locator("#v2LgCard").evaluate("node => node.open"):
                        page.click("#v2LgCard > summary")
                    star = page.locator("#v2LgTeams .v2-lg-star").nth(MINE)
                    star.scroll_into_view_if_needed()
                    star.click()
                    page.wait_for_function(f"() => window.TradeValueWorkspace.store.get().myTeamId === window.TradeValueWorkspace.store.get().teams[{MINE}].id", timeout=5000)
                    before = page.evaluate(STORE)
                    mine = stored_names[MINE]
                    if before["mine"] != mine or star.get_attribute("aria-pressed") != "true":
                        errors.append(f"{tag}: pressing the star did not mark {mine!r}: {before['mine']!r}")
                    errors += a11y_problems(page.evaluate(A11Y), f"{tag} marked")

                    # Return after reload: same teams, rosters and team, still in Fieldnotes.
                    page.reload(wait_until="networkidle")
                    wait_ready(page)
                    after = page.evaluate(STORE)
                    if after != before:
                        errors.append(f"{tag}: reload lost the league: {after['mine']!r}, {len(after['teams'])} teams")
                    if page.evaluate("() => document.documentElement.dataset.design") != "fieldnotes":
                        errors.append(f"{tag}: reload dropped the Fieldnotes flag")
                    if not page.locator("#v2LgCard").evaluate("node => node.open"):
                        page.click("#v2LgCard > summary")
                    if page.locator("#v2LgTeams .v2-lg-star").nth(MINE).get_attribute("aria-pressed") != "true":
                        errors.append(f"{tag}: after reload the star does not show {mine!r} as yours")
                    errors += a11y_problems(page.evaluate(A11Y), f"{tag} reloaded")
                    page.context.close()
                    self.assertEqual(errors, [])

    def test_default_page_unchanged(self):
        with browser_on_build() as (browser, base):
            snaps = []
            for css in (None, without_slice_2a()):
                page = open_league(browser, base, 1280, 900, flag="", css=css)
                self.assertIsNone(page.evaluate("() => document.documentElement.dataset.design || null"))
                snaps.append(page.evaluate(STYLE_SNAPSHOT))
                page.context.close()
            self.assertEqual(len(snaps[0]), len(snaps[1]))
            changed = [a[:3] for a, b in zip(*snaps) if a != b]
            self.assertEqual(changed, [], "slice 2a changed the unflagged page")

    def test_guard_fails_without_slice_2a(self):
        with browser_on_build() as (browser, base):
            for css, should_pass in ((None, True), (without_slice_2a(), False)):
                page = open_league(browser, base, 1280, 900, css=css)
                edge = page.evaluate(A11Y)["edge"]
                heading = page.evaluate(HEADING)
                page.context.close()
                with self.subTest(slice_2a=should_pass):
                    self.assertEqual(edge >= 3, should_pass, f"paste box edge {edge:.2f}:1")
                    self.assertEqual(heading < 64, should_pass, f"card heading sits {heading:.0f}px from its summary's start")


if __name__ == "__main__":
    unittest.main()
