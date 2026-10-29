"""v2 Find a trade (JEG-995): typed search offers kickers and defenses by name as unpriced entries.

The engine prices no K or DEF (players.json is QB/RB/WR/TE only, GAP-FINDER-NO-KDEF-ROWS), so before this a defense or
kicker could only arrive from a pasted page or a league import. Jeremy (2026-10-23): typed search offers them too, added as
the same unpriced "Not evaluated" entries. Loads Find a trade headless at 1440, 390 and 320 wide and checks:

  * the page has the build-time name list: all 32 defenses, kickers each with a team, none of them in the engine's rows;
  * typing "chiefs" suggests the Kansas City Chiefs (DEF KC) and typing a kicker's surname suggests that kicker, each with a
    "Not evaluated" tag inside the suggestion; a priced player's suggestion has no tag;
  * the a11y combobox model still holds: options, aria-activedescendant on ArrowDown, Enter picks the highlighted one;
  * the pick lands on the roster as a "Not evaluated" row with no score chips, key "x:DEF:KC" / "x:K:<name>" (the key a paste
    gives a defense), cannot be added twice or to both rosters, and survives Clear then Undo, Move and Find trades;
  * Find trades with a defense and a kicker on each roster gives the same trades, groups, edges and scores as without them,
    and the engine's rows are byte-identical before and after;
  * suggestions stay inside the box's width and the page does not scroll sideways at 390 and 320.

Discrimination: test_guard_fails_on_broken_builds serves finder.js without the K/DEF choices, without the tag, with the
duplicate check dropped, and with a K/DEF entry given an engine row's key, and kdef-names.js with a defense missing; each
must fail.
"""
from __future__ import annotations

import functools
import json
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
sys_path = str(ROOT / "pipelines")


def setUpModule():
    _render_env.ensure_built()


ROWS = "(id) => [...document.querySelectorAll(`#${id} li.v2-find-row`)].map(li => ({name: li.querySelector('b').textContent, text: li.textContent, chips: li.querySelectorAll('.v2-find-chip').length}))"
OPTIONS = "() => [...document.querySelectorAll('#v2FindMineResults li > button')].map(b => ({text: b.textContent, tag: !!b.querySelector('.v2-find-noteval'), disabled: b.disabled, role: b.getAttribute('role'), id: b.id}))"
OVER = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
INSIDE = """() => {
  const wrap = document.querySelector('#v2FindMine .v2-find-search-wrap').getBoundingClientRect();
  return [...document.querySelectorAll('#v2FindMineResults li > button, #v2FindMineResults .v2-find-noteval')]
    .every(e => { const r = e.getBoundingClientRect(); return r.left >= wrap.left - 1 && r.right <= wrap.right + 1; });
}"""
ENGINE_HASH = "() => { const s = JSON.stringify(window.TradeValueCurveControls.getAllRows()); let h = 0; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0; return [s.length, h]; }"
TRADES = "() => [...document.querySelectorAll('#v2FindList li')].map(li => li.innerText)"
GROUPS = "() => document.getElementById('v2FindOut').innerText.split('\\n').filter(line => line.trim() && !/not evaluated/i.test(line)).join('\\n')"


def names(page, side):
    return page.evaluate("(id) => [...document.querySelectorAll(`#${id} li b`)].map(b => b.textContent)", f"v2Find{side}Players")


