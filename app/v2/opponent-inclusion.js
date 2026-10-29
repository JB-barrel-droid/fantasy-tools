// JEG-1231: which opponents the league-wide trade search includes. View/search selection only.
//
// The reader ticks the teams to search. Everything is keyed by the stable workspace team id (workspace.js), never by a
// display name, so a rename keeps the choice, two teams with one name stay apart, and a team that is removed and added
// again (a new id) arrives included like any new team. Today's baseline is kept: every opponent is searched until the
// reader leaves one out. Only exclusions are stored, so no new default selection policy is introduced.
//
// State lives in the league's existing workspace ui (ws.ui.opponentInclusion = {v: 1, excluded: [teamId]}), saved by the
// workspace store like the other league filters. There is no second store.
//
// A manager the reader marked "won't trade" (JEG-1217 manager profiles, profile.excluded) is a stronger, separate choice.
// This module reads it through opts.profileExcluded(teamId) and never re-includes that team: its box shows unticked,
// cannot be ticked here, and says where the choice lives. Nothing here changes a value, a fit, a ranking, the League star,
// a saved roster or a manager profile.
//
// Pure helpers (no DOM) plus one accessible checkbox component (createControl), so the private preview and the league page
// draw the same thing. Node: module.exports. Browser: window.TradeValueOpponentInclusion.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.TradeValueOpponentInclusion = factory();
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";

  const VERSION = 1;
  const UI_KEY = "opponentInclusion";
  const isObject = v => Boolean(v) && typeof v === "object" && !Array.isArray(v);
  const teamsOf = ws => (ws && Array.isArray(ws.teams) ? ws.teams : []);
  const idOf = t => String(t.id);
  const nameKey = name => String(name || "").trim().toLowerCase().replace(/\s+/g, " ");
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;

  // ---------- state ----------
  const emptyState = () => ({v: VERSION, excluded: []});
  // Reads any stored value. Unknown versions, non-arrays and ids that are not teams in this league are dropped, so a team
  // that left the league never carries an exclusion to whichever team is added next.
  function normalize(raw, ws) {
    if (!isObject(raw) || raw.v !== VERSION || !Array.isArray(raw.excluded)) return emptyState();
    const known = new Set(teamsOf(ws).map(idOf));
    const seen = new Set();
    raw.excluded.forEach(id => {
      const key = String(id);
      if (id !== null && id !== undefined && known.has(key)) seen.add(key);
    });
    const clean = {v: VERSION, excluded: teamsOf(ws).map(idOf).filter(id => seen.has(id))};
    // An already-clean state comes back as itself, so "nothing changed" is a plain identity check for callers.
    return Object.keys(raw).length === 2 && raw.excluded.every(id => typeof id === "string") && same(clean, raw) ? raw : clean;
  }
  const read = ws => normalize(ws && isObject(ws.ui) ? ws.ui[UI_KEY] : null, ws);
  // The patch for workspace ops.setUi.
  const patch = state => ({[UI_KEY]: state});
  const same = (a, b) => a.excluded.length === b.excluded.length && a.excluded.every((id, i) => id === b.excluded[i]);

  // ---------- who counts ----------
  const opponents = ws => teamsOf(ws).filter(t => idOf(t) !== String(ws && ws.myTeamId));
  const profileTest = opts => (opts && typeof opts.profileExcluded === "function" ? id => opts.profileExcluded(id) === true : () => false);
  const rosterTest = opts => (opts && typeof opts.hasRoster === "function" ? t => Boolean(opts.hasRoster(t)) : t => Array.isArray(t.entries) && t.entries.length > 0);

  // One row per opponent, in league order:
  //   {id, name, label, duplicate, position, viewExcluded, profileExcluded, included, hasRoster, searched}
  // label adds "team N" (its place in the league list) when two opponents share a name, so a screen reader can tell them apart.
  function describe(ws, rawState, opts) {
    const state = normalize(rawState === undefined ? (ws && ws.ui && ws.ui[UI_KEY]) : rawState, ws);
    const excluded = new Set(state.excluded);
    const isProfile = profileTest(opts);
    const hasRoster = rosterTest(opts);
    const all = teamsOf(ws);
    const opps = opponents(ws);
    const counts = new Map();
    opps.forEach(t => counts.set(nameKey(t.name), (counts.get(nameKey(t.name)) || 0) + 1));
    const rows = opps.map(t => {
      const id = idOf(t);
      const position = all.findIndex(x => idOf(x) === id) + 1;
      const duplicate = counts.get(nameKey(t.name)) > 1;
      const profileExcluded = isProfile(id);
      const viewExcluded = excluded.has(id);
      const included = !viewExcluded && !profileExcluded;
      const roster = hasRoster(t);
      const name = String(t.name || "");
      return {id, name, label: duplicate ? `${name} · team ${position}` : name, duplicate, position, viewExcluded, profileExcluded,
        included, hasRoster: roster, searched: included && roster};
    });
    const total = rows.length;
    const included = rows.filter(r => r.included).length;
    const searched = rows.filter(r => r.searched).length;
    const profile = rows.filter(r => r.profileExcluded).length;
    const view = rows.filter(r => r.viewExcluded && !r.profileExcluded).length;
    const empty = rows.filter(r => r.included && !r.hasRoster).length;
    const status = !total ? "none" : included === 0 ? "allExcluded" : "ok";
    return {state, rows, counts: {total, included, searched, viewExcluded: view, profileExcluded: profile, noRoster: empty}, status};
  }

  // Plain sentences for the count line and the screen-reader status.
  function summary(model) {
    const c = model.counts;
    if (model.status === "none") return "Add another team to choose which opponents to search.";
    if (model.status === "allExcluded") return "No opponents are included, so no trades can be found. Tick at least one team.";
    const parts = [`Searching ${c.searched} of ${plural(c.total, "opponent")}.`];
    if (c.viewExcluded) parts.push(`${c.viewExcluded} left out here.`);
    if (c.profileExcluded) parts.push(`${c.profileExcluded} marked won't trade in Managers.`);
    if (c.noRoster) parts.push(`${c.noRoster} included ${c.noRoster === 1 ? "has" : "have"} no roster yet.`);
    return parts.join(" ");
  }

  // ---------- operations: each returns a new state (the same object when nothing changed) ----------
  function setIncluded(rawState, ws, teamId, include) {
    const state = normalize(rawState, ws);
    const id = String(teamId);
    if (!opponents(ws).some(t => idOf(t) === id)) return state;
    const set = new Set(state.excluded);
    if (include) set.delete(id); else set.add(id);
    const next = {v: VERSION, excluded: teamsOf(ws).map(idOf).filter(x => set.has(x))};
    return same(next, state) ? state : next;
  }
  const toggle = (rawState, ws, teamId) => setIncluded(rawState, ws, teamId, normalize(rawState, ws).excluded.includes(String(teamId)));
  // Select all clears this view's exclusions only; a manager marked won't trade stays out.
  function includeAll(rawState, ws) {
    const state = normalize(rawState, ws);
    return state.excluded.length ? emptyState() : state;
  }
  function excludeAll(rawState, ws) {
    const state = normalize(rawState, ws);
    const next = {v: VERSION, excluded: opponents(ws).map(idOf)};
    return same(next, state) ? state : next;
  }

  // ---------- the search adapter ----------
  // The opponents the league search should run against: included teams in league order, the team objects themselves.
  function searchOpponents(ws, rawState, opts) {
    const ids = new Set(describe(ws, rawState, opts).rows.filter(r => r.included).map(r => r.id));
    return opponents(ws).filter(t => ids.has(idOf(t)));
  }
  // Belt and braces for results from an earlier run: rows against a team that is not included never show.
  function filterRows(rows, ws, rawState, opts) {
    const ids = new Set(describe(ws, rawState, opts).rows.filter(r => r.included).map(r => r.id));
    return (rows || []).filter(r => ids.has(String(r.opponentId)));
  }
  // The single "Opponent:" results filter falls back to all when it points at a team that is no longer included.
  function opponentFilter(filters, ws, rawState, opts) {
    const f = isObject(filters) ? filters : {};
    if (f.opponent === undefined || f.opponent === null || f.opponent === "all") return f;
    const ok = describe(ws, rawState, opts).rows.some(r => r.included && r.id === String(f.opponent));
    return ok ? f : {...f, opponent: "all"};
  }
  // Changes when, and only when, the set of included opponents changes. A caller reruns the search on a change; the
  // per-pairing cache in opportunities.js is keyed by roster content, so reused pairings keep their exact values.
  const selectionKey = (ws, rawState, opts) => describe(ws, rawState, opts).rows.filter(r => r.included).map(r => r.id).join("|");

  // ---------- the checkbox component ----------
  // createControl({document, idPrefix, legend, onToggle(teamId, include), onIncludeAll(), onExcludeAll(), profileNote})
  // returns {element, update(model)}. update keeps each team's row and box by team id, so the focused box keeps focus
  // while the page redraws around it.
  function createControl(options) {
    const o = options || {};
    const doc = o.document || (typeof document !== "undefined" ? document : null);
    if (!doc) throw new Error("createControl needs a document");
    const prefix = o.idPrefix || "oi";
    const el = (tag, attrs, ...kids) => {
      const node = doc.createElement(tag);
      Object.entries(attrs || {}).forEach(([k, v]) => {
        if (v === null || v === undefined || v === false) return;
        if (k === "text") node.textContent = v;
        else if (k === "class") node.className = v;
        else node.setAttribute(k, v === true ? "" : String(v));
      });
      kids.flat().forEach(k => { if (k !== null && k !== undefined) node.append(k); });
      return node;
    };
    const safe = id => String(id).replace(/[^A-Za-z0-9_-]/g, c => `_${c.charCodeAt(0).toString(16)}`);
    const countId = `${prefix}Count`;
    const legend = el("legend", {class: "oi-legend", text: o.legend || "Opponents to search"});
    const count = el("p", {class: "oi-count", id: countId, role: "status", "aria-live": "polite"});
    const allBtn = el("button", {type: "button", class: "oi-btn", id: `${prefix}All`, text: "Select all"});
    const noneBtn = el("button", {type: "button", class: "oi-btn", id: `${prefix}None`, text: "Clear all"});
    const actions = el("div", {class: "oi-actions"}, allBtn, noneBtn);
    const list = el("ul", {class: "oi-list", id: `${prefix}List`});
    const empty = el("p", {class: "oi-empty", id: `${prefix}Empty`, hidden: true});
    const element = el("fieldset", {class: "oi", id: prefix, "aria-describedby": countId}, legend, count, actions, list, empty);
    allBtn.addEventListener("click", () => { if (o.onIncludeAll) o.onIncludeAll(); });
    noneBtn.addEventListener("click", () => { if (o.onExcludeAll) o.onExcludeAll(); });
    const items = new Map();
    const profileNote = o.profileNote || "Marked won't trade in Managers. Change it there.";

    function makeItem(row) {
      const boxId = `${prefix}Box-${safe(row.id)}`;
      const noteId = `${prefix}Note-${safe(row.id)}`;
      const box = el("input", {type: "checkbox", class: "oi-box", id: boxId, "data-team-id": row.id});
      const name = el("span", {class: "oi-name"});
      const tag = el("span", {class: "oi-tag", "aria-hidden": "true"});
      const label = el("label", {class: "oi-label", for: boxId}, name, tag);
      const note = el("span", {class: "oi-note", id: noteId});
      const li = el("li", {class: "oi-item", "data-team-id": row.id}, box, label, note);
      // A won't-trade manager stays out: the box stays focusable so a screen reader reaches it and hears why, but it cannot be ticked.
      box.addEventListener("click", event => { if (box.getAttribute("aria-disabled") === "true") event.preventDefault(); });
      box.addEventListener("change", () => { if (box.getAttribute("aria-disabled") !== "true" && o.onToggle) o.onToggle(row.id, box.checked); });
      return {li, box, name, tag, note, noteId};
    }

    function update(model) {
      const rows = model ? model.rows : [];
      const keep = new Set(rows.map(r => r.id));
      items.forEach((item, id) => { if (!keep.has(id)) { item.li.remove(); items.delete(id); } });
      rows.forEach((row, i) => {
        let item = items.get(row.id);
        if (!item) { item = makeItem(row); items.set(row.id, item); }
        item.name.textContent = row.name;
        item.tag.textContent = row.duplicate ? `team ${row.position}` : "";
        item.tag.hidden = !row.duplicate;
        // The accessible name carries the team number when names repeat; the visible tag is the same words.
        item.box.setAttribute("aria-label", row.label);
        item.box.checked = row.included;
        const note = row.profileExcluded ? profileNote : !row.hasRoster ? "No roster yet, so nothing to search." : "";
        item.note.textContent = note;
        item.note.hidden = !note;
        if (note) item.box.setAttribute("aria-describedby", item.noteId); else item.box.removeAttribute("aria-describedby");
        if (row.profileExcluded) item.box.setAttribute("aria-disabled", "true"); else item.box.removeAttribute("aria-disabled");
        item.li.dataset.state = row.profileExcluded ? "profile" : row.included ? "included" : "excluded";
        if (list.children[i] !== item.li) list.insertBefore(item.li, list.children[i] || null);
      });
      const text = model ? summary(model) : summary({status: "none", counts: {}});
      if (count.textContent !== text) count.textContent = text;
      element.dataset.status = model ? model.status : "none";
      const none = !rows.length;
      actions.hidden = none;
      list.hidden = none;
      empty.hidden = !none;
      empty.textContent = none ? "No other teams yet." : "";
    }
    return {element, update};
  }

  return {VERSION, UI_KEY, emptyState, normalize, read, patch, describe, summary, setIncluded, toggle, includeAll, excludeAll,
    searchOpponents, filterRows, opponentFilter, selectionKey, createControl};
});
