// test_entry_league_paste.js — JEG-1538: the connect.html paste reader (app/next/league-paste.js).
// Run: node tests/test_entry_league_paste.js
// 1. Parity: on the live whole-league fixtures (tests/fixtures/league_paste), read() gives the same teams and players
//    as the live reader DDFRosterPaste.parseLeague, so a paste the live League tab reads today reads the same here.
// 2. Regression: tests/fixtures/entry_paste, the rosterparse.js fixtures from the redesign, including two real pastes
//    (01 iPhone Safari tab text, 02 Yahoo markdown; team and league names replaced): team names (*.expect.json) and the
//    matched players per team (players.expect.json) against the published player table.
// 3. The edit-names path (readWithNames), one-team pages, and the ddf:pasted record shape setup.html reads.
"use strict";
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const ROOT = path.resolve(__dirname, "..");
global.window = globalThis;
globalThis.DDFRosterPaste = require(path.join(ROOT, "app", "v2", "roster-paste.js"));
require(path.join(ROOT, "app", "next", "rosterparse.js"));
const LP = require(path.join(ROOT, "app", "next", "league-paste.js"));
const TABLE = JSON.parse(fs.readFileSync(path.join(ROOT, "app", "next", "players-table-1.json"), "utf8"));
const TABLE_ROWS = TABLE.map(r => { const f = r.split("|"); return {name: f[0], pos: f[1], team: f[2], player_key: Number(f[3])}; });

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log(`  ok  ${name}`); }
  catch (error) { failed++; console.log(`  FAIL ${name}\n       ${error.message}`); }
}

// 1. parity with the live reader
const LIVE_DIR = path.join(ROOT, "tests", "fixtures", "league_paste");
const LIVE_TEAMS = JSON.parse(fs.readFileSync(path.join(LIVE_DIR, "teams.json"), "utf8"));
const LIVE_ROWS = [];
Object.values(LIVE_TEAMS).forEach(rows => rows.forEach(([name, team, pos]) => {
  if (pos !== "K" && pos !== "D/ST") LIVE_ROWS.push({player_key: name.toLowerCase().replace(/[^a-z]/g, "_"), name, pos, team});
}));
fs.readdirSync(LIVE_DIR).filter(f => f.endsWith(".txt")).sort().forEach(f => {
  test(`parity with parseLeague: ${f}`, () => {
    const text = fs.readFileSync(path.join(LIVE_DIR, f), "utf8");
    const live = DDFRosterPaste.parseLeague(text, LIVE_ROWS);
    const ours = LP.read(text, LIVE_ROWS);
    assert.ok(live.teams.length >= 2, "the live reader reads this fixture");
    assert.strictEqual(ours.ok, true, `read() ok (${ours.reason})`);
    assert.deepStrictEqual(ours.teams.map(t => t.name), live.teams.map(t => t.teamName), "team names");
    ours.teams.forEach((t, i) => assert.deepStrictEqual(t.players.map(p => p.key).sort(), live.teams[i].players.map(p => String(p.id)).sort(), `${t.name} players`));
    assert.strictEqual(ours.site, live.site, "site");
  });
});

// 2. redesign fixtures, real pastes included
const DIR = path.join(ROOT, "tests", "fixtures", "entry_paste");
const PLAYERS = JSON.parse(fs.readFileSync(path.join(DIR, "players.expect.json"), "utf8"));
fs.readdirSync(DIR).filter(f => f.endsWith(".txt")).sort().forEach(f => {
  test(`entry fixture: ${f}`, () => {
    const text = fs.readFileSync(path.join(DIR, f), "utf8");
    const names = JSON.parse(fs.readFileSync(path.join(DIR, f.replace(".txt", ".expect.json")), "utf8"));
    assert.deepStrictEqual(window.DDF.rosterParse.teams(text, {players: TABLE}).map(t => t.name), names, "rosterparse team names");
    const res = LP.read(text, TABLE_ROWS, {table: TABLE});
    const want = PLAYERS[f];
    assert.strictEqual(res.ok, want.ok, `ok (${res.reason})`);
    assert.strictEqual(res.reason, want.reason, "reason");
    assert.deepStrictEqual(res.teams.map(t => ({name: t.name, players: t.players.map(p => p.name), unmatched: t.unmatched.map(u => u.reason)})), want.teams);
    if (res.ok) assert.deepStrictEqual(res.teams.map(t => t.name), names, "read() keeps rosterparse's names");
    res.teams.forEach(t => t.players.forEach(p => {
      assert.ok(p.key && /^\d+$/.test(p.key), `${p.name}: engine key`);
      assert.strictEqual(String(TABLE[p.id]).split("|")[3], p.key, `${p.name}: table id points at the same player`);
    }));
  });
});

