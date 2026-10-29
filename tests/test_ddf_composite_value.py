"""JEG-471 / JEG-479 / JEG-497 (engine): the DDF Composite Value ("DDF Value").

The rule is docs/methodology.md "DDF Composite Value" (Jeremy, 2026-10-08/09):
per player, the equal-weight mean of each included input's ADJUSTED-view
value only. Three versions (JEG-497): ddf_value (the main one),
ddf_value_charts (the four charts), ddf_value_projections (ESPN, CBS rest of
season and Razzball); each is ONE number, the same in every view and tab.

JEG-1073 (Jeremy, 2026-10-25: "Keep adj trade chart avg as the main ddf and
projections as an alt."): ddf_value is the equal-weight mean of the four trade
charts' Adjusted values (FantasyCalc, USA Today, FantasyPros, CBS); the
projections are the alternate, ddf_value_projections. This reverses JEG-804,
which had made ddf_value the projections. The inputs setCompositeInputs
accepts are the four charts and it refuses projection keys; with no chart in I
ddf_value is null (no fallback to the projections). A reader's per-player
override replaces ddf_value only. The assertions below moved with that rule
(projection <-> chart roles swapped), not to get green. Exactly one
input pricing him gives that value, flagged low confidence ("Only one source
prices this player"); none gives null with "No source prices this player". An
input that is held or has not published the current week is never included,
even when a reader selects it; an input without the prior week is left out of
both weeks. Tier: rank by DDF Value and cut at the league's slot counts.

Checks, headless on the built dist/ (the live page):
1. ValueModel.compositeValue: mean of finite values, missing left out, 0 kept.
2. Every row's three versions, counts, sources, reasons and low-confidence
   flags are that mean over the version's inputs' Adjusted-view values, and
   identical in every tab, across scorings, team counts, a superflex roster,
   a bench share and a position-share edit.
3. setCompositeInputs: a subset changes the DDF fields only, fires the rows
   and shared events (shared only with publish), invalid input (no usable
   input) is refused with no change, null restores every value exactly.
4. Rank, zones and tiers by DDF Value.
5. Prior week: getPriorWeek(version) and the rows' priors use exactly the
   current week's inputs; an input without the prior week is left out of the
   current week too (simulated with an edited history index).
6. A held source (validationHold / promotionHold on its section, or on the
   derived section) and a source that has not published the current week are
   never inputs, even when requested; excluded lists the reason.

JEG-508 (docs/methodology.md "Value Pipeline", VP-6.3 / VP-7.3 / VP-11)
changed three rules this file pins, and only those assertions moved: the
inputs and series are source keys (a chart's input is "fantasycalc", whose
Adjusted-tab value is its Adjusted value; "fantasycalc_adjusted" and
"fantasycalc_adj_values" are retired); the tier is VP-7.3 (rank by DDF Value
within the position, then mean projected points, cut at the league
allocation of VP-2.2, DDF 0 = waiver) instead of ValueModel.roleMap; a source's
prior week is compared in the Adjusted tab, where its averaged value lives.
"""
from __future__ import annotations

import json
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from pipelines.nfl_week import content_week, content_week_start
from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402
from tests._holds import HOLD_FIELDS  # noqa: E402


def page_week() -> int:
    """The content week the page is on: product-data.js todayIsoDay takes the
    New York date. content_week() alone takes the machine's date (UTC on CI),
    which says week N+1 from 00:00 UTC Tuesday while the page still says
    week N, so the bumped charts read as a week ahead (JEG-1152)."""
    return content_week(datetime.now(ZoneInfo("America/New_York")).date())


def setUpModule():
    _render_env.ensure_built()


# JEG-1073: DDF Value = the four trade charts (JEG-804 had made it the projections).
PROJECTIONS = ["espn", "cbsros", "razzball"]
CHARTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
INPUTS = list(CHARTS)
ALL_SOURCES = PROJECTIONS + CHARTS  # all pipeline sources (for setups that need the full list)
VERSIONS = ["ddf_value", "ddf_value_charts", "ddf_value_projections"]
NONE = "No source prices this player"
ONE = "Only one source prices this player"

HELPERS = """
  const c = window.TradeValueCurveControls;
  const INPUTS = %s;
  const NONE = %s;
  const ONE = %s;
  const VERSIONS = ['ddf_value', 'ddf_value_charts', 'ddf_value_projections'];
  const NAME = {ddf_value: 'blended', ddf_value_charts: 'charts', ddf_value_projections: 'projections'};
  const COUNT = {ddf_value: 'ddfCount', ddf_value_charts: 'ddfChartsCount', ddf_value_projections: 'ddfProjectionsCount'};
  const LOW = {ddf_value: 'ddfLowConfidence', ddf_value_charts: 'ddfChartsLowConfidence', ddf_value_projections: 'ddfProjectionsLowConfidence'};
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  const activeView = () => c.getState().viewMode;
  const mean = (values, keys) => {
    const used = keys.filter(k => typeof values[k] === 'number' && Number.isFinite(values[k]));
    const v = used.map(k => values[k]);
    return {value: v.length >= 1 ? v.reduce((a, b) => a + b, 0) / v.length : null, count: v.length, used};
  };
  const near = (a, b) => (a === null || a === undefined) ? (b === null || b === undefined) : (b !== null && b !== undefined && Math.abs(a - b) <= 1e-9);
  const isDdf = k => VERSIONS.includes(k);
  // JEG-1044: Indexed follows the reader's basis, so a basis change legitimately moves the trade charts' Indexed
  // series. others() is every non-DDF series; othersNoCharts() drops those four for the "nothing else moved" rule.
  const CHART_SERIES = ['fantasycalc', 'usatoday', 'fantasypros', 'cbs'];
  const others = (skip = []) => JSON.stringify(c.getAllRows().map(r => {
    const v = {...r.values}; VERSIONS.concat(skip).forEach(k => delete v[k]); return [r.player_key, v];
  }));
  const othersNoCharts = () => others(CHART_SERIES);
  // The Adjusted tab does not follow the basis (VP-5.5), so there every non-DDF series must stay put.
  const adjOthers = () => { const was = activeView(); if (was !== 'adj') view('adj'); const o = others(); if (was !== 'adj') view(was); return o; };
  const ddf = () => JSON.stringify(c.getAllRows().map(r => [r.player_key, r.ddfTier, r.ddfPrior, r.ddfByVersion]));
  // A source's Adjusted value: its value on the Adjusted tab's row (VP-11).
  const seriesValue = (adjRow, s) => adjRow.values[s];
  // Every row against the rule. The expected Adjusted-view values come from
  // the Adjusted tab's rows; every version must also be the same on the rows
  // of the tab that was open.
  const checkMean = (tag, problems) => {
    let priced = 0, short = 0;
    const was = activeView();
    const rowsNow = c.getAllRows();
    if (was !== 'adj') view('adj');
    const adj = new Map(c.getAllRows().map(r => [r.player_key, r]));
    if (was !== 'adj') view(was);
    rowsNow.forEach(r => {
      const a = adj.get(r.player_key);
      for (const v of VERSIONS) {
        const series = c.getCompositeInputs(v).series;
        const values = Object.fromEntries(series.map(s => [s, seriesValue(a, s)]));
        const want = mean(values, series);
        const got = r.ddfByVersion[NAME[v]];
        if (!near(got.value, want.value) && problems.length < 40) problems.push(`${tag}/${v} ${r.name}: ${got.value} != mean ${want.value}`);
        if (!near(r.values[v], got.value) || !near(a.values[v], got.value)) problems.push(`${tag}/${v} ${r.name}: not the same in every tab`);
        if (got.count !== want.count || r[COUNT[v]] !== want.count) problems.push(`${tag}/${v} ${r.name}: count ${got.count} != ${want.count}`);
        if (JSON.stringify(got.sources) !== JSON.stringify(want.used)) problems.push(`${tag}/${v} ${r.name}: sources ${got.sources}`);
        if (got.reason !== (want.value === null ? NONE : null)) problems.push(`${tag}/${v} ${r.name}: reason ${got.reason}`);
        if (want.value === null && r.missingReasons?.[v] !== NONE) problems.push(`${tag}/${v} ${r.name}: missingReasons ${r.missingReasons?.[v]}`);
        if (got.lowConfidence !== (want.count === 1) || r[LOW[v]] !== (want.count === 1)) problems.push(`${tag}/${v} ${r.name}: lowConfidence ${got.lowConfidence} with ${want.count}`);
        if (got.confidenceNote !== (want.count === 1 ? ONE : null)) problems.push(`${tag}/${v} ${r.name}: note ${got.confidenceNote}`);
      }
      const blend = r.ddfByVersion.blended;
      if (r.ddfReason !== blend.reason || r.ddfPrior !== blend.prior || r.ddfConfidenceNote !== blend.confidenceNote
          || JSON.stringify(r.ddfSources) !== JSON.stringify(blend.sources)) {
        problems.push(`${tag} ${r.name}: flat DDF fields differ from ddfByVersion.blended`);
      }
      if (r.values.ddf_value !== null) priced += 1;
      if (r.ddfCount === 1) short += 1;
    });
    if (priced < 100) problems.push(`${tag}: only ${priced} players have a DDF Value`);
    return {priced, short};
  };
""" % (json.dumps(INPUTS), json.dumps(NONE), json.dumps(ONE))

