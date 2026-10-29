// Unit checks for manager profiles (JEG-1217 stages 1-2). Pure Node, no browser.
//   node manager_profiles_harness.cjs <dir with manager-profiles.js and workspace.js>
// Prints one JSON object: {ran: [names], failures: [{name, message}]}. tests/test_jeg1217_manager_profiles.py runs it on the
// real modules and, for every mutation, on a broken copy that it requires to fail.
"use strict";
const path = require("path");
const assert = require("assert");

const dir = path.resolve(process.argv[2]);
const M = require(path.join(dir, "manager-profiles.js"));
const W = require(path.join(dir, "workspace.js"));

const ran = [];
const failures = [];
function check(name, fn) {
  ran.push(name);
  try { fn(); } catch (error) { failures.push({name, message: String(error && error.message || error).slice(0, 400)}); }
}
function memoryStorage(initial) {
  const data = new Map(Object.entries(initial || {}));
  return {getItem: k => (data.has(k) ? data.get(k) : null), setItem: (k, v) => { data.set(k, String(v)); }, removeItem: k => { data.delete(k); }, data};
}
// A four-team league; two teams share a name on purpose.
function league() {
  let ws = W.newWorkspace({id: "league-a", name: "Test league"});
  ["Mine", "Alpha", "Twin", "Twin"].forEach((name, i) => { ws = W.ops.addTeam(ws, name, {id: `t${i}`, now: 1}); });
  return W.ops.setMyTeam(ws, "t0");
}

check("test_unknown_profile_is_default", () => {
  const ws = league();
  const p = M.get(M.emptyBook(), ws, "t1");
  assert.strictEqual(p.teamId, "t1");
  M.ANCHORS.forEach(a => assert.strictEqual(p.anchors[a], "unknown", a));
  assert.strictEqual(p.confidence, "unknown");
  assert.strictEqual(p.excluded, false);
  assert.deepStrictEqual(p.tags, [], "nothing ticked to start");
  assert.ok(!("note" in p), "no free-text field");
  assert.strictEqual(M.describe(p).kind, "unknown");
  assert.strictEqual(M.isBlank(p), true);
});

