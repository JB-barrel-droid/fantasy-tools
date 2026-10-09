"""JEG-471 / JEG-479 (engine): the DDF Composite Value ("DDF Value") series.

The rule is docs/methodology.md "DDF Composite Value" (Jeremy, 2026-10-08):
one DDF Value per view (Indexed, VORP vs waivers, Adjusted values), each for
the current and the prior week; per player the equal-weight mean of the
included inputs' finite values, published only when at least two price him
(else null, ddfReason "Needs at least two source values"). A missing series
never counts as 0; ESPN's 0 for a player it lists at 0 (GAP-025) does. An
input that is held or has not published the current week is never included,
even when a reader selects it; an input without the prior week is left out of
both weeks. Tier: rank by DDF Value and cut at the league's slot counts.

Checks, headless on the built dist/ (the live page):
1. ValueModel.compositeValue: mean of finite values, missing left out, 0 kept.
2. Every row's values.ddf_value / ddfCount / ddfSources / ddfReason and all
   three ddfByView entries are that mean (two or more values) over the view's
   inputs, across scorings, team counts, a superflex roster, a bench share, a
   position-share edit and the three view tabs.
3. setCompositeInputs: a subset changes ddf_value (and only the DDF fields),
   fires the rows and shared events (shared only with publish), invalid input
   (including fewer than two usable inputs) is refused with no change, null
   restores every value exactly.
4. Rank, zones and tiers by DDF Value.
5. Prior week: getPriorWeek("ddf_value") and the rows' ddfPrior use exactly the
   current week's inputs; an input without the prior week is left out of the
   current week too (simulated with an edited history index).
6. A held source (validationHold / promotionHold on its section, or on the
   derived section) and a source that has not published the current week are
   never inputs, even when requested; excluded lists the reason.
The before/after 12-combo x 3-view sweep (every non-DDF value identical) is in
the PR.
"""
from __future__ import annotations

import json
import unittest

from tests._dist_server import DIST, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


INPUTS = ["espn", "cbsros", "razzball", "fantasycalc_adjusted", "usatoday_adjusted",
          "fantasypros_adjusted", "cbs_adjusted"]
SHORT = "Needs at least two source values"

