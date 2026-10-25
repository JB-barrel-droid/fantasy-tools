// Trade Value v2 — forgiving player-name search (JEG-812, JEG-861).
//
// Pure functions, no DOM. One matcher for every name box on the page (Player
// values, Trade targets, Risers, Compare a trade, Find a trade rosters and the
// unpriced lists), so "Amon Ra", "JaMarr", "Ja’Marr" (curly apostrophe),
// "st-brown", "Nacua Puka" (reversed) and the typo "Mcafrey" all find the
// player they mean, and a short query never pulls in a name it merely contains.
//
//   key(text)            lower case, accents, apostrophes (straight, curly,
//                        backtick) and periods dropped, every other run of
//                        punctuation or spaces becomes one space.
//   tokens(text)         key(text) split into words, with a trailing Jr., Sr.,
//                        II, III, IV or V dropped (kept only when the text is
//                        nothing else).
//   rank(name, query)    0 the whole name, 1 the name starts with the query,
//                        2 a word of the name starts with the query (spaces in
//                        the query are optional: "amonra", "jamarr", "stbrown"),
//                        3 every query word starts a different word of the
//                        name, in any order ("nacua puka", "j chase"),
//                        null for no match. Every match is a word-start
//                        (prefix) match: "nac" never finds Arizona Cardinals.
//                        Never fuzzy.
//   search(rows, query)  rows whose name matches, best rank first (stable
//                        within a rank, so the caller's order breaks ties).
//                        Only when nothing matches by rank does it fall back
//                        to a typo-tolerant match: the spaces-dropped query
//                        against a whole word, the rest of the name from a
//                        word start, or that run cut to the query's length
//                        (or one longer), within 1 edit for 4 to 6 letters and
//                        2 for 7 or more. No fuzzy under 4 letters. A name
//                        can only be found this way, never invented.
//   filter(rows, query)  the same matches in the rows' own order.
(function (root) {
  "use strict";

  const key = text => String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[.'’‘`´]/g, "").replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();

  const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);

  // Words of the key, generational suffixes dropped ("Brian Thomas Jr." and "brian thomas" are the
  // same tokens). A text that is only a suffix keeps it, so the query "jr" is not an empty query.
  function tokens(text) {
    const words = key(text).split(" ").filter(Boolean);
    const kept = words.filter(word => !SUFFIXES.has(word));
    return kept.length ? kept : words;
  }

  // Every query word is a prefix of its own name word (no name word used twice), in any order.
  function wordsAnyOrder(nameWords, queryWords) {
    if (queryWords.length > nameWords.length) return false;
    const free = nameWords.slice();
    return queryWords.every(q => {
      const at = free.findIndex(word => word.startsWith(q));
      if (at < 0) return false;
      free.splice(at, 1);
      return true;
    });
  }

  function rank(name, query) {
    const nameWords = tokens(name);
    const queryWords = tokens(query);
    if (!nameWords.length || !queryWords.length) return null;
    const n = nameWords.join(" ");
    const q = queryWords.join(" ");
    if (n === q) return 0;
    if (n.startsWith(q)) return 1;
    // A word start, spaces in the query optional: "st brown", "stbrown", "amonra", "jamarr".
    const qs = q.replace(/ /g, "");
    for (let i = 0; i < nameWords.length; i++) {
      if (nameWords.slice(i).join("").startsWith(qs)) return i === 0 ? 1 : 2;
    }
    if (wordsAnyOrder(nameWords, queryWords)) return 3;
    return null;
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

  // The most edits a typo may be from the name: none under 4 letters, 1 for 4 to 6, 2 for 7 or more.
  const allowedEdits = length => (length >= 7 ? 2 : length >= 4 ? 1 : 0);

  // Smallest edit distance between the spaces-dropped query and a whole word of the name, the rest of
  // the name from a word start, or that run cut to the query's length or one longer (a typo in a
  // prefix); null when every candidate is over the allowance. Never a run cut shorter than the query,
  // so "kelse" is Travis Kelce (1 edit) and not Keleki Latu ("kele", a 4-letter cut).
  function fuzzyDistance(name, query) {
    const qs = tokens(query).join("");
    const limit = allowedEdits(qs.length);
    if (!limit) return null;
    const words = tokens(name);
    let best = null;
    for (let i = 0; i < words.length; i++) {
      const run = words.slice(i).join("");
      const candidates = new Set([run, words[i]]);
      for (const cut of [qs.length, qs.length + 1]) if (cut > 0 && cut < run.length) candidates.add(run.slice(0, cut));
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

  // JEG-900: the ARIA combobox pattern for a name box whose matches are `li > button` in a list the caller fills
  // and shows or hides. DOM only, browser only. The input keeps focus; ArrowDown / ArrowUp move aria-activedescendant
  // through the enabled results, Enter picks the highlighted one (else the caller's own Enter handling runs), and a
  // polite status line says how many players match. The caller's code is unchanged: a MutationObserver on the list
  // watches what it renders.
  function combobox(input, list) {
    if (!input || !list || input.getAttribute("role") === "combobox" && input._combobox) return;
    input._combobox = true;
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-haspopup", "listbox");
    input.setAttribute("aria-controls", list.id);
    input.setAttribute("aria-expanded", "false");
    list.setAttribute("role", "listbox");
    if (!list.hasAttribute("aria-label")) list.setAttribute("aria-label", "Matching players");
    const status = document.createElement("div");
    status.className = "v2-sr";
    status.id = `${list.id}Count`;
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    list.insertAdjacentElement("afterend", status);
    let active = -1;
    const buttons = () => [...list.querySelectorAll("li:not(.is-empty) > button")];
    const enabled = () => buttons().filter(b => !b.disabled);
    const setActive = at => {
      const all = enabled();
      buttons().forEach(b => { b.classList.remove("is-active"); b.setAttribute("aria-selected", "false"); });
      active = at;
      const b = all[at];
      if (!b) { input.removeAttribute("aria-activedescendant"); return; }
      b.classList.add("is-active");
      b.setAttribute("aria-selected", "true");
      input.setAttribute("aria-activedescendant", b.id);
      if (b.scrollIntoView) b.scrollIntoView({block: "nearest"});
    };
    let n = 0;
    const sync = () => {
      const all = buttons();
      all.forEach(b => {
        b.setAttribute("role", "option");
        b.tabIndex = -1;
        if (!b.id) b.id = `${list.id}Opt${++n}`;
        b.parentElement.setAttribute("role", "presentation");
      });
      const open = !list.hidden;
      input.setAttribute("aria-expanded", String(open));
      active = -1;
      input.removeAttribute("aria-activedescendant");
      const empty = !!list.querySelector("li.is-empty");
      status.textContent = !open ? "" : all.length && !empty ? `${all.length} player${all.length === 1 ? "" : "s"} match` : "No players match";
    };
    new MutationObserver(sync).observe(list, {childList: true, attributes: true, attributeFilter: ["hidden"]});
    // Capture phase: runs before the caller's own Enter / Escape handler on the same input.
    input.addEventListener("keydown", event => {
      if (list.hidden) return;
      const all = enabled();
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        if (!all.length) return;
        event.preventDefault();
        setActive(event.key === "ArrowDown" ? (active + 1) % all.length : (active - 1 + all.length) % all.length);
      } else if (event.key === "Enter" && all[active]) {
        event.preventDefault();
        event.stopImmediatePropagation();
        all[active].click();
      }
    }, true);
  }

  const api = {key, tokens, rank, distance, fuzzyDistance, search, filter};
  if (typeof document !== "undefined") api.combobox = combobox;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueNameSearch = api;
})(typeof window !== "undefined" ? window : globalThis);
