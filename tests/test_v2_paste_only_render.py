"""JEG-1131: paste is the only league load at launch (Jeremy, 2026-10-26: no platform integrations).

With default settings (no ?integrations=1):
  * Your league: the "Load a whole league" box offers a paste box only; no league-ID select, field or Load teams button,
    and its summary names no league ID;
  * Find a trade: "Other ways to add players" offers pasted names only, with no Sleeper/ESPN league-ID option;
  * pasting a Sleeper or ESPN league link makes no request to api.sleeper.app or fantasy.espn.com and shows the
    copy-each-team-or-rosters-page tip instead;
  * the fetchers are deleted (Jeremy, 2026-10-27): the shipped sources hold no api.sleeper.app / espn API URL, loadSleeper,
    loadEspn or integrations flag, and ?integrations=1 changes nothing.

Discrimination: test_guard_fails_on_broken_builds serves league.js with a league-ID field added and finder.js with a
Sleeper fetch added, and requires the checks to fail on each.
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
    page.wait_for_function("() => document.getElementById('v2FindMinePaste')", timeout=20000)
    find = page.evaluate("""() => ({source: !!document.getElementById('v2FindMineSource'), league: !!document.getElementById('v2FindMineLeague'),
      summary: document.getElementById('v2FindMinePaste').closest('details').querySelector('summary').textContent})""")
    if find["source"] or find["league"] or "ID" in find["summary"]:
        errors.append(f"Find a trade offers a league ID by default: {find}")
    page.click("#v2FindMinePaste >> xpath=ancestor::details/summary")
    page.fill("#v2FindMinePaste", "Josh Allen")
    page.click("#v2FindMineLoad")   # adding players must not reach a platform either
    page.wait_for_timeout(500)
    if platform:
        errors.append(f"requests to a platform API on the default page: {platform}")
    # The old flag changes nothing.
    page.goto(base + "?integrations=1#find-league", wait_until="networkidle")
    page.wait_for_function("() => document.getElementById('v2LgCard')", timeout=30000)
    if page.evaluate("() => !!document.getElementById('v2LgLeagueId')"):
        errors.append("?integrations=1 brings back the league-ID field")
    return errors


def run_checks(overrides=None):
    with browser_on_build() as (browser, base):
        return check(browser, base, overrides)


class PasteOnlyRenderTest(unittest.TestCase):
    def test_default_is_paste_only(self):
        self.assertEqual(run_checks(), [])

    def test_fetcher_code_is_gone(self):
        for name in ("finder.js", "league.js"):
            text = source(name)
            for needle in ("api.sleeper.app", "lm-api-reads.fantasy.espn.com", "loadSleeper", "loadEspn", "parseSleeper", "parseEspn",
                           "integrationsOn", "loadWholeLeague", "root.fetch"):
                self.assertNotIn(needle, text, f"{needle} is back in app/v2/{name}")

    def test_guard_fails_on_broken_builds(self):
        league, finder = source("league.js"), source("finder.js")
        league_anchor = 'el("div", {class: "v2-meta", id: "v2LgLeagueStatus", role: "status"})'
        finder_anchor = 'el("details", {class: "v2-find-import"}'
        broken = {
            "league ID field added": {"league.js": league.replace(league_anchor, 'el("input", {id: "v2LgLeagueId"}), ' + league_anchor, 1)},
            "finder fetches Sleeper": {"finder.js": finder.replace('load.addEventListener("click", () => {', 'load.addEventListener("click", () => { root.fetch("https://api.sleeper.app/v1/x").catch(() => {});', 1)},
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