PURE = """() => {
  const m = window.ValueModel.compositeValue;
  return {
    mixed: m({a: 10, b: null, c: 0, d: NaN, e: undefined, f: 20}, ['a', 'b', 'c', 'd', 'e', 'f', 'g']),
    none: m({a: null}, ['a', 'b']),
    order: m({a: 1, b: 2}, ['b', 'a']),
  };
}"""

MEAN = """async () => {""" + HELPERS + """
  const problems = [];
  const info = c.getCompositeInputs();
  if (!info.isDefault) problems.push('inputs are not the defaults on load');
  const keys = {}, series = {}, excluded = {};
  VERSIONS.forEach(v => { const i = c.getCompositeInputs(v); keys[v] = i.inputs; series[v] = i.series; excluded[v] = i.excluded; });
  let shortPlayers = 0;
  const steps = [
    ['load', () => {}],
    ['standard/8', () => { c.setScoring('standard'); c.setTeams(8); }],
    ['half_ppr/14', () => { c.setScoring('half_ppr'); c.setTeams(14); }],
    ['ppr/10', () => { c.setScoring('ppr'); c.setTeams(10); }],
    ['ppr/12 superflex', () => { c.setTeams(12); c.setRosterSpot('SUPERFLEX', 1); }],
    ['bench share 25%', () => { c.setRosterSpot('SUPERFLEX', 0); c.setBenchShareFraction(0.25); }],
    ['QB share +5pp', () => { c.setBenchShareFraction(0.15); c.setPositionWeights({QB: c.getPositionWeights().QB + 0.05}); }],
    ['VORP vs waivers tab', () => { c.setPositionWeights(null); view('vorp'); }],
    ['Indexed tab', () => { view('indexed'); }],
  ];
  for (const [tag, step] of steps) {
    step();
    shortPlayers += checkMean(tag, problems).short;
  }
  return {problems, keys, series, excluded, shortPlayers, activeAtEnd: activeView()};
}"""

SETTER = """async () => {""" + HELPERS + """
  const out = {problems: []};
  const events = {rows: 0, shared: []};
  window.addEventListener('trade-value-rows-change', () => { events.rows += 1; });
  window.addEventListener('trade-value-shared-change', e => { events.shared.push(e.detail.compositeInputs); });
  const baseOthers = others(), baseOthersNoCharts = othersNoCharts(), baseAdj = adjOthers(), baseDdf = ddf();
  out.set = c.setCompositeInputs(['fantasypros', 'fantasycalc', 'fantasycalc']);
  // Two charts: players only one of them prices exercise the one-source rule
  // (JEG-508: every chart prices every rosterable player, so the full blend
  // rarely has a one-source player).
  out.subsetShort = checkMean('subset', out.problems).short;
  // The charts all price the same players, so a pair never has a one-source
  // player; a single chart makes every priced player a one-source player.
  out.singleSet = c.setCompositeInputs(['cbs'], false);
  out.singleShort = checkMean('single chart', out.problems).short;
  out.singleInputs = c.getCompositeInputs('ddf_value').inputs;
  c.setCompositeInputs(['fantasypros', 'fantasycalc'], false);
  out.subsetMoved = ddf() !== baseDdf;
  out.othersSame = othersNoCharts() === baseOthersNoCharts;
  out.adjSame = adjOthers() === baseAdj;
  out.indexedFollowsBasis = activeView() !== 'indexed' || others() !== baseOthers;
  out.eventsAfterSet = JSON.parse(JSON.stringify(events));
  out.get = c.getCompositeInputs();
  const before = ddf();
  // JEG-1073: projection keys are not DDF Value inputs any more (alone or mixed with charts).
  out.invalid = [c.setCompositeInputs([]), c.setCompositeInputs(['fantasycalc_adj_values']), c.setCompositeInputs(['espn_vorp']),
    c.setCompositeInputs(['ddf_value']), c.setCompositeInputs('fantasycalc'), c.setCompositeInputs({fantasycalc: true}),
    c.setCompositeInputs(['fantasycalc', 'ddf_value_charts']),
    c.setCompositeInputs(['espn']), c.setCompositeInputs(['espn', 'cbsros', 'razzball']), c.setCompositeInputs(['fantasycalc', 'razzball'])];
  out.unchangedAfterInvalid = ddf() === before && JSON.stringify(c.getCompositeInputs()) === JSON.stringify(out.get);
  const quiet = events.shared.length;
  out.quietSet = c.setCompositeInputs(['cbs', 'usatoday'], false);
  checkMean('cbs + usatoday', out.problems);
  out.quietShared = events.shared.length - quiet;
  out.reset = c.setCompositeInputs(null);
  out.resetRestores = ddf() === baseDdf && others() === baseOthers;
  // JEG-1073: defaults == allowed == chart keys.  Passing defaults
  // explicitly should be recognised as the default state (isDefault: true).
  out.explicitDefaults = c.setCompositeInputs(c.getCompositeInputs().defaults);
  out.explicitDefaultsSame = ddf() === baseDdf;
  out.resetAlias = c.resetCompositeInputs();
  out.eventsEnd = events;
  return out;
}"""

