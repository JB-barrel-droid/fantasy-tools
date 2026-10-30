// JEG-1216: presentation only. Callers supply the lineups selected by finder.js; this module never picks starters.
(function (root) {
  "use strict";
  const ORDER = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  const id = row => row && row.player_key !== undefined && row.player_key !== null ? String(row.player_key) : null;
  const finite = n => typeof n === "number" && Number.isFinite(n);

  // Keep players selected in the same slot group in their old visual row. New players fill the remaining rows.
  // A player moving between RB/WR and FLEX is shown in the actual selected slot on both sides.
  function align(slot, before, after, count) {
    const left = (before || []).slice();
    const right = (after || []).slice();
    const size = Math.max(count || 0, left.length, right.length);
    const cells = Array.from({length: size}, (_, i) => ({slot, before: left[i] || null, after: null}));
    const remaining = new Map(right.filter(row => id(row) !== null).map(row => [id(row), row]));
    cells.forEach(cell => {
      const key = id(cell.before);
      if (key !== null && remaining.has(key)) { cell.after = remaining.get(key); remaining.delete(key); }
    });
    const newcomers = right.filter(row => remaining.has(id(row)));
    let next = 0;
    cells.forEach(cell => { if (!cell.after && next < newcomers.length) { cell.after = newcomers[next++]; remaining.delete(id(cell.after)); } });
    while (next < newcomers.length) cells.push({slot, before: null, after: newcomers[next++]});
    return cells.map(cell => ({...cell, changed: id(cell.before) !== id(cell.after)}));
  }

  // before/after are finder.lineupValue results. Bench includes unvalued players so missing prices stay visible.
  function buildRows(before, after, shape) {
    const starters = ORDER.flatMap(slot => align(slot, before && before.slots && before.slots[slot],
      after && after.slots && after.slots[slot], shape && shape[slot]));
    const bench = align("Bench", (before && (before.bench || []).concat(before.unvalued || [])) || [],
      (after && (after.bench || []).concat(after.unvalued || [])) || [], 0);
    return {starters, bench};
  }

  function node(tag, attrs, ...children) {
    const item = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (key === "text") item.textContent = value;
      else if (value !== null && value !== undefined) item.setAttribute(key, value);
    });
    item.append(...children);
    return item;
  }
  const value = (row, key) => row && row.values && finite(row.values[key]) ? row.values[key] : null;
  const amount = n => finite(n) ? n.toFixed(1) : "—";
  const signed = n => !finite(n) ? "—" : Math.abs(n) < 0.05 ? "0.0" : `${n > 0 ? "+" : "−"}${Math.abs(n).toFixed(1)}`;
  function cells(row, key) {
    const before = value(row.before, key);
    const after = value(row.after, key);
    const label = player => player ? `${player.name || player.player_key} ${value(player, key) === null ? "no value" : amount(value(player, key))}` : "empty";
    const delta = (row.before && before === null) || (row.after && after === null) ? null : (after || 0) - (before || 0);
    return node("tr", {"data-slot": row.slot, "data-changed": String(row.changed)},
      node("th", {scope: "row", text: row.slot}), node("td", {text: label(row.before)}),
      node("td", {text: label(row.after)}), node("td", {class: "num", text: signed(delta)}));
  }
  let sequence = 0;
  // Returns a DOM container with the familiar four-column table and an accessible bench expander.
  function renderTable(impact, shape, valueKey, caption) {
    const rows = buildRows(impact.before, impact.after, shape);
    const label = caption || "Best starting lineup";
    const benchId = `v2-lineup-bench-${++sequence}`;
    const head = node("thead", {}, node("tr", {}, ...["Position", "Before", "After", "Change"].map(text => node("th", {scope: "col", text}))));
    const total = (text, before, after) => node("tr", {"data-total": text.toLowerCase()}, node("th", {scope: "row", text}),
      node("td", {text: amount(before)}), node("td", {text: amount(after)}), node("td", {class: "num", text: signed(finite(before) && finite(after) ? after - before : null)}));
    const body = node("tbody", {}, ...rows.starters.map(row => cells(row, valueKey)),
      total("Starters", impact.before.starterValue, impact.after.starterValue),
      total("Bench", impact.before.benchValue, impact.after.benchValue));
    const benchBody = node("tbody", {id: benchId, class: "v2-lineup-bench-rows"}, ...rows.bench.map(row => cells(row, valueKey)));
    benchBody.hidden = true;
    const table = node("table", {class: "v2-find-lineup v2-lineup-comparison"}, node("caption", {text: label}), head, body, benchBody);
    const toggle = node("button", {type: "button", class: "v2-btn v2-lineup-bench-toggle", "aria-expanded": "false", "aria-controls": benchId,
      text: `Show bench (${rows.bench.length})`});
    toggle.addEventListener("click", () => {
      benchBody.hidden = !benchBody.hidden;
      toggle.setAttribute("aria-expanded", String(!benchBody.hidden));
      toggle.textContent = `${benchBody.hidden ? "Show" : "Hide"} bench (${rows.bench.length})`;
    });
    return node("div", {class: "v2-find-table-wrap v2-lineup-comparison-wrap"}, table, toggle);
  }
  const api = {buildRows, renderTable};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueLineupComparison = api;
})(typeof window !== "undefined" ? window : globalThis);
