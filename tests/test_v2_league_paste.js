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
// The 20-team league fixture holds real rosters, including a team whose name starts "Bye Week" (JEG-1110).
const LEAGUE_FX = JSON.parse(fs.readFileSync(path.join(ROOT, "tests", "fixtures", "league", "fixture-20team.json"), "utf8"));

// An ESPN league rosters paste: "Team Name (5-1-0)", a "SLOT PLAYER ACQ" header, then each
// player as a position line, ESPN's doubled name, a "TEAM POS" line and "Draft".
// Returns the paste and, per team, the players the engine can hold (no kicker or defense row).
function espnLeaguePaste(fixtures, {extraLine = null, extraAfter = -1, splitRecord = false} = {}) {
  const rows = [];
  const lines = ["ESPN", "NFL", "ESPN Fantasy", "League Rosters", "Test league", ""];
  const expect = [];
  fixtures.forEach((team, i) => {
    const players = team.players.filter(p => p.pos !== "K" && p.pos !== "D/ST");
    players.forEach(p => rows.push({player_key: p.key, name: p.name, pos: p.pos, team: p.team}));
    if (extraLine && i === extraAfter) lines.push(extraLine);
    lines.push(splitRecord ? team.name : `${team.name} (5-1-0)`);
    if (splitRecord) lines.push("(5-1-0)");
    lines.push("SLOT\tPLAYER\tACQ");
    players.forEach(p => lines.push(p.pos, `${p.name}${p.name}`, `${p.team} ${p.pos}`, "Draft"));
    expect.push([team.name, players.length]);
  });
  return {text: lines.join("\n") + "\n", rows, expect};
}

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
test("ESPN league paste with a team named 'Bye Week Bandits': 12 teams, none swallowed (JEG-1110)", () => {
  [false, true].forEach(splitRecord => {
    const {text, rows, expect} = espnLeaguePaste(LEAGUE_FX.teams.slice(0, 12), {splitRecord});
    const where = splitRecord ? "record on its own line" : "record beside the name";
    const res = P.parseLeague(text, rows);
    assert.strictEqual(res.teams.length, 12, `${where} — teams found: ${res.teams.map(t => t.teamName).join(" | ")}`);
    assert.deepStrictEqual(res.teams.map(t => t.teamName), expect.map(e => e[0]), where);
    res.teams.forEach(t => {
      const want = expect.find(e => e[0] === t.teamName)[1];
      assert.strictEqual(t.players.length, want, `${where} — ${t.teamName}: ${t.players.length} players, want ${want}`);
    });
    // The team before "Bye Week Bandits" must not be inflated with its roster (JEG-1110).
    const bandits = res.teams.findIndex(t => t.teamName === "Bye Week Bandits");
    assert.ok(bandits > 0, "the paste has a team before Bye Week Bandits");
    assert.strictEqual(res.teams[bandits - 1].players.length, expect[bandits - 1][1], `${where} — the team before Bye Week Bandits is not inflated`);
  });
});
test("A real 'Bye Week Players' section header is still not a team (JEG-1110)", () => {
  const plain = espnLeaguePaste(LEAGUE_FX.teams.slice(0, 12));
  const withSection = espnLeaguePaste(LEAGUE_FX.teams.slice(0, 12), {extraLine: "Bye Week Players", extraAfter: 4});
  const before = P.parseLeague(plain.text, plain.rows);
  const after = P.parseLeague(withSection.text, withSection.rows);
  assert.ok(!after.teams.some(t => t.teamName === "Bye Week Players"), `a section header became a team: ${after.teams.map(t => t.teamName).join(" | ")}`);
  assert.deepStrictEqual(after.teams.map(t => [t.teamName, t.players.length]),
    before.teams.map(t => [t.teamName, t.players.length]), "the section header changes nothing else");
});
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
