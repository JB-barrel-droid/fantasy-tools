"""v2 Compare: Trade chart average must be the mean of the per-chart rows, not the DDF blend (JEG-832).

Live bug: the "Trade chart average" card showed the same number as DDF Value on every trade
(+4.8, +6.3, +5.1, +12.7, +21.5), even when all three compared chart rows (USA Today, FantasyCalc,
FantasyPros) were negative. The Deal read was built on that card and said "the trade charts agree"
while the chart rows contradicted it.

Root cause: dealRead used the ddf_value_charts engine series, which is a DDF-weighted blend of the
chart inputs. When projections are held, DDF Value IS the blend of the same charts, so
ddf_value == ddf_value_charts by construction.

Fix: dealRead now takes chartKeys and computes the mean of the per-chart rescaled nets (the same
rows Compare's table shows). The deal read card, the deal read text, and the finder-to-compare
path all use this mean.

Discrimination: test_guard_fails_on_broken_builds serves trade.js with the chartKeys parameter
removed from dealRead and asserts that the test catches it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRADE_JS = ROOT / "app" / "v2" / "trade.js"

CHARTS = ["usatoday", "fantasycalc", "fantasypros"]


def player(key, ddf, usat, fc, fp):
    return {"player_key": key, "name": f"P{key}",
            "values": {"ddf_value": ddf, "ddf_value_projections": ddf * 0.9,
                       "usatoday": usat, "fantasycalc": fc, "fantasypros": fp}}


# Fixture: DDF Value says you win (+20 on 120 traded), but every chart row says you lose.
# USA Today: give 60, receive 45, net -15; FantasyCalc: give 55, receive 40, net -15;
# FantasyPros: give 70, receive 50, net -20. Mean chart net = (-15 + -15 + -20) / 3 ≈ -16.67.
GIVE = [player(1, 50, 60, 55, 70)]
RECEIVE = [player(2, 70, 45, 40, 50)]

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const deal = T.dealRead(input.give, input.receive, input.charts);
console.log(JSON.stringify({
  kind: deal.kind,
  marketNet: deal.market.net,
  marketSide: deal.market.side,
  valueNet: deal.value.net,
  valueSide: deal.value.side,
  tooFew: deal.market.tooFew || false,
  chartCount: deal.market.chartCount || null,
  title: deal.title || null,
  text: deal.text || null
}));
"""


def run_deal(trade_js: Path, give=None, receive=None, charts=None) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    payload = json.dumps({"give": give or GIVE, "receive": receive or RECEIVE, "charts": charts or CHARTS})
    out = subprocess.run([node, "-e", HARNESS, str(trade_js), payload], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"node failed: {out.stderr}")
    return json.loads(out.stdout)


def check(trade_js: Path) -> list[str]:
    errors = []
    d = run_deal(trade_js)

    # 1. The chart average net must be negative (≈ -16.67), not +20 like DDF Value.
    if d["marketNet"] is None:
        errors.append(f"market net is null (tooFew={d['tooFew']})")
    elif d["marketNet"] >= 0:
        errors.append(f"market net {d['marketNet']:.1f} should be negative (chart rows are all negative)")

    # 2. The market side must be "lose" (you lose on the charts).
    if d["marketSide"] != "lose":
        errors.append(f"market side is {d['marketSide']!r}, expected 'lose'")

    # 3. DDF Value net must still be positive (the fix does not change the value card).
    if d["valueNet"] is None or d["valueNet"] <= 0:
        errors.append(f"value net {d['valueNet']} should be positive")

    # 4. The deal read must NOT say "the trade charts agree".
    if d["text"] and "trade charts agree" in d["text"]:
        errors.append(f"deal read says 'trade charts agree' when they disagree: {d['text']!r}")

    # 5. The title should be the arbitrage case (win on value, lose on market).
    if d["title"] != "Value win, charts say you lose: send it":
        errors.append(f"title is {d['title']!r}, expected 'Value win, charts say you lose: send it' (win|lose)")

    return errors


# Mutation: revert dealRead to use the old ddf_value_charts blend (remove chartKeys parameter use).
MUTATION_ANCHOR = "const chartRows = chartKeys && chartKeys.length ? compareTrade(giveRows, receiveRows, chartKeys).rows : [];"
MUTATION_REPLACE = "const chartRows = compareTrade(giveRows, receiveRows, [DEAL_KEYS.market]).rows;"


class DealReadChartAvgTest(unittest.TestCase):
    def test_chart_average_is_mean_of_rows(self):
        """The Trade chart average must be the mean of per-chart rows, not the DDF blend."""
        self.assertEqual(check(TRADE_JS), [])

    def test_guard_fails_on_broken_builds(self):
        """Reverting to ddf_value_charts must fail the regression guard."""
        source = TRADE_JS.read_text(encoding="utf-8")
        self.assertIn(MUTATION_ANCHOR, source, "mutation anchor is stale")
        patched = source.replace(MUTATION_ANCHOR, MUTATION_REPLACE, 1)
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".js", mode="w", encoding="utf-8", delete=False) as f:
            f.write(patched)
            f.flush()
            result = check(Path(f.name))
        self.assertNotEqual(result, [], "mutation test did not catch the revert to ddf_value_charts")


if __name__ == "__main__":
    unittest.main()
