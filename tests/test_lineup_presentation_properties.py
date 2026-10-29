"""JEG-1270: property guards for the lineup comparison rows (app/v2/lineup-comparison.js buildRows).

The real finder.js picks the lineups from a seeded corpus; buildRows is only read. Every expectation is derived from
the inputs, so no totals are pinned here. Mutated copies of the module (written to a temp dir, never to app/) must
each fail a named property, which proves the properties can see the defect they guard against.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app/v2/lineup-comparison.js"
FINDER = ROOT / "app/v2/finder.js"
FIXTURE = ROOT / "tests/fixtures/lineup-presentation-properties.json"

HARNESS = r"""
'use strict';
const [modulePath, finderPath, fixturePath] = process.argv.slice(1);
const fs = require('node:fs');
const F = require(finderPath);
const L = require(modulePath);
const fx = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));
const ORDER = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX'];
const KEY = fx.value_key;

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const pick = (rnd, list) => list[Math.floor(rnd() * list.length)];
const int = (rnd, lo, hi) => lo + Math.floor(rnd() * (hi - lo + 1));
function shuffle(rnd, list) {
  const out = list.slice();
  for (let i = out.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [out[i], out[j]] = [out[j], out[i]]; }
  return out;
}
// Every shape the finder treats as "no price": null, undefined, NaN, a numeric string, no values object at all.
const UNPRICED = [r => { r.values = {[KEY]: null}; }, r => { r.values = {}; }, r => { r.values = {[KEY]: NaN}; },
  r => { r.values = {[KEY]: '12.5'}; }, r => { delete r.values; }, r => { r.values = {[KEY]: Infinity}; }];
function player(rnd, key, pos, name) {
  const row = {player_key: key, name, pos, values: {[KEY]: Math.round(rnd() * 1000) / 10}};
  if (rnd() < fx.unpriced_rate) pick(rnd, UNPRICED)(row);
  return row;
}
const shapeOf = label => { const s = fx.shapes.find(x => x.label === label); const {label: _, ...slots} = s; return slots; };

function generated() {
  const cases = [];
  fx.seeds.forEach(seed => {
    const rnd = mulberry32(seed);
    for (let c = 0; c < fx.cases_per_seed; c++) {
      const tag = `s${seed}c${c}`;
      const shapeSpec = fx.shapes[c % fx.shapes.length];
      const size = int(rnd, fx.roster_size[0], fx.roster_size[1]);
      const roster = Array.from({length: size}, (_, i) => player(rnd, `${tag}-p${i}`, pick(rnd, fx.positions), pick(rnd, fx.name_pool)));
      const leaving = shuffle(rnd, roster).slice(0, int(rnd, 0, fx.max_leaving));
      const arriving = Array.from({length: int(rnd, 0, fx.max_arriving)}, (_, i) => {
        const twin = leaving.length && rnd() < fx.arrival_reuses_leaving_name_rate ? pick(rnd, leaving) : null;
        // A twin arrives at the leaving player's position under the same display name but its own key.
        return player(rnd, `${tag}-in${i}`, twin ? twin.pos : pick(rnd, fx.positions), twin ? twin.name : pick(rnd, fx.name_pool));
      });
      cases.push({label: tag, shapeLabel: shapeSpec.label, roster, leaving, arriving, rnd});
    }
  });
  return cases;
}
function handCases() {
  const rnd = mulberry32(1);
  const build = r => ({player_key: r.player_key, name: r.name, pos: r.pos, values: {[KEY]: r.value}});
  return fx.hand_cases.map(h => {
    const roster = h.roster.map(build);
    return {label: h.label, shapeLabel: h.shape, roster, leaving: roster.filter(r => h.leaving.includes(r.player_key)),
      arriving: h.arriving.map(build), rnd};
  });
}

function deepFreeze(value, seen = new Set()) {
  if (value && typeof value === 'object' && !seen.has(value)) {
    seen.add(value);
    Object.values(value).forEach(v => deepFreeze(v, seen));
    Object.freeze(value);
  }
  return value;
}
// JSON drops undefined, NaN and Infinity; spell them out so a rewrite of any of them is visible.
const snapshot = value => JSON.stringify(value, (k, v) => v === undefined ? '<undefined>'
  : typeof v === 'number' && !Number.isFinite(v) ? `<${v}>` : v);
const keyOf = row => row ? String(row.player_key) : null;
const priced = row => Boolean(row && row.values) && typeof row.values[KEY] === 'number' && Number.isFinite(row.values[KEY]);

