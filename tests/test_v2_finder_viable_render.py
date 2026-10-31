"""v2 Find a trade (JEG-1043, Jeremy 2026-10-27: "A"), rendered: "Show viable offers only" and the starters line at the
positions each side gives up.

Two full rosters are typed in (they hold the top QB only; RB, WR, TE dealt alternately), keep-lineup boxes off, size
up to 3-for-3, Find trades runs. At 1366x768, 390 and
320 wide:

  * the toggle is shown, unticked, with "N of M groups" where M is the groups found and N <= M; it is at least 44 px tall;
  * every group card carries its viability (data-find-viable), and the card's fit line names a viability exactly when
    that value is set;
  * ticking it lists only cards with a viability, min(10, N) of them (or the empty state when N is 0), and unticking
    restores the full list;
  * each card says, for you and for them, the starters at the positions given up: the positions named are exactly
    the QB/RB/WR/TE among the players that side sends;
  * no sideways scroll on a phone; no page errors.

Discrimination: test_guard_fails_on_broken_builds serves finder.js with the toggle not re-listing, the filter keeping
every group, and the given-positions line read from the wrong side, and requires each to fail.
"""
from __future__ import annotations

import functools
import re
import unittest

from tests import _render_env
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_finder_render import FINDER_JS, _built_dist, add
from tests.test_v2_modules_render import _serve


def setUpModule():
    _render_env.ensure_built()


# Two full rosters, by position, from the top players by DDF Value with unique names. They get the top QB only and you
# the next two, so a package that takes their only QB is listed (keep-lineup boxes off) but is not viable: the week's
# data gives a mix of viable and non-viable groups. RB, WR, TE are dealt alternately (theirs first at RB and TE).
PICK = """() => {
  const rows = window.TradeValueCurveControls.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value) && r.name)
    .sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const count = new Map(); rows.forEach(r => count.set(r.name, (count.get(r.name) || 0) + 1));
  const at = pos => rows.filter(r => r.pos === pos && count.get(r.name) === 1);
  const qbs = at('QB').slice(0, 3);
  const mine = [qbs[1].name, qbs[2].name], theirs = [qbs[0].name];
  [['RB', 8, 1], ['WR', 8, 0], ['TE', 4, 1]].forEach(([pos, n, first]) => {
    at(pos).slice(0, n).forEach((r, i) => (((i + first) % 2) ? theirs : mine).push(r.name));
  });
  return {mine, theirs};
}"""

MIXED = []   # widths where the week's data gave both viable and non-viable groups (the filter is then observable)

CARDS = """() => {
  const byName = new Map(window.TradeValueCurveControls.getAllRows().map(r => [r.name, r]));
  return [...document.querySelectorAll('#v2FindList > li.v2-find-group')].map(li => {
    const [give, get] = li.querySelector('b').textContent.replace('You give ', '').split('; you receive ').map(s => s.split(' + '));
    const posOf = names => [...new Set(names.map(n => (byName.get(n) || {}).pos).filter(p => ['QB', 'RB', 'WR', 'TE'].includes(p)))].sort();
    const given = [...li.querySelectorAll('.v2-find-given')].map(p => p.textContent);
    const fit = li.querySelector('.v2-find-fit');
    return {viable: li.dataset.findViable, hasViable: 'findViable' in li.dataset, givePos: posOf(give), getPos: posOf(get), given,
            fitNamesViability: Boolean(fit && !fit.hidden && /viability/.test(fit.textContent))};
  });
}"""

POS_IN_LINE = re.compile(r"\b(QB|RB|WR|TE) ")


def given_positions(line: str) -> list[str]:
    return sorted(set(POS_IN_LINE.findall(line.split(": ", 1)[1]))) if ": " in line else []