RANK = """async () => {""" + HELPERS + """
  const problems = [];
  const firstTierInversion = rows => {
    const rank = ['starter', 'bench', 'waiver', null];
    let previousValue, groupWorst = -1, priorWorst = -1;
    for (let i = 0; i < rows.length; i += 1) {
      const value = rows[i].values.ddf_value, tier = rank.indexOf(rows[i].ddfTier);
      if (i > 0 && value !== previousValue) {
        priorWorst = Math.max(priorWorst, groupWorst);
        groupWorst = -1;
      }
      if (tier < priorWorst) return i;
      groupWorst = Math.max(groupWorst, tier);
      previousValue = value;
    }
    return -1;
  };
  // The display breaks exact value ties by name, while VP-7.3 uses mean PPG
  // then key. Check distinct value groups without imposing a display tie order.
  // Negative cases also catch an inversion hidden behind a mixed-tier tie group.
  const tierRow = (value, tier) => ({values: {ddf_value: value}, ddfTier: tier});
  if (firstTierInversion([tierRow(2, 'waiver'), tierRow(2, 'bench')]) !== -1)
    problems.push('tier-order guard rejects an exact value tie');
  for (const rows of [
    [tierRow(2, 'waiver'), tierRow(1, 'bench')],
    [tierRow(2, 'waiver'), tierRow(2, 'bench'), tierRow(1, 'bench')],
    [tierRow(2, 'waiver'), tierRow(2 - Number.EPSILON, 'bench')]
  ]) if (firstTierInversion(rows) < 0) problems.push('tier-order guard missed a strict value inversion');
  const P = ['QB', 'RB', 'WR', 'TE'];
  const sum = shape => P.reduce((s, p) => s + shape[p], 0) + shape.FLEX + (shape.SUPERFLEX || 0);
  c.setLockOrder('ddf_value');
  if (c.getRankSource() !== 'ddf_value') problems.push(`rank source ${c.getRankSource()} after setLockOrder`);
  const cases = [['ppr', 12, 0], ['standard', 8, 0], ['half_ppr', 14, 0], ['ppr', 10, 1]];
  for (const [scoring, teams, sf] of cases) {
    c.setScoring(scoring); c.setTeams(teams); c.setRosterSpot('SUPERFLEX', sf);
    const tag = `${scoring}/${teams}/sf${sf}`;
    if (c.getRankSource() !== 'ddf_value') problems.push(`${tag}: rank source fell back to ${c.getRankSource()}`);
    const shape = c.getRosterShape();
    const all = c.getAllRows();
    // VP-7.3: within a position, rank by DDF Value, then mean projected
    // points (missing last), then key; cut at the league allocation (VP-7.2);
    // DDF 0 is waiver.
    const alloc = Object.fromEntries(c.getAdjustmentWeights().allocation.map(a => [a.pos, a]));
    const want = new Map();
    P.forEach(pos => {
      const ranked = all.filter(r => r.pos === pos && r.values.ddf_value !== null).sort((a, b) =>
        (b.values.ddf_value - a.values.ddf_value)
        || ((a.meanPpg === null) - (b.meanPpg === null)) || ((b.meanPpg ?? 0) - (a.meanPpg ?? 0))
        || (a.player_key - b.player_key));
      ranked.forEach((r, i) => want.set(r.player_key, r.values.ddf_value === 0 ? 'waiver'
        : i + 1 <= alloc[pos].lineup ? 'starter' : i + 1 <= alloc[pos].rostered ? 'bench' : 'waiver'));
    });
    all.forEach(r => {
      const w = want.has(r.player_key) ? want.get(r.player_key) : null;
      if (r.ddfTier !== w) problems.push(`${tag} ${r.name}: ddfTier ${r.ddfTier} != ${w}`);
    });
    const starters = all.filter(r => r.ddfTier === 'starter').length;
    const bench = all.filter(r => r.ddfTier === 'bench').length;
    const slots = P.reduce((a, pos) => a + alloc[pos].lineup, 0);
    const rostered = P.reduce((a, pos) => a + alloc[pos].rostered, 0);
    if (slots !== teams * sum(shape)) problems.push(`${tag}: allocation starts ${slots}, slots ${teams * sum(shape)}`);
    if (starters > slots) problems.push(`${tag}: ${starters} DDF starters, slots ${slots}`);
    if (bench > rostered - slots) problems.push(`${tag}: ${bench} DDF bench, bench seats ${rostered - slots}`);
    for (const pos of ['ALL', 'QB', 'RB', 'WR', 'TE', 'FLEX']) {
      c.setPosition(pos);
      const rows = c.getRows();
      const t = `${tag}/${pos}`;
      for (let i = 1; i < rows.length; i += 1) {
        const a = rows[i - 1].values.ddf_value, b = rows[i].values.ddf_value;
        if (a === null && b !== null) { problems.push(`${t}: a priced player ranks after an unpriced one`); break; }
        if (a !== null && b !== null && b > a) { problems.push(`${t}: rows not in DDF Value order at ${i}`); break; }
      }
      const zones = c.getZones();
      const s = rows.filter(r => r.ddfTier === 'starter').length;
      const n = s + rows.filter(r => r.ddfTier === 'bench').length;
      const at = k => Math.max(1, Math.min(rows.length, k + 0.5));
      if (zones.starter_to_bench !== at(s)) problems.push(`${t}: starter zone ${zones.starter_to_bench}, DDF starters ${s}`);
      if (zones.bench_to_waiver !== at(n)) problems.push(`${t}: bench zone ${zones.bench_to_waiver}, DDF rostered ${n}`);
      if (P.includes(pos)) {
        // Across distinct values within one position, tiers are a prefix of
        // DDF order. Exact per-player VP-7.3 tie breaks are checked above.
        // ALL/FLEX can assign a slot to a lower value at another position.
        const firstBad = firstTierInversion(rows);
        if (firstBad >= 0) problems.push(`${t}: tiers out of DDF order at ${firstBad}`);
      }
      if (!window.TradeValueCurveDiagnostics.fixedPieIndexed) problems.push(`${t}: fixedPieIndexed false`);
    }
    c.setPosition('ALL');
  }
  c.setRosterSpot('SUPERFLEX', 0); c.setScoring('ppr'); c.setTeams(12);
  c.setLockOrder('espn');
  const plain = {info: c.getSourceInfo().map(i => i.key), active: c.getActiveSources(),
    withComposite: c.getSourceInfo({includeComposite: true}).filter(i => i.composite)};
  return {problems, plain, rank: c.getRankSource()};
}"""

