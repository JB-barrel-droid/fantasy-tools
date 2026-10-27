"""JEG-1095: after a whole-league paste the league-wide screen says what it read.

  * a 12-team ESPN-style paste: the summary names the team count, every team with its roster size, says which team is
    yours (none marked yet, then the one whose star is pressed), and lists a line that matched no player;
  * a paste with no teams in it shows a plain error and no team list.

Discrimination: test_guard_fails_on_broken_builds serves league.js with the summary never shown, and with the unmatched
lines dropped, and requires the checks to fail on each.
"""
from __future__ import annotations

import unittest

from tests._league_render import browser_on_build, fixture, open_page, source

BOGUS = "Jalen Qwertyuiop"


def espn_league_text(teams=12) -> tuple[str, list[tuple[str, int]]]:
    fx = fixture("20team")
    lines = ["ESPN", "NFL", "ESPN Fantasy", "League Rosters", "Test league", ""]
    expect = []
    for i, team in enumerate(fx["teams"][:teams]):
        players = [p for p in team["players"] if not p["key"].startswith("x:")]
        name = team["name"].replace("Bye Week Bandits", "Fumble Bandits")   # a team name starting "Bye Week" is read as ESPN's Bye Week Players section (JEG-1110)
        lines.append(f"{name} (5-1-0)")
        lines += ["SLOT\tPLAYER\tACQ"]
        for p in players:
            lines += [p["pos"], f"{p['name']}{p['name']}", f"{p['team']} {p['pos']}", "Draft"]
        expect.append((name, len(players)))
    return "\n".join(lines) + "\n", expect


SNAP = """() => { const box = document.getElementById('v2LgParsed');
  return {hidden: box.hidden, state: box.dataset.state || '', head: (box.querySelector('h3') || {}).textContent || '',
    error: (document.getElementById('v2LgParsedError') || {}).textContent || '',
    mine: (document.getElementById('v2LgParsedMine') || {}).textContent || '',
    teams: [...box.querySelectorAll('#v2LgParsedTeams > li')].map(li => ({name: li.dataset.team, count: Number(li.dataset.count), text: li.textContent})),
    miss: (document.getElementById('v2LgParsedMiss') || {}).textContent || '', text: box.textContent}; }"""


def check(browser, base, overrides=None):
    errors = []
    page = open_page(browser, base, overrides=overrides, errors=errors, tag="[parsed] ")
    text, expect = espn_league_text()
    # The parser only reports a line it could not place when the line is ambiguous; add one to the second team's result
    # so the display of an unmatched line is checked against the real page code.
    page.evaluate("""line => { const P = window.DDFRosterPaste; const real = P.parseLeague;
      P.parseLeague = (t, rows) => { const res = real(t, rows); if (res.teams[1]) res.teams[1].unmatched.push({line, reason: 'ambiguous', pos: 'WR', team: 'FA'}); return res; }; }""", BOGUS)
    page.fill("#v2LgLeaguePaste", text)
    page.wait_for_function("() => !document.getElementById('v2LgParsed').hidden", timeout=20000)
    s = page.evaluate(SNAP)
    if s["state"] != "ok" or "12 teams" not in s["head"]:
        errors.append(f"summary does not say 12 teams: {s['state']!r} {s['head']!r}")
    got = [(t["name"], t["count"]) for t in s["teams"]]
    want = [(n, c) for n, c in expect]
    if [n for n, _ in got] != [n for n, _ in want]:
        errors.append(f"team names {got} != {want}")
    short = [(g, w) for g, w in zip(got, want) if g[1] < w[1] - 3]
    if short or not all(c > 0 for _, c in got):
        errors.append(f"roster sizes far below the pasted rosters: {short}")
    if "No team is marked as yours" not in s["mine"]:
        errors.append(f"no 'yours' notice before a team is marked: {s['mine']!r}")
    if BOGUS not in s["text"] or "not matched" not in s["text"]:
        errors.append("the unmatched line is not listed")
    if "could not be matched" not in s["miss"]:
        errors.append(f"unmatched summary missing: {s['miss']!r}")
    # Marking a team updates which team is called yours.
    page.evaluate("""() => { const W = window.TradeValueWorkspace; const ws = W.store.get();
      W.store.replace(W.ops.setMyTeam(ws, ws.teams[3].id), 'other'); }""")
    page.wait_for_timeout(200)
    s = page.evaluate(SNAP)
    if want[3][0] not in s["mine"] or not any("your team" in t["text"] and t["name"] == want[3][0] for t in s["teams"]):
        errors.append(f"marked team not shown as yours: {s['mine']!r}")
    # A paste with no teams: a plain error.
    page.click("#v2LgParsedClose")
    page.fill("#v2LgLeaguePaste", "")
    page.evaluate("""() => { const t = document.getElementById('v2LgLeaguePaste'); const data = new DataTransfer();
      data.setData('text', 'League Rosters\\nnothing useful here\\n'.repeat(30));
      t.dispatchEvent(new ClipboardEvent('paste', {clipboardData: data, bubbles: true, cancelable: true})); }""")
    page.wait_for_function("() => !document.getElementById('v2LgParsed').hidden", timeout=10000)
    s = page.evaluate(SNAP)
    if s["state"] != "error" or "No teams found" not in s["error"] or s["teams"]:
        errors.append(f"a bad paste did not show a plain error: {s}")
    page.close()
    return errors


def run_checks(overrides=None):
    with browser_on_build() as (browser, base):
        return check(browser, base, overrides)


class LeagueParsedRenderTest(unittest.TestCase):
    def test_summary_after_paste(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        league = source("league.js")
        broken = {
            "summary never shown": league.replace('showParsed({teams: parsed, skipped, source: "Read"});', "", 1),
            "unmatched lines dropped": league.replace("unmatched: item.missed, unsure: item.unsure}", "unmatched: [], unsure: item.unsure}", 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, league, f"mutation anchor for {name!r} is stale")
                try:
                    caught = run_checks({"league.js": body})
                except Exception as exc:   # a broken build that never shows the summary times out: that is a catch
                    caught = [f"raised {type(exc).__name__}"]
                self.assertNotEqual(caught, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
