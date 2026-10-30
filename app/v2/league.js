// Trade Value v2 — Your league (JEG-1021): any number of named teams, a team summary and a trade opportunities table.
//
// Three cards above the two-team finder on the Find a trade tab:
//   * Your league: add, name, fill (paste or search), reorder, clear and remove teams; one marked "my team"; saved in this
//     browser as you type (workspace.js), with Download / Load / Copy;
//   * Team summary: roster, starter and bench value in DDF Value and the Trade chart average, a rank in each view, strengths,
//     weaknesses and the players the market prices away from DDF Value (team-summary.js);
//   * Trade opportunities: my team against every other team in one sortable table (opportunities.js).
// No value math here: every number comes from the modules above, which use finder.js and the engine's own rows.
(function (root) {
  "use strict";
  if (typeof document === "undefined") return;
  const W = root.TradeValueWorkspace;
  const F = root.TradeValueFinder;
  const T = root.TradeValueTeamSummary;
  const O = root.TradeValueOpportunities;
  const S = root.TradeValueTableSort;
  const L = root.TradeValueLineupComparison;
  if (!W || !F || !T || !O || !S || !L || !F.page) return;
  const store = W.store;
  const engine = () => root.TradeValueCurveControls;
  const $ = id => document.getElementById(id);
  const finite = v => typeof v === "number" && Number.isFinite(v);
  const OUR_KEY = "ddf_value";
  const MARKET_KEY = "chart_avg";
  const PAGE = 10;   // JEG-1098: the opportunities list opens on the top 10; "Show 10 more" and "Show all" reveal the rest
  const OPP_DEBOUNCE_MS = 300;
  const money = n => n.toFixed(1);
  const signed = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1));
  const plural = (n, word, many) => `${n} ${n === 1 ? word : (many || `${word}s`)}`;
  const listJoin = items => (items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (v === false || v === null || v === undefined) return; if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : v); });
    node.append(...kids.filter(k => k !== null && k !== undefined && k !== false));
    return node;
  }
  const button = (text, props, onClick) => { const b = el("button", {type: "button", ...(props || {})}, text); if (onClick) b.addEventListener("click", onClick); return b; };

  // ---------- state that is not saved ----------
  const UI = {collapsed: new Map(), renaming: null, confirmRemove: null, confirmLoad: null, undo: null, comps: new Map(), oppsShown: PAGE, expanded: new Set(), expandedCores: new Set(), result: null,
    running: false, runId: 0, timer: null, cache: O.createCache(), notice: "", justAdded: null, ready: false, firstPaint: true};

  function announce(text) { const live = $("v2LgLive"); if (live) { live.textContent = ""; live.textContent = text; } }
  function notice(text) { UI.notice = text; const n = $("v2LgNotice"); if (n) n.textContent = text; }
  const leagueQuery = () => root.TradeValueV2 && root.TradeValueV2.leagueQuery ? root.TradeValueV2.leagueQuery() : "";
  const settingsSnapshot = () => ({...(store.get().settings || {}), query: leagueQuery()});

  // Wait for a plausible full league before warning about its team count. The engine currently prices 8/10/12/14 teams.
  function renderCountMismatch() {
    const box = $("v2LgMismatch");
    if (!box || !engine() || !engine().getState) return;
    const count = store.get().teams.length;
    const priced = engine().getState().teams;
    box.hidden = count < 8 || count === priced;
    if (box.hidden) { box.replaceChildren(); return; }
    const supported = [8, 10, 12, 14].includes(count);
    box.replaceChildren(...[el("span", {text: `Your league has ${count} teams, but league settings use ${priced}. `}),
      supported ? button(`Use ${count} teams in league settings`, {class: "v2-btn", id: "v2LgMatchTeams"}, () => {
        const V = root.TradeValueV2;
        if (V && V.applyLinkLeague) {
          const params = new URLSearchParams(leagueQuery());
          params.set("teams", String(store.get().teams.length));
          V.applyLinkLeague(params);
          renderCountMismatch();
          announce(`League settings now use ${store.get().teams.length} teams.`);
        }
      }) : el("span", {text: "Values currently support 8, 10, 12 or 14 teams. "}),
      !supported ? button("Edit league settings", {class: "v2-btn"}, () => { const edit = $("v2EditLeague"); if (edit) edit.click(); }) : null].filter(Boolean));
  }

  // ---------- the engine, read once per render ----------
  function mathContext() {
    const C = engine();
    if (!C || !C.getAllRows) return null;
    const all = C.getAllRows();
    if (!all.length) return null;
    const rowsByKey = new Map(all.map(r => [String(r.player_key), r]));
    const shape = C.getRosterShape ? C.getRosterShape() : null;
    let expected = null;
    try { expected = F.expectedDepth(C.getAdjustmentWeights().allocation, C.getState().teams); } catch (error) { expected = null; }
    const info = C.getSourceInfo ? C.getSourceInfo() : [];
    const available = new Set(info.filter(item => item.available).map(item => item.key));
    const charts = F.CHART_KEYS.filter(key => available.has(key));
    const market = charts.length >= F.MIN_CHARTS ? charts : null;
    const readout = C.getBenchShareReadout ? C.getBenchShareReadout() : null;
    const overall = readout && finite(readout.overall) ? readout.overall : (C.getBenchShare ? C.getBenchShare() : null);
    const weights = {overall: finite(overall) ? overall : 0};
    F.DEPTH_POS.forEach(pos => { if (readout && finite(readout[pos])) weights[pos] = readout[pos]; });
    return {rowsByKey, shape, expected, charts, market, chartKeys: market, weights};
  }
  const rowsOfTeam = (team, ctx) => team.entries.map(e => ctx.rowsByKey.get(e.key)).filter(Boolean);
  const isK = entry => F.isNotEvaluated(entry);

  // ---------- team list ----------
  const teamById = (ws, id) => ws.teams.find(t => t.id === id);
  const update = (fn, reason) => store.update(fn, reason);
  const rosterNote = team => `${plural(team.entries.length, "player")}`;

  // Entries from engine rows, with the slot a pasted page gave.
  const entryOf = (row, slot) => ({key: String(row.player_key), name: row.name, pos: row.pos, team: row.team || undefined, slot: slot || undefined});
  const holderOf = (ws, key, exceptId) => ws.teams.find(t => t.id !== exceptId && t.entries.some(e => e.key === key));
  const chipsFor = (entry, ctx) => {
    const row = ctx && ctx.rowsByKey.get(entry.key);
    if (isK(entry)) return el("span", {class: "v2-find-noteval", text: "Not evaluated"});
    if (!row) return el("span", {class: "v2-find-noteval", text: "Not in this week's values"});
    const ddf = row.values ? row.values[OUR_KEY] : null;
    const avg = ctx.market ? F.withChartAverage([row], ctx.market)[0].values[MARKET_KEY] : null;
    const chip = (kind, label, value) => el("span", {class: `v2-find-chip${finite(value) ? "" : " is-missing"}`, "data-kind": kind},
      el("span", {class: "v2-find-chip-value", text: finite(value) ? value.toFixed(1) : "no value"}), el("span", {class: "v2-find-chip-label", text: ` ${label}`}));
    return el("span", {class: "v2-find-chips"}, chip("ddf", "DDF Value", ddf), chip("market", ctx.market ? "Trade chart average" : "Trade chart average (too few charts)", avg));
  };

  // Paste and search for one team. Returns the body node and a render() for its player list.
  function teamBody(teamId, bodyId) {
    const input = el("textarea", {id: `${bodyId}-in`, rows: "1", placeholder: "Search a player, or paste a team page", autocomplete: "off", spellcheck: "false",
      "aria-controls": `${bodyId}-res`, "aria-describedby": `${bodyId}-help`});
    const results = el("ul", {class: "v2-trade-results", id: `${bodyId}-res`, hidden: true});
    const label = el("label", {class: "v2-find-search-label"}, el("span", {class: "v2-sr", text: "Add players to this team: search by name, or paste a whole team page"}), input);
    const help = el("p", {class: "v2-meta v2-find-paste-help", id: `${bodyId}-help`,
      text: "Type a name to search, or paste a team page: select all and copy on the page (Ctrl+A, Ctrl+C), then paste here. It stays on this device; nothing is sent anywhere."});
    const panel = el("div", {class: "v2-find-paste-result", id: `${bodyId}-panel`, role: "status", "aria-live": "polite"});
    const list = el("ul", {class: "v2-trade-players v2-lg-players", id: `${bodyId}-list`});
    const node = el("div", {class: "v2-lg-team-body", id: bodyId}, el("div", {class: "v2-find-search-wrap"}, label, results), help, panel, list);
    const team = () => teamById(store.get(), teamId);

    function renderList() {
      const t = team();
      if (!t) return;
      const ctx = mathContext();
      list.replaceChildren(...t.entries.map(entry => {
        const remove = button("Remove", {class: "v2-link v2-find-remove", "aria-label": `Remove ${entry.name} from ${t.name}`}, () => {
          update(w => W.ops.addRemoved(W.ops.setEntries(w, teamId, teamById(w, teamId).entries.filter(e => e.key !== entry.key)), teamId, entry.key), "entries");
          announce(`Removed ${entry.name}.`);
        });
        return el("li", {class: "v2-find-row v2-lg-row"}, el("div", {}, el("b", {text: entry.name}), el("span", {class: "v2-meta", text: entry.pos ? ` ${entry.pos}` : ""}), chipsFor(entry, ctx)), remove);
      }));
      if (!t.entries.length) list.append(el("li", {class: "v2-meta v2-lg-empty", text: "No players yet."}));
    }

    const say = (...kids) => panel.replaceChildren(...kids.filter(Boolean));
    const para = (text, cls) => el("p", {class: cls || "v2-meta", text});

    // Add entries (engine rows or kept K/DEF) to this team; returns {added, onOther}.
    function place(rows, replace, extra) {
      const ws = store.get();
      const t = teamById(ws, teamId);
      const keep = replace ? [] : t.entries;
      const have = new Set(keep.map(e => e.key));
      const added = [];
      const onOther = [];
      rows.forEach(({row, slot}) => {
        const key = String(row.player_key);
        const holder = holderOf(ws, key, teamId);
        if (holder) { onOther.push(`${row.name} (${holder.name})`); return; }
        if (have.has(key)) return;
        have.add(key);
        added.push(entryOf(row, slot));
      });
      update(w => W.ops.setEntries(w, teamId, keep.concat(added), extra), "entries");
      return {added, onOther};
    }
    function keepKD(unmatched) {
      const kept = [];
      const ws = store.get();
      const t = teamById(ws, teamId);
      const taken = new Set(ws.teams.flatMap(x => x.entries.map(e => e.key)));
      const add = [];
      (unmatched || []).filter(F.isNotEvaluated).forEach(u => {
        const name = F.page.cleanLine(u.line || u.name);
        const key = `x:${u.pos}:${u.team || F.normName(name)}`;
        if (!name || taken.has(key)) return;
        taken.add(key);
        add.push({key, name, pos: u.pos, team: u.team || undefined});
        kept.push(`${name} (${u.pos})`);
      });
      if (add.length) update(w => W.ops.setEntries(w, teamId, t.entries.concat(add).concat([]), {}), "entries");
      return kept;
    }
    const searchFor = line => { input.value = F.page.cleanLine(line); input.dispatchEvent(new Event("input", {bubbles: true})); input.focus(); };
    const evaluatedOnly = list2 => (list2 || []).filter(u => !F.isNotEvaluated(u));
    const unmatchedBlock = items => (items.length ? [para(`Not matched (${items.length}): add them by search.`, "v2-find-paste-note"),
      el("ul", {class: "v2-find-unmatched"}, ...items.slice(0, 40).map(u => el("li", {}, el("span", {text: F.page.cleanLine(u.line || u.name)}), el("span", {class: "v2-meta", text: u.reason ? ` (${u.reason})` : ""}),
        button("Search to add", {class: "v2-btn v2-find-search-add", "aria-label": `Search to add ${F.page.cleanLine(u.line || u.name)}`}, () => searchFor(u.line || u.name))))) ] : []);
    const unsureBlock = unsure => (unsure.length ? [para(`Check ${plural(unsure.length, "match", "matches")}: not added until you say so.`, "v2-find-paste-note"),
      el("ul", {class: "v2-find-unsure-list"}, ...unsure.map(p => {
        const li = el("li", {class: "v2-find-unsure"});
        const yes = button("Yes, add", {class: "v2-btn v2-find-confirm", "aria-label": `Yes, add ${p.row.name}`}, () => {
          const r = place([{row: p.row, slot: p.slot}], false);
          li.replaceChildren(el("span", {text: r.added.length ? `Added ${p.row.name}.` : `${p.row.name} is already on a roster.`}));
        });
        const no = button("No, search", {class: "v2-btn v2-find-search-add", "aria-label": `No, search for ${F.page.cleanLine(p.sourceLine)}`}, () => { li.remove(); searchFor(p.sourceLine); });
        li.append(el("span", {text: `Pasted “${F.page.cleanLine(p.sourceLine)}”: is this `}), el("b", {text: p.row.name}), el("span", {class: "v2-meta", text: ` ${p.row.pos || ""} ${p.row.team || ""}`.trimEnd()}), el("span", {text: "?"}), yes, no);
        return li;
      }))] : []);

    // players: parser players ({id, confidence, slot, sourceLine}); replace: a whole team page is the whole team.
    function placePlayers(res, players, replace, teamIndex) {
      const ctx = mathContext();
      const sure = [];
      const unsure = [];
      players.forEach(p => {
        const row = ctx.rowsByKey.get(String(p.id));
        if (!row) return;
        if (p.confidence >= 1) sure.push({row, slot: p.slot}); else unsure.push({...p, row});
      });
      const {added, onOther} = place(sure, replace, replace ? {sourceText: res.sourceText, sourceTeam: teamIndex === undefined ? null : teamIndex, removed: []} : undefined);
      const kept = keepKD(res.unmatched);
      return {added, onOther, unsure, kept};
    }
    function report(res, placed, extra) {
      const t = team();
      say(para(`Matched ${res.matched} of ${res.total} players. ${t.name} now has ${plural(t.entries.length, "player")}.${placed.onOther.length ? ` Left out because they are on another team: ${placed.onOther.join(", ")}.` : ""}`, "v2-find-paste-count is-ok"),
        placed.kept.length ? para(`Kept, not evaluated (no value for defenses and kickers): ${placed.kept.join(", ")}.`, "v2-meta v2-find-kept") : null,
        ...unsureBlock(placed.unsure), ...unmatchedBlock(evaluatedOnly(res.unmatched)), ...(extra || []));
    }
    function readMatchup(res) {
      const label = (r, i) => res.teams[i].teamName || `Team ${i + 1} (listed ${i ? "second" : "first"})`;
      const cards = res.teams.map((tm, i) => {
        const use = button(`${label(res, i)} is this team`, {class: "v2-btn v2-find-pick-team"}, () => {
          const placed = placePlayers(res, tm.players, true, i);
          const other = 1 - i;
          const addOther = button(`Add ${label(res, other)} as a new team`, {class: "v2-btn"}, () => {
            addTeamFromPlayers(label(res, other), res, res.teams[other].players, other);
            addOther.disabled = true;
          });
          report(res, placed, [addOther]);
        });
        return el("div", {class: "v2-find-team"}, el("h4", {text: label(res, i)}), el("p", {class: "v2-meta", text: `${tm.matched} of ${tm.total} matched: ${tm.players.map(p => p.name).join(", ") || "none"}.`}), use);
      });
      say(para(`This is a matchup page with two teams. Matched ${res.matched} of ${res.total} players.`, "v2-find-paste-count is-ok"), para("Which team is this?", "v2-find-which"), el("div", {class: "v2-find-teams"}, ...cards));
    }
    function consume(text) {
      input.value = "";
      results.replaceChildren();
      results.hidden = true;
      const C = engine();
      const rows = C ? C.getAllRows() : [];
      const lines = F.parsePasted(text);
      const nameMatch = F.matchNames(lines, rows);
      if (nameMatch.matched.length >= 2 && nameMatch.matched.length >= F.page.NAME_LIST_SHARE * lines.length) {
        const placed = place(nameMatch.matched.map(row => ({row})), false);
        const kept = keepKD(nameMatch.unmatched);
        const rest = evaluatedOnly(nameMatch.unmatched);
        say(para(`Added ${plural(placed.added.length, "player")} from the list.${kept.length ? ` Kept, not evaluated: ${kept.join(", ")}.` : ""}${placed.onOther.length ? ` Left out because they are on another team: ${placed.onOther.join(", ")}.` : ""}`),
          ...unmatchedBlock(rest));
        return;
      }
      const lg = root.DDFRosterPaste && root.DDFRosterPaste.parseLeague && C ? root.DDFRosterPaste.parseLeague(text, rows) : null;
      if (lg && lg.teams.length >= 3) {
        say(para(`This is a whole league: ${plural(lg.teams.length, "team")}. Nothing was added to this team.`, "v2-find-paste-count is-ok"),
          button(`Set up all ${plural(lg.teams.length, "team")}`, {class: "v2-btn"}, () => { say(); pasteWholeLeague(text); const d = $("v2LgImport"); if (d) { d.open = true; d.scrollIntoView({block: "nearest"}); } }));
        return;
      }
      const res = F.page.parsePage(text);
      if (!res) { say(para("Values are still loading. Try again in a moment.")); return; }
      res.sourceText = text;
      if (res.mode === "matchup" && res.teams && res.teams.length === 2) { readMatchup(res); return; }
      if (!res.matched) {
        say(para("No players recognised in that text. Nothing was added.", "v2-find-paste-count is-bad"), para("Paste a team page from any fantasy site (Ctrl+A, Ctrl+C on the page), or a list of player names. Search and add players by name below."));
        return;
      }
      if (res.mode !== "extract" && (res.matched < F.page.MIN_MATCHED || res.matched / res.total < F.page.MIN_SHARE)) {
        const anyway = button(`Add these ${res.matched} anyway`, {class: "v2-btn"}, () => report(res, placePlayers(res, res.players, true)));
        say(para(`Matched ${res.matched} of ${res.total} players.`, "v2-find-paste-count is-bad"), para("That is too few to trust, so nothing was added. Paste the whole team page, or search and add players by name below."), anyway,
          ...unmatchedBlock(evaluatedOnly(res.unmatched)));
        return;
      }
      report(res, placePlayers(res, res.players, true));
    }
    input.addEventListener("paste", event => {
      const text = event.clipboardData ? event.clipboardData.getData("text") : "";
      if (text && F.looksLikePage(text)) { event.preventDefault(); consume(text); }
    });
    input.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) event.preventDefault(); });
    if (root.TradeValueNameSearch) root.TradeValueNameSearch.combobox(input, results);
    input.addEventListener("input", () => {
      if (F.looksLikePage(input.value)) { consume(input.value); return; }
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = !q;
      const C = engine();
      if (!q || !C || !root.TradeValueNameSearch) return;
      const ws = store.get();
      const hits = root.TradeValueNameSearch.search(C.getAllRows().concat(F.page.notEvaluatedChoices()), q).slice(0, 8);
      if (!hits.length) results.append(el("li", {class: "is-empty v2-meta", text: `Can't find “${q}”. Check the spelling, or he may not have a value yet.`}));
      hits.forEach(row => {
        const key = String(row.player_key);
        const holder = ws.teams.find(t => t.entries.some(e => e.key === key
          || (row.notEvaluated && e.pos === row.pos && (row.pos === "DEF" ? F.page.teamCode(e.team) === row.team : F.normName(e.name) === F.normName(row.name)))));
        const b = el("button", {type: "button"}, `${`${row.name} · ${row.pos || ""} ${row.team || ""}`.trim()}${holder ? ` ✓ On ${holder.name}` : ""}`,
          row.notEvaluated ? el("span", {class: "v2-find-noteval", text: "Not evaluated"}) : null);
        if (holder) b.disabled = true;
        b.addEventListener("click", () => {
          const t = team();
          update(w => W.ops.setEntries(w, teamId, t.entries.concat([row.notEvaluated ? {key, name: row.name, pos: row.pos, team: row.team} : entryOf(row)])), "entries");
          input.value = "";
          results.replaceChildren();
          results.hidden = true;
          input.focus();
        });
        results.append(el("li", {}, b));
      });
    });
    return {node, renderList, input, say};
  }

  function addTeamFromPlayers(name, res, players, teamIndex) {
    const ctx = mathContext();
    const ws = store.get();
    const rows = [];
    players.forEach(p => { const row = ctx.rowsByKey.get(String(p.id)); if (row && p.confidence >= 1 && !holderOf(ws, String(row.player_key), null)) rows.push(entryOf(row, p.slot)); });
    update(w => W.ops.addTeam(w, name, {entries: rows}), "add");
    const added = store.get().teams[store.get().teams.length - 1];
    update(w => W.ops.setEntries(w, added.id, rows, {sourceText: res.sourceText, sourceTeam: teamIndex}), "entries");
    UI.justAdded = added.id;
    announce(`Team added: ${added.name}.`);
  }

  // Table 3.2: with three or more teams all fold except the one edited last; with fewer, a team folds once it has players.
  function defaultCollapsed(team, ws) {
    if (ws.teams.length >= 3) {
      const newest = ws.teams.reduce((a, b) => (b.updatedAt > a.updatedAt ? b : a), ws.teams[0]);
      return team.id !== newest.id;
    }
    return team.entries.length > 0;
  }

  function createTeam(team, ws) {
    const bodyId = `v2LgBody-${team.id}`;
    const body = teamBody(team.id, bodyId);
    const li = el("li", {class: "v2-lg-team", "data-team-id": team.id});
    const star = button("", {class: "v2-lg-star", "aria-pressed": "false"});
    const nameSlot = el("span", {class: "v2-lg-nameslot"});
    const nameBtn = button("", {class: "v2-lg-name", title: "Rename"}, () => comp.startRename());
    const meta = el("span", {class: "v2-meta v2-lg-count"});
    const toggle = button("", {class: "v2-mod-btn v2-lg-toggle", "aria-controls": bodyId, "aria-expanded": "true"});
    const up = button("Up", {class: "v2-btn v2-lg-up"});
    const down = button("Down", {class: "v2-btn v2-lg-down"});
    const rename = button("Rename", {class: "v2-btn v2-lg-rename"});
    const clear = button("Clear", {class: "v2-btn v2-lg-clear"});
    const remove = button("Remove", {class: "v2-btn v2-lg-remove"});
    const confirmBox = el("div", {class: "v2-lg-confirm", role: "group", hidden: true});
    const head = el("div", {class: "v2-lg-team-head"}, star, nameSlot, meta, el("div", {class: "v2-lg-actions"}, up, down, rename, clear, remove), toggle);
    li.append(head, confirmBox, body.node);
    const comp = {li, body, id: team.id, collapsed: UI.justAdded === team.id ? false : defaultCollapsed(team, ws), lastEntries: null};
    UI.justAdded = UI.justAdded === team.id ? null : UI.justAdded;
    const current = () => teamById(store.get(), team.id);

    star.addEventListener("click", () => { const t = current(); update(w => W.ops.setMyTeam(w, w.myTeamId === t.id ? null : t.id), "mine"); announce(store.get().myTeamId === t.id ? `${t.name} is now your team.` : "No team is marked as yours."); });
    toggle.addEventListener("click", () => { comp.collapsed = !comp.collapsed; comp.update(); });
    li.addEventListener("keydown", event => { if (event.key === "Escape" && !comp.collapsed && event.target.closest(".v2-lg-team-body") && !event.target.closest(".v2-find-search-wrap [aria-expanded='true']")) { comp.collapsed = true; comp.update(); toggle.focus(); } });
    up.addEventListener("click", () => { update(w => W.ops.moveTeam(w, team.id, -1), "order"); (up.disabled ? down : up).focus(); });
    down.addEventListener("click", () => { update(w => W.ops.moveTeam(w, team.id, 1), "order"); (down.disabled ? up : down).focus(); });
    rename.addEventListener("click", () => startRename());
    clear.addEventListener("click", () => {
      const t = current();
      UI.undo = {label: `Cleared ${t.name}`, ws: store.get()};
      update(w => W.ops.clearTeam(w, team.id), "entries");
      body.say();
      announce(`Cleared ${t.name}.`);
      renderUndo();
    });
    remove.addEventListener("click", () => {
      const t = current();
      confirmBox.hidden = false;
      const yes = button("Remove", {class: "v2-btn v2-lg-remove-yes"}, () => {
        UI.undo = {label: `Removed ${t.name}`, ws: store.get()};
        update(w => W.ops.removeTeam(w, team.id), "remove");
        announce(`Team removed: ${t.name}.`);
        renderUndo();
        const first = document.querySelector("#v2LgTeams .v2-lg-name, #v2LgAdd");
        if (first) first.focus();
      });
      const no = button("Cancel", {class: "v2-btn v2-lg-remove-no"}, () => { confirmBox.hidden = true; remove.focus(); });
      confirmBox.replaceChildren(el("span", {text: `Remove ${t.name} and its ${plural(t.entries.length, "player")}? `}), yes, no);
      no.focus();
    });
    function startRename() {
      const t = current();
      const input = el("input", {type: "text", class: "v2-lg-name-input", value: t.name, maxlength: String(W.MAX_NAME), "aria-label": `Team name (${W.MAX_NAME} characters at most)`});
      let done = false;
      const finish = save => {
        if (done) return;
        done = true;
        nameSlot.replaceChildren();
        if (save) { update(w => W.ops.renameTeam(w, team.id, input.value), "rename"); announce(`Renamed to ${current().name}.`); }
        comp.update();
        const b = nameSlot.querySelector(".v2-lg-name");
        if (b) b.focus();
      };
      input.addEventListener("keydown", event => { if (event.key === "Enter") { event.preventDefault(); finish(true); } else if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); finish(false); } });
      input.addEventListener("blur", () => finish(true));
      nameSlot.replaceChildren(input);
      input.focus();
      input.select();
    }
    comp.startRename = startRename;
    comp.update = () => {
      const t = current();
      if (!t) return;
      const ws2 = store.get();
      const i = ws2.teams.findIndex(x => x.id === t.id);
      const mine = ws2.myTeamId === t.id;
      li.dataset.mine = String(mine);
      star.textContent = mine ? "★" : "☆";
      star.setAttribute("aria-pressed", String(mine));
      star.setAttribute("aria-label", mine ? `${t.name} is my team (press to unmark)` : `Set ${t.name} as my team`);
      nameBtn.textContent = t.name;
      nameBtn.setAttribute("aria-label", `${t.name}, rename`);
      if (!nameSlot.querySelector("input") && !nameSlot.contains(nameBtn)) nameSlot.replaceChildren(nameBtn);
      meta.textContent = `(${rosterNote(t)})`;
      up.disabled = i === 0;
      down.disabled = i === ws2.teams.length - 1;
      up.setAttribute("aria-label", `Move ${t.name} up`);
      down.setAttribute("aria-label", `Move ${t.name} down`);
      rename.setAttribute("aria-label", `Rename ${t.name}`);
      clear.setAttribute("aria-label", `Clear ${t.name}`);
      clear.disabled = !t.entries.length;
      remove.setAttribute("aria-label", `Remove ${t.name}`);
      toggle.setAttribute("aria-expanded", String(!comp.collapsed));
      toggle.setAttribute("aria-label", `${comp.collapsed ? "Expand" : "Collapse"} ${t.name}`);
      toggle.textContent = comp.collapsed ? "▸" : "▾";
      body.node.hidden = comp.collapsed;
      const sig = JSON.stringify(t.entries.map(e => e.key));
      if (sig !== comp.lastEntries) { comp.lastEntries = sig; body.renderList(); }
    };
    return comp;
  }

  function renderTeams() {
    const ws = store.get();
    const ul = $("v2LgTeams");
    if (!ul) return;
    UI.comps.forEach((comp, id) => { if (!ws.teams.some(t => t.id === id)) { comp.li.remove(); UI.comps.delete(id); } });
    ws.teams.forEach((team, i) => {
      let comp = UI.comps.get(team.id);
      if (!comp) { comp = createTeam(team, ws); UI.comps.set(team.id, comp); }
      comp.update();
      if (ul.children[i] !== comp.li) ul.insertBefore(comp.li, ul.children[i] || null);
    });
    $("v2LgEmpty").hidden = ws.teams.length > 0;
    $("v2LgCount").textContent = `Teams (${ws.teams.length})`;
    const total = ws.teams.reduce((n, t) => n + t.entries.length, 0);
    $("v2LgFootnote").hidden = !ws.teams.some(t => t.entries.some(isK));
    $("v2LgAdd").disabled = ws.teams.length >= W.MAX_TEAMS;
    $("v2LgAdd").setAttribute("aria-label", ws.teams.length >= W.MAX_TEAMS ? `Add team (the limit is ${W.MAX_TEAMS})` : "Add team");
    ["v2LgDownload", "v2LgCopyText", "v2LgCopyLink"].forEach(id => { $(id).disabled = !total && !ws.teams.length; });
    $("v2LgClearAll").hidden = !ws.teams.length;
    if (!ws.teams.length) $("v2LgClearConfirm").hidden = true;
    const editorSummary = $("v2LgEditorSummary");
    const marked = ws.teams.find(t => t.id === ws.myTeamId);
    if (editorSummary) editorSummary.textContent = `${plural(ws.teams.length, "team")}${marked ? ` · Your team: ${marked.name}` : ws.teams.length ? " · Expand to mark your team" : " · Paste your league's rosters or add teams"}`;
    renderCountMismatch();
  }

  function renderUndo() {
    const b = $("v2LgUndo");
    if (!b) return;
    b.hidden = !UI.undo;
    if (UI.undo) b.textContent = `Undo: ${UI.undo.label}`;
  }

  const SAVE_TEXT = {idle: "", saving: "Saving…", saved: "Saved", unavailable: "Private browsing: your teams won't be saved on this device between visits.",
    full: "This device's storage is full. Download your league to keep a copy, then clear old data."};
  function renderStatus() {
    const n = $("v2LgSaved");
    if (!n) return;
    const status = store.status();
    n.textContent = SAVE_TEXT[status] || "";
    n.dataset.state = status;
  }

  // ---------- Download, Load, Copy ----------
  function slug(name) { return String(name || "league").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "league"; }
  function download() {
    const ws = store.get();
    const blob = new Blob([W.exportJson({...ws, settings: settingsSnapshot()})], {type: "application/json"});
    const a = el("a", {href: URL.createObjectURL(blob), download: `${slug(ws.name)}.json`});
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    notice(`Downloaded ${slug(ws.name)}.json.`);
  }
  async function copy(text, done) {
    try { await navigator.clipboard.writeText(text); notice(done); }
    catch (error) {
      const ta = el("textarea", {class: "v2-sr", "aria-hidden": "true"});
      ta.value = text;
      document.body.append(ta);
      ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
      ta.remove();
      notice(ok ? done : "Could not copy. Use Download instead.");
    }
  }
  function applyImported(workspace, source) {
    UI.undo = {label: "Loaded a league", ws: {...store.get(), settings: settingsSnapshot()},
      valueContext: root.DDFOverrides && root.DDFOverrides.snapshotContext ? root.DDFOverrides.snapshotContext() : null};
    UI.comps.forEach(c => c.li.remove());
    UI.comps.clear();
    UI.cache = O.createCache();
    if (workspace.settings && workspace.settings.query && root.TradeValueV2 && root.TradeValueV2.applyLinkLeague) {
      root.TradeValueV2.applyLinkLeague(new URLSearchParams(workspace.settings.query));
      if (root.DDFOverrides && root.DDFOverrides.applyLink) root.DDFOverrides.applyLink(new URLSearchParams(workspace.settings.query));
    }
    store.replace(workspace, "replace");
    renderUndo();
    notice(`${source} ${plural(workspace.teams.length, "team")} loaded.`);
    announce(`${plural(workspace.teams.length, "team")} loaded.`);
  }
  function offerReplace(workspace, source) {
    const ws = store.get();
    const box = $("v2LgLoadConfirm");
    if (!ws.teams.length) { applyImported(workspace, source); return; }
    $("v2LgCard").open = true;
    box.hidden = false;
    const yes = button("Replace my league", {class: "v2-btn", id: "v2LgLoadYes"}, () => { box.hidden = true; applyImported(workspace, source); });
    const no = button("Keep my league", {class: "v2-btn"}, () => { box.hidden = true; });
    box.replaceChildren(el("span", {text: `Replace your saved league (${plural(ws.teams.length, "team")}) with “${workspace.name}” (${plural(workspace.teams.length, "team")})? `}), yes, no);
    yes.focus();
  }
  async function loadFile(file) {
    if (!file) return;
    const text = await file.text();
    const res = W.importJson(text);
    if (res.error) { notice(res.error); return; }
    offerReplace(res.workspace, `${res.workspace.name}:`);
  }
  // JEG-1095: what a whole-league paste (or ID load) understood, kept on screen outside the folded import box until the
  // next paste or Close: how many teams, each team's name and roster size, which team is marked as yours, the players that
  // did not match with the line they came from, and a plain error when nothing could be read.
  // info: {error} or {teams: [{name, count, unmatched: [text], unsure, leftOut}], skipped, source}
  function showParsed(info) {
    const box = $("v2LgParsed");
    if (!box) return;
    box.hidden = false;
    box.dataset.state = info.error ? "error" : "ok";
    UI.parsed = info;
    UI.parsedMine = store.get().myTeamId;
    const close = button("Close", {class: "v2-btn", id: "v2LgParsedClose"}, () => { box.hidden = true; box.replaceChildren(); UI.parsed = null; });
    if (info.error) {
      box.replaceChildren(el("h3", {text: "Nothing was read from that paste"}), el("p", {id: "v2LgParsedError", text: info.error}), close);
      return;
    }
    const ws = store.get();
    const mine = teamById(ws, ws.myTeamId);
    const kept = info.teams.filter(t => !t.leftOut);
    const lines = kept.map(t => {
      const isMine = Boolean(mine) && W.cleanName(t.name, "").toLowerCase() === W.cleanName(mine.name, "").toLowerCase();
      const li = el("li", {"data-team": t.name, "data-count": String(t.count), class: isMine ? "is-mine" : ""},
        el("b", {text: t.name}), ` · ${plural(t.count, "player")}${isMine ? " · your team" : ""}${t.unsure ? ` · ${t.unsure} to check` : ""}`);
      if (t.unmatched.length) {
        li.append(el("div", {class: "v2-meta"}, `${plural(t.unmatched.length, "line")} not matched to a player:`),
          el("ul", {class: "v2-lg-parsed-miss"}, ...t.unmatched.map(text => el("li", {text}))));
      }
      return li;
    });
    const unmatchedTotal = kept.reduce((n, t) => n + t.unmatched.length, 0);
    const yours = mine ? `Your team is ${mine.name}.` : "No team is marked as yours yet. Press the star beside your team's name so results are for your team.";
    const head = `${info.source || "Read"} ${plural(kept.length, "team")} from your paste.`;
    box.replaceChildren(el("h3", {text: head}),
      el("p", {id: "v2LgParsedMine", text: yours}),
      info.skipped ? el("p", {class: "v2-meta", text: `${plural(info.skipped, "team")} left out: the limit is ${W.MAX_TEAMS} teams.`}) : null,
      el("ul", {class: "v2-lg-parsed-teams", id: "v2LgParsedTeams"}, ...lines),
      el("p", {class: "v2-meta", id: "v2LgParsedMiss", text: unmatchedTotal
        ? `${plural(unmatchedTotal, "line")} could not be matched to a player. Add those players by searching inside the team.`
        : "Every player line was matched."}),
      close);
  }
  // A whole league pasted from its rosters page (ESPN League > Rosters, Yahoo, Sleeper, any site that lists every team):
  // one team per roster. A team already here with the same name gets the pasted roster; the rest are added.
  function leagueEntries(t, ctx, taken) {
    const list = [];
    let unsure = 0;
    t.players.forEach(p => {
      const row = ctx.rowsByKey.get(String(p.id));
      if (!row) return;
      if (p.confidence < 1) { unsure += 1; return; }
      const key = String(row.player_key);
      if (taken.has(key)) return;
      taken.add(key);
      list.push(entryOf(row, p.slot));
    });
    (t.unmatched || []).filter(F.isNotEvaluated).forEach(u => {
      const name = F.page.cleanLine(u.line || u.name);
      const key = `x:${u.pos}:${u.team || F.normName(name)}`;
      if (!name || taken.has(key)) return;
      taken.add(key);
      list.push({key, name, pos: u.pos, team: u.team || undefined});
    });
    const missed = (t.unmatched || []).filter(u => !F.isNotEvaluated(u)).map(u => F.page.cleanLine(u.line || u.name)).filter(Boolean);
    return {list, unsure, missed};
  }
  function pasteWholeLeague(text) {
    const status = $("v2LgLeagueStatus");
    const box = $("v2LgLeaguePaste");
    if (box) box.value = "";
    const C = engine();
    const P = root.DDFRosterPaste;
    if (!C || !P || !P.parseLeague || !mathContext()) { status.textContent = "Values are still loading. Try again in a moment."; showParsed({error: status.textContent}); return; }
    const res = P.parseLeague(String(text || ""), C.getAllRows());
    if (!res.teams.length) {
      const id = res.sleeperLeagueId || res.espnLeagueId;   // a pasted league link has no rosters in it (JEG-1131: no platform fetch)
      status.textContent = res.site === "sleeper"
        ? (id ? "A league link has no rosters in it. " : "") + "Sleeper shows one roster per page: open each team and copy its page, then paste it with Add team. Each paste adds a team, and the count above goes up."
        : (id ? "A league link has no rosters in it. " : "No teams found in that text. ") + "Open your league's rosters page (ESPN: League, then Rosters), press Ctrl+A then Ctrl+C, and paste it here.";
      showParsed({error: status.textContent});
      announce(status.textContent);
      return;
    }
    const ctx = mathContext();
    const ws0 = store.get();
    // Names are compared as saved (the workspace trims a name to W.MAX_NAME), so a long name matches on a second paste.
    const nameKey = name => W.cleanName(name, "").toLowerCase();
    const byName = new Map(ws0.teams.map(t => [nameKey(t.name), t.id]));
    const replacing = new Set();
    res.teams.forEach(t => { const id = byName.get(nameKey(t.teamName)); if (id) replacing.add(id); });
    // Players on a team this paste does not cover stay there.
    const taken = new Set(ws0.teams.filter(t => !replacing.has(t.id)).flatMap(t => t.entries.map(e => e.key)));
    const room = W.MAX_TEAMS - ws0.teams.length;
    let added = 0;
    let updated = 0;
    let skipped = 0;
    const lines = [];
    const parsed = [];
    const plan = res.teams.map(t => ({t, id: byName.get(nameKey(t.teamName)), ...leagueEntries(t, ctx, taken)}));
    update(w => {
      let next = w;
      plan.forEach(item => {
        if (item.id) { next = W.ops.setEntries(next, item.id, item.list, {sourceText: "", sourceTeam: null, removed: []}); updated += 1; }
        else if (added < room) { next = W.ops.addTeam(next, item.t.teamName, {entries: item.list}); added += 1; }
        else { skipped += 1; parsed.push({name: item.t.teamName, count: 0, unmatched: [], unsure: 0, leftOut: true}); return; }
        parsed.push({name: item.t.teamName, count: item.list.length, unmatched: item.missed, unsure: item.unsure});
        const notes = [];
        if (item.unsure) notes.push(`${item.unsure} to check`);
        if (item.missed.length) notes.push(`not matched: ${item.missed.slice(0, 6).join(", ")}${item.missed.length > 6 ? "…" : ""}`);
        lines.push(`${item.t.teamName}: ${plural(item.list.length, "player")}${notes.length ? ` (${notes.join("; ")})` : ""}`);
      });
      return next;
    }, "add");
    const parts = [];
    if (added) parts.push(`added ${plural(added, "team")}`);
    if (updated) parts.push(`updated ${plural(updated, "team")} with the same name`);
    let msg = `Found ${plural(res.teams.length, "team")}: ${parts.join(" and ")}.`;
    if (skipped) msg += ` ${plural(skipped, "team")} left out: the limit is ${W.MAX_TEAMS}.`;
    if (!ws0.myTeamId) msg += " Press the star on your team to mark it as yours.";
    status.replaceChildren(el("span", {text: msg}), el("ul", {class: "v2-lg-paste-teams"}, ...lines.map(line => el("li", {text: line}))));
    if (lines.some(l => /not matched|to check/.test(l))) status.append(el("span", {text: "Add any missing players by searching inside that team."}));
    showParsed({teams: parsed, skipped, source: "Read"});
    // Healthy rosters (including their K/DST entries) fold away after paste; unresolved players remain visible.
    const pasted = new Map(parsed.filter(t => !t.leftOut).map(t => [nameKey(t.name), t]));
    let hasIssues = skipped > 0;
    UI.comps.forEach(comp => {
      const team = teamById(store.get(), comp.id);
      const info = team && pasted.get(nameKey(team.name));
      if (!info) return;
      const issue = info.unsure > 0 || info.unmatched.length > 0;
      hasIssues = hasIssues || issue;
      comp.collapsed = !issue;
      comp.update();
    });
    $("v2LgImport").open = false;
    $("v2LgCard").open = hasIssues;
    announce(msg);
  }

  // ---------- sort controls shared by both tables ----------
  // One th per sortable column: a real button inside it (one tab stop), aria-sort on the th (valid ARIA; the button names the sort).
  function sortTh(id, columns, state, onSort, attrs, label) {
    const column = columns.find(c => c.id === id);
    const on = state.col === id;
    const th = el("th", {scope: "col", "aria-sort": S.ariaSort(state, id), "data-col": id, ...(attrs || {})});
    const arrow = el("span", {class: "v2-lg-arrow", "aria-hidden": "true", text: on ? (state.dir === "asc" ? "▲" : "▼") : "↕"});
    const btn = button(label || column.label, {class: `v2-lg-sort${on ? " is-active" : ""}`, "data-sort": id, title: `Sort by ${column.label.toLowerCase()}`}, () => onSort(S.nextState(state, id, columns)));
    btn.append(" ", arrow);
    th.append(btn);
    return th;
  }
  const plainTh = (text, attrs) => el("th", {scope: "col", ...(attrs || {})}, text);
  function phoneSort(prefix, columns, state, onSort, extra) {
    const sel = el("select", {id: `${prefix}SortBy`, "aria-label": "Sort cards by"}, ...columns.map(c => el("option", {value: c.id, text: c.label})));
    sel.value = state.col;
    sel.addEventListener("change", () => onSort(S.nextState({col: null}, sel.value, columns)));
    const column = columns.find(c => c.id === state.col);
    const dir = button(state.dir === "asc" ? "Ascending" : "Descending", {class: "v2-btn", id: `${prefix}SortDir`, "aria-label": `Sort direction: ${state.dir === "asc" ? "ascending" : "descending"}. Press to reverse.`},
      () => onSort({col: state.col, dir: state.dir === "asc" ? "desc" : "asc"}));
    void column;
    return el("div", {class: "v2-lg-phonesort"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Sort by:"}), sel), dir, extra || null);
  }
  const savedSort = (ws, key, columns, fallback) => (S.validState(ws.ui.sort[key], columns) ? ws.ui.sort[key] : fallback);
  function setSort(key, state, columns) {
    update(w => W.ops.setUi(w, {sort: {[key]: state}}), `ui:sort-${key}`);
    const column = columns.find(c => c.id === state.col);
    if (column) announce(S.announce(column, state.dir));
  }

  // A table is drawn again whenever it sorts or filters, which removes the control the reader just used. The same control (by id, sort
  // button or Details button) gets the focus back, so a keyboard reader can press it again.
  function keepFocus(box, draw) {
    const a = document.activeElement;
    let selector = null;
    if (a && box && box.contains(a)) {
      if (a.id) selector = `#${a.id}`;
      else if (a.dataset && a.dataset.sort) selector = `#${a.closest("table").id} thead button[data-sort="${a.dataset.sort}"]`;
      else if (a.dataset && a.dataset.detailsFor) selector = `[data-details-for="${a.dataset.detailsFor}"]`;
    }
    draw();
    const again = selector && document.querySelector(selector);
    if (again && again !== document.activeElement) again.focus({preventScroll: true});
  }
  const renderSummary = () => keepFocus($("v2LgSummaryBody"), renderSummaryNow);
  const renderOpps = () => keepFocus($("v2LgOppsBody"), renderOppsNow);

  // ---------- team summary ----------
  function summaryData() {
    const ws = store.get();
    const ctx = mathContext();
    if (!ctx) return null;
    const basis = ws.ui.rankBasis === "market" && ctx.market ? "market" : "fund";
    const teams = ws.teams.map(t => ({id: t.id, name: t.name, isMine: ws.myTeamId === t.id, entries: t.entries}));
    const summary = T.summarize(teams, {rowsByKey: ctx.rowsByKey, shape: ctx.shape, expected: ctx.expected, chartKeys: ctx.market}, {basis});
    return {ws, ctx, basis, summary};
  }
  function gapList(items, kind, id) {
    if (!items.length) return "—";
    const fmtGap = i => `${i.name} ${signed(i.gap)}`;
    const wrap = el("span", {class: "v2-lg-gaps", "data-gap": kind});
    wrap.append(items.slice(0, 3).map(fmtGap).join(", "));
    if (items.length > 3) {
      wrap.append(" ", el("details", {class: "v2-lg-more"}, el("summary", {text: `+${items.length - 3} more`, "aria-label": `Show ${items.length - 3} more players to ${kind}`}), el("span", {text: items.slice(3).map(fmtGap).join(", ")})));
    }
    void id;
    return wrap;
  }
  // JEG-1081: the players where the projections and the trade charts disagree, by more than 2.0 points, in plain words.
  function disagreeList(t) {
    const items = t.higher.map(i => ({...i, word: "Projections higher"})).concat(t.lower.map(i => ({...i, word: "Projections lower"})))
      .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap) || a.name.localeCompare(b.name));
    if (!items.length) return "—";
    const wrap = el("span", {class: "v2-lg-gaps", "data-gap": "disagree"});
    const one = i => `${i.name} ${signed(i.gap)} (${i.word.toLowerCase()})`;
    wrap.append(items.slice(0, 3).map(one).join(", "));
    if (items.length > 3) wrap.append(" ", el("details", {class: "v2-lg-more"}, el("summary", {text: `+${items.length - 3} more`, "aria-label": `Show ${items.length - 3} more players where projections and charts disagree`}), el("span", {text: items.slice(3).map(one).join(", ")})));
    return wrap;
  }
  const rankText = (r, ranked) => (r === null || r === undefined ? "—" : ranked < 2 ? "—" : String(r));
  function renderSummaryNow() {
    const card = $("v2LgSummary");
    if (!card) return;
    const data = summaryData();
    const body = $("v2LgSummaryBody");
    const ws = store.get();
    const has = ws.teams.some(t => t.entries.length);
    card.hidden = !has;
    if (!data || !has) { body.replaceChildren(); return; }
    const {basis, summary, ctx} = data;
    const cols = T.summaryColumns(basis);
    const state = savedSort(ws, "summary", cols, T.SUMMARY_DEFAULT);
    const rows = S.sortRows(summary.teams, cols, state, T.SUMMARY_TIES);
    const onSort = next => setSort("summary", next, cols);
    const ranked = summary.league.rankedCount;
    const marketOn = Boolean(ctx.market);
    const head = el("p", {class: "v2-find-headline", id: "v2LgSummaryHeadline", role: "status", "data-ranked": String(ranked)}, T.headline(summary) || "Add a roster to see how the teams compare.");
    const basisSel = el("select", {id: "v2LgBasis"}, el("option", {value: "fund", text: "DDF Value"}), el("option", {value: "market", text: "Trade chart average"}));
    basisSel.value = basis;
    if (!marketOn) basisSel.querySelector("option[value=market]").disabled = true;
    basisSel.addEventListener("change", () => { update(w => W.ops.setUi(w, {rankBasis: basisSel.value}), "ui:basis"); announce(`Ranking by ${basisSel.value === "market" ? "the Trade chart average" : "DDF Value"}.`); });
    const reset = button("Reset sort", {class: "v2-btn", id: "v2LgSummaryReset", hidden: S.sameState(state, T.SUMMARY_DEFAULT)}, () => onSort(T.SUMMARY_DEFAULT));
    const tools = el("div", {class: "v2-ctoolbar"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Rank by:"}), basisSel), reset);
    const alt = basis === "market" ? "fund" : "market";
    const ids = ["rank", "team", "rosterF", "starterF", "benchF", "rosterM", "starterM", "benchM", "altRank", "projRank", "disagree", "under", "over"];
    const thead = el("thead", {}, el("tr", {}, ...ids.map(id => sortTh(id, cols, state, onSort))));
    const num = (v, extra) => el("td", {class: "num", ...(extra || {})}, v === null || v === undefined ? "—" : money(v));
    const tbodies = rows.map(t => {
      const none = !t.hasRoster;
      const mark = t.isMine ? "★ " : "";
      const rk = rankText(t.rank[basis], ranked);
      const altr = t.rank[alt];
      const altText = rankText(altr, ranked);
      const same = t.rank[basis] !== null && altr === t.rank[basis] && ranked >= 2;
      const main = el("tr", {class: "v2-lg-main", "data-team-id": t.id, "data-mine": String(t.isMine)},
        el("td", {class: "num", "data-cell": "rank"}, rk),
        el("th", {scope: "row"}, mark, t.name, t.partial ? el("span", {class: "v2-meta", text: " (partial)"}) : null, none ? el("span", {class: "v2-meta", text: " No roster entered"}) : null),
        num(t.fund && t.fund.rosterValue, {"data-cell": "rosterF"}), num(t.fund && t.fund.starterValue, {"data-cell": "starterF"}), num(t.fund && t.fund.benchValue, {"data-cell": "benchF"}),
        num(t.market && t.market.rosterValue, {"data-cell": "rosterM"}), num(t.market && t.market.starterValue, {"data-cell": "starterM"}), num(t.market && t.market.benchValue, {"data-cell": "benchM"}),
        el("td", {class: "num", "data-cell": "altRank"}, same ? "=" : altText),
        el("td", {class: "num", "data-cell": "projRank"}, rankText(t.rank.proj, ranked)),
        el("td", {"data-cell": "disagree"}, none ? "—" : disagreeList(t)),
        el("td", {"data-cell": "under"}, none ? "—" : gapList(t.under, "buy", t.id)), el("td", {"data-cell": "over"}, none ? "—" : gapList(t.over, "sell", t.id)));
      const detail = el("tr", {class: "v2-lg-detail", "data-team-id": t.id},
        el("td", {colspan: String(ids.length)}, none ? "" : detailText(t, summary, basis)));
      return el("tbody", {}, main, detail);
    });
    const table = el("table", {class: "v2-find-lineup v2-lg-table", id: "v2LgSummaryTable"},
      el("caption", {text: `Team summary: roster, starter and bench value in DDF Value and the Trade chart average, ranked by ${basis === "market" ? "Trade chart average" : "DDF Value"} roster value, with the projections rank beside them`}), thead, ...tbodies);
    const cards = el("ul", {class: "v2-lg-cards", id: "v2LgSummaryCards"}, ...rows.map(t => el("li", {class: "v2-lg-card", "data-team-id": t.id, "data-mine": String(t.isMine)},
      el("h4", {}, `${rankText(t.rank[basis], ranked) === "—" ? "" : `#${t.rank[basis]} `}${t.isMine ? "★ " : ""}${t.name}`, t.partial ? " (partial)" : ""),
      t.hasRoster ? el("div", {}, el("p", {}, `DDF Value: ${money(t.fund.rosterValue)} (start ${money(t.fund.starterValue)}, bench ${money(t.fund.benchValue)})`),
        t.market ? el("p", {}, `Trade chart average: ${money(t.market.rosterValue)} (start ${money(t.market.starterValue)}, bench ${money(t.market.benchValue)})`) : null,
        t.rank[alt] ? el("p", {}, `${alt === "market" ? "Trade chart average" : "DDF Value"} rank: ${t.rank[alt]}`) : null,
        t.rank.proj ? el("p", {}, `DDF Value (projections) rank: ${t.rank.proj}`) : null,
        el("p", {}, "Projections vs charts: ", disagreeList(t)),
        el("p", {}, detailText(t, summary, basis)),
        el("p", {}, "Buy: ", gapList(t.under, "buy")), el("p", {}, "Sell: ", gapList(t.over, "sell"))) : el("p", {class: "v2-meta", text: "No roster entered"}))));
    const note = el("p", {class: "v2-meta v2-footnote", text: "K and DEF are on rosters but not evaluated. Buy and Sell: DDF Value minus the Trade chart average. Projections vs charts: DDF Value (projections) minus DDF Value on the default basis, labelled projections higher or lower. Both are listed when the gap is more than 2.0 points."});
    body.replaceChildren(head, tools, el("div", {class: "v2-lg-phonetools"}, phoneSort("v2LgSummary", cols, state, onSort)), el("div", {class: "v2-find-table-wrap v2-lg-tablewrap"}, table), cards, note);
    const live = $("v2LgSummaryCount");
    if (live) live.textContent = `${plural(summary.teams.length, "team")}`;
  }
  function detailText(t, summary, basis) {
    const strong = t.strengths.length ? t.strengths.map(i => i.text).join("; ") : "none";
    const weak = t.weaknesses.map(i => i.text).concat(t.thinBench ? [t.thinBench.text] : []);
    const single = summary.league.rankedCount < 2;
    void basis;
    return `Strengths: ${strong}. Weaknesses: ${weak.length ? weak.join("; ") : "none"}.${single ? " (Depth only: add a second team to compare against a league median.)" : ""}`;
  }

  // ---------- trade opportunities ----------
  const OPP_COLSPAN = 10;   // nine columns (JEG-1081 adds Projections agree); Market perception has two sub-columns (the chart edge and the charts that call it fair)
  const tradeNodes = (r, ctx) => {
    // JEG-1059: the badge that marks a value the reader set, right after the player's name.
    const badgeOf = p => (root.DDFOverrides && root.DDFOverrides.flag ? root.DDFOverrides.flag(p) : null);
    const side = (list, core) => list.flatMap((p, i) => [i ? " + " : "", p === core ? el("b", {text: p.name}) : p.name, badgeOf(p)]);
    void ctx;
    return ["Send ", ...side(r.give, null), ", get ", ...side(r.receive, r.core)];
  };
  // JEG-885: the received core player of a row (opportunities.js sets `core` to the highest DDF Value player you receive).
  const coreKey = r => (r.core ? String(r.core.player_key) : "");
  function ourFitDetail(r) {
    if (!r.ours) return "";
    const delta = r.fit && r.fit.us && r.fit.us.starterDelta;
    if (!finite(delta) || delta <= 0.05 || !r.give.concat(r.receive).every(p => p.values && finite(p.values[OUR_KEY]))) return r.ours.detail;
    const gain = `starters gain ${signed(delta)}`;
    return r.ours.detail.includes("starters hold") ? r.ours.detail.replace("starters hold", gain) : `${r.ours.detail}; ${gain}`;
  }
  // JEG-1081: does DDF Value (projections) back the trade? A tick when it gains you, a cross when it loses you, a dash when level or unpriced.
  function projText(r) {
    if (r.projAgrees === true) return {mark: "\u2713", word: "Projections agree", cls: "is-agree"};
    if (r.projAgrees === false) return {mark: "\u2717", word: "Projections disagree", cls: "is-disagree"};
    return {mark: "\u2013", word: r.projEdge === null || r.projEdge === undefined ? "Projections unavailable" : "Projections level", cls: "is-level"};
  }
  function projCell(r) {
    const t = projText(r);
    const n = r.projEdge === null || r.projEdge === undefined ? "" : ` ${signed(r.projEdge)}`;
    return el("td", {class: `num v2-lg-proj ${t.cls}`, "data-cell": "proj", title: r.projAgrees === true ? "Projections agree with the DDF Value assessment of this trade."
        : r.projAgrees === false ? "Projections disagree with the DDF Value assessment of this trade."
          : r.projEdge === null || r.projEdge === undefined ? "No projection for a player in this trade, so projections cannot say." : "Projections see this trade as level (inside 0.05 points)."},
      el("span", {"aria-hidden": "true", text: `${t.mark}${n}`}), el("span", {class: "v2-sr", text: `${t.word}${n ? `, ${n.trim()} points` : ""}`}));
  }
  function detailRow(r, ctx, colspan) {
    const valueLine = (list, key) => list.map(p => `${p.name} ${finite(p.values[key]) ? money(p.values[key]) : "no value"}`).join(", ");
    // JEG-1059: the badge that marks a value the reader set, next to each player's DDF Value.
    const ourLine = list => {
      const out = [];
      list.forEach((p, i) => {
        if (i) out.push(", ");
        out.push(`${p.name} ${finite(p.values[OUR_KEY]) ? money(p.values[OUR_KEY]) : "no value"}`);
        const badge = root.DDFOverrides && root.DDFOverrides.flag ? root.DDFOverrides.flag(p) : null;
        if (badge) out.push(badge);
      });
      return out;
    };
    const withAvg = list => (ctx.market ? F.withChartAverage(list, ctx.market) : list);
    const box = el("div", {class: "v2-lg-detail-body"});
    box.append(el("p", {}, el("b", {text: "You give: "}), ...ourLine(r.give), ` (DDF Value); ${ctx.market ? valueLine(withAvg(r.give), MARKET_KEY) : "no trade chart average"} (Trade chart average).`),
      el("p", {}, el("b", {text: "You receive: "}), ...ourLine(r.receive), ` (DDF Value); ${ctx.market ? valueLine(withAvg(r.receive), MARKET_KEY) : "no trade chart average"} (Trade chart average).`));
    if (r.fit) {
      const fit = O.fullFit(r);
      box.append(el("p", {class: "v2-find-fit", title: F.fitTip(fit.variant), text: F.fitText(fit)}));
      if (fit.us && r.give.concat(r.receive).every(p => p.values && finite(p.values[OUR_KEY]))
          && finite(fit.us.starterDelta) && fit.us.starterDelta > 0.05) {
        box.append(el("p", {class: "v2-find-fit", text: `Your best starting lineup gains ${money(fit.us.starterDelta)} on DDF Value.`}));
      }
    }
    const ws = store.get();
    const mine = teamById(ws, ws.myTeamId);
    const opp = teamById(ws, r.opponentId);
    if (mine && opp && ctx.shape) {
      const rowsOf = t => rowsOfTeam(t, ctx);
      const line = (who, team, leaving, arriving) => {
        const parts = [["ddf", OUR_KEY, rowsOf(team)]].concat(ctx.market ? [["market", MARKET_KEY, withAvg(rowsOf(team))]] : []).map(([view, key, roster]) => {
          const leave = view === "market" ? withAvg(leaving) : leaving;
          const arrive = view === "market" ? withAvg(arriving) : arriving;
          const imp = F.rosterImpact(roster, leave, arrive, ctx.shape, key);
          return `${view === "ddf" ? "DDF Value" : "Trade chart average"} ${money(imp.before.starterValue)} → ${money(imp.after.starterValue)} (${signed(imp.starterDelta)})`;
        });
        return el("p", {class: "v2-meta"}, el("b", {text: `${who} best starting lineup: `}), `${parts.join("; ")}.`);
      };
      box.append(line("Your", mine, r.give, r.receive), line(`${opp.name}'s`, opp, r.receive, r.give));
    }
    box.append(el("a", {class: "v2-link", href: `#compare-trade?give=${r.give.map(p => encodeURIComponent(p.player_key)).join(",")}&get=${r.receive.map(p => encodeURIComponent(p.player_key)).join(",")}`, text: "Open in Compare a trade"}));
    return el("tr", {class: "v2-lg-opp-detail", "data-detail-for": r.id}, el("td", {colspan: String(colspan)}, box));
  }
  // JEG-1099: click a row (or its "Both teams" button) and the two lineups it changes open below the table.
  // The pick lives in the address as ?trade=<opponent>~<give keys>~<receive keys> so the link reopens the same trade.
  const tradeParam = r => [r.opponent, r.give.map(p => p.player_key).join(","), r.receive.map(p => p.player_key).join(",")].map(encodeURIComponent).join("~");
  // Focus goes back to the button that opened the panel (the visible one: the table and the phone cards both carry one).
  function focusPick(id) {
    const all = [...document.querySelectorAll(`[data-pick-for="${id}"]`)];
    const back = all.find(b => b.offsetParent !== null) || all[0];
    if (back) back.focus();
  }
  function setTradeHash(r) {
    const hash = root.location.hash || "";
    if (!hash.startsWith("#find-league")) return;
    const base = hash.split("?")[0];
    const rest = (hash.split("?")[1] || "").split("&").filter(p => p && !p.startsWith("trade="));
    if (r) rest.push(`trade=${tradeParam(r)}`);
    try { root.history.replaceState(root.history.state, "", root.location.pathname + root.location.search + base + (rest.length ? `?${rest.join("&")}` : "")); } catch (error) { /* the pick still works on this page */ }
  }
  function selectOpp(r) {
    UI.selectedOpp = r ? r.id : null;
    UI.selectedParam = r ? tradeParam(r) : null;
    setTradeHash(r);
  }
  // The pick in the address, if any, once the rows exist.
  function pickFromHash(rows) {
    const m = /[?&]trade=([^&]+)/.exec(root.location.hash || "");
    if (!m || !rows.length) return;
    if (UI.selectedParam === m[1]) return;
    const hit = rows.find(r => tradeParam(r) === m[1]);
    if (hit) { UI.selectedOpp = hit.id; UI.selectedParam = m[1]; }
  }
  function sidePanel(heading, team, leaving, arriving, ctx) {
    const withAvg = list => (ctx.market ? F.withChartAverage(list, ctx.market) : list);
    const names = list => list.map(p => p.name).join(" + ") || "nobody";
    const node = el("section", {class: "v2-lg-oppside", "data-side": heading, "aria-label": heading},
      el("h4", {text: `${heading}${team ? `: ${team.name}` : ""}`}),
      el("p", {}, el("b", {text: "Gives: "}), names(leaving), el("br"), el("b", {text: "Gets: "}), names(arriving)));
    if (!team || !ctx.shape) return node;
    const views = [["DDF Value", OUR_KEY, rows => rows]].concat(ctx.market ? [["Trade chart average", MARKET_KEY, withAvg]] : []);
    views.forEach(([label, key, convert]) => {
      const imp = F.rosterImpact(convert(rowsOfTeam(team, ctx)), convert(leaving), convert(arriving), ctx.shape, key);
      const view = L.renderTable(imp, ctx.shape, key, `Best starting lineup in ${label}`);
      view.querySelector("table").setAttribute("data-view", label);
      node.append(view);
      if (label === "DDF Value") node.append(el("p", {class: "v2-meta", "data-line": "need", text: `${F.needLine(imp)}.`}));
    });
    return node;
  }
  // JEG-1108: the fit label and the viability level (the one-team screen's labels), e.g. "Natural fit · High viability".
  const FIT_LABEL = {natural: "Natural fit", market: "Market supported", force: "Force fit"};
  const VIAB_LABEL = {High: "High", "Med-High": "Medium-high", Medium: "Medium"};
  function viabilityText(r, mine, opp, ctx) {
    if (!r.fit || !mine || !opp || !ctx.shape || !ctx.market) return "Viability can't be judged for this trade.";
    const avg = list => F.withChartAverage(list, ctx.market);
    const level = F.viabilityLabel(r.fit, avg(rowsOfTeam(mine, ctx)), avg(rowsOfTeam(opp, ctx)), avg(r.give), avg(r.receive), ctx.shape, OUR_KEY, ctx.chartKeys || []);
    const fit = FIT_LABEL[r.fit.label] || "Fit";
    return level ? `${fit} · ${VIAB_LABEL[level] || level} viability` : `${fit} · not workable for both managers`;
  }
  function oppPanel(r, ctx) {
    const ws = store.get();
    const mine = teamById(ws, ws.myTeamId);
    const opp = teamById(ws, r.opponentId);
    const close = button("Close", {class: "v2-btn", id: "v2LgOppPanelClose"}, () => { const id = UI.selectedOpp; selectOpp(null); renderOpps(); focusPick(id); });
    const copyLinkBtn = button("Copy link to this trade", {class: "v2-btn", id: "v2LgOppPanelLink"}, () => copy(root.location.href, "Copied a link to this trade."));
    return el("section", {class: "v2-lg-oppanel", id: "v2LgOppPanel", "aria-labelledby": "v2LgOppPanelTitle", "data-opp-id": r.id},
      el("div", {class: "v2-card-head"}, el("div", {}, el("h3", {id: "v2LgOppPanelTitle", tabindex: "-1", text: `Trade details: vs ${r.opponent}`}),
        el("p", {class: "v2-meta", text: "Both teams, before and after. Press Escape to close."}))),
      el("div", {class: "v2-lg-oppsides"}, sidePanel("Your team", mine, r.give, r.receive, ctx), sidePanel("Their team", opp, r.receive, r.give, ctx)),
      r.fit ? el("p", {class: "v2-find-fit", id: "v2LgOppPanelFit", text: F.fitText(O.fullFit(r))}) : null,
      el("p", {class: "v2-meta", id: "v2LgOppPanelViability", "data-slot": "viability", text: viabilityText(r, mine, opp, ctx)}),
      el("div", {class: "v2-ctoolbar"}, copyLinkBtn, close));
  }
  // All optional fields describe the current summary before the trade, for either team.
  function summaryControls(ws, basis) {
    const fields = T.summaryFields(basis);
    const selected = new Set(Array.isArray(ws.ui.summaryColumns) ? ws.ui.summaryColumns : []);
    const rules = Array.isArray(ws.ui.summaryFilters) ? ws.ui.summaryFilters.filter(rule => rule && typeof rule === "object" && ["mine", "theirs"].includes(rule.side)) : [];
    const save = patch => { UI.oppsShown = PAGE; update(w => W.ops.setUi(w, patch), "ui:summary-fields"); };
    const columns = el("details", {id: "v2LgFields", class: "v2-lg-field-options", open: Boolean(UI.fieldsOpen)}, el("summary", {text: "Add team summary columns"}),
      el("p", {class: "v2-meta", text: "Current team summary before the trade. Values and ranks follow the summary's ranking basis."}));
    columns.addEventListener("toggle", () => { UI.fieldsOpen = columns.open; });
    [["mine", "Our team"], ["theirs", "Their team"]].forEach(([side, label]) => {
      const group = el("fieldset", {}, el("legend", {text: label}));
      fields.forEach(field => {
        const key = `${side}:${field.id}`;
        const input = el("input", {type: "checkbox", "data-summary-column": key});
        input.checked = selected.has(key);
        input.addEventListener("change", () => { if (input.checked) selected.add(key); else selected.delete(key); save({summaryColumns: [...selected]}); });
        group.append(el("label", {}, input, " ", field.label));
      });
      columns.append(group);
    });
    const filters = el("details", {id: "v2LgSummaryFilters", class: "v2-lg-field-options", open: Boolean(UI.summaryFiltersOpen) || rules.length > 0}, el("summary", {text: `Filter by team summary${rules.length ? ` (${rules.length})` : ""}`}),
      el("p", {class: "v2-meta", text: "All rules must match the current team summary before the trade. Missing values match only ‘Missing’."}));
    filters.addEventListener("toggle", () => { UI.summaryFiltersOpen = filters.open; });
    const select = (id, label, options) => {
      const control = el("select", {id}, ...options.map(([value, text]) => el("option", {value, text})));
      filters.append(el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: label}), control));
      return control;
    };
    const side = select("v2LgSummaryFilterSide", "Team", [["theirs", "Their team"], ["mine", "Our team"]]);
    const field = select("v2LgSummaryFilterField", "Summary field", fields.map(f => [f.id, f.label]));
    const op = select("v2LgSummaryFilterOp", "Condition", []);
    const value = el("input", {id: "v2LgSummaryFilterValue", type: "text", "aria-label": "Summary filter value"});
    const setOps = () => {
      const numeric = fields.find(f => f.id === field.value).type === "number";
      const choices = numeric ? [["gte", "At least"], ["lte", "At most"], ["eq", "Equals"]] : [["contains", "Contains"], ["notContains", "Does not contain"], ["eq", "Equals"]];
      op.replaceChildren(...choices.concat([["missing", "Missing"], ["present", "Has a value"]]).map(([v, t]) => el("option", {value: v, text: t})));
      value.inputMode = numeric ? "decimal" : "text";
      value.disabled = false;
    };
    field.addEventListener("change", setOps);
    op.addEventListener("change", () => { value.disabled = ["missing", "present"].includes(op.value); });
    setOps();
    filters.append(el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Value"}), value));
    const error = el("span", {class: "v2-meta", role: "status"});
    filters.append(button("Add filter", {class: "v2-btn", id: "v2LgSummaryFilterAdd"}, () => {
      const f = fields.find(f => f.id === field.value);
      if (!["missing", "present"].includes(op.value) && (!value.value.trim() || (f.type === "number" && !Number.isFinite(Number(value.value))))) {
        error.textContent = f.type === "number" ? "Enter a number for this filter." : "Enter text for this filter.";
        value.focus(); return;
      }
      UI.summaryFiltersOpen = true;
      save({summaryFilters: rules.concat([{side: side.value, field: field.value, op: op.value, value: value.value.trim()}])});
    }), error);
    rules.forEach((rule, index) => {
      const f = fields.find(f => f.id === rule.field);
      if (!f) return;
      const words = {gte: "at least", lte: "at most", eq: "equals", contains: "contains", notContains: "does not contain", missing: "missing", present: "has a value"};
      filters.append(el("p", {class: "v2-lg-summary-rule"}, `${rule.side === "mine" ? "Our" : "Their"} team · ${f.label} ${words[rule.op] || rule.op} ${["missing", "present"].includes(rule.op) ? "" : rule.value} `,
        button("Remove", {class: "v2-link", "aria-label": `Remove ${f.label} filter`}, () => save({summaryFilters: rules.filter((_, i) => i !== index)}))));
    });
    return el("div", {class: "v2-lg-summary-controls"}, columns, filters);
  }
  function fitInfo(variant) {
    const label = O.FIT_WORD[variant] || "Fit";
    return el("details", {class: "v2-lg-fit-info"}, el("summary", {"aria-label": `About ${label}`, text: "ⓘ"}), el("p", {role: "note", text: F.fitTip(variant)}));
  }
  function oppControls(ws, res) {
    const f = ws.ui.filters;
    const sel = (id, label, options, value, onChange) => {
      const s = el("select", {id}, ...options.map(([v, t]) => el("option", {value: String(v), text: t})));
      s.value = String(value);
      s.addEventListener("change", () => onChange(s.value));
      return el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: label}), s);
    };
    const set = patch => { UI.oppsShown = PAGE; update(w => W.ops.setUi(w, patch), "ui:filter"); };
    const opponents = res ? res.perOpponent : [];
    const hide = button(ws.ui.hideForce ? "Show force fits" : "Hide force fits", {class: "v2-btn", id: "v2LgHideForce", "aria-pressed": String(Boolean(ws.ui.hideForce))},
      () => { update(w => W.ops.setUi(w, {hideForce: !w.ui.hideForce}), "ui:filter"); UI.oppsShown = PAGE; announce(store.get().ui.hideForce ? "Force fits hidden." : "Force fits shown."); });
    return el("div", {class: "v2-ctoolbar v2-lg-filters"},
      sel("v2LgSize", "Package size:", [[2, "Up to 2-for-2"], [3, "Up to 3-for-3"], [4, "Up to 4-for-4"]], ws.ui.maxSize || 2, v => { update(w => W.ops.setUi(w, {maxSize: Number(v)}), "size"); }),
      sel("v2LgFilterFit", "Overall fit:", [["all", "All fits"], ["natural", "Natural only"], ["naturalMarket", "Natural and market supported"]], f.fit, v => set({filters: {fit: v}})),
      sel("v2LgFilterOpp", "Opponent:", [["all", "All opponents"]].concat(opponents.map(o => [o.id, o.name])), opponents.some(o => o.id === f.opponent) ? f.opponent : "all", v => set({filters: {opponent: v}})),
      sel("v2LgFilterCapture", "Min capture:", [[0, "Any"], [1, "1 point"], [3, "3 points"], [5, "5 points"], [10, "10 points"]], f.minCapture, v => set({filters: {minCapture: Number(v)}})),
      sel("v2LgFilterCharts", "Min charts fair:", [[0, "Any"], [1, "1"], [2, "2"], [3, "3"], [4, "4"]], f.minCharts, v => set({filters: {minCharts: Number(v)}})),
      hide);
  }
  function renderOppsNow() {
    const card = $("v2LgOpps");
    if (!card) return;
    const ws = store.get();
    const body = $("v2LgOppsBody");
    const ctx = mathContext();
    const has = ws.teams.some(t => t.entries.length);
    card.hidden = !has;
    if (!has || !ctx) { body.replaceChildren(); return; }
    const mine = teamById(ws, ws.myTeamId);
    const others = ws.teams.filter(t => t.id !== ws.myTeamId && rowsOfTeam(t, ctx).length);
    const status = text => body.replaceChildren(el("p", {class: "v2-meta", id: "v2LgOppsMsg", role: "status", text}));
    if (!mine) return status("Press the star on one team to mark it as yours. Trade opportunities are found for your team against every other team.");
    if (!rowsOfTeam(mine, ctx).length) return status(`Add players to ${mine.name} to find trade opportunities.`);
    if (!others.length) return status("Add at least one other team to find trade opportunities.");
    if (!ctx.charts.length) return status("No trade chart is available this week, so acceptance cannot be judged.");
    const res = UI.result;
    if (!res) return status(UI.running ? "Finding trades…" : "Finding trades…");
    const summary = summaryData();
    const basis = summary.basis;
    const byTeam = new Map(summary.summary.teams.map(t => [t.id, t]));
    const fields = T.summaryFields(basis);
    const selected = new Set(Array.isArray(ws.ui.summaryColumns) ? ws.ui.summaryColumns : []);
    const optional = ["mine", "theirs"].flatMap(side => fields.filter(f => selected.has(`${side}:${f.id}`)).map(f => ({...f, side, field: f,
      id: `summary:${side}:${f.id}`, label: `${side === "mine" ? "Our" : "Their"} ${f.label}`, get: r => { const t = byTeam.get(side === "mine" ? mine.id : r.opponentId); return t ? f.get(t) : null; }})));
    const cols = O.OPP_COLUMNS.concat(optional);
    const state = savedSort(ws, "opps", cols, O.OPP_DEFAULT);
    const onSort = next => setSort("opps", next, cols);
    const rules = Array.isArray(ws.ui.summaryFilters) ? ws.ui.summaryFilters.filter(rule => rule && typeof rule === "object" && ["mine", "theirs"].includes(rule.side)) : [];
    const filtered = O.filterRows(res.rows, ws.ui.filters, ws.ui.hideForce).filter(r => rules.every(rule =>
      T.summaryFieldMatches(byTeam.get(rule.side === "mine" ? mine.id : r.opponentId), rule, basis)));
    const sorted = S.sortRows(filtered, cols, state, O.OPP_TIES);
    // JEG-885 (Jeremy, 2026-10-25, option B; 2026-10-26, option A): the opening 10 rows hold at most O.CAP_PER_CORE rows for
    // one received core player, the rest fold under "N more for <player>"; "Show 10 more" and "Show all" show the plain ranked list. Selection only:
    // the order, every value, edge and fit label are exactly what the ranking produced.
    pickFromHash(res.rows);
    let capped = UI.oppsShown === PAGE && sorted.length > PAGE ? O.capPerCore(sorted, coreKey, O.CAP_PER_CORE) : {list: sorted, folds: new Map()};
    // A linked or restored pick must appear with its row, even when the opening core is folded.
    if (UI.selectedOpp && sorted.some(r => r.id === UI.selectedOpp) &&
        !capped.list.slice(0, UI.oppsShown).some(r => r.id === UI.selectedOpp)) {
      UI.oppsShown = sorted.length;
      capped = {list: sorted, folds: new Map()};
    }
    const togglePick = r => {
      const closing = UI.selectedOpp === r.id;
      selectOpp(closing ? null : r);
      renderOpps();
      if (closing) focusPick(r.id);
      else {
        const title = $("v2LgOppPanelTitle");
        if (title) { title.scrollIntoView({block: "nearest"}); title.focus({preventScroll: true}); }
      }
    };
    const phoneLayout = root.matchMedia("(max-width: 767px)").matches;
    const shownRows = capped.list.slice(0, UI.oppsShown);
    // Which cores show a fold control: the last visible row that carries the core, so the control sits with the player's rows.
    const foldAt = new Map();
    shownRows.forEach((r, i) => { if (capped.folds.has(coreKey(r))) foldAt.set(coreKey(r), i); });
    const openFolds = new Map();
    capped.folds.forEach((rows, key) => { if (UI.expandedCores.has(key) && foldAt.has(key)) openFolds.set(key, rows); });
    const revealed = [...openFolds.values()].reduce((n, rows) => n + rows.length, 0);
    // Expanding a core reveals more candidates without moving a worse rank ahead of a better one.
    const displayRows = S.sortRows(shownRows.concat(...openFolds.values()), cols, state, O.OPP_TIES);
    const displayFoldAt = new Map();
    displayRows.forEach((r, i) => { if (capped.folds.has(coreKey(r))) displayFoldAt.set(coreKey(r), i); });
    const mineRows = rowsOfTeam(mine, ctx);
    const balance = ctx.expected && ctx.shape ? F.rosterBalance(mineRows, ctx.expected, OUR_KEY, ctx.shape) : null;
    const headline = el("p", {class: "v2-find-headline", id: "v2LgOppsHeadline", role: "status"}, O.leagueHeadline(res, balance && balance.ready ? {over: balance.over, under: balance.under} : null) || "No trade opportunities found.");
    const oneOpp = ws.ui.filters.opponent !== "all" && res.perOpponent.find(o => o.id === ws.ui.filters.opponent);
    let oppHead = null;
    if (oneOpp) {
      const t = teamById(ws, oneOpp.id);
      const tb = ctx.expected && ctx.shape && t ? F.rosterBalance(rowsOfTeam(t, ctx), ctx.expected, OUR_KEY, ctx.shape) : null;
      oppHead = el("p", {class: "v2-meta", id: "v2LgOppHeadline", text: O.opponentHeadline(oneOpp, tb && tb.ready ? {under: tb.under} : null)});
    }
    const warn = [];
    if (res.capped) warn.push(`Only the first ${O.MAX_OPPONENTS} opponents with a roster were searched.`);
    if (res.skipped) warn.push(`${plural(res.skipped, "team")} with no roster ${res.skipped === 1 ? "was" : "were"} skipped.`);
    const notEval = ws.teams.some(t => t.entries.some(isK));
    const reset = button("Reset sort", {class: "v2-btn", id: "v2LgOppsReset", hidden: S.sameState(state, O.OPP_DEFAULT)}, () => onSort(O.OPP_DEFAULT));
    const two = {rowspan: "2"};
    const thead = el("thead", {},
      el("tr", {}, sortTh("opponent", cols, state, onSort, two), plainTh("Trade", two), sortTh("capture", cols, state, onSort, two), sortTh("proj", cols, state, onSort, {...two, title: "Projections agree or disagree with the DDF Value assessment of this trade."}), plainTh("Our team fit", two),
        plainTh("Market perception", {colspan: "2", scope: "colgroup"}), plainTh("Their team fit", two), sortTh("overall", cols, state, onSort, two), sortTh("rank", cols, state, onSort, two), ...optional.map(c => sortTh(c.id, cols, state, onSort, two))),
      el("tr", {}, sortTh("market", cols, state, onSort, null, "Edge"), sortTh("fair", cols, state, onSort, null, "Charts fair")));
    const colspan = OPP_COLSPAN + optional.length;
    // JEG-885: one trade row, used for the visible rows and for the rows an open fold reveals.
    const oppRowBody = r => {
      const open = UI.expanded.has(r.id);
      const details = button(open ? "Hide details" : "Details", {class: "v2-link v2-lg-details-btn", "data-details-for": r.id, "aria-expanded": String(open), "aria-label": `${open ? "Hide" : "Show"} details for ${r.opponent}: ${r.give.map(p => p.name).join(" and ")} for ${r.receive.map(p => p.name).join(" and ")}`}, () => {
        if (UI.expanded.has(r.id)) UI.expanded.delete(r.id); else UI.expanded.add(r.id);
        renderOpps();
      });
      const fitWord = r.overall ? O.FIT_WORD[r.overall] : "Not judged";
      const picked = UI.selectedOpp === r.id;
      const pickBtn = button(picked ? "Hide both teams" : "Both teams", {class: "v2-link v2-lg-pick-btn", "data-pick-for": r.id, "aria-expanded": String(picked), "aria-controls": "v2LgOppPanel"}, () => togglePick(r));
      const tr = el("tr", {class: `v2-lg-opp${picked ? " is-selected" : ""}`, "data-opp-id": r.id, "data-overall": r.overall || "none", "data-rank": String(r.rank)},
        el("td", {}, r.opponent, r.partial ? el("span", {class: "v2-meta", text: " (partial roster)"}) : null),
        el("th", {scope: "row", class: "v2-lg-trade"}, ...tradeNodes(r, ctx), el("br"), details, " ", pickBtn),
        el("td", {class: "num", "data-cell": "capture"}, `${signed(r.edge)} pts${r.edgePct === null ? "" : ` (${signed(r.edgePct)}%)`}`),
        projCell(r),
        el("td", {"data-cell": "ours"}, r.ours ? `${r.ours.label[0].toUpperCase()}${r.ours.label.slice(1)}` : "—", r.ours ? el("span", {class: "v2-meta", text: ` ${ourFitDetail(r)}`}) : null),
        el("td", {class: "num", "data-cell": "market"}, r.chartEdge === null ? "—" : signed(r.chartEdge)),
        el("td", {class: "num", "data-cell": "fair"}, `${r.rivalOkCount}/${r.chartCount} fair`),
        el("td", {"data-cell": "theirs"}, r.theirs ? r.theirs.detail[0].toUpperCase() + r.theirs.detail.slice(1) : "—"),
        el("td", {"data-cell": "overall"}, el("span", {class: `v2-lg-fit is-${r.overall || "none"}`, text: fitWord}), r.overall ? fitInfo(r.overall) : null),
        el("td", {class: "num", "data-cell": "rank"}, `#${r.rank}`),
        ...optional.map(c => el("td", {class: c.type === "number" ? "num" : "", "data-cell": c.id}, T.summaryFieldText(byTeam.get(c.side === "mine" ? mine.id : r.opponentId), c.field))));
      return el("tbody", {}, tr,
        ...(picked && !phoneLayout ? [el("tr", {class: "v2-lg-panel-row"}, el("td", {colspan: String(colspan)}, oppPanel(r, ctx)))] : []),
        ...(open ? [detailRow(r, ctx, colspan)] : []));
    };
    // The fold control: "N more for <player>", opening the rest of that player's rows right under it (keyboard: focus comes back).
    const foldLabel = key => `${capped.folds.get(key).length} more for ${capped.folds.get(key)[0].core.name}`;
    const foldButton = (key, suffix) => button(openFolds.has(key) ? `Hide ${foldLabel(key)}` : foldLabel(key),
      {class: "v2-link v2-lg-fold-btn", id: `v2LgFold-${key}${suffix}`, "aria-expanded": String(openFolds.has(key))},
      () => { if (UI.expandedCores.has(key)) UI.expandedCores.delete(key); else UI.expandedCores.add(key); renderOpps(); });
    const bodyRows = [];
    displayRows.forEach((r, i) => {
      bodyRows.push(oppRowBody(r));
      const key = coreKey(r);
      if (capped.folds.has(key) && displayFoldAt.get(key) === i) {
        bodyRows.push(el("tbody", {class: "v2-lg-fold"}, el("tr", {}, el("td", {class: "v2-lg-fold-cell", colspan: String(colspan)}, foldButton(key, "")))));
      }
    });
    const table = el("table", {class: "v2-find-lineup v2-lg-table", id: "v2LgOppsTable"},
      el("caption", {text: "Trade opportunities: my team against every other team, ranked by fit then by DDF Value capture"}), thead, ...bodyRows);
    // The phone cards: the same rows, the fold tucked inside the card of the player it belongs to.
    const oppCard = (r, tail) => el("li", {class: `v2-lg-card${UI.selectedOpp === r.id ? " is-selected" : ""}`, "data-opp-id": r.id, "data-overall": r.overall || "none"},
      el("h4", {}, `#${r.rank} · vs ${r.opponent} · ${r.overall ? O.FIT_WORD[r.overall] : "Not judged"}${r.partial ? " (partial roster)" : ""}`),
      // JEG-1232: one line per table column, in the table's order (value first), so Our fit and Their fit each get a line.
      el("p", {"data-line": "trade"}, ...tradeNodes(r, ctx)),
      el("p", {"data-line": "capture"}, `DDF Value: ${signed(r.edge)} pts${r.edgePct === null ? "" : ` (${signed(r.edgePct)}%)`}`),
      el("p", {"data-line": "proj"}, `${projText(r).word}${r.projEdge === null || r.projEdge === undefined ? "" : `: ${signed(r.projEdge)} points`}`),
      el("p", {"data-line": "ours"}, `Our fit: ${r.ours ? `${r.ours.label} · ${ourFitDetail(r)}` : "—"}`),
      el("p", {"data-line": "market"}, `Market: ${r.chartEdge === null ? "—" : `${signed(r.chartEdge)} (${r.rivalOkCount}/${r.chartCount} fair)`}`),
      el("p", {"data-line": "theirs"}, `Their fit: ${r.theirs ? r.theirs.detail : "—"}`),
      el("a", {class: "v2-link", href: `#compare-trade?give=${r.give.map(p => encodeURIComponent(p.player_key)).join(",")}&get=${r.receive.map(p => encodeURIComponent(p.player_key)).join(",")}`, text: "Open in Compare a trade"}),
      " ", button(UI.selectedOpp === r.id ? "Hide both teams" : "Both teams", {class: "v2-link v2-lg-pick-btn", "data-pick-for": r.id, "data-card": "1", "aria-expanded": String(UI.selectedOpp === r.id), "aria-controls": "v2LgOppPanel"}, () => togglePick(r)),
      r.overall ? fitInfo(r.overall) : null,
      ...optional.map(c => el("p", {"data-cell": c.id}, `${c.label}: ${T.summaryFieldText(byTeam.get(c.side === "mine" ? mine.id : r.opponentId), c.field)}`)),
      tail || null,
      UI.selectedOpp === r.id && phoneLayout ? oppPanel(r, ctx) : null);
    const cardNodes = [];
    displayRows.forEach((r, i) => {
      const key = coreKey(r);
      const tail = capped.folds.has(key) && displayFoldAt.get(key) === i ? foldButton(key, "-card") : null;
      cardNodes.push(oppCard(r, tail));
    });
    const cards = el("ul", {class: "v2-lg-cards", id: "v2LgOppsCards"}, ...cardNodes);
    const remaining = sorted.length - shownRows.length;
    const reveal = count => { UI.oppsShown = shownRows.length + count; renderOpps(); };
    const moreButtons = remaining > 0 ? [
      button(`Show ${Math.min(PAGE, remaining)} more`, {class: "v2-btn", id: "v2LgOppsMore"}, () => reveal(PAGE)),
      remaining > PAGE ? button(`Show all (${sorted.length})`, {class: "v2-btn", id: "v2LgOppsAll"}, () => reveal(remaining)) : null] : [];
    if (shownRows.length > PAGE) moreButtons.push(button(`Show top ${PAGE} only`, {class: "v2-btn", id: "v2LgOppsLess"}, () => { UI.oppsShown = PAGE; renderOpps(); }));
    const more = moreButtons.length ? el("div", {class: "v2-ctoolbar v2-lg-more"}, ...moreButtons) : null;
    const count = sorted.length ? el("p", {class: "v2-meta", id: "v2LgOppsCount", role: "status", text: `Showing ${shownRows.length + revealed} of ${sorted.length}`}) : null;
    const empty = !sorted.length ? el("p", {class: "v2-meta", id: "v2LgOppsMsg", text: res.rows.length ? "No opportunity matches these filters." : "No trade opportunities found."}) : null;
    body.replaceChildren(...[headline, oppHead, warn.length ? el("p", {class: "v2-meta", text: warn.join(" ")}) : null, oppControls(ws, res), summaryControls(ws, basis), el("div", {class: "v2-ctoolbar"}, reset),
      el("div", {class: "v2-lg-phonetools"}, phoneSort("v2LgOpps", cols, state, onSort)), empty,
      count, sorted.length ? el("div", {class: "v2-find-table-wrap v2-lg-tablewrap"}, table) : null, sorted.length ? cards : null, more,
      notEval ? el("p", {class: "v2-meta v2-footnote", text: "K and DEF are on rosters but not evaluated."}) : null].filter(Boolean));
  }

  // The finder runs for my team against every other team: debounced, one pairing at a time, cached by roster and values.
  function scheduleOpps() {
    if (UI.timer) clearTimeout(UI.timer);
    UI.runId += 1;
    const id = UI.runId;
    UI.timer = setTimeout(() => runOpps(id), OPP_DEBOUNCE_MS);
  }
  async function runOpps(id) {
    UI.timer = null;
    const ws = store.get();
    const ctx = mathContext();
    const mine = ws && teamById(ws, ws.myTeamId);
    const live = $("v2LgOppsStatus");
    if (!ctx || !mine || !ctx.charts.length) { UI.result = null; renderOpps(); return; }
    const opponents = ws.teams.filter(t => t.id !== mine.id);
    const maxSize = ws.ui.maxSize || 2;
    const heavy = (maxSize === 3 && opponents.length > 10) || (maxSize === 4 && opponents.length > 5);
    UI.running = true;
    const body = $("v2LgOppsBody");
    if (body) body.setAttribute("aria-busy", "true");
    const started = Date.now();
    const result = await O.runAll({id: mine.id, name: mine.name, entries: mine.entries}, opponents.map(t => ({id: t.id, name: t.name, entries: t.entries})),
      {rowsByKey: ctx.rowsByKey, shape: ctx.shape, expected: ctx.expected, weights: ctx.weights, charts: ctx.charts, market: ctx.market, maxSize, keepMine: true, keepTheirs: true},
      {cache: UI.cache, isCancelled: () => id !== UI.runId,
        onProgress: p => { if (live && (Date.now() - started > 500 || heavy)) live.textContent = `Finding trades… ${p.name} (${p.index + 1} of ${p.total}).${heavy ? " This may take several seconds." : ""}`; }});
    if (result.cancelled || id !== UI.runId) return;
    UI.running = false;
    if (body) body.removeAttribute("aria-busy");
    if (live) live.textContent = "";
    UI.result = result;
    renderOpps();
    announce(`${plural(result.rows.length, "trade opportunity", "trade opportunities")} found across ${plural(result.perOpponent.length, "opponent")}.`);
  }

  // ---------- keeping the page in step ----------
  function refreshAll(reason) {
    // The engine's numbers (or its readiness) changed: the player lines show values, so they are drawn again.
    if (reason === "load" || reason === "settings" || reason === "replace" || reason === "other-tab") UI.comps.forEach(c => { c.lastEntries = null; });
    renderTeams();
    renderStatus();
    if (String(reason).startsWith("ui:")) {
      if (reason === "ui:sort-summary" || reason === "ui:basis") { renderSummary(); if (reason === "ui:basis") renderOpps(); }
      else renderOpps();
      return;
    }
    renderSummary();
    if (reason === "size" || !String(reason).startsWith("ui:")) scheduleOpps();
    renderOpps();
  }

  // The league settings changed (JEG-1020): names and positions follow the engine, a stored page is read again for players the new
  // settings can now match, every number is recomputed from the engine, the saved settings snapshot follows.
  function onSettingsChanged(event) {
    if (!UI.ready || !engine()) return;
    const ctx = mathContext();
    if (!ctx) return;
    const notes = [];
    let ws = store.get();
    const taken = new Set(ws.teams.flatMap(t => t.entries.map(e => e.key)));
    ws.teams.forEach(team => {
      let entries = team.entries.map(e => { const row = ctx.rowsByKey.get(e.key); return row ? {...e, name: row.name, pos: row.pos} : e; });
      const res = team.sourceText ? F.page.parsePage(team.sourceText) : null;
      if (res) {
        const players = team.sourceTeam !== null && res.teams && res.teams[team.sourceTeam] ? res.teams[team.sourceTeam].players : res.players;
        const added = [];
        players.forEach(p => {
          const row = ctx.rowsByKey.get(String(p.id));
          if (!row || !(p.confidence >= 1)) return;
          const key = String(row.player_key);
          if (taken.has(key) || team.removed.includes(key)) return;
          taken.add(key);
          entries.push(entryOf(row, p.slot));
          added.push(row.name);
        });
        if (added.length) notes.push(`${team.name} read again: added ${added.join(", ")}.`);
      }
      if (JSON.stringify(entries) !== JSON.stringify(team.entries)) ws = W.ops.setEntries(ws, team.id, entries);
    });
    const C = engine();
    let snapshot = null;
    try { snapshot = {state: C.getState(), shape: C.getRosterShape ? C.getRosterShape() : null}; } catch (error) { snapshot = null; }
    if (snapshot) ws = W.ops.setSettings(ws, JSON.parse(JSON.stringify(snapshot)));
    UI.cache = O.createCache();
    store.replace(ws, "settings");
    if (ws.teams.length) {
      const text = `League settings updated. Reprocessing ${plural(ws.teams.length, "team")}.`;
      notice(`${text}${notes.length ? ` ${notes.join(" ")}` : ""}`);
      announce(text);
    }
    if (event && event.detail && event.detail.notes && notes.length) event.detail.notes.push(...notes);
  }

  // A share link: #find-league?workspace=<text> (older links used #find-trade?workspace=; v2.js rewrites them first).
  function readShareHash() {
    const hash = root.location.hash || "";
    const at = hash.indexOf("workspace=");
    if (at < 0 || !/^#find-(league|trade)\?/.test(hash)) return;
    const text = hash.slice(at + "workspace=".length).split("&")[0];
    const params = new URLSearchParams(hash.slice(hash.indexOf("?") + 1));
    const ctx = mathContext();
    if (!ctx) return;
    let teams;
    try { teams = W.decodeShare(text, ctx.rowsByKey); }
    catch (error) {
      $("v2LgCard").open = true;
      notice("That league link is incomplete or invalid. Your saved league has been kept.");
      return;
    }
    const keep = /[?&](trade=[^&]+)/.exec(hash);
    try { root.history.replaceState(root.history.state, "", root.location.pathname + root.location.search + "#find-league" + (keep ? `?${keep[1]}` : "")); } catch (error) { /* the link stays in the address bar */ }
    if (!teams.length) { $("v2LgCard").open = true; notice("That league link is empty or invalid. Your saved league has been kept."); return; }
    let w = W.newWorkspace({name: "Shared league"});
    teams.forEach(t => { w = W.ops.addTeam(w, t.name, {entries: t.entries.filter(e => !e.unknown)}); });
    // New links preserve an unmarked league; legacy links have always put the marked roster first.
    const mine = params.has("wm") ? (params.get("wm") === "none" ? null : Number(params.get("wm"))) : 0;
    if (Number.isInteger(mine) && w.teams[mine]) w = W.ops.setMyTeam(w, w.teams[mine].id);
    params.delete("workspace");
    params.delete("wm");
    params.delete("trade");
    if (params.toString()) w = W.ops.setSettings(w, {query: params.toString()});
    offerReplace(w, "Shared link:");
  }

  // ---------- the cards ----------
  function build() {
    const host = $("v2FindLeague");
    if (!host || $("v2LgCard")) return;
    const addBtn = button("Add team", {class: "v2-btn", id: "v2LgAdd"}, () => {
      const ws = store.get();
      const before = ws.teams.length;
      update(w => W.ops.addTeam(w, `Team ${w.teams.length + 1}`), "add");
      const t = store.get().teams[before];
      if (t) { announce(`Team added: ${t.name}.`); const comp = UI.comps.get(t.id); if (comp) { comp.collapsed = false; comp.update(); comp.startRename(); } }
    });
    const fileInput = el("input", {type: "file", accept: "application/json,.json", id: "v2LgFile", class: "v2-sr", tabindex: "-1", "aria-hidden": "true"});
    fileInput.addEventListener("change", () => { loadFile(fileInput.files[0]); fileInput.value = ""; });
    const load = button("Load", {class: "v2-btn", id: "v2LgLoad"}, () => fileInput.click());
    const download2 = button("Download", {class: "v2-btn", id: "v2LgDownload"}, download);
    const copyText = button("Copy as text", {class: "v2-btn", id: "v2LgCopyText"}, () => copy(W.copyText(store.get()), "Copied the teams as text."));
    const copyLink = button("Copy link", {class: "v2-btn", id: "v2LgCopyLink"}, () => {
      const enc = W.shareHash(store.get(), leagueQuery());
      const ov = root.DDFOverrides;
      const shared = ov && ov.shareLink ? ov.shareLink(enc.hash) : {hash: enc.hash, dropped: false};
      const url = `${root.location.origin}${root.location.pathname}${shared.hash}`;
      copy(url, (enc.full ? "Copied a link to the whole league and its settings." : "Link carries your team and league settings only. For the full league, use Download.")
        + (shared.dropped ? " " + ov.dropOverridesNote() : ""));
    });
    const transferInfo = (label, text) => el("details", {class: "v2-lg-transfer-info"},
      el("summary", {"aria-label": `About ${label}`, text: "ⓘ"}), el("p", {class: "v2-meta", text}));
    const transfer = el("details", {class: "v2-lg-transfer", id: "v2LgTransfer"},
      el("summary", {class: "v2-btn", text: "Import / export"}),
      el("div", {class: "v2-lg-transfer-menu"},
        el("div", {class: "v2-lg-transfer-action"}, download2, transferInfo("Download", "Save a JSON file with every team, roster and your current league settings. Use Load to open that file on another device.")),
        el("div", {class: "v2-lg-transfer-action"}, load, transferInfo("Load", "Open a downloaded league JSON file. If you have a saved league here, you can choose whether to replace it. Undo restores your previous league.")),
        el("div", {class: "v2-lg-transfer-action"}, copyLink, transferInfo("Copy link", "Copy a link that opens the league rosters and current league settings on another device. If the league is too large for a link, only your marked team travels; Download always keeps every team.")),
        copyText));
    const undo = button("", {class: "v2-btn", id: "v2LgUndo", hidden: true}, () => {
      if (!UI.undo) return;
      const snap = UI.undo.ws;
      const valueContext = UI.undo.valueContext;
      UI.undo = null;
      UI.comps.forEach(c => c.li.remove());
      UI.comps.clear();
      if (snap.settings && snap.settings.query && root.TradeValueV2 && root.TradeValueV2.applyLinkLeague) {
        root.TradeValueV2.applyLinkLeague(new URLSearchParams(snap.settings.query));
      }
      if (valueContext && root.DDFOverrides && root.DDFOverrides.restoreContext) root.DDFOverrides.restoreContext(valueContext);
      store.replace(snap, "replace");
      renderUndo();
      announce("Undone.");
    });
    // JEG-1190: clear the whole league in one go, after one confirm, with Undo (Claude's pick under Jeremy's 2026-10-28
    // rule; see the picks log). Your roster is the marked team, so it goes too, on every tab.
    const clearConfirm = el("div", {class: "v2-lg-confirm", id: "v2LgClearConfirm", role: "group", "aria-label": "Clear league", hidden: true});
    const clearAll = button("Clear league", {class: "v2-btn", id: "v2LgClearAll", hidden: true}, () => {
      const ws = store.get();
      const yes = button("Clear league", {class: "v2-btn v2-lg-remove-yes", id: "v2LgClearYes"}, () => {
        UI.undo = {label: "Cleared the league", ws: store.get()};
        clearConfirm.hidden = true;
        update(w => W.ops.clearLeague(w), "remove");
        renderUndo();
        announce("League cleared. Undo puts it back.");
        $("v2LgUndo").focus();
      });
      const no = button("Cancel", {class: "v2-btn v2-lg-remove-no"}, () => { clearConfirm.hidden = true; clearAll.focus(); });
      const players = ws.teams.reduce((n, t) => n + t.entries.length, 0);
      clearConfirm.replaceChildren(el("span", {text: `Clear all ${plural(ws.teams.length, "team")} and ${plural(players, "player")}, your roster included? `}), yes, no);
      clearConfirm.hidden = false;
      no.focus();
    });
    const leaguePaste = el("textarea", {id: "v2LgLeaguePaste", rows: "3", autocomplete: "off", spellcheck: "false",
      placeholder: "Paste your league's whole rosters page here (ESPN, Yahoo or any site)", "aria-describedby": "v2LgLeaguePasteHelp"});
    leaguePaste.addEventListener("paste", event => {
      const text = event.clipboardData ? event.clipboardData.getData("text") : "";
      if (text) { event.preventDefault(); pasteWholeLeague(text); }
    });
    leaguePaste.addEventListener("input", () => { if (F.looksLikePage(leaguePaste.value)) pasteWholeLeague(leaguePaste.value); });
    const leagueBox = el("details", {class: "v2-find-import", id: "v2LgImport", open: store.get().teams.length === 0}, el("summary", {text: "Load a whole league: paste its rosters page"}),
      el("div", {class: "v2-find-import-body"},
        el("label", {class: "v2-find-search-label"}, el("span", {class: "v2-sr", text: "Paste a whole league's rosters page"}), leaguePaste),
        el("p", {class: "v2-meta", id: "v2LgLeaguePasteHelp", text: "ESPN: League, then Rosters. Yahoo: your league's rosters page. Press Ctrl+A then Ctrl+C on the page (on a phone, select all and copy) and paste. Every team is set up with its name. Sleeper shows one roster per page: copy each team's page and paste it with Add team. Nothing to connect, no sign-up. You copy, we read the text, and it stays on this device."}),
        el("div", {class: "v2-meta", id: "v2LgLeagueStatus", role: "status"})));
    const league = el("details", {class: "v2-card v2-lg-editor", id: "v2LgCard", "aria-labelledby": "v2LgTitle", open: true},
      el("summary", {class: "v2-card-head v2-lg-card-summary"}, el("div", {},
        el("h2", {id: "v2LgTitle", text: "Your league"}),
        el("p", {class: "v2-meta", id: "v2LgEditorSummary", text: "Paste your league rosters or add teams, then mark your team with the star."}))),
      el("div", {class: "v2-ctoolbar v2-lg-toolbar"}, el("b", {id: "v2LgCount", text: "Teams (0)"}), addBtn, clearAll, undo, fileInput,
        el("span", {class: "v2-meta v2-lg-saved", id: "v2LgSaved", role: "status", "aria-live": "polite"})),
      clearConfirm,
      el("div", {class: "v2-lg-confirm", id: "v2LgLoadConfirm", role: "group", hidden: true}),
      el("section", {class: "v2-lg-parsed", id: "v2LgParsed", role: "status", "aria-live": "polite", "aria-label": "What was read from your paste", hidden: true}),
      el("p", {class: "v2-meta", text: "Saved on this device. Bookmark this page to come back, or use Download to keep a copy or move it to another device. Nothing is sent anywhere."}),
      el("p", {class: "v2-meta", id: "v2LgEmpty", text: "No teams yet. Let's get your league in here: paste your league's rosters page below, or add a team and paste its roster or search players by name. No sign-up; it saves on this device."}),
      leagueBox,
      el("ul", {class: "v2-lg-teams", id: "v2LgTeams"}),
      el("p", {class: "v2-meta v2-footnote", id: "v2LgFootnote", hidden: true, text: "K and DEF are on rosters (and counted) but not evaluated."}),
      el("div", {class: "v2-sr", id: "v2LgLive", role: "status", "aria-live": "polite"}));
    const summary = el("section", {class: "v2-card", id: "v2LgSummary", "aria-labelledby": "v2LgSummaryTitle", hidden: true},
      el("div", {class: "v2-card-head"}, el("div", {}, el("h2", {id: "v2LgSummaryTitle", text: "Team summary"}),
        el("p", {class: "v2-meta", text: "Roster, starter and bench value for every team in DDF Value, DDF Value (projections) and the Trade chart average, with position allocation, ranks in each view and the players the views price differently."}))),
      el("div", {id: "v2LgSummaryBody"}), el("p", {class: "v2-sr", id: "v2LgSummaryCount"}));
    const opps = el("section", {class: "v2-card", id: "v2LgOpps", "aria-labelledby": "v2LgOppsTitle", hidden: true},
      el("div", {class: "v2-card-head"}, el("div", {}, el("h2", {id: "v2LgOppsTitle", text: "Trade opportunities"}),
        el("p", {class: "v2-meta", text: "Your team against every other team. Each trade is one you win on DDF Value while the market (at least three of the four trade charts) says the other manager breaks even or wins. Ranked by fit first, then by DDF Value capture."}))),
      el("p", {class: "v2-meta", id: "v2LgOppsStatus", role: "status"}), el("div", {id: "v2LgOppsBody"}));
    // JEG-1099: a click anywhere on a row (not on its own buttons and links) picks it; Escape closes the panel.
    opps.addEventListener("click", event => {
      const tr = event.target.closest && event.target.closest("tr.v2-lg-opp");
      if (!tr || event.target.closest("button, a, select, input, summary, details")) return;
      const row = UI.result && UI.result.rows.find(r => r.id === tr.dataset.oppId);
      if (row) {
        const closing = UI.selectedOpp === row.id;
        selectOpp(closing ? null : row);
        renderOpps();
        if (closing) focusPick(row.id);
        else {
          const title = $("v2LgOppPanelTitle");
          if (title) { title.scrollIntoView({block: "nearest"}); title.focus({preventScroll: true}); }
        }
      }
    });
    opps.addEventListener("keydown", event => {
      if (event.key !== "Escape" || !UI.selectedOpp) return;
      const id = UI.selectedOpp;
      selectOpp(null);
      renderOpps();
      focusPick(id);
    });
    const anchor = host.querySelector(".v2-footnote");
    host.insertBefore(el("div", {class: "v2-lg-transfer-bar"}, transfer), anchor);
    host.insertBefore(el("p", {class: "v2-meta", id: "v2LgNotice", role: "status"}), anchor);
    host.insertBefore(el("div", {class: "v2-lg-mismatch", id: "v2LgMismatch", role: "status", hidden: true}), anchor);
    host.insertBefore(league, anchor);
    host.insertBefore(summary, anchor);
    host.insertBefore(opps, anchor);
  }

  function start() {
    build();
    if (!$("v2LgCard")) return;
    store.onChange((ws, change) => {
      if (UI.ready) refreshAll(change.reason);
      // JEG-1095: pressing the star changes which team the paste summary calls yours.
      if (UI.parsed && !UI.parsed.error && ws.myTeamId !== UI.parsedMine) showParsed(UI.parsed);
    });
    store.onStatus(renderStatus);
    const lc = store.loadStatus();
    if (lc === "corrupt" || lc === "version") notice("Saved league data could not be read. You can re-enter your teams.");
    $("v2LgTeams").addEventListener("input", () => {});
    document.addEventListener("ddf:league-settings-changed", onSettingsChanged);
    root.addEventListener("hashchange", readShareHash);
    const phoneLayout = root.matchMedia("(max-width: 767px)");
    if (phoneLayout.addEventListener) phoneLayout.addEventListener("change", () => { if (UI.selectedOpp) renderOpps(); });
    const ready = () => {
      const ctx = mathContext();
      if (!ctx) return false;
      UI.ready = true;
      refreshAll("load");
      UI.firstPaint = false;
      renderUndo();
      readShareHash();
      return true;
    };
    if (!ready()) {
      let tries = 0;
      const timer = setInterval(() => { tries += 1; if (ready() || tries > 120) clearInterval(timer); }, 250);
      renderTeams();
      renderStatus();
    }
    root.TradeValueLeague = {refresh: () => refreshAll("load"), ui: UI};
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof window !== "undefined" ? window : globalThis);
