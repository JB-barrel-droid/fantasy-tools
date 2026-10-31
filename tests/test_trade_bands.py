"""One "even" band for Compare a trade and Find a trade (JEG-1125, option A).

Found 2026-10-26 by the values review: "even" was defined three ways. Compare's Deal read used max(1, 3% of the
average side) (sideOf), while Compare's verdict, its per-source sides, the trade story, "Will they accept?" and Find
a trade used "shows as 0.0" (under 0.05). So the same trade could be "even on value" in the Deal read and a win in
Find a trade, and a chart up 0.8 for you counted against acceptance in one place and as fair in the other.

Rule (Jeremy, 2026-10-29 9:11 PM CT, option A; trade.js JEG-1125 block): one band, evenBand = max(EVEN_FLOOR,
EVEN_SHARE x the average side), EVEN_FLOOR = 1 point and EVEN_SHARE = 3%, applied to each series' own give and
receive. A net inside it is even. Compare's verdict and per-source sides (tradeVerdict), the trade story,
"Will they accept?" (the other manager wins or breaks even), the Deal read (sideOf) and Find a trade (its DDF Value
edge and its "rival breaks even or wins" chart check) all use it. THIN_MARGIN (5% of the value traded) is a
separate confidence rule, pinned by test_v2_headlines.py. SHOWN_EVEN (0.05) is only how a net prints and Find a
trade's fit floor NET_FLOOR. finder.js keeps standalone copies (after the ||) because the MCP edge function
evaluates finder.js on its own, without trade.js.

These checks pin:
  * source: trade.js defines EVEN_FLOOR, EVEN_SHARE and SHOWN_EVEN once each, builds evenBand from them, and sideOf,
    the trade story, tradeVerdict, "Will they accept?" and the Deal read's chart count from evenBand (no literal band,
    no win / even call on signOf); finder.js reads all three from trade.js with copies equal to trade.js's values,
    builds its band from them, judges the edge, the rival check and the search bound with it, has no literal band
    and keeps NET_FLOOR = SHOWN_EVEN;
  * behaviour, for finder.js loaded with Node (reads trade.js) and evaluated on its own the way the MCP edge function
    does (its copies): on probe nets either side of every band anyone has proposed, at two trade sizes (where the
    1-point floor decides and where 3% decides), Find a trade's per-chart "rival breaks even or wins" equals Compare's,
    its count equals "Will they accept?" and the Deal read's chart count, and its DDF Value edge passes exactly when
    Compare's verdict and the Deal read both say you win, and exactly when the net clears the band.

Discrimination: test_checks_fail_on_broken_builds copies both files, breaks one rule at a time and requires each to
fail. The checks also fail on the pre-A build (25efb1d: 0.05 band in Find a trade and the verdict).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_V2 = ROOT / "app" / "v2"
CHARTS = ["usatoday", "fantasycalc", "fantasypros", "cbs"]
# Nets either side of every band anyone has proposed (0.0 as shown, 1 point, 3% of a side, 5% of the value traded).
PROBES = [0, 0.01, 0.049, 0.051, 0.2, 0.55, 0.8, 0.99, 1.01, 1.5, 2.9, 3.1, 4, 10]
# Side sizes: at 30 the 1-point floor is the band; at 100 the band is 3% of the average side (about 3 points).
BASES = [30, 100]

HARNESS = r"""
const [tradePath, finderPath, mode, chartsJson, probesJson, basesJson] = process.argv.slice(1);
const fs = require("fs");
const vm = require("vm");
const T = require(tradePath);
let F;
if (mode === "require") {
  F = require(finderPath);
} else {
  // The MCP edge function: evaluate the source on its own (no module, no require, no trade.js, no DOM).
  const ctx = {console: {log() {}, warn() {}, error() {}}};
  ctx.globalThis = ctx;
  try { vm.runInNewContext(fs.readFileSync(finderPath, "utf8"), ctx); } catch (e) { /* page code after publishing */ }
  F = ctx.TradeValueFinder;
}
const charts = JSON.parse(chartsJson);
const probes = JSON.parse(probesJson);
const keys = ["ddf_value", "ddf_value_projections"].concat(charts);
const row = (key, base, net) => ({player_key: key, name: key, pos: "WR", values: Object.fromEntries(keys.map(k => [k, base + net]))});
const out = [];
for (const base of JSON.parse(basesJson)) for (const p of probes) for (const sign of [1, -1]) {
  const net = sign * p;
  const give = [row("g", base, 0)];
  const receive = [row("r", base, net)];
  const combo = F.evaluateCombo(give, receive, {ourKey: "ddf_value", chartKeys: charts, minCharts: 3, sanity: null});
  const rows = T.compareTrade(give, receive, keys).rows;
  const deal = T.dealRead(give, receive, charts);
  const head = T.tradeHeadlines(rows, "ddf_value", {chartKeys: charts, deal});
  const verdict = T.tradeVerdict(rows, "ddf_value");
  const chartRows = rows.filter(r => charts.includes(r.key));
  out.push({base, net, finderRivalOk: combo.charts.map(c => c.rivalOk), finderCount: combo.rivalOkCount,
    finderEdgeWins: combo.passes.edge,
    compareRivalOk: chartRows.map(r => !verdict.upKeys.includes(r.key)),
    compareCount: head.accept.yes, dealCount: deal.market.charts ? deal.market.charts.yes : null,
    verdictWins: verdict.kind === "win", dealWins: deal.value.side === "win"});
}
process.stdout.write(JSON.stringify(out));
"""


def run(app_dir: Path, mode: str) -> list[dict]:
    proc = subprocess.run(["node", "-e", HARNESS, str(app_dir / "trade.js"), str(app_dir / "finder.js"), mode,
                           json.dumps(CHARTS), json.dumps(PROBES), json.dumps(BASES)],
                          capture_output=True, text=True, timeout=60)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-2000:])
    return json.loads(proc.stdout)


NUMBER = r"([0-9]*\.?[0-9]+)"
LITERAL_BAND = re.compile(r"Math\.max\(\s*[0-9.]+\s*,\s*[0-9.]+\s*\*")


def source_errors(app_dir: Path) -> list[str]:
    errors = []
    trade = (app_dir / "trade.js").read_text(encoding="utf-8")
    finder = (app_dir / "finder.js").read_text(encoding="utf-8")
    values = {}
    for name in ("EVEN_FLOOR", "EVEN_SHARE", "SHOWN_EVEN"):
        defs = re.findall(r"const " + name + " = " + NUMBER + ";", trade)
        if len(defs) != 1:
            errors.append(f"trade.js must define {name} exactly once, found {len(defs)}")
        else:
            values[name] = float(defs[0])
    trade_needs = {
        "const evenBand = (give, receive) => Math.max(EVEN_FLOOR, EVEN_SHARE * ((give + receive) / 2));":
            "trade.js evenBand must be built from EVEN_FLOOR and EVEN_SHARE",
        "const bandSign = (net, give, receive) => (Math.abs(net) < evenBand(give, receive) ? 0":
            "trade.js bandSign must use evenBand",
        "const rowSign = row => bandSign(row.net, row.give, row.receive);": "trade.js rowSign must use bandSign",
        "const threshold = evenBand(give, receive);": "trade.js sideOf (Deal read) must use evenBand",
        "const sign = row => rowSign(row);": "trade.js tradeStory must use rowSign",
        "const s = rowSign(head);": "trade.js tradeVerdict's head must use rowSign",
        "complete.filter(row => rowSign(row) === want)": "trade.js tradeVerdict's per-source sides must use rowSign",
        "const yes = charts.filter(row => rowSign(row) <= 0).length;": "trade.js \"Will they accept?\" must use rowSign",
        "const yes = completeCharts.filter(row => rowSign(row) <= 0).length;":
            "trade.js Deal read chart count must use rowSign",
    }
    errors += [msg for text, msg in trade_needs.items() if text not in trade]
    calls = len(re.findall(r"signOf\(", trade))
    if calls:
        errors.append(f"trade.js decides win / even on signOf (0.0 as shown) in {calls} place(s)")
    if LITERAL_BAND.search(trade):
        errors.append(f"trade.js has a literal band: {LITERAL_BAND.search(trade).group(0)!r}")
    for name in ("EVEN_FLOOR", "EVEN_SHARE", "SHOWN_EVEN"):
        copy = re.search(r"const " + name + r" = \(TRADE && finite\(TRADE\." + name + r"\) && TRADE\." + name
                         + r"\) \|\| " + NUMBER + ";", finder)
        if not copy:
            errors.append(f"finder.js must read {name} from trade.js, with one standalone copy after ||")
        elif name in values and float(copy.group(1)) != values[name]:
            errors.append(f"finder.js standalone {name} {copy.group(1)} differs from trade.js {values[name]}")
    finder_needs = {
        "const evenBand = (give, get) => Math.max(EVEN_FLOOR, EVEN_SHARE * ((give + get) / 2));":
            "finder.js evenBand must be built from EVEN_FLOOR and EVEN_SHARE",
        "const pointsPastEven = (net, give, get) => (Math.abs(net) < evenBand(give, get) ? 0 : net);":
            "finder.js pointsPastEven must use evenBand",
        "const rivalOk = pointsPastEven(net, g, r) <= 0;": "finder.js rival check must use the even band",
        "pointsPastEven(edge, give[0], get[0]) > 0": "finder.js DDF Value edge must clear the even band",
        "if (pointsPastEven(mid0 - give.sums[0], give.sums[0], mid0) > 0)":
            "finder.js search bound must use the even band",
        "const NET_FLOOR = SHOWN_EVEN;": "finder.js NET_FLOOR must be SHOWN_EVEN",
    }
    errors += [msg for text, msg in finder_needs.items() if text not in finder]
    if "pointsAsShown" in finder:
        errors.append("finder.js still has pointsAsShown (the 0.0-as-shown even rule)")
    if LITERAL_BAND.search(finder):
        errors.append(f"finder.js has a literal band: {LITERAL_BAND.search(finder).group(0)!r}")
    return errors


def behaviour_errors(app_dir: Path) -> list[str]:
    errors = []
    for mode in ("require", "standalone"):
        for case in run(app_dir, mode):
            tag = f"{mode} base {case['base']} net {case['net']:+}: "
            if case["finderRivalOk"] != case["compareRivalOk"]:
                errors.append(tag + f"Find a trade rival-even {case['finderRivalOk']} != Compare {case['compareRivalOk']}")
            if not (case["finderCount"] == case["compareCount"] == case["dealCount"]):
                errors.append(tag + f"Find a trade count {case['finderCount']}, Will they accept? {case['compareCount']},"
                                    f" Deal read {case['dealCount']} differ")
            if not (case["finderEdgeWins"] == case["verdictWins"] == case["dealWins"]):
                errors.append(tag + f"Find a trade edge {case['finderEdgeWins']}, verdict win {case['verdictWins']},"
                                    f" Deal read win {case['dealWins']} differ")
            band = max(1.0, 0.03 * (2 * case["base"] + case["net"]) / 2)
            want_win = case["net"] >= band
            if case["finderEdgeWins"] != want_win:
                errors.append(tag + f"edge wins {case['finderEdgeWins']}, the band {band:.3f} says {want_win}")
    return errors


def check(app_dir: Path) -> list[str]:
    return source_errors(app_dir) + behaviour_errors(app_dir)


MUTATIONS = {
    "standalone floor drifts": ("finder.js", "TRADE.EVEN_FLOOR) || 1;", "TRADE.EVEN_FLOOR) || 2;"),
    "standalone share drifts": ("finder.js", "TRADE.EVEN_SHARE) || 0.03;", "TRADE.EVEN_SHARE) || 0.05;"),
    "trade.js share moves (copy left behind)": ("trade.js", "const EVEN_SHARE = 0.03;", "const EVEN_SHARE = 0.05;"),
    "trade.js floor moves (copy left behind)": ("trade.js", "const EVEN_FLOOR = 1;", "const EVEN_FLOOR = 2;"),
    "finder ignores trade.js": ("finder.js", "const EVEN_SHARE = (TRADE && finite(TRADE.EVEN_SHARE) && TRADE.EVEN_SHARE) || 0.03;",
                                "const EVEN_SHARE = 0.03;"),
    "finder literal band": ("finder.js", "Math.max(EVEN_FLOOR, EVEN_SHARE * ((give + get) / 2))",
                            "Math.max(1, 0.03 * ((give + get) / 2))"),
    "finder rival back on 0.0 as shown": ("finder.js", "const rivalOk = pointsPastEven(net, g, r) <= 0;",
                                          "const rivalOk = Math.abs(net) < SHOWN_EVEN || net < 0;"),
    "finder edge back on 0.0 as shown": ("finder.js", "pointsPastEven(edge, give[0], get[0]) > 0", "edge >= SHOWN_EVEN"),
    "NET_FLOOR literal": ("finder.js", "const NET_FLOOR = SHOWN_EVEN;", "const NET_FLOOR = 0.05;"),
    "verdict back on 0.0 as shown": ("trade.js", "const s = rowSign(head);", "const s = signOf(head.net);"),
    "accept back on 0.0 as shown": ("trade.js", "const yes = charts.filter(row => rowSign(row) <= 0).length;",
                                    "const yes = charts.filter(row => signOf(row.net) <= 0).length;"),
    "Deal read band of its own": ("trade.js", "const threshold = evenBand(give, receive);",
                                  "const threshold = Math.max(1, 0.05 * ((give + receive) / 2));"),
    "trade story band of its own": ("trade.js", "const sign = row => rowSign(row);", "const sign = row => signOf(row.net);"),
}


RIVAL_EDGE = ROOT / "tests" / "node" / "rival_edge_band_check.mjs"
FIND_TRADES = ROOT / "supabase" / "functions" / "mcp" / "find-trades.ts"


def rival_edge_errors(find_trades: Path = FIND_TRADES) -> list[str]:
    """The connector's min_rival_edge filter counts only the rival's own gain per chart (review of #1033)."""
    with tempfile.TemporaryDirectory() as tmp:
        node_dir = Path(tmp) / "tests" / "node"
        mcp_dir = Path(tmp) / "supabase" / "functions" / "mcp"
        node_dir.mkdir(parents=True)
        mcp_dir.mkdir(parents=True)
        shutil.copy2(RIVAL_EDGE, node_dir / RIVAL_EDGE.name)
        shutil.copy2(find_trades, mcp_dir / "find-trades.ts")
        out = subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(node_dir / RIVAL_EDGE.name),
                              str(APP_V2 / "finder.js")], capture_output=True, text=True, timeout=60)
    return [] if out.returncode == 0 and out.stdout.strip().endswith("rival edge ok") else [(out.stdout + out.stderr)[-600:]]


