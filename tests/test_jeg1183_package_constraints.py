"""Trade package constraints (JEG-1262, part of JEG-1183): the pure helper in app/v2/trade-package-constraints.js that
checks a set of already chosen trades can happen together and applies them to the rosters. Run under node against the
fixtures in tests/fixtures/jeg1183_package/ (a four-team league, so three counterparties):

  * the fixture package validates, and applyPackage gives exactly the expected final rosters;
  * applyPackage equals applying its trades one after another with applyTrade;
  * every ordering of the (disjoint) package gives the same final roster per team, and an unequal-count package conserves
    every player: each key ends on exactly one roster and team sizes change by received minus given;
  * the negatives each fail with their own error code and no league: duplicate counterparty, duplicate player (across
    trades, within a side, across sides), a player not on the sending roster, a player received twice from the wrong
    team, missing and ambiguous keys, a key held by two teams, unknown, missing and self counterparties, no my team,
    duplicate team ids, an empty trade, and bad shapes;
  * an invalid package is never applied in part: a valid first trade with an invalid second one returns no rosters;
  * inputs are never modified (deep-frozen inputs under strict mode, and a JSON comparison before and after), and the
    output shares no object with the input;
  * x: keys (K, DEF, unmatched players) move like any other key, every moved entry is the roster's own entry unchanged,
    and the values carried on engine rows never reach a roster.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against mutated copies of the helper (the
counterparty check removed, the used-player check removed, membership not checked, partial application on error,
roster entries moved by reference, the engine row moved instead of the roster entry) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HELPER_JS = REPO / "app" / "v2" / "trade-package-constraints.js"
FIXTURES = REPO / "tests" / "fixtures" / "jeg1183_package"

CHECKS = r"""
const P = require(process.argv[1]);
const D = JSON.parse(process.argv[2]);
const fails = [];
const fail = msg => fails.push(msg);
const clone = v => JSON.parse(JSON.stringify(v));
const keysOf = league => Object.fromEntries(league.teams.map(t => [t.id, t.entries.map(e => e.key)]));
const sortedKeysOf = league => Object.fromEntries(league.teams.map(t => [t.id, t.entries.map(e => e.key).slice().sort()]));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const deepFreeze = v => { if (v && typeof v === "object") { Object.values(v).forEach(deepFreeze); Object.freeze(v); } return v; };
const codesOf = res => (res.errors || []).map(e => e.code);
const C = P.CODES;
const L = () => clone(D.league);
const T = () => clone(D.package.trades);

// ---- positive ----
const v = P.validatePackage(L(), T());
if (!v.ok) fail(`fixture package should validate, got ${JSON.stringify(codesOf(v))}`);
const res = P.applyPackage(L(), T());
if (!res.ok) fail(`fixture package should apply, got ${JSON.stringify(codesOf(res))}`);
else {
  if (!same(keysOf(res.league), D.package.expected)) fail(`final rosters ${JSON.stringify(keysOf(res.league))} != expected ${JSON.stringify(D.package.expected)}`);
  if (res.league.myTeamId !== D.league.myTeamId) fail("myTeamId changed");
  if (res.moves.length !== 8) fail(`expected 8 moves, got ${res.moves.length}`);
  // identity conserved: each final entry is the original roster entry, unchanged; no values from engine rows
  const original = new Map(D.league.teams.flatMap(t => t.entries.map(e => [e.key, e])));
  res.league.teams.forEach(t => t.entries.forEach(e => {
    if (!same(e, original.get(e.key))) fail(`entry ${e.key} changed: ${JSON.stringify(e)} vs ${JSON.stringify(original.get(e.key))}`);
    if ("values" in e || "player_key" in e) fail(`entry ${e.key} picked up engine fields`);
  }));
  const allKeys = res.league.teams.flatMap(t => t.entries.map(e => e.key)).sort();
  if (!same(allKeys, [...original.keys()].sort())) fail("players not conserved");
  const def = res.league.teams.find(t => t.entries.some(e => e.key === "x:DEF:GGG"));
  if (!def || def.id !== "team-b") fail("x: DEF did not move to team-b");
  const rookie = res.league.teams.find(t => t.entries.some(e => e.key === "x:WR:unmatched rookie"));
  if (!rookie || rookie.id !== "team-b") fail("unmatched x: player left team-b though nobody traded him");
  // the output shares no object with the input
  const inLeague = L();
  const out = P.applyPackage(inLeague, T());
  out.league.teams[0].entries[0].name = "CHANGED";
  out.league.teams[0].entries.push({key: "zzz", name: "z"});
  if (inLeague.teams[0].entries[0].name === "CHANGED" || inLeague.teams[0].entries.some(e => e.key === "zzz")) fail("output shares objects with the input");
}

