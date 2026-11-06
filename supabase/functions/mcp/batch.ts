// JEG-1036: batch trade discovery across a league for the remote MCP.
// One request with the user's roster plus up to ~11 opposing rosters returns
// the strongest trades across the league, ranked and deduplicated.
// Pure functions, no Deno APIs, so the same file runs under node in tests.

// ---------- types from the single-pair find_trades tool (parallel branch) ----------

export interface TradeCandidate {
  given: string[];           // player names I give up
  received: string[];        // player names I receive
  givenKeys: number[];       // player_key ids (stable dedup key)
  receivedKeys: number[];    // player_key ids
  myValueEdge: number;       // my DDF Value gain (receive - give)
  opponentMarketEdge: number; // opponent's market-chart edge (they break even or win)
  myLineupPointChange: number; // my starting-lineup point change
  reasons: string[];          // human-readable reasons this trade works
}

export interface PairResult {
  trades: TradeCandidate[];
  unmatchedMine: string[];
  unmatchedTheirs: string[];
}

export type FindTradesForPair = (
  settings: { scoring: string; teams: number; superflex: number },
  mineRoster: string[],
  theirRoster: string[],
  opts?: { limit?: number; maxSize?: number },
) => Promise<PairResult>;

// ---------- batch types ----------

export interface Opponent {
  name: string;
  roster: string[];
}

export interface LeagueTradeCandidate extends TradeCandidate {
  opponent: string;          // opponent name
}

export interface LeagueResult {
  trades: LeagueTradeCandidate[];
  total: number;             // before cap
  duplicatesRemoved: number;
  perOpponent: Array<{
    name: string;
    tradesFound: number;     // before dedup
    unmatchedNames: string[];
  }>;
}

// ---------- dedup helpers ----------

// Canonical key for a trade: sorted player keys on each side, joined.
// Two trades with the same players (regardless of opponent) are duplicates.
function tradeKey(t: TradeCandidate): string {
  const give = t.givenKeys.slice().sort((a, b) => a - b).join(",");
  const recv = t.receivedKeys.slice().sort((a, b) => a - b).join(",");
  return `${give}|${recv}`;
}

// Same trade seen "both directions": I give A for B vs I give B for A.
// The reverse of give|recv is recv|give.
function reverseKey(key: string): string {
  const [give, recv] = key.split("|");
  return `${recv}|${give}`;
}

// ---------- main ----------

const DEFAULT_LIMIT = 25;
const MAX_OPPONENTS = 15;

export async function findTradesLeague(
  settings: { scoring: string; teams: number; superflex: number },
  mine: string[],
  opponents: Opponent[],
  findPair: FindTradesForPair,
  opts?: { limit?: number; maxSize?: number },
): Promise<LeagueResult> {
  if (!mine.length) {
    throw new Error("mine roster is empty");
  }
  if (!opponents.length) {
    throw new Error("opponents list is empty");
  }
  if (opponents.length > MAX_OPPONENTS) {
    throw new Error(`too many opponents: ${opponents.length} (max ${MAX_OPPONENTS})`);
  }

  const limit = Math.min(200, Math.max(1, opts?.limit ?? DEFAULT_LIMIT));
  const pairOpts = { limit: 50, maxSize: opts?.maxSize };

  // Run all pairs (sequential to stay within edge-function memory/CPU).
  const allTrades: LeagueTradeCandidate[] = [];
  const perOpponent: LeagueResult["perOpponent"] = [];

  for (const opp of opponents) {
    if (!opp.roster.length) {
      perOpponent.push({ name: opp.name, tradesFound: 0, unmatchedNames: [] });
      continue;
    }

    const result = await findPair(settings, mine, opp.roster, pairOpts);
    const tagged: LeagueTradeCandidate[] = result.trades.map((t) => ({
      ...t,
      opponent: opp.name,
    }));
    allTrades.push(...tagged);
    perOpponent.push({
      name: opp.name,
      tradesFound: result.trades.length,
      unmatchedNames: [
        ...result.unmatchedMine.map((n) => `(mine) ${n}`),
        ...result.unmatchedTheirs.map((n) => `(${opp.name}) ${n}`),
      ],
    });
  }

  // Deduplicate: same player sets across opponents keeps the best;
  // same trade both directions keeps only the one with higher myLineupPointChange.
  const seen = new Map<string, LeagueTradeCandidate>();
  for (const trade of allTrades) {
    const key = tradeKey(trade);
    const rev = reverseKey(key);
    // Check if a reverse already exists — drop the worse one.
    const existingReverse = seen.get(rev);
    if (existingReverse) {
      if (trade.myLineupPointChange > existingReverse.myLineupPointChange) {
        seen.delete(rev);
        seen.set(key, trade);
      }
      // else keep the existing one
      continue;
    }
    const existing = seen.get(key);
    if (!existing || trade.myLineupPointChange > existing.myLineupPointChange) {
      seen.set(key, trade);
    }
  }

  const deduped = [...seen.values()];
  const duplicatesRemoved = allTrades.length - deduped.length;

  // Rank: positive lineup-point gain for me AND opponent Trade chart average edge.
  // Default sort: my lineup point change descending, then opponent Trade chart average edge descending.
  const ranked = deduped
    .filter((t) => t.myLineupPointChange > 0 && t.opponentMarketEdge >= 0)
    .sort((a, b) =>
      b.myLineupPointChange - a.myLineupPointChange ||
      b.opponentMarketEdge - a.opponentMarketEdge ||
      a.given.length + a.received.length - (b.given.length + b.received.length) ||
      a.opponent.localeCompare(b.opponent)
    );

  return {
    trades: ranked.slice(0, limit),
    total: ranked.length,
    duplicatesRemoved,
    perOpponent,
  };
}
