"""One "even" rule for Compare a trade and Find a trade (JEG-1125).

Found 2026-10-26 by the values review: the band that calls a trade even was written out separately in trade.js
(Compare) and finder.js (Find a trade), so a copy could drift and the two screens could call the same chart net
even on one and lopsided on the other.

Rule (trade.js, JEG-1125 block): SHOWN_EVEN is defined once, in trade.js. A single series' net that shows as 0.0
(under SHOWN_EVEN) points neither way. Compare uses it for its per-source rows, the trade story and "Will they
accept?" (the other manager wins or breaks even: net <= 0 as shown); Find a trade reads the same constant from
trade.js for its "rival breaks even or wins" chart check, its "DDF Value says you win" edge and its display floor
NET_FLOOR. finder.js keeps one standalone copy (after the ||) because the MCP edge function evaluates finder.js on
its own, without trade.js. The Deal read's band (sideOf: max(1, 3% of the average side)) and the headline's
THIN_MARGIN are separate rules and are pinned by test_v2_deal_read*.py and test_v2_headlines.py.

These checks pin:
  * source: trade.js defines SHOWN_EVEN exactly once and builds signOf and the trade story's sign from it, with no
    other "shows as 0.0" sign literal; finder.js builds pointsAsShown and NET_FLOOR from SHOWN_EVEN, has no literal
    sign band of its own, and its standalone copy equals trade.js's value;
  * behaviour, for finder.js loaded with Node (reads trade.js) and evaluated on its own the way the MCP edge
    function does (its copy): on every probe net, Find a trade's per-chart "rival breaks even or wins" equals
    Compare's signOf(net) <= 0, Find a trade's count equals Compare's "Will they accept?" count, and Find a trade's
    DDF Value edge passes exactly when Compare's signOf says you win.

Discrimination: test_checks_fail_on_broken_builds copies both files, breaks one rule at a time (the standalone copy
drifts, trade.js's band moves, a literal band comes back in either file, NET_FLOOR goes literal) and requires each
to fail.
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
PROBES = [0, 0.01, 0.03, 0.049, 0.051, 0.06, 0.1, 0.2, 0.45, 0.55, 0.8, 0.99, 1.01, 1.5, 3, 10]

HARNESS = r"""
const [tradePath, finderPath, mode, chartsJson, probesJson] = process.argv.slice(1);
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
const keys = ["ddf_value"].concat(charts);
const row = (key, base, net) => ({player_key: key, name: key, pos: "WR", values: Object.fromEntries(keys.map(k => [k, base + net]))});
const out = [];
const base = 30;
for (const p of probes) for (const sign of [1, -1]) {
  const net = sign * p;
  const give = [row("g", base, 0)];
  const receive = [row("r", base, net)];
  const combo = F.evaluateCombo(give, receive, {ourKey: "ddf_value", chartKeys: charts, minCharts: 3, sanity: null});
  const rows = T.compareTrade(give, receive, keys).rows;
  const head = T.tradeHeadlines(rows, "ddf_value", {chartKeys: charts});
  out.push({net, finderRivalOk: combo.charts.map(c => c.rivalOk), finderCount: combo.rivalOkCount,
    finderEdgeWins: combo.passes.edge,
    compareRivalOk: rows.filter(r => charts.includes(r.key)).map(r => T.signOf(r.net) <= 0),
    compareCount: head.accept.yes, compareWins: T.signOf(rows[0].net) > 0});
}
process.stdout.write(JSON.stringify(out));
"""


def run(app_dir: Path, mode: str) -> list[dict]:
    proc = subprocess.run(["node", "-e", HARNESS, str(app_dir / "trade.js"), str(app_dir / "finder.js"), mode,
                           json.dumps(CHARTS), json.dumps(PROBES)], capture_output=True, text=True, timeout=60)
    if proc.returncode:
        raise RuntimeError(proc.stderr[-2000:])
    return json.loads(proc.stdout)


NUMBER = r"([0-9]*\.?[0-9]+)"
SHOWN_SIGN_LITERAL = re.compile(r"Math\.abs\([^)]*\)\s*<\s*[0-9]*\.?[0-9]+\s*\?\s*0\s*:")


def source_errors(app_dir: Path) -> list[str]:
    errors = []
    trade = (app_dir / "trade.js").read_text(encoding="utf-8")
    finder = (app_dir / "finder.js").read_text(encoding="utf-8")
    defs = re.findall(r"const SHOWN_EVEN = " + NUMBER + ";", trade)
    if len(defs) != 1:
        errors.append(f"trade.js must define SHOWN_EVEN exactly once, found {len(defs)}")
    if not re.search(r"const signOf = net => \(Math\.abs\(net\) < SHOWN_EVEN \?", trade):
        errors.append("trade.js signOf must be built from SHOWN_EVEN")
    if "const sign = row => signOf(row.net);" not in trade:
        errors.append("trade.js tradeStory must use signOf, not a band of its own")
    if SHOWN_SIGN_LITERAL.search(trade):
        errors.append(f"trade.js has a literal 'shows as 0.0' band: {SHOWN_SIGN_LITERAL.search(trade).group(0)!r}")
    if not re.search(r"const pointsAsShown = net => \(Math\.abs\(net\) < SHOWN_EVEN \?", finder):
        errors.append("finder.js pointsAsShown must be built from SHOWN_EVEN")
    if not re.search(r"const NET_FLOOR = SHOWN_EVEN;", finder):
        errors.append("finder.js NET_FLOOR must be SHOWN_EVEN")
    if SHOWN_SIGN_LITERAL.search(finder):
        errors.append(f"finder.js has a literal 'shows as 0.0' band: {SHOWN_SIGN_LITERAL.search(finder).group(0)!r}")
    copy = re.search(r"const SHOWN_EVEN = \(TRADE && finite\(TRADE\.SHOWN_EVEN\) && TRADE\.SHOWN_EVEN\) \|\| " + NUMBER + ";",
                     finder)
    if not copy:
        errors.append("finder.js must read SHOWN_EVEN from trade.js, with one standalone copy after ||")
    elif defs and float(copy.group(1)) != float(defs[0]):
        errors.append(f"finder.js standalone copy {copy.group(1)} differs from trade.js SHOWN_EVEN {defs[0]}")
    return errors


def behaviour_errors(app_dir: Path) -> list[str]:
    errors = []
    for mode in ("require", "standalone"):
        for case in run(app_dir, mode):
            tag = f"{mode} net {case['net']:+}: "
            if case["finderRivalOk"] != case["compareRivalOk"]:
                errors.append(tag + f"Find a trade rival-even {case['finderRivalOk']} != Compare {case['compareRivalOk']}")
            if case["finderCount"] != case["compareCount"]:
                errors.append(tag + f"Find a trade count {case['finderCount']} != Will they accept? {case['compareCount']}")
            if case["finderEdgeWins"] != case["compareWins"]:
                errors.append(tag + f"Find a trade edge {case['finderEdgeWins']} != Compare win {case['compareWins']}")
    return errors


def check(app_dir: Path) -> list[str]:
    return source_errors(app_dir) + behaviour_errors(app_dir)


MUTATIONS = {
    "standalone copy drifts": ("finder.js", "TRADE.SHOWN_EVEN) || 0.05;", "TRADE.SHOWN_EVEN) || 0.5;"),
    "trade.js band moves (copy left behind)": ("trade.js", "const SHOWN_EVEN = 0.05;", "const SHOWN_EVEN = 1;"),
    "finder literal band": ("finder.js", "const pointsAsShown = net => (Math.abs(net) < SHOWN_EVEN ? 0 : net);",
                            "const pointsAsShown = net => (Math.abs(net) < 0.05 ? 0 : net);"),
    "finder ignores trade.js": ("finder.js", "const SHOWN_EVEN = (TRADE && finite(TRADE.SHOWN_EVEN) && TRADE.SHOWN_EVEN) || 0.05;",
                                "const SHOWN_EVEN = 0.05;"),
    "NET_FLOOR literal": ("finder.js", "const NET_FLOOR = SHOWN_EVEN;", "const NET_FLOOR = 0.05;"),
    "Compare literal band": ("trade.js", "const signOf = net => (Math.abs(net) < SHOWN_EVEN ? 0",
                             "const signOf = net => (Math.abs(net) < 0.05 ? 0"),
    "trade story band of its own": ("trade.js", "const sign = row => signOf(row.net);",
                                    "const sign = row => (Math.abs(row.net) < 0.05 ? 0 : row.net > 0 ? 1 : -1);"),
}


class TradeBandsTest(unittest.TestCase):
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
