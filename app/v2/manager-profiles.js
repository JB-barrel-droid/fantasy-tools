// Trade Value v2 — manager profiles for manager-aware trade recommendations (JEG-1217, stages 1-2).
//
// What the reader believes about how each opposing manager values players. These are the reader's own subjective
// beliefs, never verified facts about a manager and never an acceptance probability. Pure data and a small store; no
// DOM, no engine values, no weights and no ranking. One profile per team in the saved league, keyed by the stable
// workspace team id (workspace.js), so a rename keeps the profile and a removed team's profile is dropped.
//
//   Profile: {teamId, anchors: {draft, market, rankings, names}, confidence, excluded, tags,
//             source: "user", createdAt, updatedAt}
//   Anchor levels are ordinal labels only: "unknown" | "none" | "some" | "strong". Mapping them to numbers is a
//   separate decision for Jeremy (JEG-1217 stage 3) and does not live here.
//   confidence: how sure the reader is of this profile: "unknown" | "low" | "medium" | "high".
//   excluded: true when the reader says this manager will not trade. Excluded teams are left out of recommendations.
//   tags: fixed checkboxes for other leanings (TAGS), in TAGS order. No free text (Jeremy, 2026-10-29: no text boxes for
//   how league-mates trade, everyone starts at the default). Every manager starts with nothing marked.
//   Kept from an earlier build of this same version: a free-text note and an "Other preferences" level (anchors.subjective).
//   They can no longer be entered, but a saved one is kept verbatim and shown read-only until the reader clears the profile
//   (JEG-1255: no silent deletion while VERSION stays 1). They never change a number.
//
// Saved in this browser only (localStorage key ddf.v2.managerProfiles, versioned), separately from the league so an
// older build that rewrites ddf.v2.workspaces cannot drop profiles. A corrupt or unknown-version value is ignored,
// reported, and not overwritten until the reader changes something (the workspace.js convention).
(function (root) {
  "use strict";

  const STORAGE_KEY = "ddf.v2.managerProfiles";
  const VERSION = 1;
  const SAVE_DELAY_MS = 1000;
  const MAX_NOTE = 280;   // the earlier build's limit, so a note it saved is kept whole
  const LEGACY_ANCHOR = "subjective";
  const ANCHORS = ["draft", "market", "rankings", "names"];
  const ANCHOR_LABELS = {draft: "Draft capital", market: "Market and trade charts", rankings: "Player rankings", names: "Big names"};
  const TAGS = ["rookies", "picks", "winNow", "rebuilding", "slowReply", "rarelyTrades"];
  const TAG_LABELS = {rookies: "Likes rookies", picks: "Wants draft picks", winNow: "Win-now", rebuilding: "Rebuilding",
    slowReply: "Slow to reply", rarelyTrades: "Rarely trades"};
  const LEVELS = ["unknown", "none", "some", "strong"];
  const CONFIDENCE = ["unknown", "low", "medium", "high"];

  const isObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  const clone = value => JSON.parse(JSON.stringify(value));
  const pick = (value, allowed) => (allowed.includes(value) ? value : allowed[0]);
  const cleanTags = list => (Array.isArray(list) ? TAGS.filter(tag => list.includes(tag)) : []);
  const cleanNote = text => String(text == null ? "" : text).replace(/\s+/g, " ").trim().slice(0, MAX_NOTE);
  const time = (value, fallback) => (Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : fallback);

  // ---------- shapes ----------
  function newProfile(teamId, opts) {
    const o = opts || {};
    const now = o.now || Date.now();
    return {teamId: String(teamId), anchors: Object.fromEntries(ANCHORS.map(a => [a, "unknown"])), confidence: "unknown", excluded: false, tags: [],
      source: "user", createdAt: now, updatedAt: now};
  }
  // Fills anything missing so a profile saved by an older build still loads. Unknown fields and levels fall back to
  // "unknown"; nothing is guessed. An earlier note and "Other preferences" level are kept as saved (see above).
  function normalizeProfile(raw, teamId, now) {
    if (!isObject(raw)) return null;
    const id = String(teamId == null ? raw.teamId : teamId);
    if (!id || id === "undefined" || id === "null") return null;
    const base = newProfile(id, {now: time(raw.createdAt, now || Date.now())});
    const anchors = isObject(raw.anchors) ? raw.anchors : {};
    const kept = pick(anchors[LEGACY_ANCHOR], LEVELS);
    const note = cleanNote(raw.note);
    return {...base, anchors: {...Object.fromEntries(ANCHORS.map(a => [a, pick(anchors[a], LEVELS)])), ...(kept !== "unknown" ? {[LEGACY_ANCHOR]: kept} : {})},
      confidence: pick(raw.confidence, CONFIDENCE), excluded: raw.excluded === true, tags: cleanTags(raw.tags), ...(note ? {note} : {}),
      updatedAt: time(raw.updatedAt, base.createdAt)};
  }
  // What an earlier build saved that can no longer be entered: {note, subjective}, each null when absent.
  const legacyOf = p => ({note: (p && p.note) || null, subjective: (p && p.anchors && p.anchors[LEGACY_ANCHOR]) || null});
  // A profile that says nothing: every anchor unknown, no confidence, not excluded, nothing ticked and nothing kept. Saved as nothing.
  const isBlank = p => !p || (!p.excluded && !p.tags.length && p.confidence === "unknown" && ANCHORS.every(a => p.anchors[a] === "unknown")
    && !legacyOf(p).note && !legacyOf(p).subjective);

  // How the reader described this manager, for labels and later explanations. "unknown" when nothing is set,
  // "single" when exactly one anchor is above "none", "mixed" when two or more are, "none" when every set anchor is "none".
  function describe(profile) {
    const p = profile || newProfile("");
    const known = ANCHORS.filter(a => p.anchors[a] !== "unknown");
    const active = ANCHORS.filter(a => p.anchors[a] === "some" || p.anchors[a] === "strong");
    const kind = !known.length ? "unknown" : active.length === 0 ? "none" : active.length === 1 ? "single" : "mixed";
    return {kind, active, strong: active.filter(a => p.anchors[a] === "strong"), unknownAnchors: ANCHORS.filter(a => p.anchors[a] === "unknown"),
      confidence: p.confidence, excluded: p.excluded, tags: p.tags.slice(), legacy: legacyOf(p)};
  }

  // ---------- the profile book: {v, leagues: {workspaceId: {teamId: profile}}} ----------
  const emptyBook = () => ({v: VERSION, leagues: {}});
  function normalizeBook(raw) {
    if (!isObject(raw) || raw.v !== VERSION || !isObject(raw.leagues)) return null;
    const leagues = {};
    Object.keys(raw.leagues).forEach(wsId => {
      const teams = raw.leagues[wsId];
      if (!isObject(teams)) return;
      const out = {};
      Object.keys(teams).forEach(teamId => {
        const p = normalizeProfile(teams[teamId], teamId);
        if (p && !isBlank(p)) out[teamId] = p;
      });
      if (Object.keys(out).length) leagues[String(wsId)] = out;
    });
    return {v: VERSION, leagues};
  }

  // ---------- pure operations: each returns a new book (the same object when nothing changed) ----------
  const teamIds = ws => new Set((ws && Array.isArray(ws.teams) ? ws.teams : []).map(t => String(t.id)));
  // The profile for a team: the saved one, or a fresh unknown profile. Never null for a team in the league.
  function get(book, ws, teamId) {
    const saved = book.leagues[ws.id] && book.leagues[ws.id][String(teamId)];
    return saved ? clone(saved) : newProfile(teamId);
  }
  function put(book, ws, teamId, profile) {
    const id = String(teamId);
    if (!teamIds(ws).has(id)) return book;   // a team that is not in this league gets no profile
    const league = {...(book.leagues[ws.id] || {})};
    if (isBlank(profile)) delete league[id];
    else league[id] = profile;
    const leagues = {...book.leagues};
    if (Object.keys(league).length) leagues[ws.id] = league;
    else delete leagues[ws.id];
    return {...book, leagues};
  }
  function change(book, ws, teamId, fn, now) {
    const before = get(book, ws, teamId);
    const next = fn(before);
    if (JSON.stringify({...next, updatedAt: 0}) === JSON.stringify({...before, updatedAt: 0})) return book;
    return put(book, ws, teamId, {...next, updatedAt: now || Date.now()});
  }
  const ops = {
    setAnchor: (book, ws, teamId, anchor, level, now) => (ANCHORS.includes(anchor) && LEVELS.includes(level)
      ? change(book, ws, teamId, p => ({...p, anchors: {...p.anchors, [anchor]: level}}), now) : book),
    setConfidence: (book, ws, teamId, level, now) => (CONFIDENCE.includes(level) ? change(book, ws, teamId, p => ({...p, confidence: level}), now) : book),
    setExcluded: (book, ws, teamId, excluded, now) => change(book, ws, teamId, p => ({...p, excluded: excluded === true}), now),
    toggleExcluded: (book, ws, teamId, now) => change(book, ws, teamId, p => ({...p, excluded: !p.excluded}), now),
    setTag: (book, ws, teamId, tag, on, now) => (TAGS.includes(tag)
      ? change(book, ws, teamId, p => ({...p, tags: cleanTags(on === true ? p.tags.concat([tag]) : p.tags.filter(x => x !== tag))}), now) : book),
    reset: (book, ws, teamId) => put(book, ws, teamId, null),
    // Drops profiles for teams no longer in the league (removed, cleared, or a league replaced by a file or link).
    // Returns {book, dropped: [teamId]}. A team added later gets a new id, so an old profile never attaches to it.
    reconcile(book, ws) {
      const league = book.leagues[ws.id];
      if (!league) return {book, dropped: []};
      const ids = teamIds(ws);
      const dropped = Object.keys(league).filter(id => !ids.has(id));
      if (!dropped.length) return {book, dropped};
      const kept = Object.fromEntries(Object.entries(league).filter(([id]) => ids.has(id)));
      const leagues = {...book.leagues};
      if (Object.keys(kept).length) leagues[ws.id] = kept;
      else delete leagues[ws.id];
      return {book: {...book, leagues}, dropped};
    }
  };

  // Every team in the league with its profile, display name from the league (so a rename shows at once). The reader's
  // own team is marked mine and is never a counterparty; excluded teams stay listed but are not eligible.
  function roster(book, ws) {
    return (ws.teams || []).map(t => {
      const profile = get(book, ws, t.id);
      const mine = String(ws.myTeamId) === String(t.id);
      return {teamId: String(t.id), name: t.name, mine, profile, description: describe(profile), eligible: !mine && !profile.excluded,
        reason: mine ? "mine" : profile.excluded ? "excluded" : null};
    });
  }
  // The counterparties a recommendation may use: every team except the reader's own and the ones marked as nontraders.
  const eligibleOpponents = (book, ws) => roster(book, ws).filter(r => r.eligible);

  // ---------- storage text ----------
  // status: "empty" | "ok" | "corrupt" | "version", as in workspace.js.
  function parseStored(text) {
    if (text === null || text === undefined || text === "") return {status: "empty", book: emptyBook()};
    let data;
    try { data = JSON.parse(text); } catch (error) { return {status: "corrupt", book: emptyBook()}; }
    if (!isObject(data)) return {status: "corrupt", book: emptyBook()};
    if (data.v !== VERSION) return {status: "version", book: emptyBook()};
    const book = normalizeBook(data);
    return book ? {status: "ok", book} : {status: "corrupt", book: emptyBook()};
  }
  const serialize = book => JSON.stringify(book);

  // Export: one league's profiles, {kind, v, workspaceId, teams: [{teamId, name, profile}]}. Names travel so an import
  // into a different saved league can match by name when the ids differ.
  function exportJson(book, ws) {
    const teams = roster(book, ws).filter(r => !isBlank(r.profile)).map(r => ({teamId: r.teamId, name: r.name, profile: r.profile}));
    return JSON.stringify({kind: "ddf.managerProfiles", v: VERSION, workspaceId: ws.id, teams}, null, 2);
  }
  // Import into the current league. A profile matches a team by id first; failing that, by a name that exactly one team
  // in each list has (duplicate names never match by name). Returns {book, matched, unmatched: [name], error?}.
  function importJson(book, ws, text) {
    let data;
    try { data = JSON.parse(text); } catch (error) { return {book, matched: 0, unmatched: [], error: "That file is not valid JSON."}; }
    if (!isObject(data) || data.kind !== "ddf.managerProfiles" || !Array.isArray(data.teams)) {
      return {book, matched: 0, unmatched: [], error: "That file is not a saved set of manager profiles."};
    }
    if (data.v !== VERSION) return {book, matched: 0, unmatched: [], error: "Those manager profiles were saved by a newer version of this page."};
    const ids = teamIds(ws);
    const count = (list, name) => list.filter(n => n === name).length;
    const leagueNames = (ws.teams || []).map(t => t.name);
    const fileNames = data.teams.map(t => (isObject(t) ? String(t.name || "") : ""));
    let next = book;
    let matched = 0;
    const unmatched = [];
    data.teams.forEach(item => {
      if (!isObject(item)) return;
      const name = String(item.name || "");
      let id = ids.has(String(item.teamId)) ? String(item.teamId) : null;
      if (!id && name && count(leagueNames, name) === 1 && count(fileNames, name) === 1) id = String(ws.teams.find(t => t.name === name).id);
      const profile = id && normalizeProfile(item.profile, id);
      if (!profile) { unmatched.push(name || "Unnamed team"); return; }
      next = put(next, ws, id, profile);
      matched += 1;
    });
    return {book: next, matched, unmatched};
  }

  // Another tab saved while this tab had an unsaved edit (JEG-1318). Three-way merge from the book both last agreed on:
  // a value only one side changed takes that side's; a value both changed takes this tab's (its edit is the later one);
  // ticked boxes combine box by box. Returns a book for normalizeBook, so blank profiles drop out.
  const same = (x, y) => JSON.stringify(x) === JSON.stringify(y);
  function merge3(base, mine, theirs) {
    if (same(mine, base)) return theirs;
    if (same(theirs, base) || same(mine, theirs)) return mine;
    if (Array.isArray(mine) && Array.isArray(theirs)) {
      const was = Array.isArray(base) ? base : [];
      return [...new Set(mine.concat(theirs))].filter(x => (mine.includes(x) !== was.includes(x) ? mine.includes(x) : theirs.includes(x)));
    }
    if (isObject(mine) && isObject(theirs)) {
      const was = isObject(base) ? base : {};
      const out = {};
      new Set([...Object.keys(was), ...Object.keys(mine), ...Object.keys(theirs)]).forEach(k => {
        const v = merge3(was[k], mine[k], theirs[k]);
        if (v !== undefined) out[k] = v;
      });
      return out;
    }
    return mine;
  }
  // Merges whole books profile by profile. A blank profile and an empty league are never stored, so a missing one is read
  // as the blank profile (JEG-1339): a first mark, a reset or an untick that blanks a manager then merges field by field
  // like any other change instead of one side winning the whole manager.
  function mergeBook(base, mine, theirs) {
    // A missing profile takes the base's timestamps, so being absent is not itself read as a change.
    const blank = (teamId, ref) => ({...newProfile(teamId), createdAt: ref ? ref.createdAt : 0, updatedAt: ref ? ref.updatedAt : 0});
    const leagues = {};
    new Set([base, mine, theirs].flatMap(b => Object.keys(b.leagues))).forEach(wsId => {
      const sides = [base, mine, theirs].map(b => b.leagues[wsId] || {});
      const out = {};
      new Set(sides.flatMap(Object.keys)).forEach(teamId => {
        const [b, m, t] = sides.map(league => league[teamId] || blank(teamId, sides[0][teamId]));
        out[teamId] = merge3(b, m, t);
      });
      leagues[wsId] = out;
    });
    return normalizeBook({v: VERSION, leagues}) || mine;
  }

  // ---------- the store ----------
  // opts: {storage, delay, setTimer, clearTimer}. status(): "idle" | "saving" | "saved" | "unavailable" | "full".
  // onStatus(fn) hears every change of status, including a delayed save that fails, so the page never claims "saved"
  // when it is not. A failed save stays dirty and is retried on the next change or flush.
  // reloadFromStorage() takes another tab's save; an edit still waiting to be written here is merged in, not dropped.
  function createStore(opts) {
    const o = opts || {};
    const delay = o.delay === undefined ? SAVE_DELAY_MS : o.delay;
    const setTimer = o.setTimer || ((fn, ms) => root.setTimeout(fn, ms));
    const clearTimer = o.clearTimer || (id => root.clearTimeout(id));
    let storage = o.storage === undefined ? safeStorage() : o.storage;
    let book = emptyBook();
    let shared = book;   // the book this tab last read from or wrote to storage: the base for a merge (JEG-1318)
    let loadStatus = "empty";
    let timer = null;
    let dirty = false;
    let state = "idle";
    const listeners = new Set();
    const statusListeners = new Set();
    const setState = next => {
      if (next === state) return;
      state = next;
      statusListeners.forEach(fn => { try { fn(state); } catch (error) { /* a listener must not stop the save */ } });
    };
    // Folds another tab's saved book into this tab's: merged with an unsaved edit here, taken as is otherwise. Returns
    // true when this tab's book changed.
    function absorb(theirs) {
      const next = dirty ? mergeBook(shared, book, theirs) : theirs;
      shared = theirs;
      if (serialize(next) === serialize(book)) return false;
      book = next;
      return true;
    }
    // Another tab's save this tab has not heard about yet (its storage event can come after this tab's timer), or null.
    function unheard() {
      let text = null;
      try { text = storage.getItem(STORAGE_KEY); } catch (error) { return null; }
      const parsed = parseStored(text);
      return parsed.status === "ok" && serialize(parsed.book) !== serialize(shared) ? parsed.book : null;
    }
    function write() {
      timer = null;
      if (!dirty) return true;
      if (!storage) { setState("unavailable"); return false; }
      const theirs = unheard();   // JEG-1339: never write over a save not yet merged
      if (theirs && absorb(theirs)) notify("other-tab");
      try {
        storage.setItem(STORAGE_KEY, serialize(book));
        dirty = false;
        shared = book;
        setState("saved");
        return true;
      } catch (error) {
        const full = error && (error.name === "QuotaExceededError" || error.code === 22 || error.code === 1014);
        setState(full ? "full" : "unavailable");
        return false;
      }
    }
    function schedule() {
      dirty = true;
      if (!storage) { setState("unavailable"); return; }
      setState("saving");
      if (timer !== null) clearTimer(timer);
      timer = delay > 0 ? setTimer(write, delay) : null;
      if (delay <= 0) write();
    }
    const notify = reason => listeners.forEach(fn => { try { fn(book, {reason}); } catch (error) { /* a listener must not stop the save */ } });
    const api = {
      STORAGE_KEY,
      load() {
        let text = null;
        if (!storage) loadStatus = "unavailable";
        else {
          try { text = storage.getItem(STORAGE_KEY); } catch (error) { storage = null; loadStatus = "unavailable"; }
          if (storage) {
            const parsed = parseStored(text);
            loadStatus = parsed.status;
            book = parsed.book;
            shared = book;
          }
        }
        setState(loadStatus === "unavailable" ? "unavailable" : loadStatus === "ok" ? "saved" : "idle");
        notify("load");
        return loadStatus;
      },
      loadStatus: () => loadStatus,
      get: () => book,
      status: () => state,
      // fn(book) returns the new book; nothing is saved when it returns the same object.
      update(fn, reason) {
        const next = fn(book);
        if (!next || next === book) return book;
        book = next;
        schedule();
        notify(reason || "change");
        return book;
      },
      flush() { if (timer !== null) { clearTimer(timer); timer = null; } return write(); },
      onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
      onStatus(fn) { statusListeners.add(fn); return () => statusListeners.delete(fn); },
      reloadFromStorage() {
        if (!storage) return;
        let text = null;
        try { text = storage.getItem(STORAGE_KEY); } catch (error) { return; }
        const parsed = parseStored(text);
        if (parsed.status !== "ok") return;
        // An unsaved edit here is merged onto the other tab's book and stays owed, never dropped (JEG-1318).
        const changed = absorb(parsed.book);
        if (dirty && serialize(book) === serialize(shared)) {   // storage already holds this edit: nothing is owed
          dirty = false;
          if (timer !== null) { clearTimer(timer); timer = null; }
          setState("saved");
        }
        if (changed) notify("other-tab");
      }
    };
    return api;
  }
  function safeStorage() {
    try {
      const s = root.localStorage;
      if (!s) return null;
      const probe = "ddf.v2.probe";
      s.setItem(probe, "1");
      s.removeItem(probe);
      return s;
    } catch (error) { return null; }
  }

  const api = {STORAGE_KEY, VERSION, ANCHORS, ANCHOR_LABELS, LEVELS, CONFIDENCE, TAGS, TAG_LABELS, MAX_NOTE, LEGACY_ANCHOR, newProfile, normalizeProfile, legacyOf, isBlank, describe, emptyBook,
    normalizeBook, get, ops, roster, eligibleOpponents, parseStored, serialize, exportJson, importJson, createStore};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueManagerProfiles = api;

  // ---------- browser: the one shared store ----------
  const store = createStore();
  store.load();
  api.store = store;
  if (root.addEventListener) {
    root.addEventListener("pagehide", () => store.flush());
    root.addEventListener("beforeunload", () => store.flush());
    root.addEventListener("storage", event => { if (event.key === STORAGE_KEY) store.reloadFromStorage(); });
  }
})(typeof window !== "undefined" ? window : globalThis);
