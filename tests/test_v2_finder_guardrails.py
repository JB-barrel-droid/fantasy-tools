"""JEG-1184: protected positions, Advanced limits, saved settings and visit links."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECK = r"""
const assert = require('node:assert/strict');
const F = require('./app/v2/finder.js');
const W = require('./app/v2/workspace.js');
const shape = {QB: 0, RB: 1, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0};
const row = (id, pos, ddf, market) => ({player_key: id, name: id, pos, ddfTier: 'starter',
  values: {ddf_value: ddf, usatoday: market, fantasycalc: market, fantasypros: market, cbs: market}});
const mine = [row('my-rb', 'RB', 20, 20), row('my-wr', 'WR', 10, 10)];
const theirs = [row('their-wr', 'WR', 25, 18), row('their-rb', 'RB', 30, 30)];
const opts = {maxSize: 1, sanity: {shape, mine, theirs, keepMine: false, keepTheirs: false}};
const before = F.findTrades(mine, theirs, opts);
const one = F.findTrades(mine, theirs, {...opts, maxSize: 1});
assert(one.trades.every(t => t.give.length === 1 && t.receive.length === 1));
assert(F.subsets(3, 1).every(s => s.length === 1));
assert(F.subsets(3, 2).some(s => s.length === 2));
assert.deepEqual(F.decodeFinderHash(F.encodeFinderHash({mine: ['my-rb'], theirs: ['their-wr'], maxSize: 1})).size, 1);
assert(before.trades.some(t => t.give[0].player_key === 'my-rb' && t.receive[0].player_key === 'their-wr'));
const guardrails = {shape, mine, theirs, protectedPositions: ['RB'], minDdfEdge: 0,
  minUserLineupGain: null, minTheirLineupGain: null};
assert.deepEqual(F.findTrades(mine, theirs, {...opts, guardrails: {...guardrails, protectedPositions: []}}), before);
const protectedResult = F.findTrades(mine, theirs, {...opts, guardrails});
assert(!protectedResult.trades.some(t => t.give[0].player_key === 'my-rb' && t.receive[0].player_key === 'their-wr'));
assert(protectedResult.guardrailDropped > 0);
assert(F.findTrades(mine, theirs, {...opts, guardrails: {...guardrails, protectedPositions: []}}).total === before.total);
assert(F.findTrades(mine, theirs, {...opts, guardrails: {...guardrails, protectedPositions: [], minDdfEdge: 100}}).total === 0);
assert(F.findTrades(mine, theirs, {...opts, guardrails: {...guardrails, protectedPositions: [], minUserLineupGain: 0}}).total < before.total);
assert(F.findTrades(mine, theirs, {...opts, guardrails: {...guardrails, protectedPositions: [], minTheirLineupGain: 0}}).total < before.total);
const trade = before.trades.find(t => t.give[0].player_key === 'my-rb' && t.receive[0].player_key === 'their-wr');
const combo = F.evaluateCombo(trade.give, trade.receive, {...before.ctx, guardrails});
assert.equal(combo.passes.guardrails, false);
const flexShape = {QB: 1, RB: 1, WR: 1, TE: 0, FLEX: 1, SUPERFLEX: 1};
const depth = [row('q', 'QB', 10, 10), row('rb1', 'RB', 9, 9), row('rb2', 'RB', 8, 8),
  row('wr1', 'WR', 7, 7), row('wr2', 'WR', 6, 6), row('te-zero', 'TE', 0, 0),
  {player_key: 'rb-missing', pos: 'RB', values: {ddf_value: null}}];
assert.deepEqual(F.benchBackups(depth, flexShape, 'ddf_value'), {QB: 0, RB: 0, WR: 0, TE: 1});
const depthMine = [row('starter', 'RB', 20, 20), row('last-backup', 'RB', 2, 20)];
const depthTheirs = [row('target', 'WR', 30, 10)];
const depthShape = {QB: 0, RB: 1, WR: 0, TE: 0, FLEX: 0, SUPERFLEX: 0};
const depthOpts = {maxSize: 1, sanity: {shape: depthShape, mine: depthMine, theirs: depthTheirs, keepMine: true, keepTheirs: false}};
const noMinimum = F.findTrades(depthMine, depthTheirs, depthOpts);
assert(noMinimum.trades.some(t => t.give[0].player_key === 'last-backup'));
assert.deepEqual(F.findTrades(depthMine, depthTheirs, {...depthOpts,
  guardrails: {shape: depthShape, mine: depthMine, theirs: depthTheirs, minBackups: {RB: 0}}}), noMinimum);
