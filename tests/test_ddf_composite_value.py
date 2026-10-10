"""JEG-471 / JEG-479 / JEG-497 (engine): the DDF Composite Value ("DDF Value").

The rule is docs/methodology.md "DDF Composite Value" (Jeremy, 2026-10-08/09):
per player, the equal-weight mean of each included input's ADJUSTED-view
value only -- ESPN, CBS rest of season and Razzball, and each published
chart's Adjusted values. Three versions (JEG-497): ddf_value (all seven
inputs), ddf_value_charts (the four charts), ddf_value_projections (the three
projections); each is ONE number, the same in every view and tab. Exactly one
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

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


INPUTS = ["espn", "cbsros", "razzball", "fantasycalc", "usatoday", "fantasypros", "cbs"]
PROJECTIONS = ["espn", "cbsros", "razzball"]
CHARTS = ["fantasycalc", "usatoday", "fantasypros", "cbs"]
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
  const others = () => JSON.stringify(c.getAllRows().map(r => {
    const v = {...r.values}; VERSIONS.forEach(k => delete v[k]); return [r.player_key, v];
  }));
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
  const baseOthers = others(), baseDdf = ddf();
  out.set = c.setCompositeInputs(['cbsros', 'espn', 'espn']);
  // Two projections: players only one of them projects exercise the
  // one-source rule (JEG-508: every chart prices every rosterable player, so
  // the full blend rarely has a one-source player).
  out.subsetShort = checkMean('subset', out.problems).short;
  out.subsetMoved = ddf() !== baseDdf;
  out.othersSame = others() === baseOthers;
  out.eventsAfterSet = JSON.parse(JSON.stringify(events));
  out.get = c.getCompositeInputs();
  const before = ddf();
  out.invalid = [c.setCompositeInputs([]), c.setCompositeInputs(['fantasycalc_adj_values']), c.setCompositeInputs(['espn_vorp']),
    c.setCompositeInputs(['ddf_value']), c.setCompositeInputs('espn'), c.setCompositeInputs({espn: true}),
    c.setCompositeInputs(['espn', 'ddf_value_charts'])];
  out.unchangedAfterInvalid = ddf() === before && JSON.stringify(c.getCompositeInputs()) === JSON.stringify(out.get);
  const quiet = events.shared.length;
  out.quietSet = c.setCompositeInputs(['razzball', 'cbsros'], false);
  checkMean('razzball + cbsros', out.problems);
  out.quietShared = events.shared.length - quiet;
  out.reset = c.setCompositeInputs(null);
  out.resetRestores = ddf() === baseDdf && others() === baseOthers;
  out.explicitDefaults = c.setCompositeInputs(c.getCompositeInputs().defaults);
  out.explicitDefaultsSame = ddf() === baseDdf;
  out.resetAlias = c.resetCompositeInputs();
  out.eventsEnd = events;
  return out;
}"""

