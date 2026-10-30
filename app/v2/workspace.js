// Trade Value v2 — the league workspace store (JEG-1021).
//
// One saved league: a list of named teams, each with a roster, one marked "my team". Pure data and a small store; no
// DOM, no engine values. The page (league.js) and the Waivers tab share ONE "my roster" through this store:
//
//   TradeValueWorkspace.store.getMyRoster()        -> [{key, name, pos, team?, slot?}]  (a copy; [] when no team is marked)
//   TradeValueWorkspace.store.setMyRoster(entries) -> creates "My team" when none is marked, else replaces its roster
//   TradeValueWorkspace.store.subscribe(fn)        -> unsubscribe fn; fn({reason, myRoster}) when my roster or the
//                                                     "my team" mark changes (including from another tab and on load)
//
// Saved in this browser only (localStorage key ddf.v2.workspaces, versioned). Auto-saved 1 second after a change
// (JEG-1021 Q6), with a status for the "Saved" indicator. A corrupt or unknown-version value is ignored, reported
// once, and not overwritten until the reader changes something.
(function (root) {
  "use strict";

  const STORAGE_KEY = "ddf.v2.workspaces";
  const VERSION = 1;
  const MAX_NAME = 40;
  const MAX_TEAMS = 20;
  const SAVE_DELAY_MS = 1000;
  const SHARE_LIMIT = 1800;
  const FINDER_POSITIONS = ["QB", "RB", "WR", "TE"];
  const FINDER_LIMITS = ["minDdfEdge", "minUserLineupGain", "minTheirLineupGain"];

  // JEG-1249: each team's roster provenance (what a source showed, apart from local edits) goes through the JEG-1241 helper.
  const P = root.DDFRosterProvenance || (typeof require === "function" ? require("./roster-provenance-transitions.js") : null);
  const clone = value => JSON.parse(JSON.stringify(value));
  const isObject = value => Boolean(value) && typeof value === "object" && !Array.isArray(value);
  // Finder settings are stored with the league, including in JSON exports. Invalid imports reset to safe defaults.
  function normalizeFinderSettings(raw) {
    const value = isObject(raw) ? raw : {};
    const positions = Array.isArray(value.protectedPositions) ? value.protectedPositions : [];
    const out = {protectedPositions: FINDER_POSITIONS.filter(pos => positions.includes(pos)), keepMine: value.keepMine !== false,
      keepTheirs: value.keepTheirs !== false, maxSize: [1, 2, 3, 4].includes(value.maxSize) ? value.maxSize : 2,
      minBackups: Object.fromEntries(FINDER_POSITIONS.map(pos => [pos, Number.isInteger(value.minBackups && value.minBackups[pos])
        && value.minBackups[pos] >= 0 && value.minBackups[pos] <= 20 ? value.minBackups[pos] : 0])),
      minDdfEdge: 0, minUserLineupGain: null, minTheirLineupGain: null};
    FINDER_LIMITS.forEach(key => {
      const n = value[key];
      if (key !== "minDdfEdge" && (n === null || n === undefined || n === "")) return;
      if (typeof n === "number" && Number.isFinite(n) && n >= 0 && n <= 100 && Math.round(n * 10) === n * 10) out[key] = n;
    });
    return out;
  }
  const cleanName = (name, fallback) => {
    const text = String(name == null ? "" : name).replace(/\s+/g, " ").trim().slice(0, MAX_NAME);
    return text || fallback || "";
  };

  let idCounter = 0;
  function newId(prefix) {
    if (root.crypto && typeof root.crypto.randomUUID === "function") return root.crypto.randomUUID();
    idCounter += 1;
    return `${prefix || "id"}-${Date.now().toString(36)}-${idCounter}-${Math.random().toString(36).slice(2, 8)}`;
  }

  // ---------- shapes ----------
  // Entry: {key, name, pos, team?, slot?}. K and DEF stay on a roster (key "x:..."): shown "Not evaluated", never valued.
  function cleanEntry(entry) {
    if (!isObject(entry) || entry.key == null || !entry.name) return null;
    const out = {key: String(entry.key), name: String(entry.name), pos: String(entry.pos || "")};
    if (entry.team) out.team = String(entry.team);
    if (entry.slot) out.slot = String(entry.slot);
    return out;
  }
  function cleanEntries(list) {
    const seen = new Set();
    const out = [];
    (Array.isArray(list) ? list : []).forEach(item => {
      const entry = cleanEntry(item);
      if (!entry || seen.has(entry.key)) return;
      seen.add(entry.key);
      out.push(entry);
    });
    return out;
  }
  // JEG-1188 / JEG-1249: provenance = {unresolved (null = unknown), observedAt (a source roster read), editedAt (any local
  // change), coverage, settled}, from DDFRosterProvenance. The league page prices with the league's own rosters only when
  // every team's provenance shows a complete, matched, current source observation. A team made without a source
  // observation (by hand, or from a share link) has none.
  const plainProvenance = p => ({unresolved: p.unresolved, observedAt: p.observedAt, editedAt: p.editedAt, coverage: p.coverage, settled: p.settled.slice()});
  const provenanceOf = raw => plainProvenance(P.normalize(raw));
  function newTeam(name, opts) {
    const o = opts || {};
    const now = o.now || Date.now();
    return {id: o.id || newId("team"), name: cleanName(name, "Team"), sourceText: "", sourceTeam: null, removed: [], entries: cleanEntries(o.entries), createdAt: now, updatedAt: now,
      provenance: provenanceOf(o.provenance || {unresolved: 0, editedAt: now})};
  }
  function newWorkspace(opts) {
    const o = opts || {};
    const now = o.now || Date.now();
    return {id: o.id || newId("league"), name: cleanName(o.name, "My league"), settings: null, teams: [], myTeamId: null, createdAt: now, updatedAt: now,
      // leagueRosters (JEG-1249): use the league's own rosters for the bench once they qualify; false = the reader switched it off.
      ui: {sort: {summary: null, opps: null}, rankBasis: "fund", hideForce: false, leagueRosters: true, filters: {fit: "all", opponent: "all", minCapture: 0, minCharts: 0}, maxSize: 2,
        finderSettings: normalizeFinderSettings(null)}};
  }
  // Fills anything missing so a workspace saved by an older build still loads.
  function normalizeWorkspace(raw) {
    if (!isObject(raw) || !Array.isArray(raw.teams)) return null;
    const base = newWorkspace({id: raw.id, name: raw.name, now: Number(raw.createdAt) || Date.now()});
    const teams = [];
    const ids = new Set();
    raw.teams.forEach(t => {
      if (!isObject(t)) return;
      const id = t.id ? String(t.id) : newId("team");
      if (ids.has(id) || teams.length >= MAX_TEAMS) return;
      ids.add(id);
      teams.push({id, name: cleanName(t.name, `Team ${teams.length + 1}`), sourceText: typeof t.sourceText === "string" ? t.sourceText : "", sourceTeam: Number.isInteger(t.sourceTeam) ? t.sourceTeam : null,
        removed: Array.isArray(t.removed) ? t.removed.map(String) : [], entries: cleanEntries(t.entries),
        createdAt: Number(t.createdAt) || base.createdAt, updatedAt: Number(t.updatedAt) || base.createdAt,
        // A JEG-1188 save kept rosterAt / unresolved on the team: rosterAt was refreshed by every edit, so it reads as editedAt only.
        provenance: provenanceOf(isObject(t.provenance) ? t.provenance : {unresolved: t.unresolved, rosterAt: t.rosterAt})});
    });
    const ui = isObject(raw.ui) ? raw.ui : {};
    return {...base, id: String(raw.id || base.id), settings: isObject(raw.settings) ? raw.settings : null, teams,
      myTeamId: ids.has(String(raw.myTeamId)) ? String(raw.myTeamId) : null, updatedAt: Number(raw.updatedAt) || base.updatedAt,
      ui: {...base.ui, ...ui, finderSettings: normalizeFinderSettings(ui.finderSettings), filters: {...base.ui.filters, ...(isObject(ui.filters) ? ui.filters : {})}, sort: {...base.ui.sort, ...(isObject(ui.sort) ? ui.sort : {})}}};
  }

  // ---------- pure operations: each returns a new workspace ----------
  const touch = (ws, now) => ({...ws, updatedAt: now || Date.now()});
  const mapTeam = (ws, id, fn, now) => {
    if (!ws.teams.some(t => t.id === id)) return ws;
    return touch({...ws, teams: ws.teams.map(t => (t.id === id ? {...fn(t), updatedAt: now || Date.now()} : t))}, now);
  };
  const ops = {
    addTeam(ws, name, opts) {
      if (ws.teams.length >= MAX_TEAMS) return ws;
      const team = newTeam(name || `Team ${ws.teams.length + 1}`, opts);
      return touch({...ws, teams: ws.teams.concat([team]), myTeamId: ws.myTeamId || (opts && opts.mine ? team.id : ws.myTeamId)}, opts && opts.now);
    },
    removeTeam(ws, id) {
      if (!ws.teams.some(t => t.id === id)) return ws;
      return touch({...ws, teams: ws.teams.filter(t => t.id !== id), myTeamId: ws.myTeamId === id ? null : ws.myTeamId});
    },
    renameTeam: (ws, id, name) => mapTeam(ws, id, t => ({...t, name: cleanName(name, t.name)})),
    // extra.provenance: the caller's DDFRosterProvenance transition (a paste, a reconciled item); without it the change
    // is a local edit, which never counts as a source observation.
    setEntries: (ws, id, entries, extra) => mapTeam(ws, id, t => {
      const {provenance, ...rest} = extra || {};
      return {...t, entries: cleanEntries(entries), ...rest,
        provenance: provenanceOf(provenance || P.localEdit(t.provenance, {now: Date.now()}))};
    }),
    clearTeam: (ws, id) => mapTeam(ws, id, t => ({...t, entries: [], sourceText: "", sourceTeam: null, removed: [],
      provenance: provenanceOf(P.clear(t.provenance, {now: Date.now()}))})),
    // JEG-1190: every team goes; the league's settings, name and view choices stay.
    clearLeague: ws => (ws.teams.length ? touch({...ws, teams: [], myTeamId: null}) : ws),
    setSourceText: (ws, id, text) => mapTeam(ws, id, t => ({...t, sourceText: String(text || "")})),
    addRemoved: (ws, id, key) => mapTeam(ws, id, t => ({...t, removed: t.removed.includes(String(key)) ? t.removed : t.removed.concat([String(key)])})),
    setMyTeam: (ws, id) => (id === null || ws.teams.some(t => t.id === id) ? touch({...ws, myTeamId: id}) : ws),
    // dir: -1 up, +1 down. Order is display only.
    moveTeam(ws, id, dir) {
      const from = ws.teams.findIndex(t => t.id === id);
      const to = from + dir;
      if (from < 0 || to < 0 || to >= ws.teams.length) return ws;
      const teams = ws.teams.slice();
      [teams[from], teams[to]] = [teams[to], teams[from]];
      return touch({...ws, teams});
    },
    setSettings: (ws, settings) => touch({...ws, settings: isObject(settings) ? clone(settings) : null}),
    setUi: (ws, patch) => touch({...ws, ui: {...ws.ui, ...patch, filters: {...ws.ui.filters, ...((patch && patch.filters) || {})}, sort: {...ws.ui.sort, ...((patch && patch.sort) || {})}}}),
    rename: (ws, name) => touch({...ws, name: cleanName(name, ws.name)})
  };

  // ---------- storage text ----------
  // status: "empty" (nothing saved), "ok", "corrupt" (not JSON / wrong shape), "version" (a version this build does not read).
  function parseStored(text) {
    if (text === null || text === undefined || text === "") return {status: "empty", workspace: null};
    let data;
    try { data = JSON.parse(text); } catch (error) { return {status: "corrupt", workspace: null}; }
    if (!isObject(data)) return {status: "corrupt", workspace: null};
    if (data.v !== VERSION) return {status: "version", workspace: null};
    const list = Array.isArray(data.workspaces) ? data.workspaces : null;
    if (!list) return {status: "corrupt", workspace: null};
    const active = list.find(w => isObject(w) && w.id === data.activeId) || list.find(isObject);
    const workspace = active ? normalizeWorkspace(active) : null;
    return workspace ? {status: "ok", workspace} : {status: list.length ? "corrupt" : "empty", workspace: null};
  }
  const serialize = ws => JSON.stringify({v: VERSION, workspaces: [ws], activeId: ws.id});

  // Export: one Workspace object (no wrapper). Import validates and returns {workspace} or {error}.
  const exportJson = ws => JSON.stringify(ws, null, 2);
  function importJson(text) {
    let data;
    try { data = JSON.parse(text); } catch (error) { return {error: "That file is not valid JSON."}; }
    if (isObject(data) && Array.isArray(data.workspaces)) data = data.workspaces[0];   // a whole saved value is accepted too
    if (!isObject(data) || !data.id || !data.name || !Array.isArray(data.teams)) return {error: "That file is not a saved league (it needs an id, a name and a teams list)."};
    for (const team of data.teams) {
      if (!isObject(team) || !Array.isArray(team.entries)) return {error: "That file is not a saved league (a team has no player list)."};
      if (team.entries.some(e => !isObject(e) || e.key == null || !e.name)) return {error: "That file is not a saved league (a player has no key or name)."};
    }
    const workspace = normalizeWorkspace(data);
    return workspace ? {workspace} : {error: "That file is not a saved league."};
  }

  // A compact text copy for pasting into a chat: team names and player names, teams apart by a blank line. Not for re-import.
  function copyText(ws) {
    return ws.teams.map(t => [t.name + (ws.myTeamId === t.id ? " (my team)" : "")].concat(t.entries.map(e => `${e.name}${e.pos ? ` (${e.pos})` : ""}`)).join("\n")).join("\n\n");
  }

  // ---------- share links (JEG-1021 section 2.5) ----------
  // team1:k,k,k|team2:k,k ; numeric player keys are base 36, anything else is "~" + percent-encoded. K and DEF entries
  // (keys "x:...") travel by name/position plus their exact identity: "!NAME.POS:KEY[:TEAM]".
  // Older "!NAME.POS" links remain readable.
  function encodeKey(entry) {
    if (/^\d+$/.test(entry.key)) return Number(entry.key).toString(36);
    if (entry.key.startsWith("x:")) return `!${encodeURIComponent(entry.name)}.${entry.pos}:${encodeURIComponent(entry.key)}${entry.team ? `:${encodeURIComponent(entry.team)}` : ""}`;
    return `~${encodeURIComponent(entry.key)}`;
  }
  function decodeKey(token, byKey) {
    if (token.startsWith("!")) {
      const parts = token.split(":");
      const at = parts[0].lastIndexOf(".");
      const name = decodeURIComponent(parts[0].slice(1, at));
      const pos = parts[0].slice(at + 1);
      const key = parts[1] ? decodeURIComponent(parts[1]) : `x:${pos}:${name.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()}`;
      return {key, name, pos, ...(parts[2] ? {team: decodeURIComponent(parts[2])} : {})};
    }
    const key = token.startsWith("~") ? decodeURIComponent(token.slice(1)) : String(parseInt(token, 36));
    const row = byKey && byKey.get(key);
    return row ? {key, name: row.name, pos: row.pos, team: row.team} : {key, name: `Player ${key}`, pos: "", unknown: true};
  }
  // Returns {text, full}: full is false (and only the "my team" roster travels) when the whole league is over the limit.
  function encodeShare(ws) {
    const enc = list => list.map(team => `${encodeURIComponent(team.name)}:${team.entries.map(encodeKey).join(",")}`).join("|");
    const mineFirst = ws.teams.slice().sort((a, b) => (b.id === ws.myTeamId) - (a.id === ws.myTeamId));
    const full = enc(mineFirst);
    // ids: the teams that travel, in link order (JEG-1328: the link refers to a team by this position, as wm does).
    if (full.length <= SHARE_LIMIT) return {text: full, full: true, mine: ws.myTeamId ? 0 : null, ids: mineFirst.map(t => t.id)};
    const mine = ws.teams.find(t => t.id === ws.myTeamId);
    return {text: mine ? enc([mine]) : "", full: false, mine: mine ? 0 : null, ids: mine ? [mine.id] : []};
  }
  // Reuse the bounded roster codec; settings are the page's own complete league query.
  // opts.trade: the league finder's selected trade (tradePick), carried when its opponent travels.
  function shareHash(ws, leagueQuery, opts) {
    const encoded = encodeShare(ws);
    const query = String(leagueQuery || "").replace(/^[?&]+/, "");
    const extra = shareExtras(ws, encoded.ids, (opts || {}).trade);
    const {ids, ...rest} = encoded;
    return {...rest, hash: `#find-league?workspace=${encoded.text}&wm=${encoded.mine === null ? "none" : encoded.mine}${extra.length ? `&${extra.join("&")}` : ""}${query ? `&${query}` : ""}`};
  }
  function decodeShare(text, byKey) {
    try {
      const teams = String(text || "").split("|").filter(Boolean).map((part, i) => {
        const at = part.indexOf(":");
        if (at < 0) return null;
        const tokens = part.slice(at + 1).split(",").filter(Boolean);
        return {name: decodeURIComponent(part.slice(0, at)) || `Team ${i + 1}`, entries: tokens.map(token => decodeKey(token, byKey))};
      }).filter(Boolean);
      return teams.slice(0, MAX_TEAMS);
    } catch (error) {
      // Reject the entire malformed link rather than importing a partial league over a saved one.
      return [];
    }
  }

  // ---------- JEG-1328: what a league link carries beside the rosters ----------
  // The league finder's discovery controls and its selected trade. A reader's league gets new team ids, so the link names
  // a team by its position in the link (as wm does) and readShareExtras turns positions into the new teams' ids. Missing
  // means today's default, which is what a reader's new league starts with, so links made before these fields open the
  // same view they always did. Parameter names match the pair finder's link where the control is the same (size).
  const LEAGUE_SIZES = [2, 3, 4];
  const LEAGUE_FITS = ["all", "natural", "naturalMarket"];
  const SHARE_OWN_PARAMS = ["workspace", "wm", "size", "hf", "fit", "opp", "mcap", "mch", "trade"];
  const shareNumber = text => (/^\d{1,3}(?:\.\d)?$/.test(String(text)) && Number(text) <= 100 ? Number(text) : null);
  // The selected trade: "1~<opponent team id>~<give keys>~<receive keys>". Links made before JEG-1328 keyed it by the
  // opponent's name ("<name>~<give>~<receive>"); legacyTradePick reads those.
  const pickKeys = list => (list || []).map(p => String(typeof p === "object" && p ? p.player_key || p.key : p)).join(",");
  const tradePick = (opponentId, give, receive) => ["1", String(opponentId), pickKeys(give), pickKeys(receive)].map(encodeURIComponent).join("~");
  const legacyTradePick = (opponentName, give, receive) => [String(opponentName), pickKeys(give), pickKeys(receive)].map(encodeURIComponent).join("~");
  // {opponentId, give, receive} for the current form, {legacy: true, opponent, give, receive} for a name-keyed one, else null.
  function parseTradePick(text) {
    let parts;
    try { parts = String(text || "").split("~").map(decodeURIComponent); } catch (error) { return null; }
    const keys = s => s.split(",").filter(Boolean);
    if (parts.length === 4 && parts[0] === "1" && parts[1]) return {opponentId: parts[1], give: keys(parts[2]), receive: keys(parts[3])};
    if (parts.length === 3 && parts[0]) return {legacy: true, opponent: parts[0], give: keys(parts[1]), receive: keys(parts[2])};
    return null;
  }
  function shareExtras(ws, ids, trade) {
    const ui = isObject(ws.ui) ? ws.ui : {};
    const f = isObject(ui.filters) ? ui.filters : {};
    const at = id => ids.indexOf(id);
    const out = [];
    if (LEAGUE_SIZES.includes(ui.maxSize) && ui.maxSize !== 2) out.push(`size=${ui.maxSize}`);
    if (ui.hideForce) out.push("hf=1");
    if (LEAGUE_FITS.includes(f.fit) && f.fit !== "all") out.push(`fit=${f.fit}`);
    if (f.opponent && f.opponent !== "all" && at(f.opponent) >= 0) out.push(`opp=${at(f.opponent)}`);
    if (shareNumber(f.minCapture)) out.push(`mcap=${f.minCapture}`);
    if (shareNumber(f.minCharts)) out.push(`mch=${f.minCharts}`);
    const pick = trade ? parseTradePick(trade) : null;
    if (pick && !pick.legacy && at(pick.opponentId) >= 0) out.push(`trade=${tradePick(at(pick.opponentId), pick.give, pick.receive)}`);
    return out;
  }
  // params: the link's URLSearchParams; teamIds: the ids the reader's new league gave the link's teams, in link order.
  // Returns {ui (a setUi patch), trade (the pick for the address, by the new team id; a legacy pick unchanged; or null)}.
  function readShareExtras(params, teamIds) {
    const idAt = text => (/^\d{1,2}$/.test(String(text)) && teamIds[Number(text)] ? teamIds[Number(text)] : null);
    const ui = {};
    const filters = {};
    const size = Number(params.get("size"));
    if (LEAGUE_SIZES.includes(size)) ui.maxSize = size;
    if (params.get("hf") === "1") ui.hideForce = true;
    if (LEAGUE_FITS.includes(params.get("fit"))) filters.fit = params.get("fit");
    if (idAt(params.get("opp"))) filters.opponent = idAt(params.get("opp"));
    if (shareNumber(params.get("mcap")) !== null) filters.minCapture = shareNumber(params.get("mcap"));
    if (shareNumber(params.get("mch")) !== null) filters.minCharts = shareNumber(params.get("mch"));
    if (Object.keys(filters).length) ui.filters = filters;
    const pick = params.has("trade") ? parseTradePick(params.get("trade")) : null;
    const trade = !pick ? null : pick.legacy ? legacyTradePick(pick.opponent, pick.give, pick.receive)
      : idAt(pick.opponentId) ? tradePick(idAt(pick.opponentId), pick.give, pick.receive) : null;
    return {ui, trade};
  }
  // The league settings a link leaves once its own parameters are read: the league query plus the value context
  // (valuecontext, basis, ov), which the league keeps with its settings (league.js applies both when it loads).
  function shareSettingsQuery(params) {
    const rest = new URLSearchParams(params.toString());
    SHARE_OWN_PARAMS.forEach(name => rest.delete(name));
    return rest.toString();
  }

  // ---------- the store ----------
  // opts: {storage (localStorage-like), now, delay, setTimer, clearTimer}. Subscribers: onChange(ws, change) for the page,
  // subscribe(fn) for "my roster" watchers. status(): "idle" | "saving" | "saved" | "unavailable" | "full".
  function createStore(opts) {
    const o = opts || {};
    const delay = o.delay === undefined ? SAVE_DELAY_MS : o.delay;
    const setTimer = o.setTimer || ((fn, ms) => root.setTimeout(fn, ms));
    const clearTimer = o.clearTimer || (id => root.clearTimeout(id));
    let storage = o.storage === undefined ? safeStorage() : o.storage;
    let ws = newWorkspace();
    let loadStatus = "empty";
    let timer = null;
    let dirty = false;
    let state = "idle";
    const listeners = new Set();
    const mineListeners = new Set();
    const statusListeners = new Set();

    const myEntries = w => { const t = w.teams.find(x => x.id === w.myTeamId); return t ? t.entries.map(e => ({...e})) : []; };
    const setState = next => { if (state !== next) { state = next; statusListeners.forEach(fn => { try { fn(next); } catch (error) { /* a listener must not stop the save */ } }); } };
    function write() {
      timer = null;
      if (!dirty) return true;
      if (!storage) { setState("unavailable"); return false; }
      try {
        storage.setItem(STORAGE_KEY, serialize(ws));
        dirty = false;
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
    function notify(reason, before) {
      const change = {reason};
      listeners.forEach(fn => fn(ws, change));
      const was = JSON.stringify(myEntries(before));
      const now = JSON.stringify(myEntries(ws));
      if (was !== now || before.myTeamId !== ws.myTeamId) mineListeners.forEach(fn => fn({reason, myRoster: myEntries(ws)}));
    }
    const api = {
      STORAGE_KEY,
      // Reads storage. Returns the status: "ok" | "empty" | "corrupt" | "version" | "unavailable".
      load() {
        const before = ws;
        let text = null;
        if (!storage) loadStatus = "unavailable";
        else {
          try { text = storage.getItem(STORAGE_KEY); } catch (error) { storage = null; loadStatus = "unavailable"; }
          if (storage) {
            const parsed = parseStored(text);
            loadStatus = parsed.status;
            ws = parsed.workspace || newWorkspace();
          }
        }
        if (loadStatus === "unavailable") setState("unavailable");
        else if (loadStatus === "ok") setState("saved");
        notify("load", before);
        return loadStatus;
      },
      loadStatus: () => loadStatus,
      get: () => ws,
      status: () => state,
      // fn(ws) returns the new workspace; nothing is saved when it returns the same object.
      update(fn, reason) {
        const before = ws;
        const next = fn(ws);
        if (!next || next === ws) return ws;
        ws = next;
        schedule();
        notify(reason || "change", before);
        return ws;
      },
      // Replaces the whole workspace (Load from a file, a share link).
      replace(next, reason) {
        const before = ws;
        ws = next;
        schedule();
        notify(reason || "replace", before);
        return ws;
      },
      flush() { if (timer !== null) { clearTimer(timer); timer = null; } return write(); },
      onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
      onStatus(fn) { statusListeners.add(fn); return () => statusListeners.delete(fn); },
      // The shared "my roster" (Waivers tab and the league page).
      getMyRoster: () => myEntries(ws),
      getMyTeam() { const t = ws.teams.find(x => x.id === ws.myTeamId); return t ? {id: t.id, name: t.name} : null; },
      setMyRoster(entries) {
        const list = cleanEntries(entries);
        api.update(w => {
          if (!w.myTeamId || !w.teams.some(t => t.id === w.myTeamId)) {
            const team = newTeam("My team", {entries: list});
            return touch({...w, teams: w.teams.length >= MAX_TEAMS ? w.teams : w.teams.concat([team]), myTeamId: w.teams.length >= MAX_TEAMS ? w.myTeamId : team.id});
          }
          return ops.setEntries(w, w.myTeamId, list, {sourceText: "", sourceTeam: null});
        }, "my-roster");
        return myEntries(ws);
      },
      subscribe(fn) { mineListeners.add(fn); return () => mineListeners.delete(fn); },
      // Another tab saved: take its value.
      reloadFromStorage() {
        if (!storage) return;
        let text = null;
        try { text = storage.getItem(STORAGE_KEY); } catch (error) { return; }
        const parsed = parseStored(text);
        if (parsed.status !== "ok" || serialize(parsed.workspace) === serialize(ws)) return;
        const before = ws;
        ws = parsed.workspace;
        dirty = false;
        notify("other-tab", before);
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

  const api = {STORAGE_KEY, VERSION, MAX_NAME, MAX_TEAMS, SHARE_LIMIT, newWorkspace, newTeam, normalizeWorkspace, normalizeFinderSettings, cleanEntries, cleanName, ops, parseStored, serialize,
    exportJson, importJson, copyText, encodeShare, shareHash, decodeShare, tradePick, legacyTradePick, parseTradePick, readShareExtras, shareSettingsQuery, createStore};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueWorkspace = api;

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
