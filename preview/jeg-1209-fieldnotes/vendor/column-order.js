// Trade Value v2 — saved column order for the league tables (JEG-1232). Presentation only.
//
// Pure model plus one small DOM control. Nothing here reads a value, a source, a sort, a filter or a ranking: it decides
// only which order the table's existing columns are drawn in.
//   * a unit is one movable header column: {id, label, required}. A grouped header (Market perception with its Edge and
//     Charts fair sub-columns) is one unit and moves as a whole;
//   * the table passes its units in its current (baseline) order and only the ones shown now; `known` lists every id the
//     table can ever show, so a hidden optional column keeps its saved place for when it is shown again;
//   * an untouched league has no saved order and draws the baseline order exactly;
//   * a saved order is cleaned on read: duplicates and unknown or removed ids are dropped, required columns always come
//     back, and a column the saved order does not name goes next to its baseline neighbour (deterministic).
// Saved under the workspace's ui.columnOrder[table] (the store that already keeps ui.summaryColumns), only after an
// explicit move; Reset removes it.
(function (root) {
  "use strict";

  const isObject = v => v !== null && typeof v === "object" && !Array.isArray(v);

  // A saved value from any build: an array of ids (strings, or {id} objects from a hand-edited export). Anything else is
  // treated as no saved order. Returns {ids, issues}: ids deduplicated in saved order, issues names what was dropped.
  function cleanSaved(saved, known) {
    const issues = [];
    if (saved === null || saved === undefined) return {ids: null, issues};
    if (!Array.isArray(saved)) return {ids: null, issues: ["not-a-list"]};
    const knownSet = new Set(known);
    const seen = new Set();
    const ids = [];
    saved.forEach(item => {
      const id = typeof item === "string" ? item : isObject(item) && typeof item.id === "string" ? item.id : null;
      if (id === null) { issues.push("bad-entry"); return; }
      if (seen.has(id)) { issues.push(`duplicate:${id}`); return; }
      seen.add(id);
      if (!knownSet.has(id)) { issues.push(`unknown:${id}`); return; }
      ids.push(id);
    });
    return {ids, issues};
  }

  // Puts every baseline id that `list` lacks next to its nearest baseline neighbour already in `list`: after the closest
  // earlier one, else before the closest later one. Missing ids are placed in baseline order, so two new neighbours keep
  // their own order.
  function insertMissing(list, baseline) {
    const out = list.slice();
    baseline.forEach((id, i) => {
      if (out.includes(id)) return;
      for (let j = i - 1; j >= 0; j -= 1) {
        const at = out.indexOf(baseline[j]);
        if (at !== -1) { out.splice(at + 1, 0, id); return; }
      }
      for (let j = i + 1; j < baseline.length; j += 1) {
        const at = out.indexOf(baseline[j]);
        if (at !== -1) { out.splice(at, 0, id); return; }
      }
      out.push(id);
    });
    return out;
  }

  // units: the columns shown now, baseline order. saved: the stored value. known: every id the table can show (defaults to
  // the units). Returns {order: ids of the shown units, full: the cleaned list to keep (hidden known ids included),
  // explicit: whether a saved order applies, issues}.
  function reconcile(saved, units, known) {
    const baseline = units.map(u => u.id);
    const all = known && known.length ? Array.from(new Set(known.concat(baseline))) : baseline;
    const clean = cleanSaved(saved, all);
    if (!clean.ids) return {order: baseline, full: null, explicit: false, issues: clean.issues};
    const full = insertMissing(clean.ids, baseline);
    const shown = new Set(baseline);
    return {order: full.filter(id => shown.has(id)), full, explicit: true, issues: clean.issues};
  }

  const sameOrder = (a, b) => a.length === b.length && a.every((id, i) => id === b[i]);
  const isBaseline = (order, units) => sameOrder(order, units.map(u => u.id));

  // The units in draw order.
  function applyOrder(units, order) {
    const byId = new Map(units.map(u => [u.id, u]));
    return order.map(id => byId.get(id)).filter(Boolean);
  }

  // Moves one shown unit by delta (-1 earlier, +1 later) inside `full` (which may hold hidden ids). The move skips
  // hidden ids, so one press always moves one visible place. Returns {full, order, moved, index, total}.
  function move(full, order, id, delta) {
    const at = order.indexOf(id);
    const target = at + delta;
    if (at === -1 || target < 0 || target >= order.length) return {full: full.slice(), order: order.slice(), moved: false, index: at, total: order.length};
    const swapWith = order[target];
    const next = full.slice();
    const a = next.indexOf(id);
    const b = next.indexOf(swapWith);
    next[a] = swapWith;
    next[b] = id;
    const shown = new Set(order);
    const nextOrder = next.filter(x => shown.has(x));
    return {full: next, order: nextOrder, moved: true, index: target, total: order.length};
  }

  // What a screen reader hears after a press.
  function moveMessage(units, result, id, delta) {
    const unit = units.find(u => u.id === id);
    const name = unit ? unit.label : id;
    if (!result.moved) return `${name} is already ${delta < 0 ? "first" : "last"}.`;
    return `${name} moved to position ${result.index + 1} of ${result.total}.`;
  }

  // The workspace ui patch that stores one table's order (other tables' orders are kept). value null removes it.
  function savePatch(ui, table, value) {
    const prev = ui && isObject(ui.columnOrder) ? ui.columnOrder : {};
    const next = {...prev};
    if (value === null) delete next[table];
    else next[table] = value.slice();
    return {columnOrder: next};
  }
  const savedOf = (ui, table) => (ui && isObject(ui.columnOrder) ? ui.columnOrder[table] : undefined);

  // The trade opportunities table's movable units, in the order it draws them today (league.js renderOpps). Labels of the
  // sortable columns come from the table's own column list (O.OPP_COLUMNS); Trade and the two fit columns are not
  // sortable and keep their header text. Every base column is required: only the optional team summary columns can be
  // hidden, through the existing "Add team summary columns" choice. Market perception is one unit over Edge and Charts fair.
  const OPP_BASE = ["opponent", "trade", "capture", "proj", "ours", "market", "theirs", "overall", "rank"];
  const OPP_PLAIN = {trade: "Trade", ours: "Our team fit", theirs: "Their team fit"};
  function opportunityUnits(oppColumns, optional) {
    const byId = new Map(oppColumns.map(c => [c.id, c]));
    const base = OPP_BASE.map(id => ({id, label: OPP_PLAIN[id] || byId.get(id).label, required: true, sub: id === "market" ? ["market", "fair"] : null}));
    return base.concat((optional || []).map(c => ({id: c.id, label: c.label, required: false, sub: null})));
  }
  // Every id the opportunities table can show: the base columns and every optional summary column, both sides.
  const opportunityKnown = fields => OPP_BASE.concat(["mine", "theirs"].flatMap(side => fields.map(f => `summary:${side}:${f.id}`)));

  // ---------- the control ----------
  // doc: a document. opts: {id, units (draw order), baseline (ids), onMove(id, delta), onReset(), open, title, help}.
  // A list with Move up / Move down per column (real buttons, so Tab, Enter and Space work and no pointer or drag is
  // needed), each named for its column and position. The end buttons stay focusable with aria-disabled, so focus never
  // drops when a column reaches the end; pressing one announces "already first". The page re-renders after a move and
  // calls focusMove() to put focus back on the same button.
  function renderControl(doc, opts) {
    const make = (tag, attrs, ...kids) => {
      const node = doc.createElement(tag);
      Object.entries(attrs || {}).forEach(([k, v]) => {
        if (v === null || v === undefined || v === false) return;
        if (k === "text") node.textContent = v;
        else node.setAttribute(k, v === true ? "" : String(v));
      });
      kids.filter(k => k !== null && k !== undefined).forEach(k => node.append(k));
      return node;
    };
    const id = opts.id;
    const units = opts.units;
    const total = units.length;
    const box = make("details", {id, class: "v2-lg-field-options v2-colorder", open: Boolean(opts.open)},
      make("summary", {text: opts.title || "Column order"}),
      make("p", {class: "v2-meta", id: `${id}Help`, text: opts.help || "Move a column up to show it earlier: further left in the table, higher on phone cards. Saved on this device with this league."}));
    const list = make("ol", {class: "v2-colorder-list", "aria-describedby": `${id}Help`});
    units.forEach((u, i) => {
      const pos = `${id}Pos-${u.id}`;
      const btn = (dir, glyph, word) => {
        const edge = dir === "up" ? i === 0 : i === total - 1;
        const b = make("button", {type: "button", class: "v2-btn v2-colorder-move", "data-move": dir, "data-column": u.id,
          "aria-label": `Move ${u.label} ${word}`, "aria-describedby": pos, "aria-disabled": edge ? "true" : null},
          make("span", {"aria-hidden": "true", text: glyph}), ` ${word[0].toUpperCase()}${word.slice(1)}`);
        b.addEventListener("click", () => opts.onMove(u.id, dir === "up" ? -1 : 1));
        return b;
      };
      list.append(make("li", {class: "v2-colorder-item", "data-column": u.id},
        make("span", {class: "v2-colorder-name", text: u.label}),
        make("span", {class: "v2-meta v2-colorder-pos", id: pos, text: `${i + 1} of ${total}`}),
        make("span", {class: "v2-colorder-btns"}, btn("up", "↑", "up"), btn("down", "↓", "down"))));
    });
    box.append(list);
    const reset = make("button", {type: "button", class: "v2-btn", id: `${id}Reset`, hidden: sameOrder(units.map(u => u.id), opts.baseline)}, "Reset column order");
    reset.addEventListener("click", () => opts.onReset());
    box.append(make("div", {class: "v2-ctoolbar"}, reset));
    return box;
  }
  // After a re-render: focus the button the reader pressed, or the column's other button when it is the only one left
  // that does something; after Reset, the summary.
  function focusMove(container, controlId, columnId, dir) {
    const box = container.querySelector(`#${controlId}`);
    if (!box) return null;
    const target = columnId ? box.querySelector(`button[data-column="${columnId}"][data-move="${dir}"]`) : box.querySelector("summary");
    if (target) target.focus();
    return target;
  }

  const api = {cleanSaved, insertMissing, reconcile, sameOrder, isBaseline, applyOrder, move, moveMessage, savePatch, savedOf,
    OPP_BASE, opportunityUnits, opportunityKnown, renderControl, focusMove};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueColumnOrder = api;
})(typeof window !== "undefined" ? window : globalThis);
