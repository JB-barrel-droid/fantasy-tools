// Name matching for the MCP tools. The rank and typo rules are the site's
// app/v2/namesearch.js (JEG-812), so "Amon Ra St Brown", "Ja'Marr" and
// "Mcafrey" resolve the same way in chat as they do on the page. The chat
// adds an ambiguity stop the page's search box does not need: a query that
// fits more than one player is not silently given to the best-valued one.

export interface Named {
  name: string;
  value?: number;
}

export type NameMatchKind = "exact" | "partial" | "fuzzy" | "ambiguous" | "none";

export interface NameMatch<T> {
  player: T | null;
  match: NameMatchKind;
  suggestions: T[];
  /** Short note for the model. Empty on an exact unique match. */
  note: string;
}

const SUFFIXES = new Set(["jr", "sr", "ii", "iii", "iv", "v"]);
const SUGGESTIONS = 5;

export function key(text: string): string {
  return String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .toLowerCase().replace(/[.'’‘`´]/g, "").replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
}

/** Words of the key. A trailing Jr/Sr/II/III/IV/V is dropped, except when the text is only that suffix. */
export function tokens(text: string): string[] {
  const words = key(text).split(" ").filter(Boolean);
  const kept = words.filter((word) => !SUFFIXES.has(word));
  return kept.length ? kept : words;
}

function wordsAnyOrder(nameWords: string[], queryWords: string[]): boolean {
  if (queryWords.length > nameWords.length) return false;
  const free = nameWords.slice();
  return queryWords.every((q) => {
    const at = free.findIndex((word) => word.startsWith(q));
    if (at < 0) return false;
    free.splice(at, 1);
    return true;
  });
}

/** 0 whole name, 1 name starts with the query, 2 a word does, 3 every query word starts a different word. */
export function rank(name: string, query: string): number | null {
  const nameWords = tokens(name);
  const queryWords = tokens(query);
  if (!nameWords.length || !queryWords.length) return null;
  const n = nameWords.join(" ");
  const q = queryWords.join(" ");
  if (n === q) return 0;
  if (n.startsWith(q)) return 1;
  const qs = q.replace(/ /g, "");
  for (let i = 0; i < nameWords.length; i++) {
    if (nameWords.slice(i).join("").startsWith(qs)) return i === 0 ? 1 : 2;
  }
  if (wordsAnyOrder(nameWords, queryWords)) return 3;
  return null;
}

function distance(a: string, b: string): number {
  const rows = a.length + 1;
  const cols = b.length + 1;
  const d = Array.from({ length: rows }, (_, i) => [i].concat(Array(cols - 1).fill(0)));
  for (let j = 1; j < cols; j++) d[0][j] = j;
  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost);
      if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
        d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
      }
    }
  }
  return d[rows - 1][cols - 1];
}

const allowedEdits = (length: number) => (length >= 7 ? 2 : length >= 4 ? 1 : 0);

export function fuzzyDistance(name: string, query: string, limit = allowedEdits(tokens(query).join("").length)): number | null {
  const qs = tokens(query).join("");
  if (!limit) return null;
  const words = tokens(name);
  let best: number | null = null;
  for (let i = 0; i < words.length; i++) {
    const run = words.slice(i).join("");
    const candidates = new Set([run, words[i]]);
    for (const cut of [qs.length, qs.length + 1]) {
      if (cut > 0 && cut < run.length) candidates.add(run.slice(0, cut));
    }
    for (const candidate of candidates) {
      if (Math.abs(candidate.length - qs.length) > limit) continue;
      const found = distance(qs, candidate);
      if (found <= limit && (best === null || found < best)) best = found;
    }
  }
  return best;
}

function byValue<T extends Named>(rows: T[]): T[] {
  return rows.slice().sort((a, b) => (b.value ?? 0) - (a.value ?? 0) || a.name.localeCompare(b.name));
}

function listNames<T extends Named>(rows: T[]): string {
  return byValue(rows).slice(0, SUGGESTIONS).map((p) => p.name).join(", ");
}

function ambiguous<T extends Named>(query: string, hits: T[]): NameMatch<T> {
  const suggestions = byValue(hits).slice(0, SUGGESTIONS);
  if (!suggestions.length) return { player: null, match: "none", suggestions: [], note: `${query}: NOT FOUND` };
  return {
    player: null,
    match: "ambiguous",
    suggestions,
    note: `${query}: AMBIGUOUS. Could be ${listNames(hits)}. Use a fuller name.`,
  };
}

