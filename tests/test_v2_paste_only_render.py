"""JEG-1131: paste is the only league load at launch (Jeremy, 2026-10-26: no platform integrations).

With default settings (no ?integrations=1):
  * Your league: the "Load a whole league" box offers a paste box only; no league-ID select, field or Load teams button,
    and its summary names no league ID;
  * Find a trade: "Other ways to add players" offers pasted names only, with no Sleeper/ESPN league-ID option;
  * pasting a Sleeper or ESPN league link makes no request to api.sleeper.app or fantasy.espn.com and shows the
    copy-each-team-or-rosters-page tip instead;
  * with ?integrations=1 the ID loaders are still there (tests/test_v2_finder_import_render.py exercises them).

Discrimination: test_guard_fails_on_broken_builds serves league.js with the ID UI always shown and finder.js with the
flag always on, and requires the checks to fail on each.
"""
from __future__ import annotations

import unittest

from tests._league_render import browser_on_build, open_page, source

SLEEPER_LINK = "https://sleeper.com/leagues/1180123456789012345/roster"
ESPN_LINK = "https://fantasy.espn.com/football/league/rosters?leagueId=123456&seasonId=2026"


def paste(page, text):
    page.evaluate("""text => { const t = document.getElementById('v2LgLeaguePaste'); const data = new DataTransfer();
      data.setData('text', text); t.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true})); }""", text)


def check(browser, base, overrides=None):
    errors = []
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[paste-only] ")
    platform = []
    page.on("request", lambda r: platform.append(r.url) if ("sleeper.app" in r.url or "fantasy.espn.com" in r.url) else None)
    ids = page.evaluate("""() => ({kind: !!document.getElementById('v2LgLeagueKind'), id: !!document.getElementById('v2LgLeagueId'),
      load: !!document.getElementById('v2LgLeagueLoad'), summary: document.querySelector('#v2LgImport summary').textContent,
      help: document.getElementById('v2LgLeaguePasteHelp').textContent, placeholder: document.getElementById('v2LgLeaguePaste').placeholder})""")
    if ids["kind"] or ids["id"] or ids["load"]:
        errors.append(f"league-ID controls are on the default page: {ids}")
    if "ID" in ids["summary"] or "league link" in ids["help"] or "Sleeper league link" in ids["placeholder"]:
        errors.append(f"default copy still offers a league ID or link: {ids}")
    for link in (SLEEPER_LINK, ESPN_LINK):
        paste(page, link)
        page.wait_for_function("() => /rosters|copy/i.test((document.getElementById('v2LgLeagueStatus') || {}).textContent || '')", timeout=10000)
        tip = page.text_content("#v2LgLeagueStatus")
        if "copy" not in tip.lower() and "rosters page" not in tip.lower():
            errors.append(f"pasting {link} shows {tip!r}, want the copy tip")
    # Find a trade
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_function("() => document.getElementById('v2FindMineSource')", timeout=20000)
    find = page.evaluate("""() => { const sel = document.getElementById('v2FindMineSource'); const box = sel.closest('details');
      return {options: [...sel.options].map(o => o.value), selHidden: sel.hidden, idHidden: document.getElementById('v2FindMineLeague').hidden,
        summary: box.querySelector('summary').textContent}; }""")
    if find["options"] != ["paste"] or not find["selHidden"] or not find["idHidden"] or "ID" in find["summary"]:
        errors.append(f"Find a trade offers a league ID by default: {find}")
    if platform:
        errors.append(f"requests to a platform API on the default page: {platform}")
    # The flag brings the loaders back.
    page.goto(base + "?integrations=1#find-league", wait_until="networkidle")
    page.wait_for_function("() => document.getElementById('v2LgCard')", timeout=30000)
    if not page.evaluate("() => !!document.getElementById('v2LgLeagueId')"):
        errors.append("?integrations=1 does not bring back the league-ID field")
    return errors


def run_checks(overrides=None):
    with browser_on_build() as (browser, base):
        return check(browser, base, overrides)


class PasteOnlyRenderTest(unittest.TestCase):
    def test_default_is_paste_only(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        league, finder = source("league.js"), source("finder.js")
        broken = {
            "league ID UI always shown": {"league.js": league.replace("const integrations = F.page.integrationsOn();", "const integrations = true;", 1)},
            "finder flag always on": {"finder.js": finder.replace("const integrationsOn = () => {", "const integrationsOn = () => true; const unusedIntegrationsOn = () => {", 1)},
        }
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                for fname, body in overrides.items():
                    self.assertNotEqual(body, source(fname), f"mutation anchor for {name!r} is stale")
                try:
                    caught = run_checks(overrides)
                except Exception as exc:
                    caught = [f"raised {type(exc).__name__}"]
                self.assertNotEqual(caught, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
