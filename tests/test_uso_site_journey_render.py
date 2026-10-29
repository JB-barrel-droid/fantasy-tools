"""JEG-1240: the USO-shape league journey, from the league page to Compare a trade and back, on the real site.

The league: tests/fixtures/uso_site_journey/league.json, 12 teams, half PPR, QB 1, RB 2, WR 3, TE 1, W/R/T 1, BN 5, K, DEF.
Only the shape is USO's (recorded in #1105 from the league settings, 2026-10-29). The rosters are a synthetic snake draft
of real player keys with Jaxon Smith-Njigba (3247) on the user's team; no USO roster, name or note is in it. Values are
whatever the built page publishes for the week it is pinned to, never frozen here.

Two layers:

  UsoJourneyContractTest runs tests/node/uso_site_journey_contract.cjs on app/v2 (no browser): both sides' starters
  and bench by position, JSN discoverable in the uncapped search (every qualified candidate kept, at least one sends
  JSN), the exact selected packages (an equal one, a throw-in one and an explicit 2-for-1), the row gains equal to the
  lineup math, the Compare link and the pair link carrying the same rosters, package, values and gains, and an
  unavailable value staying unavailable. test_contract_catches_dropped_context serves three broken copies (the search
  capped at 10, the Compare link without its opponent, the pair link without its opponent) and requires each to fail
  in the named check with the named reason.

  UsoSiteJourneyRenderTest drives the built page in Chromium. It seeds the league, reads the opportunities the page
  found, requires JSN rows, picks an equal and a throw-in candidate the page itself found, opens each from the address
  (?trade=) and after a reload, reads what the league page shows (each player's DDF Value, both teams' starters before
  and change, the rosters, the scoring, teams and roster, the value basis, the bench level), follows its own "Open in
  Compare a trade" link, reads what Compare shows, and diffs the two with the contract's diff (one decimal). It then
  reloads Compare and opens Compare's own address in a fresh browser whose saved league has a different "my team",
  and requires the same trade context, not the saved one. test_unequal_deal_keeps_its_package removes the throw-in on
  Compare and requires a true 2-for-1 that keeps its package and lineup math through a reload.
  test_guard_fails_on_a_link_without_get serves league.js with the link's get= dropped and requires the package loss
  to be named.

What this does not assert: that JSN's trades are Natural fits, or that any trade passes a viability gate. It takes the
candidates the page shows.

Expected on main (2026-10-29), reported, not baked in: the league link carries only give= and get=, so Compare picks its
default opponent (team-substituted unless the opponent happens to be Team 02) and cannot draw lineups (gains-missing);
Compare's address carries no rosters, so a reader with another saved "my team" gets a substituted roster. Those are
JEG-1229's to carry (#1086). After #1105 the league page prices from league levels and Compare from the modeled bench,
which this names as level-changed and value-changed. The browser tests are not yet in the Makefile (JEG-1240 handshake).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
LEAGUE = ROOT / "tests" / "fixtures" / "uso_site_journey" / "league.json"
CONTRACT = ROOT / "tests" / "node" / "uso_site_journey_contract.cjs"
TOL = "0.051"   # the page shows one decimal


def node(*args) -> dict:
    out = subprocess.run(["node", str(CONTRACT), *map(str, args)], capture_output=True, text=True, timeout=300, cwd=ROOT)
    if not out.stdout.strip():
        raise AssertionError(f"contract printed nothing: {out.stderr[-2000:]}")
    return json.loads(out.stdout.strip().splitlines()[-1])


def league() -> dict:
    return json.loads(LEAGUE.read_text(encoding="utf-8"))


def differences(origin: dict, dest: dict) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "origin.json", Path(tmp) / "dest.json"
        a.write_text(json.dumps(origin), encoding="utf-8")
        b.write_text(json.dumps(dest), encoding="utf-8")
        return node("diff", a, b, TOL)["differences"]


# ---------- the Node contract on the site's own modules ----------

MUTATIONS = {
    # name: (file, anchor, replacement, failing check, reason the failure must name)
    "search capped at 10": ("opportunities.js", "limit: Infinity,", "limit: 10,",
                            "test_jsn_discoverable_in_the_uncapped_search", "none truncated"),
    "Compare link without its opponent": ("ddf-state.js", 'if (w.theirs) p.push("theirs=" + listToParam(w.theirs));', "",
                                          "test_compare_link_keeps_the_trade_context", "[team-missing]"),
    "pair link without its opponent": ("finder.js", "if (theirs) parts.push(`theirs=${theirs}`);", "",
                                       "test_pair_link_rediscovers_the_exact_package", "[team-substituted]"),
}


class UsoJourneyContractTest(unittest.TestCase):
    def test_contract_passes_on_the_site_modules(self):
        out = node("check", APP, LEAGUE)
        self.assertEqual(out["failures"], [])
        self.assertEqual(len(out["ran"]), 9, out["ran"])
        facts = out["facts"]
        self.assertGreater(facts["candidates"], 0)
        self.assertGreater(facts["jsnCandidates"], 0)

    def test_contract_catches_dropped_context(self):
        for name, (file, anchor, replacement, check, reason) in MUTATIONS.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as tmp:
                app = Path(tmp) / "v2"
                shutil.copytree(APP, app)
                body = (app / file).read_text(encoding="utf-8")
                self.assertIn(anchor, body, f"mutation anchor for {name!r} is stale")
                (app / file).write_text(body.replace(anchor, replacement, 1), encoding="utf-8")
                failures = node("check", app, LEAGUE)["failures"]
                self.assertEqual([f["name"] for f in failures], [check], failures)
                self.assertIn(reason, failures[0]["message"])


# ---------- the journey on the built page ----------

SETTINGS = """(s) => { const C = window.TradeValueCurveControls; C.setScoring(s.scoring, false); C.setTeams(s.teams, false);
  Object.entries(s.roster).forEach(([k, v]) => { if (C.getRosterShape()[k] !== v) C.setRosterSpot(k, v); });
  return C.getRosterShape(); }"""

# Read from the page: the league settings, the value basis and the bench level in force, and one team as the screen
# counts it (priced players by key; K, DEF and players without a row counted, not valued).
COMMON = """
  const C = window.TradeValueCurveControls, F = window.TradeValueFinder;
  const have = new Set(C.getAllRows().map(r => String(r.player_key)));
  const settings = () => { const s = C.getState(); return {scoring: s.scoring, teams: s.teams, roster: C.getRosterShape()}; };
  const basis = () => ((window.DDFOverrides && window.DDFOverrides.shareParams && window.DDFOverrides.shareParams()) || {}).basis || null;
  const side = team => team ? {id: team.id, keys: team.entries.filter(e => !F.isNotEvaluated(e) && have.has(String(e.key))).map(e => String(e.key)).sort(),
    notEvaluated: team.entries.filter(e => F.isNotEvaluated(e) || !have.has(String(e.key))).length} : null;
  const num = t => { const n = parseFloat(String(t || '').replace('−', '-').replace(/,/g, '')); return Number.isFinite(n) ? n : null; };
  const starters = table => { const tr = table && [...table.querySelectorAll('tbody tr')].find(x => x.dataset.total === 'starters' || x.firstChild.textContent === 'Starters');
    return tr ? [...tr.children].map(c => c.textContent) : null; };