// A lineup with the same selected rows in a different order: per-slot arrays, bench and unvalued are reshuffled.
function permuted(rnd, lineup) {
  const slots = {};
  ORDER.forEach(slot => { slots[slot] = shuffle(rnd, (lineup.slots && lineup.slots[slot]) || []); });
  return {...lineup, slots, bench: shuffle(rnd, lineup.bench || []), unvalued: shuffle(rnd, lineup.unvalued || [])};
}

const failures = {};
const stats = {cases: 0, calls: 0, superflexStarters: 0, sameNameDifferentKeyRows: 0, sameNameInOneSlot: 0,
  survivorsWithRankShift: 0, unpricedArrivalsOnBench: 0, survivorChecks: 0, renderedUnpricedCells: 0};
function fail(property, label, message) {
  const entry = failures[property] || (failures[property] = {count: 0, first: `${label}: ${message}`});
  entry.count += 1;
}
const sorted = list => list.slice().sort();
const same = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

// Survivor pairing per slot: [before key, after key when the same player stays, else null] in row order.
const pairing = view => ORDER.map(slot => view.starters.filter(r => r.slot === slot)
  .map(r => [keyOf(r.before), keyOf(r.before) !== null && keyOf(r.before) === keyOf(r.after) ? keyOf(r.after) : null]));

function checkView(label, before, after, shape, view) {
  stats.calls += 1;
  const allAfter = new Set(ORDER.flatMap(s => (after.slots && after.slots[s]) || []).concat(after.bench || [], after.unvalued || []));
  const allBefore = new Set(ORDER.flatMap(s => (before.slots && before.slots[s]) || []).concat(before.bench || [], before.unvalued || []));
  const groups = ORDER.map(slot => [slot, view.starters.filter(r => r.slot === slot),
    (before.slots && before.slots[slot]) || [], (after.slots && after.slots[slot]) || []]);
  groups.push(['Bench', view.bench, (before.bench || []).concat(before.unvalued || []), (after.bench || []).concat(after.unvalued || [])]);
  const known = new Set(ORDER.concat('Bench'));
  view.starters.concat(view.bench).forEach(r => { if (!known.has(r.slot)) fail('slot-ids', label, `unknown slot ${r.slot}`); });

  groups.forEach(([slot, rows, b, a]) => {
    // Exact selected IDs and multiset on both sides, slot by slot (SUPERFLEX included). A collapsed key shows as a gap.
    const gotAfter = sorted(rows.filter(r => r.after).map(r => keyOf(r.after)));
    const gotBefore = sorted(rows.filter(r => r.before).map(r => keyOf(r.before)));
    if (!same(gotAfter, sorted(a.map(keyOf)))) fail(`slot-ids:${slot}`, label, `after ${JSON.stringify(gotAfter)} != selected ${JSON.stringify(sorted(a.map(keyOf)))}`);
    if (!same(gotBefore, sorted(b.map(keyOf)))) fail(`slot-ids:${slot}`, label, `before ${JSON.stringify(gotBefore)} != selected ${JSON.stringify(sorted(b.map(keyOf)))}`);
    if (slot !== 'Bench' && rows.length < ((shape && shape[slot]) || 0)) fail(`slot-ids:${slot}`, label, `${rows.length} rows for ${shape[slot]} slots`);
    if (slot === 'SUPERFLEX') stats.superflexStarters += a.length;
    // Rows hold the caller's own objects, never copies or fabricated players.
    rows.forEach(r => {
      if (r.after && !allAfter.has(r.after)) fail('identity', label, `after row ${keyOf(r.after)} is not an input object`);
      if (r.before && !allBefore.has(r.before)) fail('identity', label, `before row ${keyOf(r.before)} is not an input object`);
    });
    // A player selected in the same slot group on both sides keeps its before row, whatever the input order.
    const afterKeys = a.map(keyOf);
    b.forEach((row, index) => {
      const k = keyOf(row);
      if (!afterKeys.includes(k)) return;
      stats.survivorChecks += 1;
      if (afterKeys.indexOf(k) !== index) stats.survivorsWithRankShift += 1;
      const cell = rows[index];
      if (!cell || keyOf(cell.before) !== k || keyOf(cell.after) !== k || cell.changed !== false) {
        fail('survivor-row', label, `${slot} ${k} expected in row ${index}, got ${cell ? `${keyOf(cell.before)} -> ${keyOf(cell.after)}` : 'no row'}`);
      }
    });
    rows.forEach(r => {
      const changed = keyOf(r.before) !== keyOf(r.after);
      const twins = r.before && r.after && r.before.name === r.after.name && keyOf(r.before) !== keyOf(r.after);
      if (twins) stats.sameNameDifferentKeyRows += 1;
      if (twins && r.changed !== true) fail('duplicate-names', label, `${slot} ${keyOf(r.before)} -> ${keyOf(r.after)} share "${r.after.name}" but read as unchanged`);
      else if (r.changed !== changed) fail('changed-by-key', label, `${slot} ${keyOf(r.before)} -> ${keyOf(r.after)} changed=${r.changed}`);
    });
    const names = a.map(r => r.name);
    if (new Set(names).size < names.length) stats.sameNameInOneSlot += 1;
  });

  // Unpriced players stay visible on the bench, are never starters and keep their missing value.
  const benchAfter = new Set(view.bench.filter(r => r.after).map(r => r.after));
  (after.unvalued || []).forEach(r => {
    if (!benchAfter.has(r)) fail('unpriced', label, `unpriced ${keyOf(r)} missing from bench rows`);
    else if (!allBefore.has(r)) stats.unpricedArrivalsOnBench += 1;
  });
  view.starters.forEach(r => [r.before, r.after].forEach(p => {
    if (p && !priced(p)) fail('unpriced', label, `unpriced ${keyOf(p)} shown as a ${r.slot} starter`);
  }));
}

