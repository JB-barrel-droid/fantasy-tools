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

/** The engine's ES-14 bench-share readout as get-values publishes it (bench_share). */
export interface BenchShareReadout {
  QB?: number | null;
  RB?: number | null;
  WR?: number | null;
  TE?: number | null;
  overall?: number | null;
  /** The league's bench-share input: the fallback when the engine gives no overall share. */
  input?: number | null;
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
 * `weights` is the engine's bench-share readout (per position) that get-values publishes
 * (see benchWeightsFromReadout). `expected` is the engine's expected
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
 * The bench weights the finder page uses (finder.js benchWeights(), JEG-988), built from the
 * engine's own ES-14 readout that get-values publishes as bench_share (Jeremy's pick B on
 * JEG-1115, 2026-10-26: the connector reads the engine's numbers instead of rebuilding them).
 * Same resolution as the page: overall is the readout's overall share, else the league's
 * bench-share input, else 0; a position is set only when the readout has a finite share for
 * it (the finder then falls back to overall). Returns null when get-values sent no readout,
 * so the caller leaves the fit unjudged rather than guess.
 */
export function benchWeightsFromReadout(readout: BenchShareReadout | null | undefined): Record<string, number> | null {
  if (!readout) return null;
  const overall = finite(readout.overall) ? readout.overall : finite(readout.input) ? readout.input : 0;
  const out: Record<string, number> = { overall };
  for (const pos of ["QB", "RB", "WR", "TE"] as const) {
    const v = readout[pos];
    if (finite(v)) out[pos] = v;
  }
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