// ---- sequential application equals the package ----
let seq = L();
for (const trade of T()) {
  const step = P.applyTrade(seq, trade);
  if (!step.ok) { fail(`sequential step failed: ${JSON.stringify(codesOf(step))}`); break; }
  seq = step.league;
}
if (res.ok && !same(seq, res.league)) fail("applyPackage differs from applying the trades one after another");

// ---- permutations of a disjoint package ----
const perms = xs => xs.length <= 1 ? [xs] : xs.flatMap((x, i) => perms(xs.slice(0, i).concat(xs.slice(i + 1))).map(p => [x].concat(p)));
const base = res.ok ? sortedKeysOf(res.league) : null;
perms([0, 1, 2]).forEach(order => {
  const trades = order.map(i => T()[i]);
  const r = P.applyPackage(L(), trades);
  if (!r.ok) fail(`order ${order} rejected: ${JSON.stringify(codesOf(r))}`);
  else if (!same(sortedKeysOf(r.league), base)) fail(`order ${order} gives different rosters`);
});

// ---- unequal counts: 3-for-1 and 0-for-2 together, sizes move by received minus given ----
const unequal = [
  {opponentId: "team-a", give: ["1001", "1002", "1004"], receive: ["x:K:KKK"]},
  {opponentId: "team-b", give: [], receive: ["3001", "x:WR:unmatched rookie"]},
];
perms([0, 1]).forEach(order => {
  const r = P.applyPackage(L(), order.map(i => clone(unequal[i])));
  if (!r.ok) { fail(`unequal package order ${order} rejected: ${JSON.stringify(codesOf(r))}`); return; }
  const size = id => r.league.teams.find(t => t.id === id).entries.length;
  const was = id => D.league.teams.find(t => t.id === id).entries.length;
  const delta = {"team-mine": 3 - 3, "team-a": 3 - 1, "team-b": -2, "team-c": 0};
  Object.entries(delta).forEach(([id, d]) => { if (size(id) - was(id) !== d) fail(`order ${order}: ${id} size moved ${size(id) - was(id)}, expected ${d}`); });
  const holders = new Map();
  r.league.teams.forEach(t => t.entries.forEach(e => holders.set(e.key, (holders.get(e.key) || []).concat([t.id]))));
  if ([...holders.values()].some(h => h.length !== 1)) fail(`order ${order}: a player ended on two rosters`);
  if (holders.get("x:K:KKK")[0] !== "team-mine" || holders.get("x:WR:unmatched rookie")[0] !== "team-mine") fail(`order ${order}: x: players did not reach my team`);
  if (holders.get("1004")[0] !== "team-a") fail(`order ${order}: 1004 did not reach team-a`);
});