PRIOR = """async () => {""" + HELPERS + """
  if (window.__setting) { c.setScoring(window.__setting[0]); c.setTeams(window.__setting[1]); }
  const out = {problems: [], versions: {}};
  view('adj');
  const adj = new Map(c.getAllRows().map(r => [r.player_key, r]));
  view('indexed');
  const rows = c.getAllRows();
  for (const v of VERSIONS) {
    const info = c.getCompositeInputs(v);
    const r = await c.getPriorWeek(v);
    const o = {available: r.available, reason: r.reason, sources: r.sources, inputs: r.inputs, excluded: r.excluded,
      currentWeek: r.currentWeek, priorWeek: r.priorWeek, week: r.week, infoSeries: info.series,
      infoPrior: info.priorAvailable, compared: 0, short: 0};
    out.versions[v] = o;
    if (!r.available) continue;
    // Every source is averaged exactly as its own prior week in the
    // Adjusted tab (VP-8: one pipeline run per week).
    view('adj');
    const ownPrior = {};
    for (const s of r.sources) ownPrior[s] = (await c.getPriorWeek(s)).values;
    view('indexed');
    for (const s of r.sources) {
      const own = ownPrior[s], used = r.seriesValues[s];
      if (JSON.stringify(Object.keys(own).sort()) !== JSON.stringify(Object.keys(used).sort())
          || Object.keys(own).some(pk => !near(own[pk], used[pk]))) out.problems.push(`${v} ${s}: averaged prior differs from getPriorWeek`);
    }
    rows.forEach(row => {
      const k = row.player_key;
      const a = adj.get(k);
      const cur = mean(Object.fromEntries(r.sources.map(s => [s, seriesValue(a, s)])), r.sources);
      if (!near(r.currentValues[k] ?? null, cur.value) && out.problems.length < 30) out.problems.push(`${v} ${row.name}: current ${r.currentValues[k]} != ${cur.value}`);
      if (!near(row.values[v], cur.value)) out.problems.push(`${v} ${row.name}: row value ${row.values[v]} != ${cur.value} over the pair's inputs`);
      const pv = {};
      r.sources.forEach(s => { pv[s] = r.seriesValues[s][k]; });
      const want = mean(pv, r.sources);
      const got = row.ddfByVersion[NAME[v]];
      if (!near(r.values[k] ?? null, want.value) && out.problems.length < 30) out.problems.push(`${v} ${row.name}: prior ${r.values[k]} != ${want.value}`);
      if (!near(got.prior, want.value) && out.problems.length < 30) out.problems.push(`${v} ${row.name}: row prior ${got.prior} != ${want.value}`);
      if (want.value !== null && r.counts[k] !== want.count) out.problems.push(`${v} ${row.name}: prior count ${r.counts[k]} != ${want.count}`);
      if (want.count === 1 && got.priorLowConfidence !== true) out.problems.push(`${v} ${row.name}: one-source prior not flagged`);
      if (want.count === 1) o.short += 1;
      if (want.value !== null && cur.value !== null) o.compared += 1;
    });
    if (v === 'ddf_value') {
      out.wrongWeek = await c.getPriorWeek(v, r.priorWeek - 1);
      const wk = await c.getWeekValues(v, r.priorWeek);
      out.weekValuesMatch = wk.available && JSON.stringify(wk.values) === JSON.stringify(r.values);
      out.history = await c.getHistoryWeeks(v);
      const all = c.getCompositeValues(v);
      out.valuesGetterMatch = JSON.stringify(all.prior) === JSON.stringify(r.values) && JSON.stringify(all.current) === JSON.stringify(r.currentValues);
    }
  }
  return out;
}"""

HELD = """async () => {""" + HELPERS + """
  const out = {problems: []};
  const leaks = (tag, held) => held && c.getAllRows().forEach(r => VERSIONS.forEach(v => {
    const s = r.ddfByVersion[NAME[v]].sources.find(k => held.includes(k));
    if (s && out.problems.length < 20) out.problems.push(`${tag}/${v} ${r.name}: ${s} in the DDF Value`);
  }));
  const held = window.__heldSeries;
  const heldKey = window.__heldKey;
  // JEG-1073: only the chart keys are valid setCompositeInputs arguments.
  const isChart = INPUTS.includes(heldKey);
  // Two other chart inputs (canonical order) to request beside the held one.
  const [A, B] = INPUTS.filter(k => k !== heldKey);
  out.load = c.getCompositeInputs();
  out.loadByVersion = Object.fromEntries(VERSIONS.map(v => [v, c.getCompositeInputs(v)]));
  // JEG-879: capture per-source excludedReason from getSourceInfo for
  // checking that held chart reasons are visible.
  out.sourceExcluded = Object.fromEntries(
    c.getSourceInfo().filter(s => s.excludedReason).map(s => [s.key, s.excludedReason])
  );
  checkMean('load', out.problems);
  leaks('load', held);
  if (isChart) {
    out.withHeld = c.setCompositeInputs([heldKey, A, B]);
    checkMean('requested with held', out.problems);
    leaks('requested with held', held);
    out.allRequested = c.setCompositeInputs(INPUTS);
    checkMean('all requested', out.problems);
    leaks('all requested', held);
    out.onlyHeld = c.setCompositeInputs([heldKey]);
    out.heldPlusOne = c.setCompositeInputs([heldKey, A]);
    out.afterStale = c.getCompositeInputs();
  } else {
    // Projection key: not a valid DDF Value input after JEG-1073.
    out.projectionRejected = c.setCompositeInputs([heldKey, 'fantasycalc', 'usatoday']);
    out.allRequested = c.setCompositeInputs(INPUTS);
    checkMean('all requested (projection held)', out.problems);
    leaks('all requested (projection held)', held);
  }
  c.setCompositeInputs(null);
  c.setScoring('standard'); c.setTeams(10);
  checkMean('standard/10', out.problems);
  leaks('standard/10', held);
  c.setScoring('ppr'); c.setTeams(12);
  const r = await c.getPriorWeek('ddf_value');
  out.prior = {available: r.available, reason: r.reason, sources: r.sources, inputs: r.inputs, excluded: r.excluded};
  const wk = await c.getWeekValues('ddf_value', r.priorWeek);
  out.weekSources = wk.sources;
  out.sourceInfo = c.getSourceInfo({includeComposite: true}).filter(i => i.composite);
  return out;
}"""

# JEG-1073 (Jeremy, 2026-10-25): with no trade chart in I the main DDF Value is
# unavailable (null), never a fallback to the projections.
NO_CHART = """async () => {
  const c = window.TradeValueCurveControls;
  const rows = c.getAllRows();
  const info = c.getCompositeInputs('ddf_value');
  return {
    inputs: info.inputs,
    ddfPriced: rows.filter(r => r.values.ddf_value !== null && r.values.ddf_value !== undefined).length,
    blendedPriced: rows.filter(r => r.ddfByVersion.blended.value !== null).length,
    blendedSources: rows.filter(r => r.ddfByVersion.blended.sources.length).length,
    projectionsPriced: rows.filter(r => r.values.ddf_value_projections !== null && r.values.ddf_value_projections !== undefined).length,
    reasons: [...new Set(rows.map(r => r.ddfByVersion.blended.reason))],
  };
}"""

