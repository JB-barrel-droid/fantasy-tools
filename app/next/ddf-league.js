/* DDF league adapter for the workspace pages (JEG-1539, lane "team").
 *
 * The reader's league (teams, rosters, which team is theirs) resolved to DDF.engine records, plus the lineup, tier and
 * partner reads the workspace pages share. No value math of its own: starters, bench and totals come from
 * TradeValueFinder (pickStarters / lineupValue / withChartAverage, the functions the live Find a trade page uses) on the
 * engine's own rows; the median is TradeValueTeamSummary.median. This file only picks inputs, applies the published tier
 * rules (DECISIONS "Team assessment rework", "DDF edge threshold 15%") and ranks.
 *
 * League read order (common brief, JEG-1539):
 *   1 DDF.link.current()            a chat link (sessionStorage ddf:league): its settings are the league's settings.
 *                                   A settings-only state confirmed by hand (ddf:link source 'manual', no teams) is
 *                                   not a league here; the confirmed settings already went to the engine.
 *   2 sessionStorage ddf:pasted     connect/setup (JEG-1538): {v:1, teams:[{name, players:[{name,key,pos,..}] | count,
 *                                   unmatched}], me}
 *   3 localStorage ddf.v2.workspaces the active saved league (read only; source 'saved', never copied into ddf:pasted)
 * Nothing here writes ddf:league or ddf:pasted, except setSettings() on a link league (DDF.link.update, as asked).
 *
 * Requires (load before this file, all defer): site.js, ddf-engine.js, v2/finder.js, v2/team-summary.js.
 *
 * API: window.DDF.league
 *   ready            Promise<current()>, after DDF.engine.ready and DDF.link.ready (link decode); a link's settings applied
 *   current()        {name, source:'link'|'pasted'|'saved', settings:{scoring, teams, superflex, slots:[qb,rb,wr,te,flex,bench]},
 *                     me:index|null, teams:[{index, name, players:[record | {name, key:null, pos, unpriced:true}],
 *                     unmatched:[{line|name, reason}], count}], waivers:[record], waiversFromLink:boolean} or null
 *                     (record = DDF.engine record; waivers = state.waivers when the link has them, else every priced
 *                     player on no roster, "available players", best DDF Value first)
 *   applySettings()  the league's settings -> DDF.engine.apply (only a link league carries settings); true when changed
 *   setSettings(s)   {scoring, teams, superflex, slots} -> DDF.engine.apply, and DDF.link.update on a link league
 *   myTeam()         current().teams[me] or null
 *   opponents()      every other team that has players (waivers are never a team here)
 *   lineup(team)     {starters, bench, slots:{QB,RB,WR,TE,FLEX,SUPERFLEX}, empty, unpriced, starterValue, benchValue, total,
 *                     analyst:{starterValue, total, complete}, live:{starterValue, total, complete}} — records, engine
 *                     values; analyst = mean of CBS Sports, USA Today, FantasyPros rows (withChartAverage), live = FantasyCalc
 *   positionTiers()  {slots:{QB:[median..],..}, teams:[{index, positions:{QB:{ratio, tier, value, score, medianSum,
 *                     players:[record], empty}, ..}}]} — ratio = sum(min(v, 1.25 x slot median)) / sum(slot medians)
 *                     over the league's real per-slot medians from every team's starters; Strong >= 1.10, Average >= 0.90
 *   leagueTable()    [{index, name, mine, starter, roster, analystStarter, analystRoster, ranks:{..}, tiers:{..}}]
 *                     tiers by column rank in thirds of the team count (12 teams: 1-4 / 5-8 / 9-12)
 *   partnerTags(team) {ddf, analyst, live, ratioAnalyst, ratioLive, tags:['edge'|'analyst'|'live']} starters, 15% edge rule
 *   partnerRank()    [{index, name, rank, score, get:[{pos, amount, mine, theirs}], give:[..], twoWay, ratioAnalyst, partner}]
 *                     every opponent (never waivers), best trading partner first: score = sum over QB/RB/WR/TE where
 *                     one side is Strong (>= 1.10) and the other Weak (< 0.90) of min(surplus, need) on positionTiers
 *                     ratios (1.0 = middle team), both ways; ties by partnerTags ratioAnalyst; score null without my team
 *   held() / setHeld(keys)       explore.html Evaluate/Hold: held player keys (sessionStorage ddf:hold)
 *   skipped() / setSkipped(names) partners.html skipped teams by name (sessionStorage ddf:skip)
 *   moves() / setMoves(list)      waivers.html roster moves [{add:key, drop:key|null, at}] (sessionStorage ddf:moves), applied to my team
 *   waiversOn() / setWaiversOn(b) the shared "also look for waiver pickups" switch (sessionStorage ddf:waivers "1"/"0")
 *   on(fn)           fn(current()) after a league or value change; returns an unsubscribe
 */