// ---- negatives: each has its own code, no league, nothing applied ----
const neg = (name, league, trades, code) => {
  const before = JSON.stringify([league, trades]);
  const vv = P.validatePackage(league, trades);
  const aa = P.applyPackage(league, trades);
  if (vv.ok || !codesOf(vv).includes(code)) fail(`${name}: validate should fail with ${code}, got ${JSON.stringify(codesOf(vv))}`);
  if (aa.ok || "league" in aa || !codesOf(aa).includes(code)) fail(`${name}: apply should fail with ${code} and no league, got ${JSON.stringify(aa).slice(0, 200)}`);
  if (vv.moves && vv.moves.length) fail(`${name}: invalid package still reports moves`);
  if (JSON.stringify([league, trades]) !== before) fail(`${name}: inputs changed`);
};
const t = T();
neg("duplicate counterparty", L(), [t[0], {opponentId: "team-a", give: ["1004"], receive: ["2001"]}], C.DUPLICATE_COUNTERPARTY);
neg("duplicate player across trades", L(), [t[0], {opponentId: "team-b", give: ["1003"], receive: ["3001"]}], C.DUPLICATE_PLAYER);
neg("duplicate player within a side", L(), [{opponentId: "team-a", give: ["1003", {key: "1003"}], receive: ["2002"]}], C.DUPLICATE_PLAYER);
neg("duplicate player across sides", L(), [{opponentId: "team-a", give: ["1003"], receive: ["2002"]}, {opponentId: "team-b", give: ["2002"], receive: ["3001"]}], C.DUPLICATE_PLAYER);
neg("give not on my roster", L(), [{opponentId: "team-a", give: ["3001"], receive: ["2002"]}], C.NOT_ON_ROSTER);
neg("receive from the wrong team", L(), [{opponentId: "team-a", give: ["1003"], receive: ["4002"]}], C.NOT_ON_ROSTER);
neg("receive a player nobody holds", L(), [{opponentId: "team-a", give: ["1003"], receive: ["9999"]}], C.NOT_ON_ROSTER);
neg("missing key (empty object)", L(), [{opponentId: "team-a", give: [{}], receive: ["2002"]}], C.MISSING_PLAYER_KEY);
neg("missing key (null)", L(), [{opponentId: "team-a", give: [null], receive: ["2002"]}], C.MISSING_PLAYER_KEY);
neg("missing key (blank)", L(), [{opponentId: "team-a", give: ["  "], receive: ["2002"]}], C.MISSING_PLAYER_KEY);
neg("ambiguous key", L(), [{opponentId: "team-a", give: [{key: "1003", player_key: "1004"}], receive: ["2002"]}], C.AMBIGUOUS_PLAYER_KEY);
const twoHolders = L(); twoHolders.teams[3].entries.push({key: "2002", name: "Ray Hotel", pos: "RB"});
neg("key held by two teams", twoHolders, [t[0]], C.DUPLICATE_ROSTER_KEY);
const twiceOnOne = L(); twiceOnOne.teams[1].entries.push({key: "2003", name: "Wade India", pos: "WR"});
neg("key twice on one roster", twiceOnOne, [t[0]], C.DUPLICATE_ROSTER_KEY);
const keyless = L(); keyless.teams[2].entries.push({name: "No Key", pos: "WR"});
neg("roster entry without key", keyless, [t[0]], C.MISSING_ROSTER_KEY);
neg("missing counterparty", L(), [{give: ["1003"], receive: ["2002"]}], C.MISSING_COUNTERPARTY);
neg("unknown counterparty", L(), [{opponentId: "team-z", give: ["1003"], receive: []}], C.UNKNOWN_COUNTERPARTY);
neg("self trade", L(), [{opponentId: "team-mine", give: ["1003"], receive: ["1004"]}], C.SELF_TRADE);
neg("empty trade", L(), [{opponentId: "team-a", give: [], receive: []}], C.EMPTY_TRADE);
neg("bad trade shape", L(), [{opponentId: "team-a", give: "1003", receive: ["2002"]}], C.BAD_TRADE);
neg("trades not an array", L(), {0: t[0]}, C.BAD_PACKAGE);
const noMine = L(); noMine.myTeamId = "team-x";
neg("no my team", noMine, [t[0]], C.NO_MY_TEAM);
const dupTeams = L(); dupTeams.teams.push({id: "team-c", name: "Copy", entries: []});
neg("duplicate team id", dupTeams, [t[0]], C.DUPLICATE_TEAM_ID);
neg("bad league", {teams: "nope"}, [t[0]], C.BAD_LEAGUE);
neg("bad team", (() => { const l = L(); l.teams.push({name: "No id", entries: []}); return l; })(), [t[0]], C.BAD_TEAM);

