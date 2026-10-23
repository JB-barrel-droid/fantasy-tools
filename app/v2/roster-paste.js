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
      return {
        site: site,
        players: et.players,
        unmatched: et.unmatched,
        matched: et.matched,
        total: et.total,
        mode: "team",
      };
    }

    // ---- Unknown: try both parsers, pick the one with more matches ----
    var tryYahoo = parseYahooTeamPage(rawLines, index);
    var tryEspn = parseESPNTeamPage(rawLines, index);
    var best = tryYahoo.matched >= tryEspn.matched ? tryYahoo : tryEspn;
    return {
      site: "unknown",
      players: best.players,
      unmatched: best.unmatched,
      matched: best.matched,
      total: best.total,
      mode: "team",
    };
  }

  function hasBNLine(lines) {
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim() === "BN") return true;
    }
    return false;
  }

  // Expose for testing and for window.DDFRosterPaste
  var api = {
    parse: parse,
    normName: normName, normTeam: normTeam, buildIndex: buildIndex, matchCandidate: matchCandidate,
    cleanYahooName: cleanYahooName, cleanESPNDoubled: cleanESPNDoubled,
    detectSite: detectSite, isMatchupPage: isMatchupPage,
    parseTeamPosYahoo: parseTeamPosYahoo,
    parseYahooTeamPage: parseYahooTeamPage, parseYahooMatchupPage: parseYahooMatchupPage,
    parseESPNTeamPage: parseESPNTeamPage, parseESPNMatchupPage: parseESPNMatchupPage,
    dstSearchNames: dstSearchNames, isSlotLabel: isSlotLabel, hasBNLine: hasBNLine,
    NICK_MAP: NICK_MAP, CITY_TO_MASCOT: CITY_TO_MASCOT, MASCOT_TO_CITY: MASCOT_TO_CITY,
  };
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.DDFRosterPaste = api;

})(typeof globalThis !== "undefined" ? globalThis : typeof self !== "undefined" ? self : this);