// 3. edit names, one team, record
test("readWithNames: typed names split a paste the reader could not", () => {
  const text = "zzz\nGG!\nJosh Allen\nBijan Robinson\nTT!\nJordan Love\nSaquon Barkley\n";
  const res = LP.readWithNames(text, ["GG!", "TT!"], TABLE_ROWS, {table: TABLE});
  assert.strictEqual(res.ok, true);
  assert.deepStrictEqual(res.teams.map(t => [t.name, t.players.map(p => p.name)]), [["GG!", ["Josh Allen", "Bijan Robinson"]], ["TT!", ["Jordan Love", "Saquon Barkley"]]]);
});
test("readWithNames: a typed name not in the paste is still a team, one name is not a league", () => {
  const res = LP.readWithNames("GG!\nJosh Allen\n", ["GG!", "Somebody Else"], TABLE_ROWS);
  assert.deepStrictEqual(res.teams.map(t => [t.name, t.players.length]), [["GG!", 1], ["Somebody Else", 0]]);
  assert.strictEqual(LP.readWithNames("GG!\nJosh Allen\n", ["GG!"], TABLE_ROWS).ok, false);
});
test("a team named like a player's first name does not swallow that player", () => {
  const res = LP.read("Josh\nJosh Allen\nBijan Robinson\nMike\nJordan Love\nSaquon Barkley\n", TABLE_ROWS, {table: TABLE});
  assert.deepStrictEqual(res.teams.map(t => [t.name, t.players.map(p => p.name)]), [["Josh", ["Josh Allen", "Bijan Robinson"]], ["Mike", ["Jordan Love", "Saquon Barkley"]]]);
  const named = LP.readWithNames("Allen\nKyler Murray\nJosh Allen\nKyler\nJordan Love\n", ["Allen", "Kyler"], TABLE_ROWS);
  assert.deepStrictEqual(named.teams.map(t => [t.name, t.players.map(p => p.name)]), [["Allen", ["Kyler Murray", "Josh Allen"]], ["Kyler", ["Jordan Love"]]]);
});
test("kickers and defenses keep the live roster key", () => {
  const res = LP.read(fs.readFileSync(path.join(DIR, "01-yahoo-iphone.txt"), "utf8"), TABLE_ROWS, {table: TABLE});
  const kd = res.teams[1].unmatched.filter(u => u.reason === "kdef");
  assert.strictEqual(kd.length, 1);
  assert.ok(/^x:DEF:/.test(kd[0].key), kd[0].key);
});
test("readWithNames: a long typed name is one team", () => {
  const long = "The Long Name Report With Bill And Friends";
  const res = LP.readWithNames("GG!\nJosh Allen\n", ["GG!", long], TABLE_ROWS);
  assert.deepStrictEqual(res.teams.map(t => t.name), ["GG!", long]);
});
test("unreadable and empty pastes", () => {
  assert.strictEqual(LP.read("", TABLE_ROWS).reason, "empty");
  const r = LP.read("Alpha Squad\nfoo bar\nBeta Crew\nbaz qux", TABLE_ROWS);
  assert.strictEqual(r.ok, false);
  assert.strictEqual(r.reason, "unreadable");
});
test("record: the ddf:pasted shape setup.html reads", () => {
  const res = LP.read(fs.readFileSync(path.join(DIR, "03-espn.txt"), "utf8"), TABLE_ROWS, {table: TABLE});
  const rec = LP.record(res, "paste");
  assert.deepStrictEqual(Object.keys(rec).sort(), ["me", "site", "source", "teams", "v"]);
  assert.strictEqual(rec.me, null);
  assert.deepStrictEqual(Object.keys(rec.teams[0]).sort(), ["name", "players", "unmatched"]);
  assert.deepStrictEqual(Object.keys(rec.teams[0].players[0]).sort(), ["id", "key", "line", "name", "pos", "slot", "team"]);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
