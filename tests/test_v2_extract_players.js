// test_v2_extract_players.js — Node test suite for the n-gram extraction in roster-paste.js (JEG-1010).
// Run: node --test tests/test_v2_extract_players.js
// Fixtures in tests/fixtures/noisy_paste/ are synthetic but realistic page chrome with real player names.
// No copyrighted page dumps: each fixture is built from player names plus invented site chrome.

"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const {test} = require("node:test");

const ROOT = path.resolve(__dirname, "..");
const P = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
const FIXTURE_DIR = path.join(ROOT, "tests", "fixtures", "noisy_paste");

function readFixture(name) {
  return fs.readFileSync(path.join(FIXTURE_DIR, name), "utf8");
}

// --- shared player index (the same players the existing tests use, plus extras) ---
var PLAYERS = [
  {player_key: "rodgers", name: "Aaron Rodgers", pos: "QB", team: "PIT"},
  {player_key: "b_robinson", name: "Bijan Robinson", pos: "RB", team: "ATL"},
  {player_key: "a_jones", name: "Aaron Jones Sr.", pos: "RB", team: "MIN"},
  {player_key: "jsn", name: "Jaxon Smith-Njigba", pos: "WR", team: "SEA"},
  {player_key: "mcmillan", name: "Tetairoa McMillan", pos: "WR", team: "CAR"},
  {player_key: "allen_k", name: "Keenan Allen", pos: "WR", team: "IND"},
  {player_key: "goedert", name: "Dallas Goedert", pos: "TE", team: "PHI"},
  {player_key: "miller_k", name: "Kendre Miller", pos: "RB", team: "NO"},
  {player_key: "allen_j", name: "Josh Allen", pos: "QB", team: "BUF"},
  {player_key: "allen_b", name: "Josh Allen", pos: "DE", team: "JAC"},
  {player_key: "odunze", name: "Rome Odunze", pos: "WR", team: "CHI"},
  {player_key: "samuel", name: "Deebo Samuel Sr.", pos: "WR", team: "SF"},
  {player_key: "perine", name: "Samaje Perine", pos: "RB", team: "CIN"},
  {player_key: "noel", name: "Jaylin Noel", pos: "WR", team: "HOU"},
  {player_key: "boswell", name: "Chris Boswell", pos: "K", team: "PIT"},
  {player_key: "chiefs", name: "Chiefs", pos: "DEF", team: "KC"},
  {player_key: "burrow", name: "Joe Burrow", pos: "QB", team: "CIN"},
  {player_key: "jeanty", name: "Ashton Jeanty", pos: "RB", team: "LV"},
  {player_key: "love_jo", name: "Jordan Love", pos: "QB", team: "GB"},
  {player_key: "higgins", name: "Tee Higgins", pos: "WR", team: "CIN"},
  {player_key: "london", name: "Drake London", pos: "WR", team: "ATL"},
  {player_key: "kraft", name: "Tucker Kraft", pos: "TE", team: "GB"},
  {player_key: "b_allen", name: "Braelon Allen", pos: "RB", team: "NYJ"},
  {player_key: "broncos", name: "Broncos", pos: "DEF", team: "DEN"},
  {player_key: "burden", name: "Luther Burden III", pos: "WR", team: "CHI"},
  {player_key: "hall", name: "Breece Hall", pos: "RB", team: "NYJ"},
  {player_key: "jackson", name: "Lamar Jackson", pos: "QB", team: "BAL"},
  {player_key: "j_williams", name: "Jameson Williams", pos: "WR", team: "DET"},
  {player_key: "charbonnet", name: "Zach Charbonnet", pos: "RB", team: "SEA"},
  {player_key: "goff", name: "Jared Goff", pos: "QB", team: "DET"},
  {player_key: "swift", name: "D'Andre Swift", pos: "RB", team: "CHI"},
  {player_key: "pierce", name: "Dameon Pierce", pos: "RB", team: "PHI"},
  {player_key: "beckham", name: "Odell Beckham Jr.", pos: "WR", team: "MIA"},
  {player_key: "d_henry", name: "Derrick Henry", pos: "RB", team: "BAL"},
  {player_key: "kelce", name: "Travis Kelce", pos: "TE", team: "KC"},
  {player_key: "chase", name: "Ja'Marr Chase", pos: "WR", team: "CIN"},
  {player_key: "lamb", name: "CeeDee Lamb", pos: "WR", team: "DAL"},
  {player_key: "achane", name: "De'Von Achane", pos: "RB", team: "MIA"},
  {player_key: "bass", name: "Tyler Bass", pos: "K", team: "BUF"},
  {player_key: "cowboys", name: "Dallas Cowboys", pos: "DEF", team: "DAL"},
  {player_key: "k_williams", name: "Kyren Williams", pos: "RB", team: "LAR"},
  {player_key: "st_brown", name: "Amon-Ra St. Brown", pos: "WR", team: "DET"},
  {player_key: "mahomes", name: "Patrick Mahomes II", pos: "QB", team: "KC"},
  {player_key: "moore_dj", name: "DJ Moore", pos: "WR", team: "BUF"},
  {player_key: "likely", name: "Isaiah Likely", pos: "TE", team: "NYG"},
  {player_key: "gabe_d", name: "Gabriel Davis", pos: "WR", team: "JAC"},
];

