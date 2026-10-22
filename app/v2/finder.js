// Trade Value v2 — Find a trade (JEG-481: first slice, then league import and roster sanity).
//
// You type in your roster and a rival's. The search lists packages (1-for-1 up to N-for-N)
// where the published trade charts say the rival breaks even or wins, and DDF Value says you win.
//
// No value math of its own: every number is an engine row value (TradeValueCurveControls
// .getAllRows()); the search only adds and compares them, as Compare a trade does. A missing
// value stays missing, never 0.
//
// Decisions (Jeremy, 2026-10-09 / 2026-10-10, recorded on JEG-481):
//   * rosters are typed in with player search; the second slice (2026-10-16) adds import from a Sleeper league,
//     a public ESPN league, or pasted names. Direct fetches need no key and no account; a private league is
//     refused by the host, and the card says to paste the roster instead;
//   * default 1-for-1 up to 2-for-2, a toggle raises the maximum players per side;
//   * "fair to the rival" = at least 3 of the 4 trade charts say the rival breaks even or wins;
//   * ranking prefers simpler trades.
// Defaults chosen here, listed in docs/math-review-agenda.md: the simplicity weight (EXTRA_PLAYER_WEIGHT)
// and the cap on subsets searched per side (MAX_SUBSETS).
(function (root) {
  "use strict";

  const OUR_KEY = "ddf_value";
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const MIN_CHARTS = 3;
  const MAX_SIZE_CHOICES = [2, 3, 4];
  const MAX_SUBSETS = 6000;          // per side; larger rosters search the top players by DDF Value
  const EXTRA_PLAYER_WEIGHT = 0.1;   // each player beyond a 1-for-1 takes 10% off the ranking score
  const LIMIT = 10;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const pointsAsShown = net => (Math.abs(net) < 0.05 ? 0 : net);   // 0.0 as shown points neither way

  // Every subset of 1..maxSize items, as arrays of indices.
  function subsets(count, maxSize) {
    const out = [];
    const walk = (start, picked) => {
      if (picked.length) out.push(picked.slice());
      if (picked.length === maxSize) return;
      for (let i = start; i < count; i++) { picked.push(i); walk(i + 1, picked); picked.pop(); }
    };
    walk(0, []);
    return out;
  }
  const choose = (n, k) => { let r = 1; for (let i = 1; i <= k; i++) r = r * (n - k + i) / i; return Math.round(r); };
  const subsetCount = (n, maxSize) => { let total = 0; for (let k = 1; k <= Math.min(n, maxSize); k++) total += choose(n, k); return total; };

  // The most players to search on one side so the subsets stay under the cap: the top by DDF Value.
  function pool(rows, ourKey, maxSize) {
    const priced = rows.filter(row => row.values && finite(row.values[ourKey]))
      .sort((a, b) => b.values[ourKey] - a.values[ourKey] || String(a.player_key).localeCompare(String(b.player_key)));
    let n = priced.length;
    while (n > maxSize && subsetCount(n, maxSize) > MAX_SUBSETS) n -= 1;
    return {rows: priced.slice(0, n), unpriced: rows.length - priced.length, searched: n, of: priced.length};
  }

  // mine / theirs: engine rows. opts: {ourKey, chartKeys, maxSize, minCharts, limit}.
  // Each trade: {give, receive, edge, charts: [{key, net, rivalOk}], pricedCharts, rivalOkCount, score}.
  // edge and net are receive - give for you; the rival is happy when a chart's net is <= 0 as shown.
  // A chart that does not price every player in the package is left out of the count (net null).
  function findTrades(mine, theirs, opts) {
    const o = opts || {};
    const ourKey = o.ourKey || OUR_KEY;
    const maxSize = Math.max(1, o.maxSize || 2);
    const chartKeys = (o.chartKeys || CHART_KEYS).slice();
    const minCharts = o.minCharts || Math.min(MIN_CHARTS, chartKeys.length);
    const limit = o.limit || LIMIT;
    // Optional roster sanity: {shape, mine, theirs (all the side's rows), keepMine, keepTheirs}.
    const sanity = o.sanity ? {...o.sanity, mineCounts: countByPos(o.sanity.mine || []), theirCounts: countByPos(o.sanity.theirs || [])} : null;
    let sanityDropped = 0;
    const mineP = pool(mine, ourKey, maxSize);
    const theirsP = pool(theirs, ourKey, maxSize);
    const keys = [ourKey].concat(chartKeys);
    // Per subset: the sum in each series, or null when any player in it lacks that series.
    const describe = (rows, combo) => {
      const sums = keys.map(key => {
        let total = 0;
        for (const i of combo) { const v = rows[i].values[key]; if (!finite(v)) return null; total += v; }
        return total;
      });
      return {combo, sums};
    };
    const mineSubs = subsets(mineP.rows.length, maxSize).map(c => describe(mineP.rows, c));
    const theirSubs = subsets(theirsP.rows.length, maxSize).map(c => describe(theirsP.rows, c))
      .sort((a, b) => a.sums[0] - b.sums[0]);
    const found = [];
    for (const give of mineSubs) {
      // DDF Value: you must win, so only their packages worth more than yours (sorted: binary search).
      let lo = 0; let hi = theirSubs.length;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (pointsAsShown(theirSubs[mid].sums[0] - give.sums[0]) > 0) hi = mid; else lo = mid + 1;
      }
      for (let t = lo; t < theirSubs.length; t++) {
        const get = theirSubs[t];
        const edge = get.sums[0] - give.sums[0];
        if (pointsAsShown(edge) <= 0) continue;
        let priced = 0;
        let ok = 0;
        const charts = [];
        for (let c = 0; c < chartKeys.length; c++) {
          const g = give.sums[c + 1];
          const r = get.sums[c + 1];
          if (g === null || r === null) { charts.push({key: chartKeys[c], net: null, rivalOk: null}); continue; }
          const net = r - g;
          const rivalOk = pointsAsShown(net) <= 0;
          priced += 1;
          if (rivalOk) ok += 1;
          charts.push({key: chartKeys[c], net, rivalOk});
        }
        if (priced < minCharts || ok < minCharts) continue;
        const players = give.combo.length + get.combo.length;
        const giveRows = give.combo.map(i => mineP.rows[i]);
        const getRows = get.combo.map(i => theirsP.rows[i]);
        let issues = null;
        if (sanity) {
          issues = {mine: lineupIssues(sanity.mineCounts, giveRows, getRows, sanity.shape),
            theirs: lineupIssues(sanity.theirCounts, getRows, giveRows, sanity.shape)};
          if ((sanity.keepMine && issues.mine.length) || (sanity.keepTheirs && issues.theirs.length)) { sanityDropped += 1; continue; }
        }
        found.push({give: giveRows, receive: getRows, edge, charts, issues,
          pricedCharts: priced, rivalOkCount: ok, score: edge * (1 - EXTRA_PLAYER_WEIGHT * (players - 2))});
      }
    }
    const idOf = trade => `${trade.give.map(r => r.player_key)}|${trade.receive.map(r => r.player_key)}`;
    found.sort((a, b) => b.score - a.score || b.edge - a.edge
      || (a.give.length + a.receive.length) - (b.give.length + b.receive.length)
      || idOf(a).localeCompare(idOf(b)));
    return {trades: found.slice(0, limit), total: found.length, sanityDropped, ourKey, chartKeys, minCharts, maxSize,
      mine: mineP, theirs: theirsP};
  }

  // ---------- roster sanity (JEG-481, second slice) ----------
  // Slots that need a named position. FLEX and SUPERFLEX are not counted, so the check is conservative toward the
  // positions a lineup cannot do without. A side is "thin" at a position when the trade leaves it with fewer players
  // there than the league starts (and fewer than it had), or fewer DDF starter-tier players than it had, short of
  // the slots (ddfTier is the engine's own tier, read, not recomputed).
  const SLOT_POSITIONS = ["QB", "RB", "WR", "TE"];
  const countByPos = rows => {
    const out = {};
    SLOT_POSITIONS.forEach(pos => { out[pos] = {all: 0, starter: 0}; });
    rows.forEach(row => {
      const bucket = out[row.pos];
      if (!bucket) return;
      bucket.all += 1;
      if (row.ddfTier === "starter") bucket.starter += 1;
    });
    return out;
  };
  // roster: the side's engine rows; leaving / arriving: the rows moving out of / into it; shape: the league's slots.
  function lineupIssues(roster, leaving, arriving, shape) {
    const before = Array.isArray(roster) ? countByPos(roster) : roster;
    const gone = countByPos(leaving);
    const came = countByPos(arriving);
    const issues = [];
    SLOT_POSITIONS.forEach(pos => {
      const need = (shape && shape[pos]) || 0;
      if (!need) return;
      const all = before[pos].all - gone[pos].all + came[pos].all;
      const starters = before[pos].starter - gone[pos].starter + came[pos].starter;
      if (all < need && all < before[pos].all) issues.push({pos, have: all, need, kind: "count"});
      else if (starters < Math.min(before[pos].starter, need)) issues.push({pos, have: starters, need, kind: "starter"});
    });
    return issues;
  }
  const issueText = issue => (issue.kind === "count"
    ? `${issue.have} ${issue.pos} left for ${issue.need} starting slot${issue.need === 1 ? "" : "s"}`
    : `${issue.have} ${issue.pos} starter${issue.have === 1 ? "" : "s"} left for ${issue.need} slot${issue.need === 1 ? "" : "s"}`);

  // The roster as typed in, before any search: positions the league starts that the roster does not have at all.
  function rosterGaps(rows, shape) {
    const counts = countByPos(rows);
    return SLOT_POSITIONS.filter(pos => shape && shape[pos] && counts[pos].all < shape[pos])
      .map(pos => ({pos, have: counts[pos].all, need: shape[pos]}));
  }

  // ---------- league import (JEG-481, second slice) ----------
  // Rosters come from a public league (Sleeper or ESPN) or pasted names; they become the same typed-in lists the
  // search card already uses. Names are matched to the engine's own rows, never invented.
  const SUFFIX = /\b(jr|sr|ii|iii|iv|v)\b\.?$/;
  const normName = name => String(name || "").toLowerCase().replace(/[.'’`]/g, "").replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ").trim().replace(SUFFIX, "").trim();
  // entries: [{name, pos}]; rows: engine rows. A name shared by two players is told apart by position, else left
  // unmatched (never guessed).
  function matchNames(entries, rows) {
    const byName = new Map();
    rows.forEach(row => {
      if (!row.name) return;
      const key = normName(row.name);
      if (!byName.has(key)) byName.set(key, []);
      byName.get(key).push(row);
    });
    const matched = [];
    const unmatched = [];
    const seen = new Set();
    entries.forEach(entry => {
      let hits = byName.get(normName(entry.name)) || [];
      if (hits.length > 1 && entry.pos) hits = hits.filter(row => row.pos === entry.pos);
      if (hits.length !== 1) { unmatched.push({...entry, reason: hits.length ? "more than one player has this name" : "not in the values"}); return; }
      const key = String(hits[0].player_key);
      if (seen.has(key)) return;
      seen.add(key);
      matched.push(hits[0]);
    });
    return {matched, unmatched};
  }
  const SLEEPER_POS = {DEF: "DEF"};
  // Sleeper: league rosters + league users + the player directory. Returns [{id, label, entries}].
  function parseSleeper(rosters, users, directory) {
    const owners = new Map((users || []).map(u => [String(u.user_id), (u.metadata && u.metadata.team_name) || u.display_name || u.username]));
    return (rosters || []).map(r => ({
      id: String(r.roster_id),
      label: owners.get(String(r.owner_id)) || `Team ${r.roster_id}`,
      entries: (r.players || []).map(id => {
        const p = (directory || {})[id];
        if (!p) return null;
        const name = p.full_name || [p.first_name, p.last_name].filter(Boolean).join(" ");
        return name ? {name, pos: SLEEPER_POS[p.position] || p.position || ""} : null;
      }).filter(Boolean)
    }));
  }
  const ESPN_POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"};
  // ESPN (public league, view=mRoster&view=mTeam). Returns [{id, label, entries}].
  function parseEspn(json) {
    return ((json && json.teams) || []).map(team => ({
      id: String(team.id),
      label: team.name || [team.location, team.nickname].filter(Boolean).join(" ") || `Team ${team.id}`,
      entries: (((team.roster || {}).entries) || []).map(entry => {
        const player = (entry.playerPoolEntry || {}).player || {};
        return player.fullName ? {name: player.fullName, pos: ESPN_POS[player.defaultPositionId] || ""} : null;
      }).filter(Boolean)
    }));
  }
  // Pasted names: one per line or comma-separated; a trailing "(QB - TEN)" style note is dropped.
  function parsePasted(text) {
    return String(text || "").split(/[\n,;]+/).map(s => s.replace(/\(.*?\)/g, "").replace(/\s+-\s+.*$/, "").trim())
      .filter(Boolean).map(name => ({name, pos: ""}));
  }

  const api = {findTrades, lineupIssues, issueText, rosterGaps, matchNames, normName, parseSleeper, parseEspn, parsePasted, subsets, subsetCount, OUR_KEY, CHART_KEYS, MIN_CHARTS, MAX_SIZE_CHOICES, MAX_SUBSETS, EXTRA_PLAYER_WEIGHT, LIMIT};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueFinder = api;

  // ---------- page (browser only) ----------
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};
  const $ = id => document.getElementById(id);
  const engine = () => root.TradeValueCurveControls;
  const S = {mine: [], theirs: [], maxSize: 2, keepMine: true, keepTheirs: true};   // mine / theirs: [{key, name, pos}]

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (k === "text") node.textContent = v; else node.setAttribute(k, v); });
    node.append(...kids);
    return node;
  }
  const clearOutput = () => { const out = $("v2FindOut"); out.hidden = true; out.replaceChildren(); };

  // Public league endpoints. Both answer cross-origin requests; a private ESPN league answers 401/403.
  let sleeperDirectory = null;
  async function getJson(url, what) {
    let response;
    try { response = await root.fetch(url); } catch (error) { throw new Error(`Could not reach ${what}.`); }
    if (response.status === 401 || response.status === 403) throw new Error(`${what} says that league is private.`);
    if (response.status === 404) throw new Error(`${what} has no league with that ID.`);
    if (!response.ok) throw new Error(`${what} answered with an error (${response.status}).`);
    return response.json();
  }
  async function loadSleeper(leagueId) {
    const base = "https://api.sleeper.app/v1";
    const [rosters, users] = await Promise.all([getJson(`${base}/league/${leagueId}/rosters`, "Sleeper"), getJson(`${base}/league/${leagueId}/users`, "Sleeper")]);
    if (!sleeperDirectory) sleeperDirectory = await getJson(`${base}/players/nfl`, "Sleeper");
    return parseSleeper(rosters, users, sleeperDirectory);
  }
  async function loadEspn(leagueId) {
    const now = new Date();
    const season = now.getMonth() < 2 ? now.getFullYear() - 1 : now.getFullYear();
    const json = await getJson(`https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/${season}/segments/0/leagues/${leagueId}?view=mRoster&view=mTeam`, "ESPN");
    return parseEspn(json);
  }

  function sideCard(side, title) {
    const id = `v2Find${side[0].toUpperCase()}${side.slice(1)}`;
    const list = el("ul", {class: "v2-trade-players", id: `${id}Players`});
    const results = el("ul", {class: "v2-trade-results", id: `${id}Results`, hidden: ""});
    const input = el("input", {type: "search", id: `${id}Search`, placeholder: "Search and add a player…", autocomplete: "off", "aria-controls": `${id}Results`});
    const label = el("label", {class: "v2-search"}, el("span", {class: "v2-sr", text: `Search and add a player to ${title.toLowerCase()}`}), input);
    const wrap = el("div", {class: "v2-trade-side v2-find-side", id}, el("h3", {text: title}), label, results, list, importBox());
    const render = () => {
      list.replaceChildren(...S[side].map(p => {
        const remove = el("button", {type: "button", class: "v2-link", "aria-label": `Remove ${p.name}`, text: "Remove"});
        remove.addEventListener("click", () => { S[side] = S[side].filter(q => q.key !== p.key); render(); clearOutput(); });
        return el("li", {}, el("div", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: p.pos ? ` ${p.pos}` : ""})), remove);
      }));
    };
    // Import: a Sleeper league, a public ESPN league, or pasted names. Names are matched to the engine's rows.
    function importBox() {
      const sel = el("select", {id: `${id}Source`, "aria-label": "Where the roster comes from"},
        el("option", {value: "sleeper", text: "Sleeper league ID"}), el("option", {value: "espn", text: "ESPN public league ID"}),
        el("option", {value: "paste", text: "Pasted names"}));
      const leagueId = el("input", {type: "text", id: `${id}League`, placeholder: "League ID", autocomplete: "off", inputmode: "numeric", "aria-label": "League ID"});
      const paste = el("textarea", {id: `${id}Paste`, rows: "4", placeholder: "One player per line", hidden: "", "aria-label": "Pasted player names"});
      const load = el("button", {type: "button", class: "v2-btn", id: `${id}Load`, text: "Load teams"});
      const team = el("select", {id: `${id}Team`, hidden: "", "aria-label": "Team to import"});
      const use = el("button", {type: "button", class: "v2-btn", id: `${id}Use`, text: "Use this team", hidden: ""});
      const status = el("p", {class: "v2-meta", id: `${id}Status`, role: "status"});
      let teams = [];
      const say = text => { status.textContent = text; };
      sel.addEventListener("change", () => {
        const isPaste = sel.value === "paste";
        paste.hidden = !isPaste;
        leagueId.hidden = isPaste;
        load.textContent = isPaste ? "Add players" : "Load teams";
        team.hidden = true; use.hidden = true; say("");
      });
      // entries -> engine rows; replace (a team) or add (pasted names). A player on the other roster is not moved.
      function apply(entries, from, replace) {
        const rows = engine() ? engine().getAllRows() : [];
        const {matched, unmatched} = matchNames(entries, rows);
        const other = new Set(S[side === "mine" ? "theirs" : "mine"].map(p => p.key));
        const keep = replace ? [] : S[side];
        const have = new Set(keep.map(p => p.key));
        const added = [];
        const onOther = [];
        matched.forEach(row => {
          const key = String(row.player_key);
          if (other.has(key)) onOther.push(row.name);
          else if (!have.has(key)) { have.add(key); added.push({key, name: row.name, pos: row.pos}); }
        });
        S[side] = keep.concat(added);
        render();
        clearOutput();
        const parts = [`Added ${added.length} player${added.length === 1 ? "" : "s"}${from ? ` from ${from}` : ""}.`];
        if (onOther.length) parts.push(`Left out because they are on the other roster: ${onOther.join(", ")}.`);
        if (unmatched.length) parts.push(`Not matched (${unmatched.length}): ${unmatched.slice(0, 8).map(u => u.name).join(", ")}${unmatched.length > 8 ? ", …" : ""}.`);
        say(parts.join(" "));
      }
      load.addEventListener("click", async () => {
        if (sel.value === "paste") { apply(parsePasted(paste.value), "", false); paste.value = ""; return; }
        const idText = leagueId.value.trim();
        if (!/^[A-Za-z0-9_-]+$/.test(idText)) { say("Enter the league ID: the number in your league's web address."); return; }
        say(sel.value === "sleeper" ? "Loading the league and Sleeper's player names (about 15 MB the first time)…" : "Loading the league…");
        try {
          teams = await (sel.value === "sleeper" ? loadSleeper(idText) : loadEspn(idText));
        } catch (error) {
          teams = [];
          say(`${error.message} You can paste the roster instead.`);
          team.hidden = true; use.hidden = true;
          return;
        }
        team.replaceChildren(...teams.map((t, i) => el("option", {value: String(i), text: `${t.label} (${t.entries.length} players)`})));
        team.hidden = !teams.length; use.hidden = !teams.length;
        say(teams.length ? `Found ${teams.length} teams. Pick yours and choose Use this team.` : "That league has no teams.");
      });
      use.addEventListener("click", () => { const t = teams[Number(team.value)]; if (t) apply(t.entries, t.label, true); });
      return el("details", {class: "v2-find-import"}, el("summary", {text: "Import this roster"}),
        el("div", {class: "v2-find-import-body"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "From:"}), sel),
          leagueId, paste, load, team, use, status));
    }
    input.addEventListener("input", () => {
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = !q;
      if (!q || !engine()) return;
      const taken = new Set(S.mine.concat(S.theirs).map(p => p.key));
      // JEG-861: the page's one name matcher (reversed names, suffixes, typos), never a plain "contains".
      const hits = window.TradeValueNameSearch.search(engine().getAllRows(), q).slice(0, 8);
      if (!hits.length) results.append(el("li", {class: "is-empty v2-meta", text: `No player name matches “${q}”.`}));
      hits.forEach(row => {
        const key = String(row.player_key);
        const added = taken.has(key);
        const button = el("button", {type: "button", text: `${`${row.name} · ${row.pos || ""} ${row.team || ""}`.trim()}${added ? " ✓ Added" : ""}`});
        if (added) button.disabled = true;
        button.addEventListener("click", () => {
          S[side].push({key, name: row.name, pos: row.pos});
          input.value = "";
          results.replaceChildren();
          results.hidden = true;
          render();
          clearOutput();
          input.focus();
        });
        results.append(el("li", {}, button));
      });
    });
    return wrap;
  }

  const fmt = n => (Math.abs(n) < 0.05 ? "0.0" : (n > 0 ? "+" : "") + n.toFixed(1));
  const names = rows => rows.map(r => r.name).join(" + ");

  function run() {
    const out = $("v2FindOut");
    out.hidden = false;
    out.replaceChildren();
    const note = text => out.append(el("p", {class: "v2-meta", text}));
    const C = engine();
    if (!C) return note("Values are still loading.");
    if (!S.mine.length || !S.theirs.length) return note("Add at least one player to each roster.");
    const all = C.getAllRows();
    const byKey = new Map(all.map(r => [String(r.player_key), r]));
    const rowsOf = list => list.map(p => byKey.get(p.key)).filter(Boolean);
    // JEG-819: use only charts the engine says are available (not held or missing), matching Compare and Targets.
    const sourceInfo = C.getSourceInfo ? C.getSourceInfo() : [];
    const availableKeys = new Set(sourceInfo.filter(item => item.available).map(item => item.key));
    const charts = CHART_KEYS.filter(key => availableKeys.has(key));
    if (!charts.length) return note("No trade chart is available this week.");
    if (charts.length < MIN_CHARTS) note(`Only ${charts.length} trade chart${charts.length === 1 ? " is" : "s are"} available this week. Not enough charts to judge acceptance.`);
    const shape = C.getRosterShape ? C.getRosterShape() : null;
    const mineRows = rowsOf(S.mine);
    const theirRows = rowsOf(S.theirs);
    // Roster sanity on what was typed in: a position the league starts that the roster does not cover.
    [["Your", mineRows], ["Their", theirRows]].forEach(([who, rows]) => {
      rosterGaps(rows, shape).forEach(g => note(`${who} roster has ${g.have} ${g.pos} for ${g.need} starting slot${g.need === 1 ? "" : "s"} in this league.`));
    });
    const res = findTrades(mineRows, theirRows, {chartKeys: charts, maxSize: S.maxSize,
      sanity: shape ? {shape, mine: mineRows, theirs: theirRows, keepMine: S.keepMine, keepTheirs: S.keepTheirs} : null});
    if (res.sanityDropped) note(`${res.sanityDropped} trade${res.sanityDropped === 1 ? "" : "s"} left out because ${res.sanityDropped === 1 ? "it leaves" : "they leave"} a starting lineup short at a position. Untick the boxes below to see ${res.sanityDropped === 1 ? "it" : "them"}.`);
    const skipped = res.mine.unpriced + res.theirs.unpriced;
    if (skipped) note(`${skipped} player${skipped === 1 ? " has" : "s have"} no DDF Value and ${skipped === 1 ? "is" : "are"} left out, not counted as 0.`);
    if (res.mine.searched < res.mine.of || res.theirs.searched < res.theirs.of) {
      note(`Packages of up to ${S.maxSize} are searched among your top ${res.mine.searched} and their top ${res.theirs.searched} players by DDF Value.`);
    }
    if (!res.trades.length) {
      return note(`No trade found where DDF Value says you win and at least ${res.minCharts} of ${charts.length} available trade chart${charts.length === 1 ? "s say" : "s say"} they break even or win. Try a larger package.`);
    }
    note(`${res.total} trade${res.total === 1 ? "" : "s"} found; the top ${res.trades.length} are listed, ranked by DDF Value edge with simpler trades first.`);
    const list = el("ol", {class: "v2-find-list", id: "v2FindList"});
    res.trades.forEach(t => {
      const favor = t.charts.filter(c => c.rivalOk).map(c => CHART_NAMES[c.key] || c.key);
      const unpriced = t.charts.filter(c => c.net === null).length;
      const ids = rows => rows.map(r => encodeURIComponent(r.player_key)).join(",");
      const thin = t.issues ? [["you", t.issues.mine], ["them", t.issues.theirs]].filter(([, list]) => list.length)
        .map(([who, list]) => `Leaves ${who} thin: ${list.map(issueText).join("; ")}.`) : [];
      const open = el("a", {class: "v2-link", href: `v2/#compare-trade?give=${ids(t.give)}&get=${ids(t.receive)}`, text: "Open in Compare a trade"});
      list.append(el("li", {"data-find-edge": String(t.edge)},
        el("b", {text: `You give ${names(t.give)}; you receive ${names(t.receive)}`}),
        el("span", {class: "v2-meta", text: `DDF Value edge ${fmt(t.edge)} for you. ${favor.length} of ${t.pricedCharts} trade chart${t.pricedCharts === 1 ? "" : "s"} have them winning or even${favor.length ? `: ${favor.join(", ")}` : ""}.`
          + (t.pricedCharts < MIN_CHARTS ? ` Not enough charts to judge acceptance.` : "")
          + (unpriced ? ` ${unpriced} chart${unpriced === 1 ? " does" : "s do"} not price every player and ${unpriced === 1 ? "is" : "are"} not counted.` : "")
          + (thin.length ? ` ${thin.join(" ")}` : "")}),
        open));
    });
    out.append(list);
  }

  function build() {
    const host = $("v2Compare");
    if (!host || $("v2Find")) return;
    const size = el("select", {id: "v2FindSize"}, ...MAX_SIZE_CHOICES.map(n => el("option", {value: String(n), text: `Up to ${n}-for-${n}`})));
    size.addEventListener("change", () => { S.maxSize = Number(size.value); clearOutput(); });
    const keep = (id, label, field) => {
      const box = el("input", {type: "checkbox", id});
      box.checked = S[field];
      box.addEventListener("change", () => { S[field] = box.checked; clearOutput(); });
      return el("label", {class: "v2-field"}, box, el("span", {text: ` ${label}`}));
    };
    const go = el("button", {type: "button", class: "v2-btn", id: "v2FindGo", text: "Find trades"});
    go.addEventListener("click", run);
    const card = el("section", {class: "v2-card", id: "v2Find", "aria-labelledby": "v2FindTitle"},
      el("div", {class: "v2-card-head"}, el("div", {},
        el("h2", {id: "v2FindTitle", text: "Find a trade to propose"}),
        el("p", {class: "v2-meta", text: "Type in your roster and another manager's. Lists trades where DDF Value says you win and the available trade charts say the other manager breaks even or wins."}))),
      el("div", {class: "v2-trade-sides"}, sideCard("mine", "Your roster"), sideCard("theirs", "Their roster")),
      el("div", {class: "v2-ctoolbar"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Package size:"}), size),
        keep("v2FindKeepMine", "Keep my starting lineup filled", "keepMine"), keep("v2FindKeepTheirs", "Keep theirs filled", "keepTheirs"), go),
      el("div", {id: "v2FindOut", "aria-live": "polite", hidden: ""}));
    host.insertBefore(card, host.querySelector(".v2-footnote"));
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", build);
  else build();
})(typeof window !== "undefined" ? window : globalThis);
