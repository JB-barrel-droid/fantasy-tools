// test_v2_roster_paste.js — Node test suite for app/v2/roster-paste.js (JEG-853).
// Run: node tests/test_v2_roster_paste.js
// Fixtures in tests/fixtures/roster_paste/ are scrubbed real page pastes.
// To add a new real sample: paste the raw Ctrl+A text, scrub personal info
// (owner, team, league names/IDs), save to the fixtures dir, and add a test case.

"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
const P = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
const FIXTURE_DIR = path.join(ROOT, "tests", "fixtures", "roster_paste");

// --- shared player index (all players that appear across the four samples) ---
const PLAYERS = [
  // Yahoo team page players
  {player_key: "rodgers", name: "Aaron Rodgers", pos: "QB", team: "PIT"},
  {player_key: "b_robinson", name: "Bijan Robinson", pos: "RB", team: "ATL"},
  {player_key: "a_jones", name: "Aaron Jones Sr.", pos: "RB", team: "MIN"},
  {player_key: "jsn", name: "Jaxon Smith-Njigba", pos: "WR", team: "SEA"},
  {player_key: "mcmillan", name: "Tetairoa McMillan", pos: "WR", team: "CAR"},
  {player_key: "allen_k", name: "Keenan Allen", pos: "WR", team: "IND"},
  {player_key: "goedert", name: "Dallas Goedert", pos: "TE", team: "PHI"},
  {player_key: "miller_k", name: "Kendre Miller", pos: "RB", team: "NO"},
  {player_key: "allen_j", name: "Josh Allen", pos: "QB", team: "BUF"},
  {player_key: "odunze", name: "Rome Odunze", pos: "WR", team: "CHI"},
  {player_key: "samuel", name: "Deebo Samuel Sr.", pos: "WR", team: "SF"},
  {player_key: "perine", name: "Samaje Perine", pos: "RB", team: "CIN"},
  {player_key: "noel", name: "Jaylin Noel", pos: "WR", team: "HOU"},
  {player_key: "boswell", name: "Chris Boswell", pos: "K", team: "PIT"},
  {player_key: "chiefs", name: "Chiefs", pos: "DEF", team: "KC"},
  // Yahoo matchup opponent players
  {player_key: "burrow", name: "Joe Burrow", pos: "QB", team: "CIN"},
  {player_key: "jeanty", name: "Ashton Jeanty", pos: "RB", team: "LV"},
  {player_key: "love_j", name: "Jeremiyah Love", pos: "RB", team: "ARI"},
  {player_key: "watson_c", name: "Christian Watson", pos: "WR", team: "GB"},
  {player_key: "bernard", name: "Germie Bernard", pos: "WR", team: "PIT"},
  {player_key: "egbuka", name: "Emeka Egbuka", pos: "WR", team: "TB"},
  {player_key: "loveland", name: "Colston Loveland", pos: "TE", team: "CHI"},
  {player_key: "skattebo", name: "Cam Skattebo", pos: "RB", team: "NYG"},
  {player_key: "fitzgerald", name: "Ryan Fitzgerald", pos: "K", team: "CAR"},
  {player_key: "titans", name: "Titans", pos: "DEF", team: "TEN"},
  // ESPN team page players
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
  // ESPN matchup opponent players
  {player_key: "goff", name: "Jared Goff", pos: "QB", team: "DET"},
  {player_key: "swift", name: "D'Andre Swift", pos: "RB", team: "CHI"},
  {player_key: "pierce", name: "Dameon Pierce", pos: "RB", team: "PHI"},
  {player_key: "cooper_jr", name: "Omar Cooper Jr.", pos: "WR", team: "NYJ"},
  {player_key: "likely", name: "Isaiah Likely", pos: "TE", team: "NYG"},
  {player_key: "lane", name: "Ja'Kobi Lane", pos: "WR", team: "BAL"},
  {player_key: "browns", name: "Browns", pos: "DEF", team: "CLE"},
  {player_key: "shrader", name: "Spencer Shrader", pos: "K", team: "IND"},
  {player_key: "hampton", name: "Omarion Hampton", pos: "RB", team: "LAC"},
  {player_key: "moore_dj", name: "DJ Moore", pos: "WR", team: "BUF"},
  {player_key: "tyson", name: "Jordyn Tyson", pos: "WR", team: "NO"},
  // Trap-like players (names that appear in ESPN nav as team/manager names)
  {player_key: "beckham", name: "Odell Beckham Jr.", pos: "WR", team: "MIA"},
];

