// JEG-1233: the loaded-league status header and collapsed summary (app/v2/league-status.js).
// Runs in node with the real workspace store and a small fake DOM, so the view model, the disclosure and its keyboard
// behavior are checked without a browser. Phone layout and real focus rings: tests/test_v2_league_status_render.py.
"use strict";
const assert = require("node:assert/strict");
const W = require("../../app/v2/workspace.js");
const S = require("../../app/v2/league-status.js");

// ---------- a fake DOM: just what league-status.js touches ----------
class FakeNode {
  constructor(doc, tag) { this.ownerDocument = doc; this.tagName = tag.toUpperCase(); this.attrs = new Map(); this.children = []; this.parent = null; this._text = ""; this.hidden = false; this.listeners = {}; }
  setAttribute(k, v) { this.attrs.set(k, String(v)); }
  getAttribute(k) { return this.attrs.has(k) ? this.attrs.get(k) : null; }
  get id() { return this.getAttribute("id") || ""; }
  set className(v) { this.attrs.set("class", v); }
  get className() { return this.getAttribute("class") || ""; }
  set textContent(v) { this.children.forEach(c => { c.parent = null; }); this.children = []; this._text = String(v); }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(""); }
  append(...kids) { kids.forEach(k => { if (k.parent) k.parent.children = k.parent.children.filter(c => c !== k); k.parent = this; this.children.push(k); }); }
  replaceChildren(...kids) { this.children.forEach(c => { c.parent = null; }); this.children = []; this._text = ""; this.append(...kids); }
  remove() { if (this.parent) { this.parent.children = this.parent.children.filter(c => c !== this); this.parent = null; } }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatch(type, extra) {
    const event = {type, target: this, ...(extra || {})};
    for (let n = this; n; n = n.parent) (n.listeners[type] || []).forEach(fn => fn(event));
    return event;
  }
  click() { this.dispatch("click"); }
  focus() { this.ownerDocument.activeElement = this; }
  // Only the one selector the component uses.
  closest(sel) {
    assert.equal(sel, "[aria-expanded='true']");
    for (let n = this; n; n = n.parent) if (n.getAttribute("aria-expanded") === "true") return n;
    return null;
  }
  find(pred) { if (pred(this)) return this; for (const c of this.children) { const f = c.find(pred); if (f) return f; } return null; }
  byId(id) { return this.find(n => n.id === id); }
  visible() { for (let n = this; n; n = n.parent) if (n.hidden) return false; return true; }
}
const makeDoc = () => { const doc = {activeElement: null, createElement: tag => new FakeNode(doc, tag)}; return doc; };

function memoryStorage(initial) {
  const data = new Map(Object.entries(initial || {}));
  return {data, getItem: k => (data.has(k) ? data.get(k) : null), setItem: (k, v) => { data.set(k, String(v)); }, removeItem: k => data.delete(k)};
}
function newStore(storage) { const store = W.createStore({storage, delay: 0}); store.load(); return store; }
function league(names, opts) {
  let ws = W.newWorkspace({name: (opts && opts.name) || "Glenview Dynasty"});
  names.forEach((name, i) => {
    const entries = name.empty ? [] : Array.from({length: name.n || 3}, (_, k) => ({key: `${i}-${k}`, name: `P${i}-${k}`, pos: k === 0 && name.k ? "K" : "RB"}));
    ws = W.ops.addTeam(ws, name.name || name, {entries});
  });
  return ws;
}
const allText = node => node.textContent;
const BANNED = /\b(sync(ed|s|ing)?|connect(ed)?|account|live|every device|all your devices|cloud|complete import|imported everything)\b/i;
let checks = 0;
const check = (name, fn) => { fn(); checks += 1; };

