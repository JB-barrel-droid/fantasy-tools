"""JEG-1129: withChartAverage writes chart_avg, never ddf_value_charts, in app/v2/finder.js.

MARKET_KEY is "ddf_value_charts", the engine's own value that the viability rule reads (my side gains on DDF Value;
the other team judges by ddf_value_charts). withChartAverage adds the plain mean of the compared chart rows as the
Trade chart average display series, so it must write that mean under CHART_AVG_KEY = "chart_avg". When it wrote
MARKET_KEY instead, every caller of withChartAverage overwrote the engine's ddf_value_charts with the chart mean
(waivers' valueNoise read the wrong series and the DDF Value noise floor moved).

Cases:
  * MARKET_KEY stays "ddf_value_charts" and CHART_AVG_KEY is "chart_avg";
  * withChartAverage leaves a row's ddf_value_charts exactly as it was and puts the chart mean under chart_avg;
  * a missing chart price leaves chart_avg null (never 0) and still leaves ddf_value_charts alone;
  * the input rows are not mutated;
  * valueNoise treats chart_avg like the market key (the standard error of the chart values).

Discrimination: test_checks_fail_on_broken_builds runs the same checks on a copy of finder.js that writes the mean
under MARKET_KEY again (the pre-fix line).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call

CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
MAR = "ddf_value_charts"
AVG = "chart_avg"


def row(**values):
    return {"player_key": "x", "pos": "RB", "name": "x", "values": values}


def close(a, b):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) < 1e-9


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append
    # 1. Exports: the viability key is unchanged, the display key is the plain mean.
    out = subprocess.run(["node", "-e", "const F = require(process.argv[1]); console.log(JSON.stringify([F.MARKET_KEY, F.CHART_AVG_KEY]))", str(finder_js)],
                         check=True, capture_output=True, text=True)
    keys = json.loads(out.stdout)
    if keys != [MAR, AVG]:
        say(f"MARKET_KEY / CHART_AVG_KEY: {keys}, want {[MAR, AVG]}")
    # 2. The engine's ddf_value_charts (50) is not the chart mean (13): the mean goes to chart_avg only.
    r = row(ddf_value_charts=50, usatoday=10, fantasycalc=12, fantasypros=14, cbs=16)
    got = call(finder_js, "withChartAverage", [r], CH)[0]["values"]
    if got.get(MAR) != 50:
        say(f"ddf_value_charts overwritten: {got.get(MAR)}, want 50")
    if not close(got.get(AVG), 13):
        say(f"chart_avg: {got.get(AVG)}, want 13")
    # 3. A missing chart price: no average (null, never 0), and ddf_value_charts is still untouched.
    got = call(finder_js, "withChartAverage", [row(ddf_value_charts=50, usatoday=10, fantasycalc=12, fantasypros=14)], CH)[0]["values"]
    if got.get(AVG) is not None:
        say(f"one chart missing: chart_avg {got.get(AVG)}, want null")
    if got.get(MAR) != 50:
        say(f"one chart missing: ddf_value_charts {got.get(MAR)}, want 50")
    # 4. No charts compared: no average key value; ddf_value_charts untouched.
    got = call(finder_js, "withChartAverage", [row(ddf_value_charts=50, usatoday=10)], [])[0]["values"]
    if got.get(AVG) is not None or got.get(MAR) != 50:
        say(f"no charts: {got}, want chart_avg null and ddf_value_charts 50")
    # 5. The input rows are not mutated (the result is a copy).
    script = ("const F = require(process.argv[1]);"
              "const r = {player_key:'x',pos:'RB',name:'x',values:{ddf_value_charts:50,usatoday:10,fantasycalc:12,fantasypros:14,cbs:16}};"
              "const before = JSON.stringify(r);"
              "F.withChartAverage([r], process.argv[2].split(','));"
              "console.log(r.chart_avg === undefined && JSON.stringify(r) === before ? 'ok' : 'mutated');")
    out = subprocess.run(["node", "-e", script, str(finder_js), ",".join(CH)], check=True, capture_output=True, text=True)
    if out.stdout.strip() != "ok":
        say(f"input row mutated: {out.stdout.strip()}")
    # 6. valueNoise: chart_avg is the standard error of the chart values, same as the market key.
    mixed = row(usatoday=10, fantasycalc=12, fantasypros=14, cbs=16)
    avg = call(finder_js, "valueNoise", mixed, AVG, CH)
    mar = call(finder_js, "valueNoise", mixed, MAR, CH)
    if not close(avg, mar):
        say(f"valueNoise(chart_avg) {avg} != valueNoise(ddf_value_charts) {mar}")
    if avg == 0:
        say("valueNoise(chart_avg) is 0 for four different charts, want the spread")
    return errors


MUTANTS = {
    # The pre-fix line: the chart mean overwrites the engine's ddf_value_charts.
    "mean written under MARKET_KEY": ("{...r.values, [CHART_AVG_KEY]: complete", "{...r.values, [MARKET_KEY]: complete"),
    "chart_avg dropped": ("[CHART_AVG_KEY]: complete ?", "[CHART_AVG_KEY + \"_x\"]: complete ?"),
    "valueNoise ignores chart_avg": ("if (key === MARKET_KEY || key === CHART_AVG_KEY)", "if (key === MARKET_KEY)"),
}


class ChartAvgKeyTests(unittest.TestCase):
    def test_rules(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
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