def type_in(page, side, text):
    page.fill(f"#v2Find{side}Search", text)
    page.wait_for_timeout(120)


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    page.wait_for_timeout(300)

    # 1. The build-time list.
    data = page.evaluate("() => window.TradeValueKDef || null")
    if not data or len(data.get("defenses", [])) != 32 or len(data.get("kickers", [])) < 25 or not all(k.get("team") for k in data["kickers"]):
        say(f"name list: {None if not data else (len(data.get('defenses', [])), len(data.get('kickers', [])))}")
        return errors
    priced = page.evaluate("() => new Set(window.TradeValueCurveControls.getAllRows().map(r => r.pos)).has('K') || new Set(window.TradeValueCurveControls.getAllRows().map(r => r.pos)).has('DEF')")
    if priced:
        say("the engine has K or DEF rows: the premise of the unpriced entries changed")
    kicker = data["kickers"][0]
    surname = kicker["name"].split()[-1]
    pick = page.evaluate(PICK)
    before_engine = page.evaluate(ENGINE_HASH)

    # 2. Suggestions: defense and kicker carry the tag, a priced player does not.
    type_in(page, "Mine", "chiefs")
    opts = page.evaluate(OPTIONS)
    chiefs = [o for o in opts if "Kansas City Chiefs" in o["text"]]
    if not chiefs or "DEF" not in chiefs[0]["text"] or not chiefs[0]["tag"] or "Not evaluated" not in chiefs[0]["text"]:
        say(f"'chiefs' did not suggest the Kansas City Chiefs with the Not evaluated tag: {opts}")
    type_in(page, "Mine", surname)
    opts = page.evaluate(OPTIONS)
    found = [o for o in opts if kicker["name"] in o["text"]]
    if not found or not found[0]["tag"] or " K " not in found[0]["text"]:
        say(f"{surname!r} did not suggest kicker {kicker['name']} tagged: {opts}")
    type_in(page, "Mine", pick["mine"][0])
    opts = page.evaluate(OPTIONS)
    if not opts or opts[0]["tag"] or pick["mine"][0] not in opts[0]["text"]:
        say(f"a priced player's suggestion is missing, first, or tagged: {opts[:2]}")

    # 3. Combobox model: options, activedescendant, Enter picks.
    type_in(page, "Mine", "kansas city")
    opts = page.evaluate(OPTIONS)
    if not opts or any(o["role"] != "option" for o in opts):
        say(f"suggestions are not options: {opts}")
    page.press("#v2FindMineSearch", "ArrowDown")
    active = page.evaluate("() => document.getElementById('v2FindMineSearch').getAttribute('aria-activedescendant')")
    if not active or not page.evaluate("(id) => document.getElementById(id).textContent", active).startswith("Kansas City"):
        say(f"ArrowDown did not point at the first suggestion: {active}")
    page.press("#v2FindMineSearch", "Enter")
    page.wait_for_timeout(150)
    rows = page.evaluate(ROWS, "v2FindMinePlayers")
    if len(rows) != 1 or "Kansas City Chiefs" not in rows[0]["name"] or "Not evaluated" not in rows[0]["text"] or rows[0]["chips"]:
        say(f"Enter on a defense gave {rows}")
    # 4. Not twice, not on both sides, kicker added the same way.
    type_in(page, "Mine", "chiefs")
    again = [o for o in page.evaluate(OPTIONS) if "Chiefs" in o["text"]]
    if not again or not again[0]["disabled"] or "Added" not in again[0]["text"]:
        say(f"a defense already on the roster can be added again: {again}")
    type_in(page, "Theirs", "chiefs")
    other = page.evaluate("() => [...document.querySelectorAll('#v2FindTheirsResults li > button')].map(b => ({text: b.textContent, disabled: b.disabled}))")
    if not other or not other[0]["disabled"]:
        say(f"a defense on your roster can be added to theirs: {other}")
    page.fill("#v2FindTheirsSearch", "")
    type_in(page, "Mine", surname)
    page.click(f"#v2FindMineResults button:not([disabled]) >> nth=0")
    rows = page.evaluate(ROWS, "v2FindMinePlayers")
    if [r["name"] for r in rows if "Not evaluated" in r["text"]] != ["Kansas City Chiefs", kicker["name"]]:
        say(f"after adding the kicker the unpriced rows are {[r['name'] for r in rows]}")
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow after adding")

    # 5. Clear then Undo keep them; Move carries them.
    page.click("#v2FindMineClear")
    page.wait_for_timeout(150)
    if names(page, "Mine"):
        say("Clear left rows")
    page.click("#v2FindUndo")
    page.wait_for_timeout(150)
    if names(page, "Mine") != ["Kansas City Chiefs", kicker["name"]]:
        say(f"Undo after Clear gave {names(page, 'Mine')}")
    page.click("#v2FindMineClear")
    page.wait_for_timeout(100)
    # 6. Same trades, groups, edges, scores with and without the unpriced entries.
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    # Up to 3-for-3, as test_v2_finder_render searches the same PICK rosters. Since JEG-1108 count balancing (e696bf25;
    # Jeremy 2026-10-26: the throw-in is the supplying team's least valuable bench player) these rosters have no 2-for-2
    # trade left, so the default size gave the equality check below nothing to compare.
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(700)
    trades_a, groups_a = page.evaluate(TRADES), page.evaluate(GROUPS)
    page.click("#v2FindEdit")
    for side, word in (("Mine", "chiefs"), ("Theirs", "ravens")):
        type_in(page, side, word)
        page.click(f"#v2Find{side}Results button:not([disabled]) >> nth=0")
        type_in(page, side, surname if side == "Mine" else data["kickers"][1]["name"].split()[-1])
        page.click(f"#v2Find{side}Results button:not([disabled]) >> nth=0")
    unpriced = [r["name"] for side in ("Mine", "Theirs") for r in page.evaluate(ROWS, f"v2Find{side}Players") if "Not evaluated" in r["text"]]
    if len(unpriced) != 4:
        say(f"expected two unpriced entries per side, found {unpriced}")
    page.click("#v2FindGo")
    page.wait_for_timeout(700)
    trades_b, groups_b = page.evaluate(TRADES), page.evaluate(GROUPS)
    if not trades_a:
        say("no trades found without the unpriced entries: the equality check has nothing to compare")
    if trades_a != trades_b:
        say(f"trades changed with unpriced entries on the rosters: {trades_a[:2]} vs {trades_b[:2]}")
    if groups_a != groups_b:
        differ = [(a, b) for a, b in zip(groups_a.split("\n"), groups_b.split("\n")) if a != b][:2]
        say(f"groups or scores changed with unpriced entries: {differ or (len(groups_a), len(groups_b))}")
    if page.evaluate(ENGINE_HASH) != before_engine:
        say("the engine's rows changed")
    page.click("#v2FindEdit")
    if len([r for side in ("Mine", "Theirs") for r in page.evaluate(ROWS, f"v2Find{side}Players") if "Not evaluated" in r["text"]]) != 4:
        say("Find trades dropped an unpriced entry")
    # Move to the other team.
    page.click("#v2FindMineClear")
    page.click("#v2FindUndo")
    row = page.locator("#v2FindMinePlayers li.v2-find-row", has_text="Kansas City Chiefs")
    if row.count():
        row.locator(".v2-find-move").click()
        page.wait_for_timeout(150)
        if "Kansas City Chiefs" not in names(page, "Theirs") or "Kansas City Chiefs" in names(page, "Mine"):
            say("Move did not carry the defense to the other team")

    # 7. Layout.
    type_in(page, "Mine", "new")
    if not page.evaluate(INSIDE):
        say("suggestions (or the tag) spill outside the box's width")
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow with suggestions open")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844), (320, 640))) -> list[str]:
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
            for width, height in viewports:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, body in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, "text/javascript"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


