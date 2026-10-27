"""JEG-1081 PR 1: the noise of DDF Value (projections) in the fit rule, pure logic in app/v2/finder.js.

valueNoise(row, key) is the standard error of one player's value in a view. Existing branches: DDF Value (half the gap
between its chart and projection versions) and the Trade chart average (standard error of the mean of the charts). New:
DDF Value (projections), the standard error of the mean of ESPN, CBS rest of season and Razzball. Cases:

  * three projections 10 / 12 / 14: SE = sd 2 / sqrt(3);
  * two readings are enough (a missing source is skipped); one or none is 0, not NaN;
  * the projection sources do not leak into the other branches and the chart sources do not leak into this one;
  * zeroing one projection source widens the spread (the mutation proof in the spec) and a spread-free row is 0;
  * the existing branches are unchanged (frozen values), and teamFit's tau for the projections key uses the new noise;
  * PROJECTION_KEYS and PROJECTIONS_KEY are exported.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of finder.js with a rule broken.
"""
from __future__ import annotations

import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call
from tests.test_v2_finder_balance import ALLOC, SHAPE

CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
PK = "ddf_value_projections"


def row(**values):
    return {"player_key": "x", "pos": "RB", "name": "x", "values": values}


def se(vals):
    mean = sum(vals) / len(vals)
    return math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1) / len(vals))


def close(a, b):
    return abs(a - b) < 1e-9


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append
    # 1. Three projections: SE of the mean.
    got = call(finder_js, "valueNoise", row(espn=10, cbsros=12, razzball=14), PK)
    if not close(got, se([10, 12, 14])) or not close(got, 2 / math.sqrt(3)):
        say(f"three projections 10/12/14: {got}, want {2 / math.sqrt(3)}")
    # 2. A missing source is skipped; fewer than two readings is 0.
    got = call(finder_js, "valueNoise", row(espn=10, razzball=14), PK)
    if not close(got, se([10, 14])):
        say(f"two projections 10/14: {got}, want {se([10, 14])}")
    for label, r in (("one source", row(espn=10)), ("no sources", row()), ("null values", row(espn=None, cbsros=None, razzball=5)), ("no values", {"player_key": "x"})):
        got = call(finder_js, "valueNoise", r, PK)
        if got != 0:
            say(f"{label}: {got}, want 0")
    # 3. Sources do not leak across branches.
    mixed = row(espn=10, cbsros=12, razzball=14, usatoday=20, fantasycalc=20, fantasypros=20, cbs=20)
    got = call(finder_js, "valueNoise", mixed, PK)
    if not close(got, se([10, 12, 14])):
        say(f"charts leaked into the projections branch: {got}")
    got = call(finder_js, "valueNoise", mixed, "chart_avg", CH)
    if got != 0:
        say(f"projections leaked into the chart branch (charts all 20): {got}")
    # 4. Mutation proof from the spec: zero one projection source and the noise rises.
    base = call(finder_js, "valueNoise", row(espn=20, cbsros=21, razzball=22), PK)
    zeroed = call(finder_js, "valueNoise", row(espn=0, cbsros=21, razzball=22), PK)
    if not zeroed > base + 1:
        say(f"zeroing one projection source: {base} -> {zeroed}, want a clear increase")
    if call(finder_js, "valueNoise", row(espn=15, cbsros=15, razzball=15), PK) != 0:
        say("three identical projections should have no noise")
    # 5. Existing branches unchanged (frozen values).
    got = call(finder_js, "valueNoise", row(ddf_value_charts=10, ddf_value_projections=13), "ddf_value")
    if not close(got, 1.5):
        say(f"DDF Value branch: {got}, want 1.5")
    got = call(finder_js, "valueNoise", row(usatoday=10, fantasycalc=12, fantasypros=14, cbs=16), "chart_avg", CH)
    if not close(got, se([10, 12, 14, 16])):
        say(f"chart_avg branch: {got}, want {se([10, 12, 14, 16])}")
    got = call(finder_js, "valueNoise", row(usatoday=10, fantasycalc=12, fantasypros=14, cbs=16), "chart_avg", ["usatoday", "fantasycalc"])
    if not close(got, se([10, 12])):
        say(f"chart_avg with a chart subset: {got}, want {se([10, 12])}")
    # 6. teamFit's tau for the projections view uses the projections noise (z = 1, one player arriving).
    def p(key, pos, v, **src):
        return {"player_key": key, "pos": pos, "name": key, "values": {"ddf_value": v, PK: v, "chart_avg": v, **src}}
    mine = [p("q", "QB", 20), p("r1", "RB", 30), p("r2", "RB", 25), p("w1", "WR", 20), p("w2", "WR", 18), p("t", "TE", 10)]
    arriving = [p("a", "RB", 28, espn=20, cbsros=28, razzball=36)]
    expected = call(finder_js, "expectedDepth", ALLOC, 12)
    ctx = {"shape": SHAPE, "weights": {"overall": 0.15}, "chartKeys": CH, "z": 1, "expected": expected}
    out = call(finder_js, "teamFit", {"roster": mine, "leaving": [], "arriving": arriving}, ctx, PK)
    if not close(out["tau"], se([20, 28, 36])):
        say(f"teamFit tau under projections: {out['tau']}, want {se([20, 28, 36])}")
    # 7. Exports.
    out = subprocess.run(["node", "-e", "const F = require(process.argv[1]); console.log(JSON.stringify([F.PROJECTION_KEYS, F.PROJECTIONS_KEY]))", str(finder_js)],
                         check=True, capture_output=True, text=True)
    keys = json.loads(out.stdout)
    if keys != [["espn", "cbsros", "razzball"], PK]:
        say(f"PROJECTION_KEYS: {keys}")
    return errors


MUTANTS = {
    "projections branch missing": ('if (key === PROJECTIONS_KEY) return standardErrorOfMean(PROJECTION_KEYS.map(k => v[k]).filter(finite));', ""),
    "projections read the charts": ("PROJECTION_KEYS.map(k => v[k]).filter(finite)", "CHART_KEYS.map(k => v[k]).filter(finite)"),
    "one source missing from the set": ('const PROJECTION_KEYS = ["espn", "cbsros", "razzball"];', 'const PROJECTION_KEYS = ["espn", "cbsros"];'),
    "sd not standard error": ("return Math.sqrt(variance / vals.length);", "return Math.sqrt(variance);"),
    "population variance": ("(b - mean) * (b - mean), 0) / (vals.length - 1);", "(b - mean) * (b - mean), 0) / vals.length;"),
    "single reading allowed": ("if (vals.length < 2) return 0;", "if (vals.length < 1) return 0;"),
    "DDF Value branch dropped": ("if (key === OUR_KEY) return finite(v.ddf_value_charts)", "if (false) return finite(v.ddf_value_charts)"),
}


class ProjectionNoiseTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, source, f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