"""

CANDIDATES = """(focus) => { const res = window.TradeValueLeague.ui.result; if (!res) return null;
  const rows = res.rows;
  const jsn = rows.filter(r => r.give.some(p => String(p.player_key) === focus));
  const pack = r => r && {id: r.id, opponent: r.opponent, opponentId: r.opponentId,
    give: r.give.map(p => String(p.player_key)), get: r.receive.map(p => String(p.player_key)),
    throwIns: r.addedThrowIns || [], unbalanced: Boolean(r.unbalanced)};
  const equal = jsn.find(r => !(r.addedThrowIns || []).length && !r.unbalanced);
  const thrown = jsn.find(r => (r.addedThrowIns || []).length && !(r.addedThrowIns || []).includes('give:' + focus));
  return {count: rows.length, jsn: jsn.length, opponents: new Set(jsn.map(r => r.opponentId)).size, equal: pack(equal), thrown: pack(thrown)}; }"""

ORIGIN = "([id]) => {" + COMMON + """
  const ws = window.TradeValueWorkspace.store.get();
  const r = window.TradeValueLeague.ui.result.rows.find(x => x.id === id);
  const p = document.getElementById('v2LgOppPanel');
  if (!r || !p || p.dataset.oppId !== id) return {error: `panel for ${id} is not open (open: ${p && p.dataset.oppId})`};
  const values = {};
  r.give.concat(r.receive).forEach(x => { const v = x.values && x.values.ddf_value; values[String(x.player_key)] = {ddf: Number.isFinite(v) ? v : null}; });
  const gain = s => starters(p.querySelector(`[data-side="${s}"] table[data-view="DDF Value"]`));
  const us = gain('Your team'), them = gain('Their team');
  return {settings: settings(), basis: basis(), level: document.getElementById('v2LgLevelCounts') ? 'league' : 'modeled', sources: null,
    mine: side(ws.teams.find(t => t.id === ws.myTeamId)), theirs: side(ws.teams.find(t => t.id === r.opponentId)),
    give: r.give.map(x => String(x.player_key)), get: r.receive.map(x => String(x.player_key)), values,
    gains: {us: us ? {ddf: num(us[3]), ddfBefore: num(us[1])} : null, them: them ? {ddf: num(them[3])} : null}}; }"""

# Compare draws one series per player (the one shown) and DDF-only lineups; Compare has no bench-level marker today,
# so it reads as the modeled bench unless an element says data-bench-level (the hook proposed to JEG-1229).
DEST = "() => {" + COMMON + """
  const ws = window.TradeValueWorkspace.store.get();
  const team = id => ws.teams.find(t => t.id === id) || null;
  const mineSel = document.getElementById('v2CMyTeam'), theirSel = document.getElementById('v2CTheirTeam');
  const listed = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => li.dataset.playerKey);
  const give = listed('v2GivePlayers'), get = listed('v2GetPlayers');
  const values = {};
  give.concat(get).forEach(k => { const li = document.querySelector(`#v2GivePlayers li[data-player-key="${CSS.escape(k)}"], #v2GetPlayers li[data-player-key="${CSS.escape(k)}"]`);
    const v = li && li.querySelector('.v2-trade-value');
    values[k] = v && v.dataset.source === 'ddf_value' ? {ddf: num(v.textContent)} : {ddf: null, shown: v ? v.dataset.source : null}; });
  const card = document.getElementById('v2CConstruction');
  const panels = [...document.querySelectorAll('#v2CConstructionBody .v2-cconstruction-panels > section')];
  const us = card && card.dataset.ready === 'true' ? starters(panels[0] && panels[0].querySelector('table')) : null;
  const them = card && card.dataset.ready === 'true' ? starters(panels[1] && panels[1].querySelector('table')) : null;
  const marker = document.querySelector('#compare-trade [data-bench-level], [data-view="compare-trade"] [data-bench-level]');
  return {settings: settings(), basis: basis(), level: marker ? marker.dataset.benchLevel : 'modeled', sources: null,
    mine: side(team(mineSel && mineSel.value)), theirs: side(team(theirSel && theirSel.value)), give, get, values,
    gains: {us: us ? {ddf: num(us[3]), ddfBefore: num(us[1])} : null, them: them ? {ddf: num(them[3])} : null},
    note: (document.getElementById('v2CRosterStatus') || {}).textContent || '', hash: location.hash}; }"""

# The lineup math Compare should show for the deal on its screen, on the rosters the league page traded between.
EXPECTED = "([mineId, theirId]) => {" + COMMON + """
  const ws = window.TradeValueWorkspace.store.get();
  const byKey = new Map(C.getAllRows().map(r => [String(r.player_key), r]));
  const rows = t => t.entries.map(e => byKey.get(String(e.key))).filter(Boolean);
  const listed = id => [...document.querySelectorAll(`#${id} li[data-player-key]`)].map(li => byKey.get(li.dataset.playerKey)).filter(Boolean);
  const give = listed('v2GivePlayers'), get = listed('v2GetPlayers');
  const mine = ws.teams.find(t => t.id === mineId), theirs = ws.teams.find(t => t.id === theirId);
  const us = F.rosterImpact(rows(mine), give, get, C.getRosterShape(), 'ddf_value');
  const them = F.rosterImpact(rows(theirs), get, give, C.getRosterShape(), 'ddf_value');
  return {us: {ddf: us.starterDelta, ddfBefore: us.before.starterValue}, them: {ddf: them.starterDelta}}; }"""


def _anon(env: dict) -> dict:
    """A different browser has different team ids: compare the rosters by their players."""
    out = json.loads(json.dumps(env))
    for s in ("mine", "theirs"):
        if out.get(s):
            out[s].pop("id", None)
    return out


def _codes(diffs: list[dict], tag: str) -> list[str]:
    return [f"{tag}[{d['code']}] {d['message']}" for d in diffs]


class _Journey:
    def __init__(self, browser, base, overrides=None):
        from tests._league_render import SEED, open_page, wait_opps
        self.browser, self.base, self.overrides = browser, base, overrides
        self.SEED, self.open_page, self.wait_opps = SEED, open_page, wait_opps
        self.fx = league()
        self.errors: list[str] = []

    def page(self, mine=None, context=None):
        page = self.open_page(self.browser, self.base, overrides=self.overrides, errors=self.errors, context=context)
        page.evaluate(SETTINGS, self.fx["settings"])
        page.evaluate(self.SEED, [self.fx, self.fx["myTeamIndex"] if mine is None else mine])
        self.wait_opps(page, timeout=120000)
        return page

    def open_league_pick(self, page, pick) -> None:
        trade = "~".join(map(_quote, [pick["opponent"], ",".join(pick["give"]), ",".join(pick["get"])]))
        page.evaluate("(h) => { location.hash = h; }", f"#find-league?trade={trade}")
        page.reload(wait_until="networkidle")
        page.wait_for_function("() => window.TradeValueLeague && window.TradeValueLeague.ui.ready", timeout=30000)
        self.wait_opps(page, timeout=120000)
        page.wait_for_timeout(300)

    def follow_compare_link(self, page, pick) -> bool:
        """Show the trade's details on the league page and click its own Open in Compare a trade link."""
        page.evaluate("() => { const more = document.getElementById('v2LgOppsAll'); if (more) more.click(); }")
        page.wait_for_timeout(200)
        clicked = page.evaluate("""(id) => { const b = document.querySelector(`[data-details-for="${CSS.escape(id)}"]`);
          if (!b) return false; if (b.getAttribute('aria-expanded') !== 'true') b.click(); return true; }""", pick["id"])
        if not clicked:
            return False
        page.wait_for_timeout(200)
        followed = page.evaluate("""(id) => { const a = [...document.querySelectorAll(`tr[data-detail-for="${CSS.escape(id)}"] a`)].find(x => x.textContent === 'Open in Compare a trade');
          if (!a) return null; const href = a.getAttribute('href'); a.click(); return href; }""", pick["id"])
        if not followed:
            return False
        self.wait_compare(page)
        return True

    @staticmethod
    def wait_compare(page, give=None, get=None):
        """Compare has drawn a trade: its address, the lists (exact counts when given) and the lineup card's verdict."""
        page.wait_for_function("""([g, r]) => { const n = id => document.querySelectorAll(`#${id} li[data-player-key]`).length;
          const card = document.getElementById('v2CConstruction');
          return location.hash.startsWith('#compare-trade') && (g === null ? n('v2GivePlayers') > 0 : n('v2GivePlayers') === g) &&
            (r === null || n('v2GetPlayers') === r) && card && card.dataset.ready !== undefined; }""", arg=[give, get], timeout=30000)
        page.wait_for_timeout(300)


