/* Waivers tab (JEG-1022): should I pick anyone up, and who do I drop?
 *
 * Part 1 (this file, top): the pure rules. Nothing here prices a player: every number comes from finder.js
 * (pickStarters, lineupValue, rosterImpact, teamFit's noise floor, rosterBalance) on the engine's own rows.
 * Part 2 (browser only, below the module.exports line): the tab.
 *
 * Spec: fantasy-tools-selfhost-notes/jeg-waivers-tab/spec.md. Deviations are listed in docs/claude-log/2026-10-24-jeg-1022-waivers.md.
 */
(function (root) {
  "use strict";
  const isNode = typeof module !== "undefined" && module.exports;
  const F = isNode ? require("./finder.js") : root.TradeValueFinder;
  const {pickStarters, lineupValue, rosterImpact, withChartAverage, rosterBalance, teamFit, valueNoise, isNotEvaluated, OUR_KEY, MARKET_KEY,
    FIT_Z, USABLE_MIN, DEPTH_POS} = F;
  const finite = value => typeof value === "number" && Number.isFinite(value);
  const SLOT_KEYS = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"];
  const MAX_PAIRS = 100;             // the two-for-two search looks at no more than this many candidate pairs
  const NET_FLOOR = 0.05;            // a change that shows as 0.0 is no change (same floor as finder.js)
  const OUT_STATUS = ["Out", "Doubtful", "IR", "PUP"];

  // JEG-1081 (PR 6): the view that decides the verdict. ddf = DDF Value (adjusted trade charts, the default), projections = DDF Value
  // (projections), market = Trade chart average, basis = whatever the Overrides basis makes DDF Value (same key as ddf), src:<key> = one source alone.
  const PROJ_KEY = "ddf_value_projections";
  const VIEW_DEFAULT = "ddf";
  const SOURCE_NAMES = {fantasycalc: "FantasyCalc", usatoday: "USA Today", fantasypros: "FantasyPros", cbs: "CBS Sports", espn: "ESPN", cbsros: "CBS rest of season", razzball: "Razzball"};
  // id -> {id, key, label, short}. label heads the verdict; short names the view in the "+x on ..." context. Unknown ids fall back to the default.
  function viewFor(id, basisName) {
    if (id === "projections") return {id, key: PROJ_KEY, label: "DDF Value (projections)", short: "projections"};
    if (id === "market") return {id, key: MARKET_KEY, label: "Trade chart average", short: "market"};
    if (id === "basis") return {id, key: OUR_KEY, label: basisName ? `Overrides basis (${basisName})` : "Overrides basis", short: "Overrides basis"};
    if (typeof id === "string" && id.startsWith("src:") && SOURCE_NAMES[id.slice(4)]) return {id, key: id.slice(4), label: SOURCE_NAMES[id.slice(4)], short: SOURCE_NAMES[id.slice(4)]};
    return {id: VIEW_DEFAULT, key: OUR_KEY, label: "DDF Value", short: "DDF Value"};
  }
  const CONTEXT_VIEWS = ["ddf", "projections", "market"];
  // A player's value in a view: null when the view cannot price him (a market value that shows 0.0 is no price).
  const viewValueOf = (row, key) => {
    const v = row && row.values ? row.values[key] : null;
    return finite(v) && (key !== MARKET_KEY || v >= USABLE_MIN) ? v : null;
  };

  const VERDICT = {pick: "Pick up", force: "Pick up (force)", consider: "Consider", hold: "Hold", skip: "Skip", none: "Not evaluated"};
  const TIER = {[VERDICT.pick]: 0, [VERDICT.force]: 1, [VERDICT.consider]: 2, [VERDICT.hold]: 3, [VERDICT.skip]: 4, [VERDICT.none]: 5};

  const keyOf = row => String(row.player_key);
  const ddfOf = row => (row && row.values && finite(row.values[OUR_KEY]) ? row.values[OUR_KEY] : null);
  // The Trade chart average, or null: a player no chart prices (or prices at a shown 0.0) has no market value to show.
  const marketOf = row => (row && row.values && finite(row.values[MARKET_KEY]) && row.values[MARKET_KEY] >= USABLE_MIN ? row.values[MARKET_KEY] : null);
  const fmt = n => (Math.abs(n) < NET_FLOOR ? "0.0" : (n > 0 ? "+" : "−") + Math.abs(n).toFixed(1));
  const settle = n => Math.round(n * 1e9) / 1e9;
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

  // ---------- roster entries to rows ----------
  // A roster entry ({key, name, pos, team}) becomes the engine's row; a kicker or defense (no engine row) becomes an
  // unpriced row that sits on the roster and in no sum. byKey: Map(player_key -> engine row). Unknown evaluated keys
  // are returned as gone (never guessed).
  function rowsFor(entries, byKey) {
    const rows = [];
    const gone = [];
    (entries || []).forEach(entry => {
      const row = byKey.get(String(entry.key));
      if (row) rows.push(row);
      else if (isNotEvaluated(entry)) rows.push({player_key: String(entry.key), name: entry.name, pos: entry.pos, team: entry.team || "", values: {}, notEvaluated: true});
      else gone.push(entry);
    });
    return {rows, gone};
  }
  // Candidates the roster already has are dropped; so are repeats. Returns the kept entries and the two counts.
  function dedupe(candidates, roster) {
    const mine = new Set((roster || []).map(p => String(p.key)));
    const seen = new Set();
    const kept = [];
    let onRoster = 0;
    let repeats = 0;
    (candidates || []).forEach(c => {
      const key = String(c.key);
      if (mine.has(key)) { onRoster += 1; return; }
      if (seen.has(key)) { repeats += 1; return; }
      seen.add(key);
      kept.push(c);
    });
    return {kept, onRoster, repeats};
  }

  // ---------- who to drop ----------
  // A roster's worth in one view: the best lineup's starter value in full plus the bench at the engine's bench weights
  // (the share of starts the bench takes, per position: the same weights the fit rule uses; Jeremy / coordinator,
  // 2026-10-24: a bench player never counts at full weight). weights: {overall, QB, RB, WR, TE}.
  const netOf = (l, key, weights) => l.starterValue + l.bench.reduce((t, r) => t + F.benchWeight(weights, r.pos) * r.values[key], 0);
  // Loss in worth (starters in full + weighted bench) if the player left with no replacement. A kicker, defense or player
  // with no DDF Value contributes nothing, so leaves at 0.
  function marginalValue(roster, row, shape, key, weights) {
    const before = netOf(lineupValue(roster, shape, key), key, weights);
    const after = netOf(lineupValue(roster.filter(r => r !== row), shape, key), key, weights);
    return Math.max(0, settle(before - after));
  }
  // Kickers and defenses the league requires are not offered as drops (dropping the only kicker leaves a slot empty);
  // a surplus one is. shape.K / shape.DST (the engine's slots) set how many are required.
  function isRequiredSpecial(row, roster, shape) {
    if (!isNotEvaluated(row)) return false;
    const group = row.pos === "K" ? "K" : "DST";
    const need = (shape && shape[group]) || 0;
    const have = roster.filter(r => isNotEvaluated(r) && (r.pos === "K" ? "K" : "DST") === group).length;
    return have <= need;
  }
  // Drop candidates, best first: lowest marginal value; then a kicker / defense; then lower DDF Value, lower market value, name.
  function dropRanking(roster, shape, key, weights) {
    const list = roster.filter(r => !isRequiredSpecial(r, roster, shape))
      .map(row => ({row, marginal: marginalValue(roster, row, shape, key, weights)}));
    // In a view other than DDF Value, a player that view cannot price (no value there) is not offered as a drop while a priced player is.
    const unpriced = r => key !== OUR_KEY && !isNotEvaluated(r) && viewValueOf(r, key) === null;
    return list.sort((a, b) => Number(unpriced(a.row)) - Number(unpriced(b.row)) || a.marginal - b.marginal
      || Number(isNotEvaluated(b.row)) - Number(isNotEvaluated(a.row))
      || (ddfOf(a.row) || 0) - (ddfOf(b.row) || 0)
      || (marketOf(a.row) || 0) - (marketOf(b.row) || 0)
      || String(a.row.name).localeCompare(String(b.row.name)) || keyOf(a.row).localeCompare(keyOf(b.row)));
  }
  // The n best drops one after the other (each marginal is recomputed on what is left).
  function bestDrops(roster, shape, key, n, weights) {
    const out = [];
    let left = roster;
    for (let i = 0; i < n; i++) {
      const ranked = dropRanking(left, shape, key, weights);
      if (!ranked.length) break;
      out.push(ranked[0]);
      left = left.filter(r => r !== ranked[0].row);
    }
    return out;
  }
  // Roster spots still open: the league's roster size less the players held (null when the size is unknown).
  const openSlots = (roster, size) => (finite(size) ? Math.max(0, size - roster.length) : 0);
  function rosterSizeOf(shape) {
    if (!shape) return null;
    const total = SLOT_KEYS.concat(["BENCH", "K", "DST"]).reduce((n, k) => n + (finite(shape[k]) ? shape[k] : 0), 0);
    return total > 0 ? total : null;
  }

  // ---------- one candidate ----------
  function slotOf(lineup, row) {
    return SLOT_KEYS.find(slot => (lineup.slots[slot] || []).includes(row)) || null;
  }
  const depthText = (depth, pos) => `${pos} (${depth[pos].before} counted, ${depth[pos].range} expected)`;
  function byeNote(ctx, roster, shape, candidate, lineup) {
    const byes = ctx.byes;
    if (!byes || !candidate.team || !finite(byes[candidate.team])) return null;
    const starters = lineup.starters.filter(r => r.pos === candidate.pos && finite(byes[r.team]));
    const weeks = {};
    starters.forEach(r => { weeks[byes[r.team]] = (weeks[byes[r.team]] || 0) + 1; });
    const clash = Object.keys(weeks).map(Number).filter(w => weeks[w] >= 2 && w !== byes[candidate.team]).sort((a, b) => a - b);
    return clash.length ? {pos: candidate.pos, week: clash[0], text: `Fills bye-week gap at ${candidate.pos} week ${clash[0]}.`} : null;
  }
  function injuryNote(roster, lineup, candidate) {
    const hurt = lineup.starters.find(r => r.pos === candidate.pos && OUT_STATUS.includes(r.injury_status));
    return hurt ? {name: hurt.name, status: hurt.injury_status, text: `Your ${hurt.name} is ${hurt.injury_status}, which adds to the need at ${candidate.pos}.`} : null;
  }
  // ctx: {shape, expected, chartKeys, rosterSize, byes}. roster: rows (engine rows plus unpriced kicker / defense rows),
  // all carrying chart_avg when charts are available. candidate: an engine row, or an unpriced row.
  // The worth change of a swap in one view (starters in full, bench at its weights): null when the candidate has no value there.
  function worthChange(roster, leaving, candidate, shape, key, weights) {
    if (viewValueOf(candidate, key) === null) return null;
    const impact = rosterImpact(roster, leaving, [candidate], shape, key);
    return netOf(impact.after, key, weights) - netOf(impact.before, key, weights);
  }
  // "+2.1 on projections, +1.8 on market": the other views' reading of the same swap, for context beside the verdict.
  function contextFor(ctx, roster, leaving, candidate, view) {
    const weights = ctx.weights || {};
    const charts = ctx.chartKeys && ctx.chartKeys.length ? ctx.chartKeys : null;
    const items = CONTEXT_VIEWS.filter(id => id !== view.id).map(id => viewFor(id)).filter(v => v.key !== view.key && (v.key !== MARKET_KEY || charts))
      .map(v => ({id: v.id, short: v.id === "ddf" ? "DDF Value" : v.short, delta: worthChange(roster, leaving, candidate, ctx.shape, v.key, weights)}));
    const text = items.filter(i => i.delta !== null).map(i => `${fmt(i.delta)} on ${i.short}`).join(", ");
    return {items, text};
  }
  function evaluateCandidate(ctx, roster, candidate) {
    const view = ctx.view || viewFor(VIEW_DEFAULT);
    const key = view.key;
    const base = {candidate, name: candidate.name, pos: candidate.pos, ddf: ddfOf(candidate), market: marketOf(candidate), team: candidate.team || "", view: view.id};
    const charts = ctx.chartKeys && ctx.chartKeys.length ? ctx.chartKeys : null;
    const marketText = charts ? (base.market !== null ? ` Trade chart average ${base.market.toFixed(1)}.` : " No market value available.") : "";
    if (isNotEvaluated(candidate)) {
      return {...base, verdict: VERDICT.none, ddf: null, market: null, starterDelta: null, benchDelta: null, totalDelta: null, drop: null, reasonKind: "kdef",
        reason: `${candidate.name}: kickers and defenses are not evaluated.`};
    }
    if (viewValueOf(candidate, key) === null) {
      if (key !== OUR_KEY) {
        return {...base, verdict: VERDICT.none, starterDelta: null, benchDelta: null, totalDelta: null, drop: null, reasonKind: "noview",
          reason: `${candidate.name}: no ${view.label} value, so not evaluated in this view.`};
      }
      return {...base, verdict: VERDICT.none, starterDelta: null, benchDelta: null, totalDelta: null, drop: null, reasonKind: "noddf",
        reason: base.market !== null
          ? `${candidate.name}: no DDF Value, so not evaluated (market value ${base.market.toFixed(1)}).`
          : `${candidate.name}: not in the engine's projections (not evaluated). Search the name on a chart site to check.`};
    }
    const free = openSlots(roster, ctx.rosterSize);
    const weights = ctx.weights || {};
    const drop = free > 0 ? null : dropRanking(roster, ctx.shape, key, weights)[0] || null;
    const leaving = drop ? [drop.row] : [];
    const impact = rosterImpact(roster, leaving, [candidate], ctx.shape, key);
    const fit = teamFit({roster, leaving, arriving: [candidate]}, {shape: ctx.shape, expected: ctx.expected, weights, chartKeys: charts || undefined, z: FIT_Z}, key);
    // Verdicts run on the weighted worth: starters in full, the bench at its weights (fit.net); the raw bench change is kept for the detail.
    const total = fit.net;
    const benchDelta = fit.benchDelta;
    const tau = fit.tau;
    const up = total > tau;
    const down = total < -tau;
    const dropName = drop ? drop.row.name : null;
    const awayAt = fit.awayAt;
    const towardAt = fit.towardAt;
    const slot = slotOf(impact.after, candidate);
    const bye = byeNote(ctx, roster, ctx.shape, candidate, impact.before);
    const injury = injuryNote(roster, impact.before, candidate);
    const verdict = up ? (fit.away ? VERDICT.force : VERDICT.pick) : down ? VERDICT.skip : fit.toward ? VERDICT.consider : VERDICT.hold;
    const dropClause = dropName ? `, drop ${dropName}` : " (open roster slot, no drop needed)";
    const need = towardAt.length ? ` Fills ${towardAt[0]} need (${fit.depth[towardAt[0]].before} counted, ${fit.depth[towardAt[0]].range} expected).` : (fit.toward ? " Fills an open starting slot." : "");
    const stash = slot ? ` Starts immediately at ${slot}.` : " Bench stash; starts if a " + candidate.pos + " is injured or on bye.";
    const extras = (bye ? ` ${bye.text}` : "") + (injury ? ` ${injury.text}` : "");
    const deepens = awayAt.length ? awayAt.map(pos => `${fit.depth[pos].distAfter > fit.depth[pos].distBefore && fit.depth[pos].after > fit.depth[pos].before ? "deepens" : "thins"} ${pos}`).join(" and ") : "moves away from the expected depth";
    let reason;
    if (verdict === VERDICT.pick) reason = `Pick up ${candidate.name}${dropClause}: ${fmt(impact.starterDelta)} starter value, ${fmt(benchDelta)} bench (weighted).${need}${stash}${extras}${marketText}`;
    else if (verdict === VERDICT.force) reason = `Pick up ${candidate.name}${dropClause}: ${fmt(total)} total value, but ${deepens}.${stash}${extras}${marketText}`;
    else if (verdict === VERDICT.consider) reason = `Consider ${candidate.name}${dropName ? ` for ${dropName}` : ""}: value is level (${fmt(total)}, inside the ${tau.toFixed(1)} noise floor), but fills ${towardAt.length ? `a need at ${towardAt[0]}` : "an open starting slot"}.${extras}${marketText}`;
    else if (verdict === VERDICT.hold) {
      const deep = DEPTH_POS.find(pos => fit.depth[pos] && fit.depth[pos].statusBefore === "over" && candidate.pos === pos);
      reason = `No clear gain from ${candidate.name} (${fmt(total)}, inside the ${tau.toFixed(1)} noise floor).${deep ? ` Already deep at ${depthText(fit.depth, deep)}.` : ""}${marketText}`;
    } else reason = `${candidate.name} does not improve the roster (${fmt(total)}${dropName ? ` against ${dropName}` : ""}).${marketText}`;
    const context = contextFor(ctx, roster, leaving, candidate, view);
    if (key !== OUR_KEY || view.id === "basis") reason += ` Judged on ${view.label}.`;
    return {...base, context: context.text, contextItems: context.items, verdict, drop: drop ? drop.row : null, dropMarginal: drop ? drop.marginal : null, openSlot: free > 0,
      starterDelta: impact.starterDelta, benchDelta, rawBenchDelta: impact.benchDelta, totalDelta: total, tau, noise: fit.tau, impact, fit,
      needGain: fit.needBefore - fit.needAfter, awayAt, towardAt, slot, starts: Boolean(slot), bye, injury, reason};
  }
  // Pick up first (biggest gain first), then force, consider (biggest need improvement), hold, skip (least negative first), then not evaluated.
  function orderResults(results) {
    return results.map((r, i) => ({r, i})).sort((a, b) => TIER[a.r.verdict] - TIER[b.r.verdict]
      || (a.r.verdict === VERDICT.consider ? (b.r.needGain || 0) - (a.r.needGain || 0) : 0)
      || (b.r.totalDelta === null ? -1 : 0) - (a.r.totalDelta === null ? -1 : 0)
      || (b.r.totalDelta || 0) - (a.r.totalDelta || 0)
      || (b.r.ddf || 0) - (a.r.ddf || 0) || a.i - b.i).map(x => x.r);
  }

  // ---------- two for two ----------
  // Candidate pairs, at most MAX_PAIRS, drawn from the candidates whose single gain is biggest (so the cap drops the
  // weakest pairs, never a strong one). singles: the evaluated single results (verdict not "Not evaluated").
  function pairsOf(singles) {
    const ranked = singles.slice().sort((x, y) => y.totalDelta - x.totalDelta || (y.ddf || 0) - (x.ddf || 0));
    const all = [];
    for (let i = 0; i < ranked.length; i++) for (let j = i + 1; j < ranked.length; j++) all.push([i, j]);
    all.sort((x, y) => (x[0] + x[1]) - (y[0] + y[1]) || x[0] - y[0]);   // strongest members first, so the cap drops the weakest pairs
    return all.slice(0, MAX_PAIRS).map(([i, j]) => [ranked[i], ranked[j]]);
  }
  // A combo is listed when its total beats the noise floor and beats the better single pickup by more than the noise floor.
  function evaluateCombos(ctx, roster, singles) {
    const valued = singles.filter(r => r.totalDelta !== null);
    if (valued.length < 2) return [];
    const free = openSlots(roster, ctx.rosterSize);
    const need = Math.max(0, 2 - free);
    const weights = ctx.weights || {};
    const key = (ctx.view || viewFor(VIEW_DEFAULT)).key;
    const out = [];
    pairsOf(valued).forEach(([a, b]) => {
      const drops = bestDrops(roster, ctx.shape, key, need, weights);
      if (drops.length < need) return;
      const leaving = drops.map(d => d.row);
      const arriving = [a.candidate, b.candidate];
      const impact = rosterImpact(roster, leaving, arriving, ctx.shape, key);
      const net = netOf(impact.after, key, weights) - netOf(impact.before, key, weights);
      impact.netDelta = net;
      impact.weightedBench = net - impact.starterDelta;
      const noise = Math.sqrt(leaving.concat(arriving).reduce((t, r) => t + Math.pow(valueNoise(r, key, ctx.chartKeys || undefined), 2), 0));
      const tau = Math.max(NET_FLOOR, FIT_Z * noise);
      const best = Math.max(a.totalDelta, b.totalDelta);
      // It must clear the noise floor, and what it adds over the better single pickup must clear it too.
      if (!(net > tau) || !(net - best > tau)) return;
      const names = rows => rows.map(r => r.name).join(" + ");
      out.push({candidates: [a.candidate, b.candidate], drops: leaving, starterDelta: impact.starterDelta, benchDelta: impact.weightedBench,
        totalDelta: net, tau, bestSingle: best, impact,
        text: `Pick up ${names(arriving)}${leaving.length ? `, drop ${names(leaving)}` : " (open roster slots)"}: ${fmt(net)} total value (${fmt(impact.starterDelta)} starters, ${fmt(impact.weightedBench)} bench, weighted).`});
    });
    return out.sort((x, y) => y.totalDelta - x.totalDelta);
  }

  // ---------- the whole tab ----------
  // The headline: the best single pickup in one sentence, else the best two-for-two, else "no pickup".
  function headlineFor(results, combos, view) {
    const h = headlineBase(results, combos);
    const on = view && (view.key !== OUR_KEY || view.id === "basis") ? ` (judged on ${view.label})` : "";
    return {...h, text: `${h.text}${on}`, context: h.best && h.best.context ? h.best.context : ""};
  }
  function headlineBase(results, combos) {
    const first = verdict => results.find(r => r.verdict === verdict);
    const pick = first(VERDICT.pick);
    const force = first(VERDICT.force);
    const consider = first(VERDICT.consider);
    const gain = r => (r.starterDelta >= NET_FLOOR ? `${fmt(r.starterDelta)} starter value` : `${fmt(r.totalDelta)} bench value`);
    const dropPart = r => (r.drop ? `, drop ${r.drop.name}` : " (open roster slot)");
    if (pick) return {state: "pick", text: `Pick up ${pick.name}${dropPart(pick)}: ${gain(pick)}`, best: pick};
    if (force) return {state: "force", text: `Pick up ${force.name}${dropPart(force)}: ${gain(force)}, but it moves you away from the expected depth`, best: force};
    if (combos && combos.length) return {state: "combo", text: `No single pickup improves your roster, but two together do: ${combos[0].text.replace(/ total value.*$/, " total value")}`, best: combos[0]};
    if (consider) return {state: "consider", text: `No clear pickup, but consider ${consider.name} for roster balance`, best: consider};
    return {state: "none", text: "No pickup improves your roster this week", best: null};
  }
  // entries -> everything the tab shows. mine: roster rows (rowsFor); cands: candidate rows; ctx as evaluateCandidate.
  function evaluateAll(ctx, mineRows, candRows) {
    const charts = ctx.chartKeys && ctx.chartKeys.length >= 1 ? ctx.chartKeys : null;
    const withMarket = rows => (charts ? withChartAverage(rows, charts) : rows);
    const roster = withMarket(mineRows);
    const results = orderResults(withMarket(candRows).map(c => evaluateCandidate(ctx, roster, c)));
    const combos = evaluateCombos(ctx, roster, results.filter(r => r.totalDelta !== null));
    return {roster, results, combos, view: ctx.view || viewFor(VIEW_DEFAULT), headline: headlineFor(results, combos, ctx.view)};
  }

  // ---------- the share link ----------
  // #waivers?mine=k1,k2&cands=k3,k4&<league settings as in Compare a trade's link>. league: a query string (no "?").
  function encodeHash(mineKeys, candKeys, league) {
    const enc = list => list.map(k => encodeURIComponent(String(k))).join(",");
    const parts = [];
    if (mineKeys.length) parts.push(`mine=${enc(mineKeys)}`);
    if (candKeys.length) parts.push(`cands=${enc(candKeys)}`);
    if (parts.length && league) parts.push(league);
    return `#waivers${parts.length ? `?${parts.join("&")}` : ""}`;
  }
  function decodeHash(hash) {
    const [base, query] = String(hash || "").split("?");
    if (base !== "#waivers" || !query) return {mine: [], cands: [], params: new URLSearchParams()};
    const params = new URLSearchParams(query);
    const read = name => {
      const seen = new Set();
      return (params.get(name) || "").split(",").map(k => decodeURIComponent(k).trim()).filter(k => k && !seen.has(k) && seen.add(k));
    };
    return {mine: read("mine"), cands: read("cands"), params};
  }

  const api = {VERDICT, TIER, MAX_PAIRS, NET_FLOOR, OUT_STATUS, rowsFor, dedupe, netOf, marginalValue, dropRanking, bestDrops, openSlots, rosterSizeOf, evaluateCandidate,
    orderResults, pairsOf, evaluateCombos, headlineFor, evaluateAll, viewFor, viewValueOf, worthChange, contextFor, VIEW_DEFAULT, CONTEXT_VIEWS, SOURCE_NAMES, encodeHash, decodeHash, ddfOf, marketOf, fmt, isRequiredSpecial};
  if (isNode) { module.exports = api; return; }
  root.TradeValueWaivers = api;

  // ======================= the tab (browser only) =======================
  const $ = id => document.getElementById(id);
  const engine = () => root.TradeValueCurveControls;
  const UI = () => F.ui;   // finder.js's page helpers: the one assessment table and the one "my roster"
  const CHART_NAMES = {usatoday: "USA Today", fantasycalc: "FantasyCalc", fantasypros: "FantasyPros", cbs: "CBS Sports"};
  const CHART_KEYS = ["usatoday", "fantasycalc", "fantasypros", "cbs"];
  const VORP_KEYS = ["espn_vorp", "cbsros_vorp", "razzball_vorp"];
  const STORE_MINE = "ddf.v2.myRoster";
  const STORE_CANDS = "ddf.v2.waiverCandidates";
  const STORE_VIEW = "ddf.v2.waivers.view";
  const MIN_MATCHED = 3;
  const MIN_SHARE = 0.5;
  const NAME_LIST_SHARE = 0.8;
  const SLOT_WORD = {SUPERFLEX: "Superflex"};
  const boxes = {};
  const S = {view: (() => { try { return root.localStorage.getItem("ddf.v2.waivers.view") || "ddf"; } catch (error) { return "ddf"; } })(), viewSig: "", cands: [], sort: {key: "verdict", dir: "asc"}, collapsed: false, hadResults: false, backSig: "", focusAfterUndo: false, answered: new Set(), linkRead: false, scheduled: false,
    notes: [], last: null, mineSig: ""};

  function el(tag, props, ...kids) {
    const node = document.createElement(tag);
    Object.entries(props || {}).forEach(([k, v]) => { if (k === "text") node.textContent = v; else node.setAttribute(k, v); });
    node.append(...kids.filter(Boolean));
    return node;
  }
  const readJson = key => { try { const raw = root.localStorage.getItem(key); return raw ? JSON.parse(raw) : null; } catch (error) { return null; } };
  const writeJson = (key, value) => { try { root.localStorage.setItem(key, JSON.stringify(value)); } catch (error) { /* private window or full: the tab still works */ } };
  const keep = list => list.map(p => ({key: String(p.key), name: p.name, pos: p.pos, team: p.team || ""}));

  // "My roster" is ONE list across Find a trade (the league's marked team and the two-team card) and Waivers (Jeremy, 2026-10-24):
  // the league workspace store (workspace.js, JEG-1021, store-api.md) holds it; this tab keeps no second copy.
  const WS = () => root.TradeValueWorkspace.store;
  const mineStore = {
    get: () => WS().getMyRoster(),
    set: list => { WS().setMyRoster(list); },
    subscribe: fn => { WS().subscribe(fn); }
  };
  const candStore = {
    get: () => S.cands,
    set: list => { S.cands = keep(list); writeJson(STORE_CANDS, S.cands); }
  };
  const stores = {mine: mineStore, cands: candStore};
  const TITLES = {mine: "Your roster", cands: "Waiver candidates"};

  const rowsAll = () => (engine() ? engine().getAllRows() : []);
  const rowMap = () => new Map(rowsAll().map(r => [String(r.player_key), r]));
  const teamCode = team => { const paste = root.DDFRosterPaste; return (paste && paste.normTeam ? paste.normTeam(team) : null) || String(team || "").toUpperCase(); };
  const cleanLine = line => (root.DDFRosterPaste ? root.DDFRosterPaste.cleanYahooName(String(line || "")) : String(line || ""))
    .replace(/\s+[A-Z]{2,4},\s*(QB|RB|WR|TE|K|DEF|D\/ST)$/, "").replace(/\s*D\/?ST$/i, "").trim();
  // Every defense and the kickers on a team, by name, as unpriced entries (the same list Find a trade's search offers).
  function notEvaluatedChoices() {
    const data = root.TradeValueKDef || {};
    const choose = (list, pos) => (list || []).filter(item => item && item.name).map(item => {
      const team = teamCode(item.team);
      return {player_key: pos === "DEF" ? `x:DEF:${team}` : `x:K:${F.normName(item.name)}`, name: item.name, pos, team, notEvaluated: true};
    });
    return choose(data.defenses, "DEF").concat(choose(data.kickers, "K"));
  }
  const entryOfRow = row => ({key: String(row.player_key), name: row.name, pos: row.pos, team: row.team || ""});
  const specialEntry = u => {
    const name = cleanLine(u.line || u.name);
    return name ? {key: `x:${u.pos}:${u.team || F.normName(name)}`, name, pos: u.pos, team: u.team || ""} : null;
  };

  // ---------- the number cells ----------
  function valueAboveWaivers(row) {
    const vals = VORP_KEYS.map(k => (row.values ? row.values[k] : null)).filter(v => typeof v === "number" && Number.isFinite(v));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  }
  const dash = () => el("span", {}, el("span", {"aria-hidden": "true", text: "—"}), el("span", {class: "v2-sr", text: "no value"}));
  const numCell = (value, signed) => (value === null || value === undefined ? dash() : document.createTextNode(signed ? api.fmt(value) : value.toFixed(1)));
  const injuryOf = row => (row && row.injury_status && !["Active", "Inactive"].includes(row.injury_status) ? row.injury_status : null);
  const injuryTag = row => (injuryOf(row) ? el("span", {class: "v2-wv-inj", "data-status": injuryOf(row), text: injuryOf(row)}) : null);

  // ---------- the one box ----------
  const chip = (label, value) => el("span", {class: `v2-find-chip${value === null ? " is-missing" : ""}`},
    el("span", {class: "v2-find-chip-value", text: value === null ? "no value" : value.toFixed(1)}), el("span", {class: "v2-find-chip-label", text: ` ${label}`}));
  function placeList(target, listNode) {
    const byKey = rowMap();
    const charts = UI() ? UI().marketKeys() : null;
    listNode.replaceChildren(...stores[target].get().map(p => {
      const row = byKey.get(String(p.key));
      const remove = el("button", {type: "button", class: "v2-link v2-wv-remove", "aria-label": `Remove ${p.name}`, text: "Remove"});
      remove.addEventListener("click", () => {
        stores[target].set(stores[target].get().filter(q => q.key !== p.key));
        schedule();
        const box = $(`v2Waivers${target === "mine" ? "Mine" : "Cands"}Search`);
        if (box) box.focus();
      });
      let tail;
      if (F.isNotEvaluated(p)) tail = el("span", {class: "v2-find-noteval", text: "Not evaluated"});
      else if (!row) tail = el("span", {class: "v2-find-noteval", text: "No longer in the data"});
      else {
        const avg = charts ? withChartAverage([row], charts)[0] : null;
        // JEG-1059: the badge that marks a value the reader set, right after the DDF Value chip.
        const badge = root.DDFOverrides && root.DDFOverrides.flag ? root.DDFOverrides.flag(row) : null;
        tail = el("span", {class: "v2-find-chips"}, chip("DDF Value", api.ddfOf(row)), badge, chip("Trade chart average", avg ? api.marketOf(avg) : null));
      }
      return el("li", {class: "v2-wv-row"}, el("div", {}, el("b", {text: p.name}), el("span", {class: "v2-meta", text: p.pos ? ` ${p.pos}${p.team ? ` ${p.team}` : ""}` : ""}), injuryTag(row) ? document.createTextNode(" ") : null, injuryTag(row), tail), remove);
    }));
  }

  function oneBox(target) {
    const id = `v2Waivers${target === "mine" ? "Mine" : "Cands"}`;
    const title = TITLES[target];
    const list = el("ul", {class: "v2-wv-players", id: `${id}List`});
    const results = el("ul", {class: "v2-trade-results", id: `${id}Results`, hidden: ""});
    const input = el("textarea", {id: `${id}Search`, rows: "1", placeholder: target === "mine" ? "Search a player, or paste your team page" : "Search a player, or paste a waiver wire page",
      autocomplete: "off", spellcheck: "false", "aria-controls": `${id}Results`, "aria-describedby": `${id}Help`});
    const label = el("label", {class: "v2-find-search-label"}, el("span", {class: "v2-sr", text: `Add players to ${title.toLowerCase()}: search by name, or paste a whole page`}), input);
    const help = el("p", {class: "v2-meta v2-find-paste-help", id: `${id}Help`,
      text: target === "mine"
        ? "Type a name to search, or paste your team page: select all and copy on the page (Ctrl+A, Ctrl+C), then paste here. It stays on this device; nothing is sent anywhere."
        : "Type a name to search, or paste a waiver wire page or a list of names. As many as you like: each paste adds to the list. It stays on this device."});
    const result = el("div", {class: "v2-find-paste-result", id: `${id}PasteResult`, role: "status", "aria-live": "polite"});
    const clear = el("button", {type: "button", class: "v2-link v2-find-clear", id: `${id}Clear`, text: "Clear", hidden: "", "aria-label": `Clear ${title.toLowerCase()}`});
    // JEG-1190: Clear says what it did and offers Undo. Your roster is the one shared with both Find a trade screens, so
    // the message says it is cleared there too (Claude's pick under Jeremy's 2026-10-28 rule; see the picks log).
    clear.addEventListener("click", () => {
      const before = stores[target].get().slice();
      stores[target].set([]);
      input.value = "";
      results.replaceChildren();
      results.hidden = true;
      const undo = el("button", {type: "button", class: "v2-link v2-wv-undo", id: `${id}Undo`, text: "Undo"});
      undo.addEventListener("click", () => {
        stores[target].set(before);
        if (target === "mine") {
          // JEG-1316 (option A, pending Jeremy's pick): results fold the roster input again on the next render, so the
          // message goes where it stays visible and focus waits for that render (render() moves it to Edit roster).
          result.replaceChildren();
          S.backSig = rosterSig(before);
          S.focusAfterUndo = true;
        } else result.replaceChildren(el("p", {class: "v2-meta", text: `${title} is back.`}));
        schedule();
        input.focus();
      });
      result.replaceChildren(el("p", {class: "v2-meta v2-wv-cleared"},
        document.createTextNode(target === "mine" ? "Cleared your roster here and on both Find a trade screens. " : `Cleared ${title.toLowerCase()}. `), undo));
      schedule();
      // JEG-1316: an empty roster unfolds its input, but only on the next render; unfold it now so focus can land there.
      if (target === "mine") renderSummary();
      input.focus();
    });
    const wrap = el("div", {class: "v2-wv-input", id: `${id}Input`}, el("div", {class: "v2-find-search-wrap"}, label, results), help, result, list);

    // Add entries (a team page replaces my roster; everything else adds). Returns the entries now on the list.
    function put(entries, replace) {
      const have = replace ? [] : stores[target].get().slice();
      const keys = new Set(have.map(p => p.key));
      entries.forEach(e => { if (!keys.has(e.key)) { keys.add(e.key); have.push(e); } });
      stores[target].set(have);
      schedule();
    }
    const note = (text, cls) => el("p", {class: cls || "v2-meta", text});
    const unmatchedBlock = unmatched => (unmatched.length ? [note(`Not matched (${unmatched.length}): add them by search.`, "v2-find-paste-note"),
      el("ul", {class: "v2-find-unmatched"}, ...unmatched.slice(0, 50).map(u => {
        const b = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "Search to add", "aria-label": `Search to add ${cleanLine(u.line || u.name)}`});
        b.addEventListener("click", () => searchFor(u.line || u.name));
        return el("li", {}, el("span", {text: cleanLine(u.line || u.name)}), el("span", {class: "v2-meta", text: u.reason ? ` (${u.reason})` : ""}), b);
      }))] : []);
    function searchFor(line) {
      input.value = cleanLine(line);
      input.dispatchEvent(new Event("input", {bubbles: true}));
      input.focus();
    }
    const unsureBlock = unsure => (unsure.length ? [note(`Check ${plural(unsure.length, "match")}: not added until you say so.`, "v2-find-paste-note"),
      el("ul", {class: "v2-find-unsure-list"}, ...unsure.map(p => {
        const li = el("li", {class: "v2-find-unsure", "data-unsure-id": String(p.id)});
        const yes = el("button", {type: "button", class: "v2-btn v2-find-confirm", text: "Yes, add", "aria-label": `Yes, add ${p.row.name}`});
        const no = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "No, search", "aria-label": `No, search for ${cleanLine(p.sourceLine)}`});
        li.append(el("span", {text: `Pasted “${cleanLine(p.sourceLine)}”: is this `}), el("b", {text: p.row.name}), el("span", {text: "?"}), yes, no);
        yes.addEventListener("click", () => { put([entryOfRow(p.row)], false); li.replaceChildren(el("span", {text: `Added ${p.row.name}.`})); });
        no.addEventListener("click", () => { li.remove(); searchFor(p.sourceLine); });
        return li;
      }))] : []);
    function ignoredBlock(lines) {
      if (!lines || !lines.length) return null;
      return el("details", {class: "v2-find-ignored"}, el("summary", {text: `Show ${plural(lines.length, "ignored line")}`}),
        el("ul", {class: "v2-find-ignored-list"}, ...lines.slice(0, 50).map(line => {
          const b = el("button", {type: "button", class: "v2-btn v2-find-search-add", text: "Search", "aria-label": `Search for ${cleanLine(line)}`});
          b.addEventListener("click", () => searchFor(line));
          return el("li", {}, el("span", {class: "v2-meta", text: cleanLine(line)}), b);
        })));
    }
    // A pasted page. res: DDFRosterPaste.parse(). team: for a matchup page, which of its two teams.
    function place(res, team, replace) {
      const map = rowMap();
      const players = team !== null && res.teams && res.teams[team] ? res.teams[team].players : res.players;
      const unmatched = team !== null && res.teams && res.teams[team] ? res.teams[team].unmatched : res.unmatched;
      const sure = [];
      const unsure = [];
      players.forEach(p => {
        const row = map.get(String(p.id));
        if (!row) return;
        if (p.confidence >= 1) sure.push(entryOfRow(row)); else unsure.push({...p, row});
      });
      const special = (unmatched || []).filter(F.isNotEvaluated).map(specialEntry).filter(Boolean);
      put(sure.concat(special), replace);
      const rest = (unmatched || []).filter(u => !F.isNotEvaluated(u));
      result.replaceChildren(el("p", {class: `v2-find-paste-count ${sure.length ? "is-ok" : "is-bad"}`, text: `Found ${plural(sure.length + special.length, "player")}${(res.ignoredLines || []).length ? `, ignored ${plural(res.ignoredLines.length, "line")}` : ""}.`}),
        note(`${title} now has ${plural(stores[target].get().length, "player")}.`),
        special.length ? note(`Kept, not evaluated (no value for defenses and kickers): ${special.map(e => `${e.name} (${e.pos})`).join(", ")}.`, "v2-meta v2-find-kept") : null,
        ...unsureBlock(unsure), ...unmatchedBlock(rest), ignoredBlock(res.ignoredLines));
    }
    function consume(text, force) {
      input.value = "";
      results.replaceChildren();
      results.hidden = true;
      const rows = rowsAll();
      if (!rows.length || !root.DDFRosterPaste) { result.replaceChildren(note("Values are still loading. Try again in a moment.")); return; }
      // A clean list of names (80% or more are players) is added directly.
      const lines = F.parsePasted(text);
      const {matched, unmatched} = F.matchNames(lines, rows);
      if (matched.length >= 2 && matched.length >= NAME_LIST_SHARE * lines.length) {
        // A typed defense or kicker name is kept, not evaluated (the same names Find a trade's search offers).
        const choices = new Map(notEvaluatedChoices().map(c => [F.normName(c.name), c]));
        const asSpecial = u => {
          const c = choices.get(F.normName(u.name));
          return c ? {key: String(c.player_key), name: c.name, pos: c.pos, team: c.team || ""} : null;
        };
        const special = unmatched.map(u => (F.isNotEvaluated(u) ? specialEntry(u) : asSpecial(u))).filter(Boolean);
        unmatched.splice(0, unmatched.length, ...unmatched.filter(u => !F.isNotEvaluated(u) && !asSpecial(u)));
        put(matched.map(entryOfRow).concat(special), false);
        const rest = unmatched;
        result.replaceChildren(note(`Added ${plural(matched.length, "player")} from the list.${special.length ? ` Kept, not evaluated: ${special.map(e => e.name).join(", ")}.` : ""}`),
          ...unmatchedBlock(rest));
        return;
      }
      const res = root.DDFRosterPaste.parse(text, rows);
      if (!res) { result.replaceChildren(note("Values are still loading. Try again in a moment.")); return; }
      // A roster page pasted into the waiver list (or a waiver page into the roster) is offered to the other list.
      const kind = root.DDFRosterPaste.detectListKind(text, res);
      const other = target === "mine" ? "cands" : "mine";
      if (!force && res.matched && kind !== "unknown" && kind !== (target === "mine" ? "roster" : "waivers") && boxes[other]) {
        const move = el("button", {type: "button", class: "v2-btn", text: `Use it for ${TITLES[other].toLowerCase()}`});
        move.addEventListener("click", () => { result.replaceChildren(); boxes[other].consume(text, true); });
        const here = el("button", {type: "button", class: "v2-btn", text: `Use it for ${title.toLowerCase()} anyway`});
        here.addEventListener("click", () => consume(text, true));
        result.replaceChildren(el("p", {class: "v2-find-paste-count is-bad", text: kind === "roster" ? "That looks like a roster page, not a waiver page." : "That looks like a waiver page, not your roster."}),
          note("Nothing was added yet."), move, here);
        return;
      }
      if (res.mode === "matchup" && res.teams && res.teams.length === 2 && target === "mine") {
        const label2 = (t, i) => t.teamName || `Team ${i + 1} (listed ${i ? "second" : "first"})`;
        result.replaceChildren(note("This is a matchup page with two teams. Which team is yours?", "v2-find-which"),
          el("div", {class: "v2-find-teams"}, ...res.teams.map((t, i) => {
            const b = el("button", {type: "button", class: "v2-btn v2-find-pick-team", text: `${label2(t, i)} is mine`});
            b.addEventListener("click", () => place(res, i, true));
            return el("div", {class: "v2-find-team"}, el("h4", {text: label2(t, i)}), el("p", {class: "v2-meta", text: `${t.matched} of ${t.total} matched: ${t.players.map(p => p.name).join(", ") || "none"}.`}), b);
          })));
        return;
      }
      if (!res.matched) {
        result.replaceChildren(el("p", {class: "v2-find-paste-count is-bad", text: "No players recognised in that text. Nothing was added."}),
          note("Paste a page from any fantasy site (Ctrl+A, Ctrl+C on the page), or a list of player names. Search and add players by name above."));
        return;
      }
      // My roster: a team page is the whole team; too few matches is not trusted unless asked.
      if (target === "mine" && res.mode !== "extract" && (res.matched < MIN_MATCHED || res.matched / res.total < MIN_SHARE)) {
        const anyway = el("button", {type: "button", class: "v2-btn", text: `Add these ${res.matched} anyway`});
        anyway.addEventListener("click", () => place(res, null, true));
        result.replaceChildren(el("p", {class: "v2-find-paste-count is-bad", text: `Matched ${res.matched} of ${res.total} players.`}),
          note("That is too few to trust, so nothing was added. Paste the whole team page, or search and add players by name above."), anyway);
        return;
      }
      place(res, null, target === "mine");
    }
    input.addEventListener("paste", event => {
      const text = event.clipboardData ? event.clipboardData.getData("text") : "";
      if (text && F.looksLikePage(text)) { event.preventDefault(); consume(text); }
    });
    input.addEventListener("keydown", event => { if (event.key === "Enter" && !event.shiftKey) event.preventDefault(); });
    if (root.TradeValueNameSearch) root.TradeValueNameSearch.combobox(input, results);
    input.addEventListener("input", () => {
      if (F.looksLikePage(input.value)) { consume(input.value); return; }
      const q = input.value.trim();
      results.replaceChildren();
      results.hidden = !q;
      if (!q || !engine() || !root.TradeValueNameSearch) return;
      const onList = stores.mine.get().concat(stores.cands.get());
      const hits = root.TradeValueNameSearch.search(rowsAll().concat(notEvaluatedChoices()), q).slice(0, 8);
      if (!hits.length) results.append(el("li", {class: "is-empty v2-meta", text: `Can't find “${q}”. Check the spelling, or he may not have a value yet.`}));
      hits.forEach(row => {
        const key = String(row.player_key);
        const added = onList.some(p => p.key === key || (F.isNotEvaluated(p) && F.isNotEvaluated(row) && p.pos === row.pos && F.normName(p.name) === F.normName(row.name)));
        const tag = row.notEvaluated ? el("span", {class: "v2-find-noteval", text: "Not evaluated"}) : null;
        const button = el("button", {type: "button"}, `${`${row.name} · ${row.pos || ""} ${row.team || ""}`.trim()}${added ? " ✓ Added" : ""}`, tag);
        if (added) button.disabled = true;
        button.addEventListener("click", () => {
          put([{key, name: row.name, pos: row.pos, team: row.team || ""}], false);
          input.value = "";
          results.replaceChildren();
          results.hidden = true;
          input.focus();
        });
        results.append(el("li", {}, button));
      });
    });
    return {wrap, list, clear, input, result, consume, render: () => { clear.hidden = !stores[target].get().length; placeList(target, list); }};
  }

  // ---------- the results ----------
  const VERDICT_CLASS = {"Pick up": "pick", "Pick up (force)": "force", "Consider": "consider", "Hold": "hold", "Skip": "skip", "Not evaluated": "none"};
  const COLS = [
    {id: "name", label: "Candidate", sort: true, text: true}, {id: "pos", label: "Pos"},
    {id: "ddf", label: "DDF Value", sort: true, num: true}, {id: "vaw", label: "Value above waivers", sort: true, num: true},
    {id: "market", label: "Market value", sort: true, num: true}, {id: "starter", label: "Starter change", sort: true, num: true, signed: true},
    {id: "bench", label: "Bench change", sort: true, num: true, signed: true}, {id: "drop", label: "Best drop"},
    {id: "verdict", label: "Verdict", sort: true}, {id: "reason", label: "Reason"}];
  const cellValue = (r, id) => ({name: r.name, ddf: r.ddf, vaw: r.vaw, market: r.market, starter: r.starterDelta, bench: r.benchDelta}[id]);
  function sortedResults(list) {
    const {key, dir} = S.sort;
    const col = COLS.find(c => c.id === key);
    if (!col || key === "verdict") return dir === "asc" ? list.slice() : list.slice().reverse();
    const sign = dir === "asc" ? 1 : -1;
    return list.map((r, i) => ({r, i})).sort((a, b) => {
      const x = cellValue(a.r, key);
      const y = cellValue(b.r, key);
      const nx = x === null || x === undefined;
      const ny = y === null || y === undefined;
      if (nx !== ny) return nx ? 1 : -1;   // dashes last, whichever way
      if (nx) return a.i - b.i;
      return (col.text ? String(x).localeCompare(String(y)) : x - y) * sign || a.i - b.i;
    }).map(x => x.r);
  }
  const dropText = r => (r.verdict === api.VERDICT.none ? null : r.drop ? r.drop.name : "Open slot");
  const slotLabel = slot => SLOT_WORD[slot] || slot;
  function lineupRows(l) {
    const starters = ["QB", "RB", "WR", "TE", "FLEX", "SUPERFLEX"].flatMap(slot => (l.slots[slot] || []).map(r => ({slot: slotLabel(slot), r})));
    return starters.concat(l.bench.map(r => ({slot: "Bench", r})));
  }
  function lineupTable(title, l, mark) {
    // JEG-1059: the badge that marks a value the reader set, next to the DDF Value number.
    const ddfCell = r => {
      const badge = root.DDFOverrides && root.DDFOverrides.flag ? root.DDFOverrides.flag(r) : null;
      return el("td", {class: "num"}, api.ddfOf(r) === null ? "—" : api.ddfOf(r).toFixed(1), badge);
    };
    const body = lineupRows(l).map(({slot, r}) => el("tr", mark && mark(r) ? {class: "is-new"} : {}, el("td", {text: slot}), el("td", {text: r.name + (mark && mark(r) ? " (new)" : "")}),
      ddfCell(r)));
    return el("div", {class: "v2-find-table-wrap"}, el("table", {class: "v2-find-lineup"},
      el("caption", {text: `${title}: starters ${l.starterValue.toFixed(1)}, bench ${l.benchValue.toFixed(1)}, total ${l.total.toFixed(1)}`}),
      el("thead", {}, el("tr", {}, el("th", {scope: "col", text: "Slot"}), el("th", {scope: "col", text: "Player"}), el("th", {scope: "col", text: "DDF Value"}))), el("tbody", {}, ...body)));
  }
  function marketTable(r, dropRow) {
    const rows = [r.candidate].concat(dropRow ? [dropRow] : []);
    // A chart price that shows as 0.0 is no price: a dash, never zero.
    const cell = (row, k) => (row.values && typeof row.values[k] === "number" && Number.isFinite(row.values[k]) && row.values[k] >= USABLE_MIN ? row.values[k].toFixed(1) : "—");
    return el("div", {class: "v2-find-table-wrap"}, el("table", {class: "v2-find-lineup"}, el("caption", {text: "The Market, by chart"}),
      el("thead", {}, el("tr", {}, el("th", {scope: "col", text: "Player"}), ...CHART_KEYS.map(k => el("th", {scope: "col", text: CHART_NAMES[k]})), el("th", {scope: "col", text: "Average"}))),
      el("tbody", {}, ...rows.map(row => el("tr", {}, el("th", {scope: "row", text: row.name}), ...CHART_KEYS.map(k => el("td", {class: "num", text: cell(row, k)})),
        el("td", {class: "num", text: row.values && api.marketOf(row) !== null ? api.marketOf(row).toFixed(1) : "—"}))))));
  }
  function detailBlock(r, roster) {
    const body = el("div", {class: "v2-wv-detail-body"});
    if (!r.impact) {
      body.append(el("p", {class: "v2-meta", text: r.reason}));
      if (r.market !== null) body.append(marketTable(r, null));
      return body;
    }
    const isNew = x => x === r.candidate;
    body.append(el("div", {class: "v2-wv-lineups"}, lineupTable("Before", r.impact.before), lineupTable("After", r.impact.after, isNew)));
    const depth = DEPTH_POS.filter(pos => r.fit.depth[pos]).map(pos => {
      const d = r.fit.depth[pos];
      return `${pos}: ${d.before} → ${d.after} counted (${d.range} expected)`;
    });
    body.append(el("p", {class: "v2-meta", text: r.fit.ready ? `Depth by position: ${depth.join("; ")}.` : "Depth by position is not judged until the roster has at least as many players as the league has starting slots."}));
    body.append(el("p", {class: "v2-meta", text: `Bench change in raw DDF Value, before the bench weights: ${api.fmt(r.rawBenchDelta)}.`}));
    if (r.bye) body.append(el("p", {class: "v2-meta", text: r.bye.text}));
    if (r.injury) body.append(el("p", {class: "v2-meta", text: r.injury.text}));
    if (UI() && UI().marketKeys()) body.append(marketTable(r, r.drop && !r.drop.notEvaluated ? r.drop : null));
    return body;
  }
  function verdictTag(r) {
    return el("span", {class: "v2-wv-verdict", "data-verdict": VERDICT_CLASS[r.verdict], text: r.verdict});
  }
  function cardFor(r, roster) {
    // JEG-1059: the badge that marks a value the reader set, next to the DDF Value number.
    const ddfBadge = root.DDFOverrides && root.DDFOverrides.flag ? root.DDFOverrides.flag(r.candidate) : null;
    const rowsDef = [["DDF Value", [numCell(r.ddf), ddfBadge]], ["Value above waivers", numCell(r.vaw)], ["Market value", numCell(r.market)],
      ["Starter change", numCell(r.starterDelta, true)], ["Bench change", numCell(r.benchDelta, true)], ["Best drop", dropText(r) || dash()]];
    return el("li", {class: "v2-wv-card", "data-verdict": VERDICT_CLASS[r.verdict]},
      el("div", {class: "v2-wv-card-banner"}, verdictTag(r)),
      el("div", {class: "v2-wv-card-name"}, el("b", {text: r.name}), el("span", {class: "v2-meta", text: ` ${r.pos || ""}${r.team ? ` ${r.team}` : ""}`})),
      el("dl", {class: "v2-wv-card-facts"}, ...rowsDef.flatMap(([k, v]) => [el("dt", {text: k}), el("dd", {}, ...(Array.isArray(v) ? v : [v]))])),
      el("p", {class: "v2-wv-card-reason"}, r.reason, r.context ? el("span", {class: "v2-meta v2-wv-ctx", text: ` Other views: ${r.context}.`}) : null),
      el("details", {class: "v2-wv-detail"}, el("summary", {text: `Details for ${r.name}`}), detailBlock(r, roster)));
  }
  function resultsTable(list, roster) {
    const head = el("tr", {}, ...COLS.map(col => {
      const th = el("th", {scope: "col", "data-col": col.id, class: col.num ? "num" : ""});
      if (S.sort.key === col.id) th.setAttribute("aria-sort", S.sort.dir === "asc" ? "ascending" : "descending");
      if (col.sort) {
        const b = el("button", {type: "button", text: col.label});
        b.addEventListener("click", () => {
          const first = col.text || col.id === "verdict" ? "asc" : "desc";
          S.sort = S.sort.key === col.id ? {key: col.id, dir: S.sort.dir === "asc" ? "desc" : "asc"} : {key: col.id, dir: first};
          const again = renderResultsOnly();
          const nb = document.querySelector(`#v2WaiversTable th[data-col="${col.id}"] button`);
          if (nb) nb.focus();
          return again;
        });
        th.append(b);
      } else th.textContent = col.label;
      return th;
    }));
    const body = [];
    list.forEach(r => {
      // JEG-1059: the badge that marks a value the reader set, next to the DDF Value number.
      const ddfBadge = root.DDFOverrides && root.DDFOverrides.flag ? root.DDFOverrides.flag(r.candidate) : null;
      body.push(el("tr", {class: "v2-wv-main", "data-verdict": VERDICT_CLASS[r.verdict]},
        el("th", {scope: "row", class: "v2-wv-name"}, el("b", {text: r.name}), injuryTag(r.candidate) ? document.createTextNode(" ") : null, injuryTag(r.candidate)), el("td", {text: r.pos || ""}),
        el("td", {class: "num"}, numCell(r.ddf), ddfBadge), el("td", {class: "num"}, numCell(r.vaw)), el("td", {class: "num"}, numCell(r.market)),
        el("td", {class: "num"}, numCell(r.starterDelta, true)), el("td", {class: "num"}, numCell(r.benchDelta, true)),
        el("td", {}, dropText(r) || dash()), el("td", {}, verdictTag(r)), el("td", {class: "v2-wv-reason"}, r.reason, r.context ? el("span", {class: "v2-meta v2-wv-ctx", text: ` Other views: ${r.context}.`}) : null)));
      body.push(el("tr", {class: "v2-wv-detailrow"}, el("td", {colspan: String(COLS.length)},
        el("details", {class: "v2-wv-detail"}, el("summary", {text: `Details for ${r.name}`}), detailBlock(r, roster)))));
    });
    const table = el("table", {class: "v2-wv-table", id: "v2WaiversTable", role: "grid", "aria-labelledby": "v2WaiversHeadline"},
      el("thead", {}, head), el("tbody", {}, ...body));
    // Arrow keys walk the controls of the grid (the sort buttons and the detail toggles) in reading order.
    table.addEventListener("keydown", event => {
      const keys = {ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1};
      if (!(event.key in keys)) return;
      const items = [...table.querySelectorAll("th button, summary")];
      const at = items.indexOf(document.activeElement);
      if (at < 0) return;
      const next = items[at + keys[event.key]];
      if (next) { event.preventDefault(); next.focus(); }
    });
    return table;
  }

  // ---------- the view selector (JEG-1081 PR 6) ----------
  // The reader picks which view decides every verdict; the other views are context. A saved choice that no longer exists falls back to DDF Value.
  function basisName() {
    const b = engine() && engine().getBasis ? engine().getBasis() : null;
    return b && !b.isDefault ? b.label : "default";
  }
  function sourceChoices() {
    const info = engine() && engine().getSourceInfo ? engine().getSourceInfo() : [];
    return info.filter(i => i.available && api.SOURCE_NAMES[i.key]).map(i => i.key);
  }
  function viewChoices() {
    const b = engine() && engine().getBasis ? engine().getBasis() : null;
    return [["ddf", "DDF Value"], ["projections", "DDF Value (projections)"]]
      .concat(UI() && UI().marketKeys() ? [["market", "Trade chart average"]] : [])
      .concat(b && !b.isDefault ? [["basis", `Overrides basis (${basisName()})`]] : [])
      .concat(sourceChoices().map(k => [`src:${k}`, `${api.SOURCE_NAMES[k]} only`]));
  }
  function viewChoice() {
    return viewChoices().some(([id]) => id === S.view) ? S.view : "ddf";
  }
  function fillViews() {
    const sel = $("v2WaiversView");
    if (!sel) return;
    const choices = viewChoices();
    const sig = choices.map(c => c.join(":")).join("|");
    if (sig !== S.viewSig) {
      S.viewSig = sig;
      sel.replaceChildren(...choices.map(([id, text]) => el("option", {value: id, text})));
    }
    sel.value = viewChoice();
  }
  // ---------- compute and render ----------
  function context() {
    const C = engine();
    if (!C || !UI()) return null;
    const depth = UI().depthContext();
    const shape = C.getRosterShape();
    return {shape, weights: UI().benchWeights(), expected: depth ? depth.expected : null, chartKeys: UI().marketKeys(), rosterSize: rosterSizeOf(shape),
      byes: root.TradeValueByes ? root.TradeValueByes.byes : null, view: api.viewFor(viewChoice(), basisName())};
  }
  function compute() {
    const ctx = context();
    if (!ctx || !rowsAll().length) return {state: "loading"};
    const byKey = rowMap();
    const mineEntries = mineStore.get();
    const mine = rowsFor(mineEntries, byKey);
    const dd = dedupe(candStore.get(), mineEntries);
    const cands = rowsFor(dd.kept, byKey);
    const specials = mine.rows.filter(r => r.notEvaluated);
    if (!mine.rows.length) return {state: "no-roster", ctx, mine, cands, dd};
    if (!cands.rows.length) return {state: "no-candidates", ctx, mine, cands, dd};
    const out = api.evaluateAll(ctx, mine.rows, cands.rows);
    out.results.forEach(r => { r.vaw = r.candidate.notEvaluated ? null : valueAboveWaivers(r.candidate); });
    const allSpecial = out.results.length && out.results.every(r => r.verdict === api.VERDICT.none && r.reasonKind === "kdef");
    return {state: allSpecial ? "all-special" : "ok", ctx, mine, cands, dd, out, specials};
  }
  function setText(node, text) { if (node.textContent !== text) node.textContent = text; }
  function summaryText(list) {
    const counts = {};
    list.forEach(p => { counts[p.pos] = (counts[p.pos] || 0) + 1; });
    return ["QB", "RB", "WR", "TE", "K", "DEF"].filter(pos => counts[pos]).map(pos => `${pos} ${counts[pos]}`).join(", ");
  }
  const rosterSig = list => list.map(p => p.key).join("|");
  function renderSummary() {
    const mine = mineStore.get();
    const box = $("v2WaiversSummary");
    if (!box) return;
    // JEG-1316: "Your roster is back." stays up until the roster changes again.
    const back = $("v2WaiversMineBack");
    if (S.backSig && S.backSig !== rosterSig(mine)) S.backSig = "";
    if (back && !S.backSig && back.firstChild) back.replaceChildren();
    else if (back && S.backSig && !back.firstChild) back.replaceChildren(el("p", {class: "v2-meta", text: `${TITLES.mine} is back.`}));
    const names = mine.slice(0, 3).map(p => p.name).join(", ");
    box.querySelector(".v2-wv-sumtext").replaceChildren(
      el("span", {class: "v2-find-sum-names", text: `${names}${mine.length > 3 ? ` + ${mine.length - 3} more` : ""}`}),
      el("span", {class: "v2-meta", text: `${plural(mine.length, "player")}${summaryText(mine) ? `: ${summaryText(mine)}` : ""}`}));
    const edit = $("v2WaiversEdit");
    edit.setAttribute("aria-expanded", String(!S.collapsed));
    edit.setAttribute("aria-label", S.collapsed ? `Edit roster (${plural(mine.length, "player")})` : "Hide the roster input");
    edit.textContent = S.collapsed ? "Edit roster" : "Hide roster";
    box.hidden = !mine.length;
    $("v2WaiversMineInput").hidden = S.collapsed && mine.length > 0;
  }
  function renderAssess(c) {
    const box = $("v2WaiversAssess");
    box.replaceChildren();
    const entries = mineStore.get();
    if (!UI() || !entries.length || c.state === "loading") { box.hidden = true; return; }
    const a = UI().sideAssessment("mine", entries);
    box.hidden = !a;
    if (!a) return;
    if (!a.ready) {
      box.append(el("p", {class: "v2-meta", text: `The roster assessment shows once the roster has at least as many QB, RB, WR and TE players as the league has starting slots. Your roster has ${a.have} of ${a.slots}.`}));
      return;
    }
    box.append(UI().assessmentTable(a));
    const f = UI().biggestImbalance(a.ddf.balance);
    const m = a.market ? UI().biggestImbalance(a.market.balance) : null;
    const notes = el("ul", {class: "v2-find-assess-notes"});
    let line = f ? `Your biggest imbalance: ${UI().imbalanceText(f)} in DDF Value.` : "Your roster is balanced by position in DDF Value.";
    if (m && (!f || m.pos !== f.pos || m.status !== f.status)) line += ` In Trade chart average: ${UI().imbalanceText(m)}.`;
    else if (!a.market) line += " Trade chart average: not enough charts this week.";
    notes.append(el("li", {"data-note": "imbalance", text: line}));
    if (a.kept.length) notes.append(el("li", {"data-note": "not-evaluated", text: `Not evaluated, left out of every count and sum: ${a.kept.map(p => p.pos).join(", ")}.`}));
    box.append(notes);
  }
  const HEAD_TEXT = {
    loading: "Values are still loading.", "no-roster": "Add your roster first.", "no-candidates": "Add waiver candidates to see recommendations.",
    "all-special": "All candidates are kickers or defenses (not evaluated). Add QB, RB, WR or TE candidates."};
  function renderResultsOnly() {
    if (S.last && S.last.state === "ok") drawResults(S.last);
  }
  function drawResults(c) {
    const box = $("v2WaiversOut");
    const list = sortedResults(c.out.results);
    const cards = el("ol", {class: "v2-wv-cards", "aria-label": "Waiver candidates as cards"}, ...list.map(r => cardFor(r, c.out.roster)));
    const kids = [el("div", {class: "v2-find-table-wrap v2-wv-tablewrap"}, resultsTable(list, c.out.roster)), cards,
      el("p", {class: "v2-meta v2-wv-legend", text: "Starter change and bench change are the swap with the best drop, in the view you decide by (DDF Value unless you pick another); the bench counts at the engine's bench weights, never in full. Value above waivers is projected points per game above the waiver line for the player's position (the engine's own line, averaged over the projection sources that price him). A dash means no value, never zero."})];
    if (c.out.combos.length) {
      const sum = `Show ${plural(c.out.combos.length, "combo")}`;
      const det = el("details", {class: "v2-wv-combos", id: "v2WaiversCombos"}, el("summary", {text: sum}),
        el("ul", {class: "v2-wv-combolist"}, ...c.out.combos.slice(0, 20).map(k => el("li", {text: k.text}))));
      det.addEventListener("toggle", () => { det.querySelector("summary").textContent = det.open ? `Hide ${plural(c.out.combos.length, "combo")}` : sum; });
      kids.push(el("h3", {class: "v2-wv-sub", text: "Combo pickups (two in, two out)"}), det);
    }
    // Keep open details open across a redraw (a sort, a settings change).
    const open = new Set([...box.querySelectorAll("details.v2-wv-detail[open] summary")].map(s => s.textContent));
    const comboOpen = box.querySelector("#v2WaiversCombos[open]");
    box.replaceChildren(...kids);
    box.querySelectorAll("details.v2-wv-detail").forEach(d => { if (open.has(d.querySelector("summary").textContent)) d.open = true; });
    const combo = box.querySelector("#v2WaiversCombos");
    if (combo && comboOpen) { combo.open = true; combo.querySelector("summary").textContent = `Hide ${plural(c.out.combos.length, "combo")}`; }
    box.hidden = false;
  }
  function render() {
    S.scheduled = false;
    const wanted = $("v2Waivers");
    if (!wanted || !$("v2WaiversHeadline")) return;
    const c = compute();
    S.last = c;
    fillViews();
    const headline = $("v2WaiversHeadline");
    const state = c.state === "ok" ? c.out.headline.state : c.state;
    const text = c.state === "ok" ? c.out.headline.text : HEAD_TEXT[c.state];
    headline.dataset.state = state;
    setText(headline.querySelector("b"), text);
    setText(headline.querySelector(".v2-wv-headctx"), c.state === "ok" && c.out.headline.context ? `Other views: ${c.out.headline.context}.` : "");
    const count = $("v2WaiversCount");
    const notes = [];
    if (c.state !== "loading") {
      if (c.dd.onRoster) notes.push(`${plural(c.dd.onRoster, "player")} already on your roster ${c.dd.onRoster === 1 ? "was" : "were"} ignored.`);
      if (c.dd.repeats) notes.push(`${plural(c.dd.repeats, "duplicate")} removed.`);
      if (c.mine.gone.length) notes.push(`Your roster no longer has ${c.mine.gone.map(p => p.name).join(", ")} in the data (left out).`);
      if (c.cands.gone.length) notes.push(`${c.cands.gone.map(p => p.name).join(", ")}: no longer in the data (left out).`);
      if (c.ctx && !c.ctx.chartKeys) notes.push("Not enough trade charts are available this week for the market view. The DDF Value evaluation is unaffected.");
    }
    if (c.state === "ok") {
      const n = c.out.results.filter(r => r.verdict === api.VERDICT.pick).length;
      notes.unshift(`${plural(c.out.results.length, "candidate")} evaluated${n ? `, ${n} to pick up` : ""}${c.out.combos.length ? `, ${plural(c.out.combos.length, "combo")}` : ""}.`);
    }
    setText(count, notes.join(" "));
    S.notes = c.state !== "loading" ? c.mine.gone.concat(c.cands.gone) : [];
    renderAssess(c);
    const out = $("v2WaiversOut");
    if (c.state === "ok") {
      if (!S.hadResults) { S.hadResults = true; S.collapsed = true; }
      drawResults(c);
    } else { out.hidden = true; out.replaceChildren(); S.hadResults = false; if (c.state !== "loading") S.collapsed = false; }
    renderSummary();
    boxes.mine.render();
    boxes.cands.render();
    // JEG-1316: after roster Undo, focus the roster control that is on screen: Edit roster when the input folded, else the input.
    if (S.focusAfterUndo && c.state !== "loading") {
      S.focusAfterUndo = false;
      ($("v2WaiversMineInput").hidden ? $("v2WaiversEdit") : boxes.mine.input).focus();
    }
    syncHash();
  }
  function schedule() {
    if (S.scheduled) return;
    S.scheduled = true;
    Promise.resolve().then(render);
  }
  function syncHash() {
    if (!/^#waivers(\?|$)/.test(location.hash)) return;
    const mine = mineStore.get().map(p => p.key);
    const cands = candStore.get().map(p => p.key);
    const league = root.TradeValueV2 && root.TradeValueV2.leagueQuery ? (() => { try { return root.TradeValueV2.leagueQuery(); } catch (error) { return ""; } })() : "";
    const want = api.encodeHash(mine, cands, league);
    if (location.hash !== want) { try { history.replaceState(null, "", want); } catch (error) { /* the page still works */ } }
  }

  // One box for either page: it reads which list was pasted and fills it. When it cannot tell, it asks.
  function anyPageCard(mineBox, candsBox) {
    const input = el("textarea", {id: "v2WaiversAnySearch", rows: "2", placeholder: "Paste a whole roster page or waiver page here",
      autocomplete: "off", spellcheck: "false", "aria-describedby": "v2WaiversAnyHelp"});
    const label = el("label", {class: "v2-find-search-label"}, el("span", {class: "v2-sr", text: "Paste a whole roster page or waiver page from a fantasy site"}), input);
    const help = el("p", {class: "v2-meta v2-find-paste-help", id: "v2WaiversAnyHelp",
      text: "Open your team page or your league's free-agent page, press Ctrl+A, then Ctrl+C (Cmd on a Mac), and paste here. We work out which list it is and fill it in. It stays on this device."});
    const result = el("div", {class: "v2-find-paste-result", id: "v2WaiversAnyResult", role: "status", "aria-live": "polite"});
    const siteName = site => ({espn: "ESPN", yahoo: "Yahoo", sleeper: "Sleeper"}[site] || "");
    function route(text, kind, site) {
      const box = kind === "roster" ? mineBox : candsBox;
      const from = siteName(site);
      result.replaceChildren(el("p", {class: "v2-meta", text: `Read as ${kind === "roster" ? "your roster" : "waiver options"}${from ? ` from ${from}` : ""}. What was found is listed under ${TITLES[kind === "roster" ? "mine" : "cands"]} below.`}));
      box.consume(text, true);
      if (box.wrap.scrollIntoView) box.wrap.scrollIntoView({block: "nearest"});
    }
    function consume(text) {
      input.value = "";
      const rows = rowsAll();
      const P = root.DDFRosterPaste;
      if (!rows.length || !P) { result.replaceChildren(el("p", {class: "v2-meta", text: "Values are still loading. Try again in a moment."})); return; }
      const res = P.parse(text, rows);
      if (!res || !res.matched) {
        result.replaceChildren(el("p", {class: "v2-find-paste-count is-bad", text: "No players recognised in that text. Nothing was added."}),
          el("p", {class: "v2-meta", text: "Paste a whole page from a fantasy site (Ctrl+A, Ctrl+C on the page), or a list of player names."}));
        return;
      }
      const kind = P.detectListKind(text, res);
      if (kind !== "unknown") { route(text, kind, res.site); return; }
      const mine = el("button", {type: "button", class: "v2-btn", text: "This is my roster"});
      const cands = el("button", {type: "button", class: "v2-btn", text: "These are waiver options"});
      mine.addEventListener("click", () => route(text, "roster", res.site));
      cands.addEventListener("click", () => route(text, "waivers", res.site));
      result.replaceChildren(el("p", {class: "v2-find-paste-count is-ok", text: `Found ${plural(res.matched, "player")}, but I cannot tell which list this is.`}),
        el("p", {class: "v2-meta", text: "Which list is it?"}), mine, cands);
    }
    input.addEventListener("paste", event => {
      const text = event.clipboardData ? event.clipboardData.getData("text") : "";
      if (text && F.looksLikePage(text)) { event.preventDefault(); consume(text); }
    });
    input.addEventListener("input", () => { if (F.looksLikePage(input.value)) consume(input.value); });
    return el("section", {class: "v2-card", id: "v2WaiversAny", "aria-labelledby": "v2WaiversAnyTitle"},
      el("div", {class: "v2-card-head"}, el("div", {}, el("h2", {id: "v2WaiversAnyTitle", text: "Paste a whole page"}),
        el("p", {class: "v2-meta", text: "Your team page or a free-agent page, from any supported site."}))),
      el("div", {class: "v2-wv-input"}, el("div", {class: "v2-find-search-wrap"}, label), help, result));
  }

  // ---------- the page ----------
  function viewPicker() {
    const sel = el("select", {id: "v2WaiversView", "aria-describedby": "v2WaiversViewHelp"});
    sel.addEventListener("change", () => {
      S.view = sel.value;
      try { root.localStorage.setItem(STORE_VIEW, S.view); } catch (error) { /* a private window: the choice lasts until reload */ }
      schedule();
    });
    return el("div", {class: "v2-wv-viewpick"}, el("label", {class: "v2-field"}, el("span", {class: "v2-field-label", text: "Decide by:"}), sel),
      el("span", {class: "v2-meta", id: "v2WaiversViewHelp", text: "The view that decides each verdict; the other views are shown as context."}));
  }
  function build() {
    const host = $("v2Waivers");
    if (!host || $("v2WaiversHeadline")) return;
    const headline = el("div", {class: "v2-find-headline v2-wv-headline", id: "v2WaiversHeadline", role: "status", "aria-live": "polite", "aria-atomic": "true", "data-state": "loading"}, el("b", {text: HEAD_TEXT.loading}), el("span", {class: "v2-wv-headctx"}));
    const count = el("p", {class: "v2-meta v2-wv-count", id: "v2WaiversCount"});
    const mineBox = oneBox("mine");
    const candsBox = oneBox("cands");
    const edit = el("button", {type: "button", class: "v2-btn", id: "v2WaiversEdit", "aria-expanded": "true", "aria-controls": "v2WaiversMineInput", text: "Hide roster"});
    edit.addEventListener("click", () => { S.collapsed = !S.collapsed; renderSummary(); if (!S.collapsed) mineBox.input.focus(); });
    const summary = el("div", {class: "v2-find-summary v2-wv-summary", id: "v2WaiversSummary", hidden: ""}, el("div", {class: "v2-find-sumrow v2-wv-sumtext"}), edit);
    const mineCard = el("section", {class: "v2-card", id: "v2WaiversMine", "aria-labelledby": "v2WaiversMineTitle"},
      el("div", {class: "v2-card-head"}, el("div", {}, el("h2", {id: "v2WaiversMineTitle", text: "Your roster"}),
        el("p", {class: "v2-meta", text: "The same roster as Find a trade: enter it once."})), mineBox.clear),
      summary, el("div", {class: "v2-find-paste-result", id: "v2WaiversMineBack", role: "status", "aria-live": "polite"}),
      mineBox.wrap, el("section", {class: "v2-find-assess", id: "v2WaiversAssess", "aria-label": "Roster assessment", hidden: ""}));
    const candsCard = el("section", {class: "v2-card", id: "v2WaiversCands", "aria-labelledby": "v2WaiversCandsTitle"},
      el("div", {class: "v2-card-head"}, el("div", {}, el("h2", {id: "v2WaiversCandsTitle", text: "Waiver candidates"}),
        el("p", {class: "v2-meta", text: "The top options on the wire. Kickers and defenses are kept but not evaluated."})), candsBox.clear),
      candsBox.wrap);
    const anyCard = anyPageCard(mineBox, candsBox);
    const outCard = el("section", {class: "v2-card", id: "v2WaiversResults", "aria-labelledby": "v2WaiversResultsTitle"},
      el("div", {class: "v2-card-head"}, el("h2", {id: "v2WaiversResultsTitle", text: "Who to pick up"}), viewPicker()),
      el("div", {id: "v2WaiversOut", hidden: ""}));
    const foot = host.querySelector(".v2-footnote");
    const live = el("div", {class: "v2-wv-live"}, headline, count);
    host.insertBefore(live, foot);
    [anyCard, mineCard, candsCard, outCard].forEach(card => host.insertBefore(card, foot));
    boxes.mine = mineBox;
    boxes.cands = candsBox;
    mineCard.addEventListener("keydown", event => {
      if (event.key === "Escape" && !S.collapsed && S.hadResults && mineStore.get().length) { S.collapsed = true; renderSummary(); edit.focus(); }
    });
  }

  // First time the tab is shown: saved lists, then a shared link.
  function firstShow() {
    if (S.linkRead) return;
    S.linkRead = true;
    const stored = readJson(STORE_CANDS);
    if (Array.isArray(stored)) S.cands = keep(stored.filter(p => p && p.key));
    const storedMine = readJson(STORE_MINE);
    if (Array.isArray(storedMine) && storedMine.length && !mineStore.get().length) mineStore.set(keep(storedMine.filter(p => p && p.key)));
    mineStore.subscribe(() => {
      const list = mineStore.get();
      const sig = list.map(p => p.key).join(",");
      if (sig !== S.mineSig) { S.mineSig = sig; schedule(); }
    });
    const link = api.decodeHash(location.hash);
    if (link.mine.length || link.cands.length) {
      const map = rowMap();
      const choices = new Map(notEvaluatedChoices().map(c => [String(c.player_key), c]));
      const toEntry = key => {
        const row = map.get(key);
        if (row) return entryOfRow(row);
        const special = choices.get(key);
        return special ? {key, name: special.name, pos: special.pos, team: special.team || ""} : null;
      };
      const mine = link.mine.map(toEntry);
      const cands = link.cands.map(toEntry);
      const lost = mine.concat(cands).filter(x => !x).length;
      if (link.mine.length) mineStore.set(mine.filter(Boolean));
      if (link.cands.length) candStore.set(cands.filter(Boolean));
      if (lost) S.linkNote = `${plural(lost, "player")} from the shared link ${lost === 1 ? "was" : "were"} not found in the current data.`;
    }
  }
  function activate() {
    build();
    if (!engine() || !rowsAll().length) { schedule(); return; }
    firstShow();
    render();
    if (S.linkNote) { const c = $("v2WaiversCount"); c.textContent = `${S.linkNote} ${c.textContent}`.trim(); }
  }
  api.activate = activate;
  function onLeagueSettingsChanged(event) {
    if (!$("v2WaiversHeadline") || !S.linkRead) return;
    render();
    const note = (S.notes || []).map(p => p.name);
    if (note.length && event && event.detail && event.detail.notes) event.detail.notes.push(`Waivers: ${note.join(", ")} no longer in the data under these settings.`);
  }
  document.addEventListener("ddf:league-settings-changed", onLeagueSettingsChanged);
  const start = () => { build(); if (/^#waivers/.test(location.hash)) schedule(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})(typeof window !== "undefined" ? window : globalThis);