HOLD = {"reason": "engine and reference disagree", "week": 5}


def hold_on(*sections, field="validationHold"):
    """The pipeline's shape: {reason, week, root} on each held section, combos stripped
    (JEG-569 part 2: no computation on old data)."""
    def edit(fixture):
        for section in sections:
            fixture["sources"][section][field] = {**HOLD, "root": section}
            fixture["sources"][section]["combos"] = {}
    return edit


def strip_holds(fixture):
    """This test's own unheld copy of the published fixture (JEG-569)."""
    for section in (fixture.get("sources") or {}).values():
        if isinstance(section, dict):
            for field in HOLD_FIELDS:
                section.pop(field, None)


def normalize_chart_weeks(fixture):
    """JEG-676: bump chart sections to the current content week.

    The published fixture may lag the calendar (e.g. charts at Week 5 while the
    calendar says Week 6) because the chain hasn't published the new week yet.
    Tests that need an unheld baseline also need charts at the current week so
    the JS freshness check doesn't mark them "not yet published".  Projections
    (ESPN, CBS ROS, Razzball) carry "rest of season" and are unaffected."""
    week = page_week()
    label = f"Week {week}"
    # The content_vintage for date-based sections (e.g. usatoday "2026-10-06")
    # needs a date in the current content week, not a "Week N" label.
    week_start = content_week_start(week)
    for key, section in (fixture.get("sources") or {}).items():
        if not isinstance(section, dict):
            continue
        wd = section.get("week_designated")
        cv = section.get("content_vintage")
        if not wd and not cv:
            continue
        # Only bump sections that carry a "Week N" week_designated (weekly
        # charts); rest-of-season projections have no week_designated.
        from pipelines.nfl_week import week_of_label
        if week_of_label(wd) is not None:
            section["week_designated"] = label
            # content_vintage: use a "Week N" label if it already is one,
            # otherwise bump the date into the current content week.
            if week_of_label(cv) is not None:
                section["content_vintage"] = label
            elif cv:
                section["content_vintage"] = week_start.isoformat()


def normalize_served_weeks(hist_index, fixture):
    """JEG-676: bump the history index's served weeks to the current content week.

    The JS determines each source's served week from the history index (via
    content fingerprinting at build time), not from the fixture's
    week_designated.  When normalize_chart_weeks bumps fixture sections to the
    current content week, the history index must agree or the JS sees a source
    as serving a stale week and excludes it.  Projections ("rest of season")
    also need bumping: they serve every week, so the history must report the
    same week as the charts for the prior-week pairing to include them."""
    week = page_week()
    served = hist_index.get("served") or {}
    for key in list(served):
        entry = served[key]
        if isinstance(entry, dict) and entry.get("week") != week:
            entry["week"] = week
            if "label_week" in entry and entry["label_week"] is not None:
                entry["label_week"] = week


def older_week(section):
    """The section's publisher has not posted the current week: label it a
    week behind every other chart."""
    def edit(fixture):
        meta = fixture["sources"][section]
        week = int(str(meta["week_designated"]).split()[-1])
        for field in ("week_designated", "content_vintage"):
            if meta.get(field):
                meta[field] = f"Week {week - 1}"
    return edit


def _launch(p):
    exe = _render_env.chromium_executable(p)
    if exe is None:
        raise _render_env.unavailable("no Chromium available")
    return p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)