function readFixture(name) {
  return fs.readFileSync(path.join(FIXTURE_DIR, name), "utf8");
}

function ids(result) {
  return result.players.map(function (p) { return p.id; }).sort();
}

let passed = 0;
let failed = 0;

function test(label, fn) {
  try {
    fn();
    passed++;
    process.stdout.write("  PASS: " + label + "\n");
  } catch (e) {
    failed++;
    process.stderr.write("  FAIL: " + label + "\n    " + e.message + "\n");
  }
}

// ===========================================================================
//  Unit tests: normName, normTeam, cleanYahooName
// ===========================================================================
console.log("--- Unit tests ---");

test("normName strips accents punctuation and suffixes", function () {
  assert.strictEqual(P.normName("Ja'Kobi Lane"), "jakobi lane");
  assert.strictEqual(P.normName("D'Andre Swift"), "dandre swift");
  assert.strictEqual(P.normName("Aaron Jones Sr."), "aaron jones");
  assert.strictEqual(P.normName("Luther Burden III"), "luther burden");
  assert.strictEqual(P.normName("Omar Cooper Jr."), "omar cooper");
});

test("normTeam resolves aliases", function () {
  assert.strictEqual(P.normTeam("Pit"), "PIT");
  assert.strictEqual(P.normTeam("KC"), "KC");
  assert.strictEqual(P.normTeam("NO"), "NO");
  assert.strictEqual(P.normTeam("gb"), "GB");
  assert.strictEqual(P.normTeam("jax"), "JAC");
  assert.strictEqual(P.normTeam("wsh"), "WAS");
  assert.strictEqual(P.normTeam("nonsense"), null);
});

test("cleanYahooName strips glued UI text", function () {
  assert.strictEqual(P.cleanYahooName("Aaron RodgersPlayer Note"), "Aaron Rodgers");
  assert.strictEqual(P.cleanYahooName("Bijan RobinsonVideo ForecastPlayer Note"), "Bijan Robinson");
  assert.strictEqual(P.cleanYahooName("Aaron Jones Sr.Video ForecastNo new player Notes"), "Aaron Jones Sr.");
  assert.strictEqual(P.cleanYahooName("ChiefsNo new player Notes"), "Chiefs");
});

test("cleanYahooName strips glued injury tags", function () {
  assert.strictEqual(P.cleanYahooName("Deebo Samuel Sr.OVideo ForecastNew Player Note"), "Deebo Samuel Sr.");
  assert.strictEqual(P.cleanYahooName("Jeremiyah LoveQVideo ForecastNew Player Note"), "Jeremiyah Love");
  assert.strictEqual(P.cleanYahooName("Christian WatsonQNew Player Note"), "Christian Watson");
  assert.strictEqual(P.cleanYahooName("Emeka EgbukaQVideo ForecastNew Player Note"), "Emeka Egbuka");
});

test("cleanESPNDoubled undoubles names", function () {
  assert.strictEqual(P.cleanESPNDoubled("Jordan LoveJordan Love"), "Jordan Love");
  assert.strictEqual(P.cleanESPNDoubled("Broncos D/STBroncos D/ST"), "Broncos D/ST");
  assert.strictEqual(P.cleanESPNDoubled("Aaron Jones Sr.Aaron Jones Sr."), "Aaron Jones Sr.");
  assert.strictEqual(P.cleanESPNDoubled("Tee Higgins"), "Tee Higgins");
});

test("detectSite identifies Yahoo", function () {
  assert.strictEqual(P.detectSite("Yahoo Sports LLC blah"), "yahoo");
  assert.strictEqual(P.detectSite("Yahoo Sports Fantasy Football"), "yahoo");
});

test("detectSite identifies ESPN", function () {
  assert.strictEqual(P.detectSite("ESPN Enterprises, LLC."), "espn");
  assert.strictEqual(P.detectSite("ESPN Fantasy Football"), "espn");
});

test("detectSite returns unknown for garbage", function () {
  assert.strictEqual(P.detectSite("random text"), "unknown");
});

test("isMatchupPage detects Yahoo matchup", function () {
  assert.ok(P.isMatchupPage("Compare Managers ... Players Remaining 10"));
});

test("isMatchupPage detects ESPN matchup", function () {
  assert.ok(P.isMatchupPage("Box Score ... TOTALS ... COMPARISON"));
});

