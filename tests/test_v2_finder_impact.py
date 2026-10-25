"""v2 Find a trade, best lineup and roster impact (JEG-972 commit 3; display only, ranking never reads it).

Pure functions in app/v2/finder.js, run under node:

  * pickStarters(rows, shape, valueKey): QB/RB/WR/TE by highest value at the position, then FLEX from what is left of
    RB/WR/TE (never a QB), then SUPERFLEX from what is left of QB/RB/WR/TE; ties by lower player_key; a player with no
    value is never a starter and is reported, not counted as 0; a slot nobody can fill stays empty;
  * rosterImpact: starter / bench / total before and after a trade in one point of view, starters per position, roster
    spots opened by a 2-for-1; the market view is the mean of the compared charts, not DDF Value;
  * needLine: the one compact line (positions whose starter count changes, an emptied slot, an opened spot).

Discrimination: test_checks_fail_on_broken_builds runs the checks against mutated copies of finder.js (FLEX taking a
QB, SUPERFLEX refusing a QB, ties to the higher key, a missing value treated as a starter, the starter delta read from
the bench, the market view reading one chart) and requires each to fail.
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
SHAPE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0}


def p(key, pos, ddf, charts=None):
    values = {"ddf_value": ddf}
    for i, name in enumerate(["usatoday", "fantasycalc", "fantasypros", "cbs"]):
        values[name] = None if charts is None else charts[i]
    return {"player_key": key, "name": key, "pos": pos, "values": values}


def roster():
    return [p("Q1", "QB", 23), p("Q2", "QB", 40), p("R1", "RB", 30), p("R2", "RB", 25), p("R3", "RB", 22), p("R4", "RB", 5),
            p("W1", "WR", 28), p("W2", "WR", 24), p("W3", "WR", 21), p("T1", "TE", 10), p("T2", "TE", 3)]


def node(finder_js, code, data):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    script = "const F = require(process.argv[1]); const D = JSON.parse(process.argv[2]); const out = (() => {" + code + "})(); console.log(JSON.stringify(out));"
    proc = subprocess.run(["node", "-e", script, str(finder_js), json.dumps(data)], capture_output=True, text=True)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-600:])
    return json.loads(proc.stdout)


PICK = """
const r = F.pickStarters(D.rows, D.shape, 'ddf_value');
const k = list => list.map(x => x.player_key);
return {slots: Object.fromEntries(Object.entries(r.slots).map(([s, l]) => [s, k(l)])), bench: k(r.bench), unvalued: k(r.unvalued), empty: r.empty, starters: k(r.starters)};
"""

IMPACT = """
const give = D.rows.filter(x => D.give.includes(x.player_key));
const recv = D.recv;
const roster = D.rows.filter(x => !D.recv.some(y => y.player_key === x.player_key));
const i = F.rosterImpact(roster, give, recv, D.shape, D.key);
return {before: i.before.starterValue, after: i.after.starterValue, starterDelta: i.starterDelta, benchDelta: i.benchDelta, totalDelta: i.totalDelta,
  spots: i.spotsOpened, counts: [i.before.counts, i.after.counts], empty: i.after.empty, need: F.needLine(i)};
