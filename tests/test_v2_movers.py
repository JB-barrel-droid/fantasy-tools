"""v2 Risers & fallers and Δ prior week: the arithmetic in app/v2/movers.js.

The only arithmetic is, per player, for one exact series:

    Δ = current value − prior-week value    (the engine's getPriorWeek recompute)

These checks pin:

  * the sign: a higher value this week is a riser (positive Δ);
  * a player with no prior value has no Δ and is counted, never 0, never the
    current value standing in;
  * a player with no current value is counted separately;
  * a series with no prior week gives no movers and carries the engine's reason;
  * a Δ that shows as 0.0 is neither a riser nor a faller;
  * risers are ordered largest rise first, fallers largest fall first.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on
mutated copies (sign flipped, missing prior read as 0, unavailable prior
ignored, unchanged players listed) and requires each to fail.
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

ROWS = [
    {"player_key": 1, "name": "A", "values": {"fantasycalc": 30.0}},
    {"player_key": 2, "name": "B", "values": {"fantasycalc": 10.0}},
    {"player_key": 3, "name": "C", "values": {"fantasycalc": 20.0}},   # no prior value
    {"player_key": 4, "name": "D", "values": {"fantasycalc": None}},   # no current value
    {"player_key": 5, "name": "E", "values": {"fantasycalc": 12.02}},  # unchanged (Δ 0.02)
    {"player_key": 6, "name": "F", "values": {"fantasycalc": 40.0}},
]
PRIOR = {"available": True, "currentWeek": 5, "priorWeek": 4,
         "values": {"1": 25.0, "2": 14.0, "4": 8.0, "5": 12.0, "6": 32.0}}
UNAVAILABLE = {"available": False, "reason": "no Week 3 content saved", "values": None}

HARNESS = """
const M = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const brief = list => list.map(m => [m.row.player_key, Math.round(m.delta * 1000) / 1000]);
const a = M.buildMovers(input.rows, 'fantasycalc', input.prior);
const b = M.buildMovers(input.rows, 'fantasycalc', input.unavailable);
const d = M.deltaFor(20, input.prior, '3');
// JEG-465: a DDF Value prior carries its own current side; "now" and Δ both come from it.
const ddf = M.buildMovers(input.rows, 'ddf_value', {...input.prior, currentValues: {'1': 40, '2': 10, '6': 32}});
const ddfBrief = ddf.risers.concat(ddf.fallers).map(m => [m.row.player_key, m.current, m.before, Math.round(m.delta * 1000) / 1000]);
console.log(JSON.stringify({risers: brief(a.risers), fallers: brief(a.fallers), noPrior: a.noPrior, noCurrent: a.noCurrent,
  unchanged: a.unchanged, priorWeek: a.priorWeek, un: {available: b.available, reason: b.reason, n: b.risers.length + b.fallers.length},
  missing: d, ddf: ddfBrief}));
"""


def run(js: Path):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, str(js), json.dumps({"rows": ROWS, "prior": PRIOR, "unavailable": UNAVAILABLE})],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def check(js: Path) -> list[str]:
    r = run(js)
    errors = []
    if r["risers"] != [[6, 8.0], [1, 5.0]]:
        errors.append(f"risers {r['risers']} != [[6, 8.0], [1, 5.0]] (largest rise first, Δ = now − prior)")
    if r["fallers"] != [[2, -4.0]]:
        errors.append(f"fallers {r['fallers']} != [[2, -4.0]]")
    if (r["noPrior"], r["noCurrent"], r["unchanged"]) != (1, 1, 1):
        errors.append(f"counts noPrior/noCurrent/unchanged {(r['noPrior'], r['noCurrent'], r['unchanged'])} != (1, 1, 1)")
    if r["un"] != {"available": False, "reason": "no Week 3 content saved", "n": 0}:
        errors.append(f"unavailable prior must give no movers and the engine's reason: {r['un']}")
    if r["missing"].get("delta") is not None or "Week 4" not in (r["missing"].get("reason") or ""):
        errors.append(f"no prior value must be Δ — with a reason naming the week: {r['missing']}")
    if sorted(r["ddf"]) != [[1, 40, 25.0, 15.0], [2, 10, 14.0, -4.0]]:
        errors.append(f"DDF Value movers {r['ddf']} must read now from currentValues: [[1, 40, 25, 15], [2, 10, 14, -4]]")
    return errors


class MoversTest(unittest.TestCase):
    def test_movers(self):
        self.assertEqual(check(MOVERS_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = MOVERS_JS.read_text(encoding="utf-8")
        broken = {
            "sign flipped": source.replace("return {delta: current - before, before, current, reason: null};",
                                           "return {delta: before - current, before, current, reason: null};", 1),
            "missing prior read as zero": source.replace(
                "const before = prior.values ? prior.values[playerKey] : undefined;",
                "const before = (prior.values ? prior.values[playerKey] : undefined) ?? 0;", 1),
            "unavailable prior ignored": source.replace(
                "if (!prior || !prior.available) {\n      return {series, available: false,",
                "if (!prior) {\n      return {series, available: false,", 1),
            "DDF now read from the row, not currentValues": source.replace(
                "if (prior.currentValues) current = prior.currentValues[playerKey];", "", 1),
            "unchanged listed": source.replace("if (Math.abs(d.delta) < 0.05) unchanged += 1;", "if (false) unchanged += 1;", 1),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in broken.items():
                with self.subTest(mutation=name):
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                    path = Path(tmp) / f"{name.replace(' ', '_')}.js"
                    path.write_text(body, encoding="utf-8")
                    try:
                        errors = check(path)
                    except subprocess.CalledProcessError as exc:
                        errors = [f"crashed: {exc.stderr[:200]}"]
                    self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
