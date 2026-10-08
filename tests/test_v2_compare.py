"""v2 Compare a trade: the per-source sums in app/v2/trade.js.

The tab's only arithmetic is, for each exact series on its own:

    net = sum(values of players you get) − sum(values of players you give)

These checks pin (frame 22 rule):

  * the sign: getting more than you give in a series is a positive net;
  * each row reads one series only: no blend across series, no overall verdict;
  * a player with no value in a series leaves that row with no sums and no net
    (null plus the missing players), never a 0 standing in for the value;
  * a real 0 (at or below that series' waiver line) is a value and counts;
  * a player the engine has no row for is missing in every series.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against
mutated copies of trade.js (sign flipped, missing read as 0, one side's sum
read from another series, give side dropped) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE_JS = ROOT / "app" / "v2" / "trade.js"

A = {"player_key": 1, "name": "A", "values": {"espn": 30.0, "fantasycalc_adjusted": 25.0, "usatoday": 10.0, "espn_vorp": 50.0}}
B = {"player_key": 2, "name": "B", "values": {"espn": 12.5, "fantasycalc_adjusted": None, "usatoday": 0.0, "espn_vorp": 9.0}}
C = {"player_key": 3, "name": "C", "values": {"espn": 40.0, "fantasycalc_adjusted": 20.0, "usatoday": 18.0, "espn_vorp": 70.0}}
GONE = {"player_key": 4, "name": "D", "values": {}}
SERIES = ["espn", "fantasycalc_adjusted", "usatoday", "espn_vorp"]

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const r = T.compareTrade(input.give, input.receive, input.series);
console.log(JSON.stringify(r.rows.map(row => ({key: row.key, give: row.give, receive: row.receive, net: row.net,
  missing: row.missing.map(m => [m.row.player_key, m.side])}))));
"""


def run(trade_js: Path, give, receive, series=SERIES):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, str(trade_js),
                          json.dumps({"give": give, "receive": receive, "series": series})],
                         check=True, capture_output=True, text=True)
    return {row["key"]: row for row in json.loads(out.stdout)}


def check(trade_js: Path) -> list[str]:
    errors = []
    # Give A + B, get C.
    rows = run(trade_js, [A, B], [C])
    if list(rows) != SERIES:
        errors.append(f"one row per series in order, got {list(rows)}")
    espn = rows.get("espn", {})
    if (espn.get("give"), espn.get("receive"), espn.get("net")) != (42.5, 40.0, -2.5):
        errors.append(f"espn: expected give 42.5, get 40.0, net -2.5; got {espn}")
    fc = rows.get("fantasycalc_adjusted", {})
    if fc.get("net") is not None or fc.get("give") is not None or fc.get("missing") != [[2, "give"]]:
        errors.append(f"fantasycalc_adjusted: B has no value, so no sums and no net; got {fc}")
    usat = rows.get("usatoday", {})
    # B's 0.0 is a real value at the waiver line: it counts.
    if (usat.get("give"), usat.get("receive"), usat.get("net"), usat.get("missing")) != (10.0, 18.0, 8.0, []):
        errors.append(f"usatoday: expected give 10.0 (0.0 counts), get 18.0, net +8.0; got {usat}")
    vorp = rows.get("espn_vorp", {})
    if vorp.get("net") != 11.0:
        errors.append(f"espn_vorp: its own series only, net 70 − 59 = 11; got {vorp}")
    # A player the engine has no row for is missing everywhere.
    rows = run(trade_js, [A], [C, GONE])
    for key, row in rows.items():
        if row["net"] is not None or [4, "receive"] not in row["missing"]:
            errors.append(f"{key}: unpriced player D must leave the row without a net; got {row}")
    return errors


class CompareTradeTest(unittest.TestCase):
    def test_sums_per_series(self):
        self.assertEqual(check(TRADE_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        broken = {
            "sign flipped": source.replace("net: receiveSum - giveSum", "net: giveSum - receiveSum", 1),
            "missing read as zero": source.replace(
                "const value = row.values ? row.values[key] : null;\n        if (finite(value)) giveSum += value;",
                "const value = (row.values ? row.values[key] : null) ?? 0;\n        if (finite(value)) giveSum += value;", 1),
            "other series read": source.replace(
                "if (finite(value)) receiveSum += value;",
                "if (finite(value)) receiveSum += row.values.espn;", 1),
            "give side dropped": source.replace("giveRows.forEach(row => {", "[].forEach(row => {", 1),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in broken.items():
                with self.subTest(mutation=name):
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                    path = Path(tmp) / f"{name.replace(' ', '_')}.js"
                    path.write_text(body, encoding="utf-8")
                    self.assertNotEqual(check(path), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