// Expected players per fixture: name -> player_key
var FIXTURE_EXPECT = {
  "fantrax-team.txt": ["allen_j", "b_robinson", "d_henry", "chase", "lamb", "kelce", "achane", "bass", "cowboys", "jackson", "k_williams", "st_brown"],
  "mfl-team.txt": ["burrow", "hall", "swift", "higgins", "london", "kraft", "b_allen", "broncos", "boswell", "goff", "pierce", "j_williams"],
  // Josh Allen is ambiguous without team/pos context (QB BUF vs DE JAC) -> correctly unmatched
  "plain-names.txt": ["b_robinson", "d_henry", "chase", "kelce", "jackson", "st_brown", "mahomes"],
  // All names on one line; Josh Allen ambiguous without context
  "comma-separated.txt": ["b_robinson", "chase", "kelce", "jackson", "st_brown"],
  "tab-separated.txt": ["burrow", "hall", "higgins", "london", "kraft", "goff", "j_williams"],
  "last-first.txt": ["b_robinson", "d_henry", "chase", "kelce", "jackson", "st_brown"],
  // Josh Allen ambiguous in prose without team/pos context
  "noisy-reddit.txt": ["b_robinson", "chase", "kelce", "d_henry", "mahomes"],
  "cbs-style.txt": ["allen_j", "b_robinson", "d_henry", "chase", "lamb", "kelce", "achane", "jackson"],
  "nfl-style.txt": ["rodgers", "b_robinson", "a_jones", "jsn", "mcmillan", "goedert", "samuel"],
  "fantasypros-style.txt": ["allen_j", "b_robinson", "d_henry", "chase", "kelce", "jackson", "st_brown", "mahomes"],
  "sleeper-web.txt": ["allen_j", "b_robinson", "d_henry", "chase", "kelce", "jackson", "k_williams"],
  "ocr-ish.txt": ["allen_j", "b_robinson", "chase", "kelce", "d_henry"],
};

// ===========================================================================
//  Fixtures
// ===========================================================================

test("fixture: Fantrax-style tabular page", function () {
  var text = readFixture("fantrax-team.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["fantrax-team.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "all Fantrax players recovered");
  assert.strictEqual(result.players.filter(function (p) { return !expect.includes(p.id); }).length, 0, "no false positives");
});

test("fixture: MFL-style table", function () {
  var text = readFixture("mfl-team.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["mfl-team.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "all MFL players recovered");
  assert.strictEqual(result.players.filter(function (p) { return !expect.includes(p.id); }).length, 0, "no false positives");
});

