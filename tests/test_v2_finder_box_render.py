"""v2 Find a trade v2 (JEG-988), commit 1: one box per side, rendered.

Loads Find a trade headless (1440x900 and 390 wide) and checks:

  * exactly one add-players box per side; typing a name shows the suggestions directly under that box (not under the
    whole side card), also when the roster already has a dozen players; short text is a search and adds nothing;
  * a whole team page (multi-line, or over 120 characters) typed or pasted into the same box is read by the page parser
    and the box clears; a plain list of names, one per line, is added by name;
  * Clear is hidden on an empty side, clears only its own side with no confirm dialog, hands focus back to the box, and
    Undo restores the roster;
  * a defense and a kicker in a pasted page stay on the roster (the engine has no row for either) (also after Find trades), are marked "Not evaluated", and the
    results say so; no player row of another position carries the mark;
  * no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves the page with the suggestion wrapper unpositioned, a pasted
page treated as a search, Clear not recording Undo, and the "Not evaluated" mark dropped, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add
from tests.test_v2_modules_render import _serve

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
FIXTURE = ROOT / "tests" / "fixtures" / "roster_paste" / "yahoo-team.txt"


def setUpModule():
    _render_env.ensure_built()


NAMES = "(id) => [...document.querySelectorAll(`#${id} li b`)].map(b => b.textContent)"
ROWS = "(id) => [...document.querySelectorAll(`#${id} li.v2-find-row`)].map(li => ({name: li.querySelector('b').textContent, text: li.textContent}))"
OVER = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
GAP = """(side) => {
  const box = document.getElementById(`v2Find${side}Search`).getBoundingClientRect();
  const list = document.getElementById(`v2Find${side}Results`);
  const wrap = box && document.querySelector(`#v2Find${side} .v2-find-search-wrap`).getBoundingClientRect();
  const l = list.getBoundingClientRect();
  return {hidden: list.hidden, gap: l.top - box.bottom, inWrap: l.left >= wrap.left - 1 && l.right <= wrap.right + 1, count: list.querySelectorAll('button').length};
}"""


def names(page, side):
    return page.evaluate(NAMES, f"v2Find{side}Players")


def check(page, tag, width) -> list[str]:
    errors = []
    say = lambda what: errors.append(tag + what)
    dialogs = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && window.DDFRosterPaste", timeout=60000)
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => !document.getElementById('v2FindTrade').hidden", timeout=20000)
    page.wait_for_timeout(300)

    # 1. One box per side.
    for side in ("Mine", "Theirs"):
        boxes = page.evaluate("(s) => [...document.querySelectorAll(`#v2Find${s} textarea, #v2Find${s} input[type=search], #v2Find${s} input[type=text]`)].filter(e => !e.closest('details')).map(e => e.id)", side)
        if boxes != [f"v2Find{side}Search"]:
            say(f"{side}: want one add-players box, found {boxes}")
        if page.locator(f"#v2Find{side}Clear").is_visible():
            say(f"{side}: Clear is shown on an empty side")

    # 2. Suggestions directly under the box, empty roster and with a dozen players on it.
    pick = page.evaluate(PICK)
    query = pick["mine"][0][:6]
    for stage in ("empty roster", "12 players"):
        page.fill("#v2FindMineSearch", query)
        page.wait_for_timeout(150)
        g = page.evaluate(GAP, "Mine")
        if g["hidden"] or not g["count"]:
            say(f"{stage}: no suggestions for {query!r}: {g}")
        elif not -2 <= g["gap"] <= 12 or not g["inWrap"]:
            say(f"{stage}: the suggestions open {g['gap']:.0f}px from the box (want under it), inside the box's width: {g['inWrap']}")
        if names(page, "Mine"):
            if stage == "empty roster":
                say("typing a name added a player")
        page.fill("#v2FindMineSearch", "")
        if stage == "empty roster":
            for name in pick["mine"]:
                add(page, "Mine", name)
    if len(names(page, "Mine")) != len(pick["mine"]):
        say(f"typed adds put {len(names(page, 'Mine'))} on your roster, want {len(pick['mine'])}")
    if page.text_content("#v2FindMinePasteResult").strip():
        say("a search left text in the paste result")

    # 3. Clear: own side only, no dialog, focus back to the box, Undo restores.
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    mine, theirs = names(page, "Mine"), names(page, "Theirs")
    if not page.locator("#v2FindMineClear").is_visible():
        say("Clear is not shown on a side with players")
    page.click("#v2FindMineClear")
    page.wait_for_timeout(200)
    if names(page, "Mine") or names(page, "Theirs") != theirs:
        say(f"Clear on your side left mine {names(page, 'Mine')} and theirs {names(page, 'Theirs')}")
    if page.locator("#v2FindMineClear").is_visible():
        say("Clear stays shown on the emptied side")
    if page.evaluate("() => document.activeElement && document.activeElement.id") != "v2FindMineSearch":
        say("focus did not return to the box after Clear")
    if page.evaluate("() => document.getElementById('v2FindUndo').disabled"):
        say("Undo is not offered after Clear")
    page.click("#v2FindUndo")
    page.wait_for_timeout(200)
    if names(page, "Mine") != mine or names(page, "Theirs") != theirs:
        say(f"Undo after Clear gave mine {names(page, 'Mine')}, want {mine}")
    page.click("#v2FindTheirsClear")
    page.wait_for_timeout(100)
    if names(page, "Theirs") or names(page, "Mine") != mine:
        say("Clear on their side changed more than their side")
    page.click("#v2FindUndo")
    if dialogs:
        say(f"Clear asked for confirmation: {dialogs}")

    # 4. A whole page typed or pasted into the same box; a list of names.
    page.click("#v2FindMineClear")
    text = FIXTURE.read_text(encoding="utf-8")
    page.fill("#v2FindMineSearch", text)
    page.wait_for_timeout(300)
    if len(names(page, "Mine")) < 10 or "Matched" not in page.text_content("#v2FindMinePasteResult"):
        say(f"a pasted page put {len(names(page, 'Mine'))} players on your roster; result {page.text_content('#v2FindMinePasteResult')[:80]!r}")
    if page.input_value("#v2FindMineSearch"):
        say("the box kept the pasted page")
    page.click("#v2FindMineClear")
    page.evaluate("([id, text]) => { const dt = new DataTransfer(); dt.setData('text', text); document.getElementById(id).dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true})); }",
                  ["v2FindMineSearch", text])
    page.wait_for_timeout(300)
    if len(names(page, "Mine")) < 10:
        say("a paste event with a whole page added nothing")
    page.click("#v2FindMineClear")
    page.fill("#v2FindMineSearch", "\n".join(pick["mine"][:4]))
    page.wait_for_timeout(300)
    if sorted(names(page, "Mine")) != sorted(pick["mine"][:4]):
        say(f"a list of four names, one per line, gave {names(page, 'Mine')}")
    page.click("#v2FindMineClear")
    page.fill("#v2FindMineSearch", "short search text")
    if names(page, "Mine"):
        say("short text was read as a page")
    page.fill("#v2FindMineSearch", "")

    # 5. Defense and kicker (the engine prices neither, so the parser leaves them unmatched): kept, marked, not dropped by Find trades.
    page.fill("#v2FindMineSearch", text)
    page.wait_for_timeout(300)
    rows = page.evaluate(ROWS, "v2FindMinePlayers")
    marked = sorted(r["text"].split("Not evaluated")[0].split()[-1] for r in rows if "Not evaluated" in r["text"])
    if marked != ["DEF", "K"]:
        say(f"'Not evaluated' is on rows ending {marked}, want one defense and one kicker")
    if "Kept, not evaluated" not in page.text_content("#v2FindMinePasteResult"):
        say("the paste result does not say the defense and kicker were kept")
    if "Not matched" in page.text_content("#v2FindMinePasteResult") and "Chiefs" in page.text_content("#v2FindMinePasteResult").split("Not matched")[1]:
        say("the defense is listed as unmatched as well as kept")
    keep_rows = [r["name"] for r in rows if "Not evaluated" in r["text"]]
    page.click("#v2FindGo")
    page.wait_for_timeout(500)
    page.click("#v2FindEdit")
    if not set(keep_rows) <= set(names(page, "Mine")):
        say("Find trades dropped the defense or kicker from the roster")
    if "not evaluated" not in page.text_content("#v2FindOut"):
        say("the results do not say the defense and kicker are not evaluated")
    if width <= 390 and page.evaluate(OVER) > 0:
        say("horizontal overflow")
    return errors


def run_checks(overrides=None, css=None, viewports=((1440, 900), (390, 844))) -> list[str]:
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
                if css is not None:
                    page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
                page.goto(base + "#find-trade", wait_until="networkidle")
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


def caught(**kwargs) -> bool:
    """True when the checks report an error (or the broken page cannot even be driven, which also catches the defect)."""
    try:
        return bool(run_checks(**kwargs))
    except unittest.SkipTest:
        raise
    except Exception:
        return True


class FinderBoxRenderTest(unittest.TestCase):
    def test_one_box_per_side(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")
        wrap = ".v2-find-search-wrap { position: relative; }"
        self.assertIn(wrap, css, "stale mutation anchor")
        self.assertTrue(caught(css=css.replace(wrap, "", 1), viewports=((1440, 900),)), "not caught: unpositioned wrapper")
        broken = {
            "paste read as a search": ("if (looksLikePage(input.value)) { consume(input.value); return; }", ""),
            "clear does not record undo": ("    clear.addEventListener(\"click\", () => {\n      snapshot();", "    clear.addEventListener(\"click\", () => {"),
            "kept defense and kicker dropped": ("const kept = keepNotEvaluated(side, res.unmatched);", "const kept = [];"),
            "not-evaluated mark dropped": ("const badge = isNotEvaluated(p) ?", "const badge = false ?"),
        }
        for name, (old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertIn(old, js, f"mutation anchor for {name!r} is stale")
                self.assertTrue(caught(overrides={"finder.js": js.replace(old, new, 1)}, viewports=((1440, 900),)), f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
