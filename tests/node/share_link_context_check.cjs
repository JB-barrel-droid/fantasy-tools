// JEG-1328 (slice 9 of docs/specs/trade-page-parity.md): share links keep the league setup, the route's controls and
// both teams. Pure Node, no browser.
//   node tests/node/share_link_context_check.cjs [dir with workspace.js, finder.js, trade-context.js, ddf-state.js, league.js]
// Prints {ran, failures}; exits 1 on any failure. tests/test_jeg1328_share_links.py runs it on app/v2 and on broken copies.
//
// League link (workspace.js shareHash / readShareExtras / shareSettingsQuery, as league.js readShareHash applies them):
// every league-finder discovery control, the selected trade keyed by the opponent's team id, the marked team, and
// TradeContext common (the league query and the value context) round-trip; a link made before JEG-1328 opens with the
// same rosters, defaults and name-keyed pick it always did. Pair finder link (finder.js encode/decodeFinderHash): every
// field round-trips, including viable-only and the saved teams the rosters came from; an older link reads as before.
"use strict";
const path = require("path");
const fs = require("fs");
const assert = require("assert");

const dir = path.resolve(process.argv[2] || path.join(__dirname, "..", "..", "app", "v2"));
const W = require(path.join(dir, "workspace.js"));
const F = require(path.join(dir, "finder.js"));
const TC = require(path.join(dir, "trade-context.js"));
const leagueSrc = fs.readFileSync(path.join(dir, "league.js"), "utf8");
const finderSrc = fs.readFileSync(path.join(dir, "finder.js"), "utf8");

const ran = [];
const failures = [];
function t(name, fn) {
  ran.push(name);
  try { fn(); } catch (error) { failures.push({name, message: String(error && error.message || error)}); }
}

const entry = (key, name, pos) => ({key: String(key), name, pos});
function league() {
  let ws = W.newWorkspace({name: "USO"});
  ["Alex", "Blair", "Casey", "Drew"].forEach((name, i) => {
    ws = W.ops.addTeam(ws, name, {entries: [entry(100 + i, `QB ${i}`, "QB"), entry(200 + i, `RB ${i}`, "RB"), entry(300 + i, `WR ${i}`, "WR")]});
  });
  return ws;
}
const LEAGUE_QUERY = "scoring=ppr&teams=12&roster=QB1.RB2.WR3.TE1.FLEX2.SF1.BN6";
// What DDFOverrides.shareLink appends (JEG-1224 D3 A: the link keeps the complete value context).
const VALUE_TAIL = "valuecontext=1&basis=fantasycalc&ov=2227%3A41.5";
const withValue = hash => `${hash}&${VALUE_TAIL}`;
const queryOf = hash => hash.slice(hash.indexOf("?") + 1);
// league.js readShareHash, step for step, on the pure parts it calls.
function openLeagueLink(hash) {
  const query = queryOf(hash);
  const at = hash.indexOf("workspace=");
  const text = hash.slice(at + "workspace=".length).split("&")[0];
  const params = new URLSearchParams(query);
  const teams = W.decodeShare(text, ROWS);
  let w = W.newWorkspace({name: "Shared league"});
  teams.forEach(team => { w = W.ops.addTeam(w, team.name, {entries: team.entries.filter(e => !e.unknown)}); });
  const mine = params.has("wm") ? (params.get("wm") === "none" ? null : Number(params.get("wm"))) : 0;
  if (Number.isInteger(mine) && w.teams[mine]) w = W.ops.setMyTeam(w, w.teams[mine].id);
  const extras = W.readShareExtras(params, w.teams.map(team => team.id));
  if (Object.keys(extras.ui).length) w = W.ops.setUi(w, extras.ui);
  const settingsQuery = W.shareSettingsQuery(params);
  if (settingsQuery) w = W.ops.setSettings(w, {query: settingsQuery});
  return {w, trade: extras.trade};
}
// The engine's rows, as league.js passes ctx.rowsByKey: every numeric key prices.
const ROWS = {get: key => ({name: `Player ${key}`, pos: "WR", team: ""})};
const byName = (ws, name) => ws.teams.find(team => team.name === name);

