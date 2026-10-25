"""v2 Risers & fallers: where the market and the projections disagree (JEG-488, contract RF-02), app/v2/movers.js.

Per player, from the engine's own week pairs: dM = change in DDF Value (ddf_value_charts, the same series as ddf_value since JEG-1073) and dP = change in
DDF Value (projections) (ddf_value_projections). A player is in "Market moved, projections didn't" when |dM| >= 2.5 and
|dP| <= 1.0, and in "Projections moved, market didn't" when |dP| >= 2.5 and |dM| <= 1.0. The read comes from a fixed
rule on who moved and which way. These checks pin, against an independent recomputation:

  * both thresholds at their exact edges (2.5 and 1.0 qualify; 2.4 and 1.05 do not), either direction;
  * both sides moving, or neither, is in no list;
  * the four reads, by who moved and which way;
  * a player without a prior value on either side has no change and is counted, never read as 0;
  * a series without a prior week makes the whole comparison unavailable, with the engine's reasons;
  * each list is ordered by the size of the move that qualified it.

Discrimination: test_checks_fail_on_broken_builds mutates movers.js (thresholds, strict versus inclusive edges, a
missing prior read as 0, the reads swapped, no sorting) and requires every mutation to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOVERS_JS = ROOT / "app" / "v2" / "movers.js"

# (key, change in market, change in projections); the current value is 20 + change, the prior value 20.
CASES = [
    (1, 3.0, 0.5), (2, -4.0, 0.2), (3, 0.3, 3.0), (4, -0.5, -2.6),
    (5, 2.5, 1.0), (6, 2.4, 0.0), (7, 2.5, 1.05), (8, 3.0, 3.0), (9, 0.2, 0.3),
    (10, -2.5, -1.0), (11, 0.0, 6.0), (12, 5.0, -0.9), (13, 1.0, 2.5), (14, 1.05, 2.5),
]
NO_PRIOR = 15        # priced this week on both series, no prior value on projections
NO_MARKET_PRIOR = 16
READS = {"market|up": "Buying in without the production: sell", "market|down": "Panic the projections don't share: buy",
         "projections|up": "Market hasn't caught up: buy", "projections|down": "Market hasn't reacted: sell"}


def fixture():
    rows, prior_m, prior_p = [], {}, {}
    for key, dm, dp in CASES:
        rows.append({"player_key": key, "name": f"P{key}", "values": {"ddf_value_charts": 20.0 + dm, "ddf_value_projections": 20.0 + dp}})
        prior_m[str(key)] = 20.0
        prior_p[str(key)] = 20.0
    rows.append({"player_key": NO_PRIOR, "name": "NoP", "values": {"ddf_value_charts": 30.0, "ddf_value_projections": 30.0}})
    prior_m[str(NO_PRIOR)] = 20.0
    rows.append({"player_key": NO_MARKET_PRIOR, "name": "NoM", "values": {"ddf_value_charts": 30.0, "ddf_value_projections": 30.0}})
    prior_p[str(NO_MARKET_PRIOR)] = 20.0
    mk = lambda values: {"available": True, "currentWeek": 6, "priorWeek": 5, "values": values}
    return rows, mk(prior_m), mk(prior_p)


def expected():
    market, projections = [], []
    for key, dm, dp in CASES:
        if abs(dm) >= 2.5 and abs(dp) <= 1.0:
            market.append((key, abs(dm), READS[f"market|{'up' if dm > 0 else 'down'}"]))
        elif abs(dp) >= 2.5 and abs(dm) <= 1.0:
            projections.append((key, abs(dp), READS[f"projections|{'up' if dp > 0 else 'down'}"]))
    key_order = lambda t: (-t[1], t[0])
    return sorted(market, key=key_order), sorted(projections, key=key_order)


HARNESS = """
const M = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const brief = list => list.map(i => [i.row.player_key, i.size, i.read]);
const d = M.buildDisagreements(input.rows, input.pm, input.pp);
const bad = M.buildDisagreements(input.rows, {available: false, reason: "no Week 4 content saved"}, input.pp);
const both = M.buildDisagreements(input.rows, {available: false, reason: "a"}, {available: false, reason: "b"});
console.log(JSON.stringify({market: brief(d.market), projections: brief(d.projections), compared: d.compared, noDelta: d.noDelta,
  available: d.available, bad: {available: bad.available, reason: bad.reason, n: bad.market.length + bad.projections.length},
  both: both.reason, consts: [M.MOVE, M.QUIET]}));
"""


def run(path: Path):
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not available")
    rows, pm, pp = fixture()
    out = subprocess.run([node, "-e", HARNESS, str(path), json.dumps({"rows": rows, "pm": pm, "pp": pp})],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def check(result) -> list[str]:
    errors = []
    want_m, want_p = expected()
    got_m = [(k, round(s, 6), r) for k, s, r in result["market"]]
    got_p = [(k, round(s, 6), r) for k, s, r in result["projections"]]
    if got_m != [(k, round(s, 6), r) for k, s, r in want_m]:
        errors.append(f"market moved: {got_m}, want {want_m}")
    if got_p != [(k, round(s, 6), r) for k, s, r in want_p]:
        errors.append(f"projections moved: {got_p}, want {want_p}")
    if result["noDelta"] != 2 or result["compared"] != len(CASES):
        errors.append(f"a player with no prior value on a side is counted, not read as 0: noDelta {result['noDelta']}, compared {result['compared']}")
    if result["bad"]["available"] or result["bad"]["n"] or "DDF Value" not in result["bad"]["reason"] or "no Week 4 content saved" not in result["bad"]["reason"]:
        errors.append(f"a series without a prior week must make the comparison unavailable with the reason: {result['bad']}")
    # JEG-1073: the two sides are named DDF Value (the Adjusted chart average) and DDF Value (projections).
    if "DDF Value: a" not in result["both"] or "DDF Value (projections): b" not in result["both"]:
        errors.append(f"both reasons should be named: {result['both']!r}")
    if result["consts"] != [2.5, 1.0]:
        errors.append(f"thresholds {result['consts']}")
    return errors


MUTATIONS = {
    "move threshold raised": ("const MOVE = 2.5;", "const MOVE = 3.5;"),
    "quiet threshold raised": ("const QUIET = 1.0;", "const QUIET = 2.0;"),
    "move edge exclusive": ("if (Math.abs(m.delta) >= MOVE && Math.abs(p.delta) <= QUIET) {", "if (Math.abs(m.delta) > MOVE && Math.abs(p.delta) <= QUIET) {"),
    "quiet edge exclusive": ("Math.abs(p.delta) <= QUIET) {\n        market.push", "Math.abs(p.delta) < QUIET) {\n        market.push"),
    "both moved counted": ("Math.abs(m.delta) >= MOVE && Math.abs(p.delta) <= QUIET", "Math.abs(m.delta) >= MOVE"),
    "reads swapped": ('"market|up": "Buying in without the production: sell"', '"market|up": "Panic the projections don\'t share: buy"'),
    "missing prior read as zero": ("if (m.delta === null || p.delta === null) { noDelta += 1; return; }", "if (m.delta === null) m.delta = 0; if (p.delta === null) p.delta = 0;"),
    "not sorted": ("    market.sort(order);\n    projections.sort(order);\n", ""),
    "unavailable ignored": ("if (missing.length) return", "if (false) return"),
}


class DisagreeTest(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(run(MOVERS_JS)), [])

    def test_checks_fail_on_broken_builds(self):
        source = MOVERS_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"movers_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    try:
                        errors = check(run(broken))
                    except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
                        errors = ["crashed"]
                    self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
