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
// liveAdapter on a minimal fake page (JEG-1306): only what the adapter touches. Elements keep document order, so
// getElementById returns the first of several inputs with one id, as a browser does.
function fakePage() {
  const nodes = [];
  const winListeners = {};
  class FakeNode {
    constructor(id, type) { Object.assign(this, {id, type, files: [], hidden: false, textContent: "", l: {}}); }
    addEventListener(t, f, o) { (this.l[t] = this.l[t] || []).push({f, once: Boolean(o && o.once)}); }
    dispatch(t) { const ls = this.l[t] || []; this.l[t] = ls.filter(x => !x.once); ls.forEach(x => x.f({type: t})); }
    click() { if (this.onclick) this.onclick(); }
  }
  const later = (f, ms) => { const t = setTimeout(f, ms); if (t.unref) t.unref(); return t; };
  const w = {
    document: {getElementById: id => nodes.find(n => n.id === id) || null,
      querySelectorAll: sel => { const id = /\[id="([^"]+)"\]/.exec(sel)[1]; return nodes.filter(n => n.type === "file" && n.id === id); },
      body: {append: n => nodes.push(n)}},
    MutationObserver: class { observe() {} disconnect() {} },
    setTimeout: later, clearTimeout,
    addEventListener: (t, f, o) => (winListeners[t] = winListeners[t] || []).push(f),
    focus: () => { const ls = winListeners.focus || []; winListeners.focus = []; ls.forEach(f => f({type: "focus"})); },
    location: {hash: ""},
    DDFOverrides: {state: {engine: {}}, render() {}, count: () => 0, basis: () => ({mode: "default"})}
  };
  // The Overrides tab's Import: a new hidden input on every press, removed only when a file is chosen.
  const ovImport = new FakeNode("v2OvImport", "button");
  ovImport.onclick = () => nodes.push(new FakeNode("v2OvImportFile", "file"));
  const lgNotice = new FakeNode("v2LgNotice", "p");
  const lgFile = new FakeNode("v2LgFile", "file");
  const lgLoad = new FakeNode("v2LgLoad", "button");
  const lgConfirm = new FakeNode("v2LgLoadConfirm", "div");
  lgConfirm.hidden = true;
  nodes.push(ovImport, lgNotice, lgFile, lgLoad, lgConfirm);
  return {w, nodes, lgNotice, lgLoad, lgConfirm, newest: () => nodes.filter(n => n.id === "v2OvImportFile").pop()};
}
const settle = (p, ms) => Promise.race([Promise.resolve(p).then(r => ({done: true, ok: r.ok})), new Promise(r => setTimeout(() => r({done: false}), ms))]);
(async () => {
  out.adapter = {};
  {
    // Import overrides, cancel; Import overrides again, cancel: both waits end.
    const f = fakePage();
    const A = S.liveAdapter(f.w).actions;
    const first = A.importOverrides(); f.newest().dispatch("cancel");
    const second = A.importOverrides(); f.newest().dispatch("cancel");
    out.adapter.cancelTwice = [(await settle(first, 50)).done, (await settle(second, 50)).done];
    // No cancel event (older Safari): the window getting focus back with no file ends the wait.
    const third = A.importOverrides(); f.w.focus();
    out.adapter.focusFallback = (await settle(third, 1300)).done;
  }
  {
    // A league named "Not Bad" that loads is a success, not an error.
    const f = fakePage();
    f.lgLoad.onclick = () => { f.lgNotice.textContent = "Not Bad: 2 teams loaded."; };
    out.adapter.loadedTone = (await settle(S.liveAdapter(f.w).actions.importLeague(), 50)).ok;
    // A replace prompt already showing before the press is not this import's answer.
    const g = fakePage();
    g.lgConfirm.hidden = false;
    g.lgConfirm.textContent = "Replace your saved league (2 teams) with an older file?";
    out.adapter.staleConfirm = (await settle(S.liveAdapter(g.w).actions.importLeague(), 50)).done;
  }
  process.stdout.write(JSON.stringify(out));
})();
