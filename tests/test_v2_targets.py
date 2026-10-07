"""v2 Trade targets: the gap math in app/v2/targets.js.

The tab's only arithmetic is gap = published chart value − our value (ESPN
DDA), per player per chart, on the engine's own rows. These checks pin:

  * the sign: a chart paying more than us is a sell target (positive gap);
  * a missing value on either side gives no gap (null + reason), never 0, and a
    player without our value is left out and counted;
  * VORP vs waivers (a different unit) is never paired with anything;
  * older-week charts are left out unless asked for.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against
mutated copies of targets.js (sign flipped, missing read as 0, older weeks
included by default) and requires every one to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS_JS = ROOT / "app" / "v2" / "targets.js"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]

ROWS = [
    {"player_key": 1, "name": "A", "values": {"espn": 10.0, "usatoday": 15.0, "fantasycalc": 8.0, "fantasypros": None, "cbs": 12.0}},
    {"player_key": 2, "name": "B", "values": {"espn": None, "usatoday": 30.0}},
    {"player_key": 3, "name": "C", "values": {"espn": 20.0, "usatoday": 20.0}},
    {"player_key": 4, "name": "D", "values": {"espn": 5.0, "fantasycalc": 25.0, "espn_vorp": 99.0}},
    {"player_key": 5, "name": "E", "values": {"espn": 30.0, "usatoday": 10.0, "espn_vorp": 1.0}},
]
INFO = [
    {"key": "espn", "available": True, "stale": False},
    {"key": "usatoday", "available": True, "stale": False, "week": 5},
    {"key": "fantasycalc", "available": True, "stale": False, "week": 5},
    {"key": "fantasypros", "available": False, "stale": False, "paused": True},
    {"key": "cbs", "available": True, "stale": True, "week": 4},
]

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const r = T.buildTargets(input.rows, input.charts);
const brief = p => ({key: p.row.player_key, ours: p.ours, cells: p.cells,
  bestSell: p.bestSell, bestBuy: p.bestBuy});
console.log(JSON.stringify({
  sell: r.sell.map(brief), buy: r.buy.map(brief), compared: r.compared, omitted: r.omittedNoOurs,
  defaultCharts: T.chartsToCompare(input.info, {}),
  olderCharts: T.chartsToCompare(input.info, {includeOlder: true}),
  onlyCharts: T.chartsToCompare(input.info, {only: "fantasycalc"}),
  ourKey: T.OUR_KEY,
}));
"""


def run_targets(path: Path) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not available")
    payload = json.dumps({"rows": ROWS, "charts": CHARTS, "info": INFO})
    out = subprocess.run([node, "-e", HARNESS, str(path), payload], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def check(result: dict) -> list[str]:
    """Return every rule the result breaks (empty list = correct)."""
    errors = []
    if result["ourKey"] != "espn":
        errors.append(f"our value must be the ESPN DDA series, got {result['ourKey']}")
    sell = [(p["key"], p["bestSell"]) for p in result["sell"]]
    buy = [(p["key"], p["bestBuy"]) for p in result["buy"]]
    if sell != [(4, {"chart": "fantasycalc", "gap": 20.0}), (1, {"chart": "usatoday", "gap": 5.0})]:
        errors.append(f"sell list wrong (chart pays more = positive gap, largest first): {sell}")
    if buy != [(5, {"chart": "usatoday", "gap": -20.0}), (1, {"chart": "fantasycalc", "gap": -2.0})]:
        errors.append(f"buy list wrong (chart pays less = negative gap, most negative first): {buy}")
    a = next((p for p in result["sell"] if p["key"] == 1), None)
    if a is None:
        errors.append("player A missing from sell list")
    else:
        cell = a["cells"]["fantasypros"]
        if cell["value"] is not None or cell["gap"] is not None or not cell["reason"]:
            errors.append(f"missing chart value must be null gap + reason, never 0: {cell}")
        if a["cells"]["cbs"]["gap"] != 2.0 or a["cells"]["usatoday"]["gap"] != 5.0:
            errors.append(f"per-chart gaps wrong for A: {a['cells']}")
    if result["omitted"] != 1 or result["compared"] != 4:
        errors.append(f"player without our value must be left out and counted: omitted={result['omitted']} compared={result['compared']}")
    every = result["sell"] + result["buy"]
    if any("espn_vorp" in p["cells"] for p in every):
        errors.append("VORP vs waivers must never be paired with trade-value points")
    if 3 in {p["key"] for p in every}:
        errors.append("a zero gap is neither a buy nor a sell")
    if result["defaultCharts"]["used"] != ["usatoday", "fantasycalc"]:
        errors.append(f"default charts must be current-week available only: {result['defaultCharts']}")
    skipped = {s["key"]: s["reason"] for s in result["defaultCharts"]["skipped"]}
    if "older week" not in skipped.get("cbs", "") or "fantasypros" not in skipped:
        errors.append(f"skipped charts need a reason: {skipped}")
    if result["olderCharts"]["used"] != ["usatoday", "fantasycalc", "cbs"]:
        errors.append(f"older-week opt-in wrong: {result['olderCharts']}")
    if result["onlyCharts"]["used"] != ["fantasycalc"]:
        errors.append(f"single-chart filter wrong: {result['onlyCharts']}")
    return errors


MUTATIONS = {
    "sign flipped": ("const gap = value - ours;", "const gap = ours - value;"),
    "missing read as zero": ("const value = row.values[chart];", "const value = row.values[chart] ?? 0;"),
    "older weeks by default": ("else if (item.stale && !includeOlder)", "else if (false)"),
    "missing ours read as zero": ("const ours = row.values ? row.values[OUR_KEY] : null;",
                                  "const ours = (row.values && row.values[OUR_KEY]) || 0;"),
}


class TradeTargetsTest(unittest.TestCase):
    def test_gap_rules(self):
        self.assertEqual(check(run_targets(TARGETS_JS)), [])

    def test_checks_fail_on_broken_builds(self):
        source = TARGETS_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"targets_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertNotEqual(check(run_targets(broken)), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
