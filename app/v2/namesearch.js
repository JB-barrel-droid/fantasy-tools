// Trade Value v2 — forgiving player-name search (JEG-812).
//
// Pure functions, no DOM. One matcher for every name box on the page, so
// "Amon Ra", "JaMarr", "Ja’Marr" (curly apostrophe), "st-brown" and the typo
// "Mcafrey" all find the player they mean.
//
//   key(text)            lower case, accents, apostrophes (straight, curly,
//                        backtick) and periods dropped, every other run of
//                        punctuation or spaces becomes one space.
//   rank(name, query)    0 exact name, 1 name starts with the query,
//                        2 a word starts with the query, 3 the query sits
//                        inside the name, 4 the query matches once spaces are
//                        ignored ("amon ra" / "jamarr"), null for no match.
//                        Never fuzzy.
//   search(rows, query)  rows whose name matches, best rank first (stable
//                        within a rank, so the caller's order breaks ties).
//                        Only when nothing matches by rank does it fall back
//                        to a typo-tolerant match: up to 1 edit for 4 to 6
//                        letters, 2 for 7 or more, against any word run of
//                        the name or its start. No fuzzy under 4 letters.
//   filter(rows, query)  the same matches in the rows' own order.
(function (root) {
  "use strict";

  const key = text => String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[.'’‘`´]/g, "").replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();

  const squash = text => text.replace(/ /g, "");

  function rank(name, query) {
    const n = key(name);
    const q = key(query);
    if (!q || !n) return null;
    if (n === q) return 0;
    if (n.startsWith(q)) return 1;
    if (n.includes(` ${q}`)) return 2;
    if (n.includes(q)) return 3;
    const ns = squash(n);
    const qs = squash(q);
    return qs && ns.includes(qs) ? 4 : null;
  }

  // Optimal string alignment distance (insert, delete, replace, swap of two neighbours).
  function distance(a, b) {
    const rows = a.length + 1;
    const cols = b.length + 1;
    const d = Array.from({length: rows}, (_, i) => [i].concat(Array(cols - 1).fill(0)));
    for (let j = 1; j < cols; j++) d[0][j] = j;
    for (let i = 1; i < rows; i++) {
      for (let j = 1; j < cols; j++) {
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
    return d[rows - 1][cols - 1];
  }

  const allowedEdits = length => (length >= 7 ? 2 : length >= 4 ? 1 : 0);

  // Smallest edit distance between the squashed query and the start of any word run of the name
  // (a whole run, or a run cut to the query's length), or null when it is over the allowance.
  function fuzzyDistance(name, query) {
    const qs = squash(key(query));
    const limit = allowedEdits(qs.length);
    if (!limit) return null;
    const words = key(name).split(" ");
    let best = null;
    for (let i = 0; i < words.length; i++) {
      const run = words.slice(i).join("");
      const whole = words.slice(i, i + 1).join("");
      const candidates = new Set([run, whole]);
      for (const cut of [qs.length - 1, qs.length, qs.length + 1]) if (cut > 0 && cut < run.length) candidates.add(run.slice(0, cut));
      for (const candidate of candidates) {
        if (Math.abs(candidate.length - qs.length) > limit) continue;
        const found = distance(qs, candidate);
        if (found <= limit && (best === null || found < best)) best = found;
      }
    }
    return best;
  }

  function search(rows, query, nameOf = row => row && row.name) {
    const ranked = [];
    rows.forEach((row, index) => {
      const r = rank(nameOf(row), query);
      if (r !== null) ranked.push({row, r, index});
    });
    if (ranked.length) return ranked.sort((a, b) => a.r - b.r || a.index - b.index).map(item => item.row);
    const fuzzy = [];
    rows.forEach((row, index) => {
      const found = fuzzyDistance(nameOf(row), query);
      if (found !== null) fuzzy.push({row, found, index});
    });
    return fuzzy.sort((a, b) => a.found - b.found || a.index - b.index).map(item => item.row);
  }

  // The same matches, in the caller's own order (tables keep their rank order).
  function filter(rows, query, nameOf) {
    const hits = new Set(search(rows, query, nameOf));
    return rows.filter(row => hits.has(row));
  }

  const api = {key, rank, distance, fuzzyDistance, search, filter};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueNameSearch = api;
})(typeof window !== "undefined" ? window : globalThis);