/**
 * Resolve one query against the priced players.
 * An exact or unique partial match is returned. A typo with one clear nearest
 * name is returned as fuzzy. Two or more matches, or a suffix-only query
 * ("Jr"), are ambiguous and not guessed.
 */
export function matchName<T extends Named>(players: T[], query: string): NameMatch<T> {
  const q = String(query ?? "").trim();
  if (!q) return { player: null, match: "none", suggestions: [], note: "" };
  const qWords = key(q).split(" ").filter(Boolean);
  if (qWords.length === 1 && SUFFIXES.has(qWords[0])) {
    const hits = players.filter((p) => key(p.name).split(" ").includes(qWords[0]));
    return hits.length ? ambiguous(q, hits) : { player: null, match: "none", suggestions: [], note: `${q}: NOT FOUND` };
  }

  const ranked: Array<{ player: T; rank: number }> = [];
  for (const player of players) {
    const r = rank(player.name, q);
    if (r !== null) ranked.push({ player, rank: r });
  }
  if (ranked.length) {
    const best = Math.min(...ranked.map((row) => row.rank));
    const hits = ranked.filter((row) => row.rank === best).map((row) => row.player);
    if (hits.length > 1) return ambiguous(q, hits);
    const player = hits[0];
    if (best === 0) return { player, match: "exact", suggestions: [], note: "" };
    return { player, match: "partial", suggestions: [], note: `matched "${q}" to ${player.name}` };
  }

  const fuzzy: Array<{ player: T; found: number }> = [];
  for (const player of players) {
    const found = fuzzyDistance(player.name, q);
    if (found !== null) fuzzy.push({ player, found });
  }
  if (fuzzy.length) {
    const best = Math.min(...fuzzy.map((row) => row.found));
    const hits = fuzzy.filter((row) => row.found === best).map((row) => row.player);
    if (hits.length > 1) return ambiguous(q, hits);
    const player = hits[0];
    return { player, match: "fuzzy", suggestions: [], note: `interpreted "${q}" as ${player.name}` };
  }

  const close: Array<{ player: T; found: number }> = [];
  const qs = tokens(q).join("");
  if (qs.length >= 4) {
    for (const player of players) {
      const found = fuzzyDistance(player.name, q, 3);
      if (found !== null) close.push({ player, found });
    }
    close.sort((a, b) => a.found - b.found || (b.player.value ?? 0) - (a.player.value ?? 0));
  }
  const suggestions = close.slice(0, 3).map((row) => row.player);
  const note = suggestions.length
    ? `${q}: NOT FOUND. Closest: ${suggestions.map((p) => p.name).join(", ")}.`
    : `${q}: NOT FOUND`;
  return { player: null, match: "none", suggestions, note };
}

const SUFFIX_WORD = /^(jr|sr|ii|iii|iv|v)\.?$/i;

/**
 * JEG-1124: the nearest priced names for a query that matched no player, closest first
 * (ties by value). matchName's own "Closest" list when it has one; otherwise the same edit
 * distance with no cap, so a stop that asks "which player?" always has names to offer.
 */
export function closestNames<T extends Named>(players: T[], query: string, hit?: NameMatch<T>, n = 3): T[] {
  if (hit?.suggestions.length) return hit.suggestions.slice(0, n);
  const qs = tokens(query).join("");
  if (!qs) return [];
  const rows: Array<{ player: T; found: number }> = [];
  for (const player of players) {
    const found = fuzzyDistance(player.name, query, Math.max(3, qs.length));
    if (found !== null) rows.push({ player, found });
  }
  rows.sort((a, b) => a.found - b.found || (b.player.value ?? 0) - (a.player.value ?? 0));
  return rows.slice(0, n).map((row) => row.player);
}

/**
 * Split a comma-separated name list. A comma that only introduces a suffix
 * stays with the player: "Brian Thomas, Jr, Ja'Marr Chase" is two names.
 */
export function splitNames(raw: unknown): string[] {
  const parts = String(raw ?? "").split(",");
  const out: string[] = [];
  for (const part of parts) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    if (out.length && SUFFIX_WORD.test(trimmed)) out[out.length - 1] = `${out[out.length - 1]} ${trimmed.replace(/\.$/, "")}`;
    else out.push(trimmed);
  }
  return out;
}