// Minimal DOM so renderTable can run under node; it records text only.
global.document = {createElement(tag) {
  return {tag, attrs: {}, children: [], textContent: '', hidden: false,
    setAttribute(k, v) { this.attrs[k] = String(v); }, append(...kids) { this.children.push(...kids); }, addEventListener() {}};
}};
function checkRender(label, before, after, shape) {
  const wrap = L.renderTable({before, after}, shape, KEY, 'Best starting lineup');
  const table = wrap.children[0];
  const bodies = table.children.filter(n => n.tag === 'tbody');
  const rows = L.buildRows(before, after, shape);
  const trs = bodies[0].children.filter(n => !n.attrs['data-total']).concat(bodies[1].children);
  const model = rows.starters.concat(rows.bench);
  if (trs.length !== model.length) { fail('unpriced', label, `rendered ${trs.length} rows for ${model.length}`); return; }
  trs.forEach((tr, i) => {
    const [, beforeCell, afterCell, changeCell] = tr.children;
    const r = model[i];
    [[r.before, beforeCell], [r.after, afterCell]].forEach(([p, cell]) => {
      if (p && !priced(p)) {
        stats.renderedUnpricedCells += 1;
        if (!cell.textContent.endsWith('no value')) fail('unpriced', label, `${keyOf(p)} rendered "${cell.textContent}"`);
        if (changeCell.textContent !== '—') fail('unpriced', label, `${keyOf(p)} change rendered "${changeCell.textContent}"`);
      }
    });
  });
}

