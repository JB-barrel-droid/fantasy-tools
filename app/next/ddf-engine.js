/* DDF engine adapter for the redesigned pages (JEG-1535).
 *
 * No value math here. The page carries the same engine the live site runs (value-model.js, product-data.js,
 * curve-widget.js, injected by pipelines/build_root_pages.py, hidden), and this file only reads its rows and passes
 * the reader's settings, value basis and overrides to it. Every number a page shows is an engine row value, so a player
 * has one DDF Value on every page for the same settings. A value the engine does not have stays null (never 0).
 *
 * Storage bridge (plan D4, until the old pages retire): the reader's league settings and overrides live where the
 * live pages keep them, so both halves of the site show the same numbers:
 *   localStorage ddf.v2.league-settings   {v:1, scoring, teams, roster, weeks?, adv?, shares?}  (v2.js leagueSnapshot)
 *   localStorage ddf-v2-value-overrides   {v:2, basis, values:{player_key: n | {type:'adjustment', delta}}, names}
 *   sessionStorage ddf-v2-link-state      a shared link's basis and overrides for this tab (overrides.js)
 * Overrides are mirrored by name into the redesign's own session store (DDF.overrides, 'ddf:overrides') for its
 * other pages and the header pill. A link's value context (#...?valuecontext=1&basis=..&ov=.., the live format,
 * v2/ddf-value-link.js) applies for the visit and is saved only when the reader changes something.
 *
 * API: window.DDF.engine
 *   ready                 Promise<controls>, after the first build and the saved settings/overrides are applied
 *   controls()            window.TradeValueCurveControls (read-only use; settings go through apply)
 *   players()             page records for every priced player (see record below), cached per rebuild
 *   player(key)           one record
 *   settings()            {scoring, teams, roster:{QB,RB,WR,TE,FLEX,SUPERFLEX,BENCH,K,DST}}
 *   apply(partial)        set scoring / teams / superflex (bool) / roster; saves; returns settings()
 *   applyVisit(partial)   the same (plus weeks, week, adv, shares) for this visit only, never saved (a shared trade link's league)
 *   meta()                {buildTag, asOf, week}
 *   on(fn)                fn() after every rebuild (settings, basis or override change); returns an unsubscribe
 *   overrides.*           all(), get(key), set(key, value|{type:'adjustment', delta}), remove(key), clear(), count(),
 *                         replaceAll(map), session()
 *   basis() / setBasis(rec) the live basis record {mode:'default'} | {mode:'single', source} | {mode:'blend', sources, weights}
 *   priorWeek()           Promise of the engine's prior-week DDF Value (getPriorWeek('ddf_value'))
 *   league()              read-only roster bridge from ddf.v2.workspaces: {name, teams:[{id,name,keys:Set}], mine:id|null} or null
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var CHARTS = ["cbs", "usatoday", "fantasypros", "fantasycalc"];
  var SOURCES = ["cbs", "usatoday", "fantasypros", "fantasycalc", "espn", "cbsros", "razzball"];
  var POSITIONS = ["QB", "RB", "WR", "TE"];
  var LEAGUE_KEY = "ddf.v2.league-settings";
  var OV_KEY = "ddf-v2-value-overrides";
  var LINK_KEY = "ddf-v2-link-state";
  var WS_KEY = "ddf.v2.workspaces";
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var C = null, cache = null, listeners = [], state = {values: {}, names: {}, basis: {mode: "default"}, session: false};

  function readJSON(store, key) { try { return JSON.parse(store.getItem(key) || "null"); } catch (e) { return null; } }
  function writeJSON(store, key, value) { try { store.setItem(key, JSON.stringify(value)); return true; } catch (e) { return false; } }

  function normalizeEntry(entry) {
    var VL = window.DDFValueLink;
    if (VL && VL.normalizeEntry) return VL.normalizeEntry(entry);
    if (entry && typeof entry === "object" && entry.type === "adjustment") return finite(+entry.delta) ? {type: "adjustment", delta: +entry.delta} : null;
    var n = Number(entry);
    return finite(n) ? Math.min(100, Math.max(0, Math.round(n * 10) / 10)) : null;
  }

  /* ---- page records ---- */
  function record(row, vorp) {
    var v = row.values || {}, est = row.estimated || {};
    var listed = function (k) { return finite(v[k]) && !est[k] ? v[k] : null; };
    var vaw = null, vawN = 0;
    if (vorp) {
      var sum = 0;
      CHARTS.forEach(function (k) { if (finite(vorp[k])) { sum += vorp[k]; vawN += 1; } });
      vaw = vawN ? sum / vawN : null;
    }
    var spec = row.valueOverrideSpec || null;
    return {
      key: String(row.player_key), n: row.name, pos: row.pos, team: row.team || "",
      ddf: finite(v.ddf_value) ? v.ddf_value : null,
      base: finite(row.ddfPipelineValue) ? row.ddfPipelineValue : (finite(v.ddf_value) ? v.ddf_value : null),
      ov: row.valueOverride !== null && row.valueOverride !== undefined, ovSpec: spec,
      cbs: listed("cbs"), usat: listed("usatoday"), fp: listed("fantasypros"), fc: listed("fantasycalc"),
      espn: listed("espn"), cbsros: listed("cbsros"), razzball: listed("razzball"),
      est: est, vaw: vaw, vawN: vawN, tier: row.ddfTier || null, count: row.ddfCount || 0,
      lowConfidence: Boolean(row.ddfLowConfidence), row: row
    };
  }
  function build() {
    if (cache) return cache;
    var rows = C.getAllRows();
    var inspect = null;
    try { inspect = C.getInspection ? C.getInspection() : null; } catch (e) { inspect = null; }
    var list = rows.filter(function (r) { return POSITIONS.indexOf(r.pos) >= 0; }).map(function (r) {
      var ins = inspect && inspect.rows ? inspect.rows[String(r.player_key)] : null;
      return record(r, ins ? ins.vorp : null);
    }).filter(function (p) {
      return p.ddf !== null || SOURCES.some(function (k) { return p[k === "usatoday" ? "usat" : k === "fantasypros" ? "fp" : k === "fantasycalc" ? "fc" : k] !== null; });
    });
    var byKey = new Map(list.map(function (p) { return [p.key, p]; }));
    cache = {list: list, byKey: byKey};
    return cache;
  }
  function changed() {
    cache = null;
    listeners.slice().forEach(function (fn) { try { fn(); } catch (e) { console.error(e); } });
  }

  /* ---- league settings (shared with the live pages) ---- */
  function settings() {
    var st = C.getState();
    return {scoring: st.scoring, teams: st.teams, roster: C.getRosterShape()};
  }
  function applySaved(saved) {
    if (!saved || saved.v !== 1) return;
    var attempt = function (fn) { try { fn(); } catch (e) { /* a part the engine no longer accepts is skipped, like v2.js */ } };
    attempt(function () { if (saved.scoring && saved.scoring !== C.getState().scoring) C.setScoring(saved.scoring, false); });
    attempt(function () { if (Number.isInteger(saved.teams) && saved.teams !== C.getState().teams) C.setTeams(saved.teams, false); });
    attempt(function () {
      var shape = C.getRosterShape();
      Object.keys(shape).forEach(function (k) {
        var want = saved.roster && saved.roster[k];
        if (Number.isInteger(want) && want !== C.getRosterShape()[k]) C.setRosterSpot(k, want, false);
      });
    });
    attempt(function () {
      var w = saved.weeks, build = C.getBuildContentWeek ? C.getBuildContentWeek() : null;
      if (!w || !Number.isInteger(build) || !C.setLeagueWeeks) return;
      var cur = C.getLeagueWeeks();
      if (w.regularEnd !== cur.regularSeasonEnd || w.playoffLo !== cur.playoffWeeks[0] || w.playoffHi !== cur.playoffWeeks[1]) {
        C.setLeagueWeeks({regularSeasonEnd: w.regularEnd, playoffWeeks: [w.playoffLo, w.playoffHi]});
      }
      if (w.optimize && w.optimize !== C.getOptimizeFor()) C.setOptimizeFor(w.optimize);
      var content = w.build === build ? w.content : build;
      if (content !== C.getContentWeek()) C.setContentWeek(content === build ? null : content);
    });
    attempt(function () {
      if (!saved.adv || !C.setLineupSettings) return;
      var cur = C.getLineupSettings(), diff = {};
      ["injuryHistory", "projectionConfidence", "benchShareOverride"].forEach(function (k) { if (k in saved.adv && saved.adv[k] !== cur[k]) diff[k] = saved.adv[k]; });
      if (Object.keys(diff).length) C.setLineupSettings(diff);
    });
    attempt(function () {
      var s = saved.shares;
      if (s && C.setPositionWeights && POSITIONS.every(function (p) { return finite(s[p]); })) C.setPositionWeights(s);
    });
  }
  // The same record v2.js leagueSnapshot() writes, read from the engine's current state (so weeks, advanced and
  // position shares are what the engine now uses, never a stale copy); equal to the site defaults = not kept.
  var defaults = null;
  function snapshot() {
    var cur = settings();
    var snap = {v: 1, scoring: cur.scoring, teams: cur.teams, roster: cur.roster};
    try {
      var build = C.getBuildContentWeek ? C.getBuildContentWeek() : null;
      if (Number.isInteger(build) && C.getLeagueWeeks && C.getContentWeek && C.getOptimizeFor) {
        var w = C.getLeagueWeeks();
        snap.weeks = {build: build, content: C.getContentWeek(), regularEnd: w.regularSeasonEnd, playoffLo: w.playoffWeeks[0], playoffHi: w.playoffWeeks[1], optimize: C.getOptimizeFor()};
      }
      if (C.getLineupSettings && C.setLineupSettings) {
        var a = C.getLineupSettings();
        snap.adv = {injuryHistory: a.injuryHistory, projectionConfidence: a.projectionConfidence, benchShareOverride: a.benchShareOverride};
      }
      var shares = C.getPositionWeights ? C.getPositionWeights() : null, base = C.getDefaultPositionWeights ? C.getDefaultPositionWeights() : null;
      if (shares && base && POSITIONS.some(function (p) { return Math.abs(Number(shares[p]) - Number(base[p])) > 5e-4; })) {
        snap.shares = {};
        POSITIONS.forEach(function (p) { snap.shares[p] = Number(Number(shares[p]).toFixed(4)); });
      }
    } catch (e) { /* the parts the engine reports are kept */ }
    return snap;
  }
  function saveSettings() {
    var text = JSON.stringify(snapshot());
    try {
      if (text === defaults) localStorage.removeItem(LEAGUE_KEY);
      else localStorage.setItem(LEAGUE_KEY, JSON.stringify(Object.assign(JSON.parse(text), {savedAt: Date.now()})));
    } catch (e) { /* the settings still apply for this visit */ }
  }
  function apply(partial) {
    partial = partial || {};
    if (partial.scoring) C.setScoring(partial.scoring, false);
    if (partial.teams) C.setTeams(Number(partial.teams), false);
    if (typeof partial.superflex === "boolean") C.setRosterSpot("SUPERFLEX", partial.superflex ? 1 : 0, false);
    if (partial.roster) Object.keys(partial.roster).forEach(function (k) { C.setRosterSpot(k, partial.roster[k], false); });
    saveSettings();
    changed();
    return settings();
  }
  // The same settings for this visit only (a shared link's league, JEG-1537): nothing is saved, as v2 applyLinkLeague.
  function applyVisit(partial) {
    partial = partial || {};
    var attempt = function (fn) { try { fn(); } catch (e) { /* a part the engine does not accept is skipped */ } };
    // v2 applyLinkLeague's order: season weeks, the league, the week, advanced settings, position shares last.
    var w = partial.weeks;
    if (w && C.setLeagueWeeks) attempt(function () {
      var cur = C.getLeagueWeeks();
      if (w.regularEnd !== cur.regularSeasonEnd || w.playoffLo !== cur.playoffWeeks[0] || w.playoffHi !== cur.playoffWeeks[1]) {
        C.setLeagueWeeks({regularSeasonEnd: w.regularEnd, playoffWeeks: [w.playoffLo, w.playoffHi]});
      }
      if (w.optimize !== C.getOptimizeFor()) C.setOptimizeFor(w.optimize);
      if (w.content !== C.getContentWeek()) C.setContentWeek(w.content === w.build ? null : w.content);
    });
    if (partial.scoring) attempt(function () { C.setScoring(partial.scoring, false); });
    if (partial.teams) attempt(function () { C.setTeams(Number(partial.teams), false); });
    if (typeof partial.superflex === "boolean") attempt(function () { C.setRosterSpot("SUPERFLEX", partial.superflex ? 1 : 0, false); });
    if (partial.roster) Object.keys(partial.roster).forEach(function (k) { attempt(function () { C.setRosterSpot(k, partial.roster[k], false); }); });
    if (Number.isInteger(partial.week) && C.setWeek) attempt(function () { C.setWeek(partial.week, false); });
    if (partial.adv && C.setLineupSettings) attempt(function () {
      var cur = C.getLineupSettings(), diff = {};
      ["injuryHistory", "projectionConfidence", "benchShareOverride"].forEach(function (k) { if (k in partial.adv && partial.adv[k] !== cur[k]) diff[k] = partial.adv[k]; });
      if (Object.keys(diff).length) C.setLineupSettings(diff);
    });
    if (partial.shares && C.setPositionWeights) attempt(function () { C.setPositionWeights(partial.shares, false); });
    changed();
    return settings();
  }

  // JEG-1539: an old v2 link's league (#route?scoring=..&teams=..&roster=.., chat site_url; legacy-routes.js carries the
  // query after the page's own hash) applies for this visit, as v2 applied a link's league. Build a Trade and Learn read
  // the same parameters themselves; applying them twice gives the same state. Weeks and advanced settings: build.html only.
  var HASH_ROSTER = {QB: "QB", RB: "RB", WR: "WR", TE: "TE", FLEX: "FLEX", SF: "SUPERFLEX", BN: "BENCH"};
  function hashLeague() {
    var at = location.hash.indexOf("?");
    if (at < 0 || /^#s=/.test(location.hash)) return null;
    var q = new URLSearchParams(location.hash.slice(at + 1)), out = {};
    if (["standard", "half_ppr", "ppr"].indexOf(q.get("scoring")) < 0) return null;
    out.scoring = q.get("scoring");
    var teams = Number(q.get("teams"));
    if ([8, 10, 12, 14].indexOf(teams) >= 0) out.teams = teams;
    var roster = {};
    String(q.get("roster") || "").split(".").forEach(function (part) {
      var m = /^([A-Z]+)(\d+)$/.exec(part);
      if (m && HASH_ROSTER[m[1]]) roster[HASH_ROSTER[m[1]]] = Number(m[2]);
    });
    if (Object.keys(roster).length) out.roster = roster;
    return out;
  }

  /* ---- basis and overrides (shared with the live Overrides tab) ---- */
  function engineBasis() { return !state.basis || state.basis.mode === "default" ? null : state.basis; }
  function cleanBasis(rec) {
    if (!rec || typeof rec !== "object" || rec.mode === "default" || !rec.mode) return {mode: "default"};
    if (rec.mode === "single" && SOURCES.indexOf(rec.source) >= 0) return {mode: "single", source: rec.source};
    if (rec.mode === "blend") {
      var named = (Array.isArray(rec.sources) ? rec.sources : Object.keys(rec.weights || {})).filter(function (k) { return SOURCES.indexOf(k) >= 0; });
      if (!named.length) return {mode: "default"};
      var weights = {};
      named.forEach(function (k) { var w = Number(rec.weights && rec.weights[k]); weights[k] = Math.min(100, Math.max(1, Math.round(finite(w) ? w : 1))); });
      return {mode: "blend", sources: named, weights: weights};
    }
    return {mode: "default"};
  }
  function nameOf(key) { var r = C.getPlayer ? C.getPlayer(Number(key)) : null; return r && r.name ? r.name : (state.names[key] || null); }
  function mirrorMap() {
    var byName = {};
    Object.keys(state.values).forEach(function (k) {
      var name = nameOf(k), row = cache && cache.byKey.get(k);
      var entry = state.values[k];
      var value = typeof entry === "number" ? entry : (row && finite(row.ddf) ? row.ddf : null);
      if (name && finite(value)) byName[name] = Math.round(value * 10) / 10;
    });
    return byName;
  }
  function mirror() {
    // The redesign's other pages and the header pill read overrides by name ('ddf:overrides'); absolute values only
    // (that store has no adjustments), so an adjustment shows there as the value it produces.
    if (!DDF.overrides || !DDF.overrides.replace) return;
    var byName = {};
    Object.keys(state.values).forEach(function (k) {
      var name = nameOf(k), row = cache && cache.byKey.get(k);
      var entry = state.values[k];
      var value = typeof entry === "number" ? entry : (row && finite(row.ddf) ? row.ddf : null);
      if (name && finite(value)) byName[name] = Math.round(value * 10) / 10;
    });
    mirroring = true;
    try { DDF.overrides.replace(byName); } finally { mirroring = false; }
  }
  var mirroring = false;
  // Every save is a reader's own change: a shared link's visit-only state ends here and what is on screen becomes the
  // reader's saved overrides (as v2 overrides.js does once the recipient changes something). The link's value context
  // leaves the address too, so a reload does not apply the link again over the saved state.
  function save() {
    if (state.session) {
      state.session = false;
      try { sessionStorage.removeItem(LINK_KEY); } catch (e) { /* nothing stored */ }
      stripLinkContext();
    }
    writeJSON(localStorage, OV_KEY, {v: 2, basis: state.basis, values: state.values, names: state.names});
  }
  function stripLinkContext() {
    var q = location.hash.indexOf("?");
    if (q < 0) return;
    var params = new URLSearchParams(location.hash.slice(q + 1));
    ["valuecontext", "basis", "ov"].forEach(function (k) { params.delete(k); });
    var rest = params.toString();
    try { history.replaceState(history.state, "", location.pathname + location.search + location.hash.slice(0, q) + (rest ? "?" + rest : "")); }
    catch (e) { /* the address keeps the link; the saved state still wins over a reload of it only after this tab closes */ }
  }
  function push() {
    C.setBasis(engineBasis(), false);
    C.setValueOverrides(state.values);
    changed();
    mirror();
  }
  function load() {
    var saved = readJSON(localStorage, OV_KEY);
    state.values = {}; state.names = {}; state.basis = {mode: "default"}; state.session = false;
    if (saved && (saved.v === 1 || saved.v === 2) && saved.values && typeof saved.values === "object") {
      Object.keys(saved.values).forEach(function (k) { var e = normalizeEntry(saved.values[k]); if (e !== null) state.values[k] = e; });
      state.names = saved.names && typeof saved.names === "object" ? saved.names : {};
      if (saved.v === 2) state.basis = cleanBasis(saved.basis);
    }
    var link = readJSON(sessionStorage, LINK_KEY);
    if (link && typeof link === "object") {
      state.session = true;
      if (link.ours) { state.basis = {mode: "default"}; state.values = {}; }
      else {
        if (link.replace) state.values = {};
        if (link.basis) state.basis = cleanBasis(link.basis);
        if (link.values) Object.keys(link.values).forEach(function (k) { var e = normalizeEntry(link.values[k]); if (e !== null) state.values[k] = e; });
      }
    }
  }
  // A link in the live format (#overrides?valuecontext=1&basis=...&ov=...): applies for this tab's visit.
  function applyLinkContext() {
    var VL = window.DDFValueLink, q = location.hash.indexOf("?");
    if (!VL || !VL.readValueContext || q < 0) return false;
    var params = new URLSearchParams(location.hash.slice(q + 1));
    var link;
    try { link = VL.readValueContext(params); } catch (e) { return false; }
    if (!link || !link.present || (link.complete && link.unread && link.unread.length)) return false;
    var sig = (link.complete ? "full:" : "") + (link.basisText || "") + "|" + (link.ovText || "");
    var stored = readJSON(sessionStorage, LINK_KEY);
    if (stored && stored.sig === sig) return false;   // already applied in this tab (load() restored it)
    state.session = true;
    if (link.complete) state.values = {};
    if (link.basis || link.complete) state.basis = cleanBasis(link.basis || {mode: "default"});
    if (link.overrides) Object.keys(link.overrides).forEach(function (k) { var e = normalizeEntry(link.overrides[k]); if (e !== null) state.values[k] = e; });
    writeJSON(sessionStorage, LINK_KEY, {sig: sig, basis: state.basis, values: state.values, replace: true});
    return true;
  }
  // A redesign chat link (#s=...) carries overrides by name; site.js moves them into 'ddf:overrides' when it arrives.
  // Only then are they read, as that link's visit-only state (replacing what is shown, like a complete live link).
  // On an ordinary load 'ddf:overrides' is just this page's own mirror, never a source: re-reading it would bring back
  // overrides the reader removed on the live pages.
  var LINK_TOKEN = /(^#|&)s=/;
  function importLinked() {
    var named = DDF.overrides && DDF.overrides.get ? DDF.overrides.get() : {};
    var names = Object.keys(named || {});
    if (!names.length || JSON.stringify(named) === JSON.stringify(mirrorMap())) return false;   // only this page's own mirror
    var byName = new Map(C.getAllRows().map(function (r) { return [r.name, String(r.player_key)]; }));
    var values = {}, labels = {};
    names.forEach(function (n) {
      var key = /^\d+$/.test(n) ? n : byName.get(n);
      var e = normalizeEntry(named[n]);
      if (key && e !== null) { values[key] = e; labels[key] = nameOf(key) || n; }
    });
    if (!Object.keys(values).length) return false;
    state.values = values; state.names = labels; state.session = true;
    writeJSON(sessionStorage, LINK_KEY, {sig: "s:" + location.hash.length, basis: state.basis, values: state.values, replace: true});
    return true;
  }
  var overrides = {
    all: function () { return JSON.parse(JSON.stringify(state.values)); },
    get: function (key) { return Object.prototype.hasOwnProperty.call(state.values, String(key)) ? state.values[String(key)] : null; },
    set: function (key, value) {
      var e = normalizeEntry(value);
      if (e === null) return false;
      key = String(key); state.values[key] = e; state.names[key] = nameOf(key) || state.names[key] || "";
      save(); push(); return true;
    },
    remove: function (key) { key = String(key); delete state.values[key]; delete state.names[key]; save(); push(); },
    clear: function () { state.values = {}; state.names = {}; save(); push(); },
    replaceAll: function (map) {
      state.values = {}; state.names = {};
      Object.keys(map || {}).forEach(function (k) { var e = normalizeEntry(map[k]); if (e !== null) { state.values[String(k)] = e; state.names[String(k)] = nameOf(k) || ""; } });
      save(); push();
    },
    count: function () { return Object.keys(state.values).length; },
    session: function () { return state.session; }
  };
  function setBasis(rec) {
    state.basis = cleanBasis(rec);
    save(); push();
    return C.getBasis();
  }

  /* ---- league rosters (read-only from the live League tab) ---- */
  function league() {
    var data = readJSON(localStorage, WS_KEY);
    if (!data || data.v !== 1 || !Array.isArray(data.workspaces)) return null;
    var ws = data.workspaces.find(function (w) { return w && w.id === data.activeId; }) || data.workspaces[0];
    if (!ws || !Array.isArray(ws.teams) || !ws.teams.length) return null;
    var teams = ws.teams.map(function (t, i) {
      return {id: String(t.id), name: String(t.name || ("Team " + (i + 1))),
        keys: new Set((t.entries || []).filter(function (e) { return e && e.key !== undefined && e.key !== null; }).map(function (e) { return String(e.key); }))};
    });
    var mine = teams.some(function (t) { return t.id === String(ws.myTeamId); }) ? String(ws.myTeamId) : null;
    return {name: String(ws.name || "Your league"), teams: teams, mine: mine};
  }

  // Build a Trade link for players ({give:[record], get:[record]}): build.html?give=<name>&get=<name> (JEG-1537). The
  // key form (a hash route: ?give=<keys>) is kept for a BUILD_PAGE that names one.
  var BUILD_PAGE = 'build.html';
  function buildHref(o) {
    o = o || {};
    var give = o.give || [], get = o.get || [];
    if (BUILD_PAGE.indexOf("#") >= 0) {
      var q = [];
      if (give.length) q.push("give=" + give.map(function (p) { return p.key; }).join(","));
      if (get.length) q.push("get=" + get.map(function (p) { return p.key; }).join(","));
      return BUILD_PAGE + (q.length ? "?" + q.join("&") : "");
    }
    var params = new URLSearchParams();
    give.forEach(function (p) { params.append("give", p.n); });
    get.forEach(function (p) { params.append("get", p.n); });
    var text = params.toString();
    return BUILD_PAGE + (text ? "?" + text : "");
  }

  function meta() {
    var tag = document.querySelector('meta[name="trade-chart-build"]');
    var asOf = null;
    try { asOf = JSON.parse(document.getElementById("players-data").textContent).meta.as_of || null; } catch (e) { asOf = null; }
    var week = C && C.getReferenceWeek ? C.getReferenceWeek() : null;
    return {buildTag: tag ? tag.content : null, asOf: asOf, week: Number.isInteger(week) ? week : null};
  }

  var ready = new Promise(function (resolve, reject) {
    var started = Date.now();
    (function wait() {
      var c = window.TradeValueCurveControls;
      if (c && c.isReady && c.isReady()) { C = c; return resolve(c); }
      if (Date.now() - started > 60000) return reject(new Error("The value engine did not load."));
      setTimeout(wait, 60);
    })();
  }).then(function (c) {
    defaults = JSON.stringify(snapshot());
    applySaved(readJSON(localStorage, LEAGUE_KEY));
    var visit = hashLeague();
    if (visit) applyVisit(visit);
    load();
    applyLinkContext();
    if (LINK_TOKEN.test(location.hash)) importLinked();
    C.setBasis(engineBasis(), false);
    if (Object.keys(state.values).length) C.setValueOverrides(state.values);
    cache = null;
    window.addEventListener("trade-value-rows-change", function () { cache = null; });
    document.addEventListener("ddf:link", function () { if (LINK_TOKEN.test(location.hash) && importLinked()) push(); });
    window.addEventListener("storage", function (e) {
      if (e.key === OV_KEY && !state.session) { load(); push(); }
      if (e.key === LEAGUE_KEY) { applySaved(readJSON(localStorage, LEAGUE_KEY) || JSON.parse(defaults)); changed(); }
    });
    build();
    mirror();
    return c;
  });
  ready.catch(function (e) { console.error(e); });

  DDF.engine = {
    ready: ready,
    controls: function () { return C; },
    players: function () { return build().list; },
    player: function (key) { return build().byKey.get(String(key)) || null; },
    settings: settings, apply: apply, applyVisit: applyVisit, meta: meta, league: league,
    on: function (fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; },
    overrides: overrides,
    basis: function () { return JSON.parse(JSON.stringify(state.basis)); },
    basisInfo: function () { return C && C.getBasis ? C.getBasis() : null; },
    setBasis: setBasis,
    priorWeek: function () { return C.getPriorWeek("ddf_value"); },
    buildHref: buildHref,
    CHARTS: CHARTS, SOURCES: SOURCES
  };
})();