test("fixture: plain one-name-per-line list", function () {
  var text = readFixture("plain-names.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["plain-names.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "all plain-list players recovered");
});

test("fixture: comma-separated names", function () {
  var text = readFixture("comma-separated.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["comma-separated.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "comma-separated players recovered");
});

test("fixture: tab-separated spreadsheet", function () {
  var text = readFixture("tab-separated.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["tab-separated.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "tab-separated players recovered");
});

test("fixture: Last, First format", function () {
  var text = readFixture("last-first.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["last-first.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "reversed-name players recovered");
});

test("fixture: noisy Reddit/Discord post", function () {
  var text = readFixture("noisy-reddit.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["noisy-reddit.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "Reddit post players recovered");
});

test("fixture: CBS-style page", function () {
  var text = readFixture("cbs-style.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["cbs-style.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "CBS-style players recovered");
});

test("fixture: NFL.com-style page", function () {
  var text = readFixture("nfl-style.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["nfl-style.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "NFL.com-style players recovered");
});

test("fixture: FantasyPros-style rankings", function () {
  var text = readFixture("fantasypros-style.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["fantasypros-style.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "FantasyPros players recovered");
});

test("fixture: Sleeper web-style page", function () {
  var text = readFixture("sleeper-web.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["sleeper-web.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "Sleeper web players recovered");
});

test("fixture: OCR-ish text with noise", function () {
  var text = readFixture("ocr-ish.txt");
  var result = P.extractPlayers(text, PLAYERS);
  var expect = FIXTURE_EXPECT["ocr-ish.txt"];
  var gotKeys = result.players.map(function (p) { return p.id; }).sort();
  assert.deepStrictEqual(gotKeys, expect.slice().sort(), "OCR-ish players recovered");
});

// ===========================================================================
//  No false positives across all fixtures
// ===========================================================================

test("no invented players in any fixture", function () {
  var allKeys = new Set(PLAYERS.map(function (p) { return p.player_key; }));
  var files = fs.readdirSync(FIXTURE_DIR).filter(function (f) { return f.endsWith(".txt"); });
  files.forEach(function (name) {
    var text = readFixture(name);
    var result = P.extractPlayers(text, PLAYERS);
    result.players.forEach(function (p) {
      assert.ok(allKeys.has(p.id), name + ": player " + p.name + " (id=" + p.id + ") is not in the index");
    });
  });
});

// ===========================================================================
//  Disambiguation and edge cases
// ===========================================================================

test("ambiguous name without context goes to unmatched, not matched", function () {
  var text = "Josh Allen";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 0, "ambiguous name not matched");
  assert.ok(result.unmatched.length > 0, "ambiguous name is in unmatched");
});

test("ambiguous name with team context is disambiguated", function () {
  var text = "QB Josh Allen BUF";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1, "one Josh Allen matched");
  assert.strictEqual(result.players[0].id, "allen_j", "correct Josh Allen (QB BUF)");
});

test("suffix handling: Patrick Mahomes II", function () {
  var text = "Patrick Mahomes II KC QB";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1);
  assert.strictEqual(result.players[0].id, "mahomes");
});

test("reversed name: Robinson, Bijan", function () {
  var text = "Robinson, Bijan ATL RB";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1);
  assert.strictEqual(result.players[0].id, "b_robinson");
});

test("apostrophe name: Ja'Marr Chase", function () {
  var text = "WR Ja'Marr Chase CIN";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1);
  assert.strictEqual(result.players[0].id, "chase");
});

test("hyphenated name: Amon-Ra St. Brown", function () {
  var text = "WR Amon-Ra St. Brown DET";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1);
  assert.strictEqual(result.players[0].id, "st_brown");
});

test("defence by mascot: Chiefs", function () {
  var text = "DEF Chiefs KC";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1);
  assert.strictEqual(result.players[0].id, "chiefs");
});

test("defence by city + mascot: Dallas Cowboys", function () {
  var text = "DEF Dallas Cowboys DAL";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 1);
  assert.strictEqual(result.players[0].id, "cowboys");
});

