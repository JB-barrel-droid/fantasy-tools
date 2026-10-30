// Trade Value v2 — Settings and local data in the Fieldnotes design (JEG-1140).
//
// Jeremy, 2026-10-29 (JEG-1140): "JEG-1140 can prepare isolated Settings components, with final integration following the
// shared foundation. Reuse the approved copy and design; don't request those approvals again." The design is the Fieldnotes
// Settings screen (JEG-1209, docs/design/jeg-1209-fieldnotes/prototype.html settings()); the value explanations use the
// JEG-1212 source framework (DDF Value and DDF Value (projections) are outputs; Projections, Published charts and Observed-trade
// estimates are input categories, with no publisher names in a category or a definition).
//
// Presentation only. No value math, no storage, no engine calls. Export, Import, Copy link, overrides and the selected-league
// entry keep their existing contracts: this file asks an adapter for them and never re-implements a format.
//
// Three layers, each usable alone:
//   * viewModel(ctx): pure. Context in, the exact strings and states to show out. Runs under node.
//   * render(container, vm): the DOM for a view model. mount(container, {getContext, actions}) draws it, keeps one stable
//     status region outside everything it redraws, runs the actions and keeps focus on the control that was used.
//   * liveAdapter(root): the dashboard's context and actions. It only reads public APIs (TradeValueWorkspace.store,
//     TradeValueV2.leagueQuery, DDFOverrides.count/basis/state) and delegates each action to the existing control that
//     already does it (#v2LgDownload, #v2LgLoad, #v2LgCopyLink, #v2OvExport, #v2OvImport). Not mounted on any route yet:
//     the Settings route and nav entry wait on the JEG-1137 shell.
//
// Context (what an adapter hands in):
//   {status: "loading" | "error" | "ready", error?: text,
//    fixture?: {label},                                   // set by every fixture; absent only for the live adapter
//    storage: {saving: "idle" | "saving" | "saved" | "unavailable" | "full"},
//    league: {name, teams, players, myTeam: name | null, settings: {scoring, teams, qb} | null} | null,   // null: no store
//    overrides: {count, basis: "default" | "custom"} | null}                                              // null: not loaded
// A count or setting that is not known is null and shows as Unavailable, never 0.
//
// Actions (each optional; a missing one is shown as unavailable): exportLeague, importLeague, copyLink, openLeague,
// exportOverrides, importOverrides, openOverrides. Each returns (or resolves to) {ok, message}.
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory(root);
  else root.TradeValueSettingsFieldnotes = factory(root);
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  // Every visible string, in one place, so the JEG-1130 copy lane can change wording without touching behavior.
  const T = {
    kicker: "Settings",
    title: "Your league. Your context.",
    sub: "Your data: saved on this device.",
    nav: "Settings sections",
    loading: "Loading your saved league and settings.",
    error: "Settings could not load.",
    fixture: label => `Sample data: ${label}. Not your league.`,
    savedTitle: "Keep a copy of your league.",
    savedLead: "Saved on this device. It doesn't sync to your other devices.",
    storage: {
      unavailable: "Private browsing: your teams won't be saved on this device between visits. Export a file to keep a copy.",
      full: "This device's storage is full. Export your league to keep a copy, then clear old data."
    },
    exportLabel: "Export", importLabel: "Import", linkLabel: "Copy link",
    exportName: "Export league", importName: "Import league", linkName: "Copy link to this league",
    exportHelp: "Export saves a file with every team, roster and your current league settings. Import opens that file on another device; if a league is already saved here, you choose whether to replace it.",
    linkHelp: "Copy a link that opens the league rosters and current league settings on another device. If the league is too large for a link, only your marked team travels; Export always keeps every team.",
    linkTools: "A compatible chatbot with DDF connected can read supported state fields; a plain URL does not connect tools.",
    noLeagueSaved: "No league saved on this device yet, so there is nothing to export or link.",
    leagueTitle: "League settings",
    savedLeague: "Saved league",
    selectedTeam: "Selected team",
    leagueRules: "Scoring and roster",
    noLeague: "No league saved yet",
    noTeam: "No team selected",
    pasteLeague: "Paste my league",
    changeTeam: "Change team",
    chooseTeam: "Choose your team",
    rulesHelp: "Your league settings, used for every value on the site.",
    unavailable: "Unavailable",
    rulesUnavailable: "They show once values load.",
    valuesTitle: "How values work",
    valuesLead: "Three explanations, with no universal winner.",
    views: [
      ["ddf-value", "DDF Value", "The main value for your chosen basis. The default combines league-adjusted published charts and an observed-trade estimate."],
      ["ddf-projections", "DDF Value (projections)", "Forecast production converted into league-specific trade-value points, averaged across available projection inputs. Not projected fantasy points."],
      ["combined", "Combined comparison", "The current combined comparison uses published charts and an observed-trade estimate on the comparison scale. It is not a prediction of acceptance."]
    ],
    points: "A value of 60 means 60 trade-value points under the shown recipe and your league settings. It is not 60 projected fantasy points, dollars or a 60% chance of acceptance. Zero is at or below the waiver line; a missing value is unavailable, never zero.",
    sourcesTitle: "Sources and limitations",
    categories: [
      ["Projections", "What might the player produce?", "A forecast is not guaranteed or judgment-free."],
      ["Published charts", "What should the player be worth?", "Published assessments, not completed transaction prices."],
      ["Observed-trade estimates", "What does completed-trade activity suggest?", "An inferred value from transactions, not a raw price or an acceptance probability."]
    ],
    categoriesNote: "Projections, Published charts and Observed-trade estimates are three different input categories. The approved framework changes how we explain them; the current group memberships, defaults and value rules are preserved.",
    limits: "Forecasts are uncertain. Published charts can disagree. A value read is not a prediction of another manager's decision.",
    overridesTitle: "Your overrides",
    overridesCount: n => `${n} player override${n === 1 ? "" : "s"} saved on this device.`,
    overridesZero: "No player overrides. Every player uses DDF Value as calculated.",
    overridesUnavailable: "Overrides are unavailable until values load.",
    overrideMeans: "An override replaces that player's DDF Value everywhere on the site. It is not a new source or a projection of future scoring.",
    basisDefault: "Value basis: the default DDF Value.",
    basisCustom: "Value basis: your own choice of sources and weights.",
    basisMeans: "The basis decides what DDF Value means across the site. Choosing a display view never changes it.",
    openOverrides: "Open overrides",
    exportOverrides: "Export overrides", importOverrides: "Import overrides",
    actionUnavailable: "That isn't available here yet."
  };
  const SCORING = {standard: "Standard", half_ppr: "Half PPR", ppr: "Full PPR"};
  const SECTIONS = [["saved", "Saved data"], ["league", "League settings"], ["values", "How values work"], ["overrides", "Your overrides"]];

  const isCount = n => Number.isInteger(n) && n >= 0;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // ---------- pure view model ----------
  function rulesText(settings) {
    if (!settings || !SCORING[settings.scoring] || !isCount(settings.teams) || settings.teams === 0) return null;
    const qb = settings.qb === "superflex" ? "Superflex" : (isCount(settings.qb) && settings.qb > 0 ? `${settings.qb} QB` : null);
    return [SCORING[settings.scoring], `${settings.teams} teams`].concat(qb ? [qb] : []).join(" · ");
  }
  function viewModel(ctx) {
    const c = ctx && typeof ctx === "object" ? ctx : {status: "error"};
    const status = ["loading", "error", "ready"].includes(c.status) ? c.status : "error";
    const vm = {status, head: {kicker: T.kicker, title: T.title, sub: T.sub}, nav: SECTIONS.map(([id, text]) => ({id, text})),
      fixture: c.fixture && c.fixture.label ? T.fixture(c.fixture.label) : null};
    if (status !== "ready") { vm.message = status === "loading" ? T.loading : (c.error ? `${T.error} ${c.error}` : T.error); return vm; }

    const lg = c.league && typeof c.league === "object" ? c.league : null;
    const teams = lg && isCount(lg.teams) ? lg.teams : null;
    const players = lg && isCount(lg.players) ? lg.players : null;
    const hasLeague = teams !== null && teams > 0;
    const saving = c.storage && c.storage.saving;
    vm.saved = {
      title: T.savedTitle, lead: T.savedLead, warning: T.storage[saving] || null,
      actions: [
        {id: "exportLeague", text: T.exportLabel, name: T.exportName, primary: true, enabled: hasLeague},
        {id: "importLeague", text: T.importLabel, name: T.importName, enabled: true},
        {id: "copyLink", text: T.linkLabel, name: T.linkName, enabled: hasLeague}
      ],
      reason: lg && !hasLeague ? T.noLeagueSaved : null,
      help: [T.exportHelp, T.linkHelp, T.linkTools]
    };
    const rules = lg ? rulesText(lg.settings) : null;
    vm.league = {title: T.leagueTitle, rows: [
      {id: "saved-league", label: T.savedLeague,
        value: !lg || teams === null ? T.unavailable : (hasLeague ? `${lg.name || "My league"} · ${plural(teams, "team")}${players === null ? "" : ` · ${plural(players, "player")}`}` : T.noLeague)},
      {id: "selected-team", label: T.selectedTeam, value: !lg || teams === null ? T.unavailable : (lg.myTeam || T.noTeam),
        action: {id: "openLeague", text: !hasLeague ? T.pasteLeague : (lg.myTeam ? T.changeTeam : T.chooseTeam), enabled: true}},
      {id: "rules", label: T.leagueRules, value: rules || T.unavailable, help: rules ? T.rulesHelp : T.rulesUnavailable}
    ]};
    vm.values = {title: T.valuesTitle, lead: T.valuesLead, points: T.points,
      views: T.views.map(([id, title, body]) => ({id, title, body})),
      sources: {title: T.sourcesTitle, categories: T.categories.map(([name, question, limit]) => ({name, question, limit})),
        note: T.categoriesNote, limits: T.limits}};
    const ov = c.overrides && typeof c.overrides === "object" && isCount(c.overrides.count) ? c.overrides : null;
    vm.overrides = {title: T.overridesTitle,
      count: ov ? (ov.count ? T.overridesCount(ov.count) : T.overridesZero) : T.overridesUnavailable,
      basis: ov ? (ov.basis === "custom" ? T.basisCustom : T.basisDefault) : null,
      means: [T.overrideMeans, T.basisMeans],
      actions: [
        {id: "openOverrides", text: T.openOverrides, enabled: true},
        {id: "exportOverrides", text: T.exportOverrides, enabled: Boolean(ov && (ov.count || ov.basis === "custom"))},
        {id: "importOverrides", text: T.importOverrides, enabled: Boolean(ov)}
      ]};
    return vm;
  }

  // ---------- DOM ----------
  function el(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v;
      else node.setAttribute(k, v === true ? "" : String(v));
    });
    kids.flat().forEach(kid => { if (kid !== null && kid !== undefined && kid !== false) node.append(kid); });
    return node;
  }
  function actionButton(a, available) {
    const on = a.enabled && available(a.id);
    return el("button", {type: "button", class: `ddf-fn-btn${a.primary ? " ddf-fn-btn--primary" : ""}`, "data-action": a.id,
      "aria-label": a.name && a.name !== a.text ? a.name : null, disabled: !on, text: a.text});
  }
  function card(id, title, ...body) {
    return el("section", {class: "ddf-fn-settings-card", id: `ddfSet-${id}`, "aria-labelledby": `ddfSet-${id}-title`, "data-section": id},
      el("h2", {id: `ddfSet-${id}-title`, tabindex: "-1", text: title}), ...body);
  }
  // Draws vm into container (replacing what was there). available(id) says whether an action exists.
  function render(container, vm, available) {
    const can = typeof available === "function" ? available : () => true;
    const head = el("header", {class: "ddf-fn-settings-head"},
      el("p", {class: "ddf-fn-settings-kicker", text: vm.head.kicker}),
      el("h1", {class: "ddf-fn-display", id: "ddfSetTitle", text: vm.head.title}),
      el("p", {class: "ddf-fn-settings-sub", text: vm.head.sub}));
    const parts = [head];
    if (vm.fixture) parts.push(el("p", {class: "ddf-fn-settings-fixture", "data-fixture": "true", text: vm.fixture}));
    if (vm.status !== "ready") {
      parts.push(el("p", {class: "ddf-fn-settings-state", "data-state": vm.status, text: vm.message}));
      container.replaceChildren(...parts);
      container.dataset.state = vm.status;
      return;
    }
    const nav = el("nav", {class: "ddf-fn-settings-nav", "aria-label": T.nav},
      el("ul", {}, vm.nav.map(n => el("li", {}, el("button", {type: "button", class: "ddf-fn-settings-navlink", "data-scroll": n.id, text: n.text})))));
    const s = vm.saved;
    const saved = card("saved", s.title,
      el("p", {class: "ddf-fn-settings-lead", text: s.lead}),
      s.warning ? el("p", {class: "ddf-fn-settings-warn", "data-warn": "storage", text: s.warning}) : null,
      el("div", {class: "ddf-fn-settings-actions", role: "group", "aria-label": s.title}, s.actions.map(a => actionButton(a, can))),
      s.reason ? el("p", {class: "ddf-fn-settings-meta", "data-reason": "no-league", text: s.reason}) : null,
      s.help.map(text => el("p", {class: "ddf-fn-settings-meta", text})));
    const rows = el("dl", {class: "ddf-fn-settings-rows"}, vm.league.rows.map(r => el("div", {class: "ddf-fn-settings-row", "data-row": r.id},
      el("dt", {text: r.label}),
      el("dd", {"data-unavailable": r.value === T.unavailable ? "true" : null},
        el("span", {class: "ddf-fn-settings-value", text: r.value}),
        r.help ? el("span", {class: "ddf-fn-settings-meta", text: r.help}) : null),
      r.action ? el("div", {class: "ddf-fn-settings-rowaction"}, actionButton(r.action, can)) : null)));
    const league = card("league", vm.league.title, rows);
    const v = vm.values;
    const disclosure = (id, title, ...body) => el("details", {class: "ddf-fn-disclosure", "data-disclosure": id},
      el("summary", {text: title}), el("div", {class: "ddf-fn-settings-disclosure-body"}, ...body));
    const values = card("values", v.title,
      el("p", {class: "ddf-fn-settings-lead", text: v.lead}),
      el("p", {class: "ddf-fn-settings-meta", text: v.points}),
      v.views.map(view => disclosure(view.id, view.title, el("p", {text: view.body}))),
      disclosure("sources", v.sources.title,
        el("dl", {class: "ddf-fn-settings-categories"}, v.sources.categories.map(cat => el("div", {},
          el("dt", {text: cat.name}), el("dd", {}, el("span", {text: cat.question}), " ", el("span", {class: "ddf-fn-settings-meta", text: cat.limit}))))),
        el("p", {class: "ddf-fn-settings-meta", text: v.sources.note}),
        el("p", {class: "ddf-fn-settings-meta", text: v.sources.limits})));
    const o = vm.overrides;
    const overrides = card("overrides", o.title,
      el("p", {class: "ddf-fn-settings-lead", "data-count": "overrides", text: o.count}),
      o.basis ? el("p", {class: "ddf-fn-settings-meta", "data-basis": "true", text: o.basis}) : null,
      o.means.map(text => el("p", {class: "ddf-fn-settings-meta", text})),
      el("div", {class: "ddf-fn-settings-actions", role: "group", "aria-label": o.title}, o.actions.map(a => actionButton(a, can))));
    parts.push(el("div", {class: "ddf-fn-settings-grid"}, nav, el("div", {class: "ddf-fn-settings-main"}, saved, league, values, overrides)));
    container.replaceChildren(...parts);
    container.dataset.state = "ready";
  }

  // ---------- mount ----------
  // opts: {getContext: () => ctx, actions: {name: () => {ok, message} | Promise}}. Returns {update, destroy, element}.
  function mount(container, opts) {
    const o = opts || {};
    const actions = o.actions || {};
    const host = el("div", {class: "ddf-fn-settings"});
    const body = el("div", {class: "ddf-fn-settings-body"});
    // One status region, made once and never rebuilt, so every result is announced (JEG-1250 review, live regions).
    const status = el("p", {class: "ddf-fn-settings-status", role: "status", "aria-live": "polite", "aria-atomic": "true", id: "ddfSetStatus"});
    host.append(body, status);
    container.replaceChildren(host);
    const available = id => typeof actions[id] === "function";
    // One pending action (an open file picker) blocks only its own button, never the others (JEG-1306).
    const pending = new Set();

    function update() {
      const active = document.activeElement;
      const keep = active && body.contains(active)
        ? (active.dataset.action ? `[data-action="${active.dataset.action}"]`
          : active.dataset.scroll ? `[data-scroll="${active.dataset.scroll}"]`
            : active.closest("details") ? `[data-disclosure="${active.closest("details").dataset.disclosure}"] > summary` : null)
        : null;
      const open = Array.from(body.querySelectorAll("details[open]")).map(d => d.dataset.disclosure);
      let ctx;
      try { ctx = o.getContext ? o.getContext() : {status: "error"}; } catch (error) { ctx = {status: "error"}; }
      render(body, viewModel(ctx), available);
      pending.forEach(id => { const b = body.querySelector(`[data-action="${id}"]`); if (b) b.setAttribute("aria-busy", "true"); });
      open.forEach(id => { const d = body.querySelector(`details[data-disclosure="${id}"]`); if (d) d.open = true; });
      if (keep) {
        const next = body.querySelector(keep);
        if (next && !next.disabled) next.focus();
        else { const h = active && active.closest && active.closest("section"); const t = h && body.querySelector(`#${h.id} h2`); if (t) t.focus(); }
      }
    }
    let said = 0;
    function say(r) {
      status.dataset.tone = r.ok === false ? "error" : "ok";
      // Cleared now and written on the next task, so a second identical result is announced again.
      status.textContent = "";
      const n = ++said;
      setTimeout(() => { if (n === said) status.textContent = r.message || ""; }, 0);
    }
    async function run(id, button) {
      if (pending.has(id)) return;
      pending.add(id);
      button.setAttribute("aria-busy", "true");
      let result;
      try { result = await actions[id](); } catch (error) { result = {ok: false, message: T.actionUnavailable}; }
      pending.delete(id);
      say(result && typeof result === "object" ? result : {ok: true, message: ""});
      const current = body.querySelector(`[data-action="${id}"]`);
      if (current) current.removeAttribute("aria-busy");
      if (button.isConnected) button.removeAttribute("aria-busy");
      update();
    }
    function onClick(event) {
      const b = event.target.closest("button");
      if (!b || !body.contains(b) || b.disabled) return;
      if (b.dataset.scroll) {
        const section = body.querySelector(`[data-section="${b.dataset.scroll}"]`);
        if (section) { section.scrollIntoView({block: "start"}); section.querySelector("h2").focus({preventScroll: true}); }
        return;
      }
      if (b.dataset.action && available(b.dataset.action)) run(b.dataset.action, b);
    }
    body.addEventListener("click", onClick);
    update();
    return {update, element: host, status, destroy: () => { body.removeEventListener("click", onClick); host.remove(); }};
  }

  // ---------- the dashboard's adapter ----------
  // Parses the page's own league query (TradeValueV2.leagueQuery: scoring=..&teams=..&roster=QB1.RB2...SF0...) for display.
  function settingsFromQuery(query) {
    const p = new URLSearchParams(String(query || "").replace(/^[?&#]+/, ""));
    const scoring = p.get("scoring");
    const teams = Number(p.get("teams"));
    if (!SCORING[scoring] || !Number.isInteger(teams) || teams <= 0) return null;
    const roster = Object.fromEntries((p.get("roster") || "").split(".").map(part => {
      const m = /^([A-Z]+)(\d+)$/.exec(part);
      return m ? [m[1], Number(m[2])] : null;
    }).filter(Boolean));
    const qb = roster.SF > 0 ? "superflex" : (Number.isInteger(roster.QB) ? roster.QB : null);
    return {scoring, teams, qb};
  }
  function liveAdapter(win) {
    const w = win || root;
    const doc = w.document;
    const $ = id => doc.getElementById(id);
    const unavailable = {ok: false, message: T.actionUnavailable};
    // Resolves when check() returns a value, or with fallback() after ms. Watches the page's own status text.
    // wake(recheck), when given, hands the caller a way to re-run check() on an event that changes no DOM (a cancelled picker).
    function waitFor(check, ms, fallback, wake) {
      return new Promise(resolve => {
        const first = check();
        if (first) { resolve(first); return; }
        let timer = null;
        const obs = new w.MutationObserver(() => recheck());
        const recheck = () => { const v = check(); if (v) { obs.disconnect(); w.clearTimeout(timer); resolve(v); } };
        obs.observe(doc.body, {subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["hidden"]});
        timer = w.setTimeout(() => { obs.disconnect(); resolve(fallback()); }, ms);
        if (wake) wake(recheck);
      });
    }
    const notice = () => ($("v2LgNotice") ? $("v2LgNotice").textContent.trim() : "");
    // The league card's status line is cleared first, so a repeated result (two exports in a row) still reads as new.
    const clearNotice = () => { if ($("v2LgNotice")) $("v2LgNotice").textContent = ""; };
    // Clicks an existing control; the control's own handler does the work, in its own unchanged format.
    function press(id) { const b = $(id); if (!b) return false; b.click(); return true; }
    function leagueNotice(id, ms) {
      if (!$(id)) return unavailable;
      clearNotice();
      press(id);
      return waitFor(() => { const now = notice(); return now ? {ok: !/could not/i.test(now), message: now} : null; }, ms,
        () => ({ok: true, message: notice()}));
    }
    // A file picker closed without a file ends the wait: the input's own cancel event, or, where a browser has none
    // (Safari before 16.4), the window getting focus back with no file chosen.
    function onCancel(input, done) {
      if (!input) return;
      let over = false;
      const end = () => { if (!over) { over = true; done({ok: true, message: ""}); } };
      input.addEventListener("cancel", end, {once: true});
      input.addEventListener("change", () => { over = true; }, {once: true});
      const prior = input.files && input.files[0];   // a reused input can still hold the last file it was given
      w.addEventListener("focus", () => w.setTimeout(() => { const f = input.files && input.files[0]; if (!f || f === prior) end(); }, 1000), {once: true});
    }
    // The Overrides tab adds a new #v2OvImportFile on every press and drops it only on a file, so after a cancelled
    // picker there are several: the new one is the one not there before the press.
    const fileInputs = id => Array.from(doc.querySelectorAll(`input[type="file"][id="${id}"]`));
    const overridesReady = () => Boolean(w.DDFOverrides && w.DDFOverrides.state && w.DDFOverrides.state.engine);
    function getContext() {
      const W = w.TradeValueWorkspace;
      if (!W || !W.store) return {status: "loading"};
      const ws = W.store.get();
      const mine = ws.teams.find(t => t.id === ws.myTeamId);
      let query = "";
      try { query = w.TradeValueV2 && w.TradeValueV2.leagueQuery ? w.TradeValueV2.leagueQuery() : ""; } catch (error) { query = ""; }
      const O = w.DDFOverrides;
      return {status: "ready", storage: {saving: W.store.status()},
        league: {name: ws.name, teams: ws.teams.length, players: ws.teams.reduce((n, t) => n + t.entries.length, 0),
          myTeam: mine ? mine.name : null, settings: settingsFromQuery(query)},
        overrides: overridesReady() ? {count: O.count(), basis: O.basis().mode === "default" ? "default" : "custom"} : null};
    }
    const actions = {
      exportLeague: () => leagueNotice("v2LgDownload", 1500),
      copyLink: () => leagueNotice("v2LgCopyLink", 3000),
      // The existing Load picks the file and, when a league is saved here, asks replace-or-keep on Your league.
      importLeague: () => {
        if (!$("v2LgLoad")) return unavailable;
        clearNotice();
        let cancelled = null;
        let recheck = () => {};
        onCancel($("v2LgFile"), r => { cancelled = r; recheck(); });
        // A replace prompt already showing before this press is not this import's answer. league.js rebuilds the
        // prompt's children for each file, so a new first child is a new prompt even for the same file twice.
        const old = $("v2LgLoadConfirm");
        const shown = old && !old.hidden ? old.firstChild : undefined;
        press("v2LgLoad");
        return waitFor(() => {
          if (cancelled) return cancelled;
          const confirm = $("v2LgLoadConfirm");
          if (confirm && !confirm.hidden && confirm.firstChild !== shown) {
            w.location.hash = "#find-league";
            const yes = $("v2LgLoadYes");
            if (yes) w.setTimeout(() => yes.focus(), 0);
            return {ok: true, message: confirm.textContent.trim()};
          }
          const now = notice();
          // A load ends "N teams loaded."; anything else is the importer's own error text.
          return now ? {ok: /\bloaded\.$/.test(now), message: now} : null;
        }, 120000, () => ({ok: true, message: ""}), r => { recheck = r; });
      },
      openLeague: () => { w.location.hash = "#find-league"; return {ok: true, message: ""}; },
      openOverrides: () => { w.location.hash = "#value-overrides"; return {ok: true, message: ""}; },
      exportOverrides: () => {
        if (!overridesReady()) return unavailable;
        w.DDFOverrides.render();
        return press("v2OvExport") ? {ok: true, message: "Downloaded ddf-overrides.json."} : unavailable;
      },
      importOverrides: () => {
        if (!overridesReady()) return unavailable;
        w.DDFOverrides.render();
        // The Overrides tab redraws its note on every import, so a new note element is the new result.
        const before = $("v2OvImportNote");
        const inputsBefore = fileInputs("v2OvImportFile");
        if (!press("v2OvImport")) return unavailable;
        let cancelled = null;
        let recheck = () => {};
        onCancel(fileInputs("v2OvImportFile").find(i => !inputsBefore.includes(i)), r => { cancelled = r; recheck(); });
        return waitFor(() => {
          if (cancelled) return cancelled;
          const n = $("v2OvImportNote");
          return n && n !== before && n.textContent.trim() ? {ok: !/nothing was changed/.test(n.textContent), message: n.textContent.trim()} : null;
        }, 120000, () => ({ok: true, message: ""}), r => { recheck = r; });
      }
    };
    return {getContext, actions};
  }

  return {viewModel, render, mount, liveAdapter, settingsFromQuery, rulesText, STRINGS: T};
});