test("parseTeamPosYahoo parses Yahoo format", function () {
  var tp = P.parseTeamPosYahoo("Pit - QB");
  assert.strictEqual(tp.team, "PIT");
  assert.strictEqual(tp.pos, "QB");
  var tp2 = P.parseTeamPosYahoo("KC - DEF");
  assert.strictEqual(tp2.team, "KC");
  assert.strictEqual(tp2.pos, "DEF");
  assert.strictEqual(P.parseTeamPosYahoo("Some random text"), null);
});

test("dstSearchNames generates mascot and city forms", function () {
  var names = P.dstSearchNames("Chiefs");
  assert.ok(names.indexOf("Chiefs") >= 0);
  assert.ok(names.some(function (n) { return n.toLowerCase().indexOf("kansas city") >= 0; }));
});

test("nickname matching works", function () {
  var rows = [{player_key: "gabe_d", name: "Gabriel Davis", pos: "WR", team: "JAC"}];
  var index = P.buildIndex(rows);
  var seen = {};
  var result = P.matchCandidate({name: "Gabe Davis", posHint: "WR", teamHint: "JAC", isDST: false}, index, seen);
  assert.ok(result.match);
  assert.strictEqual(result.match.player_key, "gabe_d");
  assert.strictEqual(result.confidence, 0.9);
});

test("initial form matching works", function () {
  var rows = [{player_key: "d_henry", name: "Derrick Henry", pos: "RB", team: "BAL"}];
  var index = P.buildIndex(rows);
  var seen = {};
  var result = P.matchCandidate({name: "D. Henry", posHint: "RB", teamHint: "BAL", isDST: false}, index, seen);
  assert.ok(result.match);
  assert.strictEqual(result.match.player_key, "d_henry");
  assert.strictEqual(result.confidence, 0.8);
});

test("disambiguation by team works", function () {
  var rows = [
    {player_key: "allen_j", name: "Josh Allen", pos: "QB", team: "BUF"},
    {player_key: "allen_b", name: "Josh Allen", pos: "DE", team: "JAC"},
  ];
  var index = P.buildIndex(rows);
  var seen = {};
  var result = P.matchCandidate({name: "Josh Allen", posHint: "QB", teamHint: "BUF", isDST: false}, index, seen);
  assert.ok(result.match);
  assert.strictEqual(result.match.player_key, "allen_j");
});

test("ambiguous name with no team/pos hint does not match", function () {
  var rows = [
    {player_key: "allen_j", name: "Josh Allen", pos: "QB", team: "BUF"},
    {player_key: "allen_b", name: "Josh Allen", pos: "DE", team: "JAC"},
  ];
  var index = P.buildIndex(rows);
  var seen = {};
  var result = P.matchCandidate({name: "Josh Allen", posHint: null, teamHint: null, isDST: false}, index, seen);
  assert.strictEqual(result.match, null);
});

test("duplicate player is not matched twice", function () {
  var rows = [{player_key: "boswell", name: "Chris Boswell", pos: "K", team: "PIT"}];
  var index = P.buildIndex(rows);
  var seen = {};
  var r1 = P.matchCandidate({name: "Chris Boswell", posHint: "K", teamHint: "PIT", isDST: false}, index, seen);
  assert.ok(r1.match);
  var r2 = P.matchCandidate({name: "Chris Boswell", posHint: "K", teamHint: "PIT", isDST: false}, index, seen);
  assert.strictEqual(r2.match, null);
  assert.strictEqual(r2.reason, "duplicate");
});

// ===========================================================================
//  Integration: real fixture tests
// ===========================================================================
console.log("\n--- Real fixture tests ---");

test("Yahoo team page: 15/15 matched", function () {
  var text = readFixture("yahoo-team.txt");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "yahoo");
  assert.strictEqual(result.mode, "team");
  assert.strictEqual(result.matched, 15);
  assert.strictEqual(result.unmatched.length, 0);
  // Check specific players
  var foundIds = ids(result);
  assert.ok(foundIds.indexOf("rodgers") >= 0, "Aaron Rodgers");
  assert.ok(foundIds.indexOf("chiefs") >= 0, "Chiefs DEF");
  assert.ok(foundIds.indexOf("samuel") >= 0, "Deebo Samuel Sr.");
  assert.ok(foundIds.indexOf("allen_j") >= 0, "Josh Allen (QB)");
});

