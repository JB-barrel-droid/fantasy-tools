// Roster paste parser (JEG-853): deterministic, no LLM, no network.
// Turns raw Ctrl+A page text from an ESPN or Yahoo fantasy football team page
// into a list of players matched against the site's own player list.
//
// Usage: DDFRosterPaste.parse(text, playerIndex)
//   text: raw pasted page text (Ctrl+A from a browser)
//   playerIndex: array of engine rows [{player_key, name, pos, team, ...}]
//   returns: {site, players:[{id,name,confidence,sourceLine,slot}], unmatched:[{line,reason}],
//            (slot: the page's own label, e.g. QB/FLEX/BN/Bench/IR, "Injured"/"Bye" for ESPN matchup sections, "" when the page shows none)
//            matched, total, mode:'team'|'matchup', teams?:[...same shape],
//            benchIncluded (matchup: false when bench is collapsed)}

(function (root) {
  "use strict";

  // ---- name normalisation ----
  var SUFFIX_RE = /\b(jr|sr|ii|iii|iv|v)\b\.?$/;
  var NICK_MAP = {
    gabe: "gabriel", mike: "michael", rob: "robert", bob: "robert",
    ted: "theodore", ed: "edward", dan: "daniel", danny: "daniel",
    matt: "matthew", pat: "patrick", will: "william", bill: "william",
    billy: "william", willy: "william", joe: "joseph", joey: "joseph",
    tony: "anthony", chris: "christopher", nick: "nicholas",
    jake: "jacob", josh: "joshua", alex: "alexander", zach: "zachary",
    andy: "andrew", drew: "andrew", ben: "benjamin", sam: "samuel",
    charlie: "charles", dave: "david", greg: "gregory", jeff: "jeffrey",
    jim: "james", jimmy: "james", jon: "jonathan", ken: "kenneth",
    larry: "lawrence", mark: "marcus", marq: "marquise", ray: "raymond",
    rick: "richard", dick: "richard", ron: "ronald", steve: "stephen",
    tim: "timothy", tom: "thomas", tommy: "thomas",
    dk: "d.k.", jk: "j.k.", cj: "c.j.", tj: "t.j.", aj: "a.j.",
    dj: "d.j.", pj: "p.j.", jj: "j.j.", kj: "k.j.",
  };

  function normName(name) {
    return String(name || "").toLowerCase()
      .replace(/[.'''`]/g, "")
      .replace(/[^a-z0-9 ]+/g, " ")
      .replace(/\s+/g, " ").trim()
      .replace(SUFFIX_RE, "").trim();
  }

  function nickVariant(normed) {
    var parts = normed.split(" ");
    if (parts.length < 2) return null;
    var alt = NICK_MAP[parts[0]];
    if (!alt) return null;
    return [alt].concat(parts.slice(1)).join(" ");
  }

  function initialForm(normed) {
    var parts = normed.split(" ");
    if (parts.length < 2) return null;
    return parts[0][0] + " " + parts.slice(1).join(" ");
  }

  // ---- NFL team abbreviations ----
  var TEAM_ALIASES = {
    ari: "ARI", az: "ARI", arizona: "ARI",
    atl: "ATL", atlanta: "ATL",
    bal: "BAL", baltimore: "BAL",
    buf: "BUF", buffalo: "BUF",
    car: "CAR", carolina: "CAR",
    chi: "CHI", chicago: "CHI",
    cin: "CIN", cincinnati: "CIN",
    cle: "CLE", cleveland: "CLE",
    dal: "DAL", dallas: "DAL",
    den: "DEN", denver: "DEN",
    det: "DET", detroit: "DET",
    gb: "GB", gnb: "GB",
    hou: "HOU", houston: "HOU",
    ind: "IND", indianapolis: "IND",
    jac: "JAC", jax: "JAC", jacksonville: "JAC",
    kc: "KC",
    lac: "LAC",
    lar: "LAR", la: "LAR",
    lv: "LV", lvr: "LV",
    mia: "MIA", miami: "MIA",
    min: "MIN", minnesota: "MIN",
    ne: "NE",
    no: "NO",
    nyg: "NYG",
    nyj: "NYJ",
    phi: "PHI", philadelphia: "PHI",
    pit: "PIT", pittsburgh: "PIT",
    sea: "SEA", seattle: "SEA",
    sf: "SF",
    tb: "TB",
    ten: "TEN", tennessee: "TEN",
    was: "WAS", wsh: "WAS", washington: "WAS",
  };
  var VALID_TEAMS = {};
  (function () { for (var k in TEAM_ALIASES) VALID_TEAMS[TEAM_ALIASES[k]] = true; })();

  function normTeam(t) {
    if (!t) return null;
    var key = t.toLowerCase().trim();
    if (TEAM_ALIASES[key]) return TEAM_ALIASES[key];
    var upper = key.toUpperCase();
    if (VALID_TEAMS[upper]) return upper;
    return null;
  }

  // ---- position and slot tokens ----
  var POSITIONS = {QB: 1, RB: 1, WR: 1, TE: 1, K: 1, DEF: 1};
  var SLOT_LABELS = {
    QB: 1, RB: 1, WR: 1, TE: 1, K: 1, DEF: 1, "D/ST": 1, DST: 1,
    FLEX: 1, "W/R/T": 1, "W/R": 1, "RB/WR": 1, "RB/WR/TE": 1,
    SUPERFLEX: 1, SF: 1, OP: 1, "Q/W/R/T": 1,
    BN: 1, BENCH: 1, BE: 1, Bench: 1,
    IR: 1, "IR+": 1,
  };
  function isSlotLabel(s) {
    return !!(SLOT_LABELS[s] || SLOT_LABELS[s.toUpperCase()] || SLOT_LABELS[s.replace(/\d$/, "")]);
  }

  // ---- defence name mapping ----
  var CITY_TO_MASCOT = {
    arizona: "Cardinals", atlanta: "Falcons", baltimore: "Ravens",
    buffalo: "Bills", carolina: "Panthers", chicago: "Bears",
    cincinnati: "Bengals", cleveland: "Browns", dallas: "Cowboys",
    denver: "Broncos", detroit: "Lions", "green bay": "Packers",
    houston: "Texans", indianapolis: "Colts", jacksonville: "Jaguars",
    "kansas city": "Chiefs", "las vegas": "Raiders",
    "los angeles chargers": "Chargers", "los angeles rams": "Rams",
    miami: "Dolphins", minnesota: "Vikings", "new england": "Patriots",
    "new orleans": "Saints", "new york giants": "Giants",
    "new york jets": "Jets", philadelphia: "Eagles",
    pittsburgh: "Steelers", "san francisco": "49ers",
    seattle: "Seahawks", "tampa bay": "Buccaneers",
    tennessee: "Titans", washington: "Commanders",
  };
  var MASCOT_TO_CITY = {};
  (function () { for (var c in CITY_TO_MASCOT) MASCOT_TO_CITY[CITY_TO_MASCOT[c].toLowerCase()] = c; })();

  /** Generate search names for a DEF entry. */
  function dstSearchNames(raw) {
    var cleaned = raw.trim();
    var lower = cleaned.toLowerCase();
    var names = [cleaned];
    // mascot -> add city variants
    var city = MASCOT_TO_CITY[lower];
    if (city) { names.push(CITY_TO_MASCOT[city]); names.push(city); }
    // city -> add mascot
    var mascot = CITY_TO_MASCOT[lower];
    if (mascot) { names.unshift(mascot); }
    // "City Mascot" -> add mascot alone
    for (var c in CITY_TO_MASCOT) {
      if (lower === c + " " + CITY_TO_MASCOT[c].toLowerCase()) {
        names.unshift(CITY_TO_MASCOT[c]);
      }
    }
    return names;
  }

  // ---- Yahoo glued-text cleanup ----
  // Yahoo glues UI text directly onto player names with no space:
  //   "Aaron RodgersPlayer Note"
  //   "Bijan RobinsonVideo ForecastPlayer Note"
  //   "Deebo Samuel Sr.OVideo ForecastNew Player Note"
  //   "ChiefsNo new player Notes"
  var YAHOO_GLUED_RE = /(?:Video Forecast|New Player Note|No new player Notes|Player Note|Notes?)\s*$/i;
  // Injury tags glued directly onto a name: "LoveQ", "EgbukaQ", "Samuel Sr.O"
  // Single uppercase letter Q/O/D right after a lowercase letter or period, or
  // multi-char tags like IR/SSPD/PUP/DTD after a lowercase letter.
  var INJURY_TAG_GLUED = /([a-z.])(Q|O|D|IR|SSPD|PUP|DTD)$/;

  function cleanYahooName(raw) {
    var s = raw;
    for (var i = 0; i < 5; i++) {
      var before = s;
      s = s.replace(YAHOO_GLUED_RE, "").trim();
      if (s === before) break;
    }
    // Strip trailing injury tag glued on
    var m = s.match(INJURY_TAG_GLUED);
    if (m) s = s.slice(0, s.length - m[2].length).trim();
    return s;
  }

  // ---- ESPN doubled-name cleanup ----
  // ESPN team page doubles the name: "Jordan LoveJordan Love"
  // ESPN matchup "Broncos D/STBroncos D/ST" -> "Broncos D/ST"
  function cleanESPNDoubled(raw) {
    var s = raw.trim();
    // Check if the string is two copies of the same name glued together
    if (s.length >= 4 && s.length % 2 === 0) {
      var half = s.length / 2;
      if (s.substring(0, half) === s.substring(half)) return s.substring(0, half);
    }
    // Also check for near-doubles with suffixes like Jr./Sr. where the period is in the middle
    // e.g. "Aaron Jones Sr.Aaron Jones Sr." -- length is odd due to period
    for (var off = -2; off <= 2; off++) {
      var h = Math.floor(s.length / 2) + off;
      if (h >= 3 && h < s.length - 2) {
        if (s.substring(0, h) === s.substring(h)) return s.substring(0, h);
      }
    }
    return s;
  }

  // ---- Team-POS line patterns ----
  // Yahoo: "Pit - QB", "KC - DEF"
  var TEAM_POS_YAHOO_RE = /^([A-Za-z]{2,4})\s*[-–]\s*(QB|RB|WR|TE|K|DEF)$/;
  // ESPN: standalone team code on its own line, followed by position on the next line
  // Also "D/ST" as position
  var ESPN_POS_TOKENS = {QB: "QB", RB: "RB", WR: "WR", TE: "TE", K: "K", "D/ST": "DEF", DST: "DEF", DEF: "DEF"};

  function parseTeamPosYahoo(line) {
    var m = line.trim().match(TEAM_POS_YAHOO_RE);
    if (!m) return null;
    return {team: normTeam(m[1]), pos: m[2]};
  }

  // ---- build player index ----
  function buildIndex(playerRows) {
    var byName = {};
    var byInitial = {};

    function addEntry(map, key, entry) {
      if (!key) return;
      if (!map[key]) map[key] = [];
      map[key].push(entry);
    }

    for (var i = 0; i < (playerRows || []).length; i++) {
      var row = playerRows[i];
      if (!row || !row.name) continue;
      var normed = normName(row.name);
      var team = normTeam(row.team) || null;
      var pos = row.pos || "";
      var entry = {row: row, team: team, pos: pos};

      addEntry(byName, normed, entry);
      var nick = nickVariant(normed);
      if (nick) addEntry(byName, nick, entry);
      var init = initialForm(normed);
      if (init) addEntry(byInitial, init, entry);
    }

    return {byName: byName, byInitial: byInitial};
  }

  // ---- matching ----
  function matchCandidate(candidate, index, seen) {
    function tryLookup(map, key) {
      var hits = map[key];
      if (!hits || hits.length === 0) return null;
      hits = hits.slice(); // copy to allow filtering

      if (hits.length > 1 && candidate.teamHint) {
        var byTeam = hits.filter(function (h) { return h.team === candidate.teamHint; });
        if (byTeam.length > 0) hits = byTeam;
      }
      if (hits.length > 1 && candidate.posHint) {
        var byPos = hits.filter(function (h) { return h.pos === candidate.posHint; });
        if (byPos.length > 0) hits = byPos;
      }
      if (hits.length !== 1) return null;
      return hits[0];
    }

    // D/ST entries: search DEF rows by multiple name forms
    if (candidate.isDST) {
      var dstNames = candidate.dstSearch || [candidate.name];
      for (var d = 0; d < dstNames.length; d++) {
        var normedDST = normName(dstNames[d]);
        var hit = tryLookup(index.byName, normedDST);
        if (hit && hit.pos === "DEF") {
          var key = String(hit.row.player_key);
          if (seen[key]) return {match: null, confidence: 0, reason: "duplicate"};
          seen[key] = true;
          return {match: hit.row, confidence: 1.0, reason: null};
        }
      }
      return {match: null, confidence: 0, reason: "defence not matched"};
    }

    var normed = normName(candidate.name);

    // 1. Exact normalised name
    var result = tryLookup(index.byName, normed);
    if (result) {
      var k1 = String(result.row.player_key);
      if (seen[k1]) return {match: null, confidence: 0, reason: "duplicate"};
      seen[k1] = true;
      return {match: result.row, confidence: 1.0, reason: null};
    }

    // 2. Nickname variant
    var nick = nickVariant(normed);
    if (nick) {
      result = tryLookup(index.byName, nick);
      if (result) {
        var k2 = String(result.row.player_key);
        if (seen[k2]) return {match: null, confidence: 0, reason: "duplicate"};
        seen[k2] = true;
        return {match: result.row, confidence: 0.9, reason: null};
      }
    }

    // 3. Initial form: "D. Henry" -> "d henry"
    var init = initialForm(normed);
    if (init) {
      result = tryLookup(index.byInitial, init);
      if (result) {
        var k3 = String(result.row.player_key);
        if (seen[k3]) return {match: null, confidence: 0, reason: "duplicate"};
        seen[k3] = true;
        return {match: result.row, confidence: 0.8, reason: null};
      }
    }

    return {match: null, confidence: 0, reason: "not in the values"};
  }

  // ---- site detection ----
  function detectSite(text) {
    if (/ESPN Fantasy|ESPN Enterprises/i.test(text)) return "espn";
    if (/Yahoo Fantasy|Yahoo Sports Fantasy|Yahoo Sports LLC/i.test(text)) return "yahoo";
    return "unknown";
  }

  // ---- detect page type ----
  function isMatchupPage(text) {
    // Yahoo matchup: "Compare Managers" + "Players Remaining"
    if (/Compare Managers/i.test(text) && /Players Remaining/i.test(text)) return true;
    // ESPN matchup: "Box Score" in header
    if (/Box Score/i.test(text) && /TOTALS/i.test(text) && /COMPARISON/i.test(text)) return true;
    return false;
  }

  // =========================================================================
  //  FREE-AGENT / PLAYER LIST PAGES (ESPN Add Players, Yahoo Players)
  // =========================================================================
  // These pages have no roster slot labels. Each row is anchored on its team and position line instead:
  // Yahoo "Hou - WR" right under the name; ESPN a team line then a position line (optional injury tag between name and team).
  function parsePlayerListPage(lines, site, index) {
    var players = [];
    var unmatched = [];
    var seen = {};
    function take(name, team, pos, sourceLine) {
      var isDST = pos === "DEF";
      var cleaned = isDST ? name.replace(/\s*D\/?ST\s*$/i, "").trim() : name;
      var candidate = isDST
        ? {name: cleaned, teamHint: team, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(cleaned), sourceLine: sourceLine}
        : {name: cleaned, teamHint: team, posHint: pos, isDST: false, sourceLine: sourceLine};
      var result = matchCandidate(candidate, index, seen);
      if (result.match) {
        players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: sourceLine, slot: ""});
      } else if (result.reason !== "duplicate") {
        unmatched.push({line: sourceLine, reason: result.reason || "not in the values", pos: pos, team: team});
      }
    }
    for (var i = 1; i < lines.length; i++) {
      var ln = lines[i].trim();
      if (!ln) continue;
      var tp = site !== "espn" ? parseTeamPosYahoo(ln) : null;
      if (tp) {
        var prev = lines[i - 1].trim();
        if (prev && !parseTeamPosYahoo(prev)) {
          var nm = cleanYahooName(prev);
          if (nm) take(nm, tp.team, tp.pos, prev);
        }
        continue;
      }
      if (site !== "yahoo" && ESPN_POS_TOKENS[ln] && i >= 2) {
        var teamLine = lines[i - 1].trim();
        var team = normTeam(teamLine);
        if (!team) continue;
        var j = i - 2;
        if (/^(Q|O|D|IR|SSPD|PUP|DOUBTFUL|QUESTIONABLE|OUT|PROBABLE)$/i.test(lines[j].trim()) && j > 0) j--;
        var single = lines[j].trim();
        if (!single || normTeam(single)) continue;
        take(single, team, ESPN_POS_TOKENS[ln], single);
      }
    }
    return {players: players, unmatched: unmatched, matched: players.length, total: players.length + unmatched.length};
  }

  // =========================================================================
  //  YAHOO TEAM PAGE
  // =========================================================================
  // Structure: slot-label line, name line (glued text), "Team - POS" line, game line, stats
  function parseYahooTeamPage(lines, index) {
    var players = [];
    var unmatched = [];
    var seen = {};
    var i = 0;

    while (i < lines.length) {
      var trimmed = lines[i].trim();

      // Is this a slot label?
      if (isSlotLabel(trimmed)) {
        // Next line = player name, line after = "Team - POS"
        if (i + 2 < lines.length) {
          var nameLine = lines[i + 1].trim();
          var teamPosLine = lines[i + 2].trim();
          var tp = parseTeamPosYahoo(teamPosLine);

          if (tp && nameLine) {
            var cleanedName = cleanYahooName(nameLine);
            if (cleanedName) {
              var isDST = tp.pos === "DEF";
              var candidate = isDST
                ? {name: cleanedName, teamHint: tp.team, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(cleanedName), sourceLine: nameLine}
                : {name: cleanedName, teamHint: tp.team, posHint: tp.pos, isDST: false, sourceLine: nameLine};

              var result = matchCandidate(candidate, index, seen);
              if (result.match) {
                players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: nameLine, slot: trimmed});
              } else if (result.reason !== "duplicate") {
                unmatched.push({line: nameLine, reason: result.reason || "not in the values", pos: candidate.posHint, team: candidate.teamHint});
              }
              i += 3;
              continue;
            }
          }
        }
      }
      i++;
    }

    return {players: players, unmatched: unmatched, matched: players.length, total: players.length + unmatched.length};
  }

  // =========================================================================
  //  YAHOO MATCHUP PAGE
  // =========================================================================
  // Interleaved by position row. Each row's structure:
  //   [left name], [left "Team - POS"], [left game], [left proj], "–", [slot], "–", [right proj], [right name], [right "Team - POS"], [right game]
  // The team-pos lines are reliable anchors. They come in pairs.
  function parseYahooMatchupPage(lines, index) {
    // Find all team-pos lines
    var tpLines = [];
    for (var i = 0; i < lines.length; i++) {
      var tp = parseTeamPosYahoo(lines[i].trim());
      if (tp) tpLines.push({index: i, team: tp.team, pos: tp.pos});
    }

    var teamA = {players: [], unmatched: []};
    var teamB = {players: [], unmatched: []};
    var seenA = {};
    var seenB = {};

    var t = 0;
    while (t < tpLines.length) {
      var leftTP = tpLines[t];
      // Find name line above this team-pos (1-3 lines up, non-empty, non-slot, non-numeric)
      var leftNameLine = findNameAbove(lines, leftTP.index);

      // Look for right-side TP (next one, within ~15 lines)
      var rightTP = null;
      var rightNameLine = null;
      if (t + 1 < tpLines.length && tpLines[t + 1].index - leftTP.index < 15) {
        rightTP = tpLines[t + 1];
        rightNameLine = findNameAbove(lines, rightTP.index);
        t += 2;
      } else {
        t += 1;
      }

      var slot = slotBetween(lines, leftTP.index, rightTP ? rightTP.index : Math.min(lines.length, leftTP.index + 8));
      if (leftNameLine) processEntry(leftNameLine, leftTP, teamA, index, seenA, slot);
      if (rightNameLine && rightTP) processEntry(rightNameLine, rightTP, teamB, index, seenB, slot);
    }

    // Team names: Yahoo prints each side's header as a "logo" line followed by the team name (left side first).
    var names = [];
    for (var n = 0; n + 1 < lines.length && names.length < 2; n++) {
      if (lines[n].trim() === "logo" && lines[n + 1].trim()) names.push(lines[n + 1].trim());
    }
    if (names.length === 2) { teamA.teamName = names[0]; teamB.teamName = names[1]; }
    return {teamA: teamA, teamB: teamB};
  }

  // The slot label ("QB", "FLEX", "BN") printed between the two sides of a matchup row.
  function slotBetween(lines, from, to) {
    for (var i = from + 1; i < to; i++) {
      var s = lines[i].trim();
      if (isSlotLabel(s)) return s;
    }
    return "";
  }

  function findNameAbove(lines, tpIndex) {
    for (var back = 1; back <= 3 && tpIndex - back >= 0; back++) {
      var candidate = lines[tpIndex - back].trim();
      if (candidate && !parseTeamPosYahoo(candidate) && !isSlotLabel(candidate)
        && candidate !== "–" && !/^\d+\.?\d*$/.test(candidate) && candidate.length > 1) {
        return candidate;
      }
    }
    return null;
  }

  function processEntry(nameLine, tp, team, index, seen, slot) {
    var cleanedName = cleanYahooName(nameLine);
    if (!cleanedName) return;

    var isDST = tp.pos === "DEF";
    var candidate = isDST
      ? {name: cleanedName, teamHint: tp.team, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(cleanedName), sourceLine: nameLine}
      : {name: cleanedName, teamHint: tp.team, posHint: tp.pos, isDST: false, sourceLine: nameLine};

    var result = matchCandidate(candidate, index, seen);
    if (result.match) {
      team.players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: nameLine, slot: slot || ""});
    } else if (result.reason !== "duplicate") {
      team.unmatched.push({line: nameLine, reason: result.reason || "not in the values", pos: candidate.posHint, team: candidate.teamHint});
    }
  }

  // =========================================================================
  //  ESPN TEAM PAGE
  // =========================================================================
  // Structure per player:
  //   [slot label: QB/RB/WR/TE/FLEX/D\\/ST/K/Bench/IR]
  //   [doubled name: "Jordan LoveJordan Love"]
  //   [single name: "Jordan Love"]
  //   [optional injury: Q/O/D/IR/SSPD/PUP]
  //   [team code: GB]
  //   [position: QB / RB / WR / TE / K / D/ST]
  //   [blank or "MOVE"]
  //   ...stats...
  // Key: a player is recognised only when the structural slot->name->team->pos sequence holds.
  // The nav lists team/manager names that must NOT match.
  function parseESPNTeamPage(lines, index) {
    var players = [];
    var unmatched = [];
    var seen = {};

    // Find "STARTERS" line to know where the roster table begins
    var startIdx = 0;
    for (var s = 0; s < lines.length; s++) {
      if (/^STARTERS\b/.test(lines[s].trim())) { startIdx = s; break; }
    }

    var i = startIdx;
    while (i < lines.length) {
      var trimmed = lines[i].trim();

      // Stop at glossary/footer
      if (/^Fantasy Football Glossary/i.test(trimmed)) break;

      // Is this a slot label?
      if (isSlotLabel(trimmed) || trimmed === "TOTALS") {
        if (trimmed === "TOTALS") { i++; continue; }

        // Scan forward for the doubled-name + single-name + team + position pattern
        // ESPN: doubled-name, single-name, [injury], team, position
        var j = i + 1;
        // Skip blank lines
        while (j < lines.length && !lines[j].trim()) j++;
        if (j >= lines.length) { i++; continue; }

        var doubledLine = lines[j].trim();
        var singleName = null;
        var teamCode = null;
        var posCode = null;
        var injuryTag = null;

        // The doubled name should be followed by the single name on the next line
        var k = j + 1;
        while (k < lines.length && !lines[k].trim()) k++;
        if (k < lines.length) {
          singleName = lines[k].trim();
        }

        // After the single name: optional injury tag, then team code, then position
        var scan = k + 1;
        // Look for team and position within next few lines
        for (var look = 0; look < 5 && scan + look < lines.length; look++) {
          var ln = lines[scan + look].trim();
          if (!ln) continue;
          if (/^(Q|O|D|IR|SSPD|PUP|DOUBTFUL|QUESTIONABLE|OUT|PROBABLE)$/i.test(ln) && !injuryTag) {
            injuryTag = ln;
            continue;
          }
          if (!teamCode && normTeam(ln)) {
            teamCode = normTeam(ln);
            continue;
          }
          if (!posCode && ESPN_POS_TOKENS[ln]) {
            posCode = ESPN_POS_TOKENS[ln];
            break;
          }
          // If we hit MOVE or an opponent line, stop
          if (ln === "MOVE" || /^@/.test(ln) || /^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\b/i.test(ln)) break;
        }

        // We need both team and position to confirm this is a player row
        if (singleName && teamCode && posCode) {
          var isDST = posCode === "DEF";
          // Clean ESPN doubled name (for DST: "Broncos D/STBroncos D/ST" -> "Broncos D/ST" -> "Broncos")
          var playerName = singleName;
          if (isDST) {
            // Strip "D/ST" suffix
            playerName = playerName.replace(/\s*D\/?ST\s*$/i, "").trim();
          }

          var candidate = isDST
            ? {name: playerName, teamHint: teamCode, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(playerName), sourceLine: singleName}
            : {name: playerName, teamHint: teamCode, posHint: posCode, isDST: false, sourceLine: singleName};

          var result = matchCandidate(candidate, index, seen);
          if (result.match) {
            players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: singleName, slot: trimmed});
          } else if (result.reason !== "duplicate") {
            unmatched.push({line: singleName, reason: result.reason || "not in the values", pos: candidate.posHint, team: candidate.teamHint});
          }
        }
      }
      i++;
    }

    return {players: players, unmatched: unmatched, matched: players.length, total: players.length + unmatched.length};
  }

  // =========================================================================
  //  ESPN MATCHUP PAGE
  // =========================================================================
  // Two sequential blocks. Each block starts with "<Team name>\tNFL Week N\tSTATS"
  // or "<Team name>  NFL Week N  STATS" (tab-separated in the paste).
  // Then "Player, Team POS" header, then rows: name, team, position, [injury], opp, PRK, avg, proj.
  // Followed by "TOTALS". Then "COMPARISON" section, then second block.
  // Also: "Injuries" and "Bye Week Players" sections with extra rostered players.
  var ESPN_BLOCK_HEADER_RE = /^(.+?)\s+NFL Week \d+\s+STATS$/;
  var ESPN_BLOCK_HEADER_TAB_RE = /^(.+?)\tNFL Week \d+\tSTATS$/;

  function parseESPNMatchupPage(lines, index) {
    // Find block boundaries
    var blocks = [];
    for (var i = 0; i < lines.length; i++) {
      var trimmed = lines[i].trim();
      var m = trimmed.match(ESPN_BLOCK_HEADER_TAB_RE) || trimmed.match(ESPN_BLOCK_HEADER_RE);
      if (m) {
        blocks.push({teamName: m[1].trim(), startIndex: i});
      }
    }

    // Find end of each block (TOTALS line)
    for (var b = 0; b < blocks.length; b++) {
      var endIdx = blocks[b].startIndex + 1;
      while (endIdx < lines.length) {
        if (lines[endIdx].trim() === "TOTALS") { endIdx++; break; }
        if (endIdx > blocks[b].startIndex + 200) break; // safety
        endIdx++;
      }
      blocks[b].endIndex = endIdx;
    }

    // Parse each block
    var teams = [];
    for (var bi = 0; bi < blocks.length; bi++) {
      var block = blocks[bi];
      var seen = {};
      var result = parseESPNMatchupBlock(lines, block.startIndex, block.endIndex, index, seen);
      result.teamName = block.teamName;
      result.seen = seen;
      teams.push(result);
    }

    // Parse Injuries section
    var injStart = -1;
    var byeStart = -1;
    for (var ii = 0; ii < lines.length; ii++) {
      if (lines[ii].trim() === "Injuries") injStart = ii;
      if (/^Bye Week Players/i.test(lines[ii].trim())) byeStart = ii;
    }

    // Injuries: "<Team name>" then "Player" then rows of "Name\nTeam\nPos\n[Injury]"
    if (injStart >= 0) {
      var injEnd = byeStart >= 0 ? byeStart : Math.min(injStart + 100, lines.length);
      parseESPNInjuriesSection(lines, injStart, injEnd, index, teams);
    }

    // Bye Week Players: "<Team name>" then "Player" then "Name Team, POS" lines
    if (byeStart >= 0) {
      var bEnd = Math.min(byeStart + 100, lines.length);
      parseESPNByeSection(lines, byeStart, bEnd, index, teams);
    }

    return teams;
  }

  function parseESPNMatchupBlock(lines, start, end, index, seen) {
    var players = [];
    var unmatched = [];

    // Skip header lines (team name, "Player, Team POS", "opp", "PRK", "avg", "proj")
    var i = start + 1;
    // Find "Player, Team POS" header
    while (i < end) {
      if (/^Player/i.test(lines[i].trim())) { i++; break; }
      i++;
    }
    // Skip remaining column headers
    while (i < end && /^(opp|PRK|avg|proj)$/i.test(lines[i].trim())) i++;

    // Now parse player rows: name, team, position, [injury], opponent, PRK, avg, proj
    while (i < end) {
      var trimmed = lines[i].trim();
      if (trimmed === "TOTALS") break;
      if (!trimmed) { i++; continue; }

      // Potential player name
      var playerName = trimmed;
      var teamCode = null;
      var posCode = null;
      var injTag = null;

      // Scan next lines for team and position
      var found = false;
      for (var look = 1; look <= 4 && i + look < end; look++) {
        var ln = lines[i + look].trim();
        if (!ln) continue;
        if (!teamCode && normTeam(ln)) {
          teamCode = normTeam(ln);
          continue;
        }
        if (!posCode && ESPN_POS_TOKENS[ln]) {
          posCode = ESPN_POS_TOKENS[ln];
          found = true;
          break;
        }
        if (/^(Q|O|D|IR|SSPD|PUP)$/i.test(ln) && !injTag) {
          injTag = ln;
          continue;
        }
        // If we hit something else (opponent, number, etc.), this wasn't a player
        break;
      }

      if (found && teamCode && posCode) {
        var isDST = posCode === "DEF";
        var cleanName = isDST ? playerName.replace(/\s*D\/?ST\s*$/i, "").trim() : playerName;

        var candidate = isDST
          ? {name: cleanName, teamHint: teamCode, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(cleanName), sourceLine: playerName}
          : {name: cleanName, teamHint: teamCode, posHint: posCode, isDST: false, sourceLine: playerName};

        var result = matchCandidate(candidate, index, seen);
        if (result.match) {
          players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: playerName, slot: ""});
        } else if (result.reason !== "duplicate") {
          unmatched.push({line: playerName, reason: result.reason || "not in the values", pos: candidate.posHint, team: candidate.teamHint});
        }
        // Skip past this player's block
        i += (look || 1) + 1;
        // Skip numeric stat lines
        while (i < end && /^[\d.@+-]+$|^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\b/i.test(lines[i].trim())) i++;
        continue;
      }

      i++;
    }

    return {players: players, unmatched: unmatched, matched: players.length, total: players.length + unmatched.length};
  }

  function parseESPNInjuriesSection(lines, start, end, index, teams) {
    // Injuries section: "<Team name>" then "Player" then "Name\nTeam\nPos\nInjuryTag"
    var currentTeamIdx = -1;
    var i = start + 1; // skip "Injuries" header

    while (i < end) {
      var trimmed = lines[i].trim();
      if (!trimmed || trimmed === "Player") { i++; continue; }

      // Check if this line is a team name from one of the blocks
      var teamMatch = -1;
      for (var t = 0; t < teams.length; t++) {
        if (trimmed === teams[t].teamName) { teamMatch = t; break; }
      }
      if (teamMatch >= 0) { currentTeamIdx = teamMatch; i++; continue; }

      // Try to parse a player: name, team, position, injury tag
      if (currentTeamIdx >= 0 && i + 2 < end) {
        var name = trimmed;
        var teamLine = lines[i + 1] ? lines[i + 1].trim() : "";
        var posLine = lines[i + 2] ? lines[i + 2].trim() : "";
        var tc = normTeam(teamLine);
        var pc = ESPN_POS_TOKENS[posLine];

        if (tc && pc) {
          var team = teams[currentTeamIdx];
          var isDST = pc === "DEF";
          var cleanName = isDST ? name.replace(/\s*D\/?ST\s*$/i, "").trim() : name;
          var candidate = isDST
            ? {name: cleanName, teamHint: tc, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(cleanName), sourceLine: name}
            : {name: cleanName, teamHint: tc, posHint: pc, isDST: false, sourceLine: name};

          var result = matchCandidate(candidate, index, team.seen);
          if (result.match) {
            team.players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: name, slot: "Injured"});
            team.matched++;
            team.total++;
          } else if (result.reason !== "duplicate") {
            team.unmatched.push({line: name, reason: result.reason || "not in the values", pos: candidate.posHint, team: candidate.teamHint});
            team.total++;
          }
          i += 3;
          // Skip injury tag line
          if (i < end && /^(Q|O|D|IR|SSPD|PUP)$/i.test(lines[i].trim())) i++;
          continue;
        }
      }
      i++;
    }
  }

  function parseESPNByeSection(lines, start, end, index, teams) {
    // Bye Week Players: "<Team name>" then "Player" then "Name Team, POS" lines
    // or "No players on bye this week."
    var currentTeamIdx = -1;
    var i = start + 1; // skip header

    while (i < end) {
      var trimmed = lines[i].trim();
      if (!trimmed || trimmed === "Player" || /^No players on bye/i.test(trimmed)) { i++; continue; }
      // Stop at non-roster sections
      if (/^Points Scored/i.test(trimmed) || /^Fantasy Football Glossary/i.test(trimmed)) break;

      // Check if this line is a team name
      var teamMatch = -1;
      for (var t = 0; t < teams.length; t++) {
        if (trimmed === teams[t].teamName) { teamMatch = t; break; }
      }
      if (teamMatch >= 0) { currentTeamIdx = teamMatch; i++; continue; }

      // Try "Name TEAM, POS" pattern
      if (currentTeamIdx >= 0) {
        var byeMatch = trimmed.match(/^(.+?)\s+([A-Z]{2,4}),\s*(QB|RB|WR|TE|K|DEF|D\/ST)$/);
        if (byeMatch) {
          var team = teams[currentTeamIdx];
          var playerName = byeMatch[1];
          var tc = normTeam(byeMatch[2]);
          var pc = byeMatch[3] === "D/ST" ? "DEF" : byeMatch[3];

          if (tc) {
            var isDST = pc === "DEF";
            var cleanName = isDST ? playerName.replace(/\s*D\/?ST\s*$/i, "").trim() : playerName;
            var candidate = isDST
              ? {name: cleanName, teamHint: tc, posHint: "DEF", isDST: true, dstSearch: dstSearchNames(cleanName), sourceLine: trimmed}
              : {name: cleanName, teamHint: tc, posHint: pc, isDST: false, sourceLine: trimmed};

            var result = matchCandidate(candidate, index, team.seen);
            if (result.match) {
              team.players.push({id: String(result.match.player_key), name: result.match.name, confidence: result.confidence, sourceLine: trimmed, slot: "Bye"});
              team.matched++;
              team.total++;
            } else if (result.reason !== "duplicate") {
              team.unmatched.push({line: trimmed, reason: result.reason || "not in the values", pos: candidate.posHint, team: candidate.teamHint});
              team.total++;
            }
          }
        }
      }
      i++;
    }
  }

  // =========================================================================
  //  MAIN PARSE
  // =========================================================================
  function parse(text, playerIndex) {
    if (!text || typeof text !== "string" || !text.trim()) {
      return {site: "unknown", players: [], unmatched: [], matched: 0, total: 0, mode: "team"};
    }
    if (!playerIndex || !Array.isArray(playerIndex) || playerIndex.length === 0) {
      return {site: "unknown", players: [], unmatched: [{line: "(no player index)", reason: "no player list provided"}], matched: 0, total: 0, mode: "team"};
    }

    var site = detectSite(text);
    var index = buildIndex(playerIndex);
    var rawLines = text.split(/\r?\n/);
    var matchup = isMatchupPage(text);

    // ---- Yahoo ----
    if (site === "yahoo") {
      if (matchup) {
        var ym = parseYahooMatchupPage(rawLines, index);
        var allP = ym.teamA.players.concat(ym.teamB.players);
        var allU = ym.teamA.unmatched.concat(ym.teamB.unmatched);
        var benchCollapsed = /Show Bench Players/i.test(text) && !hasBNLine(rawLines);
        return {
          site: site,
          players: allP,
          unmatched: allU,
          matched: allP.length,
          total: allP.length + allU.length,
          mode: "matchup",
          benchIncluded: !benchCollapsed,
          teams: [
            {teamName: ym.teamA.teamName, players: ym.teamA.players, unmatched: ym.teamA.unmatched, matched: ym.teamA.players.length, total: ym.teamA.players.length + ym.teamA.unmatched.length},
            {teamName: ym.teamB.teamName, players: ym.teamB.players, unmatched: ym.teamB.unmatched, matched: ym.teamB.players.length, total: ym.teamB.players.length + ym.teamB.unmatched.length},
          ],
        };
      } else {
        var yt = parseYahooTeamPage(rawLines, index);
        // No slot labels: a free-agent or players page. Fall through to the extractor below.
        if (yt.matched > 0) {
          return {
            site: site,
            players: yt.players,
            unmatched: yt.unmatched,
            matched: yt.matched,
            total: yt.total,
            mode: "team",
          };
        }
      }
    }

    // ---- ESPN ----
    if (site === "espn") {
      if (matchup) {
        var espnTeams = parseESPNMatchupPage(rawLines, index);
        var hasBench = /Show Bench/i.test(text);
        if (espnTeams.length >= 2) {
          var eAllP = espnTeams[0].players.concat(espnTeams[1].players);
          var eAllU = espnTeams[0].unmatched.concat(espnTeams[1].unmatched);
          return {
            site: site,
            players: eAllP,
            unmatched: eAllU,
            matched: eAllP.length,
            total: eAllP.length + eAllU.length,
            mode: "matchup",
            benchIncluded: !hasBench,
            teams: espnTeams.map(function (t) {
              return {teamName: t.teamName, players: t.players, unmatched: t.unmatched, matched: t.players.length, total: t.players.length + t.unmatched.length};
            }),
          };
        }
        // Fall through if we couldn't find two blocks
      }

      // Team page
      var et = parseESPNTeamPage(rawLines, index);
      // No roster table (no STARTERS or slot labels): a free-agent or players page. Fall through to the extractor below.
      if (et.matched > 0) {
        return {
          site: site,
          players: et.players,
          unmatched: et.unmatched,
          matched: et.matched,
          total: et.total,
          mode: "team",
        };
      }
    }

    // ---- Unknown: try format-specific parsers, then fall back to n-gram extraction ----
    if (site !== "unknown") {
      var listed = parsePlayerListPage(rawLines, site, index);
      if (listed.matched > 0) {
        return {site: site, players: listed.players, unmatched: listed.unmatched, matched: listed.matched, total: listed.total, mode: "list"};
      }
    }
    var tryYahoo = site === "unknown" ? parseYahooTeamPage(rawLines, index) : {matched: 0};
    var tryEspn = site === "unknown" ? parseESPNTeamPage(rawLines, index) : {matched: 0};
    var best = tryYahoo.matched >= tryEspn.matched ? tryYahoo : tryEspn;
    // If format-specific parsers found players, use the best one.
    if (best.matched > 0) {
      return {
        site: "unknown",
        players: best.players,
        unmatched: best.unmatched,
        matched: best.matched,
        total: best.total,
        mode: "team",
      };
    }
    // Otherwise, use the source-agnostic n-gram extractor (JEG-1010).
    var extracted = extractPlayers(text, playerIndex);
    return {
      site: site,
      players: extracted.players,
      unmatched: extracted.unmatched,
      matched: extracted.matched,
      total: extracted.total,
      ignoredLines: extracted.ignoredLines,
      mode: "extract",
    };
  }

  // ---- which list did the reader paste? ----
  // A roster page (has slot labels, or a matchup box score) versus a free-agent / waiver page. res: the result of parse(text).
  // Returns "roster", "waivers" or "unknown" (a bare list of names, or cues for both).
  var WAIVER_CUES = /\b(free agents?|available players|add players|waiver (wire|order|priority|claims?)|% ?(owned|own)\b|claim)\b|^\s*add\s*$/im;
  var ROSTER_CUES = /\b(starters|bench|my roster|my team|roster for week|set lineup|start active players)\b/i;
  function detectListKind(text, res) {
    if (res && res.mode === "list") return "waivers";
    if (res && (res.mode === "team" || res.mode === "matchup")) return "roster";
    var t = String(text || "");
    var waiver = WAIVER_CUES.test(t);
    var roster = ROSTER_CUES.test(t);
    if (waiver && !roster) return "waivers";
    if (roster && !waiver) return "roster";
    return "unknown";
  }

  // ---- source-agnostic n-gram extraction (JEG-1010) ----
  // Scans every line for player names by sliding n-gram windows over tokens and matching
  // against the engine's player list.  Tolerates arbitrary noise (columns, headers, nav,
  // injury tags, numbers, ads).  Never invents players: a match must be exact (after
  // normalisation) or a known nickname/initial form confirmed by position or team context.
  // Defences are found by city, mascot or "City Mascot" forms.

  // Tokenize a line into word-like tokens, splitting on whitespace, tabs, pipes.
  // Preserves apostrophes and hyphens within words (for names like Ja'Marr, Amon-Ra).
  function extractTokens(line) {
    return line.replace(/\t+/g, " ").replace(/\|/g, " ").replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
  }

  // Build a set of all first-word keys from the name index, for quick rejection.
  function buildFirstWords(index) {
    var firstWords = {};
    var addKeys = function (map) {
      var names = Object.keys(map);
      for (var i = 0; i < names.length; i++) {
        var parts = names[i].split(" ");
        if (parts[0]) firstWords[parts[0]] = 1;
        // Also add last word (for reversed names)
        if (parts.length > 1) firstWords[parts[parts.length - 1]] = 1;
      }
    };
    addKeys(index.byName);
    addKeys(index.byInitial);
    return firstWords;
  }

  // Find position and team hints on a line.
  function lineHints(tokens) {
    var posHint = null;
    var teamHint = null;
    for (var i = 0; i < tokens.length; i++) {
      var raw = tokens[i];
      var upper = raw.toUpperCase().replace(/[^A-Z/]/g, "");
      if (!posHint && POSITIONS[upper]) posHint = upper;
      if (upper === "D/ST" || upper === "DST") posHint = "DEF";
      var nt = normTeam(raw);
      if (nt && !teamHint) teamHint = nt;
    }
    return {posHint: posHint, teamHint: teamHint};
  }

  // Try to match a sequence of tokens as a player name.
  // Handles "First Last", "Last, First", nicknames and initial forms.
  function tryNameMatch(tokens, start, len, index) {
    if (start + len > tokens.length) return null;
    var slice = [];
    for (var i = start; i < start + len; i++) {
      var t = tokens[i].replace(/,$/, "");
      if (!t) return null;
      slice.push(t);
    }
    var normed = normName(slice.join(" "));
    if (!normed || normed.length < 3) return null;

    // Direct lookup
    var hits = index.byName[normed];
    if (hits && hits.length > 0) return {hits: hits, normed: normed, form: "exact"};

    // Nickname variant
    var nick = nickVariant(normed);
    if (nick) {
      hits = index.byName[nick];
      if (hits && hits.length > 0) return {hits: hits, normed: nick, form: "nick"};
    }

    // Initial form: "D. Henry" -> "d henry"
    var init = initialForm(normed);
    if (init) {
      hits = index.byInitial[init];
      if (hits && hits.length > 0) return {hits: hits, normed: init, form: "initial"};
    }

    // Reversed: "Last, First" or "Last First" -> "First Last"
    if (len >= 2) {
      var reversed = slice.slice();
      reversed[0] = reversed[0].replace(/,$/, "");
      reversed = [reversed[reversed.length - 1]].concat(reversed.slice(0, reversed.length - 1));
      var revNormed = normName(reversed.join(" "));
      if (revNormed && revNormed !== normed) {
        hits = index.byName[revNormed];
        if (hits && hits.length > 0) return {hits: hits, normed: revNormed, form: "reversed"};
        nick = nickVariant(revNormed);
        if (nick) {
          hits = index.byName[nick];
          if (hits && hits.length > 0) return {hits: hits, normed: nick, form: "reversed-nick"};
        }
      }
    }

    return null;
  }

  // Disambiguate when multiple players share a normalized name.
  function disambiguate(hits, posHint, teamHint) {
    var filtered = hits;
    if (filtered.length > 1 && teamHint) {
      var byTeam = filtered.filter(function (h) { return h.team === teamHint; });
      if (byTeam.length > 0) filtered = byTeam;
    }
    if (filtered.length > 1 && posHint) {
      var byPos = filtered.filter(function (h) { return h.pos === posHint; });
      if (byPos.length > 0) filtered = byPos;
    }
    return filtered.length === 1 ? filtered[0] : null;
  }

  // Defence matching: check if tokens contain a city, mascot, "City Mascot", or a direct
  // "Team Name" match (e.g. "Dallas Cowboys" in the index).
  function tryDefenceOnLine(tokens, index, seen) {
    // Helper: look up a defence by name forms and return the entry if unique and unseen.
    function tryDef(raw) {
      var names = dstSearchNames(raw);
      for (var d = 0; d < names.length; d++) {
        var hits = index.byName[normName(names[d])];
        if (hits) {
          var def = hits.filter(function (h) { return h.pos === "DEF"; });
          if (def.length === 1 && !seen[String(def[0].row.player_key)]) return def[0];
        }
      }
      // Also try the raw form directly (e.g. "Dallas Cowboys" as-is in the index)
      var direct = index.byName[normName(raw)];
      if (direct) {
        var dd = direct.filter(function (h) { return h.pos === "DEF"; });
        if (dd.length === 1 && !seen[String(dd[0].row.player_key)]) return dd[0];
      }
      return null;
    }

    for (var i = 0; i < tokens.length; i++) {
      var lower = tokens[i].toLowerCase().replace(/[^a-z]/g, "");
      // Single-word mascot (e.g. "Cowboys") or single-word city (e.g. "Dallas")
      if (MASCOT_TO_CITY[lower] || CITY_TO_MASCOT[lower]) {
        var r = tryDef(tokens[i]);
        if (r) return r;
        // Also try combining with next token: "Dallas Cowboys", "Dallas D/ST"
        if (i + 1 < tokens.length) {
          r = tryDef(tokens[i] + " " + tokens[i + 1]);
          if (r) return r;
        }
      }
      // Two-word city (e.g. "Green Bay", "Kansas City", "New York")
      if (i + 1 < tokens.length) {
        var twoWord = tokens[i].toLowerCase().replace(/[^a-z]/g, "") + " " + tokens[i + 1].toLowerCase().replace(/[^a-z]/g, "");
        if (CITY_TO_MASCOT[twoWord]) {
          var r2 = tryDef(tokens[i] + " " + tokens[i + 1]);
          if (r2) return r2;
          // With mascot: "Kansas City Chiefs"
          if (i + 2 < tokens.length) {
            r2 = tryDef(tokens[i] + " " + tokens[i + 1] + " " + tokens[i + 2]);
            if (r2) return r2;
          }
        }
      }
    }
    return null;
  }

  // The main extraction function. Scans each line for player names using n-gram matching.
  // Returns {players, unmatched, matched, total, ignoredLines, mode:'extract'}.
  function extractPlayers(text, playerIndex) {
    if (!text || typeof text !== "string" || !text.trim()) {
      return {players: [], unmatched: [], matched: 0, total: 0, ignoredLines: [], mode: "extract"};
    }
    if (!playerIndex || !Array.isArray(playerIndex) || playerIndex.length === 0) {
      return {players: [], unmatched: [], matched: 0, total: 0, ignoredLines: [], mode: "extract"};
    }

    var index = buildIndex(playerIndex);
    var firstWords = buildFirstWords(index);
    var rawLines = text.split(/\r?\n/);
    var seen = {};
    var players = [];
    var unmatched = [];
    var ignoredLines = [];

    for (var lineIdx = 0; lineIdx < rawLines.length; lineIdx++) {
      var line = rawLines[lineIdx];
      var trimmed = line.trim();
      if (!trimmed) continue;

      // Clean Yahoo-style glued text and ESPN doubled names
      var cleaned = cleanYahooName(trimmed);
      cleaned = cleanESPNDoubled(cleaned);

      var tokens = extractTokens(cleaned);
      if (tokens.length === 0) continue;

      var hints = lineHints(tokens);
      var foundOnLine = [];
      var consumed = {};

      // D/ST or DEF lines
      if (hints.posHint === "DEF" || /\bD\/?ST\b/i.test(trimmed)) {
        var defEntry = tryDefenceOnLine(tokens, index, seen);
        if (defEntry) {
          seen[String(defEntry.row.player_key)] = true;
          foundOnLine.push({id: String(defEntry.row.player_key), name: defEntry.row.name, confidence: 1, sourceLine: trimmed, slot: ""});
        } else {
          unmatched.push({line: trimmed, reason: "defence not matched", pos: "DEF", team: hints.teamHint || ""});
        }
      }

      // Kicker lines
      if (hints.posHint === "K" && foundOnLine.length === 0) {
        // Try whole line and token combos as a kicker name
        var kMatched = false;
        for (var kw = Math.min(4, tokens.length); kw >= 2; kw--) {
          for (var ks = 0; ks + kw <= tokens.length; ks++) {
            var km = tryNameMatch(tokens, ks, kw, index);
            if (km) {
              var kEntry = km.hits.filter(function (h) { return h.pos === "K"; });
              if (kEntry.length === 1 && !seen[String(kEntry[0].row.player_key)]) {
                seen[String(kEntry[0].row.player_key)] = true;
                foundOnLine.push({id: String(kEntry[0].row.player_key), name: kEntry[0].row.name, confidence: 1, sourceLine: trimmed, slot: ""});
                kMatched = true;
                break;
              }
            }
          }
          if (kMatched) break;
        }
        if (!kMatched) {
          unmatched.push({line: trimmed, reason: "kicker not matched", pos: "K", team: hints.teamHint || ""});
        }
      }

      // N-gram scan for player names: try windows of 4, 3, 2 words (prefer longer matches).
      if (foundOnLine.length === 0 && hints.posHint !== "DEF" && hints.posHint !== "K") {
        for (var winLen = 4; winLen >= 2; winLen--) {
          for (var start = 0; start + winLen <= tokens.length; start++) {
            var overlap = false;
            for (var c = start; c < start + winLen; c++) {
              if (consumed[c]) { overlap = true; break; }
            }
            if (overlap) continue;

            // Quick rejection: first or last token must contain a known player-name word
            // normName may produce multi-word results (e.g. "Amon-Ra" -> "amon ra"),
            // so check each word of the normalized form, not just the whole string.
            var fn = normName(tokens[start].replace(/,$/, ""));
            var ln = normName(tokens[start + winLen - 1]);
            var fnHit = false, lnHit = false;
            if (fn) { var fnParts = fn.split(" "); for (var fp = 0; fp < fnParts.length; fp++) { if (firstWords[fnParts[fp]]) { fnHit = true; break; } } }
            if (ln) { var lnParts = ln.split(" "); for (var lp = 0; lp < lnParts.length; lp++) { if (firstWords[lnParts[lp]]) { lnHit = true; break; } } }
            if (!fnHit && !lnHit) continue;

            var match = tryNameMatch(tokens, start, winLen, index);
            if (!match) continue;

            var entry = disambiguate(match.hits, hints.posHint, hints.teamHint);
            if (!entry) {
              if (match.hits.length > 1) {
                // Only report ambiguous once per line
                var already = unmatched.some(function (u) { return u.line === trimmed && u.reason.indexOf("ambiguous") === 0; });
                if (!already) {
                  unmatched.push({line: trimmed, reason: "ambiguous: " + match.hits.map(function(h) { return h.row.name + " " + h.pos + " " + h.team; }).join(" / "),
                    pos: hints.posHint || "", team: hints.teamHint || ""});
                }
              }
              continue;
            }

            var key = String(entry.row.player_key);
            if (seen[key]) {
              for (var mc = start; mc < start + winLen; mc++) consumed[mc] = true;
              continue;
            }
            seen[key] = true;

            var confidence = 1.0;
            if (match.form !== "exact") {
              confidence = (hints.teamHint && entry.team === hints.teamHint) || (hints.posHint && entry.pos === hints.posHint) ? 0.9 : 0.8;
            }

            foundOnLine.push({id: String(entry.row.player_key), name: entry.row.name, confidence: confidence,
              sourceLine: trimmed, slot: ""});
            for (var mc2 = start; mc2 < start + winLen; mc2++) consumed[mc2] = true;
          }
        }
      }

      if (foundOnLine.length > 0) {
        for (var fi = 0; fi < foundOnLine.length; fi++) players.push(foundOnLine[fi]);
      } else {
        // Track non-empty non-noise lines that had no match
        var hasAlpha = /[a-zA-Z]{2,}/.test(trimmed);
        var isShort = trimmed.length < 120;
        var looksNav = /^(home|teams?|players?|matchups?|standings|transactions|settings|news|fantasy|football|copyright|menu|search|filter|sort|draft|overview|research|page \d|waivers?|add player|drop player|injury report|bye week|show bench|stat\w*|espn|yahoo|sleeper|fantrax|cbs|mfl|nfl|fanduel|draftkings|underdogs?|network|plus|video forecast|player note)s?$/i.test(trimmed);
        if (hasAlpha && isShort && !looksNav) {
          ignoredLines.push(trimmed);
        }
      }
    }

    return {
      players: players,
      unmatched: unmatched,
      matched: players.length,
      total: players.length + unmatched.length,
      ignoredLines: ignoredLines,
      mode: "extract",
    };
  }

  // =========================================================================
  //  WHOLE LEAGUE PAGE (ESPN "League Rosters", Yahoo league rosters, Sleeper, any site)
  // =========================================================================
  // A whole-league paste is cut into one block per team, then each block is read by the source-agnostic extractor.
  // Team blocks start at a team header:
  //   1. "Team Name (5-1-0)" or "Team Name" followed by a "(5-1-0)" / "5-2" line (ESPN, Sleeper, most sites);
  //   2. otherwise a roster table header ("SLOT", "Pos", "Starters") with the team name the nearest plain line above it.
  // A block with no players is dropped (standings and nav lists), and a block of one or two players folds into the one
  // before it (Yahoo's separate Kickers and Defense tables). Never invents a team: fewer than two teams is "no league".
  var RECORD_INLINE_RE = /^(.{2,80}?)\s*\(\s*\d{1,2}\s*-\s*\d{1,2}(?:\s*-\s*\d{1,2})?\s*\)\s*$/;
  var RECORD_ALONE_RE = /^\(?\s*\d{1,2}\s*-\s*\d{1,2}(?:\s*-\s*\d{1,2})?\s*\)?$/;
  var TABLE_MARKER_RE = /^(SLOT|Pos|Position|Starters)(\s|$)/i;
  // Only ESPN's actual section header is noise: a team is allowed to start with "Bye Week" (JEG-1110).
  var TEAM_NAME_NOISE_RE = /^(offense|kickers?|defen[cs]e.*|starters|bench|reserve|taxi|ir|empty|view team|propose trade|trade|rosters?|league rosters|edit|player|acq|slot|pos|position|status|action|opp|proj|score|manager|owner|record|w-l-t|free agency|draft|waivers?|keeper|my team|league|players|scoreboard|standings|fantasycast|get another team|opposing teams|\(?\d+(st|nd|rd|th) of \d+\)?|[\d.,%+\-\s]+|(mon|tue|wed|thu|fri|sat|sun)\b.*|.*\b\d{1,2}:\d{2}\b.*|bye(?:\s+weeks?(?:\s+players)?)?)$/i;

  function cleanTeamName(raw) {
    var s = cleanESPNDoubled(String(raw || "").replace(/\t+/g, " ").replace(/\s+/g, " ").trim());
    return s.replace(/\s*\.\.\.$|…$/, "").trim();
  }
  function lineIsPlayer(line, index) {
    var c = cleanESPNDoubled(cleanYahooName(String(line || "").trim()));
    if (!c) return false;
    if (/\bD\/?ST\b/i.test(c)) return true;
    var n = normName(c);
    return !!(n && index.byName[n]);
  }
  function plausibleTeamName(line, index) {
    var t = cleanTeamName(line);
    if (t.length < 2 || t.length > 60) return false;
    if (!/[A-Za-z]/.test(t) || /\t/.test(line)) return false;
    if (t.charAt(0) === "@") return false;
    if (TEAM_NAME_NOISE_RE.test(t) || isSlotLabel(t)) return false;
    return !lineIsPlayer(t, index);
  }

  function recordHeaders(lines, index) {
    var heads = [];
    for (var i = 0; i < lines.length; i++) {
      var t = lines[i].trim();
      if (!t) continue;
      var m = t.match(RECORD_INLINE_RE);
      if (m && plausibleTeamName(m[1], index)) { heads.push({line: i, name: cleanTeamName(m[1])}); continue; }
      if (RECORD_ALONE_RE.test(t)) {
        // The name is the nearest plain line above (skipping a "@handle" or manager line on Sleeper).
        for (var j = i - 1, seenLines = 0; j >= 0 && seenLines < 3; j--) {
          var u = lines[j].trim();
          if (!u) continue;
          seenLines++;
          if (u.charAt(0) === "@") continue;
          if (plausibleTeamName(u, index)) { heads.push({line: j, name: cleanTeamName(u)}); break; }
        }
      }
    }
    return heads;
  }
  function markerHeaders(lines, index) {
    var heads = [];
    for (var i = 0; i < lines.length; i++) {
      if (!TABLE_MARKER_RE.test(lines[i].trim())) continue;
      var name = null;
      for (var j = i - 1, seenLines = 0; j >= 0 && seenLines < 10; j--) {
        var u = lines[j].trim();
        if (!u) continue;
        seenLines++;
        if (lineIsPlayer(u, index)) break;          // ran into the previous team's table
        if (plausibleTeamName(u, index)) { name = cleanTeamName(u); break; }
      }
      heads.push({line: i, name: name});
    }
    return heads;
  }

  // Kickers and defenses are not in the engine's player list, so the extractor can miss a bare "Jason Myers" or "Jets"
  // line. They are caught by the position line next to them ("SEA K", "Sea - K", "K - SEA", "DEF", "Nyj - DEF") and
  // kept as not evaluated, like the team-page parsers do.
  var K_RE = /^(?:([A-Za-z]{2,4})\s*(?:[-–]\s*)?K|K\s*[-–]\s*([A-Za-z]{2,4}))$/;
  var DEF_RE = /^(?:([A-Za-z]{2,4})\s*(?:[-–]\s*)?(?:DEF|D\/ST|DST)|(?:DEF|D\/ST|DST)(?:\s*[-–]\s*([A-Za-z]{2,4}))?)$/i;
  // A position line: a bare "K"/"DEF", or one with a real NFL team code ("SEA K", "Nyj - DEF"), never "Jets D/ST".
  function posLine(re, line) {
    var m = String(line || "").match(re);
    if (!m) return null;
    var code = m[1] || m[2];
    if (code && !normTeam(code)) return null;
    return {team: code ? normTeam(code) : ""};
  }
  var K_LINE_RE = {test: function (l) { return !!posLine(K_RE, l); }};
  var DEF_LINE_RE = {test: function (l) { return !!posLine(DEF_RE, l); }};
  function blockNotEvaluated(blockLines, index) {
    var out = [];
    var lines = blockLines.map(function (l) { return cleanESPNDoubled(cleanYahooName(l.trim())); });
    for (var i = 0; i < lines.length; i++) {
      var km = posLine(K_RE, lines[i]);
      if (km && i > 0) {
        for (var j = i - 1; j >= 0 && j >= i - 2; j--) {
          var nm = lines[j];
          if (nm && /[a-z]/.test(nm) && !lineIsPlayer(nm, index) && !isSlotLabel(nm) && nm.split(/\s+/).length <= 4 && !TEAM_NAME_NOISE_RE.test(nm)) {
            out.push({line: nm, reason: "kicker not matched", pos: "K", team: km.team});
            break;
          }
        }
      }
      var mascot = lines[i].toLowerCase();
      if (MASCOT_TO_CITY[mascot]) {
        var near = false;
        for (var d = Math.max(0, i - 2); d <= Math.min(lines.length - 1, i + 2); d++) if (d !== i && DEF_LINE_RE.test(lines[d])) near = true;
        if (near) {
          var city = MASCOT_TO_CITY[mascot];
          out.push({line: lines[i], reason: "defence not matched", pos: "DEF", team: normTeam(city) || normTeam(city.split(" ").pop()) || ""});
        }
      }
    }
    return out;
  }

  function readBlocks(heads, lines, playerRows, index) {
    var teams = [];
    for (var h = 0; h < heads.length; h++) {
      var from = heads[h].line + 1;
      var to = h + 1 < heads.length ? heads[h + 1].line : lines.length;
      var blockLines = lines.slice(from, to);
      var ex = extractPlayers(blockLines.join("\n"), playerRows);
      // The extractor also flags slot and position lines ("D/ST", "SEA K") as unmatched kickers and defenses: drop those,
      // undo ESPN's doubled names, and keep one entry per kicker or defense.
      var keyOf = function (u) { return u.pos + ":" + normName(String(u.line).replace(/\s*D\/?ST$/i, "")); };
      var have = {};
      var unmatched = ex.unmatched.concat(blockNotEvaluated(blockLines, index)).map(function (u) {
        return u.pos === "K" || u.pos === "DEF" ? {line: cleanESPNDoubled(cleanYahooName(String(u.line).trim())), reason: u.reason, pos: u.pos, team: u.team} : u;
      }).filter(function (u) {
        if (u.pos !== "K" && u.pos !== "DEF") return true;
        if (isSlotLabel(u.line) || K_LINE_RE.test(u.line) || DEF_LINE_RE.test(u.line) || !/[a-z]/.test(u.line)) return false;
        var k = keyOf(u);
        if (have[k]) return false;
        have[k] = true;
        return true;
      });
      teams.push({teamName: heads[h].name, players: ex.players, unmatched: unmatched});
    }
    return teams;
  }
  function finishTeams(teams, foldSmall) {
    var out = [];
    teams.forEach(function (t) {
      var prev = out[out.length - 1];
      if (foldSmall && prev && t.players.length < 3) {
        prev.players = prev.players.concat(t.players);
        prev.unmatched = prev.unmatched.concat(t.unmatched);
        return;
      }
      if (!t.players.length) return;
      out.push({teamName: t.teamName, players: t.players.slice(), unmatched: t.unmatched.slice()});
    });
    // The same team twice (a nav list or a standings table with players): keep the fuller one.
    var byName = {};
    var result = [];
    out.forEach(function (t, i) {
      if (!t.teamName) t.teamName = "Team " + (i + 1);
      var key = t.teamName.toLowerCase();
      if (byName[key] !== undefined) {
        if (t.players.length > result[byName[key]].players.length) result[byName[key]] = t;
        return;
      }
      byName[key] = result.length;
      result.push(t);
    });
    // A player can only be on one roster: the first team that lists them keeps them.
    var taken = {};
    result.forEach(function (t) {
      t.players = t.players.filter(function (p) { if (taken[p.id]) return false; taken[p.id] = true; return true; });
      t.matched = t.players.length;
      t.total = t.players.length + t.unmatched.length;
    });
    return result;
  }

  function parseLeague(text, playerRows) {
    var out = {site: "unknown", teams: [], sleeperLeagueId: null, espnLeagueId: null};
    if (!text || typeof text !== "string" || !text.trim()) return out;
    out.site = /sleeper\.(com|app)|^\s*Sleeper\s*$/im.test(text) ? "sleeper" : detectSite(text);
    var sl = text.match(/sleeper\.(?:com|app)\/leagues\/(\d{6,})/i);
    if (sl) out.sleeperLeagueId = sl[1];
    var es = text.match(/espn\.com\/football\/\S*?[?&]leagueId=(\d+)/i);
    if (es) out.espnLeagueId = es[1];
    if (!playerRows || !Array.isArray(playerRows) || !playerRows.length) return out;
    var index = buildIndex(playerRows);
    var lines = text.split(/\r?\n/);
    var teams = finishTeams(readBlocks(recordHeaders(lines, index), lines, playerRows, index), false);
    if (teams.length < 2) {
      var byMarker = finishTeams(readBlocks(markerHeaders(lines, index), lines, playerRows, index), true);
      if (byMarker.length > teams.length) teams = byMarker;
    }
    out.teams = teams.length >= 2 ? teams : [];
    return out;
  }

  function hasBNLine(lines) {
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim() === "BN") return true;
    }
    return false;
  }

  // Expose for testing and for window.DDFRosterPaste
  var api = {
    parse: parse, detectListKind: detectListKind, extractPlayers: extractPlayers, parseLeague: parseLeague,
    normName: normName, normTeam: normTeam, buildIndex: buildIndex, matchCandidate: matchCandidate,
    cleanYahooName: cleanYahooName, cleanESPNDoubled: cleanESPNDoubled,
    detectSite: detectSite, isMatchupPage: isMatchupPage,
    parseTeamPosYahoo: parseTeamPosYahoo,
    parsePlayerListPage: parsePlayerListPage, parseYahooTeamPage: parseYahooTeamPage, parseYahooMatchupPage: parseYahooMatchupPage,
    parseESPNTeamPage: parseESPNTeamPage, parseESPNMatchupPage: parseESPNMatchupPage,
    extractTokens: extractTokens, tryNameMatch: tryNameMatch, disambiguate: disambiguate,
    lineHints: lineHints, buildFirstWords: buildFirstWords, tryDefenceOnLine: tryDefenceOnLine,
    dstSearchNames: dstSearchNames, isSlotLabel: isSlotLabel, hasBNLine: hasBNLine,
    NICK_MAP: NICK_MAP, CITY_TO_MASCOT: CITY_TO_MASCOT, MASCOT_TO_CITY: MASCOT_TO_CITY,
  };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFRosterPaste = api;

})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
