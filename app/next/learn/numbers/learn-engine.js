/* Learn > How we get our numbers: read-only view of the live engine (JEG-1536).
   No value math here. Every number is read from the engine that runs hidden on this page
   (window.DDF.engine, ddf-engine.js, over TradeValueCurveControls): getInspection() for each
   source's published / indexed / adjusted values, getAllRows() for DDF Value, getPublishedMath()
   for each chart's index factor. The Health check and Source build-up models come from the same
   modules the old #values-auditing tabs used (AuditPie in v2/audit-pie.js, DDFAuditSource in
   v2/audit-source.js), so their checks and rows are computed in one place only.
   A value the engine does not have stays null and is shown as a dash: missing is never zero. */
(function () {
  'use strict';

  var CHARTS = ['cbs', 'usatoday', 'fantasypros', 'fantasycalc'];
  var LABELS = {
    cbs: 'CBS Sports', usatoday: 'USA Today', fantasypros: 'FantasyPros', fantasycalc: 'FantasyCalc',
    espn: 'ESPN', cbsros: 'CBS rest of season', razzball: 'Razzball'
  };
  var SCORING_LABEL = { standard: 'Standard', half_ppr: 'Half PPR', ppr: 'Full PPR' };
  var SLOT_KEYS = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX', 'BENCH'];
  var finite = function (v) { return typeof v === 'number' && isFinite(v) ? v : null; };

  function engine() { return window.DDF && window.DDF.engine ? window.DDF.engine : null; }

  /* ---- settings ---- */
  function rosterLabel(r) {
    return ['QB', 'RB', 'WR', 'TE', 'FLEX'].map(function (k) { return k + (r[k] || 0); }).join(' ') +
      (r.SUPERFLEX ? ' SUPERFLEX' + r.SUPERFLEX : '') + ' BENCH' + (r.BENCH || 0);
  }
  function currentSettings(C) {
    var st = C.getState();
    var roster = C.getRosterShape();
    var r = {};
    SLOT_KEYS.forEach(function (k) { r[k] = Number(roster[k] || 0); });
    return {
      scoring: st.scoring, scoringLabel: SCORING_LABEL[st.scoring] || st.scoring, teams: Number(st.teams),
      superflex: r.SUPERFLEX > 0, roster: r, rosterLabel: rosterLabel(r)
    };
  }

  /* ---- snapshot of the engine's current build ---- */
  function snapshot() {
    var E = engine();
    var C = E.controls();
    var ins = C.getInspection();
    var vp = ins.valuePipeline || {};
    var settings = currentSettings(C);
    var meta = (E.meta && E.meta()) || {};
    var basis = C.getBasis ? C.getBasis() : null;
    var comp = C.getCompositeInputs ? C.getCompositeInputs() : null;
    var rows = C.getAllRows();

    /* Charts in the DDF Value this week (a held chart is left out, never counted as zero). */
    var inputs = (comp && comp.inputs) || CHARTS;
    var charts = CHARTS.filter(function (k) { return inputs.indexOf(k) >= 0; });

    var factor = {}, factorTotals = {};
    var players = [];
    rows.forEach(function (row) {
      var pk = String(row.player_key);
      var blended = row.ddfByVersion && row.ddfByVersion.blended;
      /* The model's own DDF Value: with a reader override, applyDdfOverride keeps it in pipelineValue. */
      var overridden = row.valueOverride !== undefined && row.valueOverride !== null;
      if (overridden && !(blended && finite(blended.pipelineValue) !== null)) return;   // no model value to explain
      var ddf = finite(blended && (overridden ? blended.pipelineValue : blended.value));
      if (ddf === null) return;
      var irow = (ins.rows && ins.rows[pk]) || {};
      var sources = {};
      CHARTS.forEach(function (s) {
        var p = ins.players && ins.players[s] && ins.players[s][pk];
        /* Indexed and adjusted come from the engine's row: a chart that does not list a player can still carry a
           real 0 there, and DDF Value averages it. Only the published value is missing (null) then. */
        var idx = finite(irow.indexed && irow.indexed[s]), adj = finite(irow.adjusted && irow.adjusted[s]);
        if (!p && idx === null && adj === null) { sources[s] = null; return; }
        if (factor[s] === undefined) {
          var pm = C.getPublishedMath(row.player_key, s);
          factor[s] = pm ? finite(pm.factor) : null;
          /* The factor's own two totals, over the same players (the ones the chart lists; estimates excluded). */
          factorTotals[s] = pm ? { ddf: finite(pm.anchorTotal), published: finite(pm.chartTotal), players: finite(pm.sharedPlayers) } : null;
        }
        sources[s] = {
          published: p ? finite(p.native) : null, indexed: idx, adjusted: adj, role: p ? p.role || null : null,
          estimated: p ? Boolean(p.estimated) : false, listed: Boolean(p), rank: p ? finite(p.rank) : null
        };
      });
      players.push({
        player_key: row.player_key, name: row.name, pos: row.pos, team: row.team || '',
        ddf: ddf, tier: row.ddfTier || null,
        ddfSources: (blended.sources || []).slice(),
        override: overridden ? finite(row.values && row.values.ddf_value) : null,
        overrideSet: overridden,
        sources: sources
      });
    });
    players.sort(function (a, b) { return b.ddf - a.ddf || a.player_key - b.player_key; });
    players.forEach(function (p, i) { p.rank = i + 1; });

    var startSlots = ['QB', 'RB', 'WR', 'TE', 'FLEX', 'SUPERFLEX'].reduce(function (t, k) { return t + (settings.roster[k] || 0); }, 0);
    var pie = finite(vp.pie);
    var perSlot = pie !== null && settings.teams && startSlots ? pie / (settings.teams * startSlots) : null;

    var srcMeta = {};
    CHARTS.forEach(function (s) {
      var ps = (ins.players && ins.players[s]) || {};
      var keys = Object.keys(ps);
      var totals = { published: 0, indexed: 0, adjusted: 0 };
      var filled = 0;
      keys.forEach(function (k) {
        var p = ps[k], r = (ins.rows && ins.rows[k]) || {};
        if (p.estimated) filled += 1; else totals.published += finite(p.native) || 0;
        totals.indexed += finite(r.indexed && r.indexed[s]) || 0;
        totals.adjusted += finite(r.adjusted && r.adjusted[s]) || 0;
      });
      var excluded = (ins.excluded || []).filter(function (e) { return e.key === s; })[0] || null;
      srcMeta[s] = {
        key: s, label: LABELS[s], players: keys.length, listed: keys.length - filled, filledIn: filled,
        totals: totals, factor: factor[s] === undefined ? null : factor[s], factorTotals: factorTotals[s] || null,
        inDdf: charts.indexOf(s) >= 0, excludedReason: excluded ? excluded.reason : null
      };
    });

    return {
      settings: settings,
      meta: { week: meta.week === undefined ? null : meta.week, asOf: meta.asOf || null, build: meta.buildTag || null },
      pie: pie, perSlot: perSlot !== null && Math.abs(perSlot - Math.round(perSlot)) < 1e-6 ? Math.round(perSlot) : perSlot,
      startSlots: startSlots,
      charts: charts,
      basis: basis ? { isDefault: basis.isDefault !== false, label: basis.label || '', percents: basis.percents || {} } : { isDefault: true, label: '', percents: {} },
      sources: srcMeta,
      players: players,
      overrides: players.filter(function (p) { return p.overrideSet; }).length,
      inspection: ins
    };
  }

  /* Health check (the old #values-auditing/health-check): AuditPie's own extract + checks. */
  function health(snap) {
    var A = window.AuditPie;
    if (!A) return null;
    var data = A.extract(snap.inspection);
    if (!data) return null;
    A.computeFlags(data);
    data.checks = A.computeChecks(data);
    return data;
  }

  /* Source build-up (the old #values-auditing/single-source): DDFAuditSource's own model. */
  function buildUp(snap, source, position) {
    var S = window.DDFAuditSource;
    return S ? S.build(snap.inspection, source, position) : null;
  }
  /* One player's path from a source's own number to its Adjusted value (JEG-1393, R1-CX-07 / R1-OP-07): the engine's
     own intermediates (getInspection players[source][key] and valuePipeline.sources[source]), for a trade chart as well
     as a projection. Nothing is derived here; a readout the engine does not expose stays null. */
  function worked(snap, source, key) {
    var ins = snap && snap.inspection;
    var p = ins && ins.players && ins.players[source] && ins.players[source][String(key)];
    if (!p) return null;
    var vsrc = (ins.valuePipeline && ins.valuePipeline.sources && ins.valuePipeline.sources[source]) || {};
    var posInfo = (vsrc.positions && vsrc.positions[p.pos]) || {};
    var rates = vsrc.rates || {};
    return {
      source: source, key: String(key), pos: p.pos, estimated: Boolean(p.estimated), role: p.role || null,
      published: finite(p.native), waiver: finite(posInfo.waiver), starterLine: finite(posInfo.starterLine),
      availability: finite(posInfo.avail), aboveWaivers: finite(p.vorp), startWorthy: finite(p.startWorthy),
      lineupShare: finite(p.lineupShare), starterPart: finite(p.starterSlice), fillInPart: finite(p.benchSlice),
      starterRate: finite(rates[p.pos + '|starter']), fillInRate: finite(rates[p.pos + '|bench']),
      adjusted: finite(p.adjusted)
    };
  }
  function buildUpSources() {
    var S = window.DDFAuditSource;
    return S ? S.SOURCES.map(function (s) { return { key: s.key, label: LABELS[s.key] || s.label, family: s.family }; }) : [];
  }

  /* A source's own page, from the bundle (sources.<key>.url, else .source_url); same position swap as audit-source.js. */
  function sourceUrl(key, position) {
    var snap = window.TradeValueProductData && window.TradeValueProductData.getSnapshot ? window.TradeValueProductData.getSnapshot() : null;
    var src = snap && snap.sources && snap.sources[key];
    var url = src && (src.url || src.source_url);
    if (typeof url !== 'string' || !/^https?:\/\//.test(url)) return '';
    var pos = ['QB', 'RB', 'WR', 'TE'].indexOf(position) >= 0 ? position : 'QB';
    if (key === 'cbsros') return url.replace('/QB/', '/' + pos + '/');
    if (key === 'razzball') return url.replace('-qb-', '-' + pos.toLowerCase() + '-');
    return url;
  }

  /* Settings checked on this page apply to this page only: the engine's own setters with publish off, never
     DDF.engine.apply (which saves them as the reader's league). With no settings the engine keeps the reader's
     saved league, which ddf-engine.js applied before `ready` resolved. */
  function applyHere(C, s) {
    if (s.scoring) C.setScoring(s.scoring, false);
    if (s.teams) C.setTeams(Number(s.teams), false);
    if (s.roster) Object.keys(s.roster).forEach(function (k) { C.setRosterSpot(k, s.roster[k], false); });
  }
  /* Learn explains the default DDF Value (the four-chart mean), so a reader's own value basis is set aside on this
     page only (publish off; ddf-engine.js keeps it saved) and named in the page's notes. */
  function readerBasisLabel(E) {
    var rec = E.basis ? E.basis() : null;
    if (!rec || !rec.mode || rec.mode === 'default') return null;
    if (rec.mode === 'single') return (LABELS[rec.source] || rec.source) + ' only';
    return 'a blend of ' + (rec.sources || []).map(function (s) { return LABELS[s] || s; }).join(', ');
  }
  function pinDefaultBasis(C) {
    var b = C.getBasis ? C.getBasis() : null;
    if (b && b.isDefault === false) C.setBasis(null, false);
  }
  function load(settings) {
    var E = engine();
    if (!E) return Promise.reject(new Error('engine missing'));
    return E.ready.then(function (C) {
      C = E.controls() || C;
      pinDefaultBasis(C);
      if (settings) applyHere(C, settings);
      var snap = snapshot();
      snap.readerBasis = readerBasisLabel(E);
      return snap;
    });
  }

  window.DDFLearnEngine = {
    CHARTS: CHARTS, LABELS: LABELS, SCORING_LABEL: SCORING_LABEL,
    load: load, snapshot: snapshot, health: health, buildUp: buildUp, worked: worked, buildUpSources: buildUpSources, sourceUrl: sourceUrl,
    rosterLabel: rosterLabel, onRebuild: function (fn) { var E = engine(); if (E && E.on) E.on(fn); }
  };
})();