RANK = """async () => {""" + HELPERS + """
  const problems = [];
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
        // Within one position the tiers are a prefix of the DDF order (not in
        // ALL or FLEX: a slot can go to a lower value at another position).
        const rank = ['starter', 'bench', 'waiver', null];
        const order = rows.map(r => rank.indexOf(r.ddfTier));
        const firstBad = order.findIndex((tier, i) => i > 0 && tier < order[i - 1]);
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
  out.load = c.getCompositeInputs();
  out.loadByVersion = Object.fromEntries(VERSIONS.map(v => [v, c.getCompositeInputs(v)]));
  checkMean('load', out.problems);
  leaks('load', held);
  out.withHeld = c.setCompositeInputs([window.__heldKey, 'espn', 'cbsros']);
  checkMean('requested with held', out.problems);
  leaks('requested with held', held);
  out.allRequested = c.setCompositeInputs(INPUTS);
  checkMean('all requested', out.problems);
  leaks('all requested', held);
  out.onlyHeld = c.setCompositeInputs([window.__heldKey]);
  out.heldPlusOne = c.setCompositeInputs([window.__heldKey, 'espn']);
  out.afterStale = c.getCompositeInputs();
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

HOLD = {"reason": "engine and reference disagree", "week": 5}


def hold_on(*sections, field="validationHold"):
    """The pipeline's shape: {reason, week, root, kept_week} on each held section."""
    def edit(fixture):
        for section in sections:
            root = "cbs" if section == "cbs_adjusted" else section.replace("_adjusted", "")
            fixture["sources"][section][field] = {**HOLD, "root": root, "kept_week": HOLD["week"] - 1}
    return edit


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
    if history_edit:
        index = json.loads((DIST / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
        history_edit(index)
        overrides["assets/history/index.json"] = json.dumps(index).encode("utf-8")
    if data_edit:
        fixture = json.loads((DIST / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
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
        self.assertEqual(out["keys"]["ddf_value"], INPUTS)
        self.assertEqual(out["series"]["ddf_value_charts"], CHARTS)
        for version in VERSIONS:
            assert_pair_or_none(self, version, out["keys"][version], out["excluded"][version])
        self.assertTrue(set(PROJECTIONS) <= set(out["keys"]["ddf_value"]))
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertEqual(out["activeAtEnd"], "indexed")

    def test_set_composite_inputs(self):
        out = run(SETTER)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertTrue(out["set"]["ok"], out["set"])
        self.assertEqual(out["set"]["inputs"], ["espn", "cbsros"])
        self.assertFalse(out["set"]["isDefault"])
        self.assertTrue(out["subsetMoved"])
        self.assertTrue(out["othersSame"], "a DDF Value input change moved another series")
        self.assertGreater(out["subsetShort"], 0, "no player has one source, so the one-source rule went untested")
        self.assertGreaterEqual(out["eventsAfterSet"]["rows"], 1)
        self.assertEqual(out["eventsAfterSet"]["shared"], [["espn", "cbsros"]])
        # v2 contract: a deselected input's reason is exactly "not selected"
        # (the only reason v2 lets a reader re-tick).
        self.assertEqual({e["key"]: e["reason"] for e in out["get"]["excluded"]},
                         {k: "not selected" for k in INPUTS if k not in ("espn", "cbsros")})
        for refused in out["invalid"]:
            self.assertFalse(refused["ok"], refused)
            self.assertIn("error", refused)
        self.assertTrue(out["unchangedAfterInvalid"])
        self.assertTrue(out["quietSet"]["ok"], out["quietSet"])
        self.assertEqual(out["quietShared"], 0, "publish=false still fired trade-value-shared-change")
        self.assertTrue(out["reset"]["ok"] and out["reset"]["isDefault"], out["reset"])
        self.assertTrue(out["resetRestores"], "null did not restore every value")
        self.assertTrue(out["explicitDefaults"]["isDefault"], out["explicitDefaults"])
        self.assertTrue(out["explicitDefaultsSame"])
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
            index["served"].pop("razzball")   # no saved week matches
        out = run(PRIOR, history_edit=edit)
        self.assertEqual(out["pageErrors"], [])
        for version in ("ddf_value", "ddf_value_projections"):
            res = out["versions"][version]
            self.assertTrue(res["available"], res)
            excluded = {e["key"]: e["reason"] for e in res["excluded"]}
            self.assertTrue(excluded["razzball"].startswith("no prior week: "), excluded)
            self.assertNotIn("razzball", res["sources"])
            self.assertGreater(res["compared"], 100)
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
        want = {"ddf_value": PROJECTIONS + CHART_SERIES, "ddf_value_charts": CHART_SERIES,
                "ddf_value_projections": PROJECTIONS}
        for version, res in out["versions"].items():
            self.assertTrue(res["available"], (version, res))
            self.assertEqual(res["excluded"], [], version)
            self.assertEqual(res["sources"], want[version], version)
            self.assertEqual(res["infoSeries"], want[version], version)
            self.assertGreater(res["compared"], 100, version)

    def test_chart_without_saved_prior_inputs_is_left_out_of_both_weeks(self):
        prior = served_week("cbs") - 1

        def drop_cbs(doc):
            doc["sources"].pop("cbs")
        out = run(PRIOR, init_script=DERIVED_SETTING, week_edit=(prior, drop_cbs))
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        for version in ("ddf_value", "ddf_value_charts"):
            res = out["versions"][version]
            self.assertTrue(res["available"], (version, res))
            excluded = {e["key"]: e["reason"] for e in res["excluded"]}
            self.assertEqual(set(excluded), {"cbs"}, (version, excluded))
            self.assertTrue(excluded["cbs"].startswith(f"no prior week: no Week {prior} CBS"), excluded)
            self.assertNotIn("cbs", res["sources"])
            self.assertEqual([s for s in res["sources"] if s in CHART_SERIES], CHART_SERIES[:3], version)

    def test_saved_setup_derives_live_too(self):
        # VA-3 (Jeremy 2026-10-09, "Compute live everywhere"): the saved
        # vorp_views are retired, so at Full PPR / 12 / standard roster too
        # every chart's Adjusted values are derived live and have a prior
        # week: all seven inputs count in both weeks.
        out = run(PRIOR)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        want = {"ddf_value": PROJECTIONS + CHART_SERIES, "ddf_value_charts": CHART_SERIES,
                "ddf_value_projections": PROJECTIONS}
        for version, res in out["versions"].items():
            self.assertTrue(res["available"], (version, res))
            self.assertEqual(res["excluded"], [], version)
            self.assertEqual(res["sources"], want[version], version)


HELD_INIT = "window.__heldKey = %s; window.__heldSeries = %s;"
# The DDF series an input contributes (exact keys).
HELD_SERIES = {"fantasycalc": ["fantasycalc"],
               "usatoday": ["usatoday"],
               "cbs": ["cbs"],
               "razzball": ["razzball"]}


class DdfHeldSeriesTest(unittest.TestCase):
    """JEG-479 (Jeremy 2026-10-08): a held source and its derived series, and a
    source that has not published the current week, never enter the DDF
    Value, even when a reader selects them."""

    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")
        # No held series: nothing is checked for leaking.
        cls.unheld = run(HELD, init_script=HELD_INIT % (json.dumps("fantasycalc"), "null"))

    def held_run(self, data_edit, key):
        return run(HELD, data_edit=data_edit, init_script=HELD_INIT % (json.dumps(key), json.dumps(HELD_SERIES[key])))

    def assert_never_included(self, out, key, reason_start):
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        base = self.unheld["loadByVersion"]
        members = {"ddf_value": INPUTS, "ddf_value_charts": CHARTS, "ddf_value_projections": PROJECTIONS}
        for version, info in out["loadByVersion"].items():
            self.assertNotIn(key, info["inputs"], version)
            # The other inputs: as without the hold, unless the hold removed
            # the only input with a prior week (then the version has none and
            # averages every eligible input, methodology step 5).
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

    def test_validation_hold_on_the_source_holds_its_derived_series(self):
        out = self.held_run(hold_on("fantasycalc"), "fantasycalc")
        self.assert_never_included(out, "fantasycalc", "held: " + HOLD["reason"])
        entry = {e["key"]: e for e in out["load"]["excluded"]}["fantasycalc"]
        self.assertEqual(entry["reason"], "held: " + HOLD["reason"])
        self.assertEqual((entry["heldBy"], entry["holdField"]), ("fantasycalc", "validationHold"))
        self.assertEqual((entry["holdRoot"], entry["holdWeek"], entry["holdKeptWeek"]), ("fantasycalc", 5, 4))
        self.assertEqual(out["load"]["held"], ["fantasycalc"])

    def test_pipeline_hold_on_raw_and_adjusted_sections(self):
        out = self.held_run(hold_on("cbs", "cbs_adjusted"), "cbs")
        self.assert_never_included(out, "cbs", "held: " + HOLD["reason"])
        entry = {e["key"]: e for e in out["load"]["excluded"]}["cbs"]
        self.assertEqual((entry["heldBy"], entry["holdRoot"]), ("cbs", "cbs"))

    def test_hold_on_the_derived_section_itself(self):
        out = self.held_run(hold_on("fantasycalc_adjusted"), "fantasycalc")
        self.assert_never_included(out, "fantasycalc", "held: " + HOLD["reason"])
        entry = {e["key"]: e for e in out["load"]["excluded"]}["fantasycalc"]
        self.assertEqual(entry["heldBy"], "fantasycalc_adjusted")

    def test_promotion_hold_is_a_hold_too(self):
        out = self.held_run(hold_on("fantasycalc", field="promotionHold"), "fantasycalc")
        self.assert_never_included(out, "fantasycalc", "held: " + HOLD["reason"])

    def test_a_held_projection_is_out_of_every_version(self):
        out = self.held_run(hold_on("razzball"), "razzball")
        self.assert_never_included(out, "razzball", "held: " + HOLD["reason"])
        excluded = {e["key"]: e for e in out["loadByVersion"]["ddf_value_projections"]["excluded"]}
        self.assertEqual(excluded["razzball"]["series"], "razzball")

    def test_a_source_not_yet_published_for_the_week_is_never_an_input(self):
        out = self.held_run(older_week("usatoday"), "usatoday")
        self.assert_never_included(out, "usatoday", "not yet published for week")
        self.assertEqual(out["load"]["notPublished"], ["usatoday"])

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
        self.assertNotIn("dropped", out["withHeld"])


if __name__ == "__main__":
    unittest.main()
