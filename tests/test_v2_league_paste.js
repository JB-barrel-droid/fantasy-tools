// test_v2_league_paste.js — whole-league roster paste (ESPN, Yahoo, Sleeper) for the League tab.
// Run: node tests/test_v2_league_paste.js
// Fixtures in tests/fixtures/league_paste/: the ESPN rosters are a real league's (team names scrubbed); the Yahoo and
// Sleeper files lay the same rosters out the way those sites print a league's rosters.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
const P = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
const DIR = path.join(ROOT, "tests", "fixtures", "league_paste");
const TEAMS = JSON.parse(fs.readFileSync(path.join(DIR, "teams.json"), "utf8"));
const read = f => fs.readFileSync(path.join(DIR, f), "utf8");

// The engine's player list has no kickers or defenses (they are not evaluated), plus decoys that share a surname.
const ROWS = [];
Object.values(TEAMS).forEach(rows => rows.forEach(([name, team, pos]) => {
  if (pos !== "K" && pos !== "D/ST") ROWS.push({player_key: name.toLowerCase().replace(/[^a-z]/g, "_"), name, pos, team});
}));
ROWS.push({player_key: "decoy_jw", name: "Jaylen Waddle", pos: "WR", team: "DEN"}, {player_key: "decoy_kw", name: "Kyren Williams", pos: "RB", team: "LAR"});

let passed = 0;
let failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ok  ${name}`); }
  catch (error) { failed++; console.log(`  FAIL ${name}\n       ${error.message}`); }
}
const expectedSkill = name => TEAMS[name].filter(r => r[2] !== "K" && r[2] !== "D/ST").map(r => r[0]).sort();
const kd = name => TEAMS[name].filter(r => r[2] === "K" || r[2] === "D/ST").length;

function checkLeague(file, site, {kdKept = true} = {}) {
  const res = P.parseLeague(read(file), ROWS);
  assert.strictEqual(res.site, site, `site ${res.site}`);
  assert.deepStrictEqual(res.teams.map(t => t.teamName), Object.keys(TEAMS), `team names: ${res.teams.map(t => t.teamName).join(" | ")}`);
  res.teams.forEach(t => {
    assert.deepStrictEqual(t.players.map(p => p.name).sort(), expectedSkill(t.teamName), `${t.teamName} players`);
    t.players.forEach(p => assert.strictEqual(p.confidence, 1, `${p.name} confidence`));
    if (kdKept) {
      const kept = t.unmatched.filter(u => u.pos === "K" || u.pos === "DEF");
      assert.strictEqual(kept.length, kd(t.teamName), `${t.teamName} K/DEF kept: ${kept.map(u => u.line).join(", ")}`);
    }
  });
  return res;
}

console.log("League paste");
test("ESPN League Rosters page: every team, named, with its own players", () => checkLeague("espn-league-rosters.txt", "espn"));
test("ESPN with the record on its own line", () => checkLeague("espn-league-rosters-split-record.txt", "espn"));
test("Yahoo league rosters: Kickers and Defense tables fold into their team", () => checkLeague("yahoo-league-rosters.txt", "yahoo"));
test("Sleeper league rosters: name, @handle, record", () => checkLeague("sleeper-league-rosters.txt", "sleeper"));
test("Nav list team names (no players) do not become teams", () => {
  const res = P.parseLeague(read("espn-league-rosters.txt"), ROWS);
  assert.ok(!res.teams.some(t => /\(TA\)|Manager/.test(t.teamName)));
});
test("A single team page is not a league", () => {
  const one = fs.readFileSync(path.join(ROOT, "tests", "fixtures", "roster_paste", "espn-team.txt"), "utf8");
  assert.strictEqual(P.parseLeague(one, ROWS).teams.length, 0);
});
test("A Sleeper league link gives its league ID", () => {
  const res = P.parseLeague("https://sleeper.com/leagues/1180123456789012345/team", ROWS);
  assert.strictEqual(res.sleeperLeagueId, "1180123456789012345");
  assert.strictEqual(res.teams.length, 0);
});
test("An ESPN league link gives its league ID", () => {
  assert.strictEqual(P.parseLeague("https://fantasy.espn.com/football/league/rosters?leagueId=123456&seasonId=2026", ROWS).espnLeagueId, "123456");
});
test("A player listed twice is kept by the first team only", () => {
  const text = "Team One (1-0)\nQB\nJoe Burrow\nRB\nAshton Jeanty\nWR\nJustin Jefferson\nTeam Two (0-1)\nQB\nJoe Burrow\nRB\nBijan Robinson\nWR\nTee Higgins";
  const res = P.parseLeague(text, ROWS);
  assert.deepStrictEqual(res.teams.map(t => t.players.map(p => p.name)), [["Joe Burrow", "Ashton Jeanty", "Justin Jefferson"], ["Bijan Robinson", "Tee Higgins"]]);
});
test("Empty text and missing player list are safe", () => {
  assert.deepStrictEqual(P.parseLeague("", ROWS).teams, []);
  assert.deepStrictEqual(P.parseLeague(read("espn-league-rosters.txt"), []).teams, []);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exit(1);
