"""v2 Trade targets: the market-consensus rule in app/v2/targets.js.

Check 1 (JEG-677, Jeremy JEG-461 2026-10-08 / JEG-476) on the engine's own rows:

  * consensus = the MEDIAN of the indexed charts that price the player (a
    finite 0 counts; a missing value is left out, never read as 0);
  * a player is a target only with 2+ charts priced, a consensus above the
    waiver line, and a strict majority of those charts on the same side of our
    value as the consensus ("N of M charts agree");
  * Sell: consensus gap > 0, largest first. Buy: gap < 0, most negative first;
  * our value defaults to DDF Projections (ddf_value_projections); DDF Value,
    ESPN, CBS rest-of-season and Razzball stay as choices, each read from its
    own series only, an unavailable one offered disabled with a reason;
  * every available chart is compared, including one still on an earlier week
    (JEG-459), listed in `prior`;
  * a chart value at or below its waiver line shows but has no per-chart gap;
  * VORP vs waivers (a different unit) is never paired with anything.

The expected lists come from an independent Python recomputation (`reference`).
Discrimination: test_checks_fail_on_broken_builds runs the same checks against
mutated copies of targets.js (mean for median, majority rule dropped or made
non-strict, single chart allowed, consensus at the waiver line allowed, sign
flipped, missing read as 0, default reverted, ...) and requires every one to
fail.
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

# ddf_value differs from espn on purpose, so the DDF Value and ESPN runs give different lists.
ROWS = [
    {"player_key": 1, "name": "A", "values": {"ddf_value": 12.0, "espn": 10.0, "cbsros": 14.0, "usatoday": 15.0, "fantasycalc": 8.0, "fantasypros": None, "cbs": 12.0}},
    {"player_key": 2, "name": "B", "values": {"ddf_value": None, "espn": None, "usatoday": 30.0}},
    {"player_key": 3, "name": "C", "values": {"ddf_value": 20.0, "espn": 20.0, "usatoday": 20.0}},
    {"player_key": 4, "name": "D", "values": {"ddf_value": 25.0, "espn": 5.0, "fantasycalc": 25.0, "usatoday": 20.0, "espn_vorp": 99.0}},
    {"player_key": 5, "name": "E", "values": {"ddf_value": 10.0, "espn": 30.0, "cbsros": 5.0, "usatoday": 10.0, "fantasycalc": 4.0, "espn_vorp": 1.0}},
    # F: USA Today puts F at its waiver line (0); FantasyCalc still pays 9 < 12.
    {"player_key": 6, "name": "F", "values": {"ddf_value": 12.0, "espn": 12.0, "usatoday": 0.0, "fantasycalc": 9.0}},
    # G: the only chart has G at its waiver line: never a target. No DDF Value.
    {"player_key": 7, "name": "G", "values": {"ddf_value": None, "espn": 8.0, "usatoday": 0.0}},
]


def _both(key: int, name: str, ours: float, **charts) -> dict:
    """ddf_value and ddf_value_projections carry the same ours, so the default and DDF Value runs both see it."""
    return {"player_key": key, "name": name, "values": {"ddf_value": ours, "ddf_value_projections": ours, **charts}}


CONSENSUS_ROWS = [
    _both(31, "K", 10.0, usatoday=20.0, fantasycalc=20.0, cbs=5.0),                    # median 20, 2 of 3 above: sell
    _both(32, "L", 10.0, usatoday=30.0, fantasycalc=5.0, cbs=5.0),                     # median 5, 2 of 3 below: buy
    _both(33, "M", 10.0, usatoday=30.0, fantasycalc=5.0),                              # median 17.5 but 1 of 2: no majority
    _both(34, "N", 10.0, usatoday=30.0),                                               # one chart only: never a target
    _both(35, "P", 10.0, usatoday=30.0, fantasycalc=12.0, cbs=9.0, fantasypros=9.0),   # median 10.5, 2 of 4: no majority
    _both(36, "Q", 10.0, usatoday=0.0, fantasycalc=0.0, cbs=0.0),                      # consensus at the waiver line: never a buy
    _both(37, "R", 10.0, usatoday=40.0, fantasycalc=3.0, cbs=2.0),                     # one huge chart, two below: buy by median
    _both(38, "S", 10.0, usatoday=10.0, fantasycalc=10.0, cbs=10.0),                   # all level: no gap
    _both(39, "T", 4.0, usatoday=9.0, fantasycalc=7.0, cbs=None),                      # median 8, 2 of 2 above, one missing: sell
]

INFO = [
    {"key": "espn", "available": True, "stale": False},
    {"key": "ddf_value", "available": True, "stale": False, "composite": True},
    {"key": "ddf_value_projections", "available": True, "stale": False},
    {"key": "usatoday", "available": True, "stale": False, "week": 5},
    {"key": "fantasycalc", "available": True, "stale": False, "week": 5},
    {"key": "fantasypros", "available": False, "stale": False, "paused": True},
    {"key": "cbs", "available": True, "stale": True, "week": 4},
    {"key": "cbsros", "available": True, "stale": False},
    {"key": "razzball", "available": False, "stale": False},
]

MARKET_ROWS = [
    {"player_key": 21, "name": "I", "values": {"ddf_value": 10.0, "usatoday": 14.0, "fantasycalc": 6.0, "cbs": 10.0}},
    {"player_key": 22, "name": "J", "values": {"ddf_value": 10.0, "usatoday": 22.0, "fantasycalc": None, "cbs": 0.0}},
]


def median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def reference(rows: list[dict], ours_key: str, charts: list[str]) -> dict:
    """The independent calculation of Check 1: {side: [(key, gap, agree, of)]} in list order."""
    sell, buy = [], []
    for order, row in enumerate(rows):
        ours = row["values"].get(ours_key)
        if ours is None:
            continue
        priced = [row["values"][c] for c in charts if row["values"].get(c) is not None]
        if len(priced) < 2:
            continue
        consensus = median(priced)
        gap = consensus - ours
        if consensus <= 0 or gap == 0:
            continue
        agree = sum(1 for v in priced if (v > ours if gap > 0 else v < ours))
        if agree * 2 <= len(priced):
            continue
        (sell if gap > 0 else buy).append((order, row["player_key"], gap, agree, len(priced)))
    sell.sort(key=lambda t: (-t[2], t[0]))
    buy.sort(key=lambda t: (t[2], t[0]))
    return {"sell": [t[1:] for t in sell], "buy": [t[1:] for t in buy]}


def recompute_market(row: dict, charts: list[str]) -> dict:
    """The independent calculation: median of the finite chart values (a 0 counts), ours minus it."""
    ours = row["values"]["ddf_value"]
    priced = [row["values"][c] for c in charts if row["values"].get(c) is not None]
    consensus = median(priced)
    return {"value": consensus, "count": len(priced), "left": len(charts) - len(priced), "diff": ours - consensus,
            "equal": f"{ours:.1f}" == f"{consensus:.1f}"}


HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const brief = p => ({key: p.row.player_key, ours: p.ours, cells: p.cells, market: p.market});
const run = (rows, opts) => { const r = T.buildTargets(rows, input.charts, opts); return {ours: r.ours, sell: r.sell.map(brief),
  buy: r.buy.map(brief), compared: r.compared, omitted: r.omittedNoOurs}; };
// Jeremy, 2026-10-08: a one-source DDF Value (ddfLowConfidence) is still a target.
const lc = T.buildTargets([{player_key: 9, name: "H", values: {ddf_value: 3.0, usatoday: 9.0, fantasycalc: 8.0}, ddfCount: 1, ddfLowConfidence: true}], ["usatoday", "fantasycalc"], {ours: "ddf_value"});
// JEG-504: consensus cases. I: the median equals our value (10.0) to one decimal;
// J: one chart does not price the player (left out), one at its waiver line (a finite 0 counts).
const mk = T.buildTargets(input.market, ["usatoday", "fantasycalc", "cbs"], {ours: "ddf_value"});
const rows = input.rows.concat(input.consensus);
console.log(JSON.stringify({
  market: mk.players.map(brief),
  lowConfidence: lc.sell.map(p => [p.row.player_key, p.ours, p.market.gap]),
  byDefault: run(rows),
  ddf: run(rows, {ours: "ddf_value"}),
  espn: run(rows, {ours: "espn"}),
  cbsros: run(rows, {ours: "cbsros"}),
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
    payload = json.dumps({"rows": ROWS, "consensus": CONSENSUS_ROWS, "charts": CHARTS, "info": INFO, "market": MARKET_ROWS})
    out = subprocess.run([node, "-e", HARNESS, str(path), payload], capture_output=True, text=True)
    if out.returncode:
        return {"crashed": out.stderr.strip().splitlines()[-1:] or ["no output"]}   # a build that throws fails the checks
    return json.loads(out.stdout)


def lists(run: dict) -> dict:
    return {side: [(p["key"], p["market"]["gap"], p["market"]["agree"], p["market"]["of"]) for p in run[side]]
            for side in ("sell", "buy")}


def check(result: dict) -> list[str]:
    """Return every rule the result breaks (empty list = correct)."""
    if "crashed" in result:
        return [f"targets.js threw: {result['crashed']}"]
    errors = []
    if result["ourKey"] != "ddf_value_projections":
        errors.append(f"our value must default to DDF Projections (JEG-677), got {result['ourKey']}")
    all_rows = ROWS + CONSENSUS_ROWS
    for name, key in (("byDefault", "ddf_value_projections"), ("ddf", "ddf_value"), ("espn", "espn"), ("cbsros", "cbsros")):
        run = result[name]
        if run["ours"] != key:
            errors.append(f"{name}: expected our value series {key}, got {run['ours']}")
        want = reference(all_rows, key, CHARTS)
        got = lists(run)
        for side in ("sell", "buy"):
            if [tuple(x) for x in got[side]] != want[side]:
                errors.append(f"{name} {side} list must follow the consensus rule: want {want[side]}, got {got[side]}")
    # The named cases, on the default series (projections).
    d = lists(result["byDefault"])
    sell_keys = [k for k, *_ in d["sell"]]
    buy_keys = [k for k, *_ in d["buy"]]
    if sell_keys != [31, 39] or buy_keys != [37, 32]:
        errors.append(f"default lists wrong (sell {sell_keys}, buy {buy_keys}); wanted sell [31, 39], buy [37, 32]")
    for key, why in ((33, "1 of 2 is not a majority"), (34, "one chart is not a consensus"),
                     (35, "2 of 4 is not a majority"), (36, "a consensus at the waiver line is never a target"),
                     (38, "no gap")):
        if key in sell_keys + buy_keys:
            errors.append(f"player {key} must not be a target: {why}")
    k = next((p for p in result["byDefault"]["sell"] if p["key"] == 31), None)
    if k is None or (k["market"]["agree"], k["market"]["of"]) != (2, 3) or [d_["side"] for d_ in k["market"]["dots"]] != ["above", "above", "below"]:
        errors.append(f"K must read 2 of 3 charts agree with one dot per chart: {k and k['market']}")
    if k is not None and [k["cells"][c]["gap"] for c in ("usatoday", "fantasycalc", "cbs")] != [10.0, 10.0, -5.0]:
        errors.append(f"per-chart gap = chart value - our value (positive: the chart pays more): {k['cells']}")
    if result["lowConfidence"] != [[9, 3.0, 5.5]]:
        errors.append(f"a one-source (low-confidence) DDF Value must still be a target: {result['lowConfidence']}")
    # Per-chart cells.
    dd = result["ddf"]
    if 1 in {p["key"] for p in dd["sell"] + dd["buy"]}:
        errors.append("DDF Value run: player A (median 12 = ours 12) has no gap and must not be listed")
    sell_e = {p["key"]: p for p in result["espn"]["sell"] + result["espn"]["buy"]}
    five = sell_e.get(5)
    if five is None:
        errors.append("ESPN run: player E missing")
    else:
        cell = five["cells"]["fantasypros"]
        if cell["value"] is not None or cell["gap"] is not None or not cell["reason"]:
            errors.append(f"missing chart value must be null gap + reason, never 0: {cell}")
    f_run = {p["key"]: p for p in result["ddf"]["sell"] + result["ddf"]["buy"]}
    fcell = f_run.get(6, {}).get("cells", {}).get("usatoday")
    if fcell is not None and (fcell["gap"] is not None or not fcell.get("atWaiver")):
        errors.append(f"chart value at the waiver line must have no gap: {fcell}")
    every = result["byDefault"]["sell"] + result["byDefault"]["buy"] + result["ddf"]["sell"] + result["ddf"]["buy"]
    if any("espn_vorp" in p["cells"] for p in every):
        errors.append("VORP vs waivers must never be paired with trade-value points")
    if 7 in {p["key"] for p in every} or 3 in {p["key"] for p in every}:
        errors.append("G (waiver line) and C (no gap) are never targets")
    if result["ddf"]["omitted"] != 2 or result["byDefault"]["omitted"] != len(ROWS):
        errors.append(f"players without our value are left out and counted: ddf={result['ddf']['omitted']} default={result['byDefault']['omitted']}")
    # JEG-459: a chart still on an earlier week is always compared, and flagged.
    if result["defaultCharts"]["used"] != ["usatoday", "fantasycalc", "cbs"]:
        errors.append(f"every available chart must be compared, prior week included: {result['defaultCharts']}")
    if result["defaultCharts"].get("prior") != ["cbs"]:
        errors.append(f"the prior-week chart must be flagged (and only it): {result['defaultCharts']}")
    skipped = {s["key"]: s["reason"] for s in result["defaultCharts"]["skipped"]}
    if set(skipped) != {"fantasypros"} or not skipped["fantasypros"]:
        errors.append(f"only unavailable charts are skipped, with a reason: {skipped}")
    if result["onlyCharts"]["used"] != ["fantasycalc"]:
        errors.append(f"single-chart filter wrong: {result['onlyCharts']}")
    if result["ourKeys"] != ["ddf_value_projections", "ddf_value", "ddf_value_charts", "espn", "cbsros", "razzball"]:
        errors.append(f"our value choices: DDF Projections first, then the other DDF Values, then the projections: {result['ourKeys']}")
    choices = {c["key"]: c for c in result["choices"]}
    if not all(choices.get(k, {}).get("available") for k in ("ddf_value", "ddf_value_projections", "espn", "cbsros")):
        errors.append(f"available series must be offered: {choices}")
    rz = choices.get("razzball", {})
    if rz.get("available") is not False or not rz.get("reason"):
        errors.append(f"an unavailable series must be offered disabled with a reason: {rz}")
    # JEG-504: the consensus and difference equal a recomputation from the engine values (every compared
    # player is returned in `players`, listed or not: I's median equals ours, J has 1 of 2 and is not listed).
    market = {p["key"]: p["market"] for p in result["market"]}
    if not market.get(21, {}).get("equal") or market.get(22, {}).get("equal"):
        errors.append(f"a consensus equal to our value to one decimal is flagged equal (and only then): {market}")
    for row in MARKET_ROWS:
        want = recompute_market(row, ["usatoday", "fantasycalc", "cbs"])
        got = market.get(row["player_key"])
        if got is None:
            errors.append(f"consensus for {row['name']} missing")
            continue
        if got["count"] != want["count"] or got["left"] != want["left"] or got["equal"] != want["equal"] \
                or abs(got["value"] - want["value"]) > 1e-9 or abs(got["diff"] - want["diff"]) > 1e-9:
            errors.append(f"consensus for {row['name']} must be {want}, got {got}")
    return errors


MUTATIONS = {
    "sign flipped": ("const gap = value - ours;\n        cells[chart]", "const gap = ours - value;\n        cells[chart]"),
    "consensus sign flipped": ("const diff = ours - value;\n    const gap = value - ours;", "const diff = ours - value;\n    const gap = ours - value;"),
    "missing read as zero": ("const value = row.values[chart];", "const value = row.values[chart] ?? 0;"),
    "prior-week chart dropped": ("      else used.push(key);", "      else if (!item.stale) used.push(key);"),
    "prior-week chart not flagged": ("if (item && item.available && item.stale) prior.push(key);", "if (false) prior.push(key);"),
    "missing ours read as zero": ("const ours = row.values ? row.values[ourKey] : null;",
                                  "const ours = (row.values && row.values[ourKey]) || 0;"),
    "waiver rule removed": ("if (value <= 0) {", "if (false) {"),
    "chosen series ignored": ("const ourKey = (opts && opts.ours) || OUR_KEY;", "const ourKey = OUR_KEY;"),
    "unavailable series offered": ("const available = Boolean(item && item.available);", "const available = true;"),
    "default reverted to DDF Value": ("const OUR_KEY = OUR_KEYS[0];", "const OUR_KEY = OUR_KEYS[1];"),
    "one-source player left out": ("      if (!finite(ours)) {", "      if (!finite(ours) || row.ddfLowConfidence) {"),
    # JEG-677
    "mean instead of median": ("const value = median(values);", "const value = values.reduce((a, b) => a + b, 0) / values.length;"),
    "majority rule dropped": (" && agree * 2 > priced.length;", ";"),
    "majority not strict": ("agree * 2 > priced.length", "agree * 2 >= priced.length"),
    "single chart allowed": ("priced.length >= 2 && value > 0", "priced.length >= 1 && value > 0"),
    "consensus at waiver line allowed": ("priced.length >= 2 && value > 0", "priced.length >= 2"),
    "consensus ignores a finite zero": ("const values = priced.map(key => cells[key].value);",
                                        "const values = priced.map(key => cells[key].value).filter(v => v > 0);"),
    "agreement counted on the wrong side": ('(side === "sell" ? v > ours : v < ours)', '(side === "sell" ? v < ours : v > ours)'),
    "equal never flagged": ("equal: ours.toFixed(1) === value.toFixed(1),\n      side", "equal: false,\n      side"),
    "DDF Value dropped from the choices": ('const OUR_KEYS = ["ddf_value_projections", "ddf_value",',
                                           'const OUR_KEYS = ["ddf_value_projections",'),
}


class TradeTargetsTest(unittest.TestCase):
    def test_consensus_rules(self):
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
