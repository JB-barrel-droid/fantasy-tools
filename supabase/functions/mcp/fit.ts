// JEG-1115: the fit label (Natural / Market supported / Force) for the trades the
// connector returns, so a chat answer shows the same label the finder page, the league
// table and the detail panel show, next to viability (High / Med-High / Medium).
//
// This module never reimplements the rule. It calls the site's own finder.js —
// TradeValueFinder.tradeFit and TradeValueFinder.fitText (app/v2/finder.js, JEG-1108) —
// the way the page's fitFor() does, and only maps the label to its display words. Every
// threshold (FIT_Z, the 0.05 floor, the noise floor) is read from the finder, never
// copied: change finder.js and the connector follows.
//
// Pure functions, no Deno APIs, no network. Runs under node in tests.

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** The finder.js API surface this module needs (the rest is ignored). */
export interface FitFinder {
  OUR_KEY: string;
  CHART_KEYS: string[];
  MIN_CHARTS: number;
  MARKET_KEY: string;
  FIT_Z: number;
  // deno-lint-ignore no-explicit-any
  withChartAverage: (rows: any[], chartKeys: string[]) => any[];
  // deno-lint-ignore no-explicit-any
  tradeFit: (sides: any, ctx: any) => any;
  // deno-lint-ignore no-explicit-any
  fitText: (fit: any) => string;
}

/** League starting-lineup shape (same fields as the page's RosterShape). */
export interface FitShape {
  QB: number;
  RB: number;
  WR: number;
  TE: number;
  FLEX: number;
  SUPERFLEX: number;
}

/** A roster row as the finder expects: player_key, name, pos, values (every series). */
export interface FitRow {
  player_key: number;
  name: string;
  pos: string;
  values: Record<string, number | null>;
  ddfTier?: string;
}

/** What the fit rule needs beyond the two rosters and the trade itself. */
export interface FitContext {
  shape: FitShape;
  /** Expected depth per position (engine allocation); null when unknown. Display only. */
  expected: Record<string, unknown> | null;
  /** Per-position bench-share weights (the engine's readout); 0 weight when unknown. */
  weights: Record<string, number>;
  /** The compared trade charts (a Trade chart average needs at least MIN_CHARTS). */
  chartKeys: string[];
  ourKey: string;
  marketKey: string;
  z: number;
}

export interface FitLabel {
  /** "Natural" | "Market supported" | "Force", or null when the fit is not judged. */
  fit: string | null;
  /** One plain-English sentence, the finder's own fitText wording; null with the label. */
  fit_reason: string | null;
}

/** A player as get-values returns them, for the bench-share weights below. */
export interface FitPlayer {
  player_key: number;
  pos: string;
  value: number;
  tier: string;
}

// The finder's lowercase variants -> the words the page shows (finder.js FIT_TIPS keys).
export const FIT_LABELS: Record<string, string> = {
  natural: "Natural",
  market: "Market supported",
  force: "Force",
};

const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

// ---------------------------------------------------------------------------
// The fit context
// ---------------------------------------------------------------------------

/**
 * Assemble the context tradeFit needs from what the connector has. Returns null when the
 * rule cannot be judged (no league shape, or too few trade charts for a Trade chart
 * average — the same bar the page's marketKeys() applies).
 *
 * `weights` is the engine's bench-share readout (per position); the connector reads it
 * back from get-values (see benchWeightsFromPlayers). `expected` is the engine's expected
 * depth: get-values does not expose it, so it is null here, which only drops the depth
 * sentence from fit_reason — it never moves the label.
 */
export function buildFitContext(
  finder: FitFinder,
  opts: {
    shape?: FitShape | null;
    chartKeys?: string[] | null;
    weights?: Record<string, number> | null;
    expected?: Record<string, unknown> | null;
    z?: number | null;
  },
): FitContext | null {
  if (!opts.shape) return null;
  const known = new Set(finder.CHART_KEYS || []);
  const charts = (opts.chartKeys || []).filter((k) => known.has(k));
  if (charts.length < (finder.MIN_CHARTS || 3)) return null;
  return {
    shape: opts.shape,
    expected: opts.expected ?? null,
    weights: opts.weights ?? {},
    chartKeys: charts,
    ourKey: finder.OUR_KEY,
    marketKey: finder.MARKET_KEY,
    z: finite(opts.z) ? opts.z : finder.FIT_Z,
  };
}

/**
 * The engine's bench-share readout (value-model.js, ES-14: each position's bench tier as a
 * share of that position's blended DDF Value, and the whole-league share), read back from
 * what get-values publishes: every priced player's blended value and the engine's own tier.
 *
 * The engine computes this inside the value pipeline (app/trade-value-chart/assets/
 * value-model.js), which the connector does not run; the site reads it from
 * TradeValueCurveControls.getBenchShareReadout(). The bench slice is [allocation.starters,
 * allocation.rostered) — exactly the engine's "bench" tier, which get-values returns — so
 * no re-ranking happens here, only the sums.
 *
 * Known difference (flagged for review on JEG-1115): the engine walks the slice in
 * projected-points order (meanPpg) while the tier is assigned on the blended-value order,
 * so membership can differ at the boundary. A position with no priced players reads 0.
 */
export function benchWeightsFromPlayers(players: FitPlayer[]): Record<string, number> {
  const out: Record<string, number> = {};
  let benchAll = 0;
  let totalAll = 0;
  for (const pos of ["QB", "RB", "WR", "TE"]) {
    let bench = 0;
    let total = 0;
    for (const p of players) {
      if (p.pos !== pos || !finite(p.value)) continue;
      total += p.value;
      if (p.tier === "bench") bench += p.value;
    }
    out[pos] = total > 0 ? bench / total : 0;
    benchAll += bench;
    totalAll += total;
  }
  out.overall = totalAll > 0 ? benchAll / totalAll : 0;
  return out;
}

// ---------------------------------------------------------------------------
// One trade's fit
// ---------------------------------------------------------------------------

/**
 * Judge one trade exactly as the finder page does: widen both sides to the rows that
 * carry the Trade chart average, hand the trade to the finder's tradeFit, and read the
 * sentence from the finder's fitText. `give` is what you send, `receive` what you get.
 *
 * Returns {fit: null, fit_reason: null} when tradeFit cannot judge (no market view).
 */
export function fitForTrade(
  finder: FitFinder,
  mineRows: FitRow[],
  theirsRows: FitRow[],
  giveRows: FitRow[],
  receiveRows: FitRow[],
  ctx: FitContext,
): FitLabel {
  const mineAvg = finder.withChartAverage(mineRows, ctx.chartKeys);
  const theirAvg = finder.withChartAverage(theirsRows, ctx.chartKeys);
  const byKey = new Map<string, FitRow>(
    (mineAvg as FitRow[]).concat(theirAvg as FitRow[]).map((r) => [String(r.player_key), r]),
  );
  const wide = (rows: FitRow[]) => rows.map((r) => byKey.get(String(r.player_key)) || r);
  const fit = finder.tradeFit(
    {
      mine: { roster: mineAvg, leaving: wide(giveRows), arriving: wide(receiveRows) },
      theirs: { roster: theirAvg, leaving: wide(receiveRows), arriving: wide(giveRows) },
    },
    ctx,
  );
  if (!fit || !fit.label) return { fit: null, fit_reason: null };
  return { fit: FIT_LABELS[fit.label] ?? null, fit_reason: finder.fitText(fit) };
}