// ---- no partial application: valid trade 0, invalid trade 1 ----
const partial = P.applyPackage(L(), [t[0], {opponentId: "team-b", give: ["1004"], receive: ["2003"]}]);
if (partial.ok || "league" in partial) fail("a package with one invalid trade was applied");

// ---- mutation: deep-frozen inputs, strict mode throws on any write ----
try {
  const fl = deepFreeze(L());
  const ft = deepFreeze(T());
  const fv = P.validatePackage(fl, ft);
  const fa = P.applyPackage(fl, ft);
  const fs = P.applyTrade(fl, ft[2]);
  if (!fv.ok || !fa.ok || !fs.ok) fail("frozen inputs rejected");
  if (fa.ok && !same(keysOf(fa.league), D.package.expected)) fail("frozen inputs gave different rosters");
} catch (e) { fail(`frozen inputs threw: ${e.message}`); }
const ml = L(); const mt = T(); const mBefore = JSON.stringify([ml, mt]);
P.validatePackage(ml, mt); P.applyPackage(ml, mt); mt.forEach(x => P.applyTrade(ml, x));
if (JSON.stringify([ml, mt]) !== mBefore) fail("inputs changed after validate/apply");

// ---- empty package is a no-op ----
const empty = P.applyPackage(L(), []);
if (!empty.ok || !same(keysOf(empty.league), keysOf(D.league))) fail("an empty package should leave every roster as it was");

console.log(JSON.stringify(fails));
"""

MUTANTS = {
    "counterparty check removed": ("else if (counterparties.has(opp))", "else if (false)"),
    "used-player check removed": ("if (used.has(key)) {", "if (false) {"),
    "membership not checked": ("if (from === null || !teams.has(from) || !held || held.teamId !== from) {", "if (from === null || !teams.has(from) || !held) {"),
    "partial application on error": ("if (!check.ok) return {ok: false, errors: check.errors};", "if (!check.ok) return {ok: false, errors: check.errors, league: {myTeamId: league.myTeamId, teams: league.teams}};"),
    "entries moved by reference": ("const teams = league.teams.map(team => ({...clone(team), id: asKey(team.id)}));", "const teams = league.teams.map(team => ({...team, id: asKey(team.id)}));"),
    "engine row moved instead of roster entry": ("const take = (team, keys) => keys.map(key => team.entries.find(e => asKey(e.key) === key));",
                                                 "const take = (team, keys) => keys.map(key => { const ref = trade.give.concat(trade.receive).find(x => x && (x === key || x.key === key || x.player_key === key)); return typeof ref === 'object' ? ref : team.entries.find(e => asKey(e.key) === key); });"),
}


def load_data() -> dict:
    return {"league": json.loads((FIXTURES / "league.json").read_text()), "package": json.loads((FIXTURES / "package.json").read_text())}


def run_checks(helper_js: Path) -> list[str]:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    proc = subprocess.run(["node", "-e", CHECKS, str(helper_js), json.dumps(load_data())], capture_output=True, text=True)
    if proc.returncode:
        return [f"node failed: {proc.stderr[-600:]}"]
    return json.loads(proc.stdout)


class PackageConstraintsTest(unittest.TestCase):
    def test_checks_pass(self):
        self.assertEqual(run_checks(HELPER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = HELPER_JS.read_text()
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTANTS.items():
                with self.subTest(mutant=name):
                    self.assertEqual(source.count(old), 1, f"mutant anchor not found once: {name}")
                    path = Path(tmp) / f"mutant-{len(name)}-{abs(hash(name))}.js"
                    path.write_text(source.replace(old, new))
                    self.assertNotEqual(run_checks(path), [], f"checks still pass with: {name}")

    def test_fixture_expected_rosters_are_hand_written(self):
        # Guard against the expected block drifting into a copy of the output: it must conserve the league's players.
        data = load_data()
        league_keys = sorted(e["key"] for t in data["league"]["teams"] for e in t["entries"])
        expected_keys = sorted(k for keys in data["package"]["expected"].values() for k in keys)
        self.assertEqual(league_keys, expected_keys)


if __name__ == "__main__":
    unittest.main()
