"""v2 Find a trade, grouping and throw-in collapse (JEG-972 commit 2, JEG-885 decisions of Jeremy 2026-10-23).

Pure functions in app/v2/finder.js, run under node:

  * evaluateCombo is the one place a package is judged; findTrades and the live group card both use it, so for every
    trade the search lists, evaluateCombo gives the same edge, chart nets, count and score (parity);
  * collapseThrowIns: rows that differ only by a player worth 0.0 on DDF Value and every compared chart become one
    row (the simpler trade) and name the player as a throw-in; when the simpler trade was not found the variant is kept;
  * groupTrades: one group per receive core (highest DDF Value you receive, tie by lower player_key); a received
    player worth at least 50% of the core is part of the group's identity, a smaller one is a side player; every
    group's preselected best is a trade the search listed; groups are ordered by that best edge, deterministically.

Discrimination: test_checks_fail_on_broken_builds runs the checks against mutated copies of finder.js (grouping on
the give core, no 50% rule, core chosen by lowest value, throw-ins not collapsed, a variant dropped when the simple
trade is absent, evaluateCombo ignoring the chart gate) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]


def row(key, ddf, charts=None, pos="RB"):
    charts = ddf if charts is None else charts
    if not isinstance(charts, list):
        charts = [charts] * 4
    return {"player_key": key, "name": key, "pos": pos, "values": dict(zip(["ddf_value"] + CH, [ddf] + charts))}


def node(finder_js, code, data):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    script = "const F = require(process.argv[1]); const D = JSON.parse(process.argv[2]); const out = (() => {" + code + "})(); console.log(JSON.stringify(out));"
    proc = subprocess.run(["node", "-e", script, str(finder_js), json.dumps(data)], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-800:])
    return json.loads(proc.stdout)


def mrow(key, ddf):
    """Your player: the market prices you high, so the rival is happy to take him."""
    return row(key, ddf, round(ddf * 3, 2))


def trow(key, ddf):
    """Their player: the market prices him low, so a trade for him can clear the 3-of-4 chart gate."""
    return row(key, ddf, round(ddf * 0.8, 2))


# A fixed pseudo-random league: 9 vs 9 players, 3-for-3.
def league():
    seed = 7
    def rnd():
        nonlocal seed
        seed = (seed * 1103515245 + 12345) % 2147483648
        return seed / 2147483648
    def side(prefix):
        out = []
        for i in range(9):
            base = 4 + rnd() * 30
            out.append(row(f"{prefix}{i}", round(base, 1), [round(max(0, base + (rnd() - 0.5) * 8), 1) for _ in range(4)]))
        return out
    return {"mine": side("m"), "theirs": side("t")}


PARITY = """
const r = F.findTrades(D.mine, D.theirs, {maxSize: 3, limit: 1e7, keepAll: true});
const ctx = r.ctx;
const bad = [];
for (const t of r.trades) {
  const e = F.evaluateCombo(t.give, t.receive, ctx);
  const same = Math.abs(e.edge - t.edge) < 1e-9 && e.rivalOkCount === t.rivalOkCount && e.pricedCharts === t.pricedCharts
    && Math.abs(e.score - t.score) < 1e-9 && e.passes.edge && e.passes.charts && e.passes.lineup
    && e.charts.every((c, i) => c.net === t.charts[i].net || Math.abs(c.net - t.charts[i].net) < 1e-9);
  if (!same) bad.push(t.give.map(p => p.player_key) + '>' + t.receive.map(p => p.player_key));
}
// a package the search would not list (you lose on DDF Value) must say so
const worst = F.evaluateCombo([D.mine.slice().sort((a, b) => b.values.ddf_value - a.values.ddf_value)[0]], [D.theirs.slice().sort((a, b) => a.values.ddf_value - b.values.ddf_value)[0]], ctx);
return {n: r.trades.length, bad, lossPassesEdge: worst.passes.edge};
"""

THROW = """
const r = F.findTrades(D.mine, D.theirs, {maxSize: 2, limit: 1e7});
return {total: r.total, rows: r.trades.map(t => ({give: t.give.map(p => p.player_key), receive: t.receive.map(p => p.player_key), throwIns: t.throwIns || null}))};
"""

ABSENT = """
const mk = (g, r, throwIns) => ({give: g, receive: r, edge: 3, score: 3, charts: [], throwIns: null});
const Z = D.z;
const variant = mk([D.a], [D.b, Z]);          // simple trade a for b is NOT in the list
const other = mk([D.a], [D.c]);
const out = F.collapseThrowIns([variant, other], D.chartKeys, 'ddf_value');
return out.map(t => ({give: t.give.map(p => p.player_key), receive: t.receive.map(p => p.player_key), throwIns: t.throwIns}));
"""

GATE = """
const r = F.findTrades([D.mine], [D.theirs], {maxSize: 1});
const e = F.evaluateCombo([D.mine], [D.theirs], r.ctx);
return {edge: e.passes.edge, charts: e.passes.charts};
"""

GROUPS = """
const r = F.findTrades(D.mine, D.theirs, {maxSize: D.maxSize, limit: 1e7});
const g = F.groupTrades(r.trades, {ourKey: 'ddf_value'});
const key = t => t.give.map(p => p.player_key) + '>' + t.receive.map(p => p.player_key);
const listed = new Set(r.trades.map(key));
return {groups: g.map(x => ({core: x.core.player_key, heavy: x.heavy.map(p => p.player_key), best: key(x.best), bestEdge: x.bestEdge,
  trades: x.trades.length, sides: x.receiveSide.map(p => p.player_key), give: x.giveCandidates.map(p => p.player_key)})),
  bestListed: g.every(x => listed.has(key(x.best))), allCovered: g.reduce((n, x) => n + x.trades.length, 0) === r.trades.length};
