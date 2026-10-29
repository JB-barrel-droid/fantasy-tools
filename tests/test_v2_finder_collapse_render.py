"""v2 Find a trade, collapsible roster input (JEG-972, decision Jeremy 2026-10-23), rendered.

Every Find trades press folds the roster input into a summary row per team (team label, first three players,
position counts); "Edit rosters" opens it again. Checked at 1366x768, 390 and 320 wide:

  * before Find the input is open, no summary shows, and the Edit button says aria-expanded=true;
  * after Find the input is hidden, the summary shows the first three names, "+ N more" and the position counts for
    both teams, the button says aria-expanded=false and names both player counts, and the results start inside the
    first screen (desktop and phone);
  * Edit rosters (by keyboard) opens the input and moves focus into the first paste box; Escape folds it again and
    focus returns to the button; pressing Find again folds it again;
  * package size, the lineup boxes and Find trades stay visible while folded;
  * JEG-1237: the protected-position and bench-backup settings fold with the rosters and read back as one "Trade
    settings:" line in the summary (Edit rosters opens them again, by keyboard), Advanced trade minimums stays on the
    page, and at 1366x768 the results start inside the first screen without enlarging the viewport;
  * no page errors, no sideways scroll.

Discrimination: test_guard_fails_on_broken_builds serves finder.js without the fold after Find, with the button not
tracking aria-expanded, with no focus move on open, with the trade settings left open after Find and with no settings
line in the summary, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, PICK, _built_dist, add
from tests.test_v2_modules_render import _serve


def setUpModule():
    _render_env.ensure_built()


STATE = """() => {
  const vis = id => { const n = document.getElementById(id); return Boolean(n) && !n.hidden && n.getBoundingClientRect().height > 0; };
  const out = document.getElementById('v2FindOut');
  return {input: vis('v2FindInput'), summary: vis('v2FindSummary'), rails: vis('v2FindGuardrails'),
    advanced: Boolean(document.querySelector('.v2-find-advanced')) && document.querySelector('.v2-find-advanced').getBoundingClientRect().height > 0,
    railsText: (document.getElementById('v2FindGuardrailSummary') || {}).innerText || '',
    expanded: document.getElementById('v2FindEdit').getAttribute('aria-expanded'),
    label: document.getElementById('v2FindEdit').getAttribute('aria-label'),
    mine: document.getElementById('v2FindMineSummary').innerText, theirs: document.getElementById('v2FindTheirsSummary').innerText,
    controls: ['v2FindSize', 'v2FindKeepMine', 'v2FindKeepTheirs', 'v2FindGo'].filter(id => !vis(id)),
    resultsTop: out.getBoundingClientRect().top, viewport: innerHeight, focus: document.activeElement && document.activeElement.id,
    scrollX: document.documentElement.scrollWidth - innerWidth};
}"""


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    page.select_option("#v2FindSize", "3")
    s = page.evaluate(STATE)
    if not s["input"] or s["summary"] or s["expanded"] != "true":
        errors.append(tag + f"before Find the input should be open with no summary: {s}")
    if not s["rails"]:
        errors.append(tag + "before Find the protected-position and bench-backup settings are not shown")
    page.focus("#v2FindGo")
    page.wait_for_timeout(900)   # the page scrolls smoothly to the focused button; a user presses Find once it has stopped
    page.keyboard.press("Enter")
    page.wait_for_timeout(400)
    s = page.evaluate(STATE)
    if s["input"] or not s["summary"] or s["expanded"] != "false":
        errors.append(tag + f"Find did not fold the roster input: input {s['input']} summary {s['summary']} expanded {s['expanded']}")
    first3 = ", ".join(pick["mine"][:3])
    for who, text, names, total in (("mine", s["mine"], pick["mine"], len(pick["mine"])), ("theirs", s["theirs"], pick["theirs"], len(pick["theirs"]))):
        shown = [n for n in names[:3]]
        if not all(n in text for n in shown) or f"+ {total - 3} more" not in text or f"{total} players" not in text:
            errors.append(tag + f"{who} summary does not show first three, '+ {total - 3} more' and the count: {text!r}")
    if not any(pos in s["mine"] for pos in ("RB", "WR", "QB", "TE")):
        errors.append(tag + "summary has no position counts")
    if f"{len(pick['mine'])} players" not in (s["label"] or "") or f"{len(pick['theirs'])} players" not in (s["label"] or ""):
        errors.append(tag + f"Edit button label lacks the player counts: {s['label']!r}")
    if s["controls"]:
        errors.append(tag + f"controls hidden while folded: {s['controls']}")
    if s["rails"]:
        errors.append(tag + "the protected-position and bench-backup settings stay open after Find")
    if not s["railsText"].startswith("Trade settings: ") or "no protected positions or bench backup minimums" not in s["railsText"]:
        errors.append(tag + f"the folded summary does not read back the default trade settings: {s['railsText']!r}")
    if not s["advanced"]:
        errors.append(tag + "Advanced trade minimums is not on the page while folded")
    if not -8 <= s["resultsTop"] < s["viewport"] * 0.8:
        errors.append(tag + f"results start at {s['resultsTop']:.0f}px of a {s['viewport']}px screen after folding")
    if s["scrollX"] > 0:
        errors.append(tag + "horizontal overflow when folded")
    # Edit rosters, from the keyboard.
    page.focus("#v2FindEdit")
    page.keyboard.press("Enter")
    page.wait_for_timeout(200)
    s = page.evaluate(STATE)
    if not s["input"] or s["summary"] or s["expanded"] != "true":
        errors.append(tag + f"Edit rosters did not open the input: {s}")
    if s["focus"] != "v2FindMineSearch":
        errors.append(tag + f"focus after Edit rosters is {s['focus']!r}, expected the first paste box")
    if not s["rails"]:
        errors.append(tag + "Edit rosters did not open the protected-position and bench-backup settings")
    page.keyboard.press("Escape")
    page.wait_for_timeout(200)
    s = page.evaluate(STATE)
    if s["input"] or s["expanded"] != "false" or s["focus"] != "v2FindEdit":
        errors.append(tag + f"Escape did not fold the input and return focus to Edit rosters: input {s['input']}, focus {s['focus']!r}")
    page.click("#v2FindEdit")
    # The opened settings work from the keyboard, and the folded line reads back what was set.
    page.focus("#v2FindProtectRB")
    page.keyboard.press("Space")
    page.focus("#v2FindBackupsTEUp")
    page.keyboard.press("Enter")
    page.keyboard.press("Enter")
    if not page.is_checked("#v2FindProtectRB") or page.inner_text("#v2FindBackupsTE") != "2":
        errors.append(tag + "the opened trade settings do not respond to the keyboard")
    page.click("#v2FindGo")
    page.wait_for_timeout(300)
    s = page.evaluate(STATE)
    if s["input"] or s["rails"]:
        errors.append(tag + "a second Find trades press did not fold the input again")
    if s["railsText"] != "Trade settings: protecting RB; minimum bench backups TE 2":
        errors.append(tag + f"the folded summary does not read back the settings just made: {s['railsText']!r}")
    return errors


def run_checks(overrides=None, viewports=((1366, 768), (390, 844), (320, 640))) -> list[str]:
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
                page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
                errors += check(page, f"[{width}px] ", width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class FinderCollapseRenderTest(unittest.TestCase):
    def test_collapsible_input(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "Find does not fold the input": js.replace("    setCollapsed(true);\n    const out", "    const out", 1),
            "button does not track aria-expanded": js.replace('edit.setAttribute("aria-expanded", String(!collapsed));', "", 1),
            "no focus move on open": js.replace('if (focus === "input") { const first', 'if (false) { const first', 1),
            "trade settings stay open after Find": js.replace("    if (rails) rails.hidden = collapsed;\n", "", 1),
            "no settings line in the summary": js.replace("    if (rails) rails.textContent = guardrailText();\n", "", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                try:
                    errors = run_checks({"finder.js": body}, viewports=((1366, 768),))
                except Exception as exc:   # the page is so broken a step cannot even run
                    errors = [str(exc)[:80]]
                self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