"""

AVG = """
const rows = F.withChartAverage(D.rows, ['usatoday', 'fantasycalc', 'fantasypros', 'cbs']);
return rows.map(r => r.values[F.MARKET_KEY]);
"""


def checks(finder_js) -> list[str]:
    errors = []
    base = {"rows": roster(), "shape": SHAPE}

    r = node(finder_js, PICK, base)
    want = {"QB": ["Q2"], "RB": ["R1", "R2"], "WR": ["W1", "W2"], "TE": ["T1"], "FLEX": ["R3"], "SUPERFLEX": []}
    if r["slots"] != want:
        errors.append(f"standard 1/2/2/1/1 lineup: {r['slots']}, want {want} (FLEX must never take a QB)")
    if sorted(r["bench"]) != sorted(["Q1", "R4", "W3", "T2"]):
        errors.append(f"bench: {r['bench']}")

    r = node(finder_js, PICK, {**base, "shape": {**SHAPE, "SUPERFLEX": 1}})
    if r["slots"]["SUPERFLEX"] != ["Q1"] or r["slots"]["FLEX"] != ["R3"]:
        errors.append(f"superflex should take the second QB (23) over the best RB/WR left (21): {r['slots']}")

    ties = [p("c", "RB", 10), p("a", "RB", 10), p("b", "RB", 10)]
    r = node(finder_js, PICK, {"rows": ties, "shape": {"RB": 2}})
    if r["slots"]["RB"] != ["a", "b"] or r["bench"] != ["c"]:
        errors.append(f"tie in value must go to the lower player_key: {r['slots']} bench {r['bench']}")

    r = node(finder_js, PICK, {"rows": [p("X", "RB", None), p("Y", "RB", 12)], "shape": {"RB": 2}})
    if r["slots"]["RB"] != ["Y"] or r["unvalued"] != ["X"] or r["empty"] != {"RB": 1} or "X" in r["bench"]:
        errors.append(f"a player with no value must not start and the slot stays empty: {r}")

    # 2-for-1: give R2 + R3 (RB 25, 22), receive one WR (30) from a roster that exactly fills the lineup.
    exact = [p("Q1", "QB", 23), p("R1", "RB", 30), p("R2", "RB", 25), p("R3", "RB", 22), p("W1", "WR", 28), p("W2", "WR", 24), p("T1", "TE", 10)]
    recv = [p("W9", "WR", 30)]
    r = node(finder_js, IMPACT, {"rows": exact + recv, "give": ["R2", "R3"], "recv": recv, "shape": SHAPE, "key": "ddf_value"})
    if abs(r["before"] - 162) > 1e-9 or abs(r["after"] - 145) > 1e-9 or abs(r["starterDelta"] + 17) > 1e-9:
        errors.append(f"starter value before/after/delta should be 162 / 145 / -17: {r}")
    if abs(r["benchDelta"]) > 1e-9 or r["spots"] != 1 or r["empty"] != {"RB": 1}:
        errors.append(f"2-for-1 should open one spot, leave the RB slot empty, bench unchanged: {r}")
    if "RB: 3 starters → 1" not in r["need"]:
        errors.append(f"need line does not say the RB count fell: {r['need']!r}")
    if "opens 1 roster spot" not in r["need"] or "RB slot left empty" not in r["need"]:
        errors.append(f"need line misses the empty slot or the opened spot: {r['need']!r}")

    # 1-for-1 at the same position: nothing to say about position needs.
    same = [p("A", "RB", 30), p("B", "RB", 20), p("C", "WR", 10)]
    recv = [p("D", "RB", 35)]
    r = node(finder_js, IMPACT, {"rows": same + recv, "give": ["A"], "recv": recv, "shape": {"RB": 1, "WR": 1}, "key": "ddf_value"})
    if abs(r["starterDelta"] - 5) > 1e-9 or r["need"] != "Starters by position unchanged":
        errors.append(f"RB for RB: {r}")

    # Market view: the mean of the four charts, a different lineup than DDF Value picks.
    rows = [p("hi", "RB", 50, [2, 4, 6, 8]), p("lo", "RB", 10, [20, 40, 20, 40]), p("part", "RB", 20, [9, None, 9, 9])]
    avg = node(finder_js, AVG, {"rows": rows})
    if avg != [5, 30, None]:
        errors.append(f"chart average should be the mean of four charts, null when one is missing: {avg}")
    market = node(finder_js, PICK.replace("'ddf_value'", "F.MARKET_KEY").replace("D.rows", "F.withChartAverage(D.rows, ['usatoday','fantasycalc','fantasypros','cbs'])"), {"rows": rows, "shape": {"RB": 1}})
    if market["slots"]["RB"] != ["lo"] or market["unvalued"] != ["part"]:
        errors.append(f"market lineup should pick the chart-average leader and leave out an unpriced player: {market}")
    return errors


class FinderImpactTest(unittest.TestCase):
    def test_lineup_and_impact(self):
        self.assertEqual(checks(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "FLEX takes a QB": js.replace('const FLEX_POS = ["RB", "WR", "TE"];', 'const FLEX_POS = ["QB", "RB", "WR", "TE"];', 1),
            "SUPERFLEX refuses a QB": js.replace('const SUPERFLEX_POS = ["QB", "RB", "WR", "TE"];', 'const SUPERFLEX_POS = ["RB", "WR", "TE"];', 1),
            "ties to the higher key": js.replace("String(a.player_key).localeCompare(String(b.player_key))", "String(b.player_key).localeCompare(String(a.player_key))"),
            "missing value may start": js.replace("const hasValue = r => Boolean(r.values) && finite(r.values[valueKey]);", "const hasValue = () => true;", 1),
            "starter delta read from the bench": js.replace("starterDelta: next.starterValue - before.starterValue", "starterDelta: next.benchValue - before.benchValue", 1),
            "market view reads one chart": js.replace("vals.reduce((a, b) => a + b, 0) / vals.length", "vals[0]", 1),
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
