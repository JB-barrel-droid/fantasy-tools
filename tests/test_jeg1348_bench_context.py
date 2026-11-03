"""JEG-1348: counted O3 provenance, resolved-window context and honest missing/zero labels."""
import copy
import importlib.util
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = json.loads((ROOT / "tests/fixtures/jeg1348_bench_context.json").read_text())
TOOL = ROOT / "tools/research/bench-decay-evidence/build_readout_asset.py"
spec = importlib.util.spec_from_file_location("bench_readout_asset", TOOL)
asset = importlib.util.module_from_spec(spec)
spec.loader.exec_module(asset)


def node(script):
    result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=True)
    return json.loads(result.stdout)


class BenchContextTest(unittest.TestCase):
    def test_fixture_counts_are_backed_by_the_committed_schedule(self):
        byes = json.loads((ROOT / CASES["bye_source"]).read_text())["byes"]
        self.assertEqual(len(byes), 32)
        for case in CASES["cases"]:
            with self.subTest(case=case["name"]):
                lo, hi = case["window"]
                self.assertEqual(case["weeks"], max(0, hi - lo + 1))
                self.assertEqual(case["byes"], sum(lo <= week <= hi for week in byes.values()))

    def test_historical_table_requires_its_fixed_cohort_metadata(self):
        result = node(r'''
const fs = require('fs'), vm = require('vm'); global.window = global;
vm.runInThisContext(fs.readFileSync('app/v2/bench-breakout-evidence.js', 'utf8'));
vm.runInThisContext(fs.readFileSync('app/v2/bench-context.js', 'utf8'));
const missing = ['seasons', 'teams', 'basis'].map(key => {
  const e = JSON.parse(JSON.stringify(TradeValueBenchEvidence)); delete e[key];
  return TradeValueBenchContext.evidenceRows(e);
});
console.log(JSON.stringify(missing));
''')
        self.assertEqual(result, [None, None, None], "missing provenance must not become an unlabelled rate table")

    def test_shipped_asset_is_only_counted_O3_and_reproducible(self):
        raw = asset.MATRIX.read_bytes()
        self.assertEqual(asset.ASSET.read_text(), asset.output(raw))
        data = asset.build(raw)
        self.assertEqual(len(data["rows"]), 12)
        self.assertEqual({r["id"] for r in data["rows"]},
                         {f"O3.{pos}.d{depth}" for pos in ("QB", "RB", "WR", "TE") for depth in (1, 2, 3)})
        qb3 = next(r for r in data["rows"] if r["id"] == "O3.QB.d3")
        self.assertEqual((qb3["rate"], qb3["breakouts"], qb3["n"]), (0, 0, 132))

    def test_missing_counts_and_mislabelled_evidence_are_rejected(self):
        original = json.loads(asset.MATRIX.read_bytes())
        for field, value in (("n", None), ("n", 0), ("evidence", "measured"), ("window", "week 17")):
            matrix = copy.deepcopy(original)
            next(r for r in matrix["rows"] if r["id"] == "O3.QB.d1")[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                asset.build(json.dumps(matrix).encode())

    def test_widget_counts_the_resolved_window_and_config_byes_without_changing_share(self):
        result = node(r'''
const fs = require('fs'), vm = require('vm');
const source = fs.readFileSync('app/trade-value-chart/assets/curve-widget.js', 'utf8');
const fn = source.slice(source.indexOf('  function benchShareReadout() {'), source.indexOf('  // Backward-compatible entry:', source.indexOf('  function benchShareReadout() {')));
const config = JSON.parse(fs.readFileSync('config/lineup_parameters.json'));
const sandbox = {lineupConfig: config, lineupConfigError: null, pipeline: {benchShare: {QB: .1, RB: .2, WR: .3, TE: .4, overall: .25, override: false}, lineup: {content_week: 8, window: [9,17]}}};
vm.createContext(sandbox); vm.runInContext(fn, sandbox);
const results = [];
for (const window of [[9,17], [15,17], [18,17], [19,17], [10,10], [15,16]]) {
  sandbox.pipeline.lineup.window = window; results.push(sandbox.benchShareReadout());
}
sandbox.lineupConfig = null; results.push(sandbox.benchShareReadout());
sandbox.pipeline.lineup = null; results.push(sandbox.benchShareReadout());
sandbox.pipeline = null; results.push(sandbox.benchShareReadout());
console.log(JSON.stringify(results));
''')
        self.assertEqual([(r.get("weeksLeft"), r.get("byesLeft")) for r in result[:6]],
                         [(9, 18), (3, 0), (0, 0), (0, 0), (1, 4), (2, 0)])
        for r in result[:6]:
            self.assertEqual(r["byeTeams"], 32)
            self.assertEqual(r["overall"], .25)
        self.assertIsNone(result[6]["byesLeft"])
        self.assertIsNone(result[7]["weeksLeft"])
        self.assertIsNone(result[8])

    def test_formatter_preserves_zero_and_fixed_historical_counts(self):
        result = node(r'''
const fs = require('fs'), vm = require('vm'); global.window = global;
vm.runInThisContext(fs.readFileSync('app/v2/bench-breakout-evidence.js', 'utf8'));
vm.runInThisContext(fs.readFileSync('app/v2/bench-context.js', 'utf8'));
const c = TradeValueBenchContext, e = TradeValueBenchEvidence;
const broken = JSON.parse(JSON.stringify(e)); broken.rows[0].n = null;
console.log(JSON.stringify({empty: c.measuredText({weeksLeft:0,window:[18,17],byesLeft:0,byeTeams:32}),
  one: c.measuredText({weeksLeft:1,window:[17,17],byesLeft:0,byeTeams:32}),
  missing: c.measuredText({weeksLeft:null}), byeMissing: c.measuredText({weeksLeft:9,window:[9,17],byesLeft:null,byeTeams:null}),
  rows:c.evidenceRows(e), absent:c.evidenceRows(null), broken:c.evidenceRows(broken)}));
''')
        self.assertEqual(result["empty"], "Measured: 0 weeks left · 0 of 32 teams have a bye in this window")
        self.assertIn("1 week left (week 17)", result["one"])
        self.assertIn("unavailable", result["missing"])
        self.assertIn("byes left unavailable", result["byeMissing"])
        self.assertEqual(result["rows"][0]["cells"], ["13.6% (18/132)", "2.3% (3/132)", "0.0% (0/132)"])
        self.assertIsNone(result["absent"])
        self.assertIsNone(result["broken"])
