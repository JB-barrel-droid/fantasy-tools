// Values explainer extractor. Runs inside the built chart page
// (dist/modules/math-inspector.html) and returns one JSON bundle of what the
// chart engine shows, read only through its public read-only accessors
// (TradeValueCurveControls, TradeValueCurveDiagnostics, TradeValueTwoTier,
// TradeValueProductData). It never changes a plotted value; it moves the
// league-setting controls and puts them back at the default setting.
// Called by pipelines/build_values_explainer.py.
async (opts) => {
  const C = window.TradeValueCurveControls;
  const TT = window.TradeValueTwoTier;
  const settle = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const clone = x => JSON.parse(JSON.stringify(x ?? null));
  const POS = ["QB", "RB", "WR", "TE"];
  const setView = async view => {
    const tab = document.querySelector(`#viewModeTabs [data-view-mode="${view}"]`);
    if (!tab) throw new Error("view tab missing: " + view);
    tab.click();
    await settle();
  };
  const valuesBySeries = rows => {
    const out = {};
    rows.forEach(row => Object.entries(row.values || {}).forEach(([k, v]) => {
      if (typeof v !== "number" || !isFinite(v)) return;
      (out[k] = out[k] || {})[row.player_key] = v;
    }));
    return out;
  };

  await setView("indexed");
  const base = {
    state: clone(C.getState()),
    info: clone(C.getSourceInfo({includeComposite: true})),
    composite: clone(C.getCompositeInputs()),
    adjustmentWeights: clone(C.getAdjustmentWeights()),
    roster: clone(C.getRosterShape()),
    benchBounds: clone(C.getBenchBounds()),
    positionWeights: clone(C.getPositionWeights()),
    zones: clone(C.getZones()),
    inspection: clone(C.getInspection()),
  };
  const diag = window.TradeValueCurveDiagnostics || {};
  base.diagnostics = clone({
    fixedPie: diag.fixedPie, viewInvariants: diag.viewInvariants,
    adjustedAgreement: diag.adjustedAgreement, sourcePeaks: diag.sourcePeaks,
    publishedDerivation: diag.publishedDerivation, liveAdjustedSources: diag.liveAdjustedSources,
    adjustmentInputsVersion: diag.adjustmentInputsVersion, savedSetup: diag.savedSetup,
  });

  // Rows (with every series value) in each of the three views.
  const rowsByView = {};
  for (const view of ["indexed", "vorp", "adj"]) {
    await setView(view);
    rowsByView[view] = C.getAllRows();
    base["composite_" + view] = clone(C.getCompositeInputs());
    if (view !== "indexed") base["viewInvariants_" + view] = clone(window.TradeValueCurveDiagnostics?.viewInvariants);
  }
  await setView("indexed");
  const players = {};
  rowsByView.indexed.forEach(row => {
    players[row.player_key] = {n: row.name, t: row.team, p: row.pos, r: row.espnRole,
      z: row.espnProjectsZero || false,
      ppg: {espn: row.espn_ppg || null, cbsros: row.cbsros_ppg || null, razzball: row.rz_ppg || null},
      ddf: row.values.ddf_value ?? null, ddfN: row.ddfCount ?? null, ddfTier: row.ddfTier ?? null};
  });
  base.players = players;
  base.views = {};
  Object.entries(rowsByView).forEach(([view, rows]) => { base.views[view] = valuesBySeries(rows); });

  // Two-tier calibration for the projection sources, rebuilt with the
  // engine's own TwoTier helpers from the per-game projections, the same way
  // the engine's twoTierConfig / ddfTwoTierValuesForSource do. Reported with
  // how closely it reproduces the values the chart shows.
  const scoringField = base.inspection.setting.scoringField;
  const teams = base.inspection.setting.teams;
  const share = base.inspection.setting.benchShare;
  const all = window.TradeValueProductData.getPlayers();
  const ppgField = {espn: "espn_ppg", cbsros: "cbsros_ppg", razzball: "rz_ppg"};
  base.twoTier = {};
  for (const src of ["espn", "cbsros", "razzball"]) {
    const lists = {QB: [], RB: [], WR: [], TE: []};
    all.forEach(p => {
      if (!POS.includes(p.pos)) return;
      const x = Number(p[ppgField[src]]?.[scoringField]);
      if (Number.isFinite(x)) lists[p.pos].push({id: Number(p.player_key), x});
    });
    try {
      const pool = TT.buildPositionTiers(lists, {teams, slots: {...TT.REF_SLOTS}, flexCount: TT.REF_FLEX_COUNT,
        flexEligible: [...TT.REF_FLEX_ELIGIBLE], benchMix: TT.legacyBenchMixFor(teams)});
      const shares = TT.skillBenchShares(share);
      const cal = {};
      POS.forEach(pos => {
        cal[pos] = TT.calibratePositionFeasible(pool.tiers[pos], Number(pool.tiers[pos]?.surplus),
          TT.skillBenchShare(shares, pos), pos);
      });
      const raw = {};
      let mx = 0;
      POS.forEach(pos => lists[pos].forEach(d => {
        const v = TT.priceForProjection(d.x, cal[pos]);
        raw[d.id] = v; if (v > mx) mx = v;
      }));
      const scale = mx > 0 ? 70 / mx : 1;
      const counts = {};
      POS.forEach(pos => {
        const ids = new Set(lists[pos].map(d => d.id));
        counts[pos] = {listed: ids.size,
          starters: [...pool.starters].filter(k => ids.has(k)).length,
          bench: [...pool.bench].filter(k => ids.has(k)).length};
      });
      base.twoTier[src] = {
        benchMix: TT.legacyBenchMixFor(teams), scale, counts,
        positions: Object.fromEntries(POS.map(pos => {
          const c = cal[pos] || {};
          return [pos, {rw: c.rw, rs: c.rs, tau: c.tau, surplus: c.surplus, pb: c.pb, ps: c.ps,
            benchRaw: c.benchRaw, starterRaw: c.starterRaw, shareUsed: c.bench_share_used ?? null,
            invalid: !!c.invalid, reason: c.invalidReason || null}];
        })),
        values: Object.fromEntries(Object.entries(raw).filter(([, v]) => v > 0).map(([k, v]) => [k, v * scale])),
        starters: [...pool.starters], bench: [...pool.bench],
      };
    } catch (e) {
      base.twoTier[src] = {error: String(e && e.message || e)};
    }
  }

  // Raw VORP vs waivers series (espn_vorp, cbsros_vorp, razzball_vorp):
  // rebuilt like the engine's buildVorpRows -- roles from
  // ValueModel.projectionRoles on the source's own per-game projections, the
  // waiver line is the best projection left unrostered at each position --
  // and the one factor that matches the shown total is reported.
  base.rawVorp = {};
  const shape = C.getRosterShape();
  for (const [src, vk] of [["espn", "espn_vorp"], ["cbsros", "cbsros_vorp"], ["razzball", "razzball_vorp"]]) {
    const pool = [];
    all.forEach(p => {
      if (!POS.includes(p.pos)) return;
      const x = Number(p[ppgField[src]]?.[scoringField]);
      if (Number.isFinite(x)) pool.push({player_key: Number(p.player_key), pos: p.pos, name: p.full_name || p.name, ppg: x});
    });
    const ppgOf = new Map(pool.map(p => [p.player_key, p.ppg]));
    const out = window.ValueModel.projectionRoles({pool, teams, shape, rankOf: p => ppgOf.get(p.player_key)});
    const waiverLine = {}, counts = {};
    POS.forEach(pos => {
      const rows = pool.filter(p => p.pos === pos).sort((a, b) => b.ppg - a.ppg);
      const w = rows.find(p => !out.roles.has(p.player_key));
      waiverLine[pos] = w ? w.ppg : (rows.length ? rows[rows.length - 1].ppg : 0);
      counts[pos] = {starter: rows.filter(p => out.roles.get(p.player_key) === "starter").length,
                     bench: rows.filter(p => out.roles.get(p.player_key) === "bench").length};
    });
    let rawSum = 0, shownSum = 0;
    const shown = base.views.indexed[vk] || {};
    const raw = {};
    pool.forEach(p => {
      const role = out.roles.get(p.player_key);
      const v = role ? Math.max(0, p.ppg - waiverLine[p.pos]) : 0;
      raw[p.player_key] = v;
      if (v > 0 && Number.isFinite(shown[p.player_key])) { rawSum += v; shownSum += shown[p.player_key]; }
    });
    base.rawVorp[vk] = {waiverLine, counts, dedicatedBaseline: out.baseline,
      factor: rawSum > 0 ? shownSum / rawSum : null, raw};
  }

  // League-settings sensitivity: what each series shows (Indexed view) at
  // other team counts and scorings. Put back to the default after.
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
    base.sensitivity.push({scoring, teams: t, series: summarize(),
      waiver: clone(C.getSourceInfo().filter(s => s.waiver).map(s => ({key: s.key, waiver: s.waiver})))});
  }
  C.setScoring(startScoring); C.setTeams(startTeams);
  await settle();
  base.restored = clone(C.getState());
  return base;
}
