"""v2 Compare: the Deal read never contradicts "Will they accept?" (JEG-886, contract CT-08 / CT-02).

Live bug (round-3 product review, 2026-10-22): give Hall + Higgins for Nacua. The chart rows were
+0.5, -7.2, +9.1; their average, +0.8, put the market side at "even", so the Deal read said "Value win at
a fair market price ... little reason to refuse" two lines under "Will they accept? Unlikely (1 of 3 trade
charts have the other manager winning or even)". The average hid a 16-point disagreement between the charts.

Rule (trade.js dealRead, DEAL_SPLIT_ACCEPT): each chart-average column's copy assumes one answer to
"Will they accept?" (charts win for you: Unlikely; charts even or lose: Likely). dealRead counts the
charts the same way tradeHeadlines does (the chart's net is even or below, using the one even band:
max(1, 3% of that chart's average side), JEG-1125 option A, Jeremy 2026-10-29; before that it was net <= 0
as shown); when that count's answer is not the one the
column assumes, market.split is set, the read names the split (range of the per-chart nets and the count)
and the title, action and text replace the cell copy. The cell (grid outline, card side) stays the
average's, and the headline logic is unchanged.

These checks pin, against an independent recomputation on hand-built trades:
  * the live fixture: under JEG-1125 option A the +0.5 chart is even (inside its 1.4-point band), so 2 of 3
    charts have the other manager winning or even, "Will they accept?" is Likely and agrees with the even
    column: cell win|even, no split (before A: split, 1 of 3, Unlikely);
  * a hand-built win|even trade whose charts lean your way past their bands still splits and names its range;
  * for every hand-built trade, "little reason to refuse" / "fair" appears only when the headline's accept
    is Likely, "will likely see a loss" only when it is Unlikely, and the split read exactly when the
    count disagrees with the column (win|Likely, even|Toss-up, lose|Unlikely split; win|Unlikely,
    even|Likely, lose|Likely do not);
  * the split changes neither the cell nor the headline.

Discrimination: test_checks_fail_on_broken_builds mutates trade.js (split ignored, the column table
wrong, the count flipped, the split text without the range) and requires each to fail.
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
CHARTS = ["usatoday", "fantasypros", "cbs", "fantasycalc"]
SERIES = ["ddf_value", "ddf_value_projections"] + CHARTS

FAIR = ("fair market price", "little reason to refuse", "easy for them")
HARD_SELL = ("will likely see a loss",)
DEAL_SPLIT_ACCEPT = {"win": "Unlikely", "even": "Likely", "lose": "Likely"}


def player(key, ddf, proj, usat, fp, cbs, fc=None):
    """fc None leaves FantasyCalc unpriced, so that chart stays out of the count (three charts)."""
    return {"player_key": key, "name": f"P{key}",
            "values": {"ddf_value": ddf, "ddf_value_projections": proj, "usatoday": usat, "fantasypros": fp, "cbs": cbs,
                       "fantasycalc": fc}}


def trade(ddf_net, chart_nets, base=48.0, proj_net=None):
    """One give row at `base` on every series, one receive row at base + net per series (3 or 4 charts)."""
    proj_net = ddf_net if proj_net is None else proj_net
    give = [player(1, base, base, base, base, base, base if len(chart_nets) == 4 else None)]
    receive = [player(2, base + ddf_net, base + proj_net, *(base + n for n in chart_nets))]
    return give, receive


# name -> (give, receive)
CASES = {
    # The live fixture: Hall (20/24/27/20) + Higgins (17/24/28/19) for Nacua (48.1/48.5/47.8/48.1):
    # DDF +11.1, charts +0.5 / -7.2 / +9.1 (average +0.8, even), 1 of 3 has the other manager winning or even.
    "hall-higgins-for-nacua": ([player(1, 20, 20, 24, 27, 20), player(2, 17, 17, 24, 28, 19)],
                               [player(3, 48.1, 47.8, 48.5, 47.8, 48.1)]),
    "win|even accept Likely": trade(10, [0.5, -0.5, 0.0]),            # no split: fair copy allowed
    "win|even accept Unlikely": trade(10, [2, 2, -3]),                # split: 2 charts past their 1.5 band your way
    "win|even accept Toss-up": trade(10, [2, 2, -2, -2]),             # split
    "win|even inside every band": trade(10, [0.9, 0.9, 0.9]),         # JEG-1125 A: all even, Likely, fair copy allowed
    "win|win accept Unlikely": trade(10, [6, 5, 4]),                  # no split: hard sell
    "win|win accept Likely": trade(10, [20, -2, -2]),                 # split: average win, 2 of 3 for them
    "win|lose accept Likely": trade(10, [-6, -5, -4]),                # no split: arbitrage
    "win|lose accept Unlikely": trade(10, [-20, 2, 2]),               # split
    "even|even accept Likely": trade(0, [0.0, 0.0, 0.0]),             # no split
    "even|even accept Unlikely": trade(0, [2, 2, -3]),                # split
    "lose|lose accept Likely": trade(-10, [-6, -5, -4]),              # no split
    "lose|lose accept Unlikely": trade(-10, [-12, 3, 3]),             # split
    "lose|win accept Unlikely": trade(-10, [6, 5, 4]),                # no split: trap
}

HARNESS = """
const T = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
console.log(JSON.stringify(Object.fromEntries(Object.entries(input.cases).map(([name, [give, receive]]) => {
  const deal = T.dealRead(give, receive, input.charts);
  const rows = T.compareTrade(give, receive, input.series).rows;
  const h = T.tradeHeadlines(rows, "ddf_value", {chartKeys: input.charts, lowConfidence: false, deal});
  return [name, {kind: deal.kind, cell: deal.cell || null, side: deal.market.side, split: Boolean(deal.market.split),
    charts: deal.market.charts || null, title: deal.title || "", action: deal.action || "", text: deal.text || "",
    propose: h.propose.answer, accept: h.accept.answer}];
}))));
"""


def run(trade_js: Path) -> dict:
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    payload = json.dumps({"cases": CASES, "charts": CHARTS, "series": SERIES})
    out = subprocess.run([node, "-e", HARNESS, str(trade_js), payload], capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"node failed: {out.stderr[-600:]}")
    return json.loads(out.stdout)


def expected(give, receive) -> dict:
    """The rule recomputed from the raw values (not from trade.js)."""
    def net(key):
        return sum(p["values"][key] for p in receive) - sum(p["values"][key] for p in give)

    def side(n, g, r):
        threshold = max(1.0, 0.03 * (g + r) / 2)
        return "win" if n >= threshold else "lose" if n <= -threshold else "even"

    charts = [k for k in CHARTS if all(p["values"][k] is not None for p in give + receive)]
    nets = [net(k) for k in charts]
    gives = [sum(p["values"][k] for p in give) for k in charts]
    recs = [sum(p["values"][k] for p in receive) for k in charts]
    avg = lambda xs: sum(xs) / len(xs)  # noqa: E731
    market = side(avg(nets), avg(gives), avg(recs))
    value = side(net("ddf_value"), sum(p["values"]["ddf_value"] for p in give), sum(p["values"]["ddf_value"] for p in receive))
    # JEG-1125 option A: the other manager wins or breaks even on a chart when its net is under that chart's band.
    yes = sum(1 for n, g, r in zip(nets, gives, recs) if n < max(1.0, 0.03 * (g + r) / 2))
    share = yes / len(nets)
    accept = "Likely" if share >= 2 / 3 else "Unlikely" if share <= 1 / 3 else "Toss-up"
    return {"cell": f"{value}|{market}", "side": market, "accept": accept, "yes": yes, "of": len(nets),
            "split": accept != DEAL_SPLIT_ACCEPT[market], "min": min(nets), "max": max(nets)}


def check(trade_js: Path) -> list[str]:
    errors = []
    got = run(trade_js)
    for name, (give, receive) in CASES.items():
        r, want = got[name], expected(give, receive)
        tag = f"{name}: "
        if r["kind"] != "read":
            errors.append(f"{tag}no read ({r['kind']})")
            continue
        if r["cell"] != want["cell"] or r["side"] != want["side"]:
            errors.append(f"{tag}cell {r['cell']} side {r['side']}, want {want['cell']}")
        if r["accept"] != want["accept"]:
            errors.append(f"{tag}headline accept {r['accept']}, recomputed {want['accept']}")
        if r["split"] != want["split"]:
            errors.append(f"{tag}market.split {r['split']}, want {want['split']} (accept {want['accept']}, side {want['side']})")
        text = f"{r['title']} {r['action']} {r['text']}"
        if r["accept"] != "Likely" and any(p in text for p in FAIR):
            errors.append(f"{tag}read {text!r} calls it fair while accept is {r['accept']}")
        if r["accept"] != "Unlikely" and any(p in text for p in HARD_SELL):
            errors.append(f"{tag}read {text!r} says a hard sell while accept is {r['accept']}")
        if want["split"]:
            count = f"{want['yes']} of {want['of']} have the other manager winning or even"
            if "split" not in r["title"] or count not in r["text"] or "acceptance is uncertain" not in r["text"]:
                errors.append(f"{tag}split read {text!r} must name the split and the count {count!r}")
            if want["min"] < 0 < want["max"]:
                spread = f"by {want['max'] - want['min']:.1f} points"
                if spread not in r["text"]:
                    errors.append(f"{tag}split read {text!r} must name the range {spread!r}")
            elif "call it close" not in r["text"]:
                errors.append(f"{tag}charts on one side of zero must read 'call it close': {text!r}")
            if not r["charts"] or r["charts"]["yes"] != want["yes"] or r["charts"]["of"] != want["of"]:
                errors.append(f"{tag}market.charts {r['charts']} != {want['yes']} of {want['of']}")
        elif "split" in r["title"]:
            errors.append(f"{tag}read {text!r} names a split the count does not support")
    # The live fixture, pinned by hand.
    live = got["hall-higgins-for-nacua"]
    if live["cell"] != "win|even" or live["split"] or live["propose"] != "Yes" or live["accept"] != "Likely":
        errors.append(f"live fixture: {live}")
    if not live["charts"] or live["charts"]["yes"] != 2 or live["charts"]["of"] != 3:
        errors.append(f"live fixture charts {live['charts']} must be 2 of 3 under the one even band")
    hand = got["win|even accept Unlikely"]
    if not hand["split"] or "by 5.0 points" not in hand["text"] or "1 of 3" not in hand["text"]:
        errors.append(f"hand-built split text {hand['text']!r} must name the 5.0-point range and 1 of 3")
    return errors


MUTATIONS = {
    "split ignored": ("market.split = market.charts.accept !== DEAL_SPLIT_ACCEPT[market.side];", "market.split = false;"),
    "even column expects Unlikely": ('const DEAL_SPLIT_ACCEPT = {win: "Unlikely", even: "Likely", lose: "Likely"};',
                                     'const DEAL_SPLIT_ACCEPT = {win: "Unlikely", even: "Unlikely", lose: "Likely"};'),
    "count flipped": ("const yes = completeCharts.filter(row => rowSign(row) <= 0).length;",
                      "const yes = completeCharts.filter(row => rowSign(row) >= 0).length;"),
    "count back on 0.0 as shown": ("const yes = completeCharts.filter(row => rowSign(row) <= 0).length;",
                                   "const yes = completeCharts.filter(row => signOf(row.net) <= 0).length;"),
    "split read keeps the cell copy": ("const cell = market.split ? splitRead(out.value.side, market.charts) : DEAL_READS[",
                                       "const cell = DEAL_READS["),
    "range dropped from the split read": ("? `disagree with each other by ${(charts.max - charts.min).toFixed(1)} points",
                                          "? `disagree with each other"),
}


class DealReadSplitTest(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(TRADE_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = TRADE_JS.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    broken = Path(tmp) / f"trade_{abs(hash(name))}.js"
                    broken.write_text(source.replace(old, new, 1), encoding="utf-8")
                    try:
                        errors = check(broken)
                    except (RuntimeError, KeyError, TypeError):
                        errors = ["crashed"]
                    self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
