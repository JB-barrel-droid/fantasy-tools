"""JEG-1273: the league checks list on the league page, in a browser.

Jeremy, 2026-10-29: "one league-wide problems list (unmatched lines, short or over teams, players on two teams, missing
kickers or defenses), each linking to its team."

A clean synthetic league fills the page's default settings exactly: 12 teams, each with 2 QB, 5 RB, 5 WR, 2 TE, a kicker
and a defense (16 players for QB 1, RB 2, WR 2, TE 1, FLEX 1, BN 7, K 1, DEF 1), every roster read from a pasted page with
nothing unmatched. It shows "every team is loaded and checks out". Then one problem at a time, each with its exact text,
its team link (which opens and focuses that team) and, where it is a reason the "Use league rosters" switch gives, the
switch grayed out. Short or over teams and missing kickers or defenses are checks only: the switch stays on.
A copy of league.js without the kicker/defense check fails the kicker case. On a phone (390, 360, 320 px) the list causes
no sideways scroll and every Open link is a 44 px target.

Needs Chromium (Playwright). Skips locally without it; CI sets RENDER_TESTS_REQUIRED.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build, open_page

ROOT = Path(__file__).resolve().parents[1]

# Build the clean league from the page's own rows and seed it; tweak(teams) edits it first.
SEED = """([tweak, prov, per]) => {
  const W = window.TradeValueWorkspace, C = window.TradeValueCurveControls;
  const rows = C.getAllRows().filter(r => r.values && Number.isFinite(r.values.ddf_value)).sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  const take = {QB: 2, RB: 5, WR: 5, TE: 2};
  const pool = Object.fromEntries(Object.keys(take).map(p => [p, rows.filter(r => r.pos === p)]));
  const teams = Array.from({length: 12}, (_, i) => ({name: `Team ${i + 1}`, entries: Object.entries(take).flatMap(([p, n]) =>
    pool[p].splice(0, n).map(r => ({key: String(r.player_key), name: r.name, pos: r.pos})))
    .concat([{key: `x:K:K${i + 1}`, name: `Kicker ${i + 1}`, pos: 'K'}, {key: `x:DEF:D${i + 1}`, name: `Defense ${i + 1}`, pos: 'DEF'}])}));
  const free = rows.filter(r => r.pos === 'WR' && !teams.some(t => t.entries.some(e => e.key === String(r.player_key))))[0];
  const now = Date.now();
  const stamp = p => ({...p, observedAt: p.observedAt === 'now' ? now : p.observedAt, editedAt: now});
  const edited = new Function('teams', 'free', tweak)(teams, {key: String(free.player_key), name: free.name, pos: free.pos}) || teams;
  let ws = W.newWorkspace({name: 'Checks'});
  edited.forEach((t, i) => { ws = W.ops.addTeam(ws, t.name, {entries: t.entries, provenance: stamp((per && per[i]) || prov)}); });
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  W.store.replace(ws, 'replace');
  return ws.teams.map(t => t.id);
}"""

STATE = """() => { const box = document.getElementById('v2LgProblems'); const sw = document.getElementById('v2LgUseLeague');
  return {state: box.dataset.state, hidden: box.hidden, ready: (document.getElementById('v2LgProblemsReady') || {}).textContent || null,
    items: [...box.querySelectorAll('li')].map(li => ({kind: li.dataset.kind, text: li.querySelector('span').textContent,
      links: [...li.querySelectorAll('.v2-lg-problem-open')].map(b => b.dataset.teamId)})),
    switch: sw ? {checked: sw.checked, disabled: sw.disabled} : null}; }"""

OPEN = """(id) => { const b = document.querySelector(`#v2LgProblemsList .v2-lg-problem-open[data-team-id="${id}"]`); b.click();
  const li = document.querySelector(`#v2LgTeams [data-team-id="${id}"]`);
  return {expanded: li.querySelector('.v2-lg-toggle').getAttribute('aria-expanded'), focused: document.activeElement === li.querySelector('.v2-lg-name')}; }"""

PASTED = {"unresolved": 0, "observedAt": "now", "coverage": "unknown"}
KICKER_CHECK = 'if (missing.length) add("kicker_defense", `no ${missing.join(" or ")}.`);'


def settle(page):
    page.wait_for_timeout(400)
    page.wait_for_function("() => window.TradeValueLeague && !window.TradeValueLeague.ui.running && !window.TradeValueLeague.ui.timer", timeout=600000)
    page.wait_for_timeout(200)


def setUpModule():
    _render_env.ensure_built()


class LeagueProblemsTest(unittest.TestCase):
    def seed(self, page, tweak="", per=None):
        ids = page.evaluate(SEED, [tweak, PASTED, {str(k): v for k, v in (per or {}).items()}])
        settle(page)
        return ids, page.evaluate(STATE)

    def only(self, got, kind):
        items = [i for i in got["items"] if i["kind"] == kind]
        self.assertEqual(len(items), 1, got["items"])
        return items[0]

    def test_problems_list(self):
        problems = []
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=problems, tag="[problems] ")
            settle(page)
            ids, clean = self.seed(page)
            self.assertEqual(clean["state"], "ready", clean["items"])
            self.assertEqual(clean["ready"], "League checks: every team is loaded and checks out.")
            self.assertEqual(clean["switch"], {"checked": True, "disabled": False})

            cases = [
                # (name, tweak, per-team provenance, kind, team index or None, exact text, switch grayed?)
                ("unmatched", "", {2: {**PASTED, "unresolved": 2}}, "unmatched", 2,
                 "Team 3: 2 pasted players not matched yet. Open the team to add them.", True),
                ("short", "teams[3].entries.pop();", None, "spots", 3, "Team 4: 15 of 16 roster spots filled.", False),
                ("over", "teams[4].entries.push(free);", None, "spots", 4, "Team 5: 1 over its 16 roster spots.", False),
                ("kicker", "teams[6].entries = teams[6].entries.filter(e => e.pos !== 'K');", None, "kicker_defense", 6,
                 "Team 7: no kicker.", False),
                ("kicker and defense", "teams[6].entries = teams[6].entries.filter(e => e.pos !== 'K' && e.pos !== 'DEF');", None,
                 "kicker_defense", 6, "Team 7: no kicker or defense.", False),
                ("bench left out", "", {7: {**PASTED, "coverage": "bench_omitted"}}, "bench_omitted", 7,
                 "Team 8: the pasted page left the bench out. Paste the team page with the bench shown.", True),
                ("count not recorded", "", {8: {**PASTED, "unresolved": None}}, "unrecorded", 8,
                 "Team 9: unmatched players weren't recorded (an older save or a shared link). Paste the roster again.", True),
                ("not read", "", {9: {"unresolved": 0, "observedAt": None, "coverage": "unknown"}}, "not_read", 9,
                 "Team 10: not read from a site page (added by hand or from a link). Paste the team page.", True),
                ("stale", "", {10: {**PASTED, "observedAt": 1}}, "stale", 10, "Team 11: roster is more than 7 days old. Paste it again.", True),
                ("team missing", "teams.pop();", None, "team_count", None, "League settings have 12 teams; 11 are loaded.", True),
            ]
            for name, tweak, per, kind, team, text, grayed in cases:
                with self.subTest(case=name):
                    ids, got = self.seed(page, tweak, per)
                    self.assertEqual(got["state"], "problems")
                    item = self.only(got, kind)
                    self.assertEqual(item["text"], text)
                    self.assertEqual(item["links"], [] if team is None else [ids[team]])
                    self.assertEqual(got["switch"]["disabled"], grayed, f"{name}: the switch and the list disagree")
                    if team is not None:
                        self.assertEqual(page.evaluate(OPEN, ids[team]), {"expanded": "true", "focused": True})

            # A player on two teams: one item, a link to each team, and the over count on the second team.
            ids, got = self.seed(page, "teams[5].entries.push(teams[0].entries[0]);")
            two = self.only(got, "two_teams")
            self.assertRegex(two["text"], r"^.+ is on Team 1 and Team 6\.$")
            self.assertEqual(two["links"], [ids[0], ids[5]])
            self.assertTrue(got["switch"]["disabled"])
            self.assertEqual(self.only(got, "spots")["text"], "Team 6: 1 over its 16 roster spots.")
            # Teams in page order, then kind.
            ids, got = self.seed(page, "teams[1].entries.pop(); teams[1].entries = teams[1].entries.filter(e => e.pos !== 'DEF');",
                                 {1: {**PASTED, "unresolved": 1}, 0: {**PASTED, "coverage": "bench_omitted"}})
            self.assertEqual([i["kind"] for i in got["items"]], ["bench_omitted", "unmatched", "spots", "kicker_defense"])
        self.assertEqual(problems, [])

    def test_phone(self):
        # 390, 360 and 320 px: no sideways scroll, every Open link at least 44 px tall.
        with browser_on_build() as (browser, base):
            for width in (390, 360, 320):
                with self.subTest(width=width):
                    page = open_page(browser, base, width=width, height=800)
                    settle(page)
                    self.seed(page, "teams[5].entries.push(teams[0].entries[0]); teams[6].entries.pop();",
                              {2: {**PASTED, "unresolved": 3}, 7: {**PASTED, "coverage": "bench_omitted"}})
                    self.assertLessEqual(page.evaluate("() => document.documentElement.scrollWidth - innerWidth"), 0)
                    small = page.evaluate("() => [...document.querySelectorAll('#v2LgProblems button')]"
                                          ".map(b => b.getBoundingClientRect().height).filter(h => h < 43.5)")
                    self.assertEqual(small, [])
                    page.context.close()

    def test_dropping_a_check_fails(self):
        source = (ROOT / "app" / "v2" / "league.js").read_text(encoding="utf-8")
        self.assertIn(KICKER_CHECK, source, "mutation anchor is stale")
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, overrides={"league.js": source.replace(KICKER_CHECK, "", 1)})
            settle(page)
            _, got = self.seed(page, "teams[6].entries = teams[6].entries.filter(e => e.pos !== 'K');")
            # The team is still one short; only the kicker item is gone.
            self.assertEqual([i["kind"] for i in got["items"]], ["spots"], "without the check the missing kicker should go unreported")


if __name__ == "__main__":
    unittest.main()
