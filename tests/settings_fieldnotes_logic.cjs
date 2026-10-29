// JEG-1140: node checks for the Settings Fieldnotes view model and the local-data contracts it presents.
// Prints one JSON object; tests/test_jeg1140_settings_fieldnotes.py asserts on it. No browser, no storage.
"use strict";
const fs = require("fs");
const path = require("path");
const ROOT = path.resolve(__dirname, "..");
const S = require(path.join(ROOT, "app/v2/settings-fieldnotes.js"));
const W = require(path.join(ROOT, "app/v2/workspace.js"));
const FIX = path.join(ROOT, "tests/fixtures/settings-fieldnotes");
const league = JSON.parse(fs.readFileSync(path.join(FIX, "league.json"), "utf8"));
const contexts = JSON.parse(fs.readFileSync(path.join(FIX, "contexts.json"), "utf8"));

const out = {vm: {}, roundTrip: {}, link: {}, query: {}};
Object.entries(contexts).forEach(([name, ctx]) => { out.vm[name] = S.viewModel(ctx); });
out.vm.garbage = S.viewModel(null);
out.strings = JSON.stringify(S.STRINGS, (k, v) => (typeof v === "function" ? v(3) + " " + v(1) : v));

// League file: the page's Export is W.exportJson of the saved league with its settings; Import is W.importJson.
const before = W.normalizeWorkspace(league);
const text = W.exportJson(before);
const back = W.importJson(text);
const pick = ws => ({name: ws.name, myTeamId: ws.myTeamId, settings: ws.settings,
  teams: ws.teams.map(t => ({id: t.id, name: t.name, entries: t.entries}))});
out.roundTrip.error = back.error || null;
out.roundTrip.equal = !back.error && JSON.stringify(pick(back.workspace)) === JSON.stringify(pick(before));
out.roundTrip.twice = !back.error && W.exportJson(back.workspace) === W.exportJson(W.importJson(W.exportJson(back.workspace)).workspace);
out.roundTrip.rejects = ["not json", "{}", JSON.stringify({id: "x", name: "y", teams: [{entries: [{name: "no key"}]}]})].map(t => Boolean(W.importJson(t).error));

// Link: the league Copy link is W.shareHash (rosters, my team) plus the page's league query.
const query = league.settings.query;
const share = W.shareHash(before, query);
// Read the way the page reads a link (league.js readShareHash): the workspace text raw, the rest as parameters.
const rawText = hash => hash.slice(hash.indexOf("workspace=") + "workspace=".length).split("&")[0];
const params = new URLSearchParams(share.hash.slice(share.hash.indexOf("?") + 1));
const teams = W.decodeShare(rawText(share.hash), null);
const mine = before.teams.find(t => t.id === before.myTeamId);
out.link.full = share.full;
out.link.mineFirst = teams[Number(params.get("wm"))].name === mine.name;
out.link.sameTeams = JSON.stringify(teams.map(t => t.name).sort()) === JSON.stringify(before.teams.map(t => t.name).sort());
out.link.sameKeys = teams.every(t => {
  const orig = before.teams.find(o => o.name === t.name);
  return orig && JSON.stringify(t.entries.map(e => e.key)) === JSON.stringify(orig.entries.map(e => e.key));
});
const kicker = teams.flatMap(t => t.entries).find(e => e.pos === "K");
out.link.kicker = kicker ? {key: kicker.key, name: kicker.name} : null;
out.link.settings = S.settingsFromQuery(params.toString());
// Over the link budget only "my team" travels (the existing documented fallback; Export keeps every team).
const big = W.normalizeWorkspace({...league, teams: Array.from({length: 20}, (_, i) => ({...league.teams[i % 2], id: `t${i}`, name: `Team ${i}`,
  entries: Array.from({length: 30}, (_, j) => ({key: String(800000000 + i * 1000 + j), name: `P ${i}-${j}`, pos: "WR"}))})), myTeamId: "t3"});
const bigShare = W.shareHash(big, query);
const bigTeams = W.decodeShare(rawText(bigShare.hash), null);
out.link.bigFull = bigShare.full;
out.link.bigOnlyMine = bigTeams.length === 1 && bigTeams[0].name === "Team 3";

out.query = {
  fixture: S.settingsFromQuery(query),
  superflex: S.settingsFromQuery("scoring=half_ppr&teams=10&roster=QB1.RB2.WR3.TE1.FLEX1.SF1.BN6"),
  bad: [S.settingsFromQuery(""), S.settingsFromQuery("scoring=ppr&teams=0"), S.settingsFromQuery("scoring=x&teams=12")],
  rules: [S.rulesText({scoring: "ppr", teams: 12, qb: 1}), S.rulesText({scoring: "standard", teams: 10, qb: "superflex"}),
    S.rulesText({scoring: "half_ppr", teams: 8, qb: null}), S.rulesText(null)]
};
process.stdout.write(JSON.stringify(out));