def run(script: str, history_edit=None, data_edit=None, init_script=None, week_edit=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    overrides = {}
    if week_edit:
        # (week, edit): serve that saved week's file edited.
        week, edit = week_edit
        path = f"assets/history/week-{week}.json"
        doc = json.loads((DIST / path).read_text(encoding="utf-8"))
        edit(doc)
        overrides[path] = json.dumps(doc).encode("utf-8")
    # JEG-569: the published fixture may legitimately carry a hold (a held
    # source never takes the site down). These tests need an unheld
    # baseline, so they strip holds from their own copy, then apply the edit.
    # JEG-676: the fixture may also lag the calendar (charts at Week N-1 while
    # the calendar says Week N), so normalize chart weeks to the current week
    # before the data_edit applies test-specific holds or staleness.
    fixture = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
    strip_holds(fixture)
    normalize_chart_weeks(fixture)
    # JEG-676: the JS reads the served week from the history index (content
    # fingerprint match), not from the fixture's week_designated.  After
    # bumping the fixture, bump the index too so the JS agrees.
    index_path = DIST / "assets" / "history" / "index.json"
    if index_path.exists():
        hist_index = json.loads(index_path.read_text(encoding="utf-8"))
        if history_edit:
            history_edit(hist_index)
        normalize_served_weeks(hist_index, fixture)
        overrides["assets/history/index.json"] = json.dumps(hist_index).encode("utf-8")
    elif history_edit:
        raise ValueError("history_edit supplied but no history index exists")
    if data_edit:
        data_edit(fixture)
    overrides["assets/comparison-sources-data.json"] = json.dumps(fixture).encode("utf-8")
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            with serve(DIST, overrides) as base:
                page = browser.new_page(viewport={"width": 1280, "height": 900})
                if init_script:
                    page.add_init_script(init_script)
                errors = []
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                page.goto(base + "/", wait_until="networkidle")
                page.wait_for_function(
                    "() => window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=60000)
                page.wait_for_timeout(300)
                result = page.evaluate(script)
                if isinstance(result, dict):
                    result["pageErrors"] = errors
                return result
        finally:
            browser.close()


def assert_pair_or_none(test, version, keys, excluded):
    """Every input of a version is either averaged or excluded with "no prior
    week" (the charts' Adjusted values have no saved prior week until the
    prior-week Adjusted derivation lands; then they are averaged)."""
    reasons = {e["key"]: e["reason"] for e in excluded}
    for key in {"ddf_value": INPUTS, "ddf_value_charts": CHARTS, "ddf_value_projections": PROJECTIONS}[version]:
        if key not in keys:
            test.assertTrue(reasons.get(key, "").startswith("no prior week"), (version, key, reasons))


class DdfCompositeValueTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_pure_mean_skips_missing_and_keeps_zero(self):
        out = run(PURE)
        self.assertEqual(out["mixed"]["value"], 10.0)
        self.assertEqual(out["mixed"]["count"], 3)
        self.assertEqual(out["mixed"]["used"], ["a", "c", "f"])
        self.assertEqual(out["none"], {"value": None, "count": 0, "used": []})
        self.assertEqual(out["order"]["used"], ["b", "a"])

    def test_three_versions_from_adjusted_values_the_same_in_every_tab(self):
        out = run(MEAN)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["keys"]["ddf_value_projections"], PROJECTIONS)
        self.assertEqual(out["series"]["ddf_value_projections"], PROJECTIONS)
        # VA-3: every setting derives the charts' Adjusted values live, so at
        # the load setting all four charts have a prior week and count.
        self.assertEqual(out["keys"]["ddf_value_charts"], CHARTS)
        self.assertEqual(out["keys"]["ddf_value"], CHARTS)
        self.assertEqual(out["series"]["ddf_value"], CHARTS)
        self.assertEqual(out["series"]["ddf_value_charts"], CHARTS)
        for version in VERSIONS:
            assert_pair_or_none(self, version, out["keys"][version], out["excluded"][version])
        self.assertTrue(set(CHARTS) <= set(out["keys"]["ddf_value"]))
        self.assertTrue(set(PROJECTIONS).isdisjoint(out["keys"]["ddf_value"]), "JEG-1073: no projection in DDF Value")
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertEqual(out["activeAtEnd"], "indexed")

    def test_set_composite_inputs(self):
        out = run(SETTER)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertTrue(out["set"]["ok"], out["set"])
        self.assertEqual(out["set"]["inputs"], ["fantasycalc", "fantasypros"])
        self.assertFalse(out["set"]["isDefault"])
        self.assertTrue(out["subsetMoved"])
        self.assertTrue(out["othersSame"], "a DDF Value input change moved another series (other than the charts' Indexed series)")
        self.assertTrue(out["adjSame"], "a DDF Value input change moved an Adjusted-tab series")
        self.assertTrue(out["indexedFollowsBasis"], "JEG-1044: Indexed should follow the basis, but no Indexed series moved")
        self.assertEqual(out["subsetShort"], 0, "charts all price the same players, so a pair has no one-source player")
        self.assertTrue(out["singleSet"]["ok"], out["singleSet"])
        self.assertEqual(out["singleInputs"], ["cbs"])
        self.assertGreater(out["singleShort"], 100, "no player has one source, so the one-source rule went untested")
        self.assertGreaterEqual(out["eventsAfterSet"]["rows"], 1)
        self.assertEqual(out["eventsAfterSet"]["shared"], [["fantasycalc", "fantasypros"]])
        # v2 contract: a deselected input's reason is exactly one string (the only reason v2 lets a reader
        # re-tick). JEG-1044 renamed it "not selected" -> "not in your basis" (no v2 code reads the string).
        self.assertEqual({e["key"]: e["reason"] for e in out["get"]["excluded"]},
                         {k: "not in your basis" for k in INPUTS if k not in ("fantasycalc", "fantasypros")})
        for refused in out["invalid"]:
            self.assertFalse(refused["ok"], refused)
            self.assertIn("error", refused)
        self.assertTrue(out["unchangedAfterInvalid"])
        self.assertTrue(out["quietSet"]["ok"], out["quietSet"])
        self.assertEqual(out["quietShared"], 0, "publish=false still fired trade-value-shared-change")
        self.assertTrue(out["reset"]["ok"] and out["reset"]["isDefault"], out["reset"])
        self.assertTrue(out["resetRestores"], "null did not restore every value")
        # JEG-1073: defaults == allowed == chart keys, so passing allowed
        # explicitly is the same as the default state.
        self.assertTrue(out["explicitDefaults"]["ok"], out["explicitDefaults"])
        self.assertTrue(out["explicitDefaults"]["isDefault"],
                        "setCompositeInputs(allowed) should be isDefault")
        self.assertTrue(out["explicitDefaultsSame"],
                        "setCompositeInputs(allowed) should produce the same DDF value as baseDdf")
        self.assertTrue(out["resetAlias"]["ok"])

    def test_rank_zones_and_tiers_by_ddf_value(self):
        out = run(RANK)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        for version in VERSIONS:
            self.assertNotIn(version, out["plain"]["info"])
            self.assertNotIn(version, out["plain"]["active"])
        entries = {e["key"]: e for e in out["plain"]["withComposite"]}
        self.assertEqual(list(entries), VERSIONS)
        entry = entries["ddf_value"]
        self.assertEqual((entry["label"], entry["composite"], entry["available"]), ("DDF Value", True, True))
        self.assertEqual(out["rank"], "espn")

    def test_prior_week_uses_exactly_the_current_inputs(self):
        out = run(PRIOR)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        for version, res in out["versions"].items():
            if not res["infoPrior"]:
                self.assertFalse(res["available"], (version, res))
                self.assertTrue(res["reason"], version)
                continue
            self.assertTrue(res["available"], (version, res))
            self.assertEqual(res["priorWeek"], res["currentWeek"] - 1)
            self.assertEqual(res["week"], res["priorWeek"])
            self.assertEqual(res["sources"], res["infoSeries"], f"{version}: the pair's inputs are not the current week's")
            self.assertGreater(res["compared"], 100, version)
        self.assertTrue(out["versions"]["ddf_value"]["available"])
        self.assertFalse(out["wrongWeek"]["available"])
        self.assertTrue(out["weekValuesMatch"], "getWeekValues(ddf_value, prior) differs from getPriorWeek")
        self.assertTrue(out["valuesGetterMatch"], "getCompositeValues differs from getPriorWeek")
        self.assertEqual(out["history"]["servedWeek"], out["versions"]["ddf_value"]["currentWeek"])

    def test_inputs_without_the_prior_week_are_left_out_of_both_weeks(self):
        def edit(index):
            index["served"].pop("usatoday")   # no saved week matches
        out = run(PRIOR, history_edit=edit)
        self.assertEqual(out["pageErrors"], [])
        # JEG-1073: a chart is a DDF Value input, so it leaves ddf_value (and the charts version).
        for version in ("ddf_value", "ddf_value_charts"):
            res = out["versions"][version]
            self.assertTrue(res["available"], res)
            excluded = {e["key"]: e["reason"] for e in res["excluded"]}
            self.assertTrue(excluded["usatoday"].startswith("no prior week: "), excluded)
            self.assertNotIn("usatoday", res["sources"])
            self.assertGreater(res["compared"], 100)
        # The projections alternate is unaffected by a chart's missing week.
        alt = out["versions"]["ddf_value_projections"]
        self.assertTrue(alt["available"], alt)
        self.assertEqual(alt["excluded"], [])
        self.assertEqual(alt["sources"], PROJECTIONS)
        # Both weeks, rows included, are means over exactly res["sources"] (checked per player).
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))


CHART_SERIES = CHARTS
# Off the saved 12-team setup the charts' Adjusted values are derived from the
# saved weeks too (JEG-479 "Build prior week").
DERIVED_SETTING = "window.__setting = ['half_ppr', 10];"


def served_week(source):
    index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    return index["served"][source]["week"]