// ---------- describe(): the view model ----------
check("no league", () => {
  const m = S.describe({workspace: W.newWorkspace(), loadStatus: "empty", saveStatus: "idle"});
  assert.equal(m.state, "empty");
  assert.equal(m.headline, "No league loaded yet");
  assert.equal(m.summary, "No league loaded yet");
  assert.equal(m.storage, null, "no saved claim with nothing saved");
  assert.deepEqual(m.facts, []);
  assert.equal(m.issues.length, 0);
});

check("loaded from this device: counts are actual rows, K/DEF counted and named", () => {
  let ws = league([{name: "Alpha", n: 4, k: true}, {name: "Bravo", n: 2}, {name: "Charlie", n: 3}]);
  ws = W.ops.setMyTeam(ws, ws.teams[1].id);
  const m = S.describe({workspace: ws, loadStatus: "ok", saveStatus: "saved", origin: "stored"});
  assert.equal(m.state, "loaded");
  assert.equal(m.title, "Glenview Dynasty");
  assert.deepEqual(m.counts, {teams: 3, players: 9, notEvaluated: 1, emptyTeams: 0});
  assert.equal(m.summary, "3 teams · 9 players · Your team: Bravo · Saved on this device");
  assert.equal(m.facts.find(f => f.id === "players").value, "9 (1 K or DEF, not evaluated)");
  assert.equal(m.facts.find(f => f.id === "origin").value, "Read from this device");
  assert.equal(m.myTeam.name, "Bravo");
});

check("a league with fewer teams than a full league is not padded or called incomplete", () => {
  const m = S.describe({workspace: league(["Alpha", "Bravo"]), saveStatus: "saved"});
  assert.equal(m.counts.teams, 2);
  assert.match(m.summary, /^2 teams · 6 players/);
  assert.ok(!/missing|incomplete|of 12/i.test(JSON.stringify(m)));
});

check("partial parse: league.js's own unmatched, unsure and left-out counts, nothing inferred", () => {
  const parsed = {teams: [{name: "Alpha", count: 3, unmatched: ["Jon Smth", "???"], unsure: 1}, {name: "Bravo", count: 3, unmatched: [], unsure: 0},
    {name: "Zulu", count: 0, unmatched: [], unsure: 0, leftOut: true}], skipped: 1, source: "Read"};
  const m = S.describe({workspace: league(["Alpha", "Bravo"]), saveStatus: "saved", origin: "pasted", parsed});
  assert.equal(m.state, "partial");
  assert.deepEqual(m.issues.map(i => i.id), ["paste-missed", "paste-unsure", "paste-left-out"]);
  assert.equal(m.issues[0].text, "2 lines from your last paste could not be matched to a player.");
  assert.equal(m.issues[2].text, "1 team from your last paste was not set up.");
  assert.equal(m.counts.teams, 2, "counts are the saved rows, not the paste's team list");
  assert.equal(m.facts.find(f => f.id === "origin").value, "Read from your paste this visit");
});

check("a paste that read nothing keeps the saved league and says so", () => {
  const m = S.describe({workspace: league(["Alpha"]), saveStatus: "saved", parsed: {error: "No teams were found in that text."}});
  assert.equal(m.issues[0].id, "paste-error");
  assert.match(m.issues[0].text, /Your saved league was kept\.$/);
  assert.equal(m.state, "loaded");
});

check("empty teams make it partial and are named", () => {
  const m = S.describe({workspace: league(["Alpha", {name: "Bravo", empty: true}]), saveStatus: "saved"});
  assert.equal(m.state, "partial");
  assert.equal(m.issues.find(i => i.id === "empty-teams").text, "1 team has no players yet: Bravo.");
});

check("duplicate names: flagged, the star stays on the team's id", () => {
  let ws = league(["Alpha", "alpha ", "Bravo"]);
  ws = W.ops.setMyTeam(ws, ws.teams[1].id);
  const m = S.describe({workspace: ws, saveStatus: "saved"});
  const dup = m.issues.find(i => i.id.startsWith("dup-"));
  assert.ok(dup, "duplicate flagged");
  assert.match(dup.text, /^2 teams are named “Alpha”/);
  assert.equal(m.myTeam.id, ws.teams[1].id);
});

