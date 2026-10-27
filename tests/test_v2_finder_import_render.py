"""v2 Find a trade, second slice (JEG-481), rendered: pasted-name import and roster sanity.

JEG-1131 (Jeremy, 2026-10-27): the Sleeper/ESPN league-ID fetchers are deleted; pasted names are the only import here.
tests/test_v2_paste_only_render.py pins that no league-ID UI or platform request exists.

Builds dist/v2 into a temp copy of the built dist/ and loads Compare a trade headless (hermetic). Checks:

  * pasted names put those players (matched to the engine's rows by name) on each side, and the status says how many
    were added;
  * a pasted name not in the values is reported, never added; a player already on the other roster is left out and said so;
  * roster sanity, recomputed here from the engine's rows and the league's roster shape: with "keep my starting lineup
    filled" and "keep theirs filled" on, no listed trade leaves a side short at QB/RB/WR/TE (fewer players than the slots
    and fewer than before); with both off, the list is at least as long and a thin trade carries "Leaves you thin";
  * no page errors, no sideways scroll at 390.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the keep flags ignored and with the pasted-name
parser dropping every name after the first, and requires each to fail.
"""
from __future__ import annotations

import functools
import unittest
from pathlib import Path

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_modules_render import _built_dist, _serve

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"


def setUpModule():
    _render_env.ensure_built()


PICK = """() => {
  const C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name && ['QB','RB','WR','TE'].includes(r.pos))
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const count = new Map(); rows.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const unique = rows.filter(r => count.get(r.name) === 1);
  const take = (pos, from, n) => unique.filter(r => r.pos === pos).slice(from, from + n);
  const mine = [].concat(take('QB', 0, 1), take('RB', 0, 2), take('WR', 0, 3), take('TE', 0, 1));
  const theirs = [].concat(take('QB', 1, 1), take('RB', 2, 3), take('WR', 3, 3), take('TE', 1, 1));
  return {mine: mine.map(r => [r.name, r.pos]), theirs: theirs.map(r => [r.name, r.pos]), shape: C.getRosterShape()};
}"""

# The listed trades, each independently checked for a thin side from the engine's rows.
AUDIT = """(shape) => {
  const C = window.TradeValueCurveControls;
  const byName = new Map(C.getAllRows().map(r => [r.name, r]));
  const side = id => [...document.querySelectorAll(`#${id} li b`)].map(b => byName.get(b.textContent)).filter(Boolean);
  const mine = side('v2FindMinePlayers'), theirs = side('v2FindTheirsPlayers');
  const POS = ['QB', 'RB', 'WR', 'TE'];
  const count = (rows, pos, tier) => rows.filter(r => r.pos === pos && (!tier || r.ddfTier === 'starter')).length;
  const thin = (roster, gone, came) => POS.some(pos => {
    const need = shape[pos] || 0; if (!need) return false;
    const before = count(roster, pos), after = before - count(gone, pos) + count(came, pos);
    const sb = count(roster, pos, true), sa = sb - count(gone, pos, true) + count(came, pos, true);
    return (after < need && after < before) || (sa < Math.min(sb, need));
  });
  return [...document.querySelectorAll('#v2FindList li')].map(li => {
    const [give, get] = li.querySelector('b').textContent.replace('You give ', '').split('; you receive ').map(s => s.split(' + ').map(n => byName.get(n)));
    return {mineThin: thin(mine, give, get), theirsThin: thin(theirs, get, give), text: li.textContent};
  });
}"""


def paste_team(page, side, names):
    if not page.evaluate("(s) => document.querySelector(`#v2Find${s} .v2-find-import`).open", side):
        page.click(f"#v2Find{side} .v2-find-import summary")
    page.fill(f"#v2Find{side}Paste", "\n".join(names))
    page.click(f"#v2Find{side}Load")


def names_on(page, side):
    return page.evaluate("(id) => [...document.querySelectorAll(`#${id} li b`)].map(b => b.textContent)", f"v2Find{side}Players")


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2Find') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)

    paste_team(page, "Mine", [n for n, _ in pick["mine"]])
    want = sorted(n for n, _ in pick["mine"])
    if sorted(names_on(page, "Mine")) != want:
        errors.append(tag + f"pasted names put {sorted(names_on(page, 'Mine'))} on my roster, want {want}")
    status = page.text_content("#v2FindMineStatus")
    if f"Added {len(want)}" not in status:
        errors.append(tag + f"paste status {status!r} does not say how many were added")
    paste_team(page, "Theirs", [n for n, _ in pick["theirs"]])
    want_theirs = sorted(n for n, _ in pick["theirs"])
    if sorted(names_on(page, "Theirs")) != want_theirs:
        errors.append(tag + f"pasted names put {sorted(names_on(page, 'Theirs'))} on their roster, want {want_theirs}")

    # Pasted names: one is real but already on my roster, one is not a player.
    paste_team(page, "Theirs", [pick["mine"][0][0], "Not A Real Player"])
    status = page.text_content("#v2FindTheirsStatus")
    if pick["mine"][0][0] not in status or "Not A Real Player" not in status:
        errors.append(tag + f"paste status {status!r} does not report the player on the other roster and the unmatched name")
    if pick["mine"][0][0] in names_on(page, "Theirs") or "Not A Real Player" in names_on(page, "Theirs"):
        errors.append(tag + "a player on the other roster or an unmatched name was added")

    # Roster sanity.
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(500)
    on = page.evaluate(AUDIT, pick["shape"])
    if any(t["mineThin"] or t["theirsThin"] for t in on):
        errors.append(tag + "a trade that leaves a side short is listed with the keep boxes on")
    page.uncheck("#v2FindKeepMine")
    page.uncheck("#v2FindKeepTheirs")
    page.click("#v2FindGo")
    page.wait_for_timeout(500)
    off = page.evaluate(AUDIT, pick["shape"])
    if len(off) < len(on):
        errors.append(tag + f"{len(off)} trades with the boxes off, fewer than {len(on)} with them on")
    thin = [t for t in off if t["mineThin"] or t["theirsThin"]]
    if not thin:
        errors.append(tag + "no thin trade appeared with the boxes off, so the sanity check was not exercised")
    for t in thin:
        who = "you" if t["mineThin"] else "them"
        if f"Leaves {who} thin" not in t["text"]:
            errors.append(tag + f"a thin trade does not say so: {t['text']!r}")
    if width <= 390 and page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "horizontal overflow")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844))) -> list[str]:
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
                context.add_init_script(_render_env.pin_data_week_script())   # the data's content week, not the real clock (JEG-1152)
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


class FinderImportRenderTest(unittest.TestCase):
    def test_import_and_sanity(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "keep flags ignored": ("((sanity.keepMine && issues.mine.length) || (sanity.keepTheirs && issues.theirs.length))", "false"),
            "pasted names keep only the first": (".filter(Boolean).map(name => ({name, pos: \"\"}));", ".filter(Boolean).slice(0, 1).map(name => ({name, pos: \"\"}));"),
        }
        for name, (old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertIn(old, js, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks({"finder.js": js.replace(old, new, 1)}, viewports=((1440, 900),)), [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