HELPERS = """
  const c = window.TradeValueCurveControls;
  const INPUTS = %s;
  const SHORT = %s;
  const VIEWS = ['indexed', 'vorp', 'adj'];
  const view = v => document.querySelector(`#viewModeTabs [data-view-mode=${v}]`).click();
  const activeView = () => c.getCompositeInputs().view;
  const mean = (values, keys) => {
    const used = keys.filter(k => typeof values[k] === 'number' && Number.isFinite(values[k]));
    const v = used.map(k => values[k]);
    return {value: v.length >= 2 ? v.reduce((a, b) => a + b, 0) / v.length : null, count: v.length, used};
  };
  const near = (a, b) => (a === null || a === undefined) ? (b === null || b === undefined) : (b !== null && b !== undefined && Math.abs(a - b) <= 1e-9);
  const others = () => JSON.stringify(c.getAllRows().map(r => {
    const v = {...r.values}; delete v.ddf_value; return [r.player_key, r.espnRole, v];
  }));
  const ddf = () => JSON.stringify(c.getAllRows().map(r => [r.player_key, r.values.ddf_value, r.ddfCount, r.ddfTier, r.ddfPrior, r.ddfByView]));
  // Every row against the rule, for the active view and (from row values,
  // which hold every series the other views include) all three views.
  const checkMean = (tag, problems) => {
    let priced = 0, short = 0;
    const active = activeView();
    c.getAllRows().forEach(r => {
      for (const v of VIEWS) {
        const series = c.getCompositeInputs(v).series;
        const want = mean(r.values, series);
        const got = r.ddfByView[v];
        if (!near(got.value, want.value) && problems.length < 40) problems.push(`${tag}/${v} ${r.name}: ddf ${got.value} != mean ${want.value}`);
        if (got.count !== want.count) problems.push(`${tag}/${v} ${r.name}: count ${got.count} != ${want.count}`);
        if (JSON.stringify(got.sources) !== JSON.stringify(want.used)) problems.push(`${tag}/${v} ${r.name}: sources ${got.sources}`);
        if (got.reason !== (want.value === null ? SHORT : null)) problems.push(`${tag}/${v} ${r.name}: reason ${got.reason}`);
      }
      const mine = r.ddfByView[active];
      if (r.values.ddf_value !== mine.value || r.ddfCount !== mine.count || r.ddfReason !== mine.reason
          || r.ddfPrior !== mine.prior || JSON.stringify(r.ddfSources) !== JSON.stringify(mine.sources)) {
        problems.push(`${tag} ${r.name}: row DDF fields differ from ddfByView.${active}`);
      }
      if (r.values.ddf_value !== null) priced += 1;
      if (r.ddfCount === 1) short += 1;
    });
    if (priced < 100) problems.push(`${tag}: only ${priced} players have a DDF Value`);
    return {priced, short};
  };
""" % (json.dumps(INPUTS), json.dumps(SHORT))

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
  const keys = {}, series = {};
  VIEWS.forEach(v => { keys[v] = c.getCompositeInputs(v).inputs; series[v] = c.getCompositeInputs(v).series; });
  let zeroPlayers = 0, shortPlayers = 0;
  const steps = [
    ['load', () => {}],
    ['standard/8', () => { c.setScoring('standard'); c.setTeams(8); }],
    ['half_ppr/14', () => { c.setScoring('half_ppr'); c.setTeams(14); }],
    ['ppr/10', () => { c.setScoring('ppr'); c.setTeams(10); }],
    ['ppr/12 superflex', () => { c.setTeams(12); c.setRosterSpot('SUPERFLEX', 1); }],
    ['bench share 25%', () => { c.setRosterSpot('SUPERFLEX', 0); c.setBenchShareFraction(0.25); }],
    ['QB share +5pp', () => { c.setBenchShareFraction(0.15); c.setPositionWeights({QB: c.getPositionWeights().QB + 0.05}); }],
    ['VORP vs waivers tab', () => { c.setPositionWeights(null); view('vorp'); }],
    ['Adjusted values tab', () => { view('adj'); }],
    ['Indexed tab', () => { view('indexed'); }],
  ];
  for (const [tag, step] of steps) {
    step();
    shortPlayers += checkMean(tag, problems).short;
    const now = c.getCompositeInputs().inputs;
    c.getAllRows().forEach(r => {
      if (r.espnProjectsZero && r.values.espn === 0 && now.includes('espn') && activeView() === 'indexed' && r.values.ddf_value !== null) {
        zeroPlayers += 1;
        if (!r.ddfSources.includes('espn')) problems.push(`${tag} ${r.name}: ESPN 0 left out of the DDF Value`);
      }
    });
  }
  return {problems, keys, series, zeroPlayers, shortPlayers, activeAtEnd: activeView()};
}"""

SETTER = """async () => {""" + HELPERS + """
  const out = {problems: []};
  const events = {rows: 0, shared: []};
  window.addEventListener('trade-value-rows-change', () => { events.rows += 1; });
  window.addEventListener('trade-value-shared-change', e => { events.shared.push(e.detail.compositeInputs); });
  const baseOthers = others(), baseDdf = ddf();
  out.set = c.setCompositeInputs(['fantasycalc_adjusted', 'espn', 'espn']);
  checkMean('subset', out.problems);
  out.subsetMoved = ddf() !== baseDdf;
  out.othersSame = others() === baseOthers;
  out.eventsAfterSet = JSON.parse(JSON.stringify(events));
  out.get = c.getCompositeInputs();
  const before = ddf();
  out.invalid = [c.setCompositeInputs([]), c.setCompositeInputs(['fantasycalc']), c.setCompositeInputs(['espn_vorp']),
    c.setCompositeInputs(['ddf_value']), c.setCompositeInputs('espn'), c.setCompositeInputs({espn: true}),
    c.setCompositeInputs(['espn', 'usatoday']), c.setCompositeInputs(['espn']), c.setCompositeInputs(['razzball', 'razzball'])];
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
    // Tier = the engine's slot fill (ValueModel.roleMap) on the DDF values.
    const values = new Map(all.filter(r => r.values.ddf_value !== null).map(r => [r.player_key, r.values.ddf_value]));
    const byKey = new Map(all.map(r => [r.player_key, r]));
    const roles = window.ValueModel.roleMap({values, playerOf: k => byKey.get(k), teams, shape});
    all.forEach(r => {
      const want = r.values.ddf_value === null ? null : (roles.get(r.player_key) || 'waiver');
      if (r.ddfTier !== want) problems.push(`${tag} ${r.name}: ddfTier ${r.ddfTier} != ${want}`);
    });
    const starters = all.filter(r => r.ddfTier === 'starter').length;
    const bench = all.filter(r => r.ddfTier === 'bench').length;
    if (starters !== teams * sum(shape)) problems.push(`${tag}: ${starters} DDF starters, slots ${teams * sum(shape)}`);
    if (bench !== teams * shape.BENCH) problems.push(`${tag}: ${bench} DDF bench, slots ${teams * shape.BENCH}`);
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
    withComposite: c.getSourceInfo({includeComposite: true}).slice(-1)[0]};
  return {problems, plain, rank: c.getRankSource()};
}"""

PRIOR = """async () => {""" + HELPERS + """
  const out = {problems: [], views: {}};
  for (const v of VIEWS) {
    view(v);
    const info = c.getCompositeInputs();
    const r = await c.getPriorWeek('ddf_value');
    const o = {available: r.available, reason: r.reason, sources: r.sources, inputs: r.inputs, excluded: r.excluded,
      currentWeek: r.currentWeek, priorWeek: r.priorWeek, week: r.week, infoSeries: info.series, compared: 0, short: 0};
    out.views[v] = o;
    if (!r.available) continue;
    const each = {};
    for (const key of r.sources) each[key] = await c.getPriorWeek(key);
    c.getAllRows().forEach(row => {
      const k = row.player_key;
      const cur = mean(row.values, r.sources);
      if (!near(r.currentValues[k] ?? null, cur.value) && out.problems.length < 30) out.problems.push(`${v} ${row.name}: current ${r.currentValues[k]} != ${cur.value}`);
      if (!near(row.values.ddf_value, cur.value)) out.problems.push(`${v} ${row.name}: row ddf_value ${row.values.ddf_value} != ${cur.value} over the pair's inputs`);
      const pv = {};
      r.sources.forEach(s => { pv[s] = each[s].values[k]; });
      const want = mean(pv, r.sources);
      if (!near(r.values[k] ?? null, want.value) && out.problems.length < 30) out.problems.push(`${v} ${row.name}: prior ${r.values[k]} != ${want.value}`);
      if (!near(row.ddfPrior, want.value) && out.problems.length < 30) out.problems.push(`${v} ${row.name}: row ddfPrior ${row.ddfPrior} != ${want.value}`);
      if (want.value !== null && r.counts[k] !== want.count) out.problems.push(`${v} ${row.name}: prior count ${r.counts[k]} != ${want.count}`);
      if (want.count === 1 && (k in r.values)) out.problems.push(`${v} ${row.name}: a one-source prior value was published`);
      if (want.count === 1) o.short += 1;
      if (want.value !== null && cur.value !== null) o.compared += 1;
    });
    if (v === 'indexed') {
      out.wrongWeek = await c.getPriorWeek('ddf_value', r.priorWeek - 1);
      const wk = await c.getWeekValues('ddf_value', r.priorWeek);
      out.weekValuesMatch = wk.available && JSON.stringify(wk.values) === JSON.stringify(r.values);
      out.history = await c.getHistoryWeeks('ddf_value');
      const all = c.getCompositeValues('indexed');
      out.valuesGetterMatch = JSON.stringify(all.prior) === JSON.stringify(r.values) && JSON.stringify(all.current) === JSON.stringify(r.currentValues);
    }
  }
  view('indexed');
  return out;
}"""

HELD = """async () => {""" + HELPERS + """
  const out = {problems: []};
  const leaks = (tag, prefix) => prefix && c.getAllRows().forEach(r => VIEWS.forEach(v => {
    const s = r.ddfByView[v].sources.find(k => k.startsWith(prefix));
    if (s && out.problems.length < 20) out.problems.push(`${tag}/${v} ${r.name}: ${s} in the DDF Value`);
  }));
  const prefix = window.__heldPrefix;
  out.load = c.getCompositeInputs();
  out.loadByView = Object.fromEntries(VIEWS.map(v => [v, c.getCompositeInputs(v)]));
  checkMean('load', out.problems);
  leaks('load', prefix);
  out.withHeld = c.setCompositeInputs([window.__heldKey, 'espn', 'cbsros']);
  checkMean('requested with held', out.problems);
  leaks('requested with held', prefix);
  out.allRequested = c.setCompositeInputs(INPUTS);
  checkMean('all requested', out.problems);
  leaks('all requested', prefix);
  out.onlyHeld = c.setCompositeInputs([window.__heldKey]);
  out.heldPlusOne = c.setCompositeInputs([window.__heldKey, 'espn']);
  out.afterStale = c.getCompositeInputs();
  c.setCompositeInputs(null);
  c.setScoring('standard'); c.setTeams(10);
  checkMean('standard/10', out.problems);
  leaks('standard/10', prefix);
  c.setScoring('ppr'); c.setTeams(12);
  const r = await c.getPriorWeek('ddf_value');
  out.prior = {available: r.available, reason: r.reason, sources: r.sources, inputs: r.inputs, excluded: r.excluded};
  const wk = await c.getWeekValues('ddf_value', r.priorWeek);
  out.weekSources = wk.sources;
  out.sourceInfo = c.getSourceInfo({includeComposite: true}).slice(-1)[0];
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


def run(script: str, history_edit=None, data_edit=None, init_script=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    overrides = {}
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

    def test_rows_carry_the_mean_of_at_least_two_inputs_in_every_view(self):
        out = run(MEAN)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["keys"]["indexed"], INPUTS, "Indexed: every current-week input with a prior week")
        self.assertEqual(out["series"]["indexed"], INPUTS)
        self.assertEqual(out["series"]["vorp"][:3], ["espn_vorp", "cbsros_vorp", "razzball_vorp"])
        self.assertEqual(out["series"]["adj"][:3], ["espn", "cbsros", "razzball"])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertGreater(out["shortPlayers"], 0, "no player has one source, so the two-source rule went untested")
        self.assertEqual(out["activeAtEnd"], "indexed")

    def test_set_composite_inputs(self):
        out = run(SETTER)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertTrue(out["set"]["ok"], out["set"])
        self.assertEqual(out["set"]["inputs"], ["espn", "fantasycalc_adjusted"])
        self.assertFalse(out["set"]["isDefault"])
        self.assertTrue(out["subsetMoved"])
        self.assertTrue(out["othersSame"], "a DDF Value input change moved another series")
        self.assertGreaterEqual(out["eventsAfterSet"]["rows"], 1)
        self.assertEqual(out["eventsAfterSet"]["shared"], [["espn", "fantasycalc_adjusted"]])
        # v2 contract: a deselected input's reason is exactly "not selected"
        # (the only reason v2 lets a reader re-tick).
        self.assertEqual({e["key"]: e["reason"] for e in out["get"]["excluded"]},
                         {k: "not selected" for k in INPUTS if k not in ("espn", "fantasycalc_adjusted")})
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
        self.assertNotIn("ddf_value", out["plain"]["info"])
        self.assertNotIn("ddf_value", out["plain"]["active"])
        entry = out["plain"]["withComposite"]
        self.assertEqual((entry["key"], entry["label"], entry["composite"], entry["available"]),
                         ("ddf_value", "DDF Value", True, True))
        self.assertEqual(out["rank"], "espn")

    def test_prior_week_uses_exactly_the_current_inputs(self):
        out = run(PRIOR)
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        for v, res in out["views"].items():
            self.assertTrue(res["available"], (v, res))
            self.assertEqual(res["priorWeek"], res["currentWeek"] - 1)
            self.assertEqual(res["week"], res["priorWeek"])
            self.assertEqual(res["sources"], res["infoSeries"], f"{v}: the pair's inputs are not the current week's")
            self.assertGreater(res["compared"], 100, v)
        self.assertGreater(sum(res["short"] for res in out["views"].values()), 0,
                           "no player has one prior-week source, so the two-source rule went untested")
        self.assertFalse(out["wrongWeek"]["available"])
        self.assertTrue(out["weekValuesMatch"], "getWeekValues(ddf_value, prior) differs from getPriorWeek")
        self.assertTrue(out["valuesGetterMatch"], "getCompositeValues differs from getPriorWeek")
        self.assertEqual(out["history"]["servedWeek"], out["views"]["indexed"]["currentWeek"])

    def test_inputs_without_the_prior_week_are_left_out_of_both_weeks(self):
        def edit(index):
            served = index["served"]
            served["cbs"] = {**served["cbs"], "week": served["cbs"]["week"] - 1}   # serves another week
            served.pop("razzball")                                               # no saved week matches
        out = run(PRIOR, history_edit=edit)
        self.assertEqual(out["pageErrors"], [])
        res = out["views"]["indexed"]
        self.assertTrue(res["available"], res)
        excluded = {e["key"]: e["reason"] for e in res["excluded"]}
        self.assertEqual(set(excluded), {"cbs_adjusted", "razzball"}, excluded)
        self.assertTrue(excluded["cbs_adjusted"].startswith("no prior week: serves Week"), excluded)
        self.assertTrue(excluded["razzball"].startswith("no prior week: "), excluded)
        self.assertNotIn("cbs_adjusted", res["sources"])
        self.assertNotIn("razzball", res["sources"])
        # Both weeks, rows included, are means over exactly res["sources"] (checked per player).
        self.assertEqual(out["problems"], [], "\n".join(out["problems"]))
        self.assertGreater(res["compared"], 100)


HELD_INIT = "window.__heldKey = %s; window.__heldPrefix = %s;"


class DdfHeldSeriesTest(unittest.TestCase):
    """JEG-479 (Jeremy 2026-10-08): a held source and its derived series, and a
    source that has not published the current week, never enter the DDF
    Value, even when a reader selects them."""

    @classmethod
    def setUpClass(cls):
        if not (DIST / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")
        # No prefix: nothing is held, so nothing is checked for leaking.
        cls.unheld = run(HELD, init_script=HELD_INIT % (json.dumps("fantasycalc_adjusted"), "null"))

    def held_run(self, data_edit, key, prefix):
        return run(HELD, data_edit=data_edit, init_script=HELD_INIT % (json.dumps(key), json.dumps(prefix)))

    def assert_never_included(self, out, key, reason_start):
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        base = self.unheld["loadByView"]
        for view, info in out["loadByView"].items():
            want = [k for k in base[view]["inputs"] if k != key]
            self.assertEqual(info["inputs"], want, view)
            entry = {e["key"]: e for e in info["excluded"]}[key]
            self.assertTrue(entry["reason"].startswith(reason_start), entry)
        self.assertNotIn(key, out["load"]["defaults"])
        # Requested with two usable inputs: dropped and reported, not fatal.
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
        # A stale saved list (v2 replays it) never fails: alone, or with one
        # other input, too few remain, so the defaults apply.
        for stale in (out["onlyHeld"], out["heldPlusOne"]):
            self.assertTrue(stale["ok"], stale)
            self.assertTrue(stale["fellBackToDefaults"], stale)
            self.assertTrue(stale["isDefault"], stale)
            self.assertEqual([d["key"] for d in stale["dropped"]], [key])
            self.assertNotIn(key, stale["inputs"])
        self.assertTrue(out["afterStale"]["isDefault"])
        # Prior week: out of both weeks.
        prior = out["prior"]
        self.assertTrue(prior["available"], prior)
        self.assertNotIn(key, prior["inputs"])
        self.assertNotIn(key, prior["sources"])
        self.assertIn(key, [e["key"] for e in prior["excluded"]])
        self.assertNotIn(key, out["weekSources"])
        self.assertNotIn(key, out["sourceInfo"]["inputs"])
        self.assertFalse(out["sourceInfo"]["stale"])

    def test_validation_hold_on_the_source_holds_its_derived_series(self):
        out = self.held_run(hold_on("fantasycalc"), "fantasycalc_adjusted", "fantasycalc")
        self.assert_never_included(out, "fantasycalc_adjusted", "held: " + HOLD["reason"])
        entry = {e["key"]: e for e in out["load"]["excluded"]}["fantasycalc_adjusted"]
        self.assertEqual(entry["reason"], "held: " + HOLD["reason"])
        self.assertEqual((entry["heldBy"], entry["holdField"]), ("fantasycalc", "validationHold"))
        self.assertEqual((entry["holdRoot"], entry["holdWeek"], entry["holdKeptWeek"]), ("fantasycalc", 5, 4))
        self.assertEqual(out["load"]["held"], ["fantasycalc_adjusted"])

    def test_pipeline_hold_on_raw_and_adjusted_sections(self):
        out = self.held_run(hold_on("cbs", "cbs_adjusted"), "cbs_adjusted", "cbs")
        self.assert_never_included(out, "cbs_adjusted", "held: " + HOLD["reason"])
        entry = {e["key"]: e for e in out["load"]["excluded"]}["cbs_adjusted"]
        self.assertEqual((entry["heldBy"], entry["holdRoot"]), ("cbs_adjusted", "cbs"))

    def test_hold_on_the_derived_section_itself(self):
        out = self.held_run(hold_on("fantasycalc_adjusted"), "fantasycalc_adjusted", "fantasycalc")
        self.assert_never_included(out, "fantasycalc_adjusted", "held: " + HOLD["reason"])
        entry = {e["key"]: e for e in out["load"]["excluded"]}["fantasycalc_adjusted"]
        self.assertEqual(entry["heldBy"], "fantasycalc_adjusted")

    def test_promotion_hold_is_a_hold_too(self):
        out = self.held_run(hold_on("fantasycalc", field="promotionHold"), "fantasycalc_adjusted", "fantasycalc")
        self.assert_never_included(out, "fantasycalc_adjusted", "held: " + HOLD["reason"])

    def test_a_held_projection_holds_its_value_above_waivers_series(self):
        out = self.held_run(hold_on("razzball"), "razzball", "razzball")
        self.assert_never_included(out, "razzball", "held: " + HOLD["reason"])
        excluded = {e["key"]: e for e in out["loadByView"]["vorp"]["excluded"]}
        self.assertEqual(excluded["razzball"]["series"], "razzball_vorp")

    def test_a_source_not_yet_published_for_the_week_is_never_an_input(self):
        out = self.held_run(older_week("usatoday"), "usatoday_adjusted", "usatoday")
        self.assert_never_included(out, "usatoday_adjusted", "not yet published for week")
        self.assertEqual(out["load"]["notPublished"], ["usatoday_adjusted"])

    def test_unheld_fixture_has_no_held_series(self):
        out = self.unheld
        self.assertEqual(out["pageErrors"], [])
        self.assertEqual(out["problems"], [], "\n".join(out["problems"][:40]))
        self.assertEqual(out["load"]["held"], [])
        self.assertEqual(out["load"]["notPublished"], [])
        self.assertIn("fantasycalc_adjusted", out["load"]["inputs"])
        self.assertIn("fantasycalc_adjusted", out["prior"]["sources"])
        self.assertEqual(out["withHeld"]["inputs"], ["espn", "cbsros", "fantasycalc_adjusted"])
        self.assertNotIn("dropped", out["withHeld"])


if __name__ == "__main__":
    unittest.main()