class DdfChartPriorWeekTest(unittest.TestCase):
    """JEG-479 (Jeremy 2026-10-09, "Build prior week"): the four trade charts
    have a prior-week Adjusted value (the same derivePublishedViews batch on
    that week's saved natives), so they count in both weeks of ddf_value and
    ddf_value_charts; a chart without saved inputs for the prior week is
    still left out of both weeks."""

    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_charts_count_in_both_weeks(self):
        out = run(PRIOR, init_script=DERIVED_SETTING)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        # JEG-1073: ddf_value = the four charts (same as ddf_value_charts); the projections are the alternate.
        want = {"ddf_value": CHART_SERIES, "ddf_value_charts": CHART_SERIES,
                "ddf_value_projections": PROJECTIONS}
        for version, res in out["versions"].items():
            self.assertTrue(res["available"], (version, res))
            self.assertEqual(res["excluded"], [], version)
            self.assertEqual(res["sources"], want[version], version)
            self.assertEqual(res["infoSeries"], want[version], version)
            self.assertGreater(res["compared"], 100, version)

    def test_chart_without_saved_prior_inputs_is_left_out_of_both_weeks(self):
        # JEG-676: use the normalized served week (content_week), not the
        # on-disk history week, since normalize_served_weeks bumps all sources.
        prior = page_week() - 1

        def drop_cbs(doc):
            doc["sources"].pop("cbs")
        out = run(PRIOR, init_script=DERIVED_SETTING, week_edit=(prior, drop_cbs))
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        # JEG-1073: cbs is a DDF Value input, so it is out of both weeks of ddf_value and ddf_value_charts.
        for version in ("ddf_value", "ddf_value_charts"):
            res = out["versions"][version]
            self.assertTrue(res["available"], (version, res))
            excluded = {e["key"]: e["reason"] for e in res["excluded"]}
            self.assertEqual(set(excluded), {"cbs"}, (version, excluded))
            self.assertTrue(excluded["cbs"].startswith(f"no prior week: no Week {prior} CBS"), excluded)
            self.assertNotIn("cbs", res["sources"])
            self.assertEqual([s for s in res["sources"] if s in CHART_SERIES], CHART_SERIES[:3], version)
        # The projections alternate is unaffected by dropping a chart.
        alt = out["versions"]["ddf_value_projections"]
        self.assertTrue(alt["available"], ("ddf_value_projections", alt))
        self.assertEqual(alt["excluded"], [], "ddf_value_projections")
        self.assertEqual(alt["sources"], PROJECTIONS, "ddf_value_projections")

    def test_saved_setup_derives_live_too(self):
        # VA-3 (Jeremy 2026-10-09, "Compute live everywhere"): the saved
        # vorp_views are retired, so at Full PPR / 12 / standard roster too
        # every chart's Adjusted values are derived live and have a prior
        # week.  JEG-1073: ddf_value = the four charts.
        out = run(PRIOR)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        want = {"ddf_value": CHART_SERIES, "ddf_value_charts": CHART_SERIES,
                "ddf_value_projections": PROJECTIONS}
        for version, res in out["versions"].items():
            self.assertTrue(res["available"], (version, res))
            self.assertEqual(res["excluded"], [], version)
            self.assertEqual(res["sources"], want[version], version)


HELD_INIT = "window.__heldKey = %s; window.__heldSeries = %s;"
# The DDF series an input contributes (exact keys).
# JEG-1073: held-but-included tests use chart sources (the DDF Value inputs).
# Held projection tests verify the projection stays in ddf_value_projections only.
HELD_SERIES = {"espn": ["espn"],
               "fantasypros": ["fantasypros"],
               "cbsros": ["cbsros"],
               "razzball": ["razzball"],
               "fantasycalc": ["fantasycalc"],
               "cbs": ["cbs"],
               "usatoday": ["usatoday"]}


