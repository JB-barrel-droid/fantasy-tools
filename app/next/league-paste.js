/* League paste reader for connect.html (JEG-1538). No value math, no network.
 *
 * Two readers, both already tested on their own:
 *   - v2/roster-paste.js (window.DDFRosterPaste, the live site's matcher, JEG-853/1021): ESPN, Yahoo and Sleeper pages,
 *     player names matched to engine rows (nicknames, platform spellings, ESPN doubled names, K/DEF lines);
 *   - rosterparse.js (DDF.rosterParse): team names from any rosters layout (Yahoo phone tab text, Yahoo markdown,
 *     CSV, "Team: a, b, c" lines, rank prefixes), which the live reader's record/table headers miss.
 * read() runs the live whole-league reader, and also cuts the paste at the team names rosterParse found and runs the
 * live player matcher on each block. The result with more matched players wins, so a page the live site reads today
 * reads the same here.
 *
 * DDF.leaguePaste.read(text, rows, opts)      rows: engine rows [{player_key, name, pos, team}]
 *   -> {ok, reason, site, strategy, names, teams:[{name, players:[{name, key, pos, team, slot, line, id}], unmatched:[{line, reason, pos, key?, team?}]}],
 *       matched, look, missing, notEvaluated}
 *   reason (when !ok): 'empty' | 'one-team' | 'unreadable'
 *   unmatched reason: 'look' (more than one player fits) | 'missing' (no player found) | 'kdef' (kicker or defense, not evaluated;
 *   carries the live roster key "x:POS:..." and team)
 * DDF.leaguePaste.readWithNames(text, names, rows, opts)   same, with team names the reader typed (the edit-names box)
 * opts.table: player table rows ("Name|POS|TEAM|player_key"), for the table id of each player (DDF.link IDs).
 */
