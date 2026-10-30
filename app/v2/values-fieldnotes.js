// Trade Value v2: the Values page (Value chart) table and controls in the Fieldnotes presentation (JEG-1265, part of JEG-1192).
//
// Isolated component. The page does not load this file yet: the runtime hookup waits on the shared tokens, shell and
// navigation work in JEG-1137, and its owner applies the integration plan in docs/claude-log/2026-10-29-jeg-1265-values-fieldnotes.md.
//
// No value math here. The page keeps every contract it has today and hands this module what it already computed:
//   * which rows match (view.visible, after search, position, Show and value-range filters; the page filters, not this file),
//   * the columns (tableColumns(): series keys, their labels and their JEG-1212 group from tableGroup()),
//   * the ranking series (view.rankKey), the sort (state.sort) and how many rows are shown (state.shown),
//   * each missing value's reason (missingReason()) and each cell's existing notes (estimated, low confidence, your override).
// This module sorts with a copy of v2.js sortedRows() and computes the next sort with a copy of the header click rule; the
// harness proves both equal to v2.js itself. Every number is drawn with v2.js fmt(): a missing value is "—" with its reason,
// never zero, and a finite 0 is "0.0". It never re-ranks, re-prices, adds a threshold, picks a source or writes a store.
//
// Three layers, each usable alone:
//   * sortRows(rows, cols, sort) and nextSort(sort, rankKey, col): the page's own sort contract.
//   * viewModel(ctx): pure. Context in, the exact strings to show out. States: loading, unavailable (no values at all),
//     mixed (columns on different horizons: withheld, weekly is never shown beside rest-of-season), empty, ready.
//   * render(container, vm, on) and mount(container, opts): the DOM. mount re-renders on update() and keeps focus.
//
// Context (what an adapter hands in; the plan's v2.js hunk builds it from view and state):
//   {status: "loading" | "unavailable" | "ready", reason?: text,
//    fixture?: {kind: "synthetic" | "historical", label},   // set by every fixture; absent only for the live page
//    title, lede, settings: text, basis: {label, text},
//    rankKey, rankOptions: [{key, label, group, reason?}],  // the Rank by picker's entries (reason: why it cannot be picked)
//    groups: [{id, label, note}],                          // the table groups in v2.js TABLE_GROUPS order
//    columns: [{id, kind: "rank" | "name" | "meta" | "value" | "spread", label, text?, order?,
//               source?, method?, group?, horizon?, unavailable?: reason}],
//    rows: [{player_key, rank, name, pos, team, tier?, tierOrder?, posRank?, values: {key: number | null},
//            spread?: number | null, reasons: {colId: text}, notes: {colId: [text]}}],
//    sort: {key, dir} | null, shown, window: [lo, hi], filters: {search, position}, positions: [{value, label}]}
(function (root) {
  "use strict";

  const NAME = "Values (Fieldnotes)";
  // v2.js fmt(), unchanged: one decimal, a true minus sign, never "-0.0", "—" when not finite.
  const fmt = v => { if (!Number.isFinite(v)) return "—"; const text = v.toFixed(1); return text === "-0.0" ? "0.0" : text.replace("-", "−"); };
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || `${one}s`)}`;
  // The table groups and their order, as v2.js TABLE_GROUPS (JEG-1212 categories plus DDF Value, value above waivers, spread).
  const GROUP_ORDER = ["ddf", "projections", "published", "observed", "vorp", "spread"];

  // ---------- the page's sort contract (copies of v2.js; the harness diffs them against the page) ----------
  function getter(col) {
    if (col.kind === "rank") return row => row.rank;
    if (col.kind === "name") return row => row.name;
    if (col.kind === "value") return row => (row.values ? row.values[col.source] : undefined);
    if (col.kind === "spread") return row => row.spread;
    if (col.id === "team") return row => row.team || "Free agent";
    return row => row[col.id];
  }
  const orderer = col => (col.order ? row => (finite(row.tierOrder) ? row.tierOrder : 3) : null);

  // v2.js sortedRows(cols): missing values always sort last, never as zero; ties keep the ranking order.
  function sortRows(rows, cols, sort) {
    const out = rows.slice();
    if (!sort) return out;
    const col = cols.find(c => c.id === sort.key);
    if (!col) return out;
    const dir = sort.dir === "asc" ? 1 : -1;
    const get = getter(col);
    const order = orderer(col);
    return out.sort((a, b) => {
      if (order) return dir * (order(a) - order(b)) || a.rank - b.rank;
      const va = get(a);
      const vb = get(b);
      if (col.text) return dir * String(va).localeCompare(String(vb));
      const fa = Number.isFinite(va);
      const fb = Number.isFinite(vb);
      if (!fa && !fb) return a.rank - b.rank;
      if (!fa) return 1;
      if (!fb) return -1;
      return dir * (va - vb) || a.rank - b.rank;
    });
  }

  // v2.js header click: the same column flips direction; a new text column starts ascending, a new number column descending.
  function nextSort(sort, rankKey, col) {
    const current = sort ? sort.key : rankKey;
    const dir = current === col.id && (!sort || sort.dir === "desc") ? "asc" : "desc";
    return {key: col.id, dir: col.text && current !== col.id ? "asc" : dir};
  }
  // v2.js aria-sort: the sorted column, or the ranking series when nothing is sorted.
  function ariaSort(sort, rankKey, col) {
    const key = sort ? sort.key : rankKey;
    if (key !== col.id) return null;
    return sort && sort.dir === "asc" ? "ascending" : "descending";
  }

  // ---------- view model ----------
  function cellFor(row, col, rankKey) {
    const get = getter(col);
    const v = get(row);
    const numeric = col.kind === "value" || col.kind === "spread";
    const notes = (row.notes && row.notes[col.id]) || [];
    if (!numeric) return {col: col.id, text: v === undefined || v === null ? "" : String(v), numeric: false, notes};
    if (Number.isFinite(v)) return {col: col.id, text: fmt(v), numeric: true, missing: false, isRank: col.source === rankKey, notes};
    const reason = (row.reasons && row.reasons[col.id]) || col.unavailable || "No value for this player";
    return {col: col.id, text: "—", numeric: true, missing: true, reason, isRank: col.source === rankKey, notes};
  }

  // Header runs: one cell per run of columns in the same group, the ranking series its own "Ranking" run (v2.js renderTable).
  function headerRuns(cols, rankKey, groups) {
    const runs = [];
    cols.forEach(col => {
      const id = col.kind === "value" && col.source === rankKey ? "rank-series" : col.group || "";
      const last = runs[runs.length - 1];
      if (last && last.id === id) last.span += 1;
      else runs.push({id, span: 1});
    });
    return runs.map(run => ({...run, label: run.id === "rank-series" ? "Ranking"
      : run.id ? ((groups.find(g => g.id === run.id) || {}).label || run.id) : ""}));
  }

  function viewModel(ctx) {
    const c = ctx || {};
    const base = {name: NAME, title: c.title || "Value chart", lede: c.lede || "", settings: c.settings || "",
      basis: c.basis ? {label: c.basis.label || "", text: c.basis.text || ""} : null,
      fixture: c.fixture ? {kind: c.fixture.kind, label: c.fixture.label} : null,
      filters: {search: (c.filters && c.filters.search) || "", position: (c.filters && c.filters.position) || "ALL"},
      positions: (c.positions || []).map(p => ({value: p.value, label: p.label})),
      groups: (c.groups || []).filter(g => GROUP_ORDER.includes(g.id)).map(g => ({id: g.id, label: g.label, note: g.note || ""})),
      rankKey: c.rankKey || null, rankLabel: "",
      rankOptions: (c.rankOptions || []).map(o => ({key: o.key, label: o.label, group: o.group, reason: o.reason || null})),
      head: [], runs: [], rows: [], total: 0, more: false, meta: "", heading: "", text: "", reasons: []};
    const rankOpt = base.rankOptions.find(o => o.key === base.rankKey);
    base.rankLabel = rankOpt ? rankOpt.label : "";
    if (c.status === "loading") return {...base, state: "loading", heading: "Loading current values…"};
    if (c.status !== "ready") {
      return {...base, state: "unavailable", heading: "Values are unavailable right now.",
        text: c.reason || "No value is shown rather than a guessed one."};
    }
    const cols = (c.columns || []).slice();
    // Weekly values are never shown beside rest-of-season values: a table that would mix them is withheld.
    const horizons = [...new Set(cols.filter(col => col.kind === "value" && col.horizon).map(col => col.horizon))];
    if (horizons.length > 1) {
      return {...base, state: "mixed", heading: "These values are not shown together.",
        text: "Some columns are weekly and some are rest of season. Pick one horizon to see its values.", reasons: horizons};
    }
    base.head = cols.map(col => ({id: col.id, kind: col.kind, label: col.label, method: col.method || "", group: col.group || "", text: Boolean(col.text),
      source: col.source || null, isRank: col.kind === "value" && col.source === base.rankKey, sortable: col.kind !== "rank",
      ariaSort: ariaSort(c.sort || null, base.rankKey, col), unavailable: col.unavailable || null,
      next: col.kind === "rank" ? null : nextSort(c.sort || null, base.rankKey, col)}));
    base.runs = headerRuns(cols, base.rankKey, base.groups);
    const sorted = sortRows(c.rows || [], cols, c.sort || null);
    const shown = Number.isFinite(c.shown) ? c.shown : sorted.length;
    const rankCol = cols.find(col => col.kind === "value" && col.source === base.rankKey) || null;
    base.total = sorted.length;
    base.rows = sorted.slice(0, shown).map(row => ({key: String(row.player_key), name: row.name,
      sub: [row.pos, row.team || "Free agent", row.tier].filter(Boolean).join(" · "), posRank: row.posRank || "",
      rank: row.rank, cells: cols.map(col => cellFor(row, col, base.rankKey)),
      ranking: rankCol ? cellFor(row, rankCol, base.rankKey) : null}));
    base.more = sorted.length > shown;
    const [lo, hi] = Array.isArray(c.window) ? c.window : [null, null];
    base.meta = `${plural(sorted.length, "player")}${finite(lo) && finite(hi) ? ` · ranks ${lo}–${hi}` : ""}`;
    base.groupedCols = base.groups.map(g => ({id: g.id, label: g.label,
      cols: cols.filter(col => (col.kind === "value" || col.kind === "spread") && col.group === g.id).map(col => col.id)}))
      .filter(g => g.cols.length);
    if (!sorted.length) {
      return {...base, state: "empty", heading: "No players match.",
        text: "Source selections, weights and league settings stay as they are."};
    }
    return {...base, state: "ready"};
  }

  // ---------- DOM ----------
  function el(tag, attrs, ...kids) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined || v === false) return;
      if (k === "text") node.textContent = v;
      else if (k === "class") node.className = v;
      else node.setAttribute(k, v === true ? "" : String(v));
    });
    kids.flat().forEach(kid => { if (kid !== null && kid !== undefined && kid !== false) node.append(kid); });
    return node;
  }
  const noteList = notes => (notes.length ? el("span", {class: "vf-notes"}, ...notes.map(n => el("span", {class: "vf-note", text: n}))) : null);
  // A value as shown: the number, or "—" with its reason as a tooltip and for screen readers.
  function valueNode(cell) {
    if (!cell.missing) return el("span", {class: "vf-num", text: cell.text});
    return el("span", {class: "vf-missing", title: cell.reason, "data-missing": "true"}, "—", el("span", {class: "vf-sr", text: `: ${cell.reason}`}));
  }

  function headerCell(h, on) {
    if (h.kind === "rank") return el("th", {scope: "col", class: "vf-rank", "data-col": h.id, "aria-sort": h.ariaSort, text: h.label});
    const button = el("button", {type: "button", class: "vf-sort", "data-focus": `sort:${h.id}`, "data-col": h.id},
      el("span", {class: "vf-th1", text: h.label}),
      h.method || h.unavailable ? el("span", {class: "vf-th2", text: [h.method, h.unavailable ? "Unavailable" : ""].filter(Boolean).join(" · ")}) : null);
    if (h.unavailable) button.title = h.unavailable;
    button.addEventListener("click", () => on.sort && on.sort(h.next));
    return el("th", {scope: "col", "data-col": h.id, "data-group": h.group || null, "aria-sort": h.ariaSort,
      class: [h.kind === "value" || h.kind === "spread" ? "vf-numcol" : "", h.isRank ? "is-rank" : ""].filter(Boolean).join(" ") || null}, button);
  }

  function table(vm, on) {
    const t = el("table", {class: "vf-table", "aria-describedby": "vfMeta"},
      el("caption", {class: "vf-sr", text: `${vm.title}: ${vm.meta}${vm.rankLabel ? `, ranked by ${vm.rankLabel}` : ""}`}));
    const gr = el("tr", {class: "vf-group-row"}, ...vm.runs.map(run => el("th", {scope: "colgroup", colspan: run.span,
      class: run.id === "rank-series" ? "is-rank" : null, "data-group": run.id || null, text: run.label})));
    const hr = el("tr", {}, ...vm.head.map(h => headerCell(h, on)), el("th", {scope: "col", class: "vf-actions"}, el("span", {class: "vf-sr", text: "Details"})));
    const body = el("tbody", {}, ...vm.rows.map(r => el("tr", {"data-player-key": r.key}, ...r.cells.map((cell, i) => {
      const h = vm.head[i];
      if (h.kind === "name") {
        return el("th", {scope: "row", class: "vf-player"}, el("span", {class: "vf-name", text: r.name}),
          r.sub ? el("span", {class: "vf-sub", text: r.sub}) : null, noteList(cell.notes));
      }
      if (h.kind === "rank") return el("td", {class: "vf-rank"}, cell.text, r.posRank ? el("span", {class: "vf-sub", text: r.posRank}) : null);
      if (!cell.numeric) return el("td", {class: "vf-meta", text: cell.text});
      return el("td", {class: ["vf-numcol", cell.isRank ? "is-rank" : ""].filter(Boolean).join(" "), "data-col": cell.col}, valueNode(cell), noteList(cell.notes));
    }), el("td", {class: "vf-actions"}, detailsButton(r, on, "table")))));
    t.append(el("thead", {}, gr, hr), body);
    return el("div", {class: "vf-tablewrap"}, t);
  }

  // where: "table" or "card". Each presentation has its own focus id, so a redraw returns focus to the button the reader
  // was on and not to its hidden twin (JEG-1299: the table is display: none on phones).
  function detailsButton(r, on, where) {
    const b = el("button", {type: "button", class: "vf-btn vf-quiet", "data-focus": `open:${where}:${r.key}`, "aria-label": `Details for ${r.name}`, text: "Details"});
    b.addEventListener("click", () => on.open && on.open(r.key));
    return b;
  }

  // Phones: one card per player, the ranking value first, every other value behind a disclosure, grouped as the table is.
  function cards(vm, on) {
    const byId = Object.fromEntries(vm.head.map((h, i) => [h.id, i]));
    return el("ol", {class: "vf-cards", "aria-label": `${vm.title}: ${vm.meta}`}, ...vm.rows.map(r => {
      const rk = r.ranking;
      const groups = vm.groupedCols.map(g => el("div", {class: "vf-cgroup"}, el("h4", {text: g.label}),
        el("dl", {}, ...g.cols.flatMap(id => {
          const h = vm.head[byId[id]];
          const cell = r.cells[byId[id]];
          return [el("dt", {}, h.label, h.method ? el("span", {class: "vf-th2", text: ` ${h.method}`}) : null),
            el("dd", {class: cell.isRank ? "is-rank" : null}, valueNode(cell), noteList(cell.notes))];
        }))));
      return el("li", {class: "vf-card", "data-player-key": r.key},
        el("div", {class: "vf-card-head"}, el("span", {class: "vf-card-rank", text: String(r.rank)}),
          el("div", {class: "vf-card-who"}, el("h3", {class: "vf-name", text: r.name}), r.sub ? el("p", {class: "vf-sub", text: r.sub}) : null),
          rk ? el("p", {class: "vf-card-value"}, el("span", {class: "vf-sr", text: `${vm.rankLabel}: `}), valueNode(rk)) : null),
        noteList(rk ? rk.notes : []),
        groups.length ? el("details", {class: "vf-disclosure"}, el("summary", {}, "All values", el("span", {class: "vf-sr", text: ` for ${r.name}`})), ...groups) : null,
        detailsButton(r, on, "card"));
    }));
  }

  // Phones have no column headers, so the same sorts are offered here: "Sort by" picks a column and the order button
  // reverses it. Both hand on the header's own next sort (nextSort), so a phone sort is exactly a header click.
  function phoneSort(vm, on) {
    const cols = vm.head.filter(h => h.sortable);
    const active = vm.head.find(h => h.ariaSort);
    if (!cols.length || !active || !active.sortable) return null;
    const by = el("select", {id: "vfSortBy", "data-focus": "sortBy"},
      ...cols.map(h => el("option", {value: h.id, selected: h.id === active.id,
        text: h.method && cols.some(o => o !== h && o.label === h.label) ? `${h.label} (${h.method})` : h.label})));
    by.addEventListener("change", () => {
      const h = cols.find(c => c.id === by.value);
      if (h && on.sort) on.sort(h.next);
    });
    const asc = active.ariaSort === "ascending";
    const order = active.text ? (asc ? "A to Z" : "Z to A") : (asc ? "Lowest first" : "Highest first");
    const flip = el("button", {type: "button", class: "vf-btn vf-quiet", id: "vfSortDir", "data-focus": "sortDir",
      "aria-label": `Order: ${order}. Reverse the order`, text: order});
    flip.addEventListener("click", () => on.sort && on.sort(active.next));
    return el("div", {class: "vf-phonesort"},
      el("label", {class: "vf-field", for: "vfSortBy"}, el("span", {class: "vf-label", text: "Sort by"}), by),
      el("div", {class: "vf-field"}, el("span", {class: "vf-label", "aria-hidden": "true", text: "Order"}), flip));
  }

  function controls(vm, on) {
    const search = el("input", {type: "search", id: "vfSearch", "data-focus": "search", value: vm.filters.search,
      placeholder: "Search players…", autocomplete: "off"});
    search.addEventListener("input", () => on.filter && on.filter({search: search.value}));
    const pos = el("select", {id: "vfPosition", "data-focus": "position"},
      ...vm.positions.map(p => el("option", {value: p.value, selected: p.value === vm.filters.position, text: p.label})));
    pos.addEventListener("change", () => on.filter && on.filter({position: pos.value}));
    const rank = el("select", {id: "vfRankBy", "data-focus": "rankBy"});
    vm.rankOptions.forEach(o => {
      let group = rank.querySelector(`optgroup[data-group="${o.group}"]`);
      if (!group) {
        const g = vm.groups.find(x => x.id === o.group);
        group = el("optgroup", {label: g ? g.label : o.group, "data-group": o.group});
        rank.append(group);
      }
      group.append(el("option", {value: o.key, selected: o.key === vm.rankKey, disabled: Boolean(o.reason),
        title: o.reason, text: o.reason ? `${o.label} — ${o.reason}` : o.label}));
    });
    rank.addEventListener("change", () => on.rankBy && on.rankBy(rank.value));
    return el("div", {class: "vf-controls", role: "search", "aria-label": "Player values controls"},
      el("label", {class: "vf-field vf-search", for: "vfSearch"}, el("span", {class: "vf-label", text: "Find a player"}), search),
      el("label", {class: "vf-field", for: "vfPosition"}, el("span", {class: "vf-label", text: "Position"}), pos),
      el("label", {class: "vf-field vf-rankby", for: "vfRankBy"}, el("span", {class: "vf-label", text: "Rank by"}), rank));
  }

  // The source kinds (JEG-1212), as a neutral evidence panel: each group's existing note, behind a disclosure.
  function sourceKinds(vm) {
    if (!vm.groups.length) return null;
    return el("details", {class: "vf-evidence"}, el("summary", {}, "What each kind of value is"),
      el("dl", {}, ...vm.groups.filter(g => g.note).flatMap(g => [el("dt", {text: g.label}), el("dd", {text: g.note})])));
  }

  function render(container, vm, on) {
    const handlers = on || {};
    const kids = [el("header", {class: "vf-head"},
      el("h1", {id: "vfTitle", tabindex: "-1", text: vm.title}),
      vm.lede ? el("p", {class: "vf-lede", text: vm.lede}) : null,
      vm.settings || vm.basis ? el("p", {class: "vf-context"}, vm.settings,
        vm.basis ? el("span", {}, `${vm.settings ? " · " : ""}Value basis: `, el("b", {text: vm.basis.label})) : null) : null)];
    if (vm.fixture) {
      kids.push(el("p", {class: "vf-fixture", role: "note", "data-fixture": vm.fixture.kind},
        el("b", {text: vm.fixture.kind === "historical" ? "Historical example. " : "Synthetic example. "}),
        vm.fixture.label || "Not your league and not live values."));
    }
    if (vm.state === "loading" || vm.state === "unavailable" || vm.state === "mixed") {
      kids.push(el("section", {class: `vf-status is-${vm.state}`, role: vm.state === "loading" ? "status" : "alert",
        "aria-busy": vm.state === "loading" ? "true" : null, "aria-labelledby": "vfStatusTitle"},
        el("h2", {id: "vfStatusTitle", text: vm.heading}), vm.text ? el("p", {text: vm.text}) : null));
      container.replaceChildren(...kids);
      container.dataset.state = vm.state;
      return container;
    }
    kids.push(controls(vm, handlers));
    if (vm.rankLabel) kids.push(el("p", {class: "vf-ranked", id: "vfRanked"}, "Ranked by ", el("b", {text: vm.rankLabel})));
    const card = el("section", {class: "vf-panel", "aria-labelledby": "vfTableTitle"},
      el("div", {class: "vf-panel-head"}, el("h2", {id: "vfTableTitle", text: "All selected values"}),
        el("p", {class: "vf-meta", id: "vfMeta", role: "status", text: vm.meta})));
    if (vm.state === "empty") {
      const clear = el("button", {type: "button", class: "vf-btn", "data-focus": "clear", text: "Clear all filters"});
      clear.addEventListener("click", () => handlers.clear && handlers.clear());
      card.append(el("div", {class: "vf-empty"}, el("p", {}, el("b", {text: vm.heading})), el("p", {class: "vf-meta", text: vm.text}), clear));
    } else {
      card.append(...[table(vm, handlers), phoneSort(vm, handlers), cards(vm, handlers)].filter(Boolean));
      if (vm.more) {
        const more = el("button", {type: "button", class: "vf-btn", "data-focus": "more", text: "Show more players"});
        more.addEventListener("click", () => handlers.showMore && handlers.showMore());
        card.append(el("div", {class: "vf-foot"}, more));
      }
    }
    kids.push(card, sourceKinds(vm),
      el("p", {class: "vf-footnote"}, vm.basis && vm.basis.text ? `DDF Value is our value: ${vm.basis.text}. ` : "",
        "Every other series keeps its source's identity. A missing value shows —, never zero."));
    container.replaceChildren(...kids.filter(Boolean));
    container.dataset.state = vm.state;
    return container;
  }

  // The visible control with this focus id. A Details button whose presentation is now hidden (the window was resized
  // across 720px) falls back to the same player's button in the other one. Null when nothing visible matches.
  function visibleFocus(container, key) {
    const shown = k => [...container.querySelectorAll(`[data-focus="${CSS.escape(k)}"]`)].find(n => n.getClientRects().length > 0) || null;
    const m = /^open:(table|card):(.*)$/.exec(key);
    return shown(key) || (m ? shown(`open:${m[1] === "table" ? "card" : "table"}:${m[2]}`) : null);
  }

  // opts: {getContext() -> context, on: {sort(next), filter(change), rankBy(key), showMore(), open(playerKey), clear()}}.
  // Returns {update(), vm()}. update() redraws from getContext() and returns focus to the control that had it.
  function mount(container, opts) {
    const o = opts || {};
    container.classList.add("values-fieldnotes");
    let current = null;
    function update(focusTitle) {
      const active = container.contains(document.activeElement) ? document.activeElement : null;
      const key = active && active.dataset ? active.dataset.focus : null;
      const caret = active && active.id === "vfSearch" ? active.selectionStart : null;
      current = viewModel(o.getContext());
      render(container, current, o.on || {});
      const back = key ? visibleFocus(container, key) : null;
      if (back) back.focus();
      if (back && document.activeElement === back) {
        if (caret !== null && back.setSelectionRange) back.setSelectionRange(caret, caret);
      } else if (focusTitle || active) container.querySelector("#vfTitle").focus();   // the focused node was redrawn or is gone (Show more, all shown)
      return current;
    }
    update(false);
    return {update, vm: () => current};
  }

  const api = {NAME, GROUP_ORDER, fmt, sortRows, nextSort, ariaSort, headerRuns, viewModel, render, mount};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueValuesFieldnotes = api;
})(typeof window !== "undefined" ? window : globalThis);