class TradeBandsTest(unittest.TestCase):
    def test_connector_rival_edge_counts_only_the_rival_gain(self):
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        self.assertEqual(rival_edge_errors(), [])
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "find-trades.ts"
            src = FIND_TRADES.read_text(encoding="utf-8")
            anchor = ".map((c) => Math.max(0, -c.net!));"
            self.assertIn(anchor, src, "mutation anchor is stale")
            broken.write_text(src.replace(anchor, ".map((c) => Math.abs(c.net!));", 1), encoding="utf-8")
            self.assertNotEqual(rival_edge_errors(broken), [], "the gap size counted as the rival's edge was not caught")

    def test_one_even_rule(self):
        self.assertEqual(check(APP_V2), [])

    def test_checks_fail_on_broken_builds(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, (file, old, new) in MUTATIONS.items():
                with self.subTest(mutation=name):
                    work = Path(tmp) / re.sub(r"\W+", "-", name)
                    work.mkdir()
                    for js in ("trade.js", "finder.js"):
                        shutil.copy2(APP_V2 / js, work / js)
                    source = (work / file).read_text(encoding="utf-8")
                    self.assertIn(old, source, f"mutation anchor for {name!r} is stale")
                    (work / file).write_text(source.replace(old, new, 1), encoding="utf-8")
                    try:
                        errors = check(work)
                    except (RuntimeError, KeyError, TypeError, ValueError):
                        errors = ["crashed"]
                    self.assertNotEqual(errors, [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
