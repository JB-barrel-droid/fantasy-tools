// JEG-1335: the page's fixed-pie check (curve-widget.js fixedPieDiagnostics)
// on an engine run of the worked example, at a given seat sigma. Prints
// {mix, checks: [{source, total, target, vorpTotal, groups, sliceGap, rowGap}],
// indexed, bothLabels}. Used by tests/test_fractional_seats_pie.py.
"use strict";
const ValueModel = require(process.argv[2]);
const doc = require(process.argv[3]);
const sigma = JSON.parse(process.argv[4]);
const v = doc.variant_fractional_seats;
const setting = Object.assign({}, doc.setting, v.setting_change, {seat_sigma: sigma});
const sources = {};
Object.entries(doc.inputs).forEach(([k, s]) => { sources[k] = {family: s.family, status: s.status, values: s.values, label: k}; });
const included = Object.keys(doc.inputs).filter(k => doc.inputs[k].status === "included");
const result = ValueModel.runValuePipeline({setting, players: doc.players, sources, included});
const pie = result.pie;
const checks = [];
Object.entries(result.sources).forEach(([key, src]) => {
  if (!src.hasWeights) return;
  // Same arithmetic as fixedPieDiagnostics.
  const funded = {...result.budgets};
  (src.unfundedMoved || []).forEach(m => { funded[m.to] += m.amount; funded[m.from] -= m.amount; });
  const unpaid = (src.unfundedGroups || []).reduce((s, g) => s + g.amount, 0);
  (src.unfundedGroups || []).forEach(g => { funded[g.group] -= g.amount; });
  const groups = {};
  Object.keys(funded).forEach(g => { groups[g] = {total: 0, budget: funded[g]}; });
  let total = 0, vorpTotal = 0, sliceGap = 0, rowGap = 0;
  Object.entries(src.players).forEach(([k, p]) => {
    total += p.adjusted;
    vorpTotal += p.vorpDisplay;
    const b = src.rates[`${p.pos}|bench`] * p.benchSlice, s = src.rates[`${p.pos}|starter`] * p.starterSlice;
    const share = b + s > 0 ? p.adjusted / (b + s) : 0;
    groups[`${p.pos}|bench`].total += b * share;
    groups[`${p.pos}|starter`].total += s * share;
    sliceGap = Math.max(sliceGap, Math.abs(b + s - p.adjusted));
    const ra = (result.rows[k].adjusted || {})[key];
    if (ra !== null && ra !== undefined) rowGap = Math.max(rowGap, Math.abs(ra - p.adjusted));
  });
  checks.push({source: key, total, target: pie - unpaid, vorpTotal, pie,
    groupGap: Math.max(...Object.values(groups).map(g => Math.abs(g.total - g.budget))), sliceGap, rowGap});
});
const indexed = Object.entries(result.indexed || {}).filter(([, ix]) => ix.factor !== null)
  .map(([key, ix]) => ({source: key, gap: Math.abs(ix.nativeTotal * ix.factor - ix.ddfTotal)}));
let bothLabels = 0;
Object.values(result.rows).forEach(row => Object.keys(row.estimated || {}).forEach(s => {
  if (/Below rosterable depth/.test((row.reasons || {})[s] || "")) bothLabels++;
}));
console.log(JSON.stringify({mix: (result.allocationMix || []).length, checks, indexed, bothLabels}));
