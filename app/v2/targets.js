// Trade Value v2 — Trade targets (Figma frames 03 / 04).
//
// Pure functions, no DOM: given the engine's own rows (TradeValueCurveControls
// .getRows()), pair our value with each published chart's value for the same
// player. The only arithmetic is one difference per player per chart:
//
//   gap = chart value − our value
//
// Both series are on the same trade-value point scale for the user's league
// (the published charts are indexed to our curve by the engine). A positive gap
// means the chart pays more than we would (a sell target); a negative gap means
// it pays less (a buy target). Lists rank by the gap weighted by the value at
// stake (JEG-820, SELL_FLOOR below). VORP vs waivers is a different unit and is never
// paired with anything here. A missing value on either side gives no gap
// (null plus a reason), never zero.
//
// GAP-025 (Jeremy, 2026-10-07: "Yes, use 0"): a player ESPN lists but projects
// at 0 (injured/out) has an ESPN · DDA value of 0.0 in the engine rows, not a
// missing one, so a chart that still pays for him is an ordinary sell target
// with gap = chart value. A player with no ESPN row is still missing.
//
// Our value (Jeremy, 2026-10-16: DDF decides who we want and don't want): DDF Value (ddf_value, the blend) is
// the default; the other DDF versions (JEG-542), ESPN, CBS rest-of-season and Razzball projections stay as
// alternatives. Each is one engine series, read as is.
//
// Waiver line (Jeremy, 2026-10-07: "It's illogical that 0 value players would
// be on a buy list."). Every series here is value above waivers for the user's
// league: 0 means at or below that series' waiver line. A chart value at or
// below 0 is shown, but it is never a buy (or sell) target and gets no gap.
(function (root) {
  "use strict";

  // Jeremy 2026-10-16 (JEG-677 follow-up): Check 1 compares DDF Value (the blend) to the market consensus of
  // the rescaled trade charts. The other versions stay selectable.
  // JEG-851: chart keys are also selectable as "Our value", so you can compare any one source against any other.
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};
  const OUR_KEYS = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "espn", "cbsros", "razzball"].concat(CHART_KEYS);
  const OUR_KEY = OUR_KEYS[0];   // default: DDF Value
  const DDF_VALUE_KEY = "ddf_value";
  // JEG-863 / JEG-1073: the names say what each is (DDF Value = the Adjusted trade charts; ddf_value_charts is the same
  // series and is hidden from the picker by v2.js; ddf_value_projections is the alternate).
  const OUR_NAMES = {ddf_value: "DDF Value", ddf_value_charts: "DDF Value", ddf_value_projections: "DDF Value (projections)", espn: "ESPN projections", cbsros: "CBS rest-of-season projections", razzball: "Razzball projections",
    usatoday: "USA Today trade chart", fantasycalc: "FantasyCalc trade chart", fantasypros: "FantasyPros trade chart", cbs: "CBS Sports trade chart"};
  const OUR_SHORT = {ddf_value: "DDF Value", ddf_value_charts: "DDF Value", ddf_value_projections: "DDF Value (projections)", espn: "ESPN projections", cbsros: "CBS rest of season", razzball: "Razzball projections",
    usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};

  const finite = value => typeof value === "number" && Number.isFinite(value);

  // JEG-820 (2026-10-22, option B of the ticket, proceeding per standing instruction): the lists rank by the
  // gap WEIGHTED by the value at stake, score = |gap| x min(our value, consensus), so a 12-point gap on a
  // player worth 1 point to us (a drop, not a trade chip) no longer outranks a 5-point gap on a 9-point
  // player. Sell also needs our value at or above SELL_FLOOR: below it the charts may pay, but a manager
  // would drop the player, not shop him. Buy has no floor; the weight already sinks a near-zero consensus.
  const SELL_FLOOR = 5;

  // JEG-833 (2026-10-22, proceeding per standing instruction): Buy compares at the charts' RANK. Our top end is
  // steeper than the charts' (Gibbs 69.6 vs 50.9, Smith-Njigba 64.7 vs 38.7 with the same rank on both sides),
  // so a consensus gap, a position-share gap or a percentage gap all list the overall top five as "buys". The
  // rank-equivalent gap is invariant to any monotone rescale: for a player the charts rank r-th at his position,
  // oursAtRank = our r-th value at that position (same compared players), rankGap = oursAtRank - ours. Negative:
  // the charts rank him lower than we do (a buy); a pure rescale gives 0 everywhere. A Buy needs rankGap at or
  // under -BUY_RANK_MARGIN points; the rest of the "market pays less" players are counted as scaleOnly.
  const BUY_RANK_MARGIN = 2;

  function rankEquivalents(players, minCharts) {
    const byPos = new Map();
    players.forEach(p => {
      if (p.market.of < minCharts || !finite(p.market.value)) return;
      if (!byPos.has(p.row.pos)) byPos.set(p.row.pos, []);
      byPos.get(p.row.pos).push(p);
    });
    byPos.forEach(list => {
      const oursDesc = list.map(p => p.ours).sort((a, b) => b - a);
      const byOurs = list.slice().sort((a, b) => b.ours - a.ours || a.order - b.order);
      const ourRank = new Map(byOurs.map((p, i) => [p, i + 1]));
      list.slice().sort((a, b) => b.market.value - a.market.value || a.order - b.order).forEach((p, i) => {
        const m = p.market;
        m.marketRank = i + 1;
        m.ourRank = ourRank.get(p);
        m.oursAtRank = oursDesc[i];
        m.rankGap = oursDesc[i] - p.ours;
        m.buyScore = Math.abs(m.rankGap) * Math.min(p.ours, m.value);
      });
    });
  }

  // JEG-677 (Jeremy, JEG-461 2026-10-08): the market consensus is the MEDIAN of the indexed charts that
  // price the player (a finite 0 counts: at or below that chart's waiver line; a null is left out and
  // counted in `left`). Eligible as a target only with minCharts+ charts (JEG-851: 1 for a single compared
  // chart, 2 otherwise), a consensus above the waiver line, and a strict majority of the charts on the same
  // side of our value as the consensus. gap = consensus - ours:
  // above 0 sells, below 0 buys. `agree` of `of` charts is shown on the row; `dots` is one entry per
  // chart (above / below / level against our value). diff = our value - consensus; equal says the two
  // match to one decimal as shown, so the page shows a note instead of a duplicate number.
  // JEG-851: minCharts defaults to 2 (the consensus rule); with exactly one compared chart it is 1.
  function marketConsensus(ours, cells, minCharts) {
    const keys = Object.keys(cells);
    const priced = keys.filter(key => finite(cells[key].value));
    const left = keys.length - priced.length;
    const none = {value: null, count: priced.length, of: priced.length, left, diff: null, gap: null, equal: false,
      side: null, agree: 0, eligible: false, dots: [], weight: null, score: null,
      marketRank: null, ourRank: null, oursAtRank: null, rankGap: null, buyScore: null};
    if (!priced.length) return none;
    const values = priced.map(key => cells[key].value);
    const value = median(values);
    const diff = ours - value;
    const gap = value - ours;
    const side = gap > 0 ? "sell" : gap < 0 ? "buy" : null;
    const agree = side ? values.filter(v => (side === "sell" ? v > ours : v < ours)).length : 0;
    const dots = priced.map(key => ({chart: key, value: cells[key].value, side: cells[key].value > ours ? "above" : cells[key].value < ours ? "below" : "level"}));
    const eligible = Boolean(side) && priced.length >= minCharts && value > 0 && agree * 2 > priced.length;
    // JEG-820: the value at stake and the ranking score (see SELL_FLOOR above).
    const weight = Math.min(ours, value);
    const score = Math.abs(gap) * weight;
    return {value, count: priced.length, of: priced.length, left, diff, gap, equal: ours.toFixed(1) === value.toFixed(1),
      side, agree, eligible, dots, weight, score,
      marketRank: null, ourRank: null, oursAtRank: null, rankGap: null, buyScore: null};   // filled by rankEquivalents
  }

  // JEG-842: "out" = the engine flagged ESPN projecting him at 0 (row.espnProjectsZero, the "ESPN: 0 (out)" chip);
  // "estimated" = row.estimated names a compared chart whose value the engine filled in.
  function unreliableSupport(row, cells) {
    if (row.espnProjectsZero) return "out";
    const est = row.estimated || {};
    return Object.keys(cells).some(key => finite(cells[key].value) && est[key]) ? "estimated" : null;
  }

  // charts: the chart keys to compare (already filtered for availability and week). Their values are the engine's Indexed series
  // (each publisher's chart rescaled to our point scale), never the adjusted (_adj_values) or native ones.
  // opts.ours: which engine series is our value (default DDF Value). opts.keep: a row predicate for a name search
  // (JEG-833): ranks are computed over every row, then only the kept players are compared and listed.
  function buildTargets(rows, charts, opts) {
    const ourKey = (opts && opts.ours) || OUR_KEY;
    if (!OUR_KEYS.includes(ourKey)) throw new Error(`not an our-value series: ${ourKey}`);
    // JEG-851: when our value is a chart key, exclude it from the compared charts (self-comparison is meaningless).
    const effectiveCharts = CHART_KEYS.includes(ourKey) ? charts.filter(c => c !== ourKey) : charts;
    // JEG-851: with exactly one compared chart, a single voter suffices; otherwise the consensus needs 2+.
    const minCharts = effectiveCharts.length === 1 ? 1 : 2;
    const keep = opts && typeof opts.keep === "function" ? opts.keep : null;
    let players = [];
    let omittedNoOurs = 0;
    let atWaiverCells = 0;
    rows.forEach((row, index) => {
      const ours = row.values ? row.values[ourKey] : null;
      if (!finite(ours)) {
        omittedNoOurs += 1;
        return;
      }
      const cells = {};
      effectiveCharts.forEach(chart => {
        const value = row.values[chart];
        if (!finite(value)) {
          // JEG-541: the engine's own reason first (after JEG-508 a chart is null only when the engine
          // says why, e.g. "Not enough shared players to index"), then the generic line.
          const own = row.missingReasons ? row.missingReasons[chart] : null;
          cells[chart] = {value: null, gap: null,
            reason: typeof own === "string" && own.trim() ? own : `Not on ${CHART_NAMES[chart] || chart}'s chart`};
          return;
        }
        if (value <= 0) {
          atWaiverCells += 1;
          cells[chart] = {value, gap: null, atWaiver: true, reason: `At ${CHART_NAMES[chart] || chart}'s waiver line for your league`};
          return;
        }
        const gap = value - ours;
        cells[chart] = {value, gap, reason: null};
      });
      players.push({row, order: index + 1, ours, cells, market: marketConsensus(ours, cells, minCharts)});
    });
    rankEquivalents(players, minCharts);
    if (keep) players = players.filter(p => keep(p.row));
    // JEG-820: biggest weighted gap first (score), engine order breaks ties; Sell needs ours >= SELL_FLOOR.
    const byScore = (a, b) => b.market.score - a.market.score || a.order - b.order;
    const sellable = players.filter(p => p.market.eligible && p.market.side === "sell");
    const sellAll = sellable.filter(p => p.ours >= SELL_FLOOR).sort(byScore);
    const belowSellFloor = sellable.length - sellAll.length;
    // JEG-833: Buy needs the charts to rank the player lower than we do by BUY_RANK_MARGIN points at his position;
    // biggest |rankGap| x value at stake first. The others are the scale, not a mispricing (scaleOnly, named by ours).
    const buyable = players.filter(p => p.market.eligible && p.market.side === "buy");
    const buyAll = buyable.filter(p => finite(p.market.rankGap) && p.market.rankGap <= -BUY_RANK_MARGIN)
      .sort((a, b) => b.market.buyScore - a.market.buyScore || a.order - b.order);
    // JEG-842: a player whose support is out (ESPN zeroed him) or estimated (a compared chart's value was filled
    // in from other charts) is never recommended, on either side; counted and named so the page can say so.
    const flagged = p => Boolean(unreliableSupport(p.row, p.cells));
    const sell = sellAll.filter(p => !flagged(p));
    const buy = buyAll.filter(p => !flagged(p));
    const leftOut = buyAll.filter(flagged).concat(sellAll.filter(flagged));
    const listed = new Set(buyAll);
    const scaleOnly = buyable.filter(p => !listed.has(p)).sort((a, b) => b.ours - a.ours || a.order - b.order);
    return {ours: ourKey, sell, buy, players, compared: players.length, omittedNoOurs, atWaiverCells, belowSellFloor,
      leftOut: leftOut.length, leftOutNames: leftOut.slice(0, 5).map(p => p.row.name),
      scaleOnly: scaleOnly.length, scaleOnlyNames: scaleOnly.slice(0, 5).map(p => p.row.name),
      singleChart: effectiveCharts.length === 1 ? effectiveCharts[0] : null};
  }

  // Chart columns to compare: every available published chart (JEG-459). A
  // chart that has not published this week yet is still compared on its
  // latest week and listed in `prior`, so the page can badge it.
  function chartsToCompare(sourceInfo, opts) {
    const byKey = Object.fromEntries((sourceInfo || []).map(item => [item.key, item]));
    const only = opts && opts.only;
    const used = [];
    const skipped = [];
    const prior = [];
    CHART_KEYS.forEach(key => {
      if (only && only !== key) return;
      const item = byKey[key];
      if (!item || !item.available) skipped.push({key, reason: unavailableReason(item)});
      else used.push(key);
      if (item && item.available && item.stale) prior.push(key);
    });
    return {used, skipped, prior};
  }

  // Our-value choices at this league setting: unavailable ones carry a reason.
  function ourChoices(sourceInfo) {
    const byKey = Object.fromEntries((sourceInfo || []).map(item => [item.key, item]));
    return OUR_KEYS.map(key => {
      const item = byKey[key];
      const available = Boolean(item && item.available);
      return {key, available, reason: available ? null : unavailableReason(item)};
    });
  }
  // JEG-807: a held source (JEG-569, hidden from the page) says so; "not available for this league" is a
  // source with no values at this setting.
  function unavailableReason(item) {
    if (item && item.excludedReason && /^held/i.test(item.excludedReason)) return "held this week (data check)";
    return item && item.paused ? "waiting on fresh inputs" : "not available for this league";
  }

  // ---------- Check 2: potential positional weight inflation (JEG-476, JEG-489) ----------
  // Does the market spend its value budget on a position (or a position's starters / bench) in
  // different proportions than DDF Value does? Raw totals cannot say: a per-player median sits under
  // the mean and one chart's whole scale can sit 20% under another's, which read as "underweighted"
  // everywhere. So each group is compared by SHARE, over the same players on both sides:
  //
  //   gap = (group share of the market total) / (group share of the DDF Value total) - 1
  //
  // Market = the consensus (median of the compared charts that price the player, 2+ charts) or one
  // chart. A positive gap says the market overweights the group (sell it); negative, underweights it (buy).
  const WEIGHT_POSITIONS = ["QB", "RB", "WR", "TE"];
  const WEIGHT_TIERS = ["starter", "bench"];
  const WEIGHT_SIGNAL = 0.10;       // +/-10%: sell / buy this group
  const WEIGHT_MIN_SHOW = 3;        // fewer players than this: no number
  const WEIGHT_MIN_HEADLINE = 8;    // fewer players than this: never named in the headline

  function median(values) {
    const sorted = values.slice().sort((a, b) => a - b);
    const mid = sorted.length >> 1;
    return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  function weightSignal(gap) {
    if (!finite(gap)) return null;
    return gap >= WEIGHT_SIGNAL ? "sell" : gap <= -WEIGHT_SIGNAL ? "buy" : "fair";
  }

  // rows: engine rows (all positions). charts: chart keys to compare. opts.ours: the DDF Value key.
  function weightCheck(rows, charts, opts) {
    const oursKey = (opts && opts.ours) || DDF_VALUE_KEY;
    const columns = ["consensus"].concat(charts);
    const marketOf = (row, column) => {
      if (column !== "consensus") return finite(row.values[column]) ? row.values[column] : null;
      const priced = charts.map(chart => row.values[chart]).filter(finite);
      return priced.length >= 2 ? median(priced) : null;
    };
    const groupKeys = [];
    WEIGHT_POSITIONS.forEach(pos => {
      groupKeys.push({key: pos, pos, tier: null});
      WEIGHT_TIERS.forEach(tier => groupKeys.push({key: `${pos}|${tier}`, pos, tier}));
    });
    const inGroup = (row, group) => row.pos === group.pos && (!group.tier || row.ddfTier === group.tier);
    const pairs = {};
    columns.forEach(column => {
      pairs[column] = rows.filter(row => row.values)
        .map(row => ({row, ours: row.values[oursKey], market: marketOf(row, column)}))
        .filter(p => finite(p.ours) && finite(p.market) && WEIGHT_POSITIONS.includes(p.row.pos));
    });
    const sum = (list, field) => list.reduce((total, p) => total + p[field], 0);
    const groups = groupKeys.map(group => {
      const byColumn = {};
      columns.forEach(column => {
        const all = pairs[column];
        const members = all.filter(p => inGroup(p.row, group));
        const totalOurs = sum(all, "ours");
        const totalMarket = sum(all, "market");
        const ours = sum(members, "ours");
        const market = sum(members, "market");
        const shown = members.length >= WEIGHT_MIN_SHOW && ours > 0 && totalOurs > 0 && totalMarket > 0;
        const gap = shown ? (market / totalMarket) / (ours / totalOurs) - 1 : null;
        byColumn[column] = {n: members.length, gap, signal: weightSignal(gap)};
      });
      return {...group, n: byColumn.consensus.n, cells: byColumn, consensus: byColumn.consensus};
    });
    // Players behind a group, sorted by the group's signal: a sell group lists the biggest overpay first,
    // a buy group the biggest underpay first, a fairly priced group the largest gap either way.
    const playersOf = group => {
      const signal = group.consensus.signal;
      const list = pairs.consensus.filter(p => inGroup(p.row, group)).map(p => ({
        row: p.row, ours: p.ours, market: p.market, gap: p.market - p.ours,
        charts: Object.fromEntries(charts.map(chart => [chart, finite(p.row.values[chart]) ? p.row.values[chart] : null]))}));
      list.sort((a, b) => signal === "buy" ? a.gap - b.gap : signal === "sell" ? b.gap - a.gap : Math.abs(b.gap) - Math.abs(a.gap));
      return list;
    };
    // Headline: the biggest consensus gaps among groups large enough to name (8+ players).
    const nameable = groups.filter(g => g.consensus.n >= WEIGHT_MIN_HEADLINE && finite(g.consensus.gap));
    const over = nameable.filter(g => g.consensus.gap > 0).sort((a, b) => b.consensus.gap - a.consensus.gap)[0] || null;
    const under = nameable.filter(g => g.consensus.gap < 0).sort((a, b) => a.consensus.gap - b.consensus.gap)[0] || null;
    const biggest = nameable.slice().sort((a, b) => Math.abs(b.consensus.gap) - Math.abs(a.consensus.gap))[0] || null;
    return {ours: oursKey, columns, groups, playersOf, headline: {over, under, biggest}, compared: pairs.consensus.length};
  }

  const api = {OUR_KEY, DDF_VALUE_KEY, OUR_KEYS, OUR_NAMES, OUR_SHORT, CHART_KEYS, CHART_NAMES, SELL_FLOOR, BUY_RANK_MARGIN, buildTargets, chartsToCompare, ourChoices,
    weightCheck, weightSignal, WEIGHT_POSITIONS, WEIGHT_TIERS, WEIGHT_SIGNAL, WEIGHT_MIN_SHOW, WEIGHT_MIN_HEADLINE};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TradeValueTargets = api;
})(typeof window !== "undefined" ? window : globalThis);