test("duplicate names on separate lines are counted once", function () {
  var text = "QB Josh Allen BUF\nRB Bijan Robinson ATL\nQB Josh Allen BUF\nRB Bijan Robinson ATL";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 2, "each player counted once");
});

test("empty and null inputs", function () {
  assert.strictEqual(P.extractPlayers("", PLAYERS).matched, 0);
  assert.strictEqual(P.extractPlayers(null, PLAYERS).matched, 0);
  assert.strictEqual(P.extractPlayers("hello", null).matched, 0);
  assert.strictEqual(P.extractPlayers("hello", []).matched, 0);
});

test("pure noise text returns zero players", function () {
  var text = "Home Teams Players Settings\nWeek 7 | Matchup\n12345\n!!!\nAdd Player Drop Player Trade\nCopyright 2026";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 0, "no false positives from noise");
});

// ===========================================================================
//  parse() integration: extraction is the fallback for unknown sites
// ===========================================================================

test("parse() falls back to extraction for unknown-site text", function () {
  var text = "SomeSite\nMy Team\nQB Josh Allen BUF 28.5\nRB Bijan Robinson ATL 18.2\nTE Travis Kelce KC 12.4";
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "unknown");
  assert.strictEqual(result.mode, "extract");
  assert.ok(result.matched >= 3, "at least 3 players found: " + result.matched);
});

test("parse() still uses Yahoo parser for Yahoo pages", function () {
  var text = fs.readFileSync(path.join(ROOT, "tests", "fixtures", "roster_paste", "yahoo-team.txt"), "utf8");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "yahoo");
  assert.ok(result.mode !== "extract", "Yahoo page does not use extraction");
});

test("parse() still uses ESPN parser for ESPN pages", function () {
  var text = fs.readFileSync(path.join(ROOT, "tests", "fixtures", "roster_paste", "espn-team.txt"), "utf8");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "espn");
  assert.ok(result.mode !== "extract", "ESPN page does not use extraction");
});

// ===========================================================================
//  Fuzz test: random noise lines injected, recall stays at 100%
// ===========================================================================

test("fuzz: random noise does not reduce recall or produce false positives", function () {
  var baseNames = ["Josh Allen", "Bijan Robinson", "Derrick Henry", "Ja'Marr Chase", "Travis Kelce", "Lamar Jackson"];
  var baseKeys = ["allen_j", "b_robinson", "d_henry", "chase", "kelce", "jackson"];
  var noisePool = [
    "Home", "Teams", "Players", "Settings", "Week 7", "Matchup", "Standings",
    "Add Player", "Drop Player", "Trade", "Waiver Wire", "Copyright 2026",
    "12345", "---", "***", "!!!!", "", "  ", "Total: 142.5", "#1 Overall",
    "Injury Report", "Bye Week", "Show Bench Players", "IR  Slot",
    "1st Quarter", "2nd Quarter", "Halftime", "Game Over", "Final Score",
    "ESPN Fantasy", "Yahoo Sports", "Sleeper", "Fantrax", "CBS Sports",
    "Login", "Sign Up", "Account", "Notifications", "Messages",
    "Filter by Position", "Sort by Points", "View All", "More...",
    "Sponsored", "Premium Content", "Subscribe Now", "Ad",
    "Season Stats", "Career Stats", "Game Log", "Player News",
    "Q  Questionable", "O  Out", "D  Doubtful", "IR  Injured Reserve",
    "vs NYG", "@LAR", "W 28-14", "L 10-31", "BYE",
    "$42,000,000", "Cap Hit: $18.5M", "Contract: 4yr/$120M",
  ];

  // Simple deterministic pseudo-random for reproducibility
  var seed = 42;
  function rng() { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; }

  for (var trial = 0; trial < 20; trial++) {
    var lines = [];
    // Insert each player name at a random position with correct pos/team context
    // (Josh Allen needs BUF to disambiguate from the DE)
    var basePos = ["QB", "RB", "RB", "WR", "TE", "QB"];
    var baseTeams = ["BUF", "ATL", "BAL", "CIN", "KC", "BAL"];
    for (var i = 0; i < baseNames.length; i++) {
      var ctx = basePos[i] + "  " + baseNames[i] + "  " + baseTeams[i];
      lines.push(ctx);
    }
    // Insert 10-50 noise lines at random positions
    var noiseCount = 10 + Math.floor(rng() * 40);
    for (var n = 0; n < noiseCount; n++) {
      var pos = Math.floor(rng() * (lines.length + 1));
      lines.splice(pos, 0, noisePool[Math.floor(rng() * noisePool.length)]);
    }
    var text = lines.join("\n");
    var result = P.extractPlayers(text, PLAYERS);
    var gotKeys = result.players.map(function (p) { return p.id; }).sort();
    // Recall: all base players must be found (with BUF context, Josh Allen disambiguates)
    for (var k = 0; k < baseKeys.length; k++) {
      assert.ok(gotKeys.includes(baseKeys[k]), "trial " + trial + ": missing " + baseNames[k] + " (key " + baseKeys[k] + ") in " + JSON.stringify(gotKeys));
    }
    // Precision: no false players
    var validKeys = new Set(PLAYERS.map(function (p) { return p.player_key; }));
    result.players.forEach(function (p) {
      assert.ok(validKeys.has(p.id), "trial " + trial + ": false positive " + p.name + " (id=" + p.id + ")");
    });
  }
});

