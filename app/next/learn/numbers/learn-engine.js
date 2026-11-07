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

    var factor = {};
    var players = [];
    rows.forEach(function (row) {
      var pk = String(row.player_key);
      var blended = row.ddfByVersion && row.ddfByVersion.blended;
      var ddf = finite(blended && blended.value);
      if (ddf === null) return;
      var irow = (ins.rows && ins.rows[pk]) || {};
      var sources = {};
      CHARTS.forEach(function (s) {
        var p = ins.players && ins.players[s] && ins.players[s][pk];
        if (!p) { sources[s] = null; return; }
        if (factor[s] === undefined) {
          var pm = C.getPublishedMath(row.player_key, s);
          factor[s] = pm ? finite(pm.factor) : null;
        }
        sources[s] = {
          published: finite(p.native), indexed: finite(irow.indexed && irow.indexed[s]),
          adjusted: finite(irow.adjusted && irow.adjusted[s]), role: p.role || null,
          estimated: Boolean(p.estimated), rank: finite(p.rank)
        };
      });
      players.push({
        player_key: row.player_key, name: row.name, pos: row.pos, team: row.team || '',
        ddf: ddf, tier: row.ddfTier || null,
        ddfSources: (blended.sources || []).slice(),
        override: row.valueOverride !== undefined && row.valueOverride !== null ? finite(row.values && row.values.ddf_value) : null,
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
        totals: totals, factor: factor[s] === undefined ? null : factor[s],
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

  /* Apply settings, then resolve with a fresh snapshot. */
  function load(settings) {
    var E = engine();
    if (!E) return Promise.reject(new Error('engine missing'));
    return E.ready.then(function () { return settings ? E.apply(settings) : null; }).then(function () { return snapshot(); });
  }

  window.DDFLearnEngine = {
    CHARTS: CHARTS, LABELS: LABELS, SCORING_LABEL: SCORING_LABEL,
    load: load, snapshot: snapshot, health: health, buildUp: buildUp, buildUpSources: buildUpSources, sourceUrl: sourceUrl,
    rosterLabel: rosterLabel, onRebuild: function (fn) { var E = engine(); if (E && E.on) E.on(fn); }
  };
})();
