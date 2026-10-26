"""JEG-1094: Find a trade is two screens. Rendered check.

  * #find-trade ("your team"): the one-roster-against-one-roster finder card, no league cards;
  * #find-league ("league-wide"): the league, team summary and trade opportunities cards, no finder card;
  * each screen has its own tab and its own empty state;
  * an old league share link (#find-trade?workspace=...) moves to the league-wide screen.

Discrimination: test_guard_fails_on_broken_builds serves v2.js with both screens shown together, and league.js
mounting its cards on the one-team page, and requires the checks to fail on each.
"""
from __future__ import annotations

import unittest


from tests._league_render import browser_on_build, open_page, source

SNAP = """() => {
  const shown = id => { const n = document.getElementById(id); return Boolean(n) && !n.hidden && n.offsetParent !== null; };
  const inside = (id, host) => { const n = document.getElementById(id), h = document.getElementById(host); return Boolean(n && h && h.contains(n)); };
  return {hash: location.hash,
    tabs: [...document.querySelectorAll('.v2-tab')].filter(t => t.getAttribute('aria-current') === 'page').map(t => t.dataset.view),
    team: shown('v2FindTrade'), league: shown('v2FindLeague'),
    finderCard: shown('v2Find'), leagueCard: shown('v2LgCard'),
    finderInLeague: inside('v2Find', 'v2FindLeague'), leagueInTeam: inside('v2LgCard', 'v2FindTrade'),
    teamEmpty: Boolean(document.querySelector('#v2FindFit')) && (document.getElementById('v2FindFit').textContent || '').trim().length > 0,
    leagueEmpty: (document.getElementById('v2LgEmpty') || {}).textContent || ''};
}"""


def check(browser, base, overrides=None):
    errors = []
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[split] ")
    page.wait_for_function("() => document.getElementById('v2Find')", timeout=30000)
    s = page.evaluate(SNAP)
    if s["tabs"] != ["league"] or not s["league"] or s["team"] or not s["leagueCard"] or s["finderCard"]:
        errors.append(f"#find-league shows the wrong screen: {s}")
    if "No teams yet" not in s["leagueEmpty"]:
        errors.append(f"league-wide screen has no empty state: {s['leagueEmpty']!r}")
    page.evaluate("() => { location.hash = '#find-trade'; }")
    page.wait_for_timeout(300)
    s = page.evaluate(SNAP)
    if s["tabs"] != ["find"] or not s["team"] or s["league"] or not s["finderCard"] or s["leagueCard"]:
        errors.append(f"#find-trade shows the wrong screen: {s}")
    if not s["teamEmpty"]:
        errors.append("your-team screen has no empty state (fit headline empty)")
    if s["finderInLeague"] or s["leagueInTeam"]:
        errors.append(f"a card sits on the wrong screen: {s}")
    page.evaluate("() => { location.hash = '#find-trade?workspace=zzz'; }")
    page.wait_for_timeout(400)
    s = page.evaluate(SNAP)
    if not s["hash"].startswith("#find-league") or s["tabs"] != ["league"]:
        errors.append(f"the old league share link did not move to the league-wide screen: {s}")
    page.close()
    return errors


def run_checks(overrides=None):
    with browser_on_build() as (browser, base):
        return check(browser, base, overrides)


class FindSplitRenderTest(unittest.TestCase):
    def test_two_screens(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2, league = source("v2.js"), source("league.js")
        broken = {
            "both screens shown": {"v2.js": v2.replace('$("v2FindLeague").hidden = v !== "league";', '$("v2FindLeague").hidden = v !== "league" && v !== "find";', 1)},
            "league cards on the team page": {"league.js": league.replace('const host = $("v2FindLeague");', 'const host = $("v2FindTrade");', 1)},
        }
        for name, over in broken.items():
            with self.subTest(mutation=name):
                (file, body), = over.items()
                self.assertNotEqual(body, {"v2.js": v2, "league.js": league}[file], f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(over), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
