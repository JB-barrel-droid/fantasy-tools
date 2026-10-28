// Trade Value v2 — the team summary (JEG-1021 section 5).
//
// One row per team: roster, starter and bench value in DDF Value (fundamental) and the Trade chart average (market), a
// dense rank in each view, strengths, weaknesses, and the players the market prices under or over their DDF Value.
//
// No value math of its own: starters, bench and depth come from finder.js (lineupValue, rosterBalance, withChartAverage),
// the same functions the Find a trade page uses. This file only sums, ranks and compares them. The same code runs for 1
// team or 20: no size-dependent path (a median needs MIN_MEDIAN_TEAMS teams, otherwise depth alone decides).
//
// Decisions (Jeremy, 2026-10-24, JEG-1021): strength = depth at or above the expected range AND starters at the position at
// or above the league median (Q12 A); players listed as under/overvalued need a gap above NOISE_FLOOR = 2.0 points (Q13 A).
(function (root) {
  "use strict";

  const NOISE_FLOOR = 2.0;          // points of DDF Value; a gap at or below this is not listed (Q13 A)
  const MIN_MEDIAN_TEAMS = 3;       // fewer teams with a starter at a position: depth alone decides (Q12 A)
  const POSITIONS = ["QB", "RB", "WR", "TE"];
  const OUR_KEY = "ddf_value";
  const MARKET_KEY = "chart_avg";
  const PROJ_KEY = "ddf_value_projections";   // JEG-1081: the third view, DDF Value (projections)
  const CHARTS_KEY = "ddf_value_charts";
  const DISAGREE_FLOOR = 2.0;                 // points; Jeremy 2026-10-25 (JEG-1081 Q1): projections vs charts listed above this gap
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const finder = () => (typeof module !== "undefined" && module.exports ? require("./finder.js") : root.TradeValueFinder);
  const shown = n => Math.round(n * 10) / 10;   // values compare as shown (one decimal)
  const money = n => n.toFixed(1);

  function median(values) {
    if (!values.length) return null;
    const sorted = values.slice().sort((a, b) => a - b);
    const mid = sorted.length >> 1;
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }
  // Dense ranks: equal (as shown) values share a rank, the next value is the next integer (1, 2, 2, 3).
  function denseRanks(items, valueOf) {
    const out = new Map();
    const distinct = [...new Set(items.map(i => shown(valueOf(i))))].sort((a, b) => b - a);
    items.forEach(i => out.set(i.id, distinct.indexOf(shown(valueOf(i))) + 1));
    return out;
  }
  const ordinal = n => {
    const mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
    return `${n}${({1: "st", 2: "nd", 3: "rd"})[n % 10] || "th"}`;
  };

  // The projections view needs a projection for every player who counts (a roster with a hole would be understated and ranked low).
  const projected = rows => rows.some(r => POSITIONS.includes(r.pos)) && rows.filter(r => POSITIONS.includes(r.pos)).every(r => r.values && finite(r.values[PROJ_KEY]));
  // One team's lineup in one view. rows: the team's engine rows; null when the view is not available.
  function viewOf(F, rows, key, ctx) {
    const source = key === MARKET_KEY ? (ctx.chartKeys ? F.withChartAverage(rows, ctx.chartKeys) : null) : key === PROJ_KEY && !projected(rows) ? null : rows;
    if (!source) return null;
    const lineup = F.lineupValue(source, ctx.shape, key);
    const balance = ctx.expected ? F.rosterBalance(source, ctx.expected, key, ctx.shape) : null;
    const byPos = {};
    POSITIONS.forEach(pos => { byPos[pos] = lineup.starters.filter(r => r.pos === pos).reduce((n, r) => n + r.values[key], 0); });
    return {key, lineup, balance, starterValue: lineup.starterValue, benchValue: lineup.benchValue, rosterValue: lineup.total, startersByPos: byPos,
      starterCountByPos: POSITIONS.reduce((o, pos) => { o[pos] = lineup.starters.filter(r => r.pos === pos).length; return o; }, {})};
  }

  // The players the market prices away from DDF Value: gap = DDF Value - chart average.
  function marketGaps(rows, floor) {
    const under = [];
    const over = [];
    rows.forEach(r => {
      const ddf = r.values && r.values[OUR_KEY];
      const chart = r.values && r.values[MARKET_KEY];
      if (!finite(ddf) || !finite(chart)) return;
      const gap = ddf - chart;
      const item = {key: String(r.player_key), name: r.name, pos: r.pos, ddf, chart, gap};
      if (gap > floor) under.push(item);
      else if (gap < -floor) over.push(item);
    });
    const order = (a, b) => Math.abs(b.gap) - Math.abs(a.gap) || a.name.localeCompare(b.name) || a.key.localeCompare(b.key);
    return {under: under.sort(order), over: over.sort(order)};
  }

  // JEG-1081: the players where DDF Value (projections) and the adjusted trade charts disagree: gap = projections - charts.
  // "higher": the projections price him above the charts; "lower": below. Both views are DDF-scaled, so this is player-level, not position-level.
  function projectionGaps(rows, floor) {
    const higher = [];
    const lower = [];
    rows.forEach(r => {
      const v = r.values || {};
      const charts = finite(v[CHARTS_KEY]) ? v[CHARTS_KEY] : v[OUR_KEY];
      const proj = v[PROJ_KEY];
      if (!finite(charts) || !finite(proj)) return;
      const gap = proj - charts;
      const item = {key: String(r.player_key), name: r.name, pos: r.pos, charts, projections: proj, gap};
      if (gap > floor) higher.push(item);
      else if (gap < -floor) lower.push(item);
    });
    const order = (a, b) => Math.abs(b.gap) - Math.abs(a.gap) || a.name.localeCompare(b.name) || a.key.localeCompare(b.key);
    return {higher: higher.sort(order), lower: lower.sort(order)};
  }

  // teams: [{id, name, entries: [{key, name, pos}], isMine?}]. ctx: {rowsByKey: Map(key -> engine row), shape, expected, chartKeys (null when
  // there is no Trade chart average), noiseFloor?}. opts: {basis: "fund" | "market"} - the view strengths and weaknesses are judged in.
  function summarize(teams, ctx, opts) {
    const F = finder();
    const floor = finite(ctx.noiseFloor) ? ctx.noiseFloor : NOISE_FLOOR;
    const basis = opts && opts.basis === "market" && ctx.chartKeys ? "market" : "fund";
    const slots = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"].reduce((n, s) => n + ((ctx.shape && ctx.shape[s]) || 0), 0);
    const rows = teams.map(team => {
      const entries = team.entries || [];
      const found = [];
      const missing = [];
      let notEvaluated = 0;
      entries.forEach(e => {
        const row = ctx.rowsByKey.get(String(e.key));
        if (row) found.push(row);
        else if (F.isNotEvaluated(e)) notEvaluated += 1;
        else missing.push(e.name);
      });
      const depthPlayers = found.filter(r => POSITIONS.includes(r.pos)).length;
      const hasRoster = found.length > 0;
      const fund = hasRoster ? viewOf(F, found, OUR_KEY, ctx) : null;
      const market = hasRoster ? viewOf(F, found, MARKET_KEY, ctx) : null;
      const proj = hasRoster ? viewOf(F, found, PROJ_KEY, ctx) : null;
      const disagree = hasRoster ? projectionGaps(found, DISAGREE_FLOOR) : {higher: [], lower: []};
      const gaps = hasRoster && market ? marketGaps(F.withChartAverage(found, ctx.chartKeys), floor) : {under: [], over: []};
      return {id: team.id, name: team.name, isMine: Boolean(team.isMine), size: entries.length, evaluated: found.length, notEvaluated, missing, hasRoster,
        partial: hasRoster && slots > 0 && depthPlayers < slots, fund, market, proj, under: gaps.under, over: gaps.over, higher: disagree.higher, lower: disagree.lower,
        rank: {fund: null, market: null, proj: null},
        strengths: [], weaknesses: [], positions: {}, thinBench: null};
    });
    const ranked = rows.filter(r => r.hasRoster);
    if (ranked.length >= 2) {
      const f = denseRanks(ranked, r => r.fund.rosterValue);
      ranked.forEach(r => { r.rank.fund = f.get(r.id); });
      const marketTeams = ranked.filter(r => r.market);
      if (marketTeams.length >= 2) {
        const m = denseRanks(marketTeams, r => r.market.rosterValue);
        marketTeams.forEach(r => { r.rank.market = m.get(r.id); });
      }
    }
    const projTeams = ranked.filter(r => r.proj);
    if (projTeams.length >= 2) {
      const pr = denseRanks(projTeams, r => r.proj.rosterValue);
      projTeams.forEach(r => { r.rank.proj = pr.get(r.id); });
    }
    // Strengths and weaknesses in the basis view, against the league median of the teams that have a roster.
    const view = r => (basis === "market" ? r.market : r.fund);
    const league = {basis, rankedCount: ranked.length, median: {}, benchMedian: null, medianTeams: {}};
    const withView = ranked.filter(r => view(r));
    POSITIONS.forEach(pos => {
      const sums = withView.filter(r => view(r).starterCountByPos[pos] > 0).map(r => view(r).startersByPos[pos]);
      league.medianTeams[pos] = sums.length;
      league.median[pos] = sums.length >= MIN_MEDIAN_TEAMS ? median(sums) : null;
    });
    league.benchMedian = withView.length >= MIN_MEDIAN_TEAMS ? median(withView.map(r => view(r).benchValue)) : null;
    withView.forEach(r => {
      const v = view(r);
      if (!v.balance) return;
      POSITIONS.forEach(pos => {
        const b = v.balance.positions[pos];
        const sum = v.startersByPos[pos];
        const med = league.median[pos];
        const depthGap = b.status === "under" ? b.lo - b.have : b.status === "over" ? b.have - b.hi : 0;
        const item = {pos, have: b.have, range: b.range, status: b.status, starters: sum, median: med, depthGap};
        r.positions[pos] = item;
        const valueLow = med !== null && shown(sum) < shown(med);
        const strength = b.status !== "under" && !valueLow;
        const weak = b.status === "under" || valueLow;
        const vs = med !== null ? `starters ${money(sum)} vs median ${money(med)}` : "";
        if (strength) {
          item.margin = med !== null ? sum - med : depthGap;
          item.text = `${pos} allocation ${med !== null ? "above the league median" : "at or above the expected depth"} (${b.have} counted${b.status === "over" ? ", deep" : ""}${vs ? `, ${vs}` : `, ${b.range} expected`})`;
          r.strengths.push(item);
        }
        if (weak) {
          item.margin = med !== null ? sum - med : -(b.lo - b.have);
          const parts = [b.status === "under" ? `${b.have} counted, ${b.range} expected` : `${b.have} counted`];
          if (valueLow) parts.push(vs);
          item.text = `${pos} allocation ${valueLow ? "below the league median" : "below the expected depth"} (${parts.join("; ")})`;
          r.weaknesses.push(item);
        }
      });
      if (league.benchMedian !== null && shown(v.benchValue) < shown(league.benchMedian)) {
        r.thinBench = {value: v.benchValue, median: league.benchMedian, margin: v.benchValue - league.benchMedian,
          text: `Thin bench (${money(v.benchValue)} vs median ${money(league.benchMedian)})`};
      }
    });
    return {teams: rows, league, basis, noiseFloor: floor};
  }

  // Rows in rank order for a view (ties: starter value high first, then name). Teams without a roster go last.
  function rankOrder(summary, view) {
    const key = view === "market" ? "market" : "fund";
    const valueOf = t => (t[key] ? t[key].rosterValue : null);
    return summary.teams.slice().sort((a, b) => {
      const av = valueOf(a);
      const bv = valueOf(b);
      if ((av === null) !== (bv === null)) return av === null ? 1 : -1;
      if (av === null) return a.name.localeCompare(b.name);
      return shown(bv) - shown(av) || (b[key].starterValue - a[key].starterValue) || a.name.localeCompare(b.name);
    });
  }

  const listJoin = items => (items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`);
  // The plain sentence above the table, from the rank and strength data (not from row positions).
  function headline(summary) {
    const teams = summary.teams;
    const ranked = teams.filter(t => t.hasRoster);
    if (!ranked.length) return "";
    const mine = ranked.find(t => t.isMine) || null;
    const subject = mine ? "Your team" : null;
    const best = list => list.slice().sort((a, b) => a.margin - b.margin);
    const notes = t => {
      const strong = t.strengths.length ? best(t.strengths).pop() : null;
      const weak = t.weaknesses.length ? best(t.weaknesses)[0] : null;
      const parts = [];
      if (strong) parts.push(`heavy at ${strong.pos}`);
      if (weak) parts.push(`light at ${weak.pos}`);
      const lead = parts.length ? `Position allocation: ${parts.join(", ")}.` : "";
      const bench = t.thinBench && !weak ? `${lead ? " " : ""}Thin bench.` : "";
      const gaps = t.higher.concat(t.lower).sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap) || a.name.localeCompare(b.name));
      const gap = gaps.length ? gaps[0] : null;
      const note = gap ? ` DDF Value (projections) prices ${gap.name} ${money(Math.abs(gap.gap))} ${gap.gap > 0 ? "above" : "below"} the adjusted trade charts, the biggest gap on ${subject ? "your" : "its"} roster.` : "";
      return `${lead}${bench}${note}`.trim();
    };
    if (ranked.length === 1) {
      const t = ranked[0];
      const depth = t.fund && t.fund.balance ? t.fund.balance : null;
      const over = depth ? depth.over : [];
      const under = depth ? depth.under : [];
      const shape = [over.length ? `over at ${listJoin(over)}` : "", under.length ? `under at ${listJoin(under)}` : ""].filter(Boolean).join(", ");
      const mkt = t.market ? `, ${money(t.market.starterValue)} charts` : "";
      return `${subject ? "Your team" : t.name}: starters ${money(t.fund.starterValue)} DDF${mkt}.${shape ? ` ${shape[0].toUpperCase()}${shape.slice(1)}.` : ""}`;
    }
    if (mine) {
      const f = mine.rank.fund;
      const m = mine.rank.market;
      const pj = mine.rank.proj;
      const others = [pj ? `${ordinal(pj)} on projections` : "", m ? `${ordinal(m)} on market` : ""].filter(Boolean);
      return `Your team ranks ${ordinal(f)} of ${ranked.length} on DDF Value${others.length ? `, ${others.join(", ")}` : ""}. ${notes(mine)}`.trim();
    }
    const top = rankOrder(summary, "fund")[0];
    const others = [top.rank.proj ? `${ordinal(top.rank.proj)} on projections` : "", top.rank.market ? `${ordinal(top.rank.market)} on market` : ""].filter(Boolean);
    return `${top.name} ranks 1st of ${ranked.length} on DDF Value${others.length ? `, ${others.join(", ")}` : ""}. Mark one team as yours to see how it compares.`;
  }

  // ---------- the table's columns, for table-sort.js (section 6) ----------
  // The gap of largest size, with its sign (higher is positive), so the column sorts on what the cell shows first; null when empty.
  const biggestSigned = list => (list.length ? list.slice().sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))[0].gap : null);
  const topGap = list => (list.length ? Math.abs(list[0].gap) : null);
  function summaryColumns(basis) {
    const other = basis === "market" ? "fund" : "market";
    const money = (key, part) => t => (t[key] ? t[key][part] : null);
    return [
      {id: "rank", label: "Rank", type: "number", first: "asc", rank: true, get: t => t.rank[basis]},
      {id: "team", label: "Team", type: "text", first: "asc", get: t => t.name},
      {id: "rosterF", label: "Roster value (DDF)", type: "number", first: "desc", get: money("fund", "rosterValue")},
      {id: "starterF", label: "Starter value (DDF)", type: "number", first: "desc", get: money("fund", "starterValue")},
      {id: "benchF", label: "Bench value (DDF)", type: "number", first: "desc", get: money("fund", "benchValue")},
      {id: "rosterM", label: "Roster value (market)", type: "number", first: "desc", get: money("market", "rosterValue")},
      {id: "starterM", label: "Starter value (market)", type: "number", first: "desc", get: money("market", "starterValue")},
      {id: "benchM", label: "Bench value (market)", type: "number", first: "desc", get: money("market", "benchValue")},
      {id: "altRank", label: other === "market" ? "Trade chart average rank" : "DDF Value rank", type: "number", first: "asc", rank: true, get: t => t.rank[other]},
      {id: "projRank", label: "DDF Value (projections) rank", type: "number", first: "asc", rank: true, get: t => t.rank.proj},
      {id: "disagree", label: "Projections vs charts", type: "number", first: "desc", get: t => biggestSigned(t.higher.concat(t.lower))},
      {id: "under", label: "Buy (market underpays)", type: "number", first: "desc", get: t => topGap(t.under)},
      {id: "over", label: "Sell (market overpays)", type: "number", first: "desc", get: t => topGap(t.over)}
    ];
  }
  const SUMMARY_DEFAULT = {col: "rank", dir: "asc"};
  const SUMMARY_TIES = [{get: t => (t.fund ? t.fund.starterValue : null), type: "number", dir: "desc"}, {get: t => t.name, type: "text", dir: "asc"}];

  const api = {summaryColumns, SUMMARY_DEFAULT, SUMMARY_TIES, NOISE_FLOOR, MIN_MEDIAN_TEAMS, POSITIONS, median, denseRanks, ordinal, marketGaps, projectionGaps, DISAGREE_FLOOR, PROJ_KEY, summarize, rankOrder, headline};
  if (typeof module !== "undefined" && module.exports) { module.exports = api; return; }
  root.TradeValueTeamSummary = api;
})(typeof window !== "undefined" ? window : globalThis);