check("unreadable saved data", () => {
  const m = S.describe({workspace: W.newWorkspace(), loadStatus: "corrupt", saveStatus: "idle"});
  assert.equal(m.state, "error");
  assert.equal(m.headline, "Saved league could not be read");
  assert.match(m.issues[0].text, /It has not been changed\.$/);
  const after = S.describe({workspace: league(["Alpha"]), loadStatus: "version", saveStatus: "saved"});
  assert.match(after.issues[0].text, /started fresh/);
});

check("storage states are only what the store reports", () => {
  const ws = league(["Alpha"]);
  assert.equal(S.describe({workspace: ws, saveStatus: "saving"}).storage.text, "Saving on this device…");
  assert.equal(S.describe({workspace: ws, saveStatus: "unavailable"}).storage.tone, "warn");
  assert.match(S.describe({workspace: ws, saveStatus: "full"}).storage.text, /storage is full/);
  assert.equal(S.describe({workspace: ws, saveStatus: "idle"}).storage.text, "Not saved yet");
});

check("values loading", () => {
  const m = S.describe({workspace: league(["Alpha"]), saveStatus: "saved", valuesReady: false});
  assert.equal(m.state, "loading");
  assert.match(m.notes[0], /still loading/);
});

check("no claim of sync, connection, accounts or completeness in any state", () => {
  const inputs = [{}, {workspace: league(["Alpha", "Bravo"]), saveStatus: "saved", origin: "stored"}, {workspace: league(["Alpha"]), origin: "loaded", saveStatus: "unavailable"},
    {workspace: league(["Alpha"]), origin: "pasted", parsed: {teams: [{name: "A", unmatched: ["x"], unsure: 2}], skipped: 0}}, {loadStatus: "corrupt"}, {workspace: league(["Alpha"]), valuesReady: false}];
  inputs.forEach(i => assert.ok(!BANNED.test(JSON.stringify(S.describe(i))), JSON.stringify(S.describe(i))));
});

check("originFor: hand edits keep where the league came from", () => {
  assert.equal(S.originFor(null, "load"), "stored");
  assert.equal(S.originFor("stored", "rename"), "stored");
  assert.equal(S.originFor("stored", "replace"), "loaded");
  assert.equal(S.originFor("loaded", "paste"), "pasted");
  assert.equal(S.originFor(null, "add"), null);
});

// ---------- mount(): the disclosure, wired to the real store ----------
function setup(initial, opts) {
  const storage = memoryStorage(initial);
  const store = newStore(storage);
  const doc = makeDoc();
  const host = doc.createElement("div");
  const controls = doc.createElement("div");
  controls.setAttribute("id", "editControls");
  const inner = doc.createElement("button");
  controls.append(inner);
  const status = S.mount(host, {store, document: doc, id: "lgs", controls, ...(opts || {})});
  return {storage, store, doc, host, controls, inner, status, node: id => host.byId(id)};
}
const saved = ws => ({[W.STORAGE_KEY]: W.serialize(ws)});

check("mount: empty league, expanded by default, disclosure semantics", () => {
  const t = setup();
  const toggle = t.node("lgsToggle");
  assert.equal(toggle.tagName, "BUTTON");
  assert.equal(toggle.getAttribute("aria-expanded"), "true");
  assert.equal(toggle.getAttribute("aria-controls"), "lgsBody");
  assert.equal(t.node("lgsBody").getAttribute("aria-labelledby"), "lgsToggle");
  assert.equal(toggle.getAttribute("aria-describedby"), "lgsSummary");
  assert.equal(t.node("lgs").getAttribute("data-state"), "empty");
  assert.ok(t.node("lgsBody").visible());
  assert.ok(t.controls.visible(), "edit controls reachable with no league");
});

