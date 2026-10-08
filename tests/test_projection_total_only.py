"""GAP-PROJ-PEAK-PIN (Jeremy, 2026-10-08, option C): projection sources match
only the overall total to the ESPN anchor.

CBS ROS and Razzball are scaled by ONE factor so their total over the players
they share with the anchor equals the anchor's. Each keeps its own weighting
across positions and its own top values. The fitted *_adjusted series keep the
per-position peak pin followed by the shared total.

The test runs the widget's real `normalizedAdjustedMapFor` (extracted from
curve-widget.js) against the real ValueModel, with a synthetic anchor and a
source whose QB sits far above the anchor's while its RB sits below. On the
old routing CBS ROS / Razzball came out peak-pinned (every position's top
equal to the anchor's times one factor), so the "keeps its own weighting"
assertions fail there.
"""
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ASSETS = REPO / "app" / "trade-value-chart" / "assets"
WIDGET = ASSETS / "curve-widget.js"
VALUE_MODEL = ASSETS / "value-model.js"


def extract_function(text, name):
    m = re.search(r"function %s\(.*?\) \{" % re.escape(name), text)
    if not m:
        return None
    depth = 0
    for i in range(m.start(), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[m.start():i + 1]
    return None


DRIVER = r"""
"use strict";
globalThis.window = globalThis;
require(process.env.VALUE_MODEL_JS);
const ValueModel = globalThis.TradeValueModel || globalThis.ValueModel;
const src = require("fs").readFileSync(0, "utf8");
const {fnSource, keySetSource} = JSON.parse(src);
const POS = ["QB", "RB", "WR", "TE"];
// Synthetic pool: 15 players per position, all shared with the anchor.
const canonicalByKey = new Map();
const anchor = new Map(), source = new Map();
// anchor tops / source tops: the source's QB is 2x the anchor's, its RB 0.6x.
const ANCHOR_TOP = {QB: 30, RB: 70, WR: 45, TE: 28};
const SOURCE_TOP = {QB: 60, RB: 42, WR: 45, TE: 28};
let k = 1;
POS.forEach(pos => {
  for (let i = 0; i < 15; i++) {
    canonicalByKey.set(k, {player_key: k, pos});
    anchor.set(k, ANCHOR_TOP[pos] * (1 - i / 20));
    source.set(k, SOURCE_TOP[pos] * (1 - i / 15));
    k++;
  }
});
const rawKeyForAdjusted = key => key === "cbs_adjusted" ? "cbs" : key.replace(/_adjusted$/, "");
const applyRosterShape = values => values;
const adjustedMapFor = () => source;
const adjustmentCellsFor = () => ({live: true});   // every source has live cells
const adjustedShareFor = () => 0.15;
const normalizeTradeChartToFixedPie = () => { throw new Error("fallback path must not run"); };
const fn = new Function("ValueModel", "canonicalByKey", "rawKeyForAdjusted",
  "applyRosterShape", "adjustedMapFor", "adjustmentCellsFor", "adjustedShareFor",
  "normalizeTradeChartToFixedPie",
  keySetSource + "\n" + fnSource + "\nreturn normalizedAdjustedMapFor;")(
  ValueModel, canonicalByKey, rawKeyForAdjusted, applyRosterShape, adjustedMapFor,
  adjustmentCellsFor, adjustedShareFor, normalizeTradeChartToFixedPie);
const out = {};
for (const key of ["cbsros", "razzball", "fantasycalc_adjusted", "cbs_adjusted"]) {
  const map = fn(key, anchor, 0.15);
  const tops = {}, srcTops = {};
  let total = 0, anchorTotal = 0;
  map.forEach((v, pk) => {
    const pos = canonicalByKey.get(pk).pos;
    tops[pos] = Math.max(tops[pos] || 0, v);
    srcTops[pos] = Math.max(srcTops[pos] || 0, source.get(pk));
    total += v;
    anchorTotal += anchor.get(pk);
  });
  out[key] = {tops, srcTops, total, anchorTotal};
}
out.anchorTops = ANCHOR_TOP;
process.stdout.write(JSON.stringify(out));
"""


def run_routing(widget_text):
    fn_source = extract_function(widget_text, "normalizedAdjustedMapFor")
    if fn_source is None:
        raise AssertionError("normalizedAdjustedMapFor missing from curve-widget.js")
    m = re.search(r"const PROJECTION_TOTAL_ONLY_KEYS = new Set\(\[.*?\]\);", widget_text)
    key_set = m.group(0) if m else ""
    proc = subprocess.run(["node", "-e", DRIVER],
                          env={**os.environ, "VALUE_MODEL_JS": str(VALUE_MODEL)},
                          input=json.dumps({"fnSource": fn_source, "keySetSource": key_set}),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("routing driver failed: %s" % proc.stderr[:2000])
    return json.loads(proc.stdout)


class ProjectionTotalOnlyRoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_routing(WIDGET.read_text(encoding="utf-8"))

    def test_every_series_total_matches_the_anchor(self):
        for key in ("cbsros", "razzball", "fantasycalc_adjusted", "cbs_adjusted"):
            got = self.out[key]
            self.assertAlmostEqual(got["anchorTotal"], got["total"], places=6,
                                   msg="%s: shared total must equal the anchor's" % key)

    def test_projection_sources_keep_their_own_positional_weighting(self):
        for key in ("cbsros", "razzball"):
            got = self.out[key]
            factors = {pos: got["tops"][pos] / got["srcTops"][pos] for pos in got["tops"]}
            self.assertLess(max(factors.values()) - min(factors.values()), 1e-9,
                            "%s: one factor for every position (got %s)" % (key, factors))
            # The source's QB top is 2x the anchor's: it must stay well above it.
            ratio_qb = got["tops"]["QB"] / self.out["anchorTops"]["QB"]
            ratio_rb = got["tops"]["RB"] / self.out["anchorTops"]["RB"]
            self.assertGreater(ratio_qb / ratio_rb, 3.0,
                               "%s: QB/RB weighting must be the source's, not the anchor's" % key)

    def test_adjusted_series_keep_the_peak_pin(self):
        for key in ("fantasycalc_adjusted", "cbs_adjusted"):
            got = self.out[key]
            ratios = {pos: got["tops"][pos] / self.out["anchorTops"][pos] for pos in got["tops"]}
            self.assertLess(max(ratios.values()) - min(ratios.values()), 1e-9,
                            "%s: each position's top must sit on the anchor's (times one factor), got %s"
                            % (key, ratios))


if __name__ == "__main__":
    unittest.main()