def caught(**kwargs) -> bool:
    try:
        return bool(run_checks(**kwargs))
    except unittest.SkipTest:
        raise
    except Exception:
        return True


class FinderKdefSearchRenderTest(unittest.TestCase):
    def test_typed_search_offers_kickers_and_defenses(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        import sys
        sys.path.insert(0, sys_path)
        import build_v2_page
        js = FINDER_JS.read_text(encoding="utf-8")
        names_js = build_v2_page.kdef_names_js()
        broken = {
            "finder.js": {
                "no K/DEF choices": ("getAllRows().concat(notEvaluatedChoices())", "getAllRows()"),
                "tag dropped": ("const tag = row.notEvaluated ?", "const tag = false ?"),
                "duplicate check dropped": ("const added = alreadyOnRoster(row, onRosters);", "const added = false;"),
                "entry given an engine key": ("player_key: pos === \"DEF\" ? `x:DEF:${team}` : `x:K:${normName(item.name)}`", "player_key: String(1)"),
                "entry added without the pos": ("{key, name: row.name, pos: row.pos, team: row.team} :", "{key, name: row.name, pos: \"\", team: row.team} :"),
            },
        }
        for name, (old, new) in broken["finder.js"].items():
            with self.subTest(mutation=name):
                self.assertIn(old, js, f"mutation anchor for {name!r} is stale")
                self.assertTrue(caught(overrides={"finder.js": js.replace(old, new, 1)}, viewports=((1440, 900),)), f"not caught: {name}")
        with self.subTest(mutation="defense missing from the list"):
            data = names_js.replace("Kansas City Chiefs", "Kansas City Chief", 1)
            self.assertNotEqual(data, names_js)
            self.assertTrue(caught(overrides={"kdef-names.js": data}, viewports=((1440, 900),)), "not caught: defense missing")
        with self.subTest(mutation="no kickers in the list"):
            empty = names_js.split('"kickers":')[0] + '"kickers":[]};\n'
            self.assertTrue(caught(overrides={"kdef-names.js": empty}, viewports=((1440, 900),)), "not caught: no kickers")


if __name__ == "__main__":
    unittest.main()
