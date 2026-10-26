// JEG-1025: the DDF state, one object that the site and the MCP endpoint both read and write.
// Two encodings: URL query (extends the shared-trade-link parameters) and a pasteable text block.
// Spec: docs/design/llm-site-state.md. Plain script; also loads under node/Deno (UMD).
(function (root, factory) {
  if (typeof module === "object" && module.exports) module.exports = factory();
  else root.DDFState = factory();
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const VERSION = 1;
  const SCORINGS = ["standard", "half_ppr", "ppr"];
  const TEAMS = [8, 10, 12, 14];
  const ROSTER_CODES = [["QB", "QB"], ["RB", "RB"], ["WR", "WR"], ["TE", "TE"], ["FLEX", "FLEX"], ["SUPERFLEX", "SF"], ["BENCH", "BN"]];
  const SHARE_POS = ["QB", "RB", "WR", "TE"];
  const VIEWS = ["compare", "targets", "finder"];
  const LISTS = ["give", "get", "mine", "theirs"];
  const MAX_LIST = 40;
  const MAX_NAME = 60;

  const isKey = k => typeof k === "string" ? /^\d{1,9}$/.test(k) : Number.isInteger(k) && k >= 0 && k < 1e9;
  const cleanName = n => typeof n === "string" ? n.replace(/[\u0000-\u001f]/g, " ").trim().slice(0, MAX_NAME) : "";

  // A player entry is {key, name?}. A name-only entry (an LLM does not know keys) is {name}; the
  // site resolves it with the roster-paste matcher and reports what it could not match.
  function cleanPlayer(p, warnings, where) {
    if (typeof p === "string") p = isKey(p) ? {key: p} : {name: p};
    if (typeof p === "number") p = {key: p};
    if (!p || typeof p !== "object") { warnings.push(`${where}: entry dropped`); return null; }
    const out = {};
    if (p.key !== undefined && p.key !== null && p.key !== "") {
      if (!isKey(p.key)) { warnings.push(`${where}: bad player key dropped`); } else out.key = String(p.key);
    }
    const name = cleanName(p.name);
    if (name) out.name = name;
    if (out.key === undefined && !out.name) { warnings.push(`${where}: entry without key or name dropped`); return null; }
    return out;
  }
  function cleanList(list, warnings, where) {
    if (!Array.isArray(list)) { warnings.push(`${where}: not a list, dropped`); return null; }
    const seen = new Set();
    const out = [];
    list.forEach(p => {
      const c = cleanPlayer(p, warnings, where);
      if (!c) return;
      const id = c.key !== undefined ? `k${c.key}` : `n${c.name.toLowerCase()}`;
      if (!seen.has(id)) { seen.add(id); out.push(c); }
    });
    if (out.length > MAX_LIST) { warnings.push(`${where}: only the first ${MAX_LIST} kept`); out.length = MAX_LIST; }
    return out;
  }

  // Validate and normalise anything into a state. Unknown fields are ignored. A bad field is dropped
  // with a warning; a bad `league` field never half-applies (see cleanLeague). Returns {state, warnings}.
  function normalize(input) {
    const warnings = [];
    const state = {v: VERSION};
    if (!input || typeof input !== "object" || Array.isArray(input)) return {state: null, warnings: ["not a DDF state"]};
    if (input.v !== undefined && Number(input.v) > VERSION) warnings.push(`state version ${input.v} is newer than this reader (${VERSION}); known fields read`);
    const league = cleanLeague(input.league, warnings);
    if (league) state.league = league;
    const work = cleanWork(input.work, warnings);
    if (work) state.work = work;
    if (Array.isArray(input.sources)) {
      const sources = input.sources.filter(s => typeof s === "string" && /^[a-z0-9_]{1,24}$/.test(s));
      if (sources.length) state.sources = sources;
    }
    if (typeof input.asOf === "string" && /^\d{4}-\d{2}-\d{2}/.test(input.asOf)) state.asOf = input.asOf.slice(0, 10);
    if (!state.league && !state.work) return {state: null, warnings: warnings.concat("no usable league or work in the state")};
    return {state, warnings};
  }

  // League settings apply all or nothing: a bad scoring or team count drops the whole league section
  // (a partial league would silently price a different league than the sender meant).
  function cleanLeague(l, warnings) {
    if (l === undefined || l === null) return null;
    if (typeof l !== "object" || Array.isArray(l)) { warnings.push("league: not an object, dropped"); return null; }
    const out = {};
    if (!SCORINGS.includes(l.scoring)) { warnings.push("league: scoring missing or unknown, league dropped"); return null; }
    out.scoring = l.scoring;
    if (l.teams !== undefined) {
      if (!TEAMS.includes(Number(l.teams))) { warnings.push("league: teams must be 8, 10, 12 or 14, league dropped"); return null; }
      out.teams = Number(l.teams);
    }
    if (l.roster !== undefined) {
      const roster = {};
      for (const [key] of ROSTER_CODES) {
        if (l.roster && l.roster[key] !== undefined) {
          const n = Number(l.roster[key]);
          if (!Number.isInteger(n) || n < 0 || n > 20) { warnings.push(`league: roster ${key} out of range, league dropped`); return null; }
          roster[key] = n;
        }
      }
      if (Object.keys(roster).length) out.roster = roster;
    }
    if (l.shares !== undefined) {
      const shares = {};
      const ok = SHARE_POS.every(pos => { const n = Number(l.shares && l.shares[pos]); if (!(n >= 0 && n <= 1)) return false; shares[pos] = Math.round(n * 1000) / 1000; return true; });
      if (ok && Math.abs(SHARE_POS.reduce((t, pos) => t + shares[pos], 0) - 1) < 0.01) out.shares = shares;
      else warnings.push("league: shares need all four positions, each 0 to 1, totalling 1; shares ignored");
    }
    if (l.bso !== undefined && l.bso !== null) {
      const n = Number(l.bso);
      if (Number.isFinite(n)) out.bso = Math.round(Math.min(0.30, Math.max(0.01, n)) * 1000) / 1000;
    }
    if (["recent", "all"].includes(l.inj)) out.inj = l.inj;
    if ([0.5, 1, 1.5].includes(Number(l.conf))) out.conf = Number(l.conf);
    const w = l.weeks;
    if (w && typeof w === "object") {
      const weeks = {};
      if (Number.isInteger(w.regend) && w.regend >= 1 && w.regend <= 18) weeks.regend = w.regend;
      if (Array.isArray(w.playoffs) && w.playoffs.length === 2 && w.playoffs.every(n => Number.isInteger(n) && n >= 1 && n <= 22) && w.playoffs[0] <= w.playoffs[1]) weeks.playoffs = w.playoffs;
      if (["season", "regular", "playoffs"].includes(w.optimize)) weeks.optimize = w.optimize;
      if (Number.isInteger(w.week) && w.week >= 1 && w.week <= 22) weeks.week = w.week;
      if (Object.keys(weeks).length) out.weeks = weeks;
    }
    return out;
  }

  function cleanWork(w, warnings) {
    if (w === undefined || w === null) return null;
    if (typeof w !== "object" || Array.isArray(w)) { warnings.push("work: not an object, dropped"); return null; }
    const out = {};
    if (VIEWS.includes(w.view)) out.view = w.view;
    LISTS.forEach(name => {
      if (w[name] === undefined) return;
      const list = cleanList(w[name], warnings, `work.${name}`);
      if (list && list.length) out[name] = list;
    });
    if (w.target !== undefined) {
      const t = cleanPlayer(w.target, warnings, "work.target");
      if (t) out.target = t;
    }
    return Object.keys(out).length ? out : null;
  }

  // ---------- URL query ----------
  // Legacy names stay: give, get, scoring, roster (QB1.RB2.WR3.TE1.FLEX1.SF0.BN6), shares (QB0.100_RB0.400_...),
  // bso, inj, conf, regend, playoffs (lo-hi), optimize, week, and the old bench= (0.150 = the old default).
  // New: v, teams, view, mine, theirs, target, src. Player lists are comma-separated keys; a name-only
  // entry is n:<name>. The name is percent-encoded once, so a space is %20 and not %2520. Commas,
  // ampersands and equals are encoded again so URLSearchParams' one decode does not split the list.
  const encodeName = name => encodeURIComponent(name).replace(/%2C/gi, "%252C").replace(/%26/gi, "%2526").replace(/%3D/gi, "%253D");
  const listToParam = list => list.map(p => p.key !== undefined ? encodeURIComponent(p.key) : "n:" + encodeName(p.name)).join(",");
  const paramToList = value => String(value || "").split(",").map(s => s.trim()).filter(Boolean).map(s => {
    if (s.startsWith("n:")) { let n; try { n = decodeURIComponent(s.slice(2)); } catch (e) { n = ""; } return {name: n}; }
    let k; try { k = decodeURIComponent(s); } catch (e) { k = ""; }
    return isKey(k) ? {key: k} : {name: k};
  });

  function encodeQuery(state) {
    const {state: s} = normalize(state);
    if (!s) return "";
    const p = [];
    const w = s.work || {};
    if (w.give) p.push("give=" + listToParam(w.give));
    if (w.get) p.push("get=" + listToParam(w.get));
    if (w.mine) p.push("mine=" + listToParam(w.mine));
    if (w.theirs) p.push("theirs=" + listToParam(w.theirs));
    if (w.target) p.push("target=" + listToParam([w.target]));
    if (w.view) p.push("view=" + w.view);
    const l = s.league;
    if (l) {
      p.push("scoring=" + l.scoring);
      if (l.teams) p.push("teams=" + l.teams);
      if (l.roster) p.push("roster=" + ROSTER_CODES.filter(([key]) => l.roster[key] !== undefined).map(([key, code]) => code + l.roster[key]).join("."));
      if (l.shares) p.push("shares=" + SHARE_POS.map(pos => pos + l.shares[pos].toFixed(3)).join("_"));
      if (l.weeks) {
        if (l.weeks.regend !== undefined) p.push("regend=" + l.weeks.regend);
        if (l.weeks.playoffs) p.push("playoffs=" + l.weeks.playoffs.join("-"));
        if (l.weeks.optimize) p.push("optimize=" + l.weeks.optimize);
        if (l.weeks.week !== undefined) p.push("week=" + l.weeks.week);
      }
      if (l.inj) p.push("inj=" + l.inj);
      if (l.conf !== undefined) p.push("conf=" + l.conf);
      if (l.bso !== undefined) p.push("bso=" + l.bso.toFixed(3));
    }
    if (s.sources) p.push("src=" + s.sources.join(","));
    p.push("v=" + VERSION);
    return p.join("&");
  }

  function decodeQuery(query) {
    const params = new URLSearchParams(String(query || "").replace(/^[#?]+/, ""));
    const warnings = [];
    const raw = {v: Number(params.get("v") || VERSION)};
    const work = {};
    ["give", "get", "mine", "theirs"].forEach(name => { if (params.has(name)) work[name] = paramToList(params.get(name)); });
    if (params.has("target")) work.target = paramToList(params.get("target"))[0];
    if (params.has("view")) work.view = params.get("view");
    if (Object.keys(work).length) raw.work = work;
    if (params.has("scoring")) {
      const league = {scoring: params.get("scoring")};
      if (params.has("teams")) league.teams = Number(params.get("teams"));
      if (params.has("roster")) {
        const roster = {};
        params.get("roster").split(".").forEach(part => {
          const m = /^([A-Z]+)(\d+)$/.exec(part);
          const slot = m && ROSTER_CODES.find(([, code]) => code === m[1]);
          if (slot) roster[slot[0]] = Number(m[2]);
        });
        league.roster = roster;
      }
      if (params.has("shares")) {
        const shares = {};
        params.get("shares").split("_").forEach(part => { const m = /^(QB|RB|WR|TE)(\d*\.?\d+)$/.exec(part); if (m) shares[m[1]] = Number(m[2]); });
        league.shares = shares;
      }
      // Older links: bench=0.150 (the old default) means no override; any other bench= without bso= is the sender's override.
      if (params.has("bso")) league.bso = Number(params.get("bso"));
      else if (params.has("bench")) { const old = Number(params.get("bench")); if (Number.isFinite(old) && Math.abs(old - 0.15) > 5e-4) league.bso = old; }
      if (params.has("inj")) league.inj = params.get("inj");
      if (params.has("conf")) league.conf = Number(params.get("conf"));
      const weeks = {};
      if (params.has("regend")) weeks.regend = Number(params.get("regend"));
      const po = /^(\d+)-(\d+)$/.exec(params.get("playoffs") || "");
      if (po) weeks.playoffs = [Number(po[1]), Number(po[2])];
      if (params.has("optimize")) weeks.optimize = params.get("optimize");
      if (params.has("week")) weeks.week = Number(params.get("week"));
      if (Object.keys(weeks).length) league.weeks = weeks;
      raw.league = league;
    }
    if (params.has("src")) raw.sources = params.get("src").split(",");
    const result = normalize(raw);
    return {state: result.state, warnings: warnings.concat(result.warnings)};
  }

  // ---------- pasteable block ----------
  const FENCE = "ddf-state";
  function encodeBlock(state, opts) {
    const {state: s} = normalize(state);
    if (!s) return "";
    const lines = ["```" + FENCE, JSON.stringify(s), "```"];
    if (opts && opts.url) lines.push("Open on the site: " + opts.url);
    return lines.join("\n");
  }

  // Accepts a fenced ddf-state block, bare JSON, or a site link carrying the query; returns {state, warnings}.
  function decodeBlock(text) {
    const src = String(text || "");
    const fenced = new RegExp("```\\s*" + FENCE + "\\s*([\\s\\S]*?)```", "i").exec(src);
    const json = fenced ? fenced[1] : (/\{[\s\S]*\}/.exec(src) || [])[0];
    if (json) {
      try { return normalize(JSON.parse(json)); } catch (e) { /* fall through to a link */ }
    }
    const link = /[#?]((?:[a-z]+=[^\s&]*&?)+)/i.exec(src);
    if (link) return decodeQuery(link[1]);
    return {state: null, warnings: ["no DDF state found in the text"]};
  }

  return {VERSION, normalize, encodeQuery, decodeQuery, encodeBlock, decodeBlock};
});