def _quote(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe="")


def journey(browser, base, overrides=None) -> list[str]:
    """Problems found on the journey; [] when every screen carried the same trade context."""
    J = _Journey(browser, base, overrides)
    problems: list[str] = []
    page = J.page()
    focus = J.fx["focus"]["key"]
    found = page.evaluate(CANDIDATES, focus)
    if not found or not found["count"]:
        page.close()
        return ["the league page found no trade opportunities on the USO-shape league"]
    if not found["jsn"]:
        page.close()
        return [f"no opportunity sends {J.fx['focus']['name']} ({found['count']} found): JSN is not discoverable"]
    for label in ("equal", "thrown"):
        pick = found[label]
        if not pick:
            problems.append(f"[{label}] no {label} candidate sends JSN among {found['jsn']}")
            continue
        tag = f"[{label} {pick['id']}] "
        if sorted(pick["give"]) != sorted(pick["id"].split("|")[1].split(",")) or sorted(pick["get"]) != sorted(pick["id"].split("|")[2].split(",")):
            problems.append(f"{tag}row id and package disagree")
        J.open_league_pick(page, pick)
        origin = page.evaluate(ORIGIN, [pick["id"]])
        if origin.get("error"):
            problems.append(f"{tag}league page: {origin['error']} after opening ?trade= and reloading")
            continue
        if not origin["gains"]["us"] or not origin["gains"]["them"]:
            problems.append(f"{tag}league panel shows no starters before/after for a side")
        if not J.follow_compare_link(page, pick):
            problems.append(f"{tag}the league page's Open in Compare a trade link was not there to follow")
            continue
        dest = page.evaluate(DEST)
        problems += _codes(differences(origin, dest), f"{tag}league -> Compare ")
        # Reload Compare: the same trade, not what the page would default to.
        share = page.evaluate("() => location.href")
        page.reload(wait_until="networkidle")
        J.wait_compare(page)
        problems += _codes(differences(origin, page.evaluate(DEST)), f"{tag}Compare reload ")
        # Share: Compare's own address in a fresh browser whose saved league names another team as "my team".
        ctx = browser.new_context(viewport={"width": 1366, "height": 768})
        other = J.page(mine=4, context=ctx)
        other.goto(share, wait_until="networkidle")
        other.reload(wait_until="networkidle")
        try:
            J.wait_compare(other)
            arrived = other.evaluate(DEST)
            problems += _codes(differences(_anon(origin), _anon(arrived)), f"{tag}shared link with other saved state ")
        except Exception as exc:   # the shared link did not rebuild the trade at all
            problems.append(f"{tag}shared link with other saved state did not open the trade: {type(exc).__name__}")
        ctx.close()
    page.close()
    problems += J.errors
    return problems