test("Yahoo matchup page: 20/20 matched, two teams of 10", function () {
  var text = readFixture("yahoo-matchup.txt");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "yahoo");
  assert.strictEqual(result.mode, "matchup");
  assert.strictEqual(result.matched, 20);
  assert.strictEqual(result.unmatched.length, 0);
  assert.strictEqual(result.teams.length, 2);
  assert.strictEqual(result.teams[0].matched, 10);
  assert.strictEqual(result.teams[1].matched, 10);
  assert.strictEqual(result.benchIncluded, false, "bench is collapsed");
  assert.strictEqual(result.teams[0].teamName, "My Test Team", "left team name from the logo line");
  assert.strictEqual(result.teams[1].teamName, "Opponent Team", "right team name from the logo line");
});

test("ESPN team page: 15/15 matched", function () {
  var text = readFixture("espn-team.txt");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "espn");
  assert.strictEqual(result.mode, "team");
  assert.strictEqual(result.matched, 15);
  assert.strictEqual(result.unmatched.length, 0);
  var foundIds = ids(result);
  assert.ok(foundIds.indexOf("love_jo") >= 0, "Jordan Love");
  assert.ok(foundIds.indexOf("broncos") >= 0, "Broncos DEF");
  assert.ok(foundIds.indexOf("charbonnet") >= 0, "Zach Charbonnet (IR)");
  assert.ok(foundIds.indexOf("burden") >= 0, "Luther Burden III (Bench)");
});

test("ESPN matchup page: 22/22 matched, two teams", function () {
  var text = readFixture("espn-matchup.txt");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.site, "espn");
  assert.strictEqual(result.mode, "matchup");
  assert.strictEqual(result.matched, 22);
  assert.strictEqual(result.unmatched.length, 0);
  assert.strictEqual(result.teams.length, 2);
  // Team 0 = opponent (first block): 9 starters + 1 injury + 2 bye = 12
  assert.strictEqual(result.teams[0].matched, 12);
  // Team 1 = user (second block): 9 starters + 1 injury = 10
  assert.strictEqual(result.teams[1].matched, 10);
  assert.strictEqual(result.benchIncluded, false, "bench is collapsed");
});

test("ESPN matchup page: a team named 'Bye Week ...' keeps both teams and the real Bye Week Players section (JEG-1110)", function () {
  var text = readFixture("espn-matchup.txt").replace(/Team Zeta/g, "Bye Week Bandits");
  var result = P.parse(text, PLAYERS);
  assert.strictEqual(result.mode, "matchup");
  assert.strictEqual(result.matched, 22);
  assert.deepStrictEqual(result.teams.map(function (t) { return t.teamName; }), ["Bye Week Bandits", "My ESPN Team"]);
  assert.strictEqual(result.teams[0].matched, 12, "9 starters, 1 injury and the 2 bye players");
  assert.strictEqual(result.teams[1].matched, 10);
  assert.strictEqual(result.players.filter(function (p) { return p.slot === "Bye"; }).length, 2, "the Bye Week Players section still parses");
});

test("all confidence scores are 1.0 on real fixtures", function () {
  ["yahoo-team.txt", "yahoo-matchup.txt", "espn-team.txt", "espn-matchup.txt"].forEach(function (f) {
    var text = readFixture(f);
    var result = P.parse(text, PLAYERS);
    result.players.forEach(function (p) {
      assert.strictEqual(p.confidence, 1.0, f + ": " + p.name + " confidence should be 1.0");
    });
  });
});

// ===========================================================================
//  Negative tests
// ===========================================================================
console.log("\n--- Negative tests ---");

test("empty input returns empty result", function () {
  var result = P.parse("", PLAYERS);
  assert.strictEqual(result.matched, 0);
  assert.strictEqual(result.mode, "team");
});

test("null input returns empty result", function () {
  var result = P.parse(null, PLAYERS);
  assert.strictEqual(result.matched, 0);
});

test("empty player index returns unmatched", function () {
  var result = P.parse("some text", []);
  assert.strictEqual(result.matched, 0);
  assert.strictEqual(result.unmatched.length, 1);
  assert.ok(result.unmatched[0].reason.indexOf("no player list") >= 0);
});

test("garbage text matches zero players", function () {
  var garbage = "Lorem ipsum dolor sit amet\nconsectetur adipiscing elit\nsed do eiusmod tempor incididunt\n42\nhttps://example.com\n";
  var result = P.parse(garbage, PLAYERS);
  assert.strictEqual(result.matched, 0);
});

test("a pasted league-wide player list without structure matches zero", function () {
  // A list of just names with no team/pos evidence
  var freeAgents = "Patrick Mahomes\nTravis Kelce\nTyreek Hill\nDavante Adams\nJustin Jefferson\n";
  var result = P.parse(freeAgents, PLAYERS);
  assert.strictEqual(result.matched, 0, "no matches without structural team/pos evidence");
});