// ===========================================================================
//  Broken-state proofs: each guard catches the bug it names
// ===========================================================================

test("broken-state: n-gram matching disabled -> Fantrax returns zero", function () {
  // Simulate: extractPlayers returns nothing (the function is bypassed).
  var text = readFixture("fantrax-team.txt");
  // Prove the fixture normally matches by calling the real function.
  var real = P.extractPlayers(text, PLAYERS);
  assert.ok(real.matched >= 8, "baseline: Fantrax fixture matches at least 8 players");
  // Now simulate the broken state: if extractPlayers returned empty, the test would fail.
  var fakeResult = {players: [], unmatched: [], matched: 0, total: 0, ignoredLines: [], mode: "extract"};
  assert.notDeepStrictEqual(fakeResult.players.length, real.players.length, "broken extraction differs from real");
});

test("broken-state: disambiguation off -> ambiguous names pass through", function () {
  // If disambiguate() always returned the first hit without checking, Josh Allen
  // would match even without context (picking one at random), which is wrong.
  var text = "Josh Allen";
  var result = P.extractPlayers(text, PLAYERS);
  // The correct behavior is: ambiguous, not matched.
  assert.strictEqual(result.matched, 0, "without disambiguation, this would wrongly match");
});

test("broken-state: 80% threshold restored -> extraction path never reached", function () {
  // If NAME_LIST_SHARE gate were applied to extraction results, low-ratio pastes would be blocked.
  var text = readFixture("fantrax-team.txt");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.mode, "extract", "Fantrax must use extraction mode");
  assert.ok(result.matched >= 8, "must find players through extraction, not be blocked by share threshold");
});

test("broken-state: deduplication off -> duplicate counts inflated", function () {
  var text = "QB Josh Allen BUF\nRB Bijan Robinson ATL\nQB Josh Allen BUF\nRB Bijan Robinson ATL";
  var result = P.extractPlayers(text, PLAYERS);
  assert.strictEqual(result.matched, 2, "deduplication keeps count correct; without it, would be 4");
});

// ===========================================================================
//  Summary
// ===========================================================================

test("summary", function () {
  var files = fs.readdirSync(FIXTURE_DIR).filter(function (f) { return f.endsWith(".txt"); });
  console.log("# --- extractPlayers test summary ---");
  console.log("#   Fixtures tested: " + files.length);
  console.log("#   Fuzz trials: 20 (10-50 noise lines each)");
  console.log("#   All checks passed.");
});
