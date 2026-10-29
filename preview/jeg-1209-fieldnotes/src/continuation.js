// JEG-1209 Fieldnotes revision 3: Find a trade (whole league), private preview.
//
// Continues the revision-2 finder (#1089, docs/design/jeg-1209-fieldnotes/prototype.html) and runs the sibling components
// unchanged (vendor/, pinned in vendor/MANIFEST.json):
//   League status header        JEG-1233 TradeValueLeagueStatus.mount on the real workspace store
//   Opponents to include        JEG-1231 TradeValueOpponentInclusion (stable team ids, Select all / Clear)
//   Managers and Trade ideas    JEG-1217 cards, mounting themselves as they do on the live page
// Columns are drawn in one fixed order, value first, with no order picker (Jeremy, 2026-10-29, JEG-1232: "Go with the
// fixed order value first."). The stores save under preview-only keys (build.py PREVIEW_STORAGE), never the live ones.
// The opportunity rows, values and labels are the historical Week 7 fixture from revision 2, unchanged. Nothing here
// computes a value, a fit or a ranking; "Review states" only swap in the inputs each state would have.
(function () {
  "use strict";
  const W = window.TradeValueWorkspace, S = window.TradeValueLeagueStatus, OI = window.TradeValueOpponentInclusion;
  const M = window.TradeValueManagerProfiles;
  const BASE = "revision2.html";   // the revision-2 routes, built next to this page so the links work wherever it is opened
  const POS = ["QB", "RB", "WR", "TE"];
  const PAGE = 8;
  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? "" : s).replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const signed = n => (finite(n) ? (n > 0.05 ? "+" : n < -0.05 ? "−" : "") + Math.abs(n).toFixed(1) : "Unavailable");
  const fmt = n => (finite(n) ? n.toFixed(1) : "—");
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;
  const names = list => list.map(p => esc(p.name)).join(" + ");
  const shot = new URLSearchParams(location.search).has("shot");
  if (shot) document.documentElement.dataset.shot = "true";
  if (new URLSearchParams(location.search).get("theme") === "dark") document.documentElement.dataset.theme = "dark";

  // ---------- fixture ----------
  const F = FIXTURE.finder;
  const byKey = new Map(FIXTURE.players.map(p => [String(p.player_key), p]));
  const priced = list => list.map(p => ({...p, values: (byKey.get(String(p.player_key)) || {}).values || {}}));
  // The JEG-1217 cards read rows the way league.js hands them over: give/receive carry each player's values.
  // ours/theirs are labelled by today's opportunities.js (ourFitOf/theirFitOf) from the fixture's own fit fields, as league.js does.
  const O = window.TradeValueOpportunities;
  const ROWS = F.rows.map(r => ({...r, give: priced(r.give), receive: priced(r.receive), ours: O.ourFitOf(r.fit), theirs: O.theirFitOf(r.fit)}));
  const fixtureWorkspace = ui => W.normalizeWorkspace({id: "sample-league", name: "Sample league (illustrative)", teams: FIXTURE.rosters, myTeamId: F.mine, ui});

  // Revision 2's outcome-first columns, ids, wording and order kept. The first six show by default; the last two are optional.
  const UNITS = [
    {id: "us", label: "Our starter Δ", hint: "DDF Value", required: true},
    {id: "usProj", label: "Our projected starter Δ", hint: "DDF Projections · value points", required: true, projection: true},
    {id: "ourRoster", label: "Our roster after", hint: "DDF lineup + bench", required: true},
    {id: "them", label: "Their starter Δ", hint: "Combined trade-value average", required: true},
    {id: "themProj", label: "Their projected starter Δ", hint: "DDF Projections · value points", required: true, projection: true},
    {id: "theirRoster", label: "Their roster after", hint: "Market lineup + bench", required: true},
    {id: "package", label: "Package capture", hint: "DDF receive − send", required: false},
    {id: "fit", label: "Current fit label", hint: "Existing rules, unchanged", required: false}
  ];
  const FIT_WORD = {natural: "Natural fit", market: "Market supported", force: "Force fit"};

  // ---------- page state (everything else lives in the stores) ----------
  const UI = {mode: "normal", size: 2, backups: {QB: 0, RB: 0, WR: 0, TE: 0}, ran: null, open: null, trigger: null, shown: PAGE,
    optional: new Set()};
  UI.ran = JSON.stringify([UI.size, UI.backups]);
  const store = W.store;
  const ws = () => store.get();
  // The sample league is written only when the preview has no league of its own yet, or on Reset preview, so filters
  // and manager profiles survive a reload. A league saved in the No league state gets the sample teams back, keeping
  // its saved filters.
  if (store.loadStatus() !== "ok") store.replace(fixtureWorkspace(), "seed");
  else if (!ws().teams.length) store.replace(fixtureWorkspace(ws().ui), "seed");
  let stash = null;   // the loaded league while No league is shown, so going back restores it

  const profileExcluded = id => {
    const p = M.get(M.store.get(), store.get(), id);
    return Boolean(p && p.excluded);
  };
  const oiOpts = () => ({profileExcluded});
  // One announcement region for the page, outside everything that rerenders; written after the render it describes.
  const announce = text => { $("previewLive").textContent = text; };
  const valuesReady = () => UI.mode !== "loading";
  const stale = () => JSON.stringify([UI.size, UI.backups]) !== UI.ran;

  // ---------- links back to the unchanged revision-2 routes ----------
  document.querySelectorAll("[data-base]").forEach(a => { a.href = `${BASE}#${a.dataset.base}`; });
  $("reviewSource").textContent = `Historical illustration · Week ${FIXTURE.provenance.contentWeek} · ${FIXTURE.provenance.setting}`;

  // ---------- League status (JEG-1233) ----------
  const leagueControls = document.createElement("div");
  leagueControls.className = "actions";
  leagueControls.innerHTML = `<a class="buttonlike" href="${BASE}#paste">Edit league</a><span class="meta">Your team follows the star on the league card.</span>`;
  const status = S.mount($("leagueStatusHost"), {store, id: "lgStatus", controls: leagueControls, valuesReady});

  // ---------- Opponents to include (JEG-1231) ----------
  const setInclusion = next => store.update(w => {
    const now = OI.read(w);
    return next(now, w) === now ? w : W.ops.setUi(w, OI.patch(next(now, w)));
  }, "opponents");
  const oi = OI.createControl({document, idPrefix: "oiFinder", legend: "Opponents to include",
    onToggle: (id, include) => setInclusion((s, w) => OI.setIncluded(s, w, id, include)),
    onIncludeAll: () => setInclusion((s, w) => OI.includeAll(s, w)),
    onExcludeAll: () => setInclusion((s, w) => OI.excludeAll(s, w))});
  $("opponentHost").append(oi.element);

  // ---------- Columns: one fixed order, value first (JEG-1232), and the optional columns ----------
  const order = () => ({drawn: UNITS.filter(u => u.required || UI.optional.has(u.id))});
  function renderColumns() {
    const host = $("columnHost");
    const extras = document.createElement("fieldset");
    extras.className = "optcols";
    extras.innerHTML = `<legend>Also show</legend>${UNITS.filter(u => !u.required).map(u => `<label class="column-choice"><input type="checkbox" data-optional="${u.id}" ${UI.optional.has(u.id) ? "checked" : ""}> ${esc(u.label)}<small>${esc(u.hint)}</small></label>`).join("")}`;
    extras.addEventListener("change", e => {
      const id = e.target.dataset.optional;
      if (!id) return;
      if (e.target.checked) UI.optional.add(id); else UI.optional.delete(id);
      renderColumns(); renderOpps();
      host.querySelector(`[data-optional="${id}"]`).focus();
      announce(`${UNITS.find(u => u.id === id).label} column ${e.target.checked ? "shown" : "hidden"}.`);
    });
    host.replaceChildren(extras);
  }

  // ---------- Trade preferences (page-only controls; results go out of date, never pretend to rerun) ----------
  function renderPrefs() {
    document.querySelectorAll("#packageSize button").forEach(b => b.setAttribute("aria-pressed", String(Number(b.dataset.size) === UI.size)));
    $("backups").innerHTML = POS.map(pos => `<div class="backup-stepper" role="group" aria-labelledby="bk-${pos}"><span class="poslabel" id="bk-${pos}">${pos}</span>
      <button type="button" class="small" data-backup="${pos}" data-delta="-1" aria-label="Fewer ${pos} backups" ${UI.backups[pos] === 0 ? "disabled" : ""}>−</button>
      <output aria-live="polite" aria-label="${pos} backups">${UI.backups[pos]}</output>
      <button type="button" class="small" data-backup="${pos}" data-delta="1" aria-label="More ${pos} backups">+</button></div>`).join("");
    $("stepPrefs").textContent = `${UI.size === 1 ? "1 for 1" : `Up to ${UI.size} players a side`}${POS.some(p => UI.backups[p]) ? " · backups set" : ""}`;
    const note = $("staleNote");
    note.hidden = !stale();
    note.innerHTML = stale() ? `<b>Results are from the previous preferences.</b> The search has not run with these yet, so the rows below are not updated. <button type="button" id="rerun" class="small">Use previous preferences</button>` : "";
  }
  $("packageSize").addEventListener("click", e => {
    const b = e.target.closest("button[data-size]");
    if (!b) return;
    UI.size = Number(b.dataset.size); renderPrefs(); renderOpps(); b.focus();
  });
  $("stagePrefs").addEventListener("click", e => {
    const b = e.target.closest("button[data-backup]");
    if (b && !b.disabled) {
      const pos = b.dataset.backup;
      UI.backups[pos] = Math.max(0, Math.min(20, UI.backups[pos] + Number(b.dataset.delta)));
      renderPrefs(); renderOpps();
      const again = document.querySelector(`button[data-backup="${pos}"][data-delta="${b.dataset.delta}"]`);
      (again && !again.disabled ? again : document.querySelector(`button[data-backup="${pos}"][data-delta="1"]`)).focus();
    }
    if (e.target.id === "rerun") {
      const back = JSON.parse(UI.ran);
      UI.size = back[0]; UI.backups = back[1]; renderPrefs(); renderOpps();
      document.querySelector(`#packageSize button[data-size="${UI.size}"]`).focus();
    }
  });

  // ---------- Trade opportunities ----------
  const roster = (r, side) => {
    const imp = r.impacts[side], fit = side === "us" ? r.fit.myConstruction : r.fit.theirConstruction;
    const counts = POS.map(pos => `${pos} ${imp.after.starters.filter(p => p.pos === pos).length}/${imp.after.bench.filter(p => p.pos === pos).length}`).join(" · ");
    return `<span class="${fit.ok ? "positive" : "warn"}">${fit.ok ? "Construction passes" : "Review construction"}</span><small>${counts}</small><small>Starters / bench by position</small>`;
  };
  const gainHtml = n => `<strong class="num ${finite(n) ? (n < -0.05 ? "negative" : n > 0.05 ? "positive" : "") : "unavailable"}">${signed(n)}</strong>`;
  function cell(r, u) {
    if (u.projection && UI.mode === "missing") return `<strong class="unavailable">Unavailable</strong><small>No projection input this week, so this is not 0.</small>`;
    if (["us", "usProj", "them", "themProj"].includes(u.id)) return gainHtml(r.impacts[u.id].starterDelta);
    if (u.id === "ourRoster") return roster(r, "us");
    if (u.id === "theirRoster") return roster(r, "them");
    if (u.id === "package") return gainHtml(r.edge);
    return esc(FIT_WORD[r.overall] || "Not judged");
  }
  function sideDetail(r, side, title) {
    const imp = r.impacts[side], pr = r.impacts[side === "us" ? "usProj" : "themProj"];
    const fit = side === "us" ? r.fit.myConstruction : r.fit.theirConstruction;
    const projBlock = UI.mode === "missing" ? `<strong class="unavailable">Unavailable</strong><small>No projection input this week.</small>`
      : `${gainHtml(pr.starterDelta)}<small>${fmt(pr.before.starterValue)} → ${fmt(pr.after.starterValue)}</small>`;
    return `<section class="finder-sideblock"><h3>${title}</h3><div class="finder-gains">
      <div><span class="meta">${side === "us" ? "DDF" : "Market"} starters</span>${gainHtml(imp.starterDelta)}<small>${fmt(imp.before.starterValue)} → ${fmt(imp.after.starterValue)}</small></div>
      <div><span class="meta">Projected starters</span>${projBlock}</div></div>
      <p class="${fit.ok ? "positive" : "warn"}">${fit.ok ? "Current construction checks pass." : esc(fit.issues.join("; "))}</p>
      <table class="roster-after"><caption class="sr">${title}: players by position after the trade</caption><thead><tr><th scope="col">Position</th><th scope="col">Starters</th><th scope="col">Bench</th></tr></thead>
      <tbody>${POS.map(pos => `<tr><th scope="row">${pos}</th><td>${imp.after.starters.filter(p => p.pos === pos).length}</td><td>${imp.after.bench.filter(p => p.pos === pos).length}</td></tr>`).join("")}</tbody></table>
      <details><summary>Names after the trade</summary><p><b>Starters:</b> ${imp.after.starters.map(p => esc(p.name)).join(", ")}</p><p><b>Bench:</b> ${imp.after.bench.map(p => esc(p.name)).join(", ") || "None"}</p></details></section>`;
  }
  function expansion(r) {
    return `<div class="finder-expansion" role="region" aria-labelledby="detail-${esc(r.id)}"><div class="pagehead"><div><p class="kicker">Selected trade · ${esc(r.opponent)}</p>
      <h3 class="detailtitle" id="detail-${esc(r.id)}" tabindex="-1">What changes for both teams?</h3></div><button type="button" data-close="${esc(r.id)}">Close details</button></div>
      <p><b>You send</b> ${names(r.give)}<br><b>You receive</b> ${names(r.receive)}</p>
      <div class="finder-sides space">${sideDetail(r, "us", "Your team · DDF perspective")}${sideDetail(r, "them", "Their team · market perspective")}</div>
      <div class="callout space"><b>${esc(FIT_WORD[r.overall] || "Not judged")}</b> <span class="meta">(historical rule, not the approved Natural-fit rule)</span>
      <p>Package capture is ${signed(r.edge)} DDF points. It is different from starter improvement and does not account for who replaces a departing starter.</p></div>
      <div class="actions space"><a class="buttonlike primary" href="${BASE}#compare">Review both teams</a></div></div>`;
  }

  function visibleRows() {
    if (UI.mode === "empty" || UI.mode === "loading") return [];
    return OI.filterRows(ROWS, ws(), OI.read(ws()), oiOpts());
  }
  function renderOpps() {
    const body = $("v2LgOppsBody");
    const {drawn} = order();
    const model = OI.describe(ws(), OI.read(ws()), oiOpts());
    let rows = visibleRows();
    const total = ROWS.length;
    let message = "";
    if (UI.mode === "empty") message = "No league loaded yet. Paste your league on a computer to find trades.";
    else if (UI.mode === "loading") message = "Player values are still loading. Results appear when they finish.";
    else if (model.status === "allExcluded") message = `No opponents are included, so no trades can be shown. ${total} stored results are hidden by this filter.`;
    else if (!rows.length) message = `None of the ${total} stored results involve the opponents you included.`;
    $("oppsCount").textContent = message ? "" : `Showing ${Math.min(rows.length, UI.shown)} of ${plural(rows.length, "result")} from ${model.counts.searched} of ${plural(model.counts.total, "opponent")}${rows.length < total ? ` (${total} stored in this example)` : ""}.`;
    $("stepResults").textContent = message ? "No results to show" : plural(rows.length, "result");
    $("v2LgOpps").dataset.stale = String(stale());
    if (message) {
      body.innerHTML = `<div class="emptystate" data-empty="${UI.mode === "normal" || UI.mode === "missing" ? "filters" : UI.mode}"><p>${esc(message)}</p>${model.status === "allExcluded" ? `<button type="button" id="emptyAll">Include all opponents</button>` : ""}</div>`;
      const all = $("emptyAll");
      if (all) all.addEventListener("click", () => { setInclusion((s, w) => OI.includeAll(s, w)); const first = document.querySelector("#oiFinder input:not([disabled])"); if (first) first.focus(); });
      return;
    }
    if (UI.open && !rows.some(r => r.id === UI.open)) {   // the open trade was filtered out: close it and say so
      UI.open = null;
      toast("The open trade is no longer in the results, so its details closed.");
    }
    const page = rows.slice(0, UI.shown);
    const head = `<thead><tr><th scope="col">Trade</th>${drawn.map(u => `<th scope="col" data-col="${u.id}">${esc(u.label)}<small>${esc(UI.mode === "missing" && u.projection ? "Unavailable this week" : u.hint)}</small></th>`).join("")}</tr></thead>`;
    const rowsHtml = page.map(r => {
      const open = UI.open === r.id;
      return `<tr class="${open ? "selected" : ""}" data-row="${esc(r.id)}"><th scope="row"><b>${esc(r.opponent)}</b><small>Send ${names(r.give)}</small><small>Get ${names(r.receive)}</small>
        <button type="button" class="small quiet opener" data-open="${esc(r.id)}" aria-expanded="${open}" aria-controls="exp-${esc(r.id)}">${open ? "Hide details" : "Details"}</button></th>
        ${drawn.map(u => `<td data-col="${u.id}">${cell(r, u)}</td>`).join("")}</tr>${open ? `<tr class="exprow" id="exp-${esc(r.id)}"><td colspan="${drawn.length + 1}">${expansion(r)}</td></tr>` : ""}`;
    }).join("");
    const cards = page.map(r => {
      const open = UI.open === r.id;
      return `<li class="finder-result ${open ? "selected" : ""}" data-row="${esc(r.id)}"><p class="kicker">${esc(r.opponent)}</p><p><b>Send</b> ${names(r.give)}<br><b>Get</b> ${names(r.receive)}</p>
        <div class="finder-mobile-metrics">${drawn.map(u => `<div data-col="${u.id}"><p class="meta">${esc(u.label)}</p>${cell(r, u)}</div>`).join("")}</div>
        <button type="button" class="opener" data-open="${esc(r.id)}" aria-expanded="${open}" aria-controls="card-exp-${esc(r.id)}">${open ? "Hide details" : "Details"}</button>
        ${open ? `<div id="card-exp-${esc(r.id)}">${expansion(r)}</div>` : ""}</li>`;
    }).join("");
    body.innerHTML = `<div class="tablewrap finder-tablewrap" tabindex="0" role="region" aria-label="Trade opportunities table, scrolls sideways"><table class="finder-table"><caption class="sr">Trade opportunities in the stored example, best ranked first</caption>${head}<tbody>${rowsHtml}</tbody></table></div>
      <ol class="finder-cards" aria-label="Trade opportunities">${cards}</ol>
      ${rows.length > UI.shown ? `<button type="button" id="showAll">Show all ${rows.length}</button>` : ""}`;
    const more = $("showAll");
    if (more) more.addEventListener("click", () => { UI.shown = Infinity; renderOpps(); });
  }
  const phone = () => matchMedia("(max-width: 700px)").matches;
  $("v2LgOppsBody").addEventListener("click", e => {
    const opener = e.target.closest("[data-open]");
    const closer = e.target.closest("[data-close]");
    if (opener) {
      const id = opener.dataset.open;
      UI.open = UI.open === id ? null : id;
      UI.trigger = id;
      renderOpps();
      if (UI.open) focusDetail(); else focusTrigger();
    } else if (closer) { UI.open = null; renderOpps(); focusTrigger(); }
  });
  $("v2LgOppsBody").addEventListener("keydown", e => {
    if (e.key !== "Escape" || !UI.open) return;
    if (e.target.closest && e.target.closest("details[open]") && e.target.tagName === "SUMMARY") return;
    UI.open = null; renderOpps(); focusTrigger();
  });
  function scope() { return phone() ? document.querySelector(".finder-cards") : document.querySelector(".finder-table"); }
  function focusDetail() { const h = scope() && scope().querySelector(".detailtitle"); if (h) { h.focus({preventScroll: true}); h.scrollIntoView({block: "nearest"}); } }
  function focusTrigger() { const b = scope() && scope().querySelector(`[data-open="${CSS.escape(UI.trigger || "")}"]`); if (b) b.focus(); }

  // ---------- review states ----------
  $("stateSwitch").addEventListener("click", e => {
    const b = e.target.closest("button[data-state]");
    if (!b) return;
    UI.mode = b.dataset.state;
    document.querySelectorAll("#stateSwitch button").forEach(x => x.setAttribute("aria-pressed", String(x === b)));
    UI.open = null;
    // The saved filters (ws.ui) carry through No league and back.
    if (UI.mode === "empty") {
      if (ws().teams.length) stash = ws();
      store.replace(W.normalizeWorkspace({id: "sample-league", name: "", teams: [], myTeamId: null, ui: ws().ui}), "replace");
    } else if (!ws().teams.length) {
      store.replace(stash ? {...stash, ui: ws().ui} : fixtureWorkspace(ws().ui), "replace");
      stash = null;
    } else status.update("status");
    renderAll();
    b.focus();
    announce(`Review state: ${b.textContent}.`);
  });
  $("resetPreview").addEventListener("click", () => {
    stash = null;
    Object.assign(UI, {mode: "normal", size: 2, backups: {QB: 0, RB: 0, WR: 0, TE: 0}, open: null, shown: PAGE, optional: new Set()});
    UI.ran = JSON.stringify([UI.size, UI.backups]);
    document.querySelectorAll("#stateSwitch button").forEach(x => x.setAttribute("aria-pressed", String(x.dataset.state === "normal")));
    M.store.update(() => M.emptyBook(), "reset");
    store.replace(fixtureWorkspace(), "reset");
    renderAll();
    $("resetPreview").focus();
    announce("Preview reset: the sample league, every opponent included, every manager at the default.");
  });

  // ---------- handoffs table ----------
  const HANDOFFS = [
    ["League status header and folded summary", "JEG-1233 · #1091", "league-status.js mounted on the real workspace store", "JEG-1137 shell and league entry"],
    ["Opponents to include (stable ids, Select all, Clear)", "JEG-1231 · #1090, hookup #1092", "opponent-inclusion.js createControl and filterRows", "JEG-1139 trade targets / league finder"],
    ["Columns in one fixed order, value first", "JEG-1232 · #1093", "Fixed revision-2 outcome order, no picker (Jeremy, Oct 29); column-order.js no longer vendored", "JEG-1139"],
    ["Managers card and Trade ideas with Stretch offers", "JEG-1217 · #1084", "manager-profiles-ui.js (note as checkboxes, earlier note text kept) and manager-recs-ui.js", "JEG-1139"],
    ["Shared and page-only trade preferences", "JEG-1229 · #1086", "Planned: named in Trade preferences only; TradeContext is not run or integrated here", "JEG-1137 common controls, JEG-1140 Settings"],
    ["Row details readout", "JEG-1230 · #1088", "Revision-2 detail panel from fixture impacts. Planned: the rollout swaps in the JEG-1230 readout (#1088 wires no routes yet)", "JEG-1138 Compare, reused by JEG-1139"],
    ["Both saved-team selectors", "JEG-1219", "Not on the whole-league page; Your team follows the star", "JEG-1138 / JEG-1139"],
    ["Candidate search and Natural fit", "#1072 and the stricter Natural fit rule (Codex)", "Not run: historical labels, marked as such", "Owners' own releases"]
  ];
  document.querySelector("#handoffTable tbody").innerHTML = HANDOFFS.map(h => `<tr><th scope="row">${esc(h[0])}</th><td>${esc(h[1])}</td><td>${esc(h[2])}</td><td>${esc(h[3])}</td></tr>`).join("");

  // ---------- routes ----------
  function route() {
    const name = (location.hash.replace("#", "").split("?")[0]) || "finder";
    const known = ["finder", "flow", "handoffs"];
    const r = known.includes(name) ? name : "finder";
    document.querySelectorAll("[data-route]").forEach(s => { s.hidden = s.dataset.route !== r; });
    document.querySelectorAll(".desktopnav a, .bottomnav a").forEach(a => { if (a.getAttribute("href") === "#finder") a.setAttribute("aria-current", r === "finder" ? "page" : "false"); });
    if (!known.includes(name)) {   // a stage anchor such as #stagePrefs
      const target = $(name);
      if (target) { target.focus({preventScroll: true}); target.scrollIntoView({block: "start"}); }
    } else if (r !== "finder") $("main").focus();
  }
  window.addEventListener("hashchange", route);

  let toastTimer = null;
  function toast(text) { $("toast").textContent = text; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $("toast").textContent = ""; }, 6000); }

  function renderAll() {
    const model = OI.describe(ws(), OI.read(ws()), oiOpts());
    oi.update(model);
    $("stepLeague").textContent = status.model() ? status.model().headline : "";
    renderPrefs();
    renderColumns();
    renderOpps();
    document.body.dataset.mode = UI.mode;
  }
  store.onChange(() => { renderAll(); });
  M.store.onChange(() => { renderAll(); });   // Won't trade in Managers greys the box in Opponents to include
  matchMedia("(max-width: 700px)").addEventListener("change", () => renderOpps());

  // The Trade ideas card reads the league's last result the way league.js exposes it.
  window.TradeValueLeague = {ui: {get result() { return UI.mode === "normal" || UI.mode === "missing" ? {rows: visibleRows()} : null; }}};
  window.TradeValueCurveControls = {getAllRows: () => FIXTURE.players};

  renderAll();
  route();
})();