check("test_no_numeric_weights", () => {
  // Capture is qualitative: anchor levels are labels, never numbers, until Jeremy picks a mapping.
  M.LEVELS.concat(M.CONFIDENCE).forEach(level => assert.strictEqual(typeof level, "string"));
  let book = M.ops.setAnchor(M.emptyBook(), league(), "t1", "market", 0.8, 5);
  assert.strictEqual(M.get(book, league(), "t1").anchors.market, "unknown");
  book = M.ops.setAnchor(book, league(), "t1", "market", "strong", 5);
  assert.strictEqual(M.get(book, league(), "t1").anchors.market, "strong");
  assert.ok(!JSON.stringify(book).match(/"weight/i), "no weight fields");
});

check("test_describe_single_mixed_none", () => {
  const ws = league();
  let book = M.ops.setAnchor(M.emptyBook(), ws, "t1", "draft", "strong", 2);
  assert.strictEqual(M.describe(M.get(book, ws, "t1")).kind, "single");
  book = M.ops.setAnchor(book, ws, "t1", "names", "some", 3);
  const d = M.describe(M.get(book, ws, "t1"));
  assert.strictEqual(d.kind, "mixed");
  assert.deepStrictEqual(d.active, ["draft", "names"]);
  assert.deepStrictEqual(d.strong, ["draft"]);
  assert.deepStrictEqual(d.unknownAnchors, ["market", "rankings"]);
  let none = M.ops.setAnchor(M.emptyBook(), ws, "t2", "market", "none", 2);
  assert.strictEqual(M.describe(M.get(none, ws, "t2")).kind, "none");
});

check("test_exclusion_toggle", () => {
  const ws = league();
  let book = M.ops.toggleExcluded(M.emptyBook(), ws, "t1", 2);
  assert.strictEqual(M.get(book, ws, "t1").excluded, true);
  assert.deepStrictEqual(M.eligibleOpponents(book, ws).map(r => r.teamId), ["t2", "t3"]);
  const row = M.roster(book, ws).find(r => r.teamId === "t1");
  assert.strictEqual(row.eligible, false);
  assert.strictEqual(row.reason, "excluded");
  book = M.ops.toggleExcluded(book, ws, "t1", 3);
  assert.strictEqual(M.get(book, ws, "t1").excluded, false);
  assert.deepStrictEqual(M.eligibleOpponents(book, ws).map(r => r.teamId), ["t1", "t2", "t3"]);
  // Toggled back to nothing: nothing is kept.
  assert.deepStrictEqual(book.leagues, {});
});

check("test_my_team_never_eligible", () => {
  const ws = league();
  const book = M.ops.setAnchor(M.emptyBook(), ws, "t0", "market", "strong", 2);
  assert.ok(!M.eligibleOpponents(book, ws).some(r => r.teamId === "t0"));
  assert.strictEqual(M.roster(book, ws)[0].reason, "mine");
  // Marking another team as mine makes t0 a counterparty again, with its profile intact.
  const moved = W.ops.setMyTeam(ws, "t1");
  assert.ok(M.eligibleOpponents(book, moved).some(r => r.teamId === "t0" && r.profile.anchors.market === "strong"));
});

check("test_duplicate_names_keep_separate_profiles", () => {
  const ws = league();
  let book = M.ops.setAnchor(M.emptyBook(), ws, "t2", "names", "strong", 2);
  book = M.ops.setExcluded(book, ws, "t3", true, 2);
  assert.strictEqual(M.get(book, ws, "t2").anchors.names, "strong");
  assert.strictEqual(M.get(book, ws, "t2").excluded, false);
  assert.strictEqual(M.get(book, ws, "t3").anchors.names, "unknown");
  assert.strictEqual(M.get(book, ws, "t3").excluded, true);
});

check("test_rename_keeps_profile", () => {
  let ws = league();
  const book = M.ops.setAnchor(M.emptyBook(), ws, "t1", "rankings", "strong", 2);
  ws = W.ops.renameTeam(ws, "t1", "Alpha Renamed");
  const row = M.roster(book, ws).find(r => r.teamId === "t1");
  assert.strictEqual(row.name, "Alpha Renamed");
  assert.strictEqual(row.profile.anchors.rankings, "strong");
  assert.strictEqual(M.ops.reconcile(book, ws).dropped.length, 0);
});

check("test_removal_drops_profile", () => {
  let ws = league();
  let book = M.ops.setAnchor(M.emptyBook(), ws, "t1", "rankings", "strong", 2);
  book = M.ops.setTag(book, ws, "t2", "rookies", true, 2);
  ws = W.ops.removeTeam(ws, "t1");
  const out = M.ops.reconcile(book, ws);
  assert.deepStrictEqual(out.dropped, ["t1"]);
  assert.strictEqual(out.book.leagues["league-a"].t1, undefined);
  assert.deepStrictEqual(out.book.leagues["league-a"].t2.tags, ["rookies"]);
  // A new team with the same name gets a new id and starts unknown.
  ws = W.ops.addTeam(ws, "Alpha", {id: "t9"});
  assert.strictEqual(M.describe(M.get(out.book, ws, "t9")).kind, "unknown");
  // Writes to a team that is not in the league are ignored.
  assert.strictEqual(M.ops.setAnchor(out.book, ws, "t1", "draft", "strong", 3), out.book);
  // Clearing the league drops every profile for it.
  assert.deepStrictEqual(M.ops.reconcile(out.book, W.ops.clearLeague(ws)).book.leagues, {});
});

check("test_profiles_are_per_league", () => {
  const a = league();
  const b = {...league(), id: "league-b"};
  const book = M.ops.setExcluded(M.emptyBook(), a, "t1", true, 2);
  assert.strictEqual(M.get(book, a, "t1").excluded, true);
  assert.strictEqual(M.get(book, b, "t1").excluded, false);
});

check("test_unchanged_write_returns_same_book", () => {
  const ws = league();
  const book = M.ops.setConfidence(M.emptyBook(), ws, "t1", "high", 2);
  assert.strictEqual(M.ops.setConfidence(book, ws, "t1", "high", 9), book);
  assert.strictEqual(M.ops.setConfidence(book, ws, "t1", "sure", 9), book);
  assert.strictEqual(M.get(book, ws, "t1").updatedAt, 2);
  assert.strictEqual(M.get(M.ops.setConfidence(book, ws, "t1", "low", 9), ws, "t1").updatedAt, 9);
});

check("test_tags_fixed_list_no_free_text", () => {
  const ws = league();
  assert.deepStrictEqual(M.TAGS.map(tag => M.TAG_LABELS[tag]), ["Likes rookies", "Wants draft picks", "Win-now", "Rebuilding", "Slow to reply", "Rarely trades"]);
  assert.strictEqual(M.ops.setNote, undefined, "no note to write");
  let book = M.ops.setTag(M.emptyBook(), ws, "t1", "rarelyTrades", true, 2);
  book = M.ops.setTag(book, ws, "t1", "rookies", true, 2);
  assert.deepStrictEqual(M.get(book, ws, "t1").tags, ["rookies", "rarelyTrades"], "kept in list order");
  assert.strictEqual(M.ops.setTag(book, ws, "t1", "rookies", true, 3), book, "ticking twice changes nothing");
  assert.strictEqual(M.ops.setTag(book, ws, "t1", "Loves young players", true, 3), book, "free text is not a tag");
  assert.strictEqual(M.isBlank(M.get(book, ws, "t1")), false);
  book = M.ops.setTag(book, ws, "t1", "rookies", false, 4);
  book = M.ops.setTag(book, ws, "t1", "rarelyTrades", false, 4);
  assert.strictEqual(book.leagues["league-a"], undefined, "unticking everything is back to the default");
});

check("test_store_reload", () => {
  const ws = league();
  const storage = memoryStorage();
  const s1 = M.createStore({storage, delay: 0});
  assert.strictEqual(s1.load(), "empty");
  s1.update(b => M.ops.setAnchor(b, ws, "t1", "draft", "strong", 2));
  s1.update(b => M.ops.setExcluded(b, ws, "t3", true, 2));
  assert.strictEqual(s1.status(), "saved");
  const s2 = M.createStore({storage, delay: 0});
  assert.strictEqual(s2.load(), "ok");
  assert.deepStrictEqual(s2.get(), s1.get());
  assert.strictEqual(M.get(s2.get(), ws, "t1").anchors.draft, "strong");
  assert.strictEqual(M.get(s2.get(), ws, "t3").excluded, true);
});

check("test_store_debounce", () => {
  const ws = league();
  const storage = memoryStorage();
  const timers = [];
  const store = M.createStore({storage, delay: 1000, setTimer: fn => { timers.push(fn); return timers.length; }, clearTimer: () => {}});
  store.load();
  store.update(b => M.ops.setConfidence(b, ws, "t1", "low", 2));
  assert.strictEqual(store.status(), "saving");
  assert.strictEqual(storage.getItem(M.STORAGE_KEY), null);
  timers[timers.length - 1]();
  assert.strictEqual(store.status(), "saved");
  assert.ok(storage.getItem(M.STORAGE_KEY));
});

check("test_store_corrupt_and_version_not_overwritten", () => {
  ["{not json", JSON.stringify({v: 99, leagues: {}}), JSON.stringify([1, 2])].forEach(text => {
    const storage = memoryStorage({[M.STORAGE_KEY]: text});
    const store = M.createStore({storage, delay: 0});
    const status = store.load();
    assert.ok(status === "corrupt" || status === "version", status);
    assert.deepStrictEqual(store.get().leagues, {});
    store.flush();
    assert.strictEqual(storage.getItem(M.STORAGE_KEY), text, "kept until the reader changes something");
  });
});

check("test_store_unavailable", () => {
  const store = M.createStore({storage: null, delay: 0});
  assert.strictEqual(store.load(), "unavailable");
  store.update(b => M.ops.setConfidence(b, league(), "t1", "low", 2));
  assert.strictEqual(store.status(), "unavailable");
  assert.strictEqual(M.get(store.get(), league(), "t1").confidence, "low", "still usable for this visit");
});

check("test_store_other_tab", () => {
  const ws = league();
  const storage = memoryStorage();
  const a = M.createStore({storage, delay: 0});
  const b = M.createStore({storage, delay: 0});
  a.load(); b.load();
  const seen = [];
  b.onChange((_, change) => seen.push(change.reason));
  a.update(x => M.ops.setExcluded(x, ws, "t2", true, 2));
  b.reloadFromStorage();
  assert.deepStrictEqual(seen, ["other-tab"]);
  assert.strictEqual(M.get(b.get(), ws, "t2").excluded, true);
});

check("test_legacy_and_partial_state", () => {
  // An older or hand-edited profile with missing or unknown fields loads with "unknown" in their place.
  const text = JSON.stringify({v: 1, leagues: {"league-a": {t1: {anchors: {draft: "strong", market: "huge", rankings: 0.7}, excluded: "yes", createdAt: 5,
    tags: ["rookies", "bogus", "rookies", 3]}, t2: {anchors: {}}, t3: "junk", t4: {anchors: {subjective: "strong"}, note: "loves rookies"}}, "league-z": []}});
  const parsed = M.parseStored(text);
  assert.strictEqual(parsed.status, "ok");
  const ws = league();
  const p = M.get(parsed.book, ws, "t1");
  assert.strictEqual(p.anchors.draft, "strong");
  assert.strictEqual(p.anchors.market, "unknown");
  assert.strictEqual(p.anchors.rankings, "unknown", "a number is never a level");
  assert.strictEqual(p.excluded, false, "only a literal true excludes");
  assert.strictEqual(p.createdAt, 5);
  assert.deepStrictEqual(p.tags, ["rookies"], "only known tags, once each");
  assert.deepStrictEqual(Object.keys(parsed.book.leagues), ["league-a"]);
  // JEG-1255: an earlier build's note and Other preferences level are kept, not dropped (was: dropped, a rule the review reversed).
  assert.deepStrictEqual(Object.keys(parsed.book.leagues["league-a"]), ["t1", "t4"], "blank and junk profiles are not kept; a note-only one is");
  const kept = M.get(parsed.book, ws, "t4");
  assert.strictEqual(kept.note, "loves rookies");
  assert.strictEqual(kept.anchors.subjective, "strong");
  assert.strictEqual(M.describe(kept).kind, "unknown", "a kept level is not one of the anchors");
  // A league saved before profiles existed has every team unknown and eligible.
  assert.deepStrictEqual(M.eligibleOpponents(M.emptyBook(), ws).map(r => r.description.kind), ["unknown", "unknown", "unknown"]);
});

// A store over storage whose setItem can be made to fail, and recover.
function flakyStorage(initial) {
  const s = memoryStorage(initial);
  s.fail = null;
  const set = s.setItem;
  s.setItem = (k, v) => {
    if (s.fail === "full") { const e = new Error("quota"); e.name = "QuotaExceededError"; throw e; }
    if (s.fail === "blocked") { const e = new Error("denied"); e.name = "SecurityError"; throw e; }
    set(k, v);
  };
  return s;
}

check("test_legacy_note_round_trip", () => {
  // A book saved by the earlier build of this same version (a1e62342): a free-text note and an Other preferences level.
  const ws = league();
  const note = "Loves rookies, hates paying for QBs";
  const saved = JSON.stringify({v: 1, leagues: {"league-a": {
    t1: {teamId: "t1", anchors: {draft: "some", market: "unknown", rankings: "unknown", names: "unknown", subjective: "strong"}, confidence: "low",
      excluded: false, note, source: "user", createdAt: 3, updatedAt: 4},
    t2: {teamId: "t2", anchors: {draft: "unknown", market: "unknown", rankings: "unknown", names: "unknown", subjective: "unknown"}, confidence: "unknown",
      excluded: false, note: "slow but fair", source: "user", createdAt: 3, updatedAt: 4}}}});
  const storage = flakyStorage({[M.STORAGE_KEY]: saved});
  const store = M.createStore({storage, delay: 0});
  assert.strictEqual(store.load(), "ok");
  const p1 = M.get(store.get(), ws, "t1");
  assert.strictEqual(p1.note, note, "note kept verbatim");
  assert.strictEqual(p1.anchors.subjective, "strong", "Other preferences level kept");
  assert.strictEqual(p1.anchors.draft, "some");
  assert.strictEqual(M.get(store.get(), ws, "t2").note, "slow but fair", "a note-only profile is not blank");
  assert.deepStrictEqual(M.legacyOf(p1), {note, subjective: "strong"});
  // Ticking boxes, changing an anchor or excluding never touches what was kept.
  store.update(b => M.ops.setTag(b, ws, "t1", "rookies", true, 5));
  store.update(b => M.ops.setAnchor(b, ws, "t1", "market", "strong", 5));
  store.update(b => M.ops.setExcluded(b, ws, "t2", true, 5));
  store.update(b => M.ops.setExcluded(b, ws, "t2", false, 6));
  const after = M.get(store.get(), ws, "t1");
  assert.strictEqual(after.note, note);
  assert.strictEqual(after.anchors.subjective, "strong");
  assert.deepStrictEqual(after.tags, ["rookies"]);
  assert.strictEqual(M.get(store.get(), ws, "t2").note, "slow but fair");
  // Saved and loaded again: unchanged; and readable field-for-field by the earlier build (same names: note, anchors.subjective).
  const raw = JSON.parse(storage.getItem(M.STORAGE_KEY));
  assert.strictEqual(raw.v, 1);
  assert.strictEqual(raw.leagues["league-a"].t1.note, note);
  assert.strictEqual(raw.leagues["league-a"].t1.anchors.subjective, "strong");
  const again = M.createStore({storage, delay: 0});
  again.load();
  assert.deepStrictEqual(again.get(), store.get());
  // Export and import carry it too.
  const out = M.importJson(M.emptyBook(), ws, M.exportJson(store.get(), ws));
  assert.strictEqual(M.get(out.book, ws, "t1").note, note);
  assert.strictEqual(M.get(out.book, ws, "t1").anchors.subjective, "strong");
  // Nothing new can be written there: no note op, and setAnchor refuses the kept level.
  assert.strictEqual(M.ops.setNote, undefined);
  assert.strictEqual(M.ops.setAnchor(store.get(), ws, "t1", "subjective", "none", 7), store.get());
  // Only an explicit Clear removes it.
  store.update(b => M.ops.reset(b, ws, "t1"));
  assert.ok(!("note" in M.get(store.get(), ws, "t1")));
});

check("test_store_save_failure_reported_and_recovers", () => {
  const ws = league();
  const storage = flakyStorage();
  const timers = [];
  const store = M.createStore({storage, delay: 1000, setTimer: fn => { timers.push(fn); return timers.length; }, clearTimer: () => {}});
  const seen = [];
  store.onStatus(state => seen.push(state));
  store.load();
  storage.fail = "full";
  store.update(b => M.ops.setConfidence(b, ws, "t1", "low", 2));
  timers.pop()();   // the delayed save runs later and fails
  assert.strictEqual(store.status(), "full");
  assert.deepStrictEqual(seen, ["saving", "full"], "a delayed failure is announced");
  assert.strictEqual(storage.getItem(M.STORAGE_KEY), null);
  assert.strictEqual(M.get(store.get(), ws, "t1").confidence, "low", "still usable for this visit");
  storage.fail = "blocked";
  assert.strictEqual(store.flush(), false);
  assert.strictEqual(store.status(), "unavailable");
  // Recovery: the next save writes everything that was pending.
  storage.fail = null;
  store.update(b => M.ops.setExcluded(b, ws, "t2", true, 3));
  timers.pop()();
  assert.strictEqual(store.status(), "saved");
  assert.deepStrictEqual(seen, ["saving", "full", "unavailable", "saving", "saved"]);
  const stored = M.parseStored(storage.getItem(M.STORAGE_KEY)).book;
  assert.strictEqual(M.get(stored, ws, "t1").confidence, "low", "the earlier failed change is saved too");
  assert.strictEqual(M.get(stored, ws, "t2").excluded, true);
});

check("test_profiles_do_not_touch_workspace", () => {
  // Profiles live under their own key; the saved league text is unchanged by any profile write.
  const ws = league();
  const before = W.serialize(ws);
  M.ops.setExcluded(M.emptyBook(), ws, "t1", true, 2);
  assert.strictEqual(W.serialize(ws), before);
  assert.notStrictEqual(M.STORAGE_KEY, W.STORAGE_KEY);
});

check("test_export_import_round_trip", () => {
  const ws = league();
  let book = M.ops.setAnchor(M.emptyBook(), ws, "t1", "market", "strong", 2);
  book = M.ops.setExcluded(book, ws, "t3", true, 2);
  book = M.ops.setTag(book, ws, "t3", "winNow", true, 2);
  const text = M.exportJson(book, ws);
  const data = JSON.parse(text);
  assert.strictEqual(data.kind, "ddf.managerProfiles");
  assert.deepStrictEqual(data.teams.map(t => t.teamId), ["t1", "t3"]);
  const out = M.importJson(M.emptyBook(), ws, text);
  assert.strictEqual(out.error, undefined);
  assert.strictEqual(out.matched, 2);
  assert.deepStrictEqual(out.book.leagues, book.leagues);
});

check("test_import_matches_by_unique_name_only", () => {
  const ws = league();
  let book = M.ops.setAnchor(M.emptyBook(), ws, "t1", "market", "strong", 2);
  book = M.ops.setAnchor(book, ws, "t2", "names", "strong", 2);
  const text = M.exportJson(book, ws);
  // The same league loaded from a link gets new team ids.
  let other = W.newWorkspace({id: "league-b"});
  ["Mine", "Alpha", "Twin", "Twin"].forEach((name, i) => { other = W.ops.addTeam(other, name, {id: `n${i}`}); });
  const out = M.importJson(M.emptyBook(), other, text);
  assert.strictEqual(out.matched, 1);
  assert.strictEqual(M.get(out.book, other, "n1").anchors.market, "strong");
  assert.deepStrictEqual(out.unmatched, ["Twin"], "a duplicated name never matches by name");
  assert.strictEqual(M.get(out.book, other, "n2").anchors.names, "unknown");
  assert.strictEqual(M.get(out.book, other, "n3").anchors.names, "unknown");
});

check("test_import_rejects_bad_files", () => {
  const ws = league();
  const book = M.emptyBook();
  [["{", "not valid JSON"], [JSON.stringify({teams: []}), "not a saved set"], [JSON.stringify({kind: "ddf.managerProfiles", v: 2, teams: []}), "newer version"],
    [W.exportJson(ws), "not a saved set"]].forEach(([text, message]) => {
    const out = M.importJson(book, ws, text);
    assert.ok(out.error && out.error.includes(message), `${message}: ${out.error}`);
    assert.strictEqual(out.book, book);
  });
});

process.stdout.write(JSON.stringify({ran, failures}));
