// JEG-1335: the page's fixed-pie check (curve-widget.js fixedPieDiagnostics)
// on an engine run of the worked example, at a given seat sigma. Prints
// {mix, checks: [{source, total, target, vorpTotal, groups, sliceGap, rowGap}],
// indexed, order: [{source, inversions, gap}], bothLabels}. Used by tests/test_fractional_seats_pie.py.
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
  let total = 0, vorpTotal = 0, sliceGap = 0, rowGap = 0, vorpGap = 0;
  Object.entries(src.players).forEach(([k, p]) => {
    total += p.adjusted;
    vorpTotal += p.vorpDisplay;
    const b = src.rates[`${p.pos}|bench`] * p.benchSlice, s = src.rates[`${p.pos}|starter`] * p.starterSlice;
    const share = b + s > 0 ? p.adjusted / (b + s) : 0;
    groups[`${p.pos}|bench`].total += b * share;
    groups[`${p.pos}|starter`].total += s * share;
    sliceGap = Math.max(sliceGap, Math.abs(b + s - p.adjusted));
    // The math inspector rebuilds VORP vs waivers as vorp x the source's factor.
    if (Number.isFinite(p.vorp)) vorpGap = Math.max(vorpGap, Math.abs(p.vorp * src.vorpFactor - p.vorpDisplay));
    const ra = (result.rows[k].adjusted || {})[key];
    if (ra !== null && ra !== undefined) rowGap = Math.max(rowGap, Math.abs(ra - p.adjusted));
  });
  checks.push({source: key, total, target: pie - unpaid, vorpTotal, pie,
    groupGap: Math.max(...Object.values(groups).map(g => Math.abs(g.total - g.budget))), sliceGap, rowGap, vorpGap});
});
const indexed = Object.entries(result.indexed || {}).filter(([, ix]) => ix.factor !== null)
  .map(([key, ix]) => ({source: key, gap: Math.abs(ix.nativeTotal * ix.factor - ix.ddfTotal)}));
// Same arithmetic as indexedOrderDiagnostics: each chart's Indexed values keep
// its own order over the players it prices, and each is native x factor.
const order = [];
Object.entries(result.sources).forEach(([key, src]) => {
  if (src.indexedFactor === null || src.indexedFactor === undefined) return;
  const ps = Object.entries(src.players).map(([k, p]) => ({k, ...p}));
  ps.sort((a, b) => b.native - a.native || (a.estimated === b.estimated ? 0 : a.estimated ? 1 : -1) || Number(a.k) - Number(b.k));
  let inversions = 0, gap = 0;
  ps.forEach(p => { gap = Math.max(gap, Math.abs(result.rows[p.k].indexed[key] - p.native * src.indexedFactor)); });
  for (let i = 0; i < ps.length; i += 1) for (let j = i + 1; j < ps.length; j += 1) {
    if (ps[i].native === ps[j].native) continue;
    if (!(result.rows[ps[i].k].indexed[key] > result.rows[ps[j].k].indexed[key])) inversions += 1;
  }
  order.push({source: key, inversions, gap});
});
let bothLabels = 0;
Object.values(result.rows).forEach(row => Object.keys(row.estimated || {}).forEach(s => {
  if (/Below rosterable depth/.test((row.reasons || {})[s] || "")) bothLabels++;
}));
console.log(JSON.stringify({mix: (result.allocationMix || []).length, checks, indexed, order, bothLabels}));
