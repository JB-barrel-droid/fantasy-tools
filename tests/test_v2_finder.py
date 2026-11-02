"""v2 Find a trade: the package search in app/v2/finder.js (JEG-481, JEG-819).

A trade is listed only when, in the engine's own values:

  * DDF Value says you win: receive - give clears the one even band, max(1, 3% of the average side)
    (JEG-1125 option A, Jeremy 2026-10-29; before that, > 0 as shown, i.e. at least 0.05);
  * at least one of the available trade charts says the rival breaks even or wins (the chart's net for you is
    inside that chart's band or below; JEG-1403, Jeremy: "I'd still want to see for even one trade chart and then we
    can use filters"; it was min(3, available charts) before); only charts the engine marks available are counted
    (JEG-819). MIN_CHARTS stays 3: it gates the Trade chart average and the trade calculator, not this search;
  * a chart that does not price every player in the package is left out of the count, never read as 0;
  * a player with no DDF Value is never searched (not counted as 0);
  * the default is up to 2-for-2; a larger maximum finds larger packages; simpler trades rank first on a tie.

Discrimination: test_checks_fail_on_broken_builds runs the same checks against mutated copies of
finder.js (rival test inverted, no chart needed, back to 3 of 4, missing chart read as 0, DDF edge not required,
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
  receive: t.receive.map(p => p.player_key), edge: t.edge, priced: t.pricedCharts, ok: t.rivalOkCount,
  charts: t.charts.map(c => ({key: c.key, rivalOk: c.rivalOk}))}))}));
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
    # DDF edge zero, inside the even band (under 1 point here) or negative: not listed, even though the rival loves it.
    for ddf in (20, 20.04, 20.5, 20.99, 15):
        if run(finder_js, mine, [row("t1", ddf, 10)])["total"] != 0:
            errors.append(f"a trade with DDF edge {ddf - 20} is listed")
    # JEG-1125 option A: an edge just past the band (1 point) is listed.
    if run(finder_js, mine, [row("t1", 21.01, 10)])["total"] != 1:
        errors.append("a trade with DDF edge 1.01 (past the band) is not listed")
    # JEG-1125 option A: a chart that has you up 0.5 (inside its 1-point band) calls it even, so the rival breaks even.
    if run(finder_js, mine, [row("t1", 25, 20.5)])["total"] != 1:
        errors.append("charts inside their even band do not count as the rival breaking even")
    # Past the band (+1.5 for you on every chart) the rival loses: not listed.
    if run(finder_js, mine, [row("t1", 25, 21.5)])["total"] != 0:
        errors.append("charts past their even band count as the rival breaking even")
    # JEG-1403: 1 of 4 charts accepting is enough to list (2 and 3 of 4 too). 0 of 4: not.
    for charts in ([18, 30, 30, 30], [18, 18, 30, 30], [18, 18, 18, 30]):
        r = run(finder_js, mine, [row("t1", 25, charts)])
        if r["total"] != 1:
            errors.append(f"{4 - charts.count(30)} of 4 charts accepting is not enough to list")
        elif r["trades"][0]["ok"] != 4 - charts.count(30) or r["trades"][0]["priced"] != 4:
            errors.append(f"charts {charts}: counted {r['trades'][0]['ok']} of {r['trades'][0]['priced']}")
    if run(finder_js, mine, [row("t1", 25, [30, 30, 30, 30])])["total"] != 0:
        errors.append("0 of 4 charts accepting is listed")
    # A chart that does not price the package is left out of the count, not read as 0.
    r = run(finder_js, mine, [row("t1", 25, [18, 18, 18, None])])
    if pairs(r) != [(["m1"], ["t1"])] or r["trades"][0]["priced"] != 3:
        errors.append(f"a missing chart is not left out of the count: {r}")
    # One priced chart that accepts is enough; one priced chart that rejects, or no priced chart, is not.
    if run(finder_js, mine, [row("t1", 25, [18, None, None, None])])["total"] != 1:
        errors.append("one priced chart accepting is not enough to list")
    if run(finder_js, mine, [row("t1", 25, [30, None, None, None])])["total"] != 0:
        errors.append("one priced chart rejecting is listed")
    if run(finder_js, mine, [row("t1", 25, None)])["total"] != 0:
        errors.append("a package no chart prices is listed")
    # A caller can still ask for more (opts.minCharts): with 3 required, 2 accepting charts are not enough.
    if run(finder_js, mine, [row("t1", 25, [18, 18, 30, 30])], {"minCharts": 3})["total"] != 0:
        errors.append("an explicit minCharts of 3 was not applied")
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
    # JEG-819: when only 2 chart keys are passed (simulating 2 available charts), a trade accepted on both is listed.
    r = run(finder_js, mine, [row("t1", 25, 18)], {"chartKeys": ["usatoday", "fantasypros"]})
    if r["total"] != 1:
        errors.append(f"a trade accepted on 2 of 2 available charts is not listed: {r}")
    # JEG-881: "cbs" is held, so the caller passes the other three keys. Expectations are
    # hand-derived, not read back from the call: the held chart must neither be counted nor listed.
    avail = ["usatoday", "fantasycalc", "fantasypros"]
    # Only the held chart rejects: 3 of 3 available accept -> listed, priced 3, charts name exactly the available keys.
    r = run(finder_js, mine, [row("t1", 25, [18, 18, 18, 30])], {"chartKeys": avail})
    if r["total"] != 1 or r["trades"][0]["priced"] != 3 or r["trades"][0]["ok"] != 3:
        errors.append(f"a held chart changed the count: {r}")
    elif [c["key"] for c in r["trades"][0]["charts"]] != avail:
        errors.append(f"a held chart is listed in charts: {r['trades'][0]['charts']}")
    # Only the held chart accepts: 0 of 3 available accept -> NOT listed (the held chart cannot make up the one).
    if run(finder_js, mine, [row("t1", 25, [30, 30, 30, 18])], {"chartKeys": avail})["total"] != 0:
        errors.append("a held chart's acceptance was counted toward the minimum")
    return errors


MUTANTS = {
    "rival test inverted": ("const rivalOk = pointsPastEven(net, g, r) <= 0;", "const rivalOk = pointsPastEven(net, g, r) >= 0;"),
    "rival test back on 0.0 as shown": ("const rivalOk = pointsPastEven(net, g, r) <= 0;", "const rivalOk = Math.abs(net) < 0.05 || net < 0;"),
    "edge back on 0.0 as shown": [("pointsPastEven(edge, give[0], get[0]) > 0", "edge >= 0.05"),
                                  ("if (pointsPastEven(mid0 - give.sums[0], give.sums[0], mid0) > 0)", "if (mid0 - give.sums[0] >= 0.05)")],
    "no chart needed": ("const SEARCH_MIN_CHARTS = 1;", "const SEARCH_MIN_CHARTS = -1;"),
    "back to 3 of 4": ("Math.min(SEARCH_MIN_CHARTS, chartKeys.length)", "Math.min(MIN_CHARTS, chartKeys.length)"),
    "missing chart read as 0": ("if (!finite(v)) return null; total += v;", "total += finite(v) ? v : 0;"),
    "DDF edge not required": [("if (!judged.passes.edge || !judged.passes.charts) continue;", "if (!judged.passes.charts) continue;"),
                              ("if (pointsPastEven(mid0 - give.sums[0], give.sums[0], mid0) > 0)", "if (true)")],
    "chartKeys ignored (held chart counted)": ("const chartKeys = (o.chartKeys || CHART_KEYS).slice();", "const chartKeys = CHART_KEYS.slice();"),
    "default size 3": ("Math.max(1, o.maxSize || 2)", "Math.max(1, o.maxSize || 3)"),
    "no simplicity weight": ("const EXTRA_PLAYER_WEIGHT = 0.1;", "const EXTRA_PLAYER_WEIGHT = 0;"),
}


CALCULATOR = """
const F = require(process.argv[1]);
const T = require(process.argv[2]);
const mine = [{player_key: "m1", name: "m1", values: {ddf_value: 20, ddf_value_projections: 20, usatoday: 20, fantasycalc: 20, fantasypros: 20, cbs: 20}}];
const theirs = [{player_key: "t1", name: "t1", values: {ddf_value: 25, ddf_value_projections: 25, usatoday: 18, fantasycalc: 30, fantasypros: 30, cbs: 30}}];
const found = F.findTrades(mine, theirs, {});
const read = keys => { const m = T.dealRead(mine, theirs, keys).market; return {tooFew: Boolean(m.tooFew), chartCount: m.chartCount, minCharts: m.minCharts || null}; };
console.log(JSON.stringify({MIN_CHARTS: F.MIN_CHARTS, SEARCH_MIN_CHARTS: F.SEARCH_MIN_CHARTS, MIN_DEAL_CHARTS: T.MIN_DEAL_CHARTS,
  found: found.total, ok: found.trades.length ? found.trades[0].rivalOkCount : null,
  two: read(["usatoday", "fantasycalc"]), three: read(["usatoday", "fantasycalc", "fantasypros"])}));
"""


class FinderTests(unittest.TestCase):
    def test_finder_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_the_calculator_keeps_its_three_chart_gate(self):
        # JEG-1403 lowers only the search's default (SEARCH_MIN_CHARTS). The shared MIN_CHARTS and Compare's
        # MIN_DEAL_CHARTS stay 3: the package the finder now lists on 1 of 4 charts still gets no market read from
        # two charts, and does get one from three.
        if not shutil.which("node"):
            self.skipTest("node is not installed")
        out = subprocess.run(["node", "-e", CALCULATOR, str(FINDER_JS), str(FINDER_JS.with_name("trade.js"))],
                             check=True, capture_output=True, text=True)
        got = json.loads(out.stdout)
        self.assertEqual((got["MIN_CHARTS"], got["SEARCH_MIN_CHARTS"], got["MIN_DEAL_CHARTS"]), (3, 1, 3))
        self.assertEqual((got["found"], got["ok"]), (1, 1))
        self.assertEqual(got["two"], {"tooFew": True, "chartCount": 2, "minCharts": 3})
        self.assertEqual(got["three"], {"tooFew": False, "chartCount": 3, "minCharts": None})

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