def check(page, tag, width) -> list[str]:
    errors = []
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view() && document.getElementById('v2FindEdit') && !document.getElementById('v2FindTrade').hidden", timeout=60000)
    pick = page.evaluate(PICK)
    for name in pick["mine"]:
        add(page, "Mine", name)
    for name in pick["theirs"]:
        add(page, "Theirs", name)
    page.uncheck("#v2FindKeepMine")
    page.uncheck("#v2FindKeepTheirs")
    page.select_option("#v2FindSize", "3")
    page.click("#v2FindGo")
    page.wait_for_timeout(500)
    if not page.is_visible("#v2FindViableOnly"):
        return [tag + "no 'Show viable offers only' toggle"]
    if page.is_checked("#v2FindViableOnly"):
        errors.append(tag + "the toggle starts ticked")
    label = page.inner_text(".v2-find-viable-toggle")
    m = re.search(r"\((\d+) of (\d+) groups?\)", label)
    if not m:
        return errors + [tag + f"toggle label has no 'N of M groups': {label!r}"]
    viable_n, total = int(m.group(1)), int(m.group(2))
    if viable_n > total:
        errors.append(tag + f"{viable_n} viable of {total}")
    if 0 < viable_n < total:
        MIXED.append(width)
    if page.evaluate("() => document.querySelector('.v2-find-viable-toggle').getBoundingClientRect().height") < 44:
        errors.append(tag + "toggle under 44 px tall")

    cards = page.evaluate(CARDS)
    if len(cards) != min(10, total):
        errors.append(tag + f"{len(cards)} cards before filtering, expected {min(10, total)}")
    for i, c in enumerate(cards):
        if not c["hasViable"]:
            errors.append(tag + f"card {i} has no data-find-viable")
        if bool(c["viable"]) != c["fitNamesViability"]:
            errors.append(tag + f"card {i}: viability {c['viable']!r} but fit line naming it is {c['fitNamesViability']}")
        mine = [g for g in c["given"] if g.startswith("Your starters")]
        theirs = [g for g in c["given"] if g.startswith("Their starters")]
        if (given_positions(mine[0]) if mine else []) != c["givePos"]:
            errors.append(tag + f"card {i}: your given-positions line {mine} vs positions you send {c['givePos']}")
        if (given_positions(theirs[0]) if theirs else []) != c["getPos"]:
            errors.append(tag + f"card {i}: their given-positions line {theirs} vs positions they send {c['getPos']}")

    page.check("#v2FindViableOnly")
    page.wait_for_timeout(200)
    filtered = page.evaluate(CARDS)
    if viable_n == 0:
        if filtered or not page.is_visible("#v2FindViableEmpty"):
            errors.append(tag + f"no viable groups but {len(filtered)} cards listed / empty state hidden")
    else:
        if len(filtered) != min(10, viable_n):
            errors.append(tag + f"{len(filtered)} cards with the filter on, expected {min(10, viable_n)}")
        if any(not c["viable"] for c in filtered):
            errors.append(tag + "a card without a viability is listed with the filter on")
    page.uncheck("#v2FindViableOnly")
    page.wait_for_timeout(200)
    if len(page.evaluate(CARDS)) != min(10, total):
        errors.append(tag + "unticking does not restore the full list")
    if width <= 390 and page.evaluate("() => document.documentElement.scrollWidth - innerWidth") > 0:
        errors.append(tag + "horizontal overflow")
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


class FinderViableRenderTest(unittest.TestCase):
    def test_viable_toggle_and_given_positions(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "toggle does not re-list": js.replace("box.addEventListener(\"change\", () => { S.viableOnly = box.checked; renderList(); });",
                                                  "box.addEventListener(\"change\", () => { S.viableOnly = box.checked; });", 1),
            "filter keeps every group": js.replace("const shown = S.viableOnly && viabOf ? viableGroups(groups, viabOf) : groups;",
                                                   "const shown = groups;", 1),
            "given line read from the other side": js.replace(
                'const given = startersAtGivenPositions(imps.ddf, sideRows(lineup, "ddf", who, giveRows, recvRows).leaving);',
                'const given = startersAtGivenPositions(imps.ddf, sideRows(lineup, "ddf", who, giveRows, recvRows).arriving);', 1),
        }
        MIXED.clear()
        self.assertEqual(run_checks(viewports=((1366, 768),)), [])
        mixed = bool(MIXED)
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                if name != "given line read from the other side" and not mixed:
                    self.skipTest("this week's data gives no non-viable group, so the filter cannot be observed")
                try:
                    errors = run_checks({"finder.js": body}, viewports=((1366, 768),))
                except Exception as exc:
                    errors = [str(exc)[:80]]
                self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
