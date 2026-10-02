"""Exact source configuration identity shared by table and curves (JEG-65)."""
import json
import subprocess
import unittest
from pathlib import Path

from tests.test_two_tier_frontend import extract_function

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'app' / 'trade-value-chart' / 'assets'


class SourceComboContractTests(unittest.TestCase):
    def run_node(self, body):
        table = (ASSETS / 'comparison-dashboard.js').read_text()
        curve = (ASSETS / 'curve-widget.js').read_text()
        helpers = '\n'.join(extract_function(table, name) for name in
                            ('comboKeyFor', 'sourceComboExists', 'selectedCombo', 'sourceValue',
                             'allColumnKeys', 'runRegressionGuards'))
        script = f"""
const assert = require('node:assert/strict');
const ValueModel = require({json.dumps(str(ASSETS / 'value-model.js'))});
const data = require({json.dumps(str(ROOT / 'data/fixtures/current/comparison-sources-data.json'))});
const PURE_VORP_KEYS = [];
const state = {{scoring:'full', teams:12, combos:{{}}}};
let scoring = 'ppr', teams = 12;
const sourceMaps = new Map();
const SOURCE_KEYS = ['usatoday','fantasypros','cbs','fantasycalc',
  'usatoday_adjusted','fantasypros_adjusted','cbs_adjusted','fantasycalc_adjusted'];
const renderKeys = SOURCE_KEYS;
const FIELD_COLUMNS = [{{key:'pos'}}, {{key:'disagreement'}}];
const rows = () => [{{pos:'QB'}}];
const activeReferenceWeek = () => 4;
const window = {{}};
const sourceAvailable = sourceComboExists;
{helpers}
{extract_function(curve, 'comboKey')}
{body}
"""
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_96_source_scoring_team_cases_match_both_views(self):
        self.run_node("""
for (const [tableScore, curveScore] of [['standard','standard'],['half','half_ppr'],['full','ppr']]) {
  state.scoring = tableScore; scoring = curveScore;
  for (const n of [8,10,12,14]) {
    state.teams = teams = n;
    for (const raw of ['usatoday','fantasypros','cbs','fantasycalc']) {
      for (const source of [raw, raw + '_adjusted']) {
        const key = comboKeyFor(source);
        assert.equal(key, comboKey(source));
        assert.ok(key.startsWith(tableScore + '_' + n));
        const expected = raw === 'fantasycalc' || n === 12;
        assert.equal(sourceComboExists(source), expected, source + ':' + key);
        assert.equal(selectedCombo(source) !== null, expected);
      }
    }
  }
}
""")

    def test_no_stale_combo_or_value_can_leak_into_missing_league(self):
        self.run_node("""
state.teams = 10;
for (const source of ['usatoday','fantasypros','cbs','usatoday_adjusted','fantasypros_adjusted','cbs_adjusted']) {
  state.combos[source] = 'full_12';
  sourceMaps.set(source, new Map([[869, 123]]));
  assert.equal(selectedCombo(source), null);
  assert.equal(sourceValue(source, 869), null);
}
""")

    def test_fantasycalc_qb_grain_is_exact_and_never_falls_back(self):
        self.run_node("""
for (const n of [8,10,12,14]) {
  for (const score of ['standard','half','full']) {
    for (const source of ['fantasycalc','fantasycalc_adjusted']) {
      const one = ValueModel.sourceComboKey(source, score, n, 1);
      const two = ValueModel.sourceComboKey(source, score, n, 2);
      assert.notEqual(one, two);
      assert.ok(data.sources[source].combos[one]);
      assert.ok(data.sources[source].combos[two]);
      assert.equal(ValueModel.sourceComboKey(source, score, n, 3), null);
      const onlyTwo = {[two]: {native:{test:10}}};
      assert.equal(onlyTwo[one], undefined);
    }
  }
}
assert.equal(ValueModel.sourceComboKey('cbs', 'bad', 12), null);
assert.equal(ValueModel.sourceComboKey('cbs', 'ppr', 0), null);
assert.equal(ValueModel.sourceComboKey('fantasycalc', 'ppr', 12), null);
""")

    def test_current_week_missing_configuration_is_not_a_guard_failure(self):
        self.run_node("""
delete data.sources.usatoday.combos.full_12;
runRegressionGuards();
assert.equal(window.TradeValueComparisonDiagnostics.configurableColumns, true);
assert.equal(window.TradeValueComparisonDiagnostics.rolloverAware, true);
assert.equal(allColumnKeys().includes('usatoday'), false);
assert.equal(sourceValue('usatoday', 869), null);
""")

    def test_league_transition_diagnostics_report_actual_coverage(self):
        self.run_node("""
for (const n of [12,10,14,12]) {
  state.teams = n;
  runRegressionGuards();
  assert.equal(window.TradeValueComparisonDiagnostics.teams, n);
  assert.equal(window.TradeValueComparisonDiagnostics.availableSourceCount, n === 12 ? 8 : 2);
  assert.equal(window.TradeValueComparisonDiagnostics.rolloverAware, true);
}
""")


if __name__ == '__main__':
    unittest.main()