"""


def run_groups(finder_js, mine, theirs, max_size=2):
    return node(finder_js, GROUPS, {"mine": mine, "theirs": theirs, "maxSize": max_size})


def checks(finder_js) -> list[str]:
    errors = []
    lg = league()
    # parity
    par = node(finder_js, PARITY, lg)
    if par["n"] < 50:
        errors.append(f"parity fixture too small ({par['n']} trades)")
    if par["bad"]:
        errors.append(f"evaluateCombo disagrees with findTrades on {len(par['bad'])} trades, e.g. {par['bad'][:2]}")
    if par["lossPassesEdge"]:
        errors.append("evaluateCombo says a losing package passes the edge gate")

    # throw-in: mine a, b; theirs c (30), z (all zero). a 20 for c is a trade; a for c + z is the same trade.
    mine = [mrow("a", 20), mrow("b", 5)]
    theirs = [trow("c", 30), trow("z", 0.0)]
    th = node(finder_js, THROW, {"mine": mine, "theirs": theirs})
    keys = [(t["give"], t["receive"]) for t in th["rows"]]
    if (["a"], ["c"]) not in keys or (["a"], ["c", "z"]) in keys or (["a"], ["z", "c"]) in keys:
        errors.append(f"throw-in variant not collapsed into the simple trade: {keys}")
    simple = [t for t in th["rows"] if t["give"] == ["a"] and t["receive"] == ["c"]]
    if not simple or not simple[0]["throwIns"] or [p["player_key"] for p in simple[0]["throwIns"]["receive"]] != ["z"]:
        errors.append(f"the throw-in is not named on the kept trade: {simple}")
    if th["total"] != len(th["rows"]):
        errors.append("total does not count the trades after the collapse")

    # the simple trade absent: keep the variant, never invent
    ab = node(finder_js, ABSENT, {"a": row("a", 20), "b": row("b", 25), "c": row("c", 22), "z": row("z", 0.0), "chartKeys": CH})
    if not any(t["receive"] == ["b", "z"] for t in ab):
        errors.append(f"the variant was dropped although the simple trade is not listed: {ab}")

    # grouping: four targets, each with two give options
    mine = [mrow("g1", 20), mrow("g2", 21), mrow("g3", 22), mrow("g4", 6), mrow("g5", 7)]
    theirs = [trow("T1", 30), trow("T2", 29), trow("T3", 28), trow("T4", 27), trow("s1", 2), trow("s2", 3)]
    gr = run_groups(finder_js, mine, theirs, 2)
    cores = [g["core"] for g in gr["groups"]]
    if len(set(cores)) < 4 or not {"T1", "T2", "T3", "T4"} <= set(cores):
        errors.append(f"expected a group for each of the four targets: {cores}")
    if {"s1", "s2"} & set(cores):
        errors.append(f"a small side player became a group core: {cores}")
    if not gr["bestListed"]:
        errors.append("a group's preselected best is not a trade the search listed")
    if not gr["allCovered"]:
        errors.append("the groups do not cover every listed trade exactly once")
    edges = [g["bestEdge"] for g in gr["groups"]]
    if edges != sorted(edges, reverse=True):
        errors.append(f"groups are not ordered by best edge: {edges}")
    shuffled = run_groups(finder_js, list(reversed(mine)), list(reversed(theirs)), 2)
    if [g["core"] for g in shuffled["groups"]] != cores or [g["best"] for g in shuffled["groups"]] != [g["best"] for g in gr["groups"]]:
        errors.append("group order depends on the order the rosters were given in")
    for g in gr["groups"]:
        if g["core"] in g["sides"]:
            errors.append(f"the core is also listed as a side player in {g['core']}")

    # 50% rule: receiving T1 (30) with B (16 >= 15) is its own group; with s (2) it is a side player of T1's group
    mine = [mrow("g1", 20), mrow("g2", 21), mrow("g3", 4)]
    theirs = [trow("T1", 40), trow("B", 21), trow("s", 2)]
    gr = run_groups(finder_js, mine, theirs, 2)
    heavy = {tuple(g["heavy"]) for g in gr["groups"]}
    if ("T1", "B") not in heavy and ("B", "T1") not in heavy:
        errors.append(f"a received player worth over half the core did not make its own group: {heavy}")
    plain = [g for g in gr["groups"] if g["heavy"] == ["T1"]]
    if plain and "B" in plain[0]["sides"]:
        errors.append("a player worth over half the core is offered as a side player")

    # singles: a 1-for-1 group has no side players; a 2-for-1 has them on the long side only
    gr = run_groups(finder_js, [mrow("m1", 10), mrow("m2", 9)], [trow("t1", 25)], 2)
    for g in gr["groups"]:
        if g["sides"]:
            errors.append(f"a one-player receive side has side players: {g}")
    # equal cores: the lower player_key is the core
    gr = run_groups(finder_js, [mrow("m1", 10)], [trow("tb", 25), trow("ta", 25)], 1)
    if sorted(g["core"] for g in gr["groups"]) != ["ta", "tb"]:
        errors.append(f"equal-value targets: {gr['groups']}")
    # equal cores in one package: the lower player_key is the core, the other is part of the group identity (equal value)
    gr = run_groups(finder_js, [mrow("m1", 20), mrow("m2", 21)], [trow("tb", 25), trow("ta", 25)], 2)
    if not any(g["core"] == "ta" and g["heavy"] == ["ta", "tb"] for g in gr["groups"]):
        errors.append(f"equal-value cores: lower key should be the core: {gr['groups']}")

    # a package that wins on DDF Value but loses the chart gate must say so (gate not assumed)
    gate = node(finder_js, GATE, {"mine": mrow("m", 10), "theirs": row("t", 20, 40)})
    if not gate["edge"] or gate["charts"]:
        errors.append(f"evaluateCombo gate flags wrong for a package that wins on DDF Value but loses on charts: {gate}")
    return errors


class FinderGroupsTest(unittest.TestCase):
    def test_grouping_and_throw_ins(self):
        self.assertEqual(checks(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "grouped on the give core": js.replace("const core = coreOf(t.receive, ourKey);", "const core = coreOf(t.give, ourKey);", 1),
            "no 50% rule": js.replace("const HEAVY_SHARE = 0.5;", "const HEAVY_SHARE = 9;", 1),
            "core is the lowest value": js.replace("b.values[ourKey] - a.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key)));\n    return sorted[0]", "a.values[ourKey] - b.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key)));\n    return sorted[0]", 1),
            "throw-ins not collapsed": js.replace("const collapsed = collapseThrowIns(found, chartKeys, ourKey);", "const collapsed = found;", 1),
            "variant dropped when the simple trade is absent": js.replace("let rep = members[0];", "let rep = members.find(m => !m.give.concat(m.receive).some(r => isZeroValue(r, keys))); if (!rep) return;", 1),
            "chart gate ignored": js.replace("charts: priced >= minCharts && ok >= minCharts", "charts: true", 1),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in broken.items():
                with self.subTest(mutation=name):
                    self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                    path = Path(tmp) / "finder.js"
                    path.write_text(body, encoding="utf-8")
                    try:
                        errors = checks(path)
                    except RuntimeError as exc:
                        errors = [str(exc)]
                    self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
