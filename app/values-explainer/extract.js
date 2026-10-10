// Values explainer extractor. Runs inside the built chart page
// (dist/modules/math-inspector.html) and returns one JSON bundle of what the
// chart engine shows, read only through its public read-only accessors
// (TradeValueCurveControls.getInspection and friends,
// TradeValueCurveDiagnostics). It never changes a plotted value; it moves the
// league-setting controls and puts them back at the default setting.
// Called by pipelines/build_values_explainer.py.
//
// Engine: value-pipeline/2 (JEG-508, docs/methodology.md "Value Pipeline").
// Every source goes native -> value above waivers -> Adjusted values on one
// fixed league pie; DDF Value is the mean of Adjusted values; Indexed is one
// factor per chart against DDF Value, for display only.
async (opts) => {
  const C = window.TradeValueCurveControls;
  const settle = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const clone = x => JSON.parse(JSON.stringify(x ?? null));
  const POS = ["QB", "RB", "WR", "TE"];
  const setView = async view => {
    const tab = document.querySelector(`#viewModeTabs [data-view-mode="${view}"]`);
    if (!tab) throw new Error("view tab missing: " + view);
    tab.click();
    await settle();
  };

  await setView("indexed");
  const diag = window.TradeValueCurveDiagnostics || {};
  const base = {
    state: clone(C.getState()),
    info: clone(C.getSourceInfo({includeComposite: true})),
    composite: clone(C.getCompositeInputs()),
    positionWeights: clone(C.getPositionWeights()),
    zones: clone(C.getZones()),
    inspection: clone(C.getInspection()),
    diagnostics: clone({
      fixedPie: diag.fixedPie, viewInvariants: diag.viewInvariants, indexedOrder: diag.indexedOrder,
      sourcePeaks: diag.sourcePeaks, publishedDerivation: diag.publishedDerivation,
      included: diag.included, excluded: diag.excluded, priorAvailable: diag.priorAvailable,
      priorReason: diag.priorReason, savedSetup: diag.savedSetup,
    }),
  };

  // The row values the chart draws, per view, so the page can show (and the
  // builder can check) that the per-source arithmetic lands on them.
  base.rowValues = {};
  base.rowMeta = {};
  for (const view of ["indexed", "vorp", "adj"]) {
    await setView(view);
    const out = {};
    C.getAllRows().forEach(row => {
      Object.entries(row.values || {}).forEach(([k, v]) => {
        if (typeof v !== "number" || !isFinite(v)) return;
        (out[k] = out[k] || {})[row.player_key] = v;
      });
      if (view === "indexed") {
        const b = row.ddfByVersion || {};
        base.rowMeta[row.player_key] = {team: row.team ?? null,
          prior: {blended: b.blended?.prior ?? row.ddfPrior ?? null, charts: b.charts?.prior ?? null,
                  projections: b.projections?.prior ?? null}};
      }
    });
    base.rowValues[view] = out;
  }
  await setView("indexed");

  // League-settings sensitivity: the pipeline at other team counts and
  // scorings. Put back to the default after.
  const startScoring = base.state.scoring, startTeams = base.state.teams;
  const summarize = () => {
    const out = {};
    C.getAllRows().forEach(row => Object.entries(row.values || {}).forEach(([k, v]) => {
      if (typeof v !== "number" || !isFinite(v) || !POS.includes(row.pos)) return;
      const s = (out[k] = out[k] || {});
      const c = (s[row.pos] = s[row.pos] || {top: 0, sum: 0, n: 0});
      c.top = Math.max(c.top, v); c.sum += v; c.n += 1;
    }));
    return out;
  };
  base.sensitivity = [];
  for (const [scoring, t] of (opts && opts.settings) || []) {
    C.setScoring(scoring); C.setTeams(t);
    await settle();
    const vp = C.getInspection().valuePipeline || {};
    base.sensitivity.push({scoring, teams: t, series: summarize(),
      pie: vp.pie, ddfWeights: clone(vp.ddfWeights), allocation: clone(vp.allocation),
      factors: Object.fromEntries(Object.entries(vp.sources || {}).map(([k, s]) => [k, {indexed: s.indexedFactor, vorp: s.vorpFactor}])),
      waiver: Object.fromEntries(Object.entries(vp.sources || {}).map(([k, s]) => [k, Object.fromEntries(POS.map(p => [p, s.positions?.[p]?.waiver ?? null]))]))});
  }
  C.setScoring(startScoring); C.setTeams(startTeams);
  await settle();
  base.restored = clone(C.getState());
  return base;
}
