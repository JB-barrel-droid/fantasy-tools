"""v2 Find a trade: the package search in app/v2/finder.js (JEG-481).

A trade is listed only when, in the engine's own values:

  * DDF Value says you win (receive - give > 0 as shown, i.e. at least 0.05);
  * at least 3 of the 4 trade charts say the rival breaks even or wins (chart net <= 0 as shown);
  * a chart that does not price every player in the package is left out of the count, never read as 0;
  * a player with no DDF Value is never searched (not counted as 0);
  * the default is up to 2-for-2; a larger maximum finds larger packages; simpler trades rank first on a tie.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against mutated copies of
finder.js (rival test inverted, 2-of-4 instead of 3, missing chart read as 0, DDF edge not required,
default size 3, no simplicity weight) and requires each to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINDER_JS = ROOT / "app" / "v2" / "finder.js"
CH = ["usatoday", "fantasycalc", "fantasypros", "cbs"]


def row(key, ddf, charts):
    """charts: one number for all four, a list of four, or None for none priced."""
    if charts is None:
        charts = [None] * 4
    elif not isinstance(charts, list):
        charts = [charts] * 4
    return {"player_key": key, "name": key, "values": dict(zip(["ddf_value"] + CH, [ddf] + charts))}


HARNESS = """
const F = require(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const r = F.findTrades(input.mine, input.theirs, input.opts);
console.log(JSON.stringify({total: r.total, trades: r.trades.map(t => ({give: t.give.map(p => p.player_key),
  receive: t.receive.map(p => p.player_key), edge: t.edge, priced: t.pricedCharts, ok: t.rivalOkCount}))}));
"""


def run(finder_js, mine, theirs, opts=None):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, str(finder_js), json.dumps({"mine": mine, "theirs": theirs, "opts": opts or {}})],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def pairs(result):
    return [(t["give"], t["receive"]) for t in result["trades"]]


def check(finder_js: Path) -> list[str]:
    errors = []
    mine = [row("m1", 20, 20)]
    # DDF says +5 for me; every chart says the rival is up or even: listed.
    r = run(finder_js, mine, [row("t1", 25, 18)])
    if pairs(r) != [(["m1"], ["t1"])] or abs(r["trades"][0]["edge"] - 5) > 1e-9:
        errors.append(f"a trade DDF wins and all charts accept is not listed: {r}")
    # Every chart says the rival loses: not listed.
    if run(finder_js, mine, [row("t1", 25, 30)])["total"] != 0:
        errors.append("a trade the charts call bad for the rival is listed")
    # DDF edge zero, under 0.05 or negative: not listed, even though the rival loves it.
    for ddf in (20, 20.04, 15):
        if run(finder_js, mine, [row("t1", ddf, 10)])["total"] != 0:
            errors.append(f"a trade with DDF edge {ddf - 20} is listed")
    # 3 of 4 charts accept: listed. 2 of 4: not.
    if run(finder_js, mine, [row("t1", 25, [18, 18, 18, 30])])["total"] != 1:
        errors.append("3 of 4 charts accepting is not enough to list")
    if run(finder_js, mine, [row("t1", 25, [18, 18, 30, 30])])["total"] != 0:
        errors.append("2 of 4 charts accepting is listed")
    # A chart that does not price the package is left out of the count, not read as 0.
    r = run(finder_js, mine, [row("t1", 25, [18, 18, 18, None])])
    if pairs(r) != [(["m1"], ["t1"])] or r["trades"][0]["priced"] != 3:
        errors.append(f"a missing chart is not left out of the count: {r}")
    # With only two priced charts, 3 cannot be reached.
    if run(finder_js, mine, [row("t1", 25, [18, 18, None, None])])["total"] != 0:
        errors.append("two priced charts cleared a 3-chart test")
    # A chart missing on MY side is not read as 0 either (0 would make their package look like a gift).
    r = run(finder_js, [row("m1", 20, [None, 20, 20, 20])], [row("t1", 25, [18, 18, 18, 18])])
    if r["trades"] and r["trades"][0]["priced"] != 3:
        errors.append("a chart missing on my side was counted")
    # A player with no DDF Value is never searched.
    if run(finder_js, mine, [row("t1", None, 1)])["total"] != 0:
        errors.append("a player with no DDF Value was searched")
    # Package sizes: default 2-for-2 does not find a 3-for-1; maxSize 3 does.
    big_mine = [row("m1", 10, 10), row("m2", 10, 10), row("m3", 10, 10)]
    star = [row("t1", 35, 28)]
    if (["m1", "m2", "m3"], ["t1"]) in pairs(run(finder_js, big_mine, star)):
        errors.append("default size found a 3-for-1")
    if (["m1", "m2", "m3"], ["t1"]) not in pairs(run(finder_js, big_mine, star, {"maxSize": 3})):
        errors.append("maxSize 3 did not find the 3-for-1")
    # Simpler first at the same edge: a 1-for-1 and a 2-for-2 with the same DDF edge.
    mine2 = [row("m1", 20, 20), row("m2", 20, 20)]
    theirs2 = [row("t1", 25, 20), row("t2", 20.5, 20)]
    ranked = pairs(run(finder_js, mine2, theirs2))
    if not ranked or len(ranked[0][0]) + len(ranked[0][1]) != 2:
        errors.append(f"a 1-for-1 is not first: {ranked}")
    return errors


MUTANTS = {
    "rival test inverted": ("const rivalOk = pointsAsShown(net) <= 0;", "const rivalOk = pointsAsShown(net) >= 0;"),
    "2 of 4 is enough": ("const MIN_CHARTS = 3;", "const MIN_CHARTS = 2;"),
    "missing chart read as 0": ("if (!finite(v)) return null; total += v;", "total += finite(v) ? v : 0;"),
    "DDF edge not required": [("if (pointsAsShown(edge) <= 0) continue;", ""),
                              ("if (pointsAsShown(theirSubs[mid].sums[0] - give.sums[0]) > 0)", "if (true)")],
    "default size 3": ("Math.max(1, o.maxSize || 2)", "Math.max(1, o.maxSize || 3)"),
    "no simplicity weight": ("const EXTRA_PLAYER_WEIGHT = 0.1;", "const EXTRA_PLAYER_WEIGHT = 0;"),
}


class FinderTests(unittest.TestCase):
    def test_finder_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        for name, edits in MUTANTS.items():
            with self.subTest(name):
                broken = source
                for old, new in edits if isinstance(edits, list) else [edits]:
                    self.assertIn(old, broken, f"mutant {name!r} no longer applies")
                    broken = broken.replace(old, new, 1)
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(broken, encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
