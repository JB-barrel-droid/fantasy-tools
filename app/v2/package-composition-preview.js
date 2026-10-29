// Trade Value v2 — selected-package composition and legality preview (JEG-1275, part of JEG-1183).
//
// Shows a package of trades that someone else has ALREADY chosen, in the order given: who is in it, how many players are
// listed on each side, whether the roster check passed, and the final lineup when a lineup is supplied. It never selects,
// ranks, searches, prices or re-orders trades, and it holds no copy of the package rules: the roster check is the injected
// JEG-1262 adapter (the TradePackageConstraints shape: validatePackage / applyPackage), read as it answers.
//
// The final lineup is shown only from a separately supplied lineup adapter. applyPackage's rosters keep each player's
// recorded slot (two RBs can both arrive as "RB"), so they are not a lineup and are never shown or relabelled as one:
// without a lineup adapter the section says the final lineup is unavailable.
//
//   TradeValuePackagePreview.viewModel(ctx)            -> the exact strings to show (pure; never mutates ctx)
//   TradeValuePackagePreview.render(container, vm)     -> draws vm into container
//   TradeValuePackagePreview.mount(container, opts)    -> render(viewModel(opts.getContext())); returns {update()}
//
// Context (an adapter hands it in; nothing here reads the workspace, the network or storage):
//   {fixture?: {kind: "synthetic" | "historical", label},   // set by every fixture; absent only for a live adapter
//    league: {myTeamId, teams: [{id, name?, entries: [{key, name, pos, slot?}]}]},   // as JEG-1262 reads it
//    trades: [{opponentId, give: [ref], receive: [ref]}] | null,                     // preselected, in order
//    package: {validatePackage(league, trades), applyPackage(league, trades)} | null, // the JEG-1262 adapter
//    lineup: {lineups(league, applied) -> {before, after, complete?, missing?: [text]}} | null}
//   ref = a key string, {key} or {player_key}, optionally with a name; a lineup side = {starters: [row], bench: [row]},
//   row = {slot, key, name}. Lineup rows are shown exactly as supplied, in order; nothing is recalculated.
(function (root) {
  "use strict";

  const NAME = "Selected package";
  const NOTE = "This checks only that the selected trades can happen together on these rosters. It does not judge value, fairness or whether a manager would accept.";
  const isObject = v => Boolean(v) && typeof v === "object" && !Array.isArray(v);
  const text = v => (typeof v === "string" && v.trim() ? v : null);
  const keyText = v => (typeof v === "string" && v.trim() ? v : typeof v === "number" && Number.isFinite(v) ? String(v) : null);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;

  // ---------- display names, read from the original league only ----------
  function lookups(league) {
    const teams = new Map();
    const players = new Map();
    const list = isObject(league) && Array.isArray(league.teams) ? league.teams : [];
    list.forEach(team => {
      if (!isObject(team)) return;
      const id = keyText(team.id);
      if (id !== null && !teams.has(id)) teams.set(id, text(team.name) || id);
      (Array.isArray(team.entries) ? team.entries : []).forEach(entry => {
        const key = isObject(entry) ? keyText(entry.key) : null;
        if (key !== null && !players.has(key)) players.set(key, text(entry.name) || key);
      });
    });
    return {teams, players};
  }
  function refName(ref, names) {
    if (!isObject(ref)) {
      const key = keyText(ref);
      return key === null ? "A player with no key" : names.players.get(key) || key;
    }
    if (text(ref.name)) return ref.name;
    const key = keyText(ref.key) !== null ? keyText(ref.key) : keyText(ref.player_key);
    return key === null ? "A player with no key" : names.players.get(key) || key;
  }

  // ---------- counts: the shown composition only ----------
  // Trades shown, distinct counterparties they name, and players listed on each side, as listed (a player listed twice
  // counts twice; the roster check says whether that is allowed).
  function countsOf(trades) {
    const rows = Array.isArray(trades) ? trades : [];
    const named = new Set();
    let give = 0;
    let receive = 0;
    rows.forEach(t => {
      if (!isObject(t)) return;
      const id = keyText(t.opponentId);
      if (id !== null) named.add(id);
      if (Array.isArray(t.give)) give += t.give.length;
      if (Array.isArray(t.receive)) receive += t.receive.length;
    });
    const out = {trades: rows.length, counterparties: named.size, give, receive};
    out.text = rows.length
      ? `${plural(out.trades, "trade")} naming ${plural(out.counterparties, "other team")}. Listed: ${plural(give, "player")} you give, ${plural(receive, "player")} you get.`
      : "No trades selected.";
    return out;
  }

  const errorText = e => (isObject(e) && text(e.message)) || (isObject(e) && text(e.code)) || "A problem the roster check did not describe.";
  // A usable roster-check answer: {ok: boolean, errors: array}, with no errors when ok. Anything else is unavailable.
  const readable = r => isObject(r) && typeof r.ok === "boolean" && Array.isArray(r.errors) && (!r.ok || r.errors.length === 0) && (r.ok || r.errors.length > 0);

  function legality(ctx, trades) {
    const adapter = ctx.package;
    if (!adapter || typeof adapter.validatePackage !== "function") {
      return {status: "unavailable", errors: [], reason: "Roster check unavailable: no roster check was supplied for this package."};
    }
    let result;
    try { result = adapter.validatePackage(ctx.league, trades); } catch (error) {
      return {status: "unavailable", errors: [], reason: `Roster check unavailable: it failed to run (${String(error && error.message || error)}).`};
    }
    if (!readable(result)) return {status: "unavailable", errors: [], reason: "Roster check unavailable: its answer could not be read."};
    if (result.ok) return {status: "passed", errors: [], reason: null};
    return {status: "failed", reason: null,
      errors: result.errors.map(e => ({code: isObject(e) && text(e.code) || null, text: errorText(e),
        tradeIndex: isObject(e) && Number.isInteger(e.tradeIndex) ? e.tradeIndex : null}))};
  }

  // ---------- the final lineup: supplied, never computed ----------
  const rowOf = r => {
    const row = isObject(r) ? r : {};
    const key = keyText(row.key);
    return {slot: keyText(row.slot) || "", key, name: text(row.name) || key || "Empty"};
  };
  const sideOf = s => (isObject(s) && Array.isArray(s.starters)
    ? {starters: s.starters.map(rowOf), bench: (Array.isArray(s.bench) ? s.bench : []).map(rowOf)} : null);
  const unavailable = reason => ({status: "unavailable", reason, missing: [], before: null, after: null});

  function lineup(ctx, trades, check) {
    if (check.status !== "passed") return unavailable("Final lineup unavailable until the roster check passes.");
    const adapter = ctx.lineup;
    if (!adapter || typeof adapter.lineups !== "function") {
      return unavailable("Final lineup unavailable: no lineup was supplied for this package. The roster check moves players between rosters; it does not set a lineup.");
    }
    let applied;
    try { applied = ctx.package.applyPackage(ctx.league, trades); } catch (error) { applied = null; }
    if (!isObject(applied) || applied.ok !== true || !isObject(applied.league)) {
      return unavailable("Final lineup unavailable: the package could not be applied to the rosters.");
    }
    let supplied;
    try { supplied = adapter.lineups(ctx.league, applied.league); } catch (error) { supplied = null; }
    const before = isObject(supplied) ? sideOf(supplied.before) : null;
    const after = isObject(supplied) ? sideOf(supplied.after) : null;
    if (!before || !after) return unavailable("Final lineup unavailable: the lineup supplied for this package could not be read.");
    const missing = (Array.isArray(supplied.missing) ? supplied.missing : []).map(m => text(m) || String(m));
    const empty = after.starters.filter(r => r.key === null).length;
    if (empty) missing.push(`${plural(empty, "starting slot is", "starting slots are")} empty in the supplied final lineup.`);
    const incomplete = supplied.complete === false || missing.length > 0;
    return {status: incomplete ? "incomplete" : "ready", reason: incomplete ? "The supplied final lineup is incomplete." : null,
      missing, before, after};
  }

  // ---------- the view model ----------
  function viewModel(input) {
    const ctx = isObject(input) ? input : {};
    const names = lookups(ctx.league);
    const vm = {name: NAME, note: NOTE, state: null, heading: "", fixture: isObject(ctx.fixture)
      ? {kind: ctx.fixture.kind, label: text(ctx.fixture.label)} : null,
    counts: countsOf(null), legality: null, trades: [], lineup: null};
    const none = ctx.trades === null || ctx.trades === undefined || (Array.isArray(ctx.trades) && ctx.trades.length === 0);
    if (none) {
      Object.assign(vm, {state: "empty", heading: "No package selected",
        legality: {status: "not_checked", errors: [], reason: "Nothing to check until trades are selected."},
        lineup: unavailable("Final lineup unavailable: no package is selected.")});
      return vm;
    }
    if (!Array.isArray(ctx.trades)) {
      Object.assign(vm, {state: "unavailable", heading: "Package unavailable",
        legality: {status: "unavailable", errors: [], reason: "Roster check unavailable: the selection is not a list of trades."},
        lineup: unavailable("Final lineup unavailable until the roster check passes.")});
      return vm;
    }
    const trades = ctx.trades;
    vm.counts = countsOf(trades);
    vm.legality = legality(ctx, trades);
    vm.trades = trades.map((t, index) => {
      const ok = isObject(t);
      const opp = ok ? keyText(t.opponentId) : null;
      const list = side => (ok && Array.isArray(t[side]) ? t[side].map(ref => refName(ref, names)) : []);
      const errors = vm.legality.errors.filter(e => e.tradeIndex === index).map(e => e.text);
      return {index, number: index + 1, readable: ok && Array.isArray(t.give) && Array.isArray(t.receive),
        opponentId: opp, opponent: opp === null ? "No team named" : names.teams.get(opp) || opp,
        give: list("give"), receive: list("receive"), errors, invalid: errors.length > 0};
    });
    vm.lineup = lineup(ctx, trades, vm.legality);
    vm.state = {passed: "valid", failed: "invalid", unavailable: "unavailable"}[vm.legality.status];
    vm.heading = {valid: "Roster check passed", invalid: `Roster check failed: ${plural(vm.legality.errors.length, "problem")}`,
      unavailable: "Roster check unavailable"}[vm.state];
    return vm;
  }

  // ---------- the DOM ----------
  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => {
      if (v === false || v === null || v === undefined) return;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v);
    });
    node.append(...kids.filter(k => k !== null && k !== undefined && k !== false));
    return node;
  }
  // A button that shows and hides one region, announced with aria-expanded (Enter and Space work, as on any button).
  function disclosure(id, label, region) {
    region.id = id;
    region.hidden = true;
    const button = el("button", {type: "button", class: "pcp-toggle", "aria-expanded": "false", "aria-controls": id, text: `Show ${label}`});
    button.addEventListener("click", () => {
      region.hidden = !region.hidden;
      button.setAttribute("aria-expanded", String(!region.hidden));
      button.textContent = `${region.hidden ? "Show" : "Hide"} ${label}`;
    });
    return button;
  }
  const players = list => (list.length ? el("ul", {class: "pcp-names"}, ...list.map(n => el("li", {text: n}))) : el("p", {class: "pcp-none", text: "Nobody"}));

  function tradeItem(t, prefix) {
    const region = el("div", {class: "pcp-trade-detail"},
      el("h4", {text: "You give"}), players(t.give),
      el("h4", {text: "You get"}), players(t.receive),
      t.errors.length ? el("ul", {class: "pcp-trade-errors"}, ...t.errors.map(e => el("li", {text: e}))) : null);
    return el("li", {class: `pcp-trade${t.invalid ? " is-invalid" : ""}`, "data-trade-index": String(t.index)},
      el("p", {class: "pcp-trade-head"},
        el("span", {class: "pcp-trade-title", text: `Trade ${t.number} with ${t.opponent}`}),
        t.invalid ? el("span", {class: "pcp-flag", text: "Has a problem"}) : null),
      el("p", {class: "pcp-trade-sum", text: t.readable ? `You give ${t.give.length}, you get ${t.receive.length}.` : "This trade could not be read."}),
      disclosure(`${prefix}-trade-${t.index}`, `players in trade ${t.number}`, region), region);
  }

  function lineupRows(rows, kind) {
    return el("table", {class: "pcp-lineup-table", "data-rows": kind},
      el("thead", {}, el("tr", {}, el("th", {scope: "col", text: "Slot"}), el("th", {scope: "col", text: "Player"}))),
      el("tbody", {}, ...rows.map(r => el("tr", {"data-key": r.key === null ? "" : r.key},
        el("th", {scope: "row", text: r.slot || "—"}), el("td", {text: r.name})))));
  }
  function lineupSide(label, side, kind, prefix) {
    const bench = el("div", {class: "pcp-bench"}, lineupRows(side.bench, "bench"));
    return el("section", {class: "pcp-lineup-side", "data-side": kind, "aria-label": `${label} lineup`},
      el("h4", {text: label}), lineupRows(side.starters, "starters"),
      disclosure(`${prefix}-bench-${kind}`, `${label.toLowerCase()} bench (${side.bench.length})`, bench), bench);
  }

  let sequence = 0;
  function render(container, vm) {
    const prefix = `pcp${++sequence}`;
    const kids = [el("h2", {id: `${prefix}-title`, class: "pcp-title", text: vm.name})];
    if (vm.fixture) {
      kids.push(el("p", {class: "pcp-fixture", role: "note", "data-fixture": vm.fixture.kind},
        el("b", {text: vm.fixture.kind === "historical" ? "Historical example. " : "Synthetic example. "}),
        vm.fixture.label || "Not your league and not a live package."));
    }
    kids.push(el("p", {class: "pcp-counts", text: vm.counts.text}));
    const L = vm.legality;
    kids.push(el("section", {class: `pcp-legality is-${L.status}`, role: L.status === "failed" ? "alert" : "status", "aria-label": "Roster check"},
      el("h3", {text: vm.heading}),
      L.reason ? el("p", {class: "pcp-reason", text: L.reason}) : null,
      L.errors.length ? el("ol", {class: "pcp-errors"}, ...L.errors.map(e => el("li", {"data-code": e.code || "", text: e.text}))) : null,
      vm.state !== "empty" ? el("p", {class: "pcp-note", text: vm.note}) : null));
    if (vm.trades.length) {
      kids.push(el("section", {class: "pcp-trades-wrap", "aria-label": "Trades in this package"},
        el("h3", {text: "Trades, in the order selected"}),
        el("ol", {class: "pcp-trades"}, ...vm.trades.map(t => tradeItem(t, prefix)))));
    }
    const Y = vm.lineup;
    kids.push(el("section", {class: `pcp-lineup is-${Y.status}`, "aria-label": "Final lineup"},
      el("h3", {text: "Final lineup"}),
      Y.reason ? el("p", {class: "pcp-reason", text: Y.reason}) : null,
      Y.missing.length ? el("ul", {class: "pcp-missing"}, ...Y.missing.map(m => el("li", {text: m}))) : null,
      Y.before ? el("div", {class: "pcp-lineup-sides"}, lineupSide("Before", Y.before, "before", prefix), lineupSide("After", Y.after, "after", prefix)) : null));
    container.replaceChildren(...kids);
    container.classList.add("package-preview");
    container.dataset.state = vm.state;
    container.dataset.lineup = Y.status;
    return container;
  }

  // opts: {getContext() -> context}. update() re-reads the context and redraws.
  function mount(container, opts) {
    const update = () => render(container, viewModel(opts.getContext()));
    update();
    return {update};
  }

  const api = {NAME, NOTE, countsOf, viewModel, render, mount};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValuePackagePreview = api;
})(typeof window !== "undefined" ? window : globalThis);