test("ESPN nav trap names produce zero matches", function () {
  // These are team/manager names from the ESPN nav that resemble player names.
  // They must NOT match because they lack slot-label + team + position evidence.
  var navText = [
    "ESPN Fantasy",
    "Hodl Beckham Jr (GORM)",    // resembles Odell Beckham Jr.
    "Bobby Gorman",
    "Team Theta (DALT)",        // scrubbed version of "Colston's Love(Is)land"
    "Manager H",
    "Aaron Oaks",               // first name of real NFL player
    "Manager D",
    "ESPN Enterprises, LLC. All rights reserved.",
  ].join("\n");
  var result = P.parse(navText, PLAYERS);
  assert.strictEqual(result.matched, 0, "nav trap names must not match");
});

test("promo/comparison block names do not double-count (Yahoo team)", function () {
  // The Yahoo team page has a promo block at the bottom listing players for comparison.
  // Those must not create extra matches beyond the roster table.
  var text = readFixture("yahoo-team.txt");
  var result = P.parse(text, PLAYERS);
  // Rome Odunze and Keenan Allen appear in the promo block too; should not be duplicated
  var odunzeCount = result.players.filter(function (p) { return p.id === "odunze"; }).length;
  assert.strictEqual(odunzeCount, 1, "Rome Odunze matched exactly once");
  var allenCount = result.players.filter(function (p) { return p.id === "allen_k"; }).length;
  assert.strictEqual(allenCount, 1, "Keenan Allen matched exactly once");
});

test("'Players Remaining' count is not a player", function () {
  var text = readFixture("yahoo-matchup.txt");
  var result = P.parse(text, PLAYERS);
  result.players.forEach(function (p) {
    assert.ok(!/Players Remaining/i.test(p.sourceLine), "source line should not be the count text");
  });
});

test("other site text returns unknown site", function () {
  var sleeper = "Sleeper Fantasy Football\nTeam roster\nPatrick Mahomes KC QB\n";
  var result = P.parse(sleeper, PLAYERS);
  assert.strictEqual(result.site, "unknown");
});

// ===========================================================================
//  Discrimination: broken parser variants must fail
// ===========================================================================
console.log("\n--- Discrimination tests ---");

test("removing team/pos requirement would cause false positives on ESPN nav", function () {
  // Simulate what would happen if the parser matched names from anywhere in the text
  // (no structural requirement). The real parser does not, so this just confirms the design.
  var text = readFixture("espn-team.txt");
  var result = P.parse(text, PLAYERS);
  // "Odell Beckham Jr." appears in trap name "Hodl Beckham Jr" -- must not match
  var beckhamMatch = result.players.filter(function (p) { return p.id === "beckham"; });
  assert.strictEqual(beckhamMatch.length, 0, "Odell Beckham Jr. must not match from nav text");
});

test("Yahoo team page fixture preserves structure across scrubbing", function () {
  // Verify the fixture has the expected structure markers
  var text = readFixture("yahoo-team.txt");
  assert.ok(text.indexOf("Pit - QB") >= 0, "team-pos lines present");
  assert.ok(text.indexOf("KC - DEF") >= 0, "DEF team-pos line present");
  assert.ok(/Yahoo Sports/i.test(text), "Yahoo marker present");
});

test("ESPN team page fixture preserves structure across scrubbing", function () {
  var text = readFixture("espn-team.txt");
  assert.ok(text.indexOf("STARTERS") >= 0, "STARTERS header present");
  assert.ok(text.indexOf("Bench") >= 0, "Bench section present");
  assert.ok(/ESPN/i.test(text), "ESPN marker present");
});

