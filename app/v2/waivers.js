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

  const VERDICT = {pick: "Pick up", force: "Pick up (force)", consider: "Consider", hold: "Hold", skip: "Skip", none: "Not evaluated"};
  const TIER = {[VERDICT.pick]: 0, [VERDICT.force]: 1, [VERDICT.consider]: 2, [VERDICT.hold]: 3, [VERDICT.skip]: 4, [VERDICT.none]: 5};

  const keyOf = row => String(row.player_key);
  const ddfOf = row => (row && row.values && finite(row.values[OUR_KEY]) ? row.values[OUR_KEY] : null);
  // The Trade chart average, or null: a player no chart prices (or prices at a shown 0.0) has no market value to show.
  const marketOf = row => (row && row.values && finite(row.values[MARKET_KEY]) && row.values[MARKET_KEY] >= USABLE_MIN ? row.values[MARKET_KEY] : null);
  const fmt = n => (Math.abs(n) < NET_FLOOR ? "0.0" : (n > 0 ? "+" : "") + n.toFixed(1));
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
  // Loss in total value (starters + bench) if the player left with no replacement. A kicker, defense or player with no
  // DDF Value contributes nothing, so leaves at 0.
  function marginalValue(roster, row, shape, key) {
    const before = lineupValue(roster, shape, key).total;
    const after = lineupValue(roster.filter(r => r !== row), shape, key).total;
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
  function dropRanking(roster, shape, key) {
    const list = roster.filter(r => !isRequiredSpecial(r, roster, shape))
      .map(row => ({row, marginal: marginalValue(roster, row, shape, key)}));
    return list.sort((a, b) => a.marginal - b.marginal
      || Number(isNotEvaluated(b.row)) - Number(isNotEvaluated(a.row))
      || (ddfOf(a.row) || 0) - (ddfOf(b.row) || 0)
      || (marketOf(a.row) || 0) - (marketOf(b.row) || 0)
      || String(a.row.name).localeCompare(String(b.row.name)) || keyOf(a.row).localeCompare(keyOf(b.row)));
  }
  // The n best drops one after the other (each marginal is recomputed on what is left).
  function bestDrops(roster, shape, key, n) {
    const out = [];
    let left = roster;
    for (let i = 0; i < n; i++) {
      const ranked = dropRanking(left, shape, key);
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
  function evaluateCandidate(ctx, roster, candidate) {
    const base = {candidate, name: candidate.name, pos: candidate.pos, ddf: ddfOf(candidate), market: marketOf(candidate), team: candidate.team || ""};
    const charts = ctx.chartKeys && ctx.chartKeys.length ? ctx.chartKeys : null;
    const marketText = charts ? (base.market !== null ? ` Trade chart avg ${base.market.toFixed(1)}.` : " No market value available.") : "";
    if (isNotEvaluated(candidate)) {
      return {...base, verdict: VERDICT.none, ddf: null, market: null, starterDelta: null, benchDelta: null, totalDelta: null, drop: null, reasonKind: "kdef",
        reason: `${candidate.name}: kickers and defenses are not evaluated.`};
    }
    if (base.ddf === null) {
      return {...base, verdict: VERDICT.none, starterDelta: null, benchDelta: null, totalDelta: null, drop: null, reasonKind: "noddf",
        reason: base.market !== null
          ? `${candidate.name}: no DDF Value, so not evaluated (market value ${base.market.toFixed(1)}).`
          : `${candidate.name}: not in the engine's projections (not evaluated). Search the name on a chart site to check.`};
    }
    const free = openSlots(roster, ctx.rosterSize);
    const drop = free > 0 ? null : dropRanking(roster, ctx.shape, OUR_KEY)[0] || null;
    const leaving = drop ? [drop.row] : [];
    const impact = rosterImpact(roster, leaving, [candidate], ctx.shape, OUR_KEY);
    const fit = teamFit({roster, leaving, arriving: [candidate]}, {shape: ctx.shape, expected: ctx.expected, weights: {}, chartKeys: charts || undefined, z: FIT_Z}, OUR_KEY);
    const total = impact.totalDelta;
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
    if (verdict === VERDICT.pick) reason = `Pick up ${candidate.name}${dropClause}: ${fmt(impact.starterDelta)} starter value, ${fmt(impact.benchDelta)} bench.${need}${stash}${extras}${marketText}`;
    else if (verdict === VERDICT.force) reason = `Pick up ${candidate.name}${dropClause}: ${fmt(total)} total value, but ${deepens}.${stash}${extras}${marketText}`;
    else if (verdict === VERDICT.consider) reason = `Consider ${candidate.name}${dropName ? ` for ${dropName}` : ""}: value is level (${fmt(total)}, inside the ${tau.toFixed(1)} noise floor), but fills ${towardAt.length ? `a need at ${towardAt[0]}` : "an open starting slot"}.${extras}${marketText}`;
    else if (verdict === VERDICT.hold) {
      const deep = DEPTH_POS.find(pos => fit.depth[pos] && fit.depth[pos].statusBefore === "over" && candidate.pos === pos);
      reason = `No clear gain from ${candidate.name} (${fmt(total)}, inside the ${tau.toFixed(1)} noise floor).${deep ? ` Already deep at ${depthText(fit.depth, deep)}.` : ""}${marketText}`;
    } else reason = `${candidate.name} does not improve the roster (${fmt(total)}${dropName ? ` against ${dropName}` : ""}).${marketText}`;
    return {...base, verdict, drop: drop ? drop.row : null, dropMarginal: drop ? drop.marginal : null, openSlot: free > 0,
      starterDelta: impact.starterDelta, benchDelta: impact.benchDelta, totalDelta: total, tau, noise: fit.tau, impact, fit,
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
    const out = [];
    pairsOf(valued).forEach(([a, b]) => {
      const drops = bestDrops(roster, ctx.shape, OUR_KEY, need);
      if (drops.length < need) return;
      const leaving = drops.map(d => d.row);
      const arriving = [a.candidate, b.candidate];
      const impact = rosterImpact(roster, leaving, arriving, ctx.shape, OUR_KEY);
      const noise = Math.sqrt(leaving.concat(arriving).reduce((t, r) => t + Math.pow(valueNoise(r, OUR_KEY, ctx.chartKeys || undefined), 2), 0));
      const tau = Math.max(NET_FLOOR, FIT_Z * noise);
      const best = Math.max(a.totalDelta, b.totalDelta);
      // It must clear the noise floor, and what it adds over the better single pickup must clear it too.
      if (!(impact.totalDelta > tau) || !(impact.totalDelta - best > tau)) return;
      const names = rows => rows.map(r => r.name).join(" + ");
      out.push({candidates: [a.candidate, b.candidate], drops: leaving, starterDelta: impact.starterDelta, benchDelta: impact.benchDelta,
        totalDelta: impact.totalDelta, tau, bestSingle: best, impact,
        text: `Pick up ${names(arriving)}${leaving.length ? `, drop ${names(leaving)}` : " (open roster slots)"}: ${fmt(impact.totalDelta)} total value (${fmt(impact.starterDelta)} starters, ${fmt(impact.benchDelta)} bench).`});
    });
    return out.sort((x, y) => y.totalDelta - x.totalDelta);
  }

  // ---------- the whole tab ----------
  // The headline: the best single pickup in one sentence, else the best two-for-two, else "no pickup".
  function headlineFor(results, combos) {
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
    return {roster, results, combos, headline: headlineFor(results, combos)};
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

  const api = {VERDICT, TIER, MAX_PAIRS, NET_FLOOR, OUT_STATUS, rowsFor, dedupe, marginalValue, dropRanking, bestDrops, openSlots, rosterSizeOf, evaluateCandidate,
    orderResults, pairsOf, evaluateCombos, headlineFor, evaluateAll, encodeHash, decodeHash, ddfOf, marketOf, fmt, isRequiredSpecial};
  if (isNode) { module.exports = api; return; }
  root.TradeValueWaivers = api;
  // (page code follows in the browser build)
})(typeof window !== "undefined" ? window : globalThis);
