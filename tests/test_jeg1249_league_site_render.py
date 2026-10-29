"""JEG-1249: the league page with the bench corrections, provenance and the Compare handoff, in a browser.

The USO rosters from tests/fixtures/league_levels/uso.json (12 teams, Yahoo, pulled 2026-10-29) on the built page.

  test_levels_need_a_clean_source_observation: the league's own rosters set the bench when every team's roster was
    read from a source with a known zero unmatched count. A paste is read as the team's whole roster (Jeremy,
    2026-10-29), so pasted rosters set the bench and the note says so. One team whose page left its bench out, one whose
    unmatched count was never recorded, or one never read from a page keeps the standard bench and says why.
  test_paste_transitions_on_the_page: the team box itself, not the helper. A duplicate paste changes nothing; an append
    keeps an unknown count unknown and the observation time where it was; a team page paste is a new observation; a
    "Yes, add" for a player another team holds keeps the count; a removal moves only the edit time.
  test_league_to_compare_journey: with the standard bench (one team's bench left out), JSN's trades are on the
    table, an equal and an unequal trade open in Compare a trade with the same players and the same DDF Value for every
    player, and the saved league is byte-identical after the round trip. A team with an unpriced player and a kicker
    renders without errors. With pasted rosters setting the bench, the handoff is held and says so.
  test_league_rosters_switch: "Use league rosters" is grayed out with one team, on by default once the league
    qualifies, switches to the standard bench (and Compare links) when turned off, and keeps that choice after a reload.

Needs Chromium (Playwright). Skips locally without it; CI sets RENDER_TESTS_REQUIRED.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests import _render_env
from tests._league_render import browser_on_build, open_page

ROOT = Path(__file__).resolve().parents[1]
USO = ROOT / "tests" / "fixtures" / "league_levels" / "uso.json"


def uso() -> dict:
    return json.loads(USO.read_text(encoding="utf-8"))


# Seed the league with each team's provenance: prov is one record for every team, with per-team overrides by index.
SEED = """([teams, mine, prov, per, extra]) => {
  const W = window.TradeValueWorkspace, C = window.TradeValueCurveControls;
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const now = Date.now();
  const stamp = p => ({...p, observedAt: p.observedAt === 'now' ? now : p.observedAt, editedAt: p.editedAt === 'now' ? now : p.editedAt});
  let ws = W.newWorkspace({name: 'USO'});
  teams.forEach((t, i) => {
    const entries = t.players.filter(p => p.key).map(p => { const row = byKey.get(p.key); return {key: p.key, name: row ? row.name : p.name, pos: p.pos, slot: p.slot}; })
      .concat((extra && extra[i]) || []);
    ws = W.ops.addTeam(ws, 'Team ' + t.id, {entries, provenance: stamp((per && per[i]) || prov)});
  });
  const m = teams.findIndex(t => t.id === mine);
  if (m >= 0) ws = W.ops.setMyTeam(ws, ws.teams[m].id);
  W.store.replace(ws, 'replace');
  return ws.teams.map(t => t.id);
}"""

STATE = """() => { const n = document.getElementById('v2LgLevelsNote'); const res = window.TradeValueLeague.ui.result;
  const sw = document.getElementById('v2LgUseLeague');
  return {note: n ? n.textContent : null, rows: res ? res.rows.length : 0,
    switch: sw ? {checked: sw.checked, disabled: sw.disabled} : null}; }"""

PROV = "([i]) => JSON.parse(JSON.stringify(window.TradeValueWorkspace.store.get().teams[i]))"
SAVED = "() => window.TradeValueWorkspace.serialize(window.TradeValueWorkspace.store.get())"

# Paste text into team i's own box, the way a reader's paste arrives (input event on the textarea).
PASTE = """([i, text]) => { const ws = window.TradeValueWorkspace.store.get(); const id = ws.teams[i].id;
  const box = document.getElementById(`v2LgBody-${id}-in`); box.value = text; box.dispatchEvent(new Event('input', {bubbles: true}));
  const panel = document.getElementById(`v2LgBody-${id}-panel`); return panel ? panel.textContent : null; }"""

YES = """([i, name]) => { const id = window.TradeValueWorkspace.store.get().teams[i].id;
  const b = document.querySelector(`#v2LgBody-${id}-panel .v2-find-confirm[aria-label="Yes, add ${name}"]`); if (!b) return null; b.click();
  return document.getElementById(`v2LgBody-${id}-panel`).textContent; }"""

REMOVE = """([i]) => { const id = window.TradeValueWorkspace.store.get().teams[i].id;
  const b = document.querySelector(`#v2LgBody-${id} .v2-lg-row button`); if (!b) return false; b.click(); return true; }"""

# The trades the page found, with each player's DDF Value as the league page priced it.
ROWS = """(jsn) => { const rows = window.TradeValueLeague.ui.result.rows;
  const side = list => list.map(p => [String(p.player_key), p.values.ddf_value]);
  const pack = r => r && {id: r.id, give: side(r.give), get: side(r.receive), opponentId: r.opponentId, throwIns: (r.addedThrowIns || []).map(t => String(t.row.player_key))};
  const thrown = r => (r.addedThrowIns || []).length > 0;
  return {count: rows.length, jsn: rows.filter(r => r.give.some(p => String(p.player_key) === jsn)).length,
    equal: pack(rows.find(r => !thrown(r))), unequal: pack(rows.find(thrown))}; }"""

# Open a trade's details row and read its handoff: the Compare link, or the hold.
PICK = """([id]) => { const b = document.querySelector(`[data-details-for="${id}"]`);
  if (!b) return false; if (b.getAttribute('aria-expanded') !== 'true') b.click(); return true; }"""
HANDOFF = """() => { const panel = document.querySelector('.v2-lg-detail-body'); const a = panel && panel.querySelector('a[href^="#compare-trade"]');
  const held = panel && panel.querySelector('[data-hold="league-pricing"]');
  return {href: a ? a.getAttribute('href') : null, held: held ? held.textContent : null}; }"""

COMPARE = """() => { const v = window.TradeValueV2.compare(); if (!v || !v.ready) return null;
  const side = rows => rows.map(r => [String(r.player_key), r.values.ddf_value]);
  return {give: side(v.giveRows), get: side(v.receiveRows)}; }"""

JSN = """() => { const r = window.TradeValueCurveControls.getAllRows().find(x => /Smith-Njigba/.test(x.name)); return r ? String(r.player_key) : null; }"""

WHOLE = {"unresolved": 0, "observedAt": "now", "editedAt": "now", "coverage": "whole_roster"}
PASTED = {"unresolved": 0, "observedAt": "now", "editedAt": "now", "coverage": "unknown"}   # any paste today


def settle(page):
    page.wait_for_timeout(400)
    page.wait_for_function("() => window.TradeValueLeague && !window.TradeValueLeague.ui.running && !window.TradeValueLeague.ui.timer", timeout=600000)
    page.wait_for_timeout(200)


def setUpModule():
    _render_env.ensure_built()


class LeagueSiteTest(unittest.TestCase):
    def setUp(self):
        self.fx = uso()
        self.teams = self.fx["league"]["teams"]
        self.problems = []

    def seed(self, page, prov, per=None, extra=None, mine="fixture"):
        keyed = lambda d: {str(k): v for k, v in (d or {}).items()}   # Playwright passes string keys only
        page.evaluate(SEED, [self.teams, self.fx["mine"] if mine == "fixture" else mine, prov, keyed(per), keyed(extra)])
        settle(page)
        return page.evaluate(STATE)

    def handoff(self, page, row_id):
        self.assertTrue(page.evaluate(PICK, [row_id]), f"no Details button for {row_id}")
        page.wait_for_function("() => { const p = document.querySelector('.v2-lg-detail-body');"
                               " return p && p.querySelector('a[href^=\"#compare-trade\"], [data-hold=\"league-pricing\"]'); }", timeout=60000)
        return page.evaluate(HANDOFF)

    def open_compare(self, page, href, trade):
        page.evaluate("(h) => { location.hash = h; }", href)
        want = [k for k, _ in trade["give"]]
        page.wait_for_function("(want) => { const v = window.TradeValueV2.compare(); return document.title.startsWith('Compare a trade') && v && v.ready"
                               " && v.giveRows.map(r => String(r.player_key)).join() === want.join(); }", arg=want, timeout=60000)
        cmp = page.evaluate(COMPARE)
        for side in ("give", "get"):
            self.assertEqual([k for k, _ in cmp[side]], [k for k, _ in trade[side]], side)
            for (k, a), (_, b) in zip(trade[side], cmp[side]):
                self.assertAlmostEqual(a, b, places=9, msg=f"{side} {k}: league {a}, Compare {b}")

    def test_levels_need_a_clean_source_observation(self):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[levels] ")
            settle(page)
            whole = self.seed(page, WHOLE)
            self.assertTrue(whole["note"].startswith("Priced with your league's rosters"), whole["note"])
            # Jeremy, 2026-10-29: a paste is read as the team's whole roster (coverage unproven doesn't block), and the note says so.
            self.assertEqual(whole["switch"], {"checked": True, "disabled": False})
            pasted = self.seed(page, PASTED)
            self.assertTrue(pasted["note"].startswith("Priced with your league's rosters"), pasted["note"])
            self.assertIn("Each team's pasted roster is read as its whole roster", pasted["note"])
            self.assertEqual(pasted["switch"], {"checked": True, "disabled": False})
            cases = {
                "bench left out": ({**WHOLE}, {"3": {**WHOLE, "coverage": "bench_omitted"}}, "a pasted page left a team's bench out"),
                "unknown count": ({**WHOLE}, {"5": {**WHOLE, "unresolved": None}}, "unmatched players were not recorded"),
                "never observed": ({**WHOLE}, {"2": {"unresolved": 0, "observedAt": None, "editedAt": "now", "coverage": "whole_roster"}},
                                   "was not read from a site page"),
            }
            for name, (prov, per, reason) in cases.items():
                with self.subTest(case=name):
                    got = self.seed(page, prov, per)
                    self.assertTrue(got["note"].startswith("Priced with the standard bench"), got["note"])
                    self.assertIn(reason, got["note"])
                    self.assertEqual(got["switch"], {"checked": False, "disabled": True}, "the switch is grayed out until the league qualifies")
        self.assertEqual(self.problems, [])

    def test_league_rosters_switch(self):
        # Jeremy, 2026-10-29: "default to not using league specifics unless the rosters are filled in, and give the user
        # visibility to that a toggle with a grayed out use of league specifics until criteria are met".
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[switch] ")
            settle(page)
            one = self.seed_teams(page, self.teams[:1])
            self.assertEqual(one["switch"], {"checked": False, "disabled": True})
            self.assertIn("once every team in your league is loaded", one["note"])
            on = self.seed(page, PASTED)
            self.assertEqual(on["switch"], {"checked": True, "disabled": False})
            page.click("#v2LgUseLeague")
            settle(page)
            off = page.evaluate(STATE)
            self.assertEqual(off["switch"], {"checked": False, "disabled": False})
            self.assertEqual(off["note"], "Priced with the standard bench: league rosters are switched off.")
            self.assertIs(page.evaluate("() => window.TradeValueWorkspace.store.get().ui.leagueRosters"), False)
            # Off: the league page prices like Compare a trade, so its trades open there again.
            first = page.evaluate("() => window.TradeValueLeague.ui.result.rows[0].id")
            hand = self.handoff(page, first)
            self.assertIsNone(hand.get("held"))
            self.assertTrue(hand.get("href"))
            # The choice is saved with the league.
            page.wait_for_timeout(1500)
            page.reload(wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=60000)
            settle(page)
            self.assertEqual(page.evaluate(STATE)["switch"], {"checked": False, "disabled": False})
            page.click("#v2LgUseLeague")
            settle(page)
            back = page.evaluate(STATE)
            self.assertEqual(back["switch"], {"checked": True, "disabled": False})
            self.assertTrue(back["note"].startswith("Priced with your league's rosters"), back["note"])
        self.assertEqual(self.problems, [])

    def seed_teams(self, page, teams):
        page.evaluate(SEED, [teams, self.fx["mine"], PASTED, {}, {}])
        settle(page)
        return page.evaluate(STATE)

    def test_paste_transitions_on_the_page(self):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[paste] ")
            settle(page)
            t0 = page.evaluate("() => Date.now() - 3600 * 1000")
            observed = {**WHOLE, "observedAt": t0, "editedAt": t0}
            self.seed(page, observed, {1: {**observed, "unresolved": None}})
            names = lambda i, n: [e["name"] for e in page.evaluate(PROV, [i])["entries"]][:n]

            # A duplicate paste: nothing added, nothing left out. The saved league does not change at all.
            before = page.evaluate(SAVED)
            page.evaluate(PASTE, [2, "\n".join(names(2, 3))])
            settle(page)
            self.assertEqual(page.evaluate(SAVED), before, "a duplicate paste changed the saved league")

            # An append onto a team whose unmatched count is unknown: the count stays unknown, the observation stays put.
            have = {e["key"] for t in self.teams for e in t["players"] if e.get("key")}
            free = page.evaluate("(have) => window.TradeValueCurveControls.getAllRows().filter(r => !have.includes(String(r.player_key)) && r.pos === 'WR')"
                                 ".sort((a, b) => b.values.ddf_value - a.values.ddf_value)[0].name", sorted(have))
            # Four names and one junk line: a name list (80% names), so an append, not a team page.
            page.evaluate(PASTE, [1, "\n".join(names(1, 3) + [free, "Notaplayer Xyzzy"])])
            settle(page)
            t1 = page.evaluate(PROV, [1])
            self.assertIn(free, [e["name"] for e in t1["entries"]])
            self.assertIsNone(t1["provenance"]["unresolved"], "an append made an unknown count known")
            self.assertEqual(t1["provenance"]["observedAt"], t0, "an append counted as a source observation")
            self.assertGreater(t1["provenance"]["editedAt"], t0)

            # A team page pasted into team 2 is a new observation. JSN (on team 0) comes in as an unsure initial match.
            jsn_line = "WR J. Smith-Njigba SEA"
            own = [f"{e['pos']} {e['name']}" for e in page.evaluate(PROV, [2])["entries"] if e["pos"] in ("QB", "RB", "WR", "TE")][:8]
            page.evaluate(PASTE, [2, "\n".join(own + [jsn_line])])
            settle(page)
            t2 = page.evaluate(PROV, [2])
            self.assertGreater(t2["provenance"]["observedAt"], t0, "a team page paste is a source observation")
            self.assertEqual(t2["provenance"]["coverage"], "unknown", "a team page does not attest every seat")
            count = t2["provenance"]["unresolved"]
            self.assertGreaterEqual(count, 1)
            # "Yes, add" for a player another team holds: rejected, and the count stays.
            said = page.evaluate(YES, [2, "Jaxon Smith-Njigba"])
            self.assertIn("already on a roster", said or "")
            settle(page)
            t2b = page.evaluate(PROV, [2])
            self.assertEqual(t2b["provenance"]["unresolved"], count, "a rejected match decremented the count")
            self.assertEqual(t2b["entries"], t2["entries"])
            self.assertEqual(t2b["provenance"]["settled"], [])

            # A removal is a local edit: the observation time stays.
            self.assertTrue(page.evaluate(REMOVE, [3]))
            settle(page)
            t3 = page.evaluate(PROV, [3])
            self.assertEqual(t3["provenance"]["observedAt"], t0)
            self.assertGreater(t3["provenance"]["editedAt"], t0)
        self.assertEqual(self.problems, [])

    def test_league_to_compare_journey(self):
        with browser_on_build() as (browser, base):
            page = open_page(browser, base, errors=self.problems, tag="[journey] ")
            settle(page)
            jsn = page.evaluate(JSN)
            self.assertIsNotNone(jsn)
            mine_i = next(i for i, t in enumerate(self.teams) if t["id"] == self.fx["mine"])
            on_mine = any(p.get("key") == jsn for p in self.teams[mine_i]["players"])
            # Missing and unpriced data: a player the engine has no row for and a kicker, on another team.
            extra = {4: [{"key": "999999", "name": "Unpriced Player", "pos": "WR"}, {"key": "x:K:Kicker", "name": "Some Kicker", "pos": "K"}]}
            # The standard bench: one team's page left its bench out (a real blocker).
            got = self.seed(page, PASTED, per={0: {**PASTED, "coverage": "bench_omitted"}}, extra=extra)
            self.assertTrue(got["note"].startswith("Priced with the standard bench"), got["note"])
            chip = page.evaluate("() => [...document.querySelectorAll('.v2-find-noteval')].map(n => n.textContent)")
            self.assertIn("Not in this week's values", chip)
            rows = page.evaluate(ROWS, jsn)
            self.assertGreater(rows["count"], 0)
            # Recorded, not asserted: whether a JSN trade qualifies depends on the values and the fit rules (JEG-1240's
            # contract checks that the search keeps every qualified candidate).
            print(f"\n[journey] standard bench: {rows['count']} trades, {rows['jsn']} send JSN (JSN on his team: {on_mine})")
            saved = page.evaluate(SAVED)
            for label in ("equal", "unequal"):
                r = rows[label]
                self.assertIsNotNone(r, f"no {label} trade on the table")
                with self.subTest(trade=label):
                    page.goto(base + "#find-league", wait_until="networkidle")
                    settle(page)
                    hand = self.handoff(page, r["id"])
                    self.assertIsNone(hand.get("held"))
                    self.assertTrue(hand.get("href"), hand)
                    self.open_compare(page, hand["href"], r)
                    self.assertEqual(page.evaluate(SAVED), saved, "opening Compare changed the saved league")
                    if label == "unequal":
                        # The core without its throw-in: a true unequal package, same players, same values.
                        drop = set(r["throwIns"])
                        core = {s: [p for p in r[s] if p[0] not in drop] for s in ("give", "get")}
                        self.assertNotEqual(len(core["give"]), len(core["get"]), r)
                        href = "#compare-trade?give=" + ",".join(k for k, _ in core["give"]) + "&get=" + ",".join(k for k, _ in core["get"])
                        page.goto(base + "#find-league", wait_until="networkidle")
                        settle(page)
                        self.open_compare(page, href, core)
                        self.assertEqual(page.evaluate(SAVED), saved)

            # With the league's rosters setting the bench, the handoff is held, and says why.
            page.goto(base + "#find-league", wait_until="networkidle")
            settle(page)
            got = self.seed(page, PASTED)
            self.assertTrue(got["note"].startswith("Priced with your league's rosters"), got["note"])
            lv = page.evaluate(ROWS, jsn)
            print(f"[journey] league rosters: {lv['count']} trades, {lv['jsn']} send JSN")
            first = page.evaluate("() => window.TradeValueLeague.ui.result.rows[0].id")
            hand = self.handoff(page, first)
            self.assertIsNone(hand.get("href"), "a league-priced trade still links to Compare's standard bench")
            self.assertIn("prices with the standard bench", hand.get("held") or "")
            self.assertEqual(page.evaluate("() => document.querySelectorAll('a[href^=\"#compare-trade\"]').length"), 0)
        self.assertEqual(self.problems, [])


if __name__ == "__main__":
    unittest.main()
