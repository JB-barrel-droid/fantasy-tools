"""v2 Trade targets: the gap math in app/v2/targets.js.

The tab's only arithmetic is gap = published chart value − our value (DDF
Value by default, JEG-455), per player per chart, on the engine's own rows.
These checks pin:

  * the sign: a chart paying more than us is a sell target (positive gap);
  * a missing value on either side gives no gap (null + reason), never 0, and a
    player without our value is left out and counted;
  * VORP vs waivers (a different unit) is never paired with anything;
  * every available chart is compared, including one still on an earlier week
    (JEG-459: the opt-in checkbox is gone), and such a chart is listed in
    `prior` so the page can badge it;
  * our value is the DDF Value (ddf_value) by default (JEG-455, Jeremy
    2026-10-08); ESPN, CBS rest-of-season and Razzball projections stay as
    alternatives, each read from that series only; an unavailable one is
    offered disabled with a reason;
  * a chart value at or below that chart's waiver line (0 after indexing) is
    never a buy target and gets no gap (Jeremy, 2026-10-07).

Discrimination: test_checks_fail_on_broken_builds runs the same checks against
mutated copies of targets.js (sign flipped, missing read as 0, prior-week
chart dropped, prior-week chart not flagged, missing ours read as 0, waiver rule removed, chosen series
ignored, unavailable series offered as available, default reverted to ESPN, DDF Value dropped from the
choices) and requires every one to fail.
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

# ddf_value differs from espn on purpose, so the default (DDF Value) and the ESPN alternative give different lists.
ROWS = [
    {"player_key": 1, "name": "A", "values": {"ddf_value": 12.0, "espn": 10.0, "cbsros": 14.0, "usatoday": 15.0, "fantasycalc": 8.0, "fantasypros": None, "cbs": 12.0}},
    {"player_key": 2, "name": "B", "values": {"ddf_value": None, "espn": None, "usatoday": 30.0}},
    {"player_key": 3, "name": "C", "values": {"ddf_value": 20.0, "espn": 20.0, "usatoday": 20.0}},
    {"player_key": 4, "name": "D", "values": {"ddf_value": 25.0, "espn": 5.0, "fantasycalc": 25.0, "espn_vorp": 99.0}},
    {"player_key": 5, "name": "E", "values": {"ddf_value": 10.0, "espn": 30.0, "cbsros": 5.0, "usatoday": 10.0, "espn_vorp": 1.0}},
    # F: USA Today puts F at its waiver line (0); FantasyCalc still pays 9 < 12.
    {"player_key": 6, "name": "F", "values": {"ddf_value": 12.0, "espn": 12.0, "usatoday": 0.0, "fantasycalc": 9.0}},
    # G: the only chart has G at its waiver line: never a buy target. No DDF Value.
    {"player_key": 7, "name": "G", "values": {"ddf_value": None, "espn": 8.0, "usatoday": 0.0}},
]
INFO = [
    {"key": "espn", "available": True, "stale": False},
    {"key": "ddf_value", "available": True, "stale": False, "composite": True},
    {"key": "usatoday", "available": True, "stale": False, "week": 5},
    {"key": "fantasycalc", "available": True, "stale": False, "week": 5},
    {"key": "fantasypros", "available": False, "stale": False, "paused": True},
    {"key": "cbs", "available": True, "stale": True, "week": 4},
    {"key": "cbsros", "available": True, "stale": False},
    {"key": "razzball", "available": False, "stale": False},
]

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const brief = p => ({key: p.row.player_key, ours: p.ours, cells: p.cells,
  bestSell: p.bestSell, bestBuy: p.bestBuy});
const d = T.buildTargets(input.rows, input.charts);
const r = T.buildTargets(input.rows, input.charts, {ours: "espn"});
const c = T.buildTargets(input.rows, input.charts, {ours: "cbsros"});
console.log(JSON.stringify({
  ddf: {ours: d.ours, sell: d.sell.map(brief), buy: d.buy.map(brief), compared: d.compared, omitted: d.omittedNoOurs},
  sell: r.sell.map(brief), buy: r.buy.map(brief), compared: r.compared, omitted: r.omittedNoOurs,
  cbsros: {ours: c.ours, sell: c.sell.map(brief), buy: c.buy.map(brief), omitted: c.omittedNoOurs},
  choices: T.ourChoices(input.info), ourKeys: T.OUR_KEYS,
  defaultCharts: T.chartsToCompare(input.info, {}),
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
    if result["ourKey"] != "ddf_value":
        errors.append(f"our value must default to the DDF Value (JEG-455), got {result['ourKey']}")
    dd = result["ddf"]
    dd_sell = [(p["key"], p["ours"], p["bestSell"]) for p in dd["sell"]]
    dd_buy = [(p["key"], p["ours"], p["bestBuy"]) for p in dd["buy"]]
    if (dd["ours"] != "ddf_value" or dd_sell != [(1, 12.0, {"chart": "usatoday", "gap": 3.0})]
            or dd_buy != [(1, 12.0, {"chart": "fantasycalc", "gap": -4.0}), (6, 12.0, {"chart": "fantasycalc", "gap": -3.0})]
            or dd["omitted"] != 2 or dd["compared"] != 5):
        errors.append(f"the default must read the engine's ddf_value series only: {dd}")
    # From here on: the ESPN alternative (picked explicitly).
    sell = [(p["key"], p["bestSell"]) for p in result["sell"]]
    buy = [(p["key"], p["bestBuy"]) for p in result["buy"]]
    if sell != [(4, {"chart": "fantasycalc", "gap": 20.0}), (1, {"chart": "usatoday", "gap": 5.0})]:
        errors.append(f"sell list wrong (chart pays more = positive gap, largest first): {sell}")
    if buy != [(5, {"chart": "usatoday", "gap": -20.0}), (6, {"chart": "fantasycalc", "gap": -3.0}),
               (1, {"chart": "fantasycalc", "gap": -2.0})]:
        errors.append(f"buy list wrong (chart pays less = negative gap, most negative first; "
                      f"a chart at its waiver line is never a buy): {buy}")
    for p in result["buy"]:
        for chart, cell in p["cells"].items():
            if cell["value"] is not None and cell["value"] <= 0 and (cell["gap"] is not None or not cell.get("atWaiver")):
                errors.append(f"{p['key']}/{chart}: chart value at the waiver line must have no gap: {cell}")
        best = p["cells"][p["bestBuy"]["chart"]]["value"]
        if best is None or best <= 0:
            errors.append(f"{p['key']}: buy target from a chart at its waiver line ({best})")
    if 7 in {p["key"] for p in result["buy"] + result["sell"]}:
        errors.append("G is at the only chart's waiver line: never a target")
    a = next((p for p in result["sell"] if p["key"] == 1), None)
    if a is None:
        errors.append("player A missing from sell list")
    else:
        cell = a["cells"]["fantasypros"]
        if cell["value"] is not None or cell["gap"] is not None or not cell["reason"]:
            errors.append(f"missing chart value must be null gap + reason, never 0: {cell}")
        if a["cells"]["cbs"]["gap"] != 2.0 or a["cells"]["usatoday"]["gap"] != 5.0:
            errors.append(f"per-chart gaps wrong for A: {a['cells']}")
    if result["omitted"] != 1 or result["compared"] != 6:
        errors.append(f"player without our value must be left out and counted: omitted={result['omitted']} compared={result['compared']}")
    every = result["sell"] + result["buy"]
    if any("espn_vorp" in p["cells"] for p in every):
        errors.append("VORP vs waivers must never be paired with trade-value points")
    if 3 in {p["key"] for p in every}:
        errors.append("a zero gap is neither a buy nor a sell")
    # JEG-459 (rule changed): a chart still on an earlier week is always compared, and flagged.
    if result["defaultCharts"]["used"] != ["usatoday", "fantasycalc", "cbs"]:
        errors.append(f"every available chart must be compared, prior week included: {result['defaultCharts']}")
    if result["defaultCharts"].get("prior") != ["cbs"]:
        errors.append(f"the prior-week chart must be flagged (and only it): {result['defaultCharts']}")
    skipped = {s["key"]: s["reason"] for s in result["defaultCharts"]["skipped"]}
    if set(skipped) != {"fantasypros"} or not skipped["fantasypros"]:
        errors.append(f"only unavailable charts are skipped, with a reason: {skipped}")
    if result["onlyCharts"]["used"] != ["fantasycalc"]:
        errors.append(f"single-chart filter wrong: {result['onlyCharts']}")
    if result["ourKeys"] != ["ddf_value", "espn", "cbsros", "razzball"]:
        errors.append(f"our value choices must be DDF Value, then the three projections: {result['ourKeys']}")
    cb = result["cbsros"]
    cb_sell = [(p["key"], p["ours"], p["bestSell"]) for p in cb["sell"]]
    cb_buy = [(p["key"], p["ours"], p["bestBuy"]) for p in cb["buy"]]
    if (cb["ours"] != "cbsros" or cb_sell != [(5, 5.0, {"chart": "usatoday", "gap": 5.0}), (1, 14.0, {"chart": "usatoday", "gap": 1.0})]
            or cb_buy != [(1, 14.0, {"chart": "fantasycalc", "gap": -6.0})] or cb["omitted"] != 5):
        errors.append(f"our value = CBS rest-of-season must read the cbsros series only: {cb}")
    choices = {c["key"]: c for c in result["choices"]}
    if not all(choices.get(k, {}).get("available") for k in ("ddf_value", "espn", "cbsros")):
        errors.append(f"available series must be offered: {choices}")
    rz = choices.get("razzball", {})
    if rz.get("available") is not False or not rz.get("reason"):
        errors.append(f"an unavailable series must be offered disabled with a reason: {rz}")
    return errors


MUTATIONS = {
    "sign flipped": ("const gap = value - ours;", "const gap = ours - value;"),
    "missing read as zero": ("const value = row.values[chart];", "const value = row.values[chart] ?? 0;"),
    "prior-week chart dropped": ("      else used.push(key);", "      else if (!item.stale) used.push(key);"),
    "prior-week chart not flagged": ("if (item && item.available && item.stale) prior.push(key);", "if (false) prior.push(key);"),
    "missing ours read as zero": ("const ours = row.values ? row.values[ourKey] : null;",
                                  "const ours = (row.values && row.values[ourKey]) || 0;"),
    "waiver rule removed": ("if (value <= 0) {", "if (false) {"),
    "chosen series ignored": ("const ourKey = (opts && opts.ours) || OUR_KEY;", "const ourKey = OUR_KEY;"),
    "unavailable series offered": ("const available = Boolean(item && item.available);", "const available = true;"),
    # JEG-455
    "default reverted to ESPN": ("const OUR_KEY = OUR_KEYS[0];", "const OUR_KEY = OUR_KEYS[1];"),
    "DDF Value dropped from the choices": ('const OUR_KEYS = ["ddf_value", "espn", "cbsros", "razzball"];',
                                           'const OUR_KEYS = ["espn", "cbsros", "razzball"];'),
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