// ---------- league link ----------
t("league_link_round_trips_every_field", () => {
  let ws = league();
  const [alex, , casey] = ws.teams;
  ws = W.ops.setMyTeam(ws, ws.teams[1].id);   // Blair is mine: the link puts the marked team first
  ws = W.ops.setUi(ws, {maxSize: 3, hideForce: true, filters: {fit: "natural", opponent: casey.id, minCapture: 3, minCharts: 2}});
  const pick = W.tradePick(casey.id, [{player_key: "201"}], [{player_key: "302"}, {player_key: "102"}]);
  const shared = W.shareHash(ws, LEAGUE_QUERY, {trade: pick});
  const {w, trade} = openLeagueLink(withValue(shared.hash));
  // Teams and the marked team, by name and roster (the reader's league gives them new ids).
  assert.deepStrictEqual(w.teams.map(team => team.name).sort(), ws.teams.map(team => team.name).sort());
  ws.teams.forEach(team => assert.deepStrictEqual(byName(w, team.name).entries.map(e => e.key), team.entries.map(e => e.key), `${team.name}'s roster`));
  assert.strictEqual(w.teams.find(team => team.id === w.myTeamId).name, "Blair", "the marked team");
  // The league finder's controls, as TradeContext reads them; the opponent filter names the same team.
  const sent = TC.routeControls("league", ws.ui);
  const got = TC.routeControls("league", w.ui);
  assert.strictEqual(byName(w, "Casey").id, got.filters.opponent, "the opponent filter keeps the same team");
  assert.deepStrictEqual({...got, filters: {...got.filters, opponent: "casey"}}, {...sent, filters: {...sent.filters, opponent: "casey"}});
  // The selected trade, keyed by the opponent's new id with the same players.
  const read = W.parseTradePick(trade);
  assert.ok(read && !read.legacy, `the pick reads in the current form: ${trade}`);
  assert.strictEqual(read.opponentId, byName(w, "Casey").id, "the pick names Casey by id");
  assert.deepStrictEqual([read.give, read.receive], [["201"], ["302", "102"]]);
  assert.strictEqual(trade, W.tradePick(byName(w, "Casey").id, ["201"], ["302", "102"]), "the address form league.js matches rows against");
  // TradeContext common: the league settings and the value context arrive with the settings, nothing of the link's own.
  const settings = new URLSearchParams(w.settings.query);
  ["workspace", "wm", "size", "hf", "fit", "opp", "mcap", "mch", "trade"].forEach(k => assert.ok(!settings.has(k), `${k} leaked into the league settings`));
  assert.deepStrictEqual(TC.leagueFromQuery(w.settings.query).league, TC.leagueFromQuery(LEAGUE_QUERY).league, "common.league");
  assert.deepStrictEqual(["valuecontext", "basis", "ov"].map(k => settings.get(k)), ["1", "fantasycalc", "2227:41.5"], "common.valuation");
  assert.ok(alex, "fixture");
});
t("league_link_pick_is_by_id_not_name", () => {
  let ws = league();
  ws = W.ops.renameTeam(ws, ws.teams[3].id, "Casey");   // two teams called Casey
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  const second = ws.teams[3];
  const {w, trade} = openLeagueLink(W.shareHash(ws, "", {trade: W.tradePick(second.id, ["100"], ["303"])}).hash);
  assert.strictEqual(W.parseTradePick(trade).opponentId, w.teams[3].id, "the pick keeps the second Casey, not the first");
  // In the address (league.js setTradeHash / pickFromHash) the pick follows the id through a rename.
  const row = {opponentId: second.id, opponent: "Casey", give: [{player_key: "100"}], receive: [{player_key: "303"}]};
  const renamed = {...row, opponent: "Casey (renamed)"};
  assert.strictEqual(W.tradePick(row.opponentId, row.give, row.receive), W.tradePick(renamed.opponentId, renamed.give, renamed.receive));
});
t("league_link_defaults_add_nothing", () => {
  let ws = W.ops.setMyTeam(league(), league().teams[0].id);
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  const shared = W.shareHash(ws, LEAGUE_QUERY, {trade: null});
  assert.deepStrictEqual([...new URLSearchParams(queryOf(shared.hash)).keys()], ["workspace", "wm", "scoring", "teams", "roster"],
    "a league on today's defaults links exactly as before");
  const {w, trade} = openLeagueLink(shared.hash);
  assert.deepStrictEqual(TC.routeControls("league", w.ui), TC.routeControls("league", W.newWorkspace().ui));
  assert.strictEqual(trade, null);
});
t("league_link_only_mine_drops_opponent_parts", () => {
  let ws = W.newWorkspace();
  for (let i = 0; i < 20; i += 1) {
    ws = W.ops.addTeam(ws, `Team ${i} with a long name to pass the link limit`, {entries: Array.from({length: 16}, (_, j) => entry(`${i}${j}00`, `P${i}-${j}`, "WR"))});
  }
  ws = W.ops.setMyTeam(ws, ws.teams[5].id);
  ws = W.ops.setUi(ws, {maxSize: 4, filters: {opponent: ws.teams[2].id}});
  const shared = W.shareHash(ws, "", {trade: W.tradePick(ws.teams[2].id, ["5000"], ["2000"])});
  assert.strictEqual(shared.full, false);
  const keys = [...new URLSearchParams(queryOf(shared.hash)).keys()];
  assert.ok(keys.includes("size") && !keys.includes("opp") && !keys.includes("trade"), `only my team travels, so no opponent: ${keys}`);
});
t("old_league_link_opens_the_same_view", () => {
  // A link as main wrote it before JEG-1328 (shareHash plus DDFOverrides.shareLink), with a name-keyed pick in the address.
  const legacyPick = ["Casey", "201", "302,102"].map(encodeURIComponent).join("~");
  const old = `#find-league?workspace=Blair:2s,5k,8c|Casey:2t,5l,8d&wm=0&${LEAGUE_QUERY}&trade=${legacyPick}&${VALUE_TAIL}`;
  const {w, trade} = openLeagueLink(old);
  assert.deepStrictEqual(w.teams.map(team => [team.name, team.entries.map(e => e.key)]), [["Blair", ["100", "200", "300"]], ["Casey", ["101", "201", "301"]]]);
  assert.strictEqual(w.teams.find(team => team.id === w.myTeamId).name, "Blair");
  assert.deepStrictEqual(TC.routeControls("league", w.ui), TC.routeControls("league", W.newWorkspace().ui), "defaults, as before");
  assert.strictEqual(trade, legacyPick, "the name-keyed pick stays in the address");
  const read = W.parseTradePick(trade);
  assert.deepStrictEqual(read, {legacy: true, opponent: "Casey", give: ["201"], receive: ["302", "102"]});
  assert.strictEqual(W.legacyTradePick("Casey", [{player_key: "201"}], [{player_key: "302"}, {player_key: "102"}]), legacyPick,
    "pickFromHash matches the old form against the rows");
  assert.deepStrictEqual(TC.leagueFromQuery(w.settings.query).league, TC.leagueFromQuery(LEAGUE_QUERY).league);
});
t("league_link_rejects_bad_controls", () => {
  const params = new URLSearchParams("size=7&hf=yes&fit=force&opp=9&mcap=-1&mch=x&trade=1~9~1~2");
  assert.deepStrictEqual(W.readShareExtras(params, ["a", "b"]), {ui: {}, trade: null});
});
t("league_page_uses_the_link_codec", () => {
  const src = leagueSrc.replace(/\s+/g, " ");
  assert.ok(src.includes("const tradeParam = r => W.tradePick(r.opponentId, r.give, r.receive);"), "the address pick is keyed by opponent id");
  assert.ok(src.includes("W.legacyTradePick(r.opponent, r.give, r.receive) === m[1]"), "an old name-keyed address still selects its trade");
  assert.ok(src.includes("W.readShareExtras(params, w.teams.map(t => t.id))"), "readShareHash reads the link's controls and pick");
  assert.ok(src.includes("W.shareSettingsQuery(params)"), "readShareHash keeps only league settings and value context as settings");
  assert.ok(src.includes("W.shareHash(store.get(), leagueQuery(), {trade: UI.selectedParam})"), "Copy link carries the selected trade");
});

