/* Team names from a pasted league rosters page.
   DDF.rosterParse.parse(text, opts) -> {teams:[{name, players}], strategy, confidence}
   DDF.rosterParse.teams(text)       -> just the teams array
   Several independent strategies each try to read the paste; every result is scored (how many teams,
   how evenly the player counts fall, how much each name looks like a team name) and the best one wins.
   Layouts covered: Yahoo (desktop, phone, markdown print), ESPN, CBS, Sleeper and NFL.com style rosters,
   CSV/TSV with a Team column, "Team: player, player, ..." one line per team, and "Team 02" style names.
   When nothing scores well the caller shows an edit box, so a bad guess never blocks the user.
   opts.players: optional array of known player names (lowercase ok). Defaults to the site's player table.
   DDF.rosterParse.league(text, {teams}) -> {leagueName, leagueId, platform, confidence} from the page header (below). */
(function(){
  var SLOT = 'QB|RB|WR|TE|FLEX|SUPERFLEX|SFLX|W\\/R\\/T|W\\/R|W\\/T|R\\/W\\/T|OP|K|PK|DEF|D\\/ST|DST|BN|BE|BENCH|IR|TAXI|RES|NA';
  var POS = new RegExp('(^|[\\s\\-·|,(])(' + SLOT + ')([\\s\\-·|,)]|$)');
  var SLOT_ONLY = new RegExp('^\\|?\\s*(' + SLOT + ')\\s*(\\||$)', 'i');
  var STOP = /^((team )?rosters?( list)?|team list|starting rosters?|league|team|teams|pos(ition)?|player|players|starters?|bench|reserve|taxi( squad)?|ir|total|proj(ected)?|opp|week \d+|bye|status|slot|name|rank|record|standings|matchup|schedule|scoreboard|home|sleeper|espn|yahoo( sports)?|cbs( sports)?|nfl|fantasy( football)?|my team|all teams|view|edit|trade|add|drop|waivers?|free agents?|transactions?|settings|owners?|managers?|fpts|avg|last|next|rost|%|stats|news|overview|draft|research|stattracker|league chat|email league|trading list|record book|dues|search|menu|log ?in|sign ?in|more|share|print|notes?|videos?|forecast|injuries|points|projected points|actual|rk|ros|pts|bye week|depth chart)$/i;
  var GAMEY = /^(sun|mon|tue|wed|thu|fri|sat)[a-z]*\.?,?\s+\d{1,2}(:\d{2})?\s*(am|pm)\b|\b\d{1,2}:\d{2}\s*(am|pm)\b|^final\s+[wlt]\b|^bye$|^(postponed|in progress)$|^(vs\.?|@)\s|^(week|wk)\s*\d+$/i;

  function words(s){ return String(s).toLowerCase().replace(/[^a-z0-9' .-]/g, ' ').replace(/\s+/g, ' ').trim(); }

  function knownSet(opts){
    var list = opts && opts.players;
    if (!list) {
      try { list = window.DDF && DDF.link && DDF.link.table && DDF.link.table(1); } catch (e) { list = null; }
    }
    var set = {};
    (list || []).forEach(function(r){ var n = String(r).split('|')[0]; if (n) set[words(n)] = 1; });
    return set;
  }
  /* does the line contain a known player name (2-4 words)? */
  function hasKnownPlayer(line, set){
    var w = words(line).split(' ');
    for (var n = 4; n >= 2; n--) for (var i = 0; i + n <= w.length; i++) if (set[w.slice(i, i + n).join(' ')]) return true;
    return false;
  }

  function normalize(text){
    return String(text || '').split(/\r?\n/).map(function(raw){
      var heading = /^\s*#{1,6}\s/.test(raw);
      var l = raw.replace(/(New |No new )?Player Notes?|Video Forecast/gi, ' ').replace(/\t+/g, ' ').replace(/\*\*|__/g, '').replace(/^\s*[*•·-]\s+/, '').replace(/^\s*#{1,6}\s*/, '').replace(/\s+/g, ' ').trim();
      return l ? {t: l, h: heading, raw: raw} : null;
    }).filter(Boolean);
  }

  function clean(s){ return String(s).replace(/\s+/g, ' ').replace(/^[#\d.)\s:-]+(?=[A-Za-z])/, '').replace(/\s*[\-–—|·:]\s*$/, '').replace(/^\|\s*|\s*\|$/g, '').trim(); }
  function isRow(line){ return POS.test(line); }
  function candidate(line, set){
    var s = clean(line);
    if (s.length < 2 || s.length > 42) return '';
    if (!/[A-Za-z]/.test(s)) return '';
    if (STOP.test(s) || GAMEY.test(s)) return '';
    if (isRow(s)) return '';
    if (/^\|/.test(line)) return '';
    if (/\b\d+-\d+(-\d+)?\b/.test(s) && s.length < 14) return '';
    if (set && hasKnownPlayer(s, set)) return '';
    return s;
  }
  var TABLE_HEAD = /^\|?\s*(pos(ition)?|slot|rk|#)\s*\|?\s*(player|name)\b/i;

  /* A: team name directly above a "Pos  Player" table header (Yahoo and similar) */
  function byTableHeader(L, set){
    var out = [], cur = null;
    for (var i = 0; i < L.length; i++) {
      if (i + 1 < L.length && TABLE_HEAD.test(L[i + 1].t) && !TABLE_HEAD.test(L[i].t)) {
        var name = candidate(L[i].t, set);
        if (name) { cur = {name: name, players: 0}; out.push(cur); i++; continue; }
      }
      if (cur && SLOT_ONLY.test(L[i].t)) cur.players++;
    }
    return out;
  }

  /* B: heading line (markdown # or a lone short line) before a block of player rows */
  function byBlocks(L, set, playersAsRows){
    var out = [], seen = {}, cur = null, run = [];
    L.forEach(function(o){
      var line = o.t, rowLike = isRow(line) || (playersAsRows && set && hasKnownPlayer(line, set));
      if (rowLike) {
        if (run.length) {
          var heads = run.filter(function(r){ return r.h; });
          var name = (heads.length ? heads[heads.length - 1] : run[0]).name, key = name.toLowerCase();
          if (!seen[key]) { seen[key] = {name: name, players: 0}; out.push(seen[key]); }
          cur = seen[key]; run = [];
        }
        if (cur) cur.players++;
        return;
      }
      if (set && hasKnownPlayer(line, set)) return;
      if (TABLE_HEAD.test(line) || /^\|/.test(o.raw.trim())) return;
      var c = candidate(line, set);
      if (c) { run.push({name: c, h: o.h}); if (run.length > 4) run.shift(); } else run = [];
    });
    return out;
  }

  /* C: "Team name: player, player, player" (or " - ", " – ") on one line */
  function byInlineLists(L, set){
    var out = [];
    L.forEach(function(o){
      var m = /^(.{2,42}?)\s*(?::|\s[-–—]\s)\s*(.+)$/.exec(o.t);
      if (!m) return;
      var items = m[2].split(/\s*[,;|•·]\s*|\s{2,}/).filter(Boolean);
      if (items.length < 4) return;
      var known = set ? items.filter(function(i){ return hasKnownPlayer(i, set); }).length : 0;
      if (known < 3 && items.filter(function(i){ return isRow(i); }).length < 3) return;
      var name = candidate(m[1], set); if (name) out.push({name: name, players: items.length});
    });
    return out;
  }

  /* D: spreadsheet style, a header row with a Team (or Owner) column, rows grouped by it */
  function byTable(rawLines){
    var lines = rawLines.filter(function(l){ return l.trim(); });
    if (lines.length < 3) return [];
    var delim = /\t/.test(lines[0]) ? '\t' : (/,/.test(lines[0]) ? ',' : (/\|/.test(lines[0]) ? '|' : ''));
    if (!delim) return [];
    var cells = function(l){ return l.split(delim).map(function(c){ return c.replace(/^\s*"|"\s*$/g, '').trim(); }); };
    var head = cells(lines[0]).map(function(c){ return c.toLowerCase(); });
    var col = -1;
    ['team name', 'team', 'owner', 'manager', 'fantasy team'].some(function(k){ var i = head.indexOf(k); if (i >= 0) { col = i; return true; } });
    if (col < 0) return [];
    var out = [], idx = {};
    lines.slice(1).forEach(function(l){
      var c = cells(l)[col]; if (!c || c.length > 42) return;
      var k = c.toLowerCase(); if (!(k in idx)) { idx[k] = {name: c, players: 0}; out.push(idx[k]); }
      idx[k].players++;
    });
    return out;
  }

  /* E: "Team 02", "Team 7" style names */
  function byNumbered(text){
    var seen = {}, out = [];
    (String(text).match(/\bTeam\s*0?\d{1,2}\b/gi) || []).forEach(function(t){
      var n = t.replace(/\s+/g, ' ').replace(/^team /i, 'Team '); if (!seen[n.toLowerCase()]) { seen[n.toLowerCase()] = 1; out.push({name: n, players: 0}); }
    });
    return out;
  }

  /* how believable is a result? 0 = reject */
  function score(teams, set, bonus){
    if (!teams || teams.length < 2 || teams.length > 32) return 0;
    var names = {}, ok = 0;
    teams.forEach(function(t){
      var k = t.name.toLowerCase(); names[k] = (names[k] || 0) + 1;
      if (t.name.length <= 40 && /[A-Za-z]/.test(t.name) && !GAMEY.test(t.name) && !STOP.test(t.name) && !(set && hasKnownPlayer(t.name, set))) ok++;
    });
    if (Object.keys(names).length !== teams.length) return 0;
    var quality = ok / teams.length;
    if (quality < 0.8) return 0;
    var counts = teams.map(function(t){ return t.players; }).filter(function(n){ return n > 0; });
    var balance = 0.6;
    if (counts.length === teams.length) {
      var mean = counts.reduce(function(a, b){ return a + b; }, 0) / counts.length;
      var sd = Math.sqrt(counts.reduce(function(a, b){ return a + (b - mean) * (b - mean); }, 0) / counts.length);
      balance = 1 - Math.min(sd / (mean || 1), 1) * 0.6;
    }
    return Math.min(teams.length, 16) * quality * balance + (bonus || 0);
  }

  function parse(text, opts){
    var set = knownSet(opts), raw = String(text || ''), L = normalize(raw);
    var tries = [
      ['table-header', byTableHeader(L, set), 3],
      ['spreadsheet', byTable(raw.split(/\r?\n/)), 3],
      ['inline-lists', byInlineLists(L, set), 2],
      ['blocks', byBlocks(L, set), 0],
      ['blocks-players', byBlocks(L, set, true), -0.5],
      ['numbered', byNumbered(raw), -1]
    ];
    var best = null;
    tries.forEach(function(t){ var s = score(t[1], set, t[2]); if (s > 0 && (!best || s > best.s)) best = {s: s, teams: t[1], how: t[0]}; });
    if (!best) return {teams: [], strategy: 'none', confidence: 0};
    var confidence = Math.max(0.1, Math.min(1, best.s / (best.teams.length + 3)));
    return {teams: best.teams, strategy: best.how, confidence: Math.round(confidence * 100) / 100};
  }

  function teams(text, opts){ return parse(text, opts).teams; }

  /* League name, league ID and platform from the page header (JEG-1564). Formats read from real pages:
     Yahoo   "**USO Season XVIII (ID# 848938)**" above the rosters (markdown or plain);
     ESPN    the line after "League Rosters" on the League Rosters page; "League ID" then the number (League Info);
             leagueId=<n> in a pasted ESPN address.
     Sleeper and CBS: platform only (their header layout is not verified). A section heading ("Starting Rosters",
     "Settings") or a team name is never taken as the league name.
     -> {leagueName, leagueId, platform, confidence}; leagueName/leagueId null when not found. */
  var YAHOO_HEAD = /^[*_#\s]*(.{2,60}?)\s*\(\s*ID#\s*(\d{3,12})\s*\)[*_\s]*$/i;
  function league(text, opts){
    var raw = String(text || ''), lines = raw.split(/\r?\n/).map(function(l){ return l.replace(/\t+/g, ' ').trim(); });
    var teamNames = {};
    ((opts && opts.teams) || []).forEach(function(t){ teamNames[String(t.name || t).toLowerCase()] = 1; });
    var plat = /\(\s*ID#\s*\d/.test(raw) || /^\s*\**\s*Yahoo Sports/im.test(raw) || /fantasysports\.yahoo\.com/i.test(raw) ? 'yahoo'
      : /^\s*ESPN( Fantasy)?\s*$/im.test(raw) || /espn\.com/i.test(raw) ? 'espn'
      : /^\s*Sleeper\s*$/im.test(raw) || /sleeper\.(com|app)/i.test(raw) ? 'sleeper'
      : /CBS Sports/i.test(raw) ? 'cbs' : null;
    var out = {leagueName: null, leagueId: null, platform: plat, confidence: 0};
    var okName = function(n){
      n = clean(n || '');
      if (n.length < 2 || n.length > 60 || !/[A-Za-z]/.test(n) || STOP.test(n) || GAMEY.test(n) || teamNames[n.toLowerCase()]) return '';
      if (/^(league rosters|starting rosters|league home|league info|basic settings)$/i.test(n)) return '';
      return n;
    };
    for (var i = 0; i < lines.length; i++) {
      var m = YAHOO_HEAD.exec(lines[i]);
      if (m && okName(m[1])) { out.leagueName = okName(m[1]); out.leagueId = m[2]; out.platform = 'yahoo'; out.confidence = 0.9; return out; }
    }
    for (var j = 0; j < lines.length - 1; j++) {
      if (/^league rosters$/i.test(lines[j])) {
        var k = j + 1; while (k < lines.length && !lines[k]) k++;
        var n = okName(lines[k]);
        if (n && !isRow(lines[k]) && !/\(\s*\d{1,2}\s*-\s*\d{1,2}/.test(lines[k])) { out.leagueName = n; out.confidence = 0.75; break; }
      }
    }
    for (var q = 0; q < lines.length; q++) {
      var id = /^league id\s*:?\s*(\d{3,12})?$/i.exec(lines[q]);
      if (id) { var v = id[1] || ((lines[q + 1] || '').match(/^(\d{3,12})$/) || [])[1]; if (v) { out.leagueId = v; break; } }
    }
    if (!out.leagueId) { var u = /[?&]leagueId=(\d{3,12})/i.exec(raw) || /fantasysports\.yahoo\.com\/f1\/(\d{3,12})/i.exec(raw) || /sleeper\.(?:com|app)\/leagues\/(\d{6,20})/i.exec(raw); if (u) out.leagueId = u[1]; }
    if (!out.confidence && out.leagueId) out.confidence = 0.3;
    return out;
  }
  window.DDF = window.DDF || {};
  window.DDF.rosterParse = {parse: parse, teams: teams, league: league};
  if (typeof module !== 'undefined') module.exports = window.DDF.rosterParse;
})();
