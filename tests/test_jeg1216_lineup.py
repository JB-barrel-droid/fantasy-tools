"""JEG-1216: row stability and starter selection use the real finder lineup calculation."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const assert = require('node:assert/strict');
const F = require(process.argv[1]);
const L = require(process.argv[2]);
const p = (key, pos, value) => ({player_key: key, name: key, pos, values: {ddf_value: value}});
const shape = {QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1, SUPERFLEX: 0};
const rows = [p('QB', 'QB', 20), p('A', 'RB', 18), p('B', 'RB', 15), p('C', 'RB', 9),
  p('W1', 'WR', 19), p('W2', 'WR', 16), p('W3', 'WR', 8), p('TE', 'TE', 12)];
// Rank swap: A remains in its RB row when the received player ranks between A and B.
let imp = F.rosterImpact(rows, [rows[2]], [p('X', 'RB', 17)], shape, 'ddf_value');
let view = L.buildRows(imp.before, imp.after, shape);
assert.deepEqual(view.starters.filter(r => r.slot === 'RB').map(r => [r.before?.name, r.after?.name]), [['A', 'A'], ['B', 'X']]);
assert.equal(imp.after.slots.RB[1].name, 'X');
// A stronger RB swaps rank with A but takes the vacated row only. FLEX remains the selected third RB.
imp = F.rosterImpact(rows, [rows[2]], [p('X', 'RB', 21)], shape, 'ddf_value');
view = L.buildRows(imp.before, imp.after, shape);
assert.deepEqual(view.starters.filter(r => r.slot === 'RB').map(r => [r.before?.name, r.after?.name]), [['A', 'A'], ['B', 'X']]);
assert.equal(imp.after.slots.RB[0].name, 'X');
assert.deepEqual(view.starters.filter(r => r.slot === 'FLEX').map(r => [r.before?.name, r.after?.name]), [['C', 'C']]);
// Two for one: actual starters and promoted bench players are retained, not recomputed for display.
imp = F.rosterImpact(rows, [rows[1], rows[4]], [p('Y', 'WR', 26)], shape, 'ddf_value');
view = L.buildRows(imp.before, imp.after, shape);
assert.deepEqual(view.starters.filter(r => r.slot === 'RB').map(r => [r.before?.name, r.after?.name]), [['A', 'C'], ['B', 'B']]);
assert.deepEqual(view.starters.filter(r => r.slot === 'WR').map(r => [r.before?.name, r.after?.name]), [['W1', 'Y'], ['W2', 'W2']]);
assert.equal(view.starters.filter(r => r.slot === 'RB' && !r.changed).length, 1);
assert.equal(imp.after.starters.length, imp.before.starters.length);
// A player's move from RB to FLEX is visible in both actual slot groups.
imp = F.rosterImpact(rows, [], [p('Z', 'RB', 30)], shape, 'ddf_value');
view = L.buildRows(imp.before, imp.after, shape);
assert.equal(view.starters.find(r => r.slot === 'RB' && r.before?.name === 'A').after?.name, 'A');
assert.equal(view.starters.find(r => r.slot === 'RB' && r.before?.name === 'B').after?.name, 'Z');
assert.equal(view.starters.find(r => r.slot === 'FLEX').after?.name, 'B');
// Bench remains inspectable. An unpriced arrival is shown without a fabricated starter or value.
imp = F.rosterImpact(rows, [], [p('U', 'WR', null)], shape, 'ddf_value');
view = L.buildRows(imp.before, imp.after, shape);
assert.equal(view.bench.some(r => r.after?.name === 'U'), true);
assert.equal(view.starters.some(r => r.after?.name === 'U'), false);
"""


class LineupComparisonTest(unittest.TestCase):
    def test_real_starter_selection_and_row_alignment(self):
        result = subprocess.run(
            ["node", "-e", SCRIPT, str(ROOT / "app/v2/finder.js"), str(ROOT / "app/v2/lineup-comparison.js")],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