// ---------- pair finder link ----------
t("finder_link_round_trips_every_field", () => {
  const state = {mine: [{key: "100"}, {key: "200"}], theirs: [{key: "300"}], maxSize: 1, keepMine: false, keepTheirs: false,
    guardrails: {protectedPositions: ["RB", "TE"], minBackups: {QB: 1, WR: 2}, minDdfEdge: 1.5, minUserLineupGain: 0.5, minTheirLineupGain: 0},
    viableOnly: true, teams: {workspaceId: "ws-1", mineId: "team-a", theirId: "team-b"}};
  const hash = F.encodeFinderHash(state, LEAGUE_QUERY);
  const back = F.decodeFinderHash(hash, null);
  assert.deepStrictEqual({mine: back.mine, theirs: back.theirs, size: back.size, keepMine: back.keepMine, keepTheirs: back.keepTheirs,
    viableOnly: back.viableOnly, teams: back.teams}, {mine: ["100", "200"], theirs: ["300"], size: 1, keepMine: false, keepTheirs: false,
    viableOnly: true, teams: {workspaceId: "ws-1", mineId: "team-a", theirId: "team-b"}});
  assert.deepStrictEqual(W.normalizeFinderSettings({...back.guardrails, maxSize: back.size, keepMine: back.keepMine, keepTheirs: back.keepTheirs}),
    W.normalizeFinderSettings({...state.guardrails, maxSize: 1, keepMine: false, keepTheirs: false}), "guardrails");
  assert.deepStrictEqual(TC.leagueFromQuery(queryOf(hash)).league, TC.leagueFromQuery(LEAGUE_QUERY).league, "common.league");
});
t("old_finder_link_reads_as_before", () => {
  const back = F.decodeFinderHash(`#find-trade?mine=100&theirs=300&size=3&km=1&kt=0&${LEAGUE_QUERY}`, null);
  assert.deepStrictEqual([back.mine, back.theirs, back.size, back.keepMine, back.keepTheirs, back.viableOnly, back.teams],
    [["100"], ["300"], 3, true, false, false, {workspaceId: null, mineId: null, theirId: null}]);
  // A link with no saved teams, or none of the new fields, writes none of them.
  const hash = F.encodeFinderHash({mine: [{key: "100"}], theirs: [{key: "300"}], maxSize: 2, keepMine: true, keepTheirs: true, teams: {workspaceId: "ws-1", mineId: null, theirId: null}}, "");
  assert.deepStrictEqual([...new URLSearchParams(queryOf(hash)).keys()], ["mine", "theirs", "size", "km", "kt"]);
});
t("finder_link_team_ids_are_checked", () => {
  const read = q => F.decodeFinderHash(`#find-trade?mine=1&theirs=2&${q}`, null).teams;
  assert.deepStrictEqual(read("mt=a&tt=b"), {workspaceId: null, mineId: null, theirId: null}, "no league id, no teams");
  assert.deepStrictEqual(read("ws=w&mt=a&tt=a"), {workspaceId: null, mineId: null, theirId: null}, "one team on both sides");
  assert.deepStrictEqual(read("ws=w&mt=a%3Cb&tt=c"), {workspaceId: "w", mineId: null, theirId: "c"}, "a malformed id is dropped");
});
t("finder_link_teams_label_only_the_link_rosters", () => {
  const link = {...F.decodeFinderHash("#find-trade?mine=k1,k2&theirs=k3&ws=w1&mt=a&tt=b", null).teams,
    mineKeys: new Set(["k1", "k2"]), theirKeys: new Set(["k3"])};
  const ws = {id: "w1", teams: [{id: "a"}, {id: "b"}]};
  const p = key => ({key});
  assert.deepStrictEqual(F.linkTeamsFor(link, [p("k1"), p("k2")], [p("k3")], ws), {mineId: "a", theirId: "b"}, "the link's rosters");
  assert.deepStrictEqual(F.linkTeamsFor(link, [p("k1")], [p("k3")], ws), {mineId: "a", theirId: "b"}, "a player the reader dropped");
  assert.deepStrictEqual(F.linkTeamsFor(link, [p("k1"), p("k9")], [p("k3")], ws), {mineId: null, theirId: null}, "another state's rosters");
  assert.deepStrictEqual(F.linkTeamsFor(link, [p("k1")], [p("k3")], {id: "w2", teams: ws.teams}), {mineId: null, theirId: null}, "another saved league");
  assert.deepStrictEqual(F.linkTeamsFor(link, [p("k1")], [p("k3")], {id: "w1", teams: [{id: "b"}]}), {mineId: null, theirId: "b"}, "each team it has");
  assert.deepStrictEqual(F.linkTeamsFor(null, [p("k1")], [], ws), {mineId: null, theirId: null}, "no link");
});
t("finder_page_carries_and_applies_the_new_fields", () => {
  const src = finderSrc.replace(/\s+/g, " ");
  assert.ok(src.includes("viableOnly: S.viableOnly, teams}, league);"), "Copy link carries viable-only and the saved teams");
  assert.ok(src.includes("if (decoded) S.viableOnly = decoded.viableOnly;"), "an opened link sets viable-only");
  assert.ok(src.includes("{...decoded.teams, mineKeys: new Set(decoded.mine), theirKeys: new Set(decoded.theirs)}"),
    "an opened link keeps its rosters beside its teams");
  assert.ok(src.includes("rosterCopy = {workspaceId: sharedStore().get().id, teamId: null, theirTeamId: null, active: true}; adoptLinkTeams(mine, theirs);"),
    "setSides adopts the link's saved teams");
});

console.log(JSON.stringify({ran, failures}, null, 2));
process.exitCode = failures.length ? 1 : 0;
