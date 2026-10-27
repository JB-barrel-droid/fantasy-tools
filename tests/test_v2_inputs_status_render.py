"""League settings are remembered like rosters, and a status strip says what the numbers were made from.

Reader's way, in headless Chromium against the built dist/:
  1. A fresh visit shows the "default league settings" note under the league row, with Edit league and Dismiss.
  2. A league change made in Edit league (injury history) is still in force after a reload, the default note is gone,
     and nothing was kept for a reader who never changed anything.
  3. Setting everything back to the defaults removes the saved record (the reader gets the current defaults again).
  4. A shared link's league settings apply for the visit, say so, and are not saved.
  5. On Find a trade with no roster entered, the strip says so; with a roster it says the roster is saved.
  6. Blocked storage is reported.
  7. A corrupt saved league record is ignored without breaking the page.

notesFor() is also unit-checked directly (stale roster, no team marked, storage full).

Skips when no browser is available, unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import json
import unittest

from tests._dist_server import DIST, serve
from tests import _render_env

KEY = "ddf.v2.league-settings"
READY = "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady() && window.TradeValueV2"


def setUpModule():
    _render_env.ensure_built()


class Browser:
    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        exe = _render_env.chromium_executable(self._pw)
        if exe is None:
            self._pw.stop()
            raise _render_env.unavailable("no Chromium available")
        self.browser = self._pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        self._srv = serve(DIST, None)
        self.base = self._srv.__enter__()
        self.context = self.browser.new_context(viewport={"width": 1366, "height": 900})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        return self

    def open(self, hash_=""):
        self.page.goto(self.base + "/v2/" + hash_, wait_until="networkidle")
        self.page.wait_for_function(READY, timeout=90000)
        self.page.wait_for_timeout(300)
        return self.page

    def reload(self):
        # goto() to the same URL and hash is not a navigation; reload() is the reader pressing F5.
        self.page.reload(wait_until="networkidle")
        self.page.wait_for_function(READY, timeout=90000)
        self.page.wait_for_timeout(300)
        return self.page

    def __exit__(self, *exc):
        self._srv.__exit__(*exc)
        self.browser.close()
        self._pw.stop()


def notes(page):
    return page.eval_on_selector_all("#v2InputsStatus [data-note]", "els => els.map(e => e.dataset.note)")


def injury(page):
    return page.evaluate("() => window.TradeValueCurveControls.getLineupSettings().injuryHistory")


def set_injury(page, value):
    page.click("#v2EditLeague")
    page.click("#v2Popover details.v2-padv summary")
    page.click(f'#v2Popover [aria-label="Injury history"] button[data-value="{value}"]')
    page.wait_for_function(f"() => window.TradeValueCurveControls.getLineupSettings().injuryHistory === '{value}'", timeout=3000)
    page.click('#v2Popover [data-done="league"]')


class InputsStatusRender(unittest.TestCase):
    def test_league_settings_are_remembered_and_the_strip_reports_inputs(self):
        with Browser() as b:
            page = b.open("#trade-targets")
            self.assertIn("league-default", notes(page), "a fresh visit should say the defaults are in use")
            self.assertIsNone(page.evaluate(f"() => localStorage.getItem('{KEY}')"), "nothing saved before a change")
            default_injury = injury(page)
            other = "all" if default_injury != "all" else "recent"

            set_injury(page, other)
            self.assertIsNotNone(page.evaluate(f"() => localStorage.getItem('{KEY}')"), "a league change must be saved")
            self.assertNotIn("league-default", notes(page))

            page = b.reload()
            self.assertEqual(injury(page), other, "the league change must survive a reload")
            self.assertNotIn("league-default", notes(page))
            self.assertEqual(page.evaluate("() => window.TradeValueV2.leagueInputs().source"), "saved")

            set_injury(page, default_injury)
            self.assertIsNone(page.evaluate(f"() => localStorage.getItem('{KEY}')"), "defaults are not kept as a record")
            self.assertIn("league-default", notes(page))
            self.assertEqual(b.errors, [])

    def test_strip_is_one_slim_line_on_desktop_and_phone_safe(self):
        """JEG-1084: the strip was 45 px and pushed Compare's trade boxes below the 1366x768 fold. Desktop: one line
        of at most 32 px (the design is about 28), the note is whole (not cut with an ellipsis) and both actions are
        on that line. Phone (390): it may wrap, nothing overflows sideways and each action is a 44 px tap target."""
        measure = """() => {
          const note = document.querySelector('#v2InputsStatus [data-note="league-default"]');
          const text = note.querySelector('.v2-inputs-text');
          const box = note.getBoundingClientRect();
          return {height: box.height, top: box.top, cut: text.scrollWidth > text.clientWidth + 1,
            textHeight: text.getBoundingClientRect().height,
            buttons: [...note.querySelectorAll('button')].map(b => {
              const r = b.getBoundingClientRect();
              return {label: b.textContent.trim(), h: r.height, w: r.width, top: r.top, bottom: r.bottom};
            }),
            overflow: document.documentElement.scrollWidth - innerWidth};
        }"""
        with Browser() as b:
            b.page.set_viewport_size({"width": 1366, "height": 768})
            page = b.open("#compare-trade")
            got = page.evaluate(measure)
            self.assertLessEqual(got["height"], 32, f"the strip must be one slim line at 1366 wide: {got}")
            self.assertFalse(got["cut"], f"the note text is cut off at 1366: {got}")
            self.assertEqual([x["label"] for x in got["buttons"]], ["Edit league", "Dismiss"])
            for x in got["buttons"]:
                self.assertGreaterEqual(x["top"], got["top"] - 0.5)
                self.assertLessEqual(x["bottom"], got["top"] + got["height"] + 0.5, f"{x['label']} is off the strip line: {got}")
            self.assertEqual(got["overflow"], 0)

            b.page.set_viewport_size({"width": 390, "height": 844})
            page = b.open("#compare-trade")
            got = page.evaluate(measure)
            self.assertLessEqual(got["overflow"], 0, f"the strip overflows sideways at 390: {got}")
            for x in got["buttons"]:
                self.assertGreaterEqual(x["h"], 44, f"{x['label']} is under 44 px tall at 390: {got}")
                self.assertGreaterEqual(x["w"], 44)
            self.assertEqual(b.errors, [])

    def test_shared_link_settings_are_flagged_and_not_saved(self):
        with Browser() as b:
            page = b.open("#compare-trade?scoring=standard&roster=QB1.RB2.WR3.TE1.FLEX2.SF1.BN7")
            self.assertEqual(page.evaluate("() => window.TradeValueCurveControls.getState().scoring"), "standard")
            self.assertIn("league-link", notes(page))
            self.assertIsNone(page.evaluate(f"() => localStorage.getItem('{KEY}')"), "a link's settings are not saved")

    def test_roster_notes_on_roster_tabs(self):
        with Browser() as b:
            page = b.open("#find-trade")
            self.assertIn("roster-none", notes(page))
            page.evaluate("""() => window.TradeValueWorkspace.store.setMyRoster([{key: 'x:k1', name: 'Some Kicker', pos: 'K'}])""")
            page.wait_for_timeout(200)
            self.assertIn("roster-ok", notes(page))
            self.assertNotIn("roster-none", notes(page))
            page.click('#v2InputsStatus [data-note="roster-ok"] button:has-text("Dismiss")')
            self.assertNotIn("roster-ok", notes(page))

    def test_blocked_storage_is_reported(self):
        with Browser() as b:
            b.page.add_init_script("""Storage.prototype.setItem = function () { throw new DOMException('blocked', 'SecurityError'); };""")
            page = b.open("#trade-targets")
            self.assertIn("storage-off", notes(page))

    def test_saved_scoring_teams_and_roster_are_restored(self):
        record = {"v": 1, "scoring": "standard", "teams": 10, "roster": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 2, "SUPERFLEX": 1, "BENCH": 6, "K": 0, "DST": 0}}
        with Browser() as b:
            b.page.add_init_script(f"if (!localStorage.getItem('{KEY}')) localStorage.setItem('{KEY}', JSON.stringify({json.dumps(record)}));")
            page = b.open("#trade-targets")
            got = page.evaluate("() => { const C = window.TradeValueCurveControls; return {s: C.getState(), r: C.getRosterShape()}; }")
            self.assertEqual((got["s"]["scoring"], got["s"]["teams"]), ("standard", 10))
            self.assertEqual({k: got["r"][k] for k in ("WR", "FLEX", "SUPERFLEX", "BENCH")}, {"WR": 3, "FLEX": 2, "SUPERFLEX": 1, "BENCH": 6})
            self.assertNotIn("league-default", notes(page))
            self.assertEqual(b.errors, [])

    def test_corrupt_saved_league_is_ignored(self):
        with Browser() as b:
            b.page.add_init_script(f"if (!localStorage.getItem('{KEY}')) localStorage.setItem('{KEY}', '{{not json');")
            page = b.open("#trade-targets")
            self.assertIn("league-default", notes(page))
            self.assertEqual(b.errors, [])


class NotesForUnits(unittest.TestCase):
    """notesFor() is pure: run it under node without a page."""

    def run_node(self, cases):
        import subprocess
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "app" / "v2" / "inputs-status.js"
        script = f"const api = require({json.dumps(str(src))}); console.log(JSON.stringify({json.dumps(cases)}.map(c => api.notesFor(c).map(n => n.id))));"
        out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout
        return json.loads(out)

    def test_cases(self):
        now = 1_800_000_000_000
        ws = lambda **kw: {"status": "saved", "loadStatus": "ok", "teamCount": 3, "myTeam": True, "myName": "Me", "myUpdatedAt": now, **kw}
        league = lambda **kw: {"source": "saved", "notes": [], "storage": "ok", "label": "PPR · 12 teams", **kw}
        cases = [
            {"now": now, "rosterTab": True, "league": league(), "workspace": ws(myUpdatedAt=now - 8 * 86400000)},
            {"now": now, "rosterTab": True, "league": league(), "workspace": ws(myTeam=False)},
            {"now": now, "rosterTab": False, "league": league(storage="full"), "workspace": ws()},
            {"now": now, "rosterTab": False, "league": league(notes=["Your saved season week was reset."]), "workspace": None},
            {"now": now, "rosterTab": True, "league": league(), "workspace": ws(loadStatus="corrupt")},
        ]
        got = self.run_node(cases)
        self.assertEqual(got[0], ["roster-stale"])
        self.assertEqual(got[1], ["roster-no-mine"])
        self.assertEqual(got[2], ["storage-full"])
        self.assertEqual(got[3], ["league-note-0"])
        self.assertEqual(got[4], ["roster-unreadable", "roster-ok"])


if __name__ == "__main__":
    unittest.main()