const depthFiltered = F.findTrades(depthMine, depthTheirs, {...depthOpts,
  guardrails: {shape: depthShape, mine: depthMine, theirs: depthTheirs, minBackups: {RB: 1}}});
assert(!depthFiltered.trades.some(t => t.give[0].player_key === 'last-backup'));
assert(depthFiltered.guardrailDropped > 0);

const defaults = W.normalizeFinderSettings(null);
assert.deepEqual(defaults.protectedPositions, []);
assert.equal(defaults.keepMine, true);
assert.equal(defaults.minUserLineupGain, null);
assert.deepEqual(defaults.minBackups, {QB: 0, RB: 0, WR: 0, TE: 0});
assert.equal(defaults.maxSize, 2);
const settings = W.normalizeFinderSettings({protectedPositions: ['RB', 'BAD', 'RB', 'WR'], keepMine: false,
  minDdfEdge: 2.5, minUserLineupGain: 0, minTheirLineupGain: 1.2});
assert.deepEqual(settings.protectedPositions, ['RB', 'WR']);
assert.equal(W.normalizeFinderSettings({minDdfEdge: -2, minUserLineupGain: '10', minTheirLineupGain: 101}).minTheirLineupGain, null);
assert.deepEqual(W.normalizeFinderSettings({minBackups: {RB: 2, WR: -1, QB: 21}, maxSize: 1}).minBackups,
  {QB: 0, RB: 2, WR: 0, TE: 0});
let ws = W.ops.setUi(W.newWorkspace({id: 'league-1'}), {finderSettings: settings});
assert.deepEqual(W.parseStored(W.serialize(ws)).workspace.ui.finderSettings, settings);
assert.deepEqual(W.importJson(W.exportJson(ws)).workspace.ui.finderSettings, settings);
assert.deepEqual(W.normalizeWorkspace({...ws, ui: {}}).ui.finderSettings, defaults);
const memory = {value: null, getItem() {return this.value}, setItem(k,v) {this.value=v}, removeItem() {this.value=null}};
const store = W.createStore({storage: memory, delay: 0});
store.load(); store.replace(ws); assert.equal(store.flush(), true);
const visit = W.createStore({storage: memory, delay: 0});
assert.equal(visit.load(), 'ok');
assert.deepEqual(visit.get().ui.finderSettings, settings);
const link = F.encodeFinderHash({mine: ['my-rb'], theirs: ['their-wr'], keepMine: false, keepTheirs: true,
  guardrails: settings}, 'teams=12');
const decoded = F.decodeFinderHash(link);
assert.deepEqual(decoded.guardrails.protectedPositions, ['RB', 'WR']);
assert.equal(decoded.guardrails.minUserLineupGain, 0);
assert.equal(decoded.guardrails.minDdfEdge, 2.5);
const backupLink = F.decodeFinderHash(F.encodeFinderHash({mine: ['my-rb'], theirs: ['their-wr'], maxSize: 1,
  guardrails: {minBackups: {RB: 2, WR: 1}}}));
assert.equal(backupLink.size, 1);
assert.deepEqual(backupLink.guardrails.minBackups, {RB: 2, WR: 1});
assert.equal(F.decodeFinderHash('#find-trade?mine=my-rb&protect=BAD&minEdge=-5&minMine=101').guardrails.minDdfEdge, 0);
assert(!F.encodeFinderHash({mine: ['my-rb'], theirs: ['their-wr']}).includes('protect='));
console.log('finder guardrails OK');
"""


class FinderGuardrailsTest(unittest.TestCase):
    def test_guardrails_settings_and_links(self):
        result = subprocess.run(["node", "-e", CHECK], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