def unequal_deal(browser, base) -> list[str]:
    """Compare: take the throw-in out of a page-found JSN trade; the 2-for-1 keeps its package and lineup math."""
    J = _Journey(browser, base)
    problems: list[str] = []
    page = J.page()
    found = page.evaluate(CANDIDATES, J.fx["focus"]["key"])
    pick = found and found["thrown"]
    if not pick:
        page.close()
        return ["no throw-in candidate sends JSN, so no explicit unequal deal can be derived"]
    side, key = pick["throwIns"][0].split(":", 1)
    give = [k for k in pick["give"] if not (side == "give" and k == key)]
    get = [k for k in pick["get"] if not (side == "receive" and k == key)]
    if len(give) == len(get):
        page.close()
        return [f"removing {pick['throwIns'][0]} left an equal deal {give} for {get}"]
    J.open_league_pick(page, pick)
    if not J.follow_compare_link(page, pick):
        page.close()
        return ["the league page's Open in Compare a trade link was not there to follow"]
    page.evaluate("""(k) => { const li = document.querySelector(`#v2GivePlayers li[data-player-key="${CSS.escape(k)}"], #v2GetPlayers li[data-player-key="${CSS.escape(k)}"]`);
      li.querySelector('button.v2-remove').click(); }""", key)
    J.wait_compare(page, len(give), len(get))
    for when in ("after removing the throw-in", "after a reload"):
        dest = page.evaluate(DEST)
        if sorted(dest["give"]) != sorted(give) or sorted(dest["get"]) != sorted(get):
            problems.append(f"[unequal {when}] package {dest['give']} for {dest['get']}, wanted {give} for {get}")
        if (dest["theirs"] or {}).get("id") != pick["opponentId"]:
            problems.append(f"[unequal {when}] [team-substituted] Compare shows {(dest['theirs'] or {}).get('id')} as their team, the trade was with {pick['opponent']}")
        want = page.evaluate(EXPECTED, [page.evaluate("() => window.TradeValueWorkspace.store.get().myTeamId"), pick["opponentId"]])
        for s in ("us", "them"):
            got = dest["gains"][s]
            if not got:
                problems.append(f"[unequal {when}] [gains-missing] Compare draws no {s} lineup: {dest['note']}")
                continue
            for v, x in want[s].items():
                if got.get(v) is None or abs(got[v] - x) > float(TOL):
                    problems.append(f"[unequal {when}] [gains-changed] {s} {v} shows {got.get(v)}, lineup math says {round(x, 2)}")
        if when == "after removing the throw-in":
            page.reload(wait_until="networkidle")
            J.wait_compare(page, len(give), len(get))
    page.close()
    return problems + J.errors


class UsoSiteJourneyRenderTest(unittest.TestCase):
    def test_journey_keeps_the_trade_context(self):
        from tests._league_render import browser_on_build
        with browser_on_build() as (browser, base):
            self.assertEqual(journey(browser, base), [])

    def test_unequal_deal_keeps_its_package(self):
        from tests._league_render import browser_on_build
        with browser_on_build() as (browser, base):
            self.assertEqual(unequal_deal(browser, base), [])

    def test_guard_fails_on_a_link_without_get(self):
        from tests._league_render import browser_on_build, source
        body = source("league.js")
        anchor = '&get=${r.receive.map(p => encodeURIComponent(p.player_key)).join(",")}`, text: "Open in Compare a trade"'
        self.assertEqual(body.count(anchor), 2, "mutation anchor is stale")
        broken = body.replace(anchor, '`, text: "Open in Compare a trade"')
        with browser_on_build() as (browser, base):
            try:
                caught = journey(browser, base, {"league.js": broken})
            except Exception as exc:   # Compare never lists the receive side: that is a catch too
                caught = [f"[package-changed] raised {type(exc).__name__}"]
        self.assertTrue(any("[package-changed]" in p for p in caught), caught)


if __name__ == "__main__":
    unittest.main()