check("mount: reload shows what was saved, and mounting writes nothing", () => {
  let ws = league(["Alpha", "Bravo", "Charlie"]);
  ws = W.ops.setMyTeam(ws, ws.teams[2].id);
  const t = setup(saved(ws));
  const before = t.storage.data.get(W.STORAGE_KEY);
  t.status.update("status");
  assert.equal(t.node("lgsSummary").textContent, "3 teams · 9 players · Your team: Charlie · Saved on this device");
  assert.equal(t.status.model().facts.find(f => f.id === "origin").value, "Read from this device");
  assert.equal(t.storage.data.get(W.STORAGE_KEY), before, "the status never writes to storage");
  // A second visit: a fresh store on the same storage reads the same league and star.
  const again = setup(Object.fromEntries(t.storage.data));
  assert.equal(again.node("lgsSummary").textContent, t.node("lgsSummary").textContent);
});

check("mount: rename, add and remove update the status; the live region speaks only on a real change", () => {
  const t = setup(saved(league(["Alpha", "Bravo"])));
  const live = t.node("lgsLive");
  t.status.update("status");
  assert.equal(live.textContent, "", "a save tick is quiet");
  const id = t.store.get().teams[0].id;
  t.store.update(w => W.ops.setMyTeam(w, id), "mine");
  assert.equal(live.textContent, "2 teams · 6 players. Your team: Alpha");
  t.store.update(w => W.ops.renameTeam(w, id, "Aces"), "rename");
  assert.match(t.node("lgsSummary").textContent, /Your team: Aces/);
  t.store.update(w => W.ops.addTeam(w, "Charlie"), "add");
  assert.match(t.node("lgsSummary").textContent, /^3 teams · 6 players/);
  assert.equal(t.status.model().state, "partial", "the new team has no players yet");
  assert.equal(t.status.model().facts.find(f => f.id === "origin").value, "Read from this device", "hand edits keep the origin");
});

check("mount: removing the starred team names it once; Undo clears the note; the status never re-stars", () => {
  let ws = league(["Alpha", "Bravo"]);
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  const t = setup(saved(ws));
  const prev = t.store.get();
  t.store.update(w => W.ops.removeTeam(w, prev.teams[0].id), "remove");
  assert.equal(t.store.get().myTeamId, null);
  assert.equal(t.status.model().mine.text, "Your team (Alpha) was removed. Star a team to mark yours.");
  assert.match(t.node("lgsSummary").textContent, /Your team was removed/);
  assert.equal(t.store.get().myTeamId, null, "no team was starred for the reader");
  t.store.replace(prev, "replace");
  assert.equal(t.status.model().mine.text, "Your team: Alpha");
  assert.equal(t.status.model().facts.find(f => f.id === "origin").value, "Loaded from a file or link this visit");
});

check("mount: unstarring is not a removal", () => {
  let ws = league(["Alpha", "Bravo"]);
  ws = W.ops.setMyTeam(ws, ws.teams[0].id);
  const t = setup(saved(ws));
  t.store.update(w => W.ops.setMyTeam(w, null), "mine");
  assert.equal(t.status.model().mine.text, "No team marked as yours yet");
});

check("mount: changed workspace from another file replaces counts and origin", () => {
  const t = setup(saved(league(["Alpha", "Bravo"])));
  t.store.replace(league(["One", "Two", "Three", "Four"], {name: "Office league"}), "replace");
  assert.equal(t.node("lgsToggle").textContent, "Office league");
  assert.match(t.node("lgsSummary").textContent, /^4 teams · 12 players · No team marked/);
});

check("mount: clearing the league then adding by hand has no origin", () => {
  const t = setup(saved(league(["Alpha"])));
  t.store.update(w => W.ops.clearLeague(w), "remove");
  assert.equal(t.status.model().state, "empty");
  t.store.update(w => W.ops.addTeam(w, "Fresh", {entries: [{key: "1", name: "A", pos: "WR"}]}), "add");
  assert.equal(t.status.model().facts.find(f => f.id === "origin"), undefined);
});