(function (root) {
  "use strict";
  var P = function () { return root.DDFRosterPaste || null; };
  var R = function () { return (root.DDF && root.DDF.rosterParse) || null; };

  function keyText(s) {
    return String(s || "").toLowerCase().replace(/[*_#|]/g, " ").replace(/[^a-z0-9]+/g, " ").trim();
  }
  function rowsByKey(rows) {
    var by = {};
    (rows || []).forEach(function (r) { if (r && r.player_key !== undefined && r.player_key !== null) by[String(r.player_key)] = r; });
    return by;
  }
  function tableIds(table) {
    var by = {};
    (table || []).forEach(function (row, i) { var k = String(row).split("|")[3]; if (k && by[k] === undefined) by[k] = i; });
    return by;
  }
  function reasonOf(u) {
    if (u.pos === "K" || u.pos === "DEF") return "kdef";
    return /^ambiguous/i.test(String(u.reason || "")) ? "look" : "missing";
  }

  /* one team from the live reader's shape ({teamName, players, unmatched}) */
  function team(name, players, unmatched, byKey, ids) {
    var seen = {};
    return {
      name: String(name || "").replace(/\s+/g, " ").trim(),
      players: (players || []).filter(function (p) { var k = String(p.id); if (seen[k]) return false; seen[k] = 1; return true; }).map(function (p) {
        var row = byKey[String(p.id)] || {};
        return {name: row.name || p.name, key: String(p.id), pos: row.pos || p.pos || "", team: row.team || "", slot: p.slot || "", line: String(p.sourceLine || "").trim().slice(0, 80),
          id: ids[String(p.id)] === undefined ? null : ids[String(p.id)]};
      }),
      /* a bare slot label ("DEF", "K") is the row's position cell, not a kicker or defense of its own */
      unmatched: (unmatched || []).filter(function (u) {
        var line = String(u.line || "").trim(), lib = P();
        return !((u.pos === "K" || u.pos === "DEF") && (!/[a-z]/.test(line) || (lib && lib.isSlotLabel && lib.isSlotLabel(line))));
      }).map(function (u) {
        var out = {line: String(u.line || "").trim().slice(0, 80), reason: reasonOf(u), pos: u.pos || ""};
        /* K and DEF keep the live roster key ("x:POS:TEAM" or "x:POS:<name>", league.js) so the live store lists them too */
        if (out.reason === "kdef") { var lib = P(); out.team = u.team || ""; out.key = "x:" + out.pos + ":" + (u.team || (lib && lib.normName ? lib.normName(out.line) : out.line.toLowerCase())); }
        return out;
      })
        .filter(function (u) { return u.line; })
    };
  }

  /* Give each line of the paste to a team. A line that is a team name (optionally with a record or rank around it)
     starts that team's block; "Team: a, b, c" gives the rest of the line to that team; a spreadsheet row with a cell
     that is a team name goes to that team. Other lines belong to the block they sit in. */
  var INLINE = /^(.{2,42}?)\s*(?::|\s[-–—]\s)\s*(.+)$/;
  function nameKey(s) { return keyText(String(s || "").replace(/^\s*[#*\s]*\d{1,2}[.)]\s+/, "")); }
  function blocks(text, names) {
    var keys = names.map(nameKey), out = names.map(function (n) { return {name: n, lines: [], found: false}; }), cur = -1;
    var headerOf = function (line) {
      var have = nameKey(line);
      if (!have) return -1;
      var exact = keys.indexOf(have);
      if (exact >= 0) return exact;
      if (/[\t,]/.test(line)) return -1;
      /* a name with a record, rank or owner after it ("Team (5-1-0)", "Team 5-2", "Team (Walt)"), never a longer name
         such as a player whose first name is a team's name ("Josh" and "Josh Allen") */
      for (var k = 0; k < keys.length; k++) {
        if (!keys[k] || have.indexOf(keys[k] + " ") !== 0 || INLINE.test(line)) continue;
        var rest = have.slice(keys[k].length).trim();
        if (/^[\d ]+$/.test(rest) || nameKey(line.replace(/\s*\([^)]*\)\s*/g, " ")) === keys[k]) return k;
      }
      return -1;
    };
    String(text || "").split(/\r?\n/).forEach(function (line) {
      var h = headerOf(line);
      if (h >= 0) { cur = h; out[h].found = true; return; }
      var m = INLINE.exec(line.trim()), k = m ? keys.indexOf(nameKey(m[1])) : -1;
      if (k >= 0) { cur = k; out[k].found = true; out[k].lines.push(m[2]); return; }
      var cells = line.split(/\t|,/);
      if (cells.length > 1) {
        for (var c = 0; c < cells.length; c++) {
          var at = keys.indexOf(nameKey(cells[c].replace(/^\s*"|"\s*$/g, "")));
          if (at >= 0) { out[at].found = true; out[at].lines.push(cells.filter(function (_, j) { return j !== c; }).join(" ")); return; }
        }
      }
      if (cur >= 0) out[cur].lines.push(line);
    });
    return out.filter(function (b) { return b.found; }).map(function (b) { return {name: b.name, text: b.lines.join("\n")}; });
  }

  function byNames(text, names, rows, byKey, ids) {
    var p = P();
    if (!p || !p.extractPlayers) return [];
    return blocks(text, names).map(function (b) {
      var ex = p.extractPlayers(b.text, rows);
      return team(b.name, ex.players, ex.unmatched, byKey, ids);
    });
  }

  function summarize(out) {
    out.matched = out.look = out.missing = out.notEvaluated = 0;
    out.teams.forEach(function (t) {
      out.matched += t.players.length;
      t.unmatched.forEach(function (u) { if (u.reason === "look") out.look++; else if (u.reason === "kdef") out.notEvaluated++; else out.missing++; });
    });
    return out;
  }
  function matchedIn(teams) { return teams.reduce(function (a, t) { return a + t.players.length; }, 0); }
  function withPlayers(teams) { return teams.filter(function (t) { return t.players.length > 0; }).length; }

  function read(text, rows, opts) {
    opts = opts || {};
    var raw = String(text || ""), out = {ok: false, reason: "empty", site: "unknown", strategy: "none", names: [], teams: []};
    if (!raw.trim()) return summarize(out);
    var p = P(), r = R(), byKey = rowsByKey(rows), ids = tableIds(opts.table);
    var live = p && p.parseLeague ? p.parseLeague(raw, rows) : {site: "unknown", teams: []};
    out.site = live.site || "unknown";
    var liveTeams = (live.teams || []).map(function (t) { return team(t.teamName, t.players, t.unmatched, byKey, ids); });
    var parsed = r ? r.parse(raw, {players: opts.table}) : {teams: [], strategy: "none"};
    out.names = (parsed.teams || []).map(function (t) { return t.name; });
    out.league = r && r.league ? r.league(raw, {teams: parsed.teams || []}) : null;
    var named = out.names.length > 1 ? byNames(raw, out.names, rows, byKey, ids) : [];
    var pick = null;
    if (withPlayers(liveTeams) >= 2) pick = {teams: liveTeams, how: "live"};
    if (withPlayers(named) >= 2 && (!pick || withPlayers(named) > withPlayers(pick.teams)
        || (withPlayers(named) === withPlayers(pick.teams) && matchedIn(named) > matchedIn(pick.teams)))) pick = {teams: named, how: "names:" + parsed.strategy};
    if (pick) {
      out.ok = true; out.reason = null; out.strategy = pick.how; out.teams = pick.teams;
      if (!out.names.length || pick.how === "live") out.names = pick.teams.map(function (t) { return t.name; });
      return summarize(out);
    }
    /* one team's page (the reader copied My Team instead of the rosters page) */
    var one = p && p.parse ? p.parse(raw, rows) : null;
    if (one && one.mode !== "matchup" && one.matched > 0 && out.names.length < 2) {
      out.reason = "one-team";
      out.teams = [team("", one.players, one.unmatched, byKey, ids)];
      return summarize(out);
    }
    out.reason = "unreadable";
    return summarize(out);
  }

  function readWithNames(text, names, rows, opts) {
    opts = opts || {};
    var list = (names || []).map(function (n) { return String(n).replace(/\s+/g, " ").trim(); }).filter(Boolean);
    var byKey = rowsByKey(rows), ids = tableIds(opts.table);
    var out = {ok: false, reason: "unreadable", site: P() ? P().detectSite(String(text || "")) : "unknown", strategy: "edited-names", names: list, teams: []};
    out.league = R() && R().league ? R().league(String(text || ""), {teams: list.map(function (n) { return {name: n}; })}) : null;
    if (list.length < 2) return summarize(out);
    var teams = byNames(text, list, rows, byKey, ids);
    var found = {};
    teams.forEach(function (t) { found[t.name.toLowerCase()] = 1; });
    /* a typed name we could not find in the paste still counts as a team (no players yet) */
    list.forEach(function (n) { if (!found[n.toLowerCase()]) teams.push({name: n, players: [], unmatched: []}); });
    out.teams = teams;
    out.ok = teams.length >= 2;
    out.reason = out.ok ? null : "unreadable";
    return summarize(out);
  }

  /* the sessionStorage record setup.html and the workspace pages read (ddf:pasted) */
  function today() { var d = new Date(); return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  /* JEG-1564: enteredAt = the local date of this read; suggestedName / leagueId / platform from the page header
     (rosterparse league()). The name is only a suggestion: setup.html saves `name` when the reader confirms it.
     leagueId stays on this device (never in links or titles). */
  function record(result, source) {
    var lg = result.league || {};
    return {v: 1, source: source || "paste", site: result.site || "unknown", me: null, enteredAt: today(),
      suggestedName: lg.leagueName || null, leagueId: lg.leagueId || null, platform: lg.platform || null,
      teams: result.teams.map(function (t) { return {name: t.name, players: t.players, unmatched: t.unmatched}; })};
  }

  var api = {read: read, readWithNames: readWithNames, record: record, _blocks: blocks};
  root.DDF = root.DDF || {};
  root.DDF.leaguePaste = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
