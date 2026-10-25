// Trade Value v2 — one sorting engine for both league tables (JEG-1021 section 6).
//
// Pure functions, no DOM. The team summary and the trade opportunities tables use this same comparator.
//   * a column is {id, label, type: "number" | "text", first: "asc" | "desc", get(row)}; first is the direction a first click sorts;
//   * a blank (null, undefined, NaN, "", "—") sorts last in BOTH directions;
//   * the sort is stable and the tie-break chain is explicit, so the same inputs always give the same order.
(function (root) {
  "use strict";

  const isBlank = value => value === null || value === undefined || value === "" || value === "—" || (typeof value === "number" && !Number.isFinite(value));
  const textOf = value => String(value).toLocaleLowerCase();
  // Compares two non-blank values of a column type, ascending.
  function compareValues(a, b, type) {
    if (type === "text") return textOf(a) < textOf(b) ? -1 : textOf(a) > textOf(b) ? 1 : 0;
    return a < b ? -1 : a > b ? 1 : 0;
  }
  // rows: any array. columns: the table's column list. state: {col, dir}. ties: [{get, type, dir}] applied in order after the
  // primary column (dir "asc" | "desc" each). Returns a new array; rows are not changed.
  function sortRows(rows, columns, state, ties) {
    const column = columns.find(c => c.id === state.col);
    if (!column) return rows.slice();
    const sign = state.dir === "desc" ? -1 : 1;
    const decorated = rows.map((row, index) => ({row, index, value: column.get(row)}));
    const chain = (a, b) => {
      for (const tie of ties || []) {
        const x = tie.get(a.row);
        const y = tie.get(b.row);
        const xb = isBlank(x);
        const yb = isBlank(y);
        if (xb || yb) { if (xb !== yb) return xb ? 1 : -1; continue; }
        const c = compareValues(x, y, tie.type || "number") * (tie.dir === "desc" ? -1 : 1);
        if (c) return c;
      }
      return a.index - b.index;
    };
    decorated.sort((a, b) => {
      const ab = isBlank(a.value);
      const bb = isBlank(b.value);
      if (ab || bb) return ab === bb ? chain(a, b) : ab ? 1 : -1;   // blanks last, whichever way the column runs
      const c = compareValues(a.value, b.value, column.type) * sign;
      return c || chain(a, b);
    });
    return decorated.map(item => item.row);
  }
  // A click on a header: the same column flips direction; another column starts in its natural first direction.
  function nextState(state, id, columns) {
    if (state && state.col === id) return {col: id, dir: state.dir === "asc" ? "desc" : "asc"};
    const column = columns.find(c => c.id === id);
    return {col: id, dir: column ? column.first : "desc"};
  }
  const ariaSort = (state, id) => (state && state.col === id ? (state.dir === "asc" ? "ascending" : "descending") : "none");
  const sameState = (a, b) => Boolean(a) && Boolean(b) && a.col === b.col && a.dir === b.dir;
  // Saved state is trusted only when it names a column of this table and a direction.
  const validState = (state, columns) => Boolean(state) && columns.some(c => c.id === state.col) && (state.dir === "asc" || state.dir === "desc");
  const dirWord = (column, dir) => {
    if (column.type === "text") return dir === "asc" ? "A to Z" : "Z to A";
    if (column.rank) return dir === "asc" ? "best first" : "worst first";
    return dir === "desc" ? "highest first" : "lowest first";
  };
  const announce = (column, dir) => `Sorted by ${column.label.toLowerCase()}, ${dirWord(column, dir)}.`;

  const api = {isBlank, compareValues, sortRows, nextState, ariaSort, sameState, validState, announce, dirWord};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueTableSort = api;
})(typeof window !== "undefined" ? window : globalThis);
