/* JEG-1418: pure local adapter for validated waiver-board 0.1.x / 0.2.x artifacts.
 * No storage, fetch, pricing, UI activation or board-schema mutation. Node callers
 * require this module; browser callers must load finder.js and waivers.js first.
 *
 * buildSwapPlan(board, {rosterKeys, wireKeys, wireOverrides: {add, remove},
 *   context: {shape, expected, weights, rosterSize}, acceptGain})
 *
 * Keys are already resolved player_key identities, never pasted names. The paste
 * resolver and the existing wire-selection policy belong to the caller. Overrides
 * change that supplied wire only. acceptGain(rawDdfGain, addValue, dropValue) is
 * REQUIRED (unary callbacks remain supported): this adapter
 * does not settle the board's gain-cutoff policy. Selection order is Waivers'
 * orderResults, not a new raw-gain ranking. After each selected move, evaluate
 * again on the resulting roster. Each player participates in at most one move.
 */
(function (root) {
  "use strict";
  const node = typeof module !== "undefined" && module.exports;
  const W = node ? require("./waivers.js") : root.TradeValueWaivers;
  const F = node ? require("./finder.js") : root.TradeValueFinder;
  const finite = n => typeof n === "number" && Number.isFinite(n);
  const keyOf = r => String(r.player_key);
  const unavailable = reason => ({available: false, missing_reason: reason, swaps: []});

  // Subtract the canonical decimal forms of the existing numeric inputs. This
  // removes binary-subtraction artifacts without rounding values to a chosen
  // precision or introducing a tolerance at the caller's policy boundary.
  function decimal(value) {
    const [mantissa, exponent = "0"] = String(value).split("e");
    const dot = mantissa.indexOf(".");
    return {coefficient: BigInt(mantissa.replace(".", "")),
      exponent: Number(exponent) - (dot < 0 ? 0 : mantissa.length - dot - 1)};
  }
  const unitsAt = (value, exponent) => value.coefficient * 10n ** BigInt(value.exponent - exponent);
  function decimalDifference(left, right) {
    const a = decimal(left), b = decimal(right);
    const exponent = Math.min(a.exponent, b.exponent);
    return {coefficient: unitsAt(a, exponent) - unitsAt(b, exponent), exponent};
  }
  function compareDecimals(a, b) {
    const exponent = Math.min(a.exponent, b.exponent);
    const delta = unitsAt(a, exponent) - unitsAt(b, exponent);
    return delta < 0n ? -1 : delta > 0n ? 1 : 0;
  }

  function keys(values, label) {
    if (!Array.isArray(values) || values.some(k =>
      !((typeof k === "string" && k.trim()) || (typeof k === "number" && Number.isSafeInteger(k))))) {
      throw new TypeError(`${label} must contain resolved player keys`);
    }
    return [...new Set(values.map(String))];
  }

  function rowsFromBoard(board) {
    if (!board || board.schema !== "waiver-board" || !/^0\.[12]\.\d+$/.test(board.schema_version)
        || !Array.isArray(board.players)) throw new TypeError("expected a validated waiver-board 0.1.x or 0.2.x artifact");
    const seen = new Set();
    return board.players.map(p => {
      if (!Number.isSafeInteger(p.player_key) || seen.has(String(p.player_key))
          || !p.value || !(p.value.ddf_value === null || finite(p.value.ddf_value))) {
        throw new TypeError("board players need unique resolved keys and finite or missing DDF Values");
      }
      seen.add(String(p.player_key));
      return {player_key: p.player_key, name: p.name, pos: p.position, team: p.team,
        values: {[F.OUR_KEY]: p.value.ddf_value},
        notEvaluated: F.isNotEvaluated({pos: p.position})};
    });
  }

  function applyWireOverrides(wireKeys, overrides = {}, rosterKeys = []) {
    const base = keys(wireKeys, "wireKeys");
    const add = keys(overrides.add || [], "wireOverrides.add");
    const remove = keys(overrides.remove || [], "wireOverrides.remove");
    const removed = new Set(remove);
    if (add.some(k => removed.has(k))) throw new TypeError("a player cannot be both added to and removed from the wire");
    const mine = new Set(keys(rosterKeys, "rosterKeys"));
    return [...new Set(base.concat(add))].filter(k => !removed.has(k) && !mine.has(k));
  }

  function buildSwapPlan(board, options) {
    if (!options || typeof options.acceptGain !== "function") throw new TypeError("acceptGain policy is required");
    const {context: ctx, acceptGain} = options;
    if (!ctx || !ctx.shape || !ctx.expected || !ctx.weights) return unavailable("league shape, expected depth and bench weights are required");
    const rows = rowsFromBoard(board);
    const byKey = new Map(rows.map(r => [keyOf(r), r]));
    const mine = keys(options.rosterKeys, "rosterKeys");
    const wire = applyWireOverrides(options.wireKeys, options.wireOverrides, mine);
    const missingRoster = mine.filter(k => !byKey.has(k));
    if (missingRoster.length) return unavailable(`roster players missing from board: ${missingRoster.join(", ")}`);
    // Unknown roster identities cannot silently open slots or become zero-cost
    // drops. Unknown wire identities are reported and never evaluated.
    const unresolvedWireKeys = wire.filter(k => !byKey.has(k));
    let roster = mine.map(k => byKey.get(k));
    const balance = F.rosterBalance(roster, ctx.expected, F.OUR_KEY, ctx.shape);
    if (!balance.ready) return unavailable("a complete starting roster is required to protect positional depth");
    let candidates = wire.filter(k => byKey.has(k)).map(k => byKey.get(k))
      .filter(row => F.DEPTH_POS.includes(row.pos));
    const context = {...ctx, view: W.viewFor("ddf"), chartKeys: [],
      rosterSize: ctx.rosterSize === undefined ? W.rosterSizeOf(ctx.shape) : ctx.rosterSize};
    const used = new Set();
    const swaps = [];
    while (candidates.length) {
      const evaluated = W.orderResults(candidates.map(c => W.evaluateCandidate(context, roster, c)));
      const eligible = evaluated.map(result => {
        if (result.verdict === W.VERDICT.none || used.has(keyOf(result.candidate))) return null;
        const drop = result.drop;
        // Reuse Waivers' best drop exactly; never replace its choice with an
        // independently ranked alternative. Only priced bench drops qualify.
        if (drop && (used.has(keyOf(drop)) || !F.DEPTH_POS.includes(drop.pos) || !result.impact.before.bench.includes(drop)
            || !finite(drop.values[F.OUR_KEY]))) return null;
        if (!drop && !result.openSlot) return null;
        // teamFit supplies the existing depth bands. Protect a position when a
        // move reduces its usable depth and increases its distance from the band.
        const thins = Object.values(result.fit.depth).some(d => d.after < d.before && d.distAfter > d.distBefore);
        if (thins || result.fit.emptyAfter > result.fit.emptyBefore) return null;
        const dropValue = drop ? drop.values[F.OUR_KEY] : 0;
        const difference = decimalDifference(result.ddf, dropValue);
        const gain = Number(`${difference.coefficient}e${difference.exponent}`);
        if (!finite(gain)) throw new RangeError("swap gain cannot be represented as a finite number");
        if (!acceptGain(gain, result.ddf, dropValue)) return null;
        return {add: result.candidate, drop, gain, evaluation: result};
      }).find(Boolean);
      if (!eligible) break;
      swaps.push(eligible);
      used.add(keyOf(eligible.add));
      if (eligible.drop) used.add(keyOf(eligible.drop));
      roster = roster.filter(r => !eligible.drop || keyOf(r) !== keyOf(eligible.drop)).concat(eligible.add);
      candidates = candidates.filter(r => !used.has(keyOf(r)));
    }
    return {available: true, missing_reason: null, swaps, unresolvedWireKeys};
  }

  // JSON boundary for the optional offline builder. Python validates the request
  // shape; retain these checks for direct JS callers. No default gain policy.
  function buildSwapBlock(board, request) {
    const policy = request && request.gain_policy;
    if (!policy || !finite(policy.minimum) || !["gt", "gte"].includes(policy.comparison)) {
      throw new TypeError("explicit gain_policy minimum and comparison are required");
    }
    const values = board.sources && board.sources.values;
    const minimum = decimal(policy.minimum);
    const plan = values && !values.enabled
      ? unavailable(values.disabled_reason)
      : buildSwapPlan(board, {rosterKeys: request.roster_keys, wireKeys: request.wire_keys,
        wireOverrides: request.wire_overrides, context: request.context,
        acceptGain: (_gain, addValue, dropValue) => {
          const comparison = compareDecimals(decimalDifference(addValue, dropValue), minimum);
          return policy.comparison === "gt" ? comparison > 0 : comparison >= 0;
        }});
    return {available: plan.available, missing_reason: plan.missing_reason, request,
      rows: plan.swaps.map(s => ({add: s.add.player_key, drop: s.drop ? s.drop.player_key : null, gain: s.gain})),
      unresolved_wire_keys: (plan.unresolvedWireKeys || []).map(Number)};
  }

  const api = {rowsFromBoard, applyWireOverrides, buildSwapPlan, buildSwapBlock};
  if (node) module.exports = api;
  else root.TradeValueWaiverBoardSwaps = api;
})(typeof window !== "undefined" ? window : globalThis);