for (const c of handCases().concat(generated())) {
  stats.cases += 1;
  const shape = deepFreeze(shapeOf(c.shapeLabel));
  const impact = F.rosterImpact(c.roster, c.leaving, c.arriving, shape, KEY);
  const before = deepFreeze(impact.before);
  const after = deepFreeze(impact.after);
  // Variant 0 is the finder's own order. Then the after side alone is reshuffled, then both sides.
  const variants = [[before, after, 'finder order']];
  for (let i = 0; i < fx.permutations_per_case; i++) variants.push([before, deepFreeze(permuted(c.rnd, after)), `after shuffle ${i}`]);
  for (let i = 0; i < fx.permutations_per_case; i++) variants.push([deepFreeze(permuted(c.rnd, before)), deepFreeze(permuted(c.rnd, after)), `both shuffle ${i}`]);
  let reference = null;
  variants.forEach(([b, a, how]) => {
    const label = `${c.label} (${c.shapeLabel}, ${how})`;
    const prior = [snapshot(b), snapshot(a), snapshot(shape)];
    let view;
    try { view = L.buildRows(b, a, shape); }
    catch (err) { fail('frozen', label, `buildRows threw on frozen input: ${err.message}`); return; }
    if (!same(prior, [snapshot(b), snapshot(a), snapshot(shape)])) fail('frozen', label, 'inputs changed');
    checkView(label, b, a, shape, view);
    if (b === before) {
      const now = JSON.stringify(pairing(view));
      if (reference === null) reference = now;
      else if (now !== reference) fail('permutation', label, `survivor rows ${now} != finder order ${reference}`);
    }
  });
  try { checkRender(`${c.label} (${c.shapeLabel}, render)`, before, after, shape); }
  catch (err) { fail('unpriced', c.label, `renderTable threw: ${err.message}`); }
}
process.stdout.write(JSON.stringify({failures, stats}));
"""

# Each mutant is one exact edit of the real module. The anchor must appear once, so a refactor of the module makes
# the test fail loudly here instead of silently testing an unmutated copy.
MUTANTS = {
    "name-as-key": (
        "const id = row => row && row.player_key !== undefined && row.player_key !== null ? String(row.player_key) : null;",
        "const id = row => row && row.name ? String(row.name) : null;",
        "duplicate-names",
    ),
    "rerank-after": (
        "    cells.forEach(cell => {\n"
        "      const key = id(cell.before);\n"
        "      if (key !== null && remaining.has(key)) { cell.after = remaining.get(key); remaining.delete(key); }\n"
        "    });\n",
        "",
        "survivor-row",
    ),
    "drop-slot": (
        'const ORDER = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];',
        'const ORDER = ["QB", "RB", "WR", "TE", "FLEX"];',
        "slot-ids:SUPERFLEX",
    ),
    "zero-fill": (
        "const value = (row, key) => row && row.values && finite(row.values[key]) ? row.values[key] : null;",
        "const value = (row, key) => row && row.values && finite(row.values[key]) ? row.values[key] : 0;",
        "unpriced",
    ),
}


def run_harness(module: Path) -> dict:
    result = subprocess.run(
        ["node", "-e", HARNESS, str(module), str(FINDER), str(FIXTURE)],
        capture_output=True, text=True, check=False, timeout=120,
    )
    if result.returncode != 0:
        raise AssertionError(f"harness crashed: {result.stderr}")
    return json.loads(result.stdout)


class LineupPresentationPropertiesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real = run_harness(MODULE)

    def test_real_module_holds_every_property(self):
        self.assertEqual(self.real["failures"], {}, json.dumps(self.real["failures"], indent=2))

    def test_corpus_exercises_each_property(self):
        # Guards against a vacuous pass: each property must have met the case it exists for.
        stats = self.real["stats"]
        fixture = json.loads(FIXTURE.read_text())
        expected_cases = len(fixture["seeds"]) * fixture["cases_per_seed"] + len(fixture["hand_cases"])
        self.assertEqual(stats["cases"], expected_cases)
        self.assertEqual(stats["calls"], expected_cases * (1 + 2 * fixture["permutations_per_case"]))
        for name in ("superflexStarters", "sameNameDifferentKeyRows", "sameNameInOneSlot", "survivorsWithRankShift",
                     "unpricedArrivalsOnBench", "survivorChecks", "renderedUnpricedCells"):
            with self.subTest(stat=name):
                self.assertGreater(stats[name], 0, json.dumps(stats))

    def test_hand_cases_alone_hold(self):
        # The hand cases pin the named duplicate-name and SUPERFLEX situations even if the seeds change.
        fixture = json.loads(FIXTURE.read_text())
        trimmed = {**fixture, "cases_per_seed": 0}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hand-only.json"
            path.write_text(json.dumps(trimmed))
            result = subprocess.run(["node", "-e", HARNESS, str(MODULE), str(FINDER), str(path)],
                                    capture_output=True, text=True, check=False, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertEqual(out["failures"], {})
        self.assertEqual(out["stats"]["cases"], len(fixture["hand_cases"]))
        self.assertGreater(out["stats"]["sameNameDifferentKeyRows"], 0)
        self.assertGreater(out["stats"]["superflexStarters"], 0)

    def test_mutants_fail_a_specific_property(self):
        source = MODULE.read_text()
        for name, (anchor, replacement, expected) in MUTANTS.items():
            with self.subTest(mutant=name):
                self.assertEqual(source.count(anchor), 1, f"{name}: anchor not found once in {MODULE.name}")
                with tempfile.TemporaryDirectory() as tmp:
                    mutant = Path(tmp) / "lineup-comparison.js"
                    mutant.write_text(source.replace(anchor, replacement))
                    failures = run_harness(mutant)["failures"]
                self.assertIn(expected, failures, f"{name} survived; failures were {sorted(failures)}")


if __name__ == "__main__":
    unittest.main()
