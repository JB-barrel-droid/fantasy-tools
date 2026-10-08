"""distinctSourcePeaks guard core (curve-widget.js sourceCurvesDistinct).

JEG332-STORED-DRIFT (2026-10-07): once FantasyCalc's saved 12-team values
became the value-above-waivers translation, every translated published chart
peaks at the same positional max (RB 70), so the old peaks-only test threw
"Curve regression guard failed: distinctSourcePeaks" whenever only published
charts were active (tests/test_lock_revert_notice_render drives that state).

The guard's job is to catch every active curve being the SAME data. This test
runs the real function (extracted from curve-widget.js) and requires:
  * identical curves -> NOT distinct (the bug the guard names is still caught);
  * equal peaks but different curves -> distinct (the false positive is gone);
  * different peaks -> distinct.
Discrimination: the old peaks-only rule is run on the same cases and must get
the equal-peak case wrong, and a variant that always says "distinct" must miss
the identical case.
"""
from __future__ import annotations

import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"

CASES = {
    "identical": [{"1": 70, "2": 40.04, "3": 0}, {"1": 70, "2": 40.0, "3": 0}],
    "same-peak-different-curves": [{"1": 70, "2": 40, "3": 0}, {"1": 70, "2": 31.2, "3": 4}],
    "different-peaks": [{"1": 70, "2": 40}, {"1": 66.9, "2": 40}],
}
EXPECTED = {"identical": False, "same-peak-different-curves": True, "different-peaks": True}

OLD_PEAKS_ONLY = """function sourceCurvesDistinct(keys, maps) {
    return new Set(keys.map(key => Math.max(...maps.get(key).values()).toFixed(1))).size > 1;
  }"""
ALWAYS_DISTINCT = "function sourceCurvesDistinct(keys, maps) { return true; }"


def extract(source: str) -> str:
    m = re.search(r"function sourceCurvesDistinct\(keys, maps\) \{.*?\n  \}\n", source, re.S)
    if not m:
        raise AssertionError("sourceCurvesDistinct not found in curve-widget.js")
    return m.group(0)


def run(function_source: str) -> dict:
    script = function_source + """
const cases = JSON.parse(process.argv[1]);
const out = {};
for (const [name, curves] of Object.entries(cases)) {
  const maps = new Map(curves.map((c, i) => [`s${i}`, new Map(Object.entries(c).map(([k, v]) => [Number(k), v]))]));
  out[name] = sourceCurvesDistinct([...maps.keys()], maps);
}
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(["node", "-e", script, json.dumps(CASES)], capture_output=True, text=True,
                          timeout=60)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr[:1000])
    return json.loads(proc.stdout)


class SourceCurvesDistinct(unittest.TestCase):
    def test_guard_core(self):
        self.assertEqual(run(extract(WIDGET.read_text(encoding="utf-8"))), EXPECTED)

    def test_guard_is_wired(self):
        text = WIDGET.read_text(encoding="utf-8")
        self.assertIn("|| sourceCurvesDistinct(activeKeysForGuard, sourceMaps);", text)

    def test_discrimination(self):
        old = run(OLD_PEAKS_ONLY)
        self.assertNotEqual(old, EXPECTED)
        self.assertFalse(old["same-peak-different-curves"])  # the false positive
        lax = run(ALWAYS_DISTINCT)
        self.assertNotEqual(lax, EXPECTED)
        self.assertTrue(lax["identical"])  # would miss the bug the guard names


if __name__ == "__main__":
    unittest.main()
