// JEG-xxx: pure find-trades logic for the MCP endpoint. Wraps the site's
// finder.js (app/v2/finder.js) which is loaded from the published site at cold
// start, the same way ddf-state.js is loaded in index.ts. This module owns the
// interface contract findTradesForPair() that both the find_trades tool and the
// league-wide batch (batch.ts) call.
//
// No Deno APIs. No DOM. Runs under node in tests.

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** An engine row as the finder expects: player_key, name, pos, values map. */
export interface FinderRow {
  player_key: number;
  name: string;
  pos: string;
  /** ddf_value, usatoday, fantasycalc, fantasypros, cbs, and optionally
   *  ddf_value_charts / ddf_value_projections for noise estimation. */
  values: Record<string, number | null>;
  ddfTier?: string;
}

export interface TradeCandidate {
  give: Array<{ player_key: number; name: string; pos: string; value: number | null }>;
  receive: Array<{ player_key: number; name: string; pos: string; value: number | null }>;
  /** DDF Value edge (receive − give for you). */
  edge: number;
  /** How many of the 4 trade charts say the rival breaks even or wins. */
  rivalOkCount: number;
  pricedCharts: number;
  /** Ranking score (edge penalised for extra players). */
  score: number;
  /** Per-chart breakdown. */
  charts: Array<{ key: string; net: number | null; rivalOk: boolean | null }>;
}

export interface FindTradesResult {
  trades: TradeCandidate[];
  total: number;
  mine: { searched: number; of: number; unpriced: number };
  theirs: { searched: number; of: number; unpriced: number };
  chartKeys: string[];
}

export interface FindTradesOpts {
  maxSize?: number;       // max players per side (default 2)
  minRivalEdge?: number;  // min market-value edge the rival needs (default 0)
  limit?: number;         // max candidates to return (default 10)
}

// ---------------------------------------------------------------------------
// The Finder interface (loaded from the site's finder.js at runtime).
// ---------------------------------------------------------------------------

export interface Finder {
  findTrades: (
    mine: FinderRow[],
    theirs: FinderRow[],
    opts?: Record<string, unknown>,
  // deno-lint-ignore no-explicit-any
  ) => any;
  OUR_KEY: string;
  CHART_KEYS: string[];
  // deno-lint-ignore no-explicit-any
  [key: string]: any;
}

/**
 * Evaluate the site's finder.js source and return its API. The file publishes
 * TradeValueFinder and then keeps running browser-only page code, which throws
 * here (no document). The API is already on the global by then, so a throw
 * after publishing is not a failed load; a source that never publishes it is.
 */
export function evalFinder(
  source: string,
  evalFn: (code: string) => unknown,
  // deno-lint-ignore no-explicit-any
  g: any = globalThis,
): Finder | null {
  try {
    evalFn(source);
  } catch (e) {
    console.error("finder.js threw after load (expected without a DOM):", String((e as Error)?.message ?? e));
  }
  const f = g.TradeValueFinder;
  return f && typeof f.findTrades === "function" ? (f as Finder) : null;
}

// ---------------------------------------------------------------------------
// findTradesForPair — the contract both tools use.
// ---------------------------------------------------------------------------

/**
 * Find trade candidates between two rosters. Pure, no side effects.
 *
 * @param finder  The site's finder.js module (loaded once at cold start).
 * @param mine    Engine rows for my roster (with .values including chart series).
 * @param theirs  Engine rows for their roster.
 * @param opts    Optional: maxSize, minRivalEdge, limit.
 */
export function findTradesForPair(
  finder: Finder,
  mine: FinderRow[],
  theirs: FinderRow[],
  opts?: FindTradesOpts,
): FindTradesResult {
  const maxSize = Math.max(1, Math.min(4, opts?.maxSize ?? 2));
  // The tool asks for a pool larger than the number it will show, so a later
  // dedupe can still fill the caller's limit. 500 is the pool cap.
  const limit = Math.max(1, Math.min(500, opts?.limit ?? 10));
  const minRivalEdge = opts?.minRivalEdge ?? 0;

  // Call the finder's own search — the same function the site uses.
  const raw = finder.findTrades(mine, theirs, {
    ourKey: finder.OUR_KEY,
    chartKeys: finder.CHART_KEYS,
    maxSize,
    limit: Math.min(500, limit + (minRivalEdge > 0 ? 20 : 0)),
  });

  const ddfKey = finder.OUR_KEY;
  const fmt = (rows: FinderRow[]) =>
    rows.map((r) => ({
      player_key: r.player_key,
      name: r.name,
      pos: r.pos,
      value: r.values?.[ddfKey] ?? null,
    }));

  let trades: TradeCandidate[] = raw.trades.map(
    // deno-lint-ignore no-explicit-any
    (t: any) => ({
      give: fmt(t.give),
      receive: fmt(t.receive),
      edge: Math.round(t.edge * 10) / 10,
      rivalOkCount: t.rivalOkCount,
      pricedCharts: t.pricedCharts,
      score: Math.round(t.score * 10) / 10,
      charts: t.charts,
    }),
  );

  // Optional: filter by a minimum market-value (chart-average) edge for the rival.
  if (minRivalEdge > 0) {
    trades = trades.filter((t) => {
      // The rival's edge on the chart average: the mean of the charts where
      // the rival breaks even or comes out ahead. JEG-1125: rivalOk now also
      // holds for a chart that has you up by less than the even band, where
      // the rival gains nothing, so a chart counts only the rival's own gain
      // (-net, never below 0), not the size of the gap.
      const rivalNets = t.charts
        .filter((c) => c.net !== null && c.rivalOk)
        .map((c) => Math.max(0, -c.net!));
      const avgRivalEdge = rivalNets.length ? rivalNets.reduce((a, b) => a + b, 0) / rivalNets.length : 0;
      return avgRivalEdge >= minRivalEdge;
    });
  }

  trades = trades.slice(0, limit);

  return {
    trades,
    total: raw.total,
    mine: { searched: raw.mine.searched, of: raw.mine.of, unpriced: raw.mine.unpriced },
    theirs: { searched: raw.theirs.searched, of: raw.theirs.of, unpriced: raw.theirs.unpriced },
    chartKeys: raw.chartKeys,
  };
}
