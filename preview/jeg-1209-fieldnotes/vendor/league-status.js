// Trade Value v2 — the loaded-league status header and its collapsed summary (JEG-1233).
//
// Says only what is actually loaded: the league's name, how many teams and roster rows the saved workspace holds,
// which team carries the star, where this visit's data came from and whether it is saved in this browser. It never
// says a league is connected, synced, complete or on another device: the workspace has no evidence of any of that.
//
//   TradeValueLeagueStatus.describe(input) -> view model (pure; no DOM). input, every field optional:
//     workspace    store.get() (TradeValueWorkspace shape)
//     loadStatus   store.loadStatus(): "ok" | "empty" | "corrupt" | "version" | "unavailable"
//     saveStatus   store.status(): "idle" | "saving" | "saved" | "unavailable" | "full"
//     origin       how this visit's league arrived: "stored" | "loaded" | "pasted" | null (see originFor)
//     parsed       league.js UI.parsed: {error} or {teams: [{name, count, unmatched, unsure, leftOut}], skipped}
//     valuesReady  false while player values are still loading
//     removedMine  {id, name} of a starred team removed this visit (the controller tracks it), else null
//     isNotEvaluated(entry) -> true for K and DEF (default: pos K or DEF)
//   TradeValueLeagueStatus.mount(host, opts) -> {update(), setExpanded(open), isExpanded(), destroy()}
//     A heading button that folds and opens the details (aria-expanded/aria-controls), the one-line summary that shows
//     in both states, and a body holding the facts, any issues and opts.controls (the existing edit controls, moved
//     in, never rebuilt). Expanded by default, as the league card is today; only the reader folds it. Escape inside
//     the body folds it and returns focus to the button. Reads the store; never writes to it.
(function (root) {
  "use strict";

  const NOT_EVALUATED = ["K", "DEF"];
  const plural = (n, word, many) => `${n} ${n === 1 ? word : (many || `${word}s`)}`;
  const nameKey = name => String(name || "").replace(/\s+/g, " ").trim().toLowerCase();

  // Saved state, as words. Only what store.status() reports; "on this device" is the most the workspace can claim.
  const STORAGE = {
    saved: {text: "Saved on this device", tone: "neutral"},
    saving: {text: "Saving on this device…", tone: "neutral"},
    idle: {text: "Not saved yet", tone: "neutral"},
    unavailable: {text: "Not saved: this browser isn't keeping data between visits", tone: "warn"},
    full: {text: "Not saved: this device's storage is full. Download your league to keep a copy", tone: "warn"}
  };
  const ORIGIN = {
    stored: "Read from this device",
    loaded: "Loaded from a file or link this visit",
    pasted: "Read from your paste this visit"
  };

  // The store's change reason -> origin. "load" is the saved copy; "replace" is a file or a share link; "paste" is
  // league.js telling the status a whole-league paste was read (it calls update("paste") after showParsed). Any other
  // edit keeps the origin it had: hand edits do not erase where the league came from.
  function originFor(previous, reason) {
    if (reason === "load") return "stored";
    if (reason === "replace") return "loaded";
    if (reason === "paste") return "pasted";
    return previous || null;
  }

  function describe(input) {
    const o = input || {};
    const ws = o.workspace && Array.isArray(o.workspace.teams) ? o.workspace : {name: "", teams: [], myTeamId: null};
    const notEval = typeof o.isNotEvaluated === "function" ? o.isNotEvaluated : e => Boolean(e) && NOT_EVALUATED.includes(e.pos);
    const teams = ws.teams;
    const players = teams.reduce((n, t) => n + (Array.isArray(t.entries) ? t.entries.length : 0), 0);
    const notEvaluated = teams.reduce((n, t) => n + (Array.isArray(t.entries) ? t.entries.filter(notEval).length : 0), 0);
    const emptyTeams = teams.filter(t => !t.entries || !t.entries.length);
    const marked = teams.find(t => t.id === ws.myTeamId) || null;
    const issues = [];

    const unreadable = o.loadStatus === "corrupt" || o.loadStatus === "version";
    // The store leaves an unreadable value alone until the reader changes something, then saves over it.
    if (unreadable) issues.push({id: "unreadable", tone: "bad", text: teams.length
      ? "Earlier saved league data on this device could not be read, so this league started fresh."
      : "Saved league data on this device could not be read. It has not been changed."});

    // Duplicate names: same name ignoring case and spacing. The star follows the team's id, so both stay distinct.
    const byName = new Map();
    teams.forEach(t => { const k = nameKey(t.name); byName.set(k, (byName.get(k) || []).concat([t])); });
    byName.forEach(list => {
      if (list.length > 1) issues.push({id: `dup-${nameKey(list[0].name)}`, tone: "warn", text: `${plural(list.length, "team")} are named “${list[0].name}”. Rename one so they're easy to tell apart.`});
    });

    if (teams.length && emptyTeams.length) {
      issues.push({id: "empty-teams", tone: "warn", text: emptyTeams.length === teams.length
        ? `${plural(emptyTeams.length, "team")} with no players yet.`
        : `${plural(emptyTeams.length, "team")} ${emptyTeams.length === 1 ? "has" : "have"} no players yet: ${emptyTeams.slice(0, 3).map(t => t.name).join(", ")}${emptyTeams.length > 3 ? "…" : ""}.`});
    }

    // What the last whole-league paste could not read, from league.js's own parse summary. Nothing is inferred.
    const parsed = o.parsed || null;
    let partial = false;
    if (parsed && parsed.error) issues.push({id: "paste-error", tone: "bad", text: `Your last paste wasn't read. ${parsed.error} Your saved league was kept.`});
    else if (parsed && Array.isArray(parsed.teams)) {
      const missed = parsed.teams.reduce((n, t) => n + ((t.unmatched && t.unmatched.length) || 0), 0);
      const unsure = parsed.teams.reduce((n, t) => n + (Number(t.unsure) || 0), 0);
      const leftOut = Math.max(parsed.teams.filter(t => t.leftOut).length, Number(parsed.skipped) || 0);
      if (missed) { partial = true; issues.push({id: "paste-missed", tone: "warn", text: `${plural(missed, "line")} from your last paste could not be matched to a player.`}); }
      if (unsure) { partial = true; issues.push({id: "paste-unsure", tone: "warn", text: `${plural(unsure, "player")} from your last paste ${unsure === 1 ? "was" : "were"} an unsure match. Check them in the team.`}); }
      if (leftOut) { partial = true; issues.push({id: "paste-left-out", tone: "warn", text: `${plural(leftOut, "team")} from your last paste ${leftOut === 1 ? "was" : "were"} not set up.`}); }
    }

    // The star: only a team that is in the league now. A starred team removed this visit is named once, so the reader
    // knows why nothing carries the star. The status never picks a team for them.
    let mine;
    if (marked) mine = {state: "marked", text: `Your team: ${marked.name}`};
    else if (o.removedMine && o.removedMine.name && !teams.some(t => t.id === o.removedMine.id)) mine = {state: "removed", text: `Your team (${o.removedMine.name}) was removed. Star a team to mark yours.`};
    else if (teams.length) mine = {state: "none", text: "No team marked as yours yet"};
    else mine = {state: "none", text: ""};

    let state;
    if (!teams.length) state = unreadable ? "error" : "empty";
    else if (o.valuesReady === false) state = "loading";
    else if (partial || emptyTeams.length) state = "partial";
    else state = "loaded";

    const storage = teams.length || o.saveStatus === "unavailable" || o.saveStatus === "full"
      ? (STORAGE[o.saveStatus] || STORAGE.idle) : null;
    const origin = teams.length && o.origin ? ORIGIN[o.origin] || null : null;

    const counts = {teams: teams.length, players, notEvaluated, emptyTeams: emptyTeams.length};
    const countText = teams.length ? `${plural(teams.length, "team")} · ${plural(players, "player")}` : "";
    let headline;
    if (state === "error") headline = "Saved league could not be read";
    else if (!teams.length) headline = "No league loaded yet";
    else headline = countText;

    // The collapsed line: counts, the star and the saved state. Nothing here is a value or a rank.
    const summary = teams.length
      ? [countText, mine.state === "marked" ? mine.text : mine.state === "removed" ? "Your team was removed" : "No team marked", storage ? storage.text : null].filter(Boolean).join(" · ")
      : headline;

    const facts = teams.length ? [
      {id: "teams", label: "Teams", value: String(teams.length)},
      {id: "players", label: "Players on rosters", value: notEvaluated ? `${players} (${notEvaluated} K or DEF, not evaluated)` : String(players)},
      {id: "mine", label: "Your team", value: marked ? marked.name : "Not marked"},
      origin ? {id: "origin", label: "Came from", value: origin} : null,
      storage ? {id: "storage", label: "Saved", value: storage.text} : null
    ].filter(Boolean) : [];

    const notes = [];
    if (state === "loading") notes.push("Player values are still loading. Counts above are from your saved rosters.");
    if (state === "empty") notes.push("Paste your league's rosters page, or add a team and fill it. It saves on this device.");

    return {state, title: teams.length ? (ws.name || "Your league") : "Your league", headline, summary, counts, myTeam: marked ? {id: marked.id, name: marked.name} : null,
      mine, storage, origin, facts, issues, notes};
  }

  // ---------- DOM ----------
  function el(doc, tag, attrs, ...kids) {
    const node = doc.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else if (k === "hidden") node.hidden = Boolean(v);
      else node.setAttribute(k, v === true ? "" : String(v));
    });
    kids.filter(Boolean).forEach(kid => node.append(kid));
    return node;
  }

  let mounts = 0;
  function mount(host, opts) {
    const o = opts || {};
    const doc = o.document || host.ownerDocument || root.document;
    const store = o.store;
    mounts += 1;
    const base = o.id || `v2LgStatus${mounts}`;
    let expanded = o.expanded !== false;
    let origin = null;
    let lastMine = null;
    let removedMine = null;
    let lastSummary = null;

    const titleText = el(doc, "span", {class: "v2-ls-title"});
    const toggle = el(doc, "button", {type: "button", class: "v2-ls-toggle", id: `${base}Toggle`, "aria-controls": `${base}Body`, "aria-expanded": String(expanded)},
      el(doc, "span", {class: "v2-ls-caret", "aria-hidden": "true"}), titleText);
    const heading = el(doc, o.headingTag || "h2", {class: "v2-ls-heading"}, toggle);
    const summary = el(doc, "p", {class: "v2-ls-summary", id: `${base}Summary`});
    toggle.setAttribute("aria-describedby", summary.id);
    const facts = el(doc, "dl", {class: "v2-ls-facts", id: `${base}Facts`});
    const issues = el(doc, "ul", {class: "v2-ls-issues", id: `${base}Issues`});
    const notes = el(doc, "div", {class: "v2-ls-notes", id: `${base}Notes`});
    const slot = el(doc, "div", {class: "v2-ls-controls", id: `${base}Controls`});
    if (o.controls) slot.append(o.controls);
    const body = el(doc, "div", {class: "v2-ls-body", id: `${base}Body`, role: "region", "aria-labelledby": toggle.id}, facts, issues, notes, slot);
    const live = el(doc, "p", {class: "v2-sr v2-ls-live", id: `${base}Live`, role: "status", "aria-live": "polite"});
    const card = el(doc, "section", {class: "v2-ls", id: base, "data-state": "empty"}, heading, summary, body, live);
    host.append(card);

    function paint(model) {
      card.setAttribute("data-state", model.state);
      card.setAttribute("data-expanded", String(expanded));
      titleText.textContent = model.title;
      summary.textContent = model.summary;
      toggle.setAttribute("aria-expanded", String(expanded));
      body.hidden = !expanded;
      facts.replaceChildren(...model.facts.flatMap(f => [el(doc, "dt", {text: f.label, "data-fact": f.id}), el(doc, "dd", {text: f.value, "data-fact": f.id})]));
      facts.hidden = !model.facts.length;
      issues.replaceChildren(...model.issues.map(i => el(doc, "li", {class: `v2-ls-issue is-${i.tone}`, "data-issue": i.id, text: i.text})));
      issues.hidden = !model.issues.length;
      notes.replaceChildren(...model.notes.map(n => el(doc, "p", {class: "v2-meta", text: n})));
      notes.hidden = !model.notes.length;
      // Announce a change in what is loaded, not every redraw (a save tick alone stays quiet).
      const spoken = [model.headline, model.mine.text].filter(Boolean).join(". ");
      if (lastSummary !== null && spoken !== lastSummary) live.textContent = spoken;
      lastSummary = spoken;
    }

    function input(reason) {
      const ws = store ? store.get() : null;
      const parsed = typeof o.parsed === "function" ? o.parsed() : null;
      // An empty league has no origin: teams added by hand afterwards were not read from anywhere.
      origin = ws && ws.teams.length ? originFor(origin, reason) : null;
      const marked = ws && ws.teams.find(t => t.id === ws.myTeamId);
      // A starred team that leaves the league (Remove, Clear all) is named once. A new league from a file, a link or
      // the saved copy is not a removal. The store may report a save before the change itself, so this keys off the
      // team's id being gone, not the change reason.
      if (reason === "load" || reason === "replace") { removedMine = null; lastMine = null; }
      if (marked) { lastMine = {id: marked.id, name: marked.name}; removedMine = null; }
      else if (lastMine && ws && !ws.teams.some(t => t.id === lastMine.id)) { removedMine = lastMine; lastMine = null; }
      else lastMine = null;
      if (ws && removedMine && ws.teams.some(t => t.id === removedMine.id)) removedMine = null; // Undo put it back
      return {workspace: ws, loadStatus: store && store.loadStatus ? store.loadStatus() : "ok", saveStatus: store && store.status ? store.status() : "idle",
        origin, parsed, valuesReady: typeof o.valuesReady === "function" ? Boolean(o.valuesReady()) : true, removedMine, isNotEvaluated: o.isNotEvaluated};
    }
    let model = null;
    function update(reason) { model = describe(input(reason)); paint(model); return model; }
    function setExpanded(open) {
      expanded = Boolean(open);
      if (model) paint(model);
      if (typeof o.onToggle === "function") o.onToggle(expanded);
    }

    toggle.addEventListener("click", () => setExpanded(!expanded));
    body.addEventListener("keydown", event => {
      if (event.key !== "Escape" || !expanded) return;
      // An open menu or listbox inside the controls handles its own Escape first.
      const t = event.target;
      if (t && t.closest && t.closest("[aria-expanded='true']")) return;
      setExpanded(false);
      toggle.focus();
    });

    const offs = [];
    if (store && store.onChange) offs.push(store.onChange((ws, change) => update(change && change.reason)));
    if (store && store.onStatus) offs.push(store.onStatus(() => update("status")));
    update("load");
    return {update, setExpanded, isExpanded: () => expanded, model: () => model, node: card, toggle,
      destroy() { offs.forEach(off => { if (typeof off === "function") off(); }); card.remove(); }};
  }

  const api = {describe, originFor, mount, STORAGE, ORIGIN};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueLeagueStatus = api;
})(typeof window !== "undefined" ? window : globalThis);
