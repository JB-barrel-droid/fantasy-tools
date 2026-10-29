import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
const require = createRequire(import.meta.url);
const S = require('../../app/v2/source-views.js');
const all = ['espn','cbsros','razzball','fantasycalc','usatoday','fantasypros','cbs'];
assert.equal(new Set(S.CATEGORIES.flatMap(c => c.keys)).size, 7);
assert.deepEqual(S.CATEGORIES.map(c => c.label), ['Projections','Published charts','Observed-trade estimates']);
for (const key of all) assert(S.categoryOf(key));
assert.equal(S.categoryOf('fantasycalc_adjusted').id,'observed');
assert.equal(S.categoryOf('espn_vorp').id,'projections');
assert.equal(S.categoryOf('ddf_value'), null);
const row = {values: {usatoday: 10, fantasypros: 0, cbs: 20, fantasycalc: 40},
  estimated: {cbs: 'Filled from peers, including FantasyCalc'}};
const pub = S.read(row,'published_chart_average',all);
assert.equal(pub.value,10);
assert.deepEqual(pub.recipe,{role:'comparison_only',scale:'indexed',aggregation:'equal_weight_mean',coverage:'all_inputs_required'});
assert.equal(pub.status,'complete');
assert.equal(pub.sourceCount,3);
assert.equal(pub.listedCount,1);
assert.equal(pub.estimatedCount,1);
assert.equal(pub.zeroUnknownCount,1);
assert.equal(pub.inputs[1].status,'zero_listing_unknown');
assert.match(pub.inputs[2].estimateReason,/FantasyCalc/);
assert.equal(S.read(row,'observed_trade_estimate',all).value,40);
assert.equal(S.read(row,'observed_trade_estimate',all).recipe.aggregation,'single_source');
const absent = S.read(row,'published_chart_average',all.filter(k=>k!=='cbs'));
assert.equal(absent.value,null);
assert.equal(absent.status,'partial');
assert.equal(absent.sourceCount,2);
assert.equal(absent.inputs[2].missingReason,'Source unavailable');
assert.equal(absent.inputs[2].status,'source_unavailable');
assert.equal(S.read({values:{...row.values,cbs:null}},'published_chart_average',all).value,null);
assert.equal(S.read({values:{...row.values,cbs:NaN}},'published_chart_average',all).value,null);
// Actual public-row shape for Kyle Juszczyk (key 30): four numeric zeroes,
// no estimated entries, and no public missingReasons although the pipeline
// has below-depth reasons. Do not claim those zeroes were listed.
const zeroPublicRow = {player_key:30,values:{usatoday:0,fantasypros:0,cbs:0,fantasycalc:0},
  estimated:{},missingReasons:{}};
const zeroPublic = S.read(zeroPublicRow,'published_chart_average',all);
assert.equal(zeroPublic.value,0);
assert.equal(zeroPublic.listedCount,0);
assert.equal(zeroPublic.zeroUnknownCount,3);
assert(zeroPublic.inputs.every(input=>input.status==='zero_listing_unknown'));
const belowDepth = S.read({values:{usatoday:0,fantasypros:0,cbs:0},
  missingReasons:{usatoday:'Below rosterable depth; source does not list him',
    fantasypros:'Below rosterable depth; source does not list him',
    cbs:'Below rosterable depth; source does not list him'}},'published_chart_average',all);
assert.equal(belowDepth.value,0);
assert.equal(belowDepth.sourceCount,3);
assert.equal(belowDepth.listedCount,0);
assert.equal(belowDepth.unlistedZeroCount,3);
assert.equal(belowDepth.inputs[0].status,'unlisted_zero');
assert.match(belowDepth.inputs[0].missingReason,/Below rosterable depth/);
assert.throws(()=>S.read(row,'unknown',all),/Unknown/);
console.log('source view definitions and complete-case comparisons: OK');