(function () {
  "use strict";
  var DDF = window.DDF = window.DDF || {};
  var VALUE_KEY = "ddf_value";
  var ANALYST = ["cbs", "usatoday", "fantasypros"];
  var LIVE = "fantasycalc";
  var CAP = 1.25, STRONG = 1.10, AVERAGE = 0.90, EDGE = 1.15;
  var POS_ROWS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  var SLOT_KEYS = ["QB", "RB", "WR", "TE", "FLEX", "BENCH"];
  var PASTED = "ddf:pasted", WS_KEY = "ddf.v2.workspaces";
  var finite = function (v) { return typeof v === "number" && isFinite(v); };
  var F = function () { return window.TradeValueFinder; };
  var listeners = [], cache = null, started = false;

  function readJSON(store, key) { try { return JSON.parse(store.getItem(key) || "null"); } catch (e) { return null; } }
  function linkInfo() { return DDF.state ? DDF.state.get("link", null) : null; }

  /* ---- player resolution ---- */
  function index() {
    var recs = DDF.engine.players();
    return {recs: recs, rows: recs.map(function (r) { return r.row; }), byRow: new Map(recs.map(function (r) { return [r.row, r]; }))};
  }
  function unpriced(name, pos) { return {name: String(name || ""), key: null, pos: String(pos || "").toUpperCase(), unpriced: true}; }
  // entry: {name, key?, pos?}. A key the engine prices wins; else the name, told apart by position (finder.matchNames).
  function resolve(entry, ix) {
    if (entry.key !== undefined && entry.key !== null && entry.key !== "") {
      var rec = DDF.engine.player(String(entry.key));
      if (rec) return rec;
    }
    if (entry.name) {
      var hit = F().matchNames([{name: entry.name, pos: entry.pos || ""}], ix.rows).matched[0];
      if (hit) return ix.byRow.get(hit);
    }
    return unpriced(entry.name, entry.pos);
  }
  function linkEntry(p) {
    var info = DDF.link.player(p);
    return {name: info.name || (typeof p === "string" ? p : null), key: info.key || null, pos: info.pos || ""};
  }
  function dedupe(players) {
    var seen = new Set();
    return players.filter(function (p) { if (p.unpriced) return true; if (seen.has(p.key)) return false; seen.add(p.key); return true; });
  }

  /* ---- league sources ---- */
  function fromLink(ix) {
    if (!DDF.link || !DDF.link.current) return null;
    var st = DDF.link.current();
    if (!st || !Array.isArray(st.teams) || !st.teams.length) return null;
    var teams = st.teams.map(function (t, i) {
      var list = Array.isArray(t && t.players) ? t.players : [];
      return {index: i, name: String((t && t.name) || ("Team " + (i + 1))), players: dedupe(list.map(function (p) { return resolve(linkEntry(p), ix); })), unmatched: [], count: list.length};
    });
    var waivers = Array.isArray(st.waivers) && st.waivers.length
      ? dedupe(st.waivers.map(function (p) { return resolve(linkEntry(p), ix); })).filter(function (p) { return !p.unpriced; }) : null;
    var info = linkInfo();
    return {name: String(st.name || (st.league && st.league.name) || "Your league"), source: "link", manual: !!(info && info.source === "manual"),
      settings: st.settings || null, me: Number.isInteger(st.me) && teams[st.me] ? st.me : null, teams: teams, linkWaivers: waivers};
  }
  function fromPasted(ix) {
    var p = DDF.state ? DDF.state.get("pasted", null) : readJSON(sessionStorage, PASTED);
    if (!p || !Array.isArray(p.teams) || !p.teams.length) return null;
    var teams = p.teams.map(function (t, i) {
      var list = Array.isArray(t && t.players) ? t.players : [];
      return {index: i, name: String((t && t.name) || ("Team " + (i + 1))),
        players: dedupe(list.map(function (e) { return resolve({name: e && e.name, key: e && e.key, pos: e && e.pos}, ix); })),
        unmatched: Array.isArray(t && t.unmatched) ? t.unmatched : [], count: Array.isArray(t && t.players) ? list.length : (Number(t && t.players) || 0)};
    });
    return {name: String(p.name || "Your league"), source: "pasted", settings: null, me: Number.isInteger(p.me) && teams[p.me] ? p.me : null, teams: teams, linkWaivers: null};
  }
  function fromSaved(ix) {
    var data = readJSON(localStorage, WS_KEY);
    if (!data || data.v !== 1 || !Array.isArray(data.workspaces)) return null;
    var ws = data.workspaces.find(function (w) { return w && w.id === data.activeId; });
    if (!ws || !Array.isArray(ws.teams) || !ws.teams.length) return null;
    var me = null;
    var teams = ws.teams.map(function (t, i) {
      if (String(t.id) === String(ws.myTeamId)) me = i;
      var list = Array.isArray(t.entries) ? t.entries : [];
      return {index: i, name: String(t.name || ("Team " + (i + 1))), players: dedupe(list.map(function (e) { return resolve({name: e && e.name, key: e && e.key, pos: e && e.pos}, ix); })), unmatched: [], count: list.length};
    });
    return {name: String(ws.name || "Your league"), source: "saved", settings: null, me: me, teams: teams, linkWaivers: null};
  }
  // The league's settings in the link format; a pasted or saved league has none of its own, so they are the engine's.
  function engineSettings() {
    var s = DDF.engine.settings(), r = s.roster || {};
    return {scoring: s.scoring, teams: s.teams, superflex: (r.SUPERFLEX || 0) > 0, slots: SLOT_KEYS.map(function (k) { return r[k] || 0; })};
  }
  // Roster moves from waivers.html ("Confirm roster move", sessionStorage ddf:moves, in order): a local layer over the
  // league, never written into ddf:league / ddf:pasted. add joins my team (skipped if rostered anywhere), drop leaves it.
  function readMoves() {
    var m = DDF.state ? DDF.state.get("moves", []) : [];
    return Array.isArray(m) ? m.filter(function (x) { return x && x.add !== undefined && x.add !== null; }) : [];
  }
  function applyMoves(lg, rostered) {
    var moves = readMoves();
    if (!moves.length || lg.me === null) return;
    var mine = lg.teams[lg.me];
    mine.players = mine.players.slice();
    moves.forEach(function (mv) {
      var add = String(mv.add), drop = mv.drop === null || mv.drop === undefined ? null : String(mv.drop);
      var rec = DDF.engine.player(add);
      if (drop !== null && mine.players.some(function (p) { return !p.unpriced && p.key === drop; })) {
        mine.players = mine.players.filter(function (p) { return p.unpriced || p.key !== drop; });
        rostered.delete(drop);
        if (lg.linkWaivers) { var dr = DDF.engine.player(drop); if (dr && dr.ddf !== null && !lg.linkWaivers.some(function (w) { return w.key === drop; })) lg.linkWaivers.push(dr); }
      }
      if (rec && !rostered.has(add)) {
        mine.players.push(rec);
        rostered.add(add);
        if (lg.linkWaivers) lg.linkWaivers = lg.linkWaivers.filter(function (w) { return w.key !== add; });
      }
    });
  }
  function build() {
    if (cache) return cache.value;
    var ix = index();
    var lg = fromLink(ix);
    if (lg && lg.manual && !lg.teams.some(function (t) { return t.players.length; })) lg = null;
    lg = lg || fromPasted(ix) || fromSaved(ix);
    if (!lg) { cache = {value: null}; return null; }
    var rostered = new Set();
    lg.teams.forEach(function (t) { t.players.forEach(function (p) { if (!p.unpriced) rostered.add(p.key); }); });
    applyMoves(lg, rostered);
    var waivers = lg.linkWaivers || ix.recs.filter(function (r) { return r.ddf !== null && !rostered.has(r.key); })
      .sort(function (a, b) { return b.ddf - a.ddf || a.key.localeCompare(b.key); });
    var value = {name: lg.name, source: lg.source, settings: lg.source === "link" && lg.settings ? lg.settings : engineSettings(),
      me: lg.me, teams: lg.teams, waivers: waivers, waiversFromLink: !!lg.linkWaivers};
    cache = {value: value};
    return value;
  }
  // The journey nav (site.js) shows the post-league links when DDF.leagueKnown is true: same source as the pages.
  function syncNav(cur) {
    var known = !!cur;
    if (DDF.leagueKnown === known) return;
    DDF.leagueKnown = known;
    if (DDF.refreshNav) { try { DDF.refreshNav(); } catch (e) { console.error(e); } }
  }
  function changed() {
    cache = null;
    if (!started) return;
    var cur = build();
    syncNav(cur);
    listeners.slice().forEach(function (fn) { try { fn(cur); } catch (e) { console.error(e); } });
  }

  /* ---- settings ---- */
  function toEngine(s) {
    var out = {};
    if (s.scoring) out.scoring = s.scoring;
    if (Number.isInteger(Number(s.teams)) && Number(s.teams) > 0) out.teams = Number(s.teams);
    if (typeof s.superflex === "boolean") out.superflex = s.superflex;
    if (Array.isArray(s.slots)) {
      out.roster = {};
      SLOT_KEYS.forEach(function (k, i) { if (Number.isInteger(s.slots[i])) out.roster[k] = s.slots[i]; });
    }
    return out;
  }
  function differs(want) {
    var cur = DDF.engine.settings(), r = cur.roster || {};
    if (want.scoring && want.scoring !== cur.scoring) return true;
    if (want.teams && want.teams !== cur.teams) return true;
    if (typeof want.superflex === "boolean" && want.superflex !== ((r.SUPERFLEX || 0) > 0)) return true;
    return Object.keys(want.roster || {}).some(function (k) { return want.roster[k] !== r[k]; });
  }
  function applySettings() {
    var cur = build();
    if (!cur || cur.source !== "link" || !cur.settings) return false;
    var want = toEngine(cur.settings);
    if (!differs(want)) return false;
    // A chat link's league applies for the visit (the tab's ddf:league re-applies it on every page); only a reader's
    // own confirm on settings.html saves settings (review of PR #1345: links must not overwrite saved settings).
    try { (DDF.engine.applyVisit || DDF.engine.apply)(want); } catch (e) { console.error(e); return false; }
    return true;
  }
  function setSettings(s) {
    var want = toEngine(s || {});
    var cur = build();
    if (cur && cur.source === "link" && DDF.link && DDF.link.update) {
      DDF.link.update({settings: Object.assign({}, DDF.link.current().settings, {scoring: s.scoring, teams: Number(s.teams), superflex: !!s.superflex, slots: s.slots.slice()})});
    }
    var out = DDF.engine.apply(want);
    changed();
    return out;
  }

  /* ---- reads on the engine rows ---- */
  function priced(team) { return (team ? team.players : []).filter(function (p) { return !p.unpriced; }); }
  function recsOf(rows, ix) { return rows.map(function (r) { return ix.get(r); }); }
  function lineup(team) {
    var recs = priced(team), rows = recs.map(function (r) { return r.row; });
    var byRow = new Map(recs.map(function (r) { return [r.row, r]; }));
    var shape = DDF.engine.settings().roster;
    var L = F().lineupValue(rows, shape, VALUE_KEY);
    var slots = {};
    POS_ROWS.forEach(function (s) { slots[s] = recsOf(L.slots[s] || [], byRow); });
    var avgRows = F().withChartAverage(rows, ANALYST);
    var A = F().lineupValue(avgRows, shape, F().MARKET_KEY);
    var Lv = F().lineupValue(rows, shape, LIVE);
    var side = function (v) { return {starterValue: v.starterValue, total: v.total, complete: v.unvalued.length === 0, starters: v.starters.length, unvalued: v.unvalued.length}; };
    return {starters: recsOf(L.starters, byRow), bench: recsOf(L.bench, byRow), unvalued: recsOf(L.unvalued, byRow), slots: slots, empty: L.empty,
      unpriced: (team ? team.players : []).filter(function (p) { return p.unpriced; }),
      starterValue: L.starterValue, benchValue: L.benchValue, total: L.total, counts: L.counts,
      analyst: side(A), live: side(Lv)};
  }
  function median(values) { return window.TradeValueTeamSummary.median(values); }
  var tierOf = function (ratio) { return ratio >= STRONG ? "strong" : ratio >= AVERAGE ? "average" : "weak"; };
  function rostered(cur) { return cur ? cur.teams.filter(function (t) { return priced(t).length > 0; }) : []; }
  function positionTiers() {
    var cur = build();
    var teams = rostered(cur);
    var lines = new Map(teams.map(function (t) { return [t.index, lineup(t)]; }));
    var shape = DDF.engine.settings().roster;
    var medians = {};
    POS_ROWS.forEach(function (pos) {
      medians[pos] = [];
      for (var i = 0; i < (shape[pos] || 0); i += 1) {
        var vals = teams.map(function (t) { var p = lines.get(t.index).slots[pos][i]; return p ? p.ddf : null; }).filter(finite);
        medians[pos].push(vals.length ? median(vals) : null);
      }
    });
    var out = teams.map(function (t) {
      var L = lines.get(t.index), positions = {};
      POS_ROWS.forEach(function (pos) {
        var meds = medians[pos];
        if (!meds.length) return;
        var players = L.slots[pos], score = 0, medianSum = 0, value = 0;
        meds.forEach(function (m, i) {
          if (!finite(m)) return;
          var v = players[i] ? players[i].ddf : 0;   // an empty slot is a real hole: nobody on the roster can start there
          value += v; score += Math.min(v, CAP * m); medianSum += m;
        });
        var ratio = medianSum > 0 ? score / medianSum : null;
        positions[pos] = {ratio: ratio, tier: ratio === null ? null : tierOf(ratio), value: value, score: score, medianSum: medianSum,
          players: players, empty: L.empty[pos] || 0};
      });
      return {index: t.index, name: t.name, positions: positions};
    });
    return {slots: medians, teams: out};
  }
  function rankTier(rank, n) { return rank <= Math.round(n / 3) ? "strong" : rank <= Math.round(2 * n / 3) ? "average" : "weak"; }
  var COLUMNS = ["starter", "roster", "analystStarter", "analystRoster"];
  function leagueTable() {
    var cur = build();
    var rows = rostered(cur).map(function (t) {
      var L = lineup(t);
      return {index: t.index, name: t.name, mine: cur.me === t.index, starter: L.starterValue, roster: L.total,
        analystStarter: L.analyst.starterValue, analystRoster: L.analyst.total, analystComplete: L.analyst.complete, ranks: {}, tiers: {}};
    });
    COLUMNS.forEach(function (c) {
      rows.forEach(function (r) {
        r.ranks[c] = 1 + rows.filter(function (o) { return o[c] > r[c]; }).length;   // ties share the better rank
        r.tiers[c] = rankTier(r.ranks[c], rows.length);
      });
    });
    return rows;
  }
  function partnerTags(team) {
    var L = lineup(team);
    var ddf = L.starterValue, analyst = L.analyst.starterValue, live = L.live.starterValue;
    // A starter a chart does not list has no chart value, so an incomplete lineup is not judged against that chart
    // (missing is never 0: it would shrink the chart total and fake an edge). Review of PR #1345.
    var ra = L.analyst.complete && analyst > 0 ? ddf / analyst : null, rl = L.live.complete && live > 0 ? ddf / live : null;
    var tags = [];
    if (ra !== null && ra >= EDGE) tags.push("edge");
    if (ra !== null && ra < 1) tags.push("analyst");
    if (rl !== null && rl < 1) tags.push("live");
    return {ddf: ddf, analyst: analyst, live: live, ratioAnalyst: ra, ratioLive: rl, tags: tags, lineup: L,
      analystComplete: Boolean(L.analyst.complete), liveComplete: Boolean(L.live.complete)};
  }
  // Partner ranking (JEG-1560, docs/claude-log/2026-11-07-jeg1560-partners-ranking.md). Only positionTiers() ratios
  // (1.0 = the league's middle team at that position), their tiers and partnerTags().ratioAnalyst; no new value math.
  // A position counts only where the published tiers line up (Strong >= 1.10 on one side, Weak < 0.90 on the other):
  //   get(p)  = theirs Strong and mine Weak ? min(theirs - 1, 1 - mine) : 0
  //   give(p) = mine Strong and theirs Weak ? min(mine - 1, 1 - theirs) : 0
  //   score   = sum over QB, RB, WR, TE of get + give; ties by ratioAnalyst (higher first, not judged last), then index.
  // Without my team the score is null and the order is the tie-break alone.
  var FIT_POS = ["QB", "RB", "WR", "TE"];
  function partnerRank() {
    var cur = build();
    if (!cur) return [];
    var tiers = positionTiers();
    var byIndex = new Map(tiers.teams.map(function (t) { return [t.index, t]; }));
    var mine = cur.me !== null ? byIndex.get(cur.me) || null : null;
    var ratio = function (t, p) { var x = t && t.positions[p]; return x && finite(x.ratio) ? x.ratio : null; };
    var rows = cur.teams.filter(function (t) { return t.index !== cur.me && t.players.length; }).map(function (team) {
      var theirs = byIndex.get(team.index) || null, tags = partnerTags(team), get = [], give = [], score = null;
      if (mine) {
        score = 0;
        FIT_POS.forEach(function (p) {
          var m = ratio(mine, p), t = ratio(theirs, p);
          if (m === null || t === null) return;
          var g = t >= STRONG && m < AVERAGE ? Math.min(t - 1, 1 - m) : 0, v = m >= STRONG && t < AVERAGE ? Math.min(m - 1, 1 - t) : 0;
          if (g > 0) get.push({pos: p, amount: g, mine: m, theirs: t});
          if (v > 0) give.push({pos: p, amount: v, mine: m, theirs: t});
          score += g + v;
        });
        var big = function (a, b) { return b.amount - a.amount || FIT_POS.indexOf(a.pos) - FIT_POS.indexOf(b.pos); };
        get.sort(big); give.sort(big);
      }
      return {index: team.index, name: team.name, score: score, get: get, give: give, twoWay: get.length > 0 && give.length > 0,
        ratioAnalyst: tags.ratioAnalyst, partner: tags};
    });
    rows.sort(function (a, b) {
      if (a.score !== null && b.score !== null && a.score !== b.score) return b.score - a.score;
      var ra = a.ratioAnalyst, rb = b.ratioAnalyst;
      if (ra !== rb) { if (ra === null) return 1; if (rb === null) return -1; return rb - ra; }
      return a.index - b.index;
    });
    rows.forEach(function (r, i) { r.rank = i + 1; });
    return rows;
  }

  /* ---- workspace choices (session store, shared with find.html / waivers.html) ---- */
  function getList(key) { var v = DDF.state ? DDF.state.get(key, []) : []; return Array.isArray(v) ? v.map(String) : []; }
  function setList(key, list) { if (DDF.state) DDF.state.set(key, (list || []).map(String)); }

  var ready = Promise.all([DDF.engine.ready, DDF.link && DDF.link.ready ? DDF.link.ready.catch(function () { return null; }) : null]).then(function () {
    started = true;
    cache = null;
    applySettings();
    DDF.engine.on(changed);
    document.addEventListener("ddf:link", function () { setTimeout(function () { changed(); applySettings(); }, 0); });
    window.addEventListener("storage", function (e) { if (e.key === WS_KEY) changed(); });
    var cur = build();
    syncNav(cur);
    return cur;
  });
  ready.catch(function (e) { console.error(e); });

  DDF.league = {
    ready: ready,
    current: function () { return started ? build() : null; },
    applySettings: applySettings,
    setSettings: setSettings,
    myTeam: function () { var c = DDF.league.current(); return c && c.me !== null ? c.teams[c.me] : null; },
    opponents: function () { var c = DDF.league.current(); return c ? c.teams.filter(function (t) { return t.index !== c.me && t.players.length; }) : []; },
    lineup: lineup,
    positionTiers: positionTiers,
    leagueTable: leagueTable,
    partnerTags: partnerTags,
    partnerRank: partnerRank,
    tierOf: tierOf,
    moves: function () { return readMoves(); },
    setMoves: function (list) { if (DDF.state) DDF.state.set("moves", Array.isArray(list) ? list : []); changed(); },
    held: function () { return getList("hold"); },
    setHeld: function (keys) { setList("hold", keys); },
    skipped: function () { return getList("skip"); },
    setSkipped: function (names) { setList("skip", names); },
    waiversOn: function () { try { return sessionStorage.getItem("ddf:waivers") !== "0"; } catch (e) { return true; } },
    setWaiversOn: function (on) { try { sessionStorage.setItem("ddf:waivers", on ? "1" : "0"); } catch (e) { /* this visit only */ } },
    refresh: changed,
    on: function (fn) { listeners.push(fn); return function () { listeners = listeners.filter(function (f) { return f !== fn; }); }; },
    RULES: {CAP: CAP, STRONG: STRONG, AVERAGE: AVERAGE, EDGE: EDGE, ANALYST: ANALYST, LIVE: LIVE, VALUE_KEY: VALUE_KEY}
  };
})();