check("mount: paste reported by league.js", () => {
  const parsed = {teams: [{name: "Alpha", count: 3, unmatched: ["x"], unsure: 0}], skipped: 0};
  const t = setup(undefined, {parsed: () => parsed});
  t.store.update(w => W.ops.addTeam(w, "Alpha", {entries: [{key: "1", name: "A", pos: "WR"}]}), "add");
  t.status.update("paste");
  assert.equal(t.status.model().state, "partial");
  assert.equal(t.status.model().facts.find(f => f.id === "origin").value, "Read from your paste this visit");
});

check("mount: fold and open by button; summary stays; controls are the same node, not rebuilt", () => {
  const t = setup(saved(league(["Alpha"])));
  const toggle = t.node("lgsToggle");
  toggle.click();
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  assert.equal(t.node("lgsBody").hidden, true);
  assert.ok(t.node("lgsSummary").visible(), "the one-line summary shows while folded");
  assert.equal(t.node("lgs").getAttribute("data-expanded"), "false");
  // Navigation and redraws keep the reader's choice.
  t.store.update(w => W.ops.rename(w, "Renamed"), "rename");
  t.status.update("load");
  assert.equal(t.status.isExpanded(), false);
  toggle.click();
  assert.equal(toggle.getAttribute("aria-expanded"), "true");
  assert.equal(t.node("editControls"), t.controls, "the same controls node is still mounted");
  assert.ok(t.inner.visible());
});

check("mount: Escape in the body folds and returns focus; Escape inside an open menu is left to the menu", () => {
  const t = setup(saved(league(["Alpha"])));
  const menu = t.doc.createElement("button");
  menu.setAttribute("aria-expanded", "true");
  t.controls.append(menu);
  menu.focus();
  menu.dispatch("keydown", {key: "Escape"});
  assert.equal(t.status.isExpanded(), true, "an open menu keeps its Escape");
  t.inner.focus();
  t.inner.dispatch("keydown", {key: "Escape"});
  assert.equal(t.status.isExpanded(), false);
  assert.equal(t.doc.activeElement, t.node("lgsToggle"));
  t.inner.dispatch("keydown", {key: "Enter"});
  assert.equal(t.status.isExpanded(), false, "other keys do nothing");
});

check("mount: starts folded only when the caller asks", () => {
  const t = setup(saved(league(["Alpha"])), {expanded: false});
  assert.equal(t.node("lgsToggle").getAttribute("aria-expanded"), "false");
  let seen = null;
  const u = setup(saved(league(["Alpha"])), {onToggle: open => { seen = open; }});
  u.node("lgsToggle").click();
  assert.equal(seen, false);
});

check("mount: unavailable storage and unreadable saved data", () => {
  const doc = makeDoc();
  const host = doc.createElement("div");
  const store = W.createStore({storage: null, delay: 0});
  store.load();
  const st = S.mount(host, {store, document: doc, id: "x"});
  store.update(w => W.ops.addTeam(w, "Alpha", {entries: [{key: "1", name: "A", pos: "WR"}]}), "add");
  assert.match(st.model().storage.text, /^Not saved: this browser isn't keeping data/);
  const bad = setup({[W.STORAGE_KEY]: "{not json"});
  assert.equal(bad.status.model().state, "error");
  assert.ok(!BANNED.test(allText(bad.host)));
});

check("mount: destroy unsubscribes and removes", () => {
  const t = setup(saved(league(["Alpha"])));
  t.status.destroy();
  assert.equal(t.host.children.length, 0);
  t.store.update(w => W.ops.addTeam(w, "Bravo"), "add");
});

console.log(`league_status_check: ${checks} checks passed`);