class DdfHeldSeriesTest(unittest.TestCase):
    """JEG-479 / JEG-569 part 2: a held source stays in the pipeline (weights,
    pie, universe) so no other source's Adjusted/VORP values change, but is
    excluded from the DDF blend and hidden from display.  A source not published
    for the current week is genuinely excluded from everything."""

    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")
        # No held series: nothing is checked for leaking (run() strips any
        # hold the published fixture carries, JEG-569).
        cls.unheld = run(HELD, init_script=HELD_INIT % (json.dumps("fantasycalc"), "null"))

    def held_run(self, data_edit, key):
        return run(HELD, data_edit=data_edit, init_script=HELD_INIT % (json.dumps(key), json.dumps(HELD_SERIES[key])))

    def assert_held_but_included(self, out, key, reason_start):
        """JEG-569 part 2: a held CHART source participates in the pipeline
        (weights, pie, universe) but is excluded from the DDF blend and hidden
        from display.  It is reported as held and in the pipeline inputs.
        JEG-1073: only called for chart sources (the DDF Value inputs)."""
        self.assertIn(key, CHARTS, "assert_held_but_included is for charts")
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        # The held chart IS in the pipeline inputs for ddf_value and ddf_value_charts.
        for version in ("ddf_value", "ddf_value_charts"):
            info = out["loadByVersion"][version]
            self.assertIn(key, info["inputs"], f"{version}: held chart should be in inputs")
        # JEG-1073: defaults = COMPOSITE_INPUT_KEYS (charts); this key IS a chart.
        self.assertIn(key, out["load"]["defaults"])
        # It is reported as held.
        self.assertIn(key, out["load"]["held"])
        # No page errors or problems.
        self.assertTrue(out["allRequested"]["ok"])
        # The held source is in the prior week too.
        prior = out["prior"]
        self.assertTrue(prior["available"], prior)

    def assert_held_projection_not_in_ddf_value(self, out, key, reason_start):
        """JEG-1073: a held PROJECTION source is not in ddf_value (charts only)
        but stays in ddf_value_projections with the 'held:' label."""
        self.assertIn(key, PROJECTIONS, "assert_held_projection_not_in_ddf_value is for projections")
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        # The held projection is NOT in ddf_value inputs (charts only).
        ddf_info = out["loadByVersion"]["ddf_value"]
        self.assertNotIn(key, ddf_info["inputs"], "ddf_value: projection should not be in chart-only inputs")
        # The held projection IS in ddf_value_projections inputs (held but included there).
        alt_info = out["loadByVersion"]["ddf_value_projections"]
        self.assertIn(key, alt_info["inputs"], "ddf_value_projections: held projection should be in inputs")
        # JEG-1073: defaults = COMPOSITE_INPUT_KEYS = charts; projection is NOT in defaults.
        self.assertNotIn(key, out["load"]["defaults"])
        # getCompositeInputs().held only reports DDF Value (chart) sources.
        self.assertNotIn(key, out["load"]["held"])
        # The projection IS hidden from display (series) but present in inputs.
        self.assertNotIn(key, alt_info["series"],
                         "held projection should be hidden from display series")
        # JEG-879: the held chart's reason is visible via getSourceInfo().excludedReason.
        self.assertIn(key, out["sourceExcluded"],
                      f"{key} should have excludedReason in sourceInfo")
        self.assertTrue(out["sourceExcluded"][key].startswith(reason_start),
                        f"{key} excludedReason: {out['sourceExcluded'][key]}")

    def assert_never_included(self, out, key, reason_start):
        """A source genuinely missing (not yet published for the week).
        JEG-804: ddf_value = projections only."""
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        base = self.unheld["loadByVersion"]
        members = {"ddf_value": CHARTS, "ddf_value_charts": CHARTS, "ddf_value_projections": PROJECTIONS}
        for version, info in out["loadByVersion"].items():
            self.assertNotIn(key, info["inputs"], version)
            if info["priorAvailable"]:
                self.assertEqual(info["inputs"], [k for k in base[version]["inputs"] if k != key], version)
            if key in members[version]:
                entry = {e["key"]: e for e in info["excluded"]}[key]
                self.assertTrue(entry["reason"].startswith(reason_start), entry)
        self.assertNotIn(key, out["load"]["defaults"])
        # Requested with usable inputs: dropped and reported, not fatal.
        self.assertTrue(out["withHeld"]["ok"], out["withHeld"])
        self.assertEqual(out["withHeld"]["inputs"], ["espn", "cbsros"])
        self.assertEqual([d["key"] for d in out["withHeld"]["dropped"]], [key])
        self.assertTrue(out["withHeld"]["dropped"][0]["reason"].startswith(reason_start))
        # v2 contract: only a reader-deselected input reads "not selected"; the
        # held / unpublished one keeps its own reason (shown disabled).
        reasons = {e["key"]: e["reason"] for e in out["withHeld"]["excluded"]}
        self.assertTrue(reasons.pop(key).startswith(reason_start), reasons)
        self.assertEqual(reasons, {k: "not selected" for k in reasons}, reasons)
        self.assertTrue(reasons, "no deselected input to check")
        self.assertTrue(out["allRequested"]["ok"])
        self.assertNotIn(key, out["allRequested"]["inputs"])
        # A stale saved list (v2 replays it) never fails. Alone, nothing
        # usable remains, so the defaults apply; with one other input that
        # input alone is the choice (one source is enough, Jeremy 2026-10-09).
        for stale in (out["onlyHeld"], out["heldPlusOne"]):
            self.assertTrue(stale["ok"], stale)
            self.assertEqual([d["key"] for d in stale["dropped"]], [key])
            self.assertNotIn(key, stale["inputs"])
        self.assertTrue(out["onlyHeld"]["fellBackToDefaults"], out["onlyHeld"])
        self.assertTrue(out["onlyHeld"]["isDefault"], out["onlyHeld"])
        self.assertNotIn("fellBackToDefaults", out["heldPlusOne"])
        self.assertEqual(out["heldPlusOne"]["inputs"], ["espn"])
        self.assertEqual(out["afterStale"]["inputs"], ["espn"])
        # Prior week: out of both weeks.
        prior = out["prior"]
        self.assertTrue(prior["available"], prior)
        self.assertNotIn(key, prior["inputs"])
        for series in HELD_SERIES[key]:
            self.assertNotIn(series, prior["sources"])
            self.assertNotIn(series, out["weekSources"])
        self.assertIn(key, [e["key"] for e in prior["excluded"]])
        for entry in out["sourceInfo"]:
            self.assertNotIn(key, entry["inputs"])
            self.assertFalse(entry["stale"])

    def test_validation_hold_on_a_chart_keeps_it_in_ddf_value(self):
        """JEG-1073: held FantasyCalc stays in ddf_value (trade chart) inputs."""
        out = self.held_run(hold_on("fantasycalc"), "fantasycalc")
        self.assert_held_but_included(out, "fantasycalc", "held: " + HOLD["reason"])

    def test_promotion_hold_on_a_chart_is_a_hold_too(self):
        out = self.held_run(hold_on("fantasypros", field="promotionHold"), "fantasypros")
        self.assert_held_but_included(out, "fantasypros", "held: " + HOLD["reason"])

    def test_a_held_chart_is_in_every_version(self):
        """JEG-569 part 2: a held chart is still included in the pipeline."""
        out = self.held_run(hold_on("usatoday"), "usatoday")
        self.assert_held_but_included(out, "usatoday", "held: " + HOLD["reason"])

    def test_held_projection_not_in_ddf_value_but_in_projections_version(self):
        """JEG-1073: a held projection (espn) is NOT in ddf_value (charts
        only) but IS in ddf_value_projections with the held label."""
        out = self.held_run(hold_on("espn"), "espn")
        self.assert_held_projection_not_in_ddf_value(out, "espn", "held: " + HOLD["reason"])

    def test_held_projection_cbsros_not_in_ddf_value(self):
        """JEG-1073: held CBS ROS (a projection) stays in ddf_value_projections, not ddf_value."""
        out = self.held_run(hold_on("cbsros"), "cbsros")
        self.assert_held_projection_not_in_ddf_value(out, "cbsros", "held: " + HOLD["reason"])

    def test_projection_key_rejected_by_set_composite_inputs(self):
        """JEG-1073: projection keys are not valid setCompositeInputs arguments."""
        out = self.held_run(hold_on("espn"), "espn")
        self.assertFalse(out["projectionRejected"]["ok"], "projection key should be rejected")
        self.assertIn("error", out["projectionRejected"])

    def test_a_chart_not_yet_published_for_the_week_is_excluded_from_charts(self):
        out = self.held_run(older_week("usatoday"), "usatoday")
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        # A chart source not published for the current week is excluded from
        # ddf_value_charts and (JEG-1073: the charts are its inputs) ddf_value.
        for version in ("ddf_value", "ddf_value_charts"):
            info = out["loadByVersion"][version]
            self.assertNotIn("usatoday", info["inputs"], version)
            excluded = {e["key"]: e["reason"] for e in info["excluded"]}
            self.assertIn("usatoday", excluded, f"usatoday should be excluded from {version}")
            self.assertTrue(excluded["usatoday"].startswith("not yet published"),
                            f"{version} usatoday reason: {excluded['usatoday']}")
        self.assertIn("usatoday", [e if isinstance(e, str) else e.get("key") for e in out["load"]["notPublished"]])
        # The projections alternate does not depend on it.
        self.assertNotIn("usatoday", out["loadByVersion"]["ddf_value_projections"]["inputs"])
        self.assertEqual(out["loadByVersion"]["ddf_value_projections"]["inputs"], PROJECTIONS)

    def test_no_chart_in_the_pipeline_leaves_ddf_value_null_not_the_projections(self):
        """JEG-1073: with every chart unpublished for the week the main DDF
        Value is null for everyone; it does not fall back to the projections
        (which still price players in the alternate). Fails on the JEG-804
        fallback, where a missing projection set fell back to all sources."""
        def all_charts_old(fixture):
            for chart in CHARTS:
                older_week(chart)(fixture)
        out = run(NO_CHART, data_edit=all_charts_old)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["inputs"], [])
        self.assertEqual(out["ddfPriced"], 0)
        self.assertEqual(out["blendedPriced"], 0)
        self.assertEqual(out["blendedSources"], 0)
        self.assertGreater(out["projectionsPriced"], 100, "the projections alternate should still price players")

    def test_unheld_fixture_has_no_held_series(self):
        out = self.unheld
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertEqual(out["load"]["held"], [])
        self.assertEqual(out["load"]["notPublished"], [])
        charts = out["loadByVersion"]["ddf_value_charts"]
        reasons = {e["key"]: e["reason"] for e in charts["excluded"]}
        for key in CHARTS:
            self.assertTrue(key in charts["inputs"] or reasons.get(key, "").startswith("no prior week"), (key, reasons))
        # JEG-1073: withHeld uses a chart key (fantasycalc) in the unheld baseline.
        self.assertNotIn("dropped", out["withHeld"])


if __name__ == "__main__":
    unittest.main()
