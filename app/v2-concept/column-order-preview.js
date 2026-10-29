// JEG-1232 private preview: the trade opportunities table drawn in a saved column order.
// Illustrative rows only (no engine values). The column catalog, sort and storage are the site's modules; the cell text
// mirrors league.js renderOpps so the wiring step can move the same per-unit renderers into it.
(function () {
  "use strict";
  const C = window.TradeValueColumnOrder;
  const O = window.TradeValueOpportunities;
  const S = window.TradeValueTableSort;
  const T = window.TradeValueTeamSummary;
  const W = window.TradeValueWorkspace;
  const store = W.store;
  const $ = id => document.getElementById(id);
  const CONTROL = "v2LgColumnOrder";
  const FIELDS = (T ? T.summaryFields("fund") : []).filter(f => ["rosterF", "starterF"].includes(f.id));
  const signed = v => `${v > 0 ? "+" : ""}${v.toFixed(1)}`;

  // Illustrative rows: names and numbers are made up and say nothing about any player's value.
  const ROWS = [
    {id: "r1", rank: 1, opponent: "Team Avery", give: "Player A", get: "Player B", edge: 4.2, chartEdge: 1.1, projAgrees: true, rivalOkCount: 3, chartCount: 4, overall: "natural", tier: 0, ours: "Fills a starter", theirs: "Upgrades their WR2", summary: {rosterF: [180.4, 171.2], starterF: [120.5, 112.9]}},
    {id: "r2", rank: 2, opponent: "Team Blake", give: "Player C", get: "Player D", edge: 3.1, chartEdge: -0.4, projAgrees: false, rivalOkCount: 2, chartCount: 4, overall: "market", tier: 1, ours: "Bench depth", theirs: "Even", summary: {rosterF: [180.4, 166.0], starterF: [120.5, 109.3]}},
    {id: "r3", rank: 3, opponent: "Team Casey", give: "Player E + Player F", get: "Player G", edge: 2.6, chartEdge: 2.3, projAgrees: true, rivalOkCount: 4, chartCount: 4, overall: "natural", tier: 0, ours: "Fills a starter", theirs: "Consolidates", summary: {rosterF: [180.4, 190.7], starterF: [120.5, 131.0]}},
    {id: "r4", rank: 4, opponent: "Team Drew", give: "Player H", get: "Player J", edge: 1.4, chartEdge: null, projAgrees: null, rivalOkCount: 1, chartCount: 4, overall: "force", tier: 2, ours: "Small gain", theirs: "Loses value", summary: {rosterF: [180.4, null], starterF: [120.5, null]}}
  ];
  const FIT = {natural: "Natural fit", market: "Market supported", force: "Force fit"};

  function optionalColumns(ws) {
    const selected = new Set(Array.isArray(ws.ui.summaryColumns) ? ws.ui.summaryColumns : []);
    return ["mine", "theirs"].flatMap(side => FIELDS.filter(f => selected.has(`${side}:${f.id}`)).map(f => ({
      id: `summary:${side}:${f.id}`, label: `${side === "mine" ? "Our" : "Their"} ${f.label}`, type: "number", first: "desc",
      get: r => r.summary[f.id][side === "mine" ? 0 : 1]})));
  }

  const el = (tag, attrs, ...kids) => {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v; else node.setAttribute(k, v === true ? "" : String(v));
    });
    kids.flat(Infinity).filter(k => k !== null && k !== undefined).forEach(k => node.append(k));
    return node;
  };
  const announce = text => { const live = $("previewAnnounce"); live.textContent = ""; setTimeout(() => { live.textContent = text; }, 30); };
  const update = patch => store.update(w => W.ops.setUi(w, patch), "ui:preview");

  let pendingFocus = null;
  function render() {
    const ws = store.get();
    const optional = optionalColumns(ws);
    const cols = O.OPP_COLUMNS.concat(optional);
    const saved = ws.ui.sort && S.validState(ws.ui.sort.opps, cols) ? ws.ui.sort.opps : O.OPP_DEFAULT;
    const units = C.opportunityUnits(O.OPP_COLUMNS, optional);
    const known = C.opportunityKnown(FIELDS);
    const r = C.reconcile(C.savedOf(ws.ui, "opps"), units, known);
    const drawn = C.applyOrder(units, r.order);
    const onSort = next => { update({sort: {opps: next}}); const c = cols.find(x => x.id === next.col); announce(S.announce(c, next.dir)); };
    const onMove = (id, delta) => {
      const m = C.move(r.full || r.order, r.order, id, delta);
      pendingFocus = {id, dir: delta < 0 ? "up" : "down"};
      if (m.moved) update(C.savePatch(store.get().ui, "opps", m.full)); else render();
      announce(C.moveMessage(units, m, id, delta));
    };
    const onReset = () => { pendingFocus = {id: null}; update(C.savePatch(store.get().ui, "opps", null)); announce("Column order reset to the default."); };

    // "Add team summary columns", as on the site (the same ui.summaryColumns key): shows or hides optional columns.
    const selected = new Set(Array.isArray(ws.ui.summaryColumns) ? ws.ui.summaryColumns : []);
    const fieldsBox = el("details", {id: "v2LgFields", class: "v2-lg-field-options", open: true}, el("summary", {text: "Add team summary columns"}));
    [["mine", "Our team"], ["theirs", "Their team"]].forEach(([side, label]) => {
      const group = el("fieldset", {}, el("legend", {text: label}));
      FIELDS.forEach(f => {
        const key = `${side}:${f.id}`;
        const input = el("input", {type: "checkbox", "data-summary-column": key});
        input.checked = selected.has(key);
        input.addEventListener("change", () => { if (input.checked) selected.add(key); else selected.delete(key); pendingFocus = {selector: `input[data-summary-column="${key}"]`}; update({summaryColumns: [...selected]}); });
        group.append(el("label", {}, input, " ", f.label));
      });
      fieldsBox.append(group);
    });
    const control = C.renderControl(document, {id: CONTROL, units: drawn, baseline: units.map(u => u.id), onMove, onReset, open: true});

    const rows = S.sortRows(ROWS, cols, saved, O.OPP_TIES);
    const sortTh = (id, attrs, label) => {
      const column = cols.find(c => c.id === id);
      const on = saved.col === id;
      const th = el("th", {scope: "col", "aria-sort": S.ariaSort(saved, id), "data-col": id, ...(attrs || {})});
      const btn = el("button", {type: "button", class: `v2-lg-sort${on ? " is-active" : ""}`, "data-sort": id, title: `Sort by ${column.label.toLowerCase()}`}, label || column.label, " ",
        el("span", {class: "v2-lg-arrow", "aria-hidden": "true", text: on ? (saved.dir === "asc" ? "▲" : "▼") : "↕"}));
      btn.addEventListener("click", () => { pendingFocus = {selector: `button[data-sort="${id}"]`}; onSort(S.nextState(saved, id, cols)); });
      th.append(btn);
      return th;
    };
    const plainTh = (id, label, attrs) => el("th", {scope: "col", "data-col": id, ...(attrs || {})}, label);
    const two = {rowspan: "2"};
    const head1 = drawn.map(u => {
      if (u.id === "trade") return plainTh("trade", "Trade", two);
      if (u.id === "ours") return plainTh("ours", "Our team fit", two);
      if (u.id === "theirs") return plainTh("theirs", "Their team fit", two);
      if (u.id === "market") return plainTh("marketGroup", "Market perception", {colspan: "2", scope: "colgroup"});
      if (u.id === "proj") return sortTh("proj", {...two, title: "Projections agree or disagree with the DDF Value assessment of this trade."});
      return sortTh(u.id, two);
    });
    const head2 = drawn.some(u => u.id === "market") ? [sortTh("market", null, "Edge"), sortTh("fair", null, "Charts fair")] : [];
    const cell = (u, row) => {
      switch (u.id) {
        case "opponent": return [el("td", {"data-cell": "opponent"}, row.opponent)];
        case "trade": return [el("th", {scope: "row", class: "v2-lg-trade", "data-cell": "trade"}, `Send ${row.give}, get ${row.get}`)];
        case "capture": return [el("td", {class: "num", "data-cell": "capture"}, `${signed(row.edge)} pts`)];
        case "proj": return [el("td", {"data-cell": "proj"}, row.projAgrees === null ? "—" : row.projAgrees ? "✓ Agree" : "✗ Disagree")];
        case "ours": return [el("td", {"data-cell": "ours"}, row.ours)];
        case "market": return [el("td", {class: "num", "data-cell": "market"}, row.chartEdge === null ? "—" : signed(row.chartEdge)),
          el("td", {class: "num", "data-cell": "fair"}, `${row.rivalOkCount}/${row.chartCount} fair`)];
        case "theirs": return [el("td", {"data-cell": "theirs"}, row.theirs)];
        case "overall": return [el("td", {"data-cell": "overall"}, el("span", {class: `v2-lg-fit is-${row.overall}`, text: FIT[row.overall]}))];
        case "rank": return [el("td", {class: "num", "data-cell": "rank"}, `#${row.rank}`)];
        default: { const c = cols.find(x => x.id === u.id); const v = c.get(row); return [el("td", {class: "num", "data-cell": u.id}, v === null ? "—" : v.toFixed(1))]; }
      }
    };
    const table = el("table", {class: "v2-find-lineup v2-lg-table", id: "v2LgOppsTable"},
      el("caption", {text: "Trade opportunities (illustrative rows): my team against every other team"}),
      el("thead", {}, el("tr", {}, head1), head2.length ? el("tr", {}, head2) : null),
      rows.map(row => el("tbody", {}, el("tr", {class: "v2-lg-opp", "data-opp-id": row.id, "data-rank": String(row.rank)}, drawn.map(u => cell(u, row))))));
    // Phone cards: the heading (rank, opponent, fit) stays the card's identity; the lines below follow the saved order.
    const line = (u, row) => {
      switch (u.id) {
        case "opponent": case "overall": case "rank": return null;
        case "trade": return el("p", {"data-line": "trade"}, `Send ${row.give}, get ${row.get}`);
        case "capture": return el("p", {"data-line": "capture"}, `DDF Value: ${signed(row.edge)} pts`);
        case "proj": return el("p", {"data-line": "proj"}, `Projections: ${row.projAgrees === null ? "—" : row.projAgrees ? "agree" : "disagree"}`);
        case "ours": return el("p", {"data-line": "ours"}, `Our fit: ${row.ours}`);
        case "market": return el("p", {"data-line": "market"}, `Market: ${row.chartEdge === null ? "—" : signed(row.chartEdge)} (${row.rivalOkCount}/${row.chartCount} fair)`);
        case "theirs": return el("p", {"data-line": "theirs"}, `Their fit: ${row.theirs}`);
        default: { const c = cols.find(x => x.id === u.id); const v = c.get(row); return el("p", {"data-line": u.id}, `${u.label}: ${v === null ? "—" : v.toFixed(1)}`); }
      }
    };
    const cards = el("ul", {class: "v2-lg-cards", id: "v2LgOppsCards"}, rows.map(row => el("li", {class: "v2-lg-card", "data-opp-id": row.id},
      el("h4", {}, `#${row.rank} · vs ${row.opponent} · ${FIT[row.overall]}`), drawn.map(u => line(u, row)))));
    const reset = el("button", {type: "button", class: "v2-btn", id: "v2LgOppsReset", hidden: S.sameState(saved, O.OPP_DEFAULT)}, "Reset sort");
    reset.addEventListener("click", () => onSort(O.OPP_DEFAULT));
    $("v2LgOppsBody").replaceChildren(el("div", {class: "v2-lg-summary-controls"}, fieldsBox, control), el("div", {class: "v2-ctoolbar"}, reset),
      el("div", {class: "v2-find-table-wrap v2-lg-tablewrap"}, table), cards);
    if (pendingFocus) {
      const f = pendingFocus;
      pendingFocus = null;
      if (f.selector) { const node = $("v2LgOppsBody").querySelector(f.selector); if (node) node.focus(); }
      else C.focusMove($("v2LgOppsBody"), CONTROL, f.id, f.dir);
    }
  }
  store.onChange(render);
  render();
})();