test("slot labels: each matched player carries the page's own slot (JEG-853 phase 2 shows starter/bench/IR)", function () {
  var yt = P.parse(readFixture("yahoo-team.txt"), PLAYERS);
  var ySlots = yt.players.map(function (p) { return p.slot; });
  assert.strictEqual(ySlots.filter(function (s) { return s === "BN"; }).length, 5, "Yahoo team: 5 bench");
  assert.ok(ySlots.indexOf("QB") >= 0 && ySlots.indexOf("W/R/T") >= 0, "Yahoo team: starter slots kept as printed");
  var et = P.parse(readFixture("espn-team.txt"), PLAYERS);
  var eSlots = et.players.map(function (p) { return p.slot; });
  assert.strictEqual(eSlots.filter(function (s) { return s === "Bench"; }).length, 5, "ESPN team: 5 bench");
  assert.strictEqual(eSlots.filter(function (s) { return s === "IR"; }).length, 1, "ESPN team: 1 IR");
  var ym = P.parse(readFixture("yahoo-matchup.txt"), PLAYERS);
  ym.players.forEach(function (p) { assert.ok(p.slot && p.slot !== "BN", "Yahoo matchup: " + p.name + " has a starter slot, got " + JSON.stringify(p.slot)); });
  var em = P.parse(readFixture("espn-matchup.txt"), PLAYERS);
  var emSlots = em.players.map(function (p) { return p.slot; });
  assert.strictEqual(emSlots.filter(function (s) { return s === "Injured"; }).length, 2, "ESPN matchup: 2 injured");
  assert.strictEqual(emSlots.filter(function (s) { return s === "Bye"; }).length, 2, "ESPN matchup: 2 bye");
  assert.strictEqual(emSlots.filter(function (s) { return s === ""; }).length, 18, "ESPN matchup: 18 starters (no slot column)");
});

test("unmatched lines carry their position and team, so a kicker or defense can be kept (JEG-988)", function () {
  var want = {"yahoo-team.txt": ["K:PIT", "DEF:KC"], "espn-team.txt": ["DEF:DEN", "K:PIT"]};
  var priced = PLAYERS.filter(function (p) { return p.pos !== "K" && p.pos !== "DEF"; });   // the engine has no K or DEF row
  Object.keys(want).forEach(function (name) {
    var r = P.parse(readFixture(name), priced);
    var got = r.unmatched.filter(function (u) { return u.pos === "K" || u.pos === "DEF"; }).map(function (u) { return u.pos + ":" + u.team; }).sort();
    assert.deepStrictEqual(got, want[name].slice().sort(), name + ": kicker and defense lines keep pos and team");
  });
  var matchup = P.parse(readFixture("espn-matchup.txt"), priced);
  matchup.teams.forEach(function (t) {
    assert.ok(t.unmatched.some(function (u) { return u.pos === "K"; }), "matchup team keeps its kicker line");
    assert.ok(t.unmatched.some(function (u) { return u.pos === "DEF"; }), "matchup team keeps its defense line");
  });
});

// ===========================================================================
//  Free-agent (waiver) pages and which list a paste is (SYNTHETIC fixtures: no real paste yet)
// ===========================================================================
var WAIVER_DIR = path.join(ROOT, "tests", "fixtures", "waivers_paste");
var FA_IDS = ["noel", "perine", "miller_k", "goedert", "allen_k", "broncos", "boswell"];
["espn-free-agents-SYNTHETIC.txt", "yahoo-free-agents-SYNTHETIC.txt"].forEach(function (name) {
  test("free-agent page reads every row, no junk lines: " + name, function () {
    var r = P.parse(fs.readFileSync(path.join(WAIVER_DIR, name), "utf8"), PLAYERS);
    assert.strictEqual(r.mode, "list");
    assert.deepStrictEqual(r.players.map(function (p) { return p.id; }).sort(), FA_IDS.slice().sort());
    assert.strictEqual(r.unmatched.length, 0, "filter labels and headers are not listed as unmatched");
    assert.strictEqual(P.detectListKind(fs.readFileSync(path.join(WAIVER_DIR, name), "utf8"), r), "waivers");
  });
});

test("roster pages are detected as roster, matchups too", function () {
  ["yahoo-team.txt", "espn-team.txt", "yahoo-matchup.txt", "espn-matchup.txt"].forEach(function (name) {
    var text = readFixture(name);
    assert.strictEqual(P.detectListKind(text, P.parse(text, PLAYERS)), "roster", name);
  });
});

test("a bare list of names has no kind unless the text says which", function () {
  assert.strictEqual(P.detectListKind("Jaylin Noel\nSamaje Perine", {mode: "extract"}), "unknown");
  assert.strictEqual(P.detectListKind("Free Agents\nJaylin Noel\nSamaje Perine", {mode: "extract"}), "waivers");
  assert.strictEqual(P.detectListKind("Bench\nJaylin Noel\nSamaje Perine", {mode: "extract"}), "roster");
  assert.strictEqual(P.detectListKind("Free Agents\nBench\nJaylin Noel", {mode: "extract"}), "unknown");
});

// ===========================================================================
//  Summary
// ===========================================================================
console.log("\n--- Results: " + passed + " passed, " + failed + " failed ---");
process.exit(failed > 0 ? 1 : 0);
