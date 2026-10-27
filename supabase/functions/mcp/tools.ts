// JEG-1012: tool logic for the remote MCP endpoint. Pure functions, no Deno
// APIs, so the same file runs under node in tests/test_mcp_remote.py.
//
// Lookups and trade math run here, so a tool call returns a small answer
// instead of the whole player list.

import { type Deps, finish, prepare } from "./state.ts";
import { type Finder, type FinderRow, findTradesForPair } from "./find-trades.ts";
import {
  type RosterShape,
  type ViabilityConfig,
  type ViabilityRow,
  type TradeOfferInput,
  DEFAULT_CONFIG,
  runViabilityChecks,
  scoreAndRankOffers,
  selectPackage,
} from "./viability.ts";

export interface PlayerValue {
  player_key: number;
  name: string;
  pos: string;
  value: number;
  tier: string;
}

export interface ValuesResponse {
  attribution: string;
  as_of: string | null;
  setting: { scoring: string; teams: number; superflex: number };
  players: PlayerValue[];
  sources_included: string[];
  sources_excluded: Array<{ key: string; reason: string }>;
}

export type FetchValues = (
  scoring: string,
  teams: number,
  superflex: number,
  league?: Record<string, unknown>,
) => Promise<ValuesResponse>;

/** Extended player record with per-chart values (from get-values?include=charts). */
export interface ChartPlayerValue extends PlayerValue {
  chart_values: Record<string, number | null>;
  ddf_value_charts: number | null;
  ddf_value_projections: number | null;
}

export interface ChartValuesResponse extends ValuesResponse {
  players: ChartPlayerValue[];
}

/** Fetches values with chart series included (for find_trades). */
export type FetchValuesWithCharts = (
  scoring: string,
  teams: number,
  superflex: number,
  league?: Record<string, unknown>,
) => Promise<ChartValuesResponse>;

export interface ToolResult {
  content: Array<{ type: "text"; text: string }>;
  structuredContent?: Record<string, unknown>;
  isError?: boolean;
}

const SCORINGS = ["standard", "half_ppr", "ppr"];
const TEAMS = [8, 10, 12, 14];
const POSITIONS = ["QB", "RB", "WR", "TE", "all"];
const EXPLAIN_TOPICS = [
  "methodology",
  "sources",
  "value_scale",
  "scoring_formats",
  "superflex",
  "tiers",
  "how_to_trade",
];

const settingsProps = {
  scoring: { type: "string", enum: SCORINGS, default: "ppr", description: "League scoring format" },
  teams: { type: "integer", enum: TEAMS, default: 12, description: "Number of teams in the league" },
  superflex: { type: "boolean", default: false, description: "Whether the league has a superflex slot" },
  state: {
    type: "string",
    description:
      "Optional: a DDF state pasted from the site (a ```ddf-state block, JSON, or a site link). Supplies the league settings; explicit settings above win.",
  },
};

const listProps = {
  give: { type: "string", description: "Comma-separated names: what you give (Compare a trade)" },
  get: { type: "string", description: "Comma-separated names: what you get (Compare a trade)" },
  mine: { type: "string", description: "Comma-separated names: your roster (Find a trade)" },
  theirs: { type: "string", description: "Comma-separated names: their roster (Find a trade)" },
  target: { type: "string", description: "One player name (Trade targets)" },
};

// Viability configuration properties, exposed as optional tool arguments.
const viabilityProps = {
  viable_only: { type: "boolean", default: false, description: "Return only viable trades (all 9 checks pass)" },
  roster_shape: {
    type: "object",
    description: "Starting lineup shape (default: QB 1, RB 2, WR 2, TE 1, FLEX 1, SUPERFLEX per league setting)",
    properties: {
      QB: { type: "integer", default: 1 }, RB: { type: "integer", default: 2 },
      WR: { type: "integer", default: 2 }, TE: { type: "integer", default: 1 },
      FLEX: { type: "integer", default: 1 }, SUPERFLEX: { type: "integer", default: 0 },
    },
  },
  min_ddf_edge: { type: "number", default: 0, description: "Minimum DDF value gain for viability (default 0)" },
  min_market_net: { type: "number", default: 0, description: "Minimum market-value gain for the other team (default 0)" },
  depth_player_cutoff: { type: "number", default: 0.5, description: "Minimum DDF value for a player to count as depth" },
  dead_weight_cutoff: { type: "number", default: 0.5, description: "Maximum DDF value for a droppable player" },
  min_rb_backups: { type: "integer", default: 1, description: "Minimum healthy RB backups beyond starters" },
  min_wr_backups: { type: "integer", default: 1, description: "Minimum healthy WR backups beyond starters" },
};

/** Build a RosterShape from tool args, defaulting SUPERFLEX from the league setting. */
function rosterShape(args: Record<string, unknown>, superflex: number): RosterShape {
  const rs = (args.roster_shape ?? {}) as Record<string, unknown>;
  return {
    QB: Number(rs.QB ?? 1),
    RB: Number(rs.RB ?? 2),
    WR: Number(rs.WR ?? 2),
    TE: Number(rs.TE ?? 1),
    FLEX: Number(rs.FLEX ?? 1),
    SUPERFLEX: Number(rs.SUPERFLEX ?? (superflex ? 1 : 0)),
  };
}

/** Build a ViabilityConfig from tool args. */
function viabilityConfig(args: Record<string, unknown>): ViabilityConfig {
  return {
    ...DEFAULT_CONFIG,
    minDdfEdge: Number(args.min_ddf_edge ?? DEFAULT_CONFIG.minDdfEdge),
    minMarketNet: Number(args.min_market_net ?? DEFAULT_CONFIG.minMarketNet),
    depthPlayerCutoff: Number(args.depth_player_cutoff ?? DEFAULT_CONFIG.depthPlayerCutoff),
    deadWeightCutoff: Number(args.dead_weight_cutoff ?? DEFAULT_CONFIG.deadWeightCutoff),
    minRbBackups: Number(args.min_rb_backups ?? DEFAULT_CONFIG.minRbBackups),
    minWrBackups: Number(args.min_wr_backups ?? DEFAULT_CONFIG.minWrBackups),
  };
}

export const TOOLS = [
  {
    name: "get_values",
    description:
      "Current fantasy football trade values for the user's league settings, from Data Driven Football (value above waivers, blended across sources). Returns name, position, value and tier, best first. Values have no fixed maximum.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter by position" },
        limit: { type: "integer", minimum: 1, maximum: 200, default: 50, description: "Maximum players to return" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "get_player_value",
    description:
      "Look up one or more players by name and return their trade value and tier. Partial names work.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        names: { type: "string", description: "Comma-separated player names" },
      },
      required: ["names"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "trade_targets",
    description:
      "Find players whose value is close to a given player's, as realistic 1-for-1 trade partners.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        player_name: { type: "string", description: "Player to trade (or trade for)" },
        range_pct: { type: "number", minimum: 1, maximum: 50, default: 15, description: "How close in value, in percent" },
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter targets by position" },
      },
      required: ["player_name"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "compare_trade",
    description:
      "Compare two sides of a trade by the sum of their blended values. Pass comma-separated player names for each side. Side A is what team A gives up. This is a market-value sum: it is not lineup-aware and has no per-source breakdown, so point the user to the site link for the full view.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        side_a: { type: "string", description: "Comma-separated names team A gives up" },
        side_b: { type: "string", description: "Comma-separated names team B gives up" },
      },
      required: ["side_a", "side_b"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "read_state",
    description:
      "Read a DDF state pasted from the Data Driven Football site (a ```ddf-state block, JSON, or a site link): the league, rosters and trade the person was working on. Resolves names to players, prices them, and reports anything it could not match. Use this first when the user pastes site work.",
    inputSchema: {
      type: "object",
      properties: { state: { type: "string", description: "The pasted block, JSON or site link" } },
      required: ["state"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "make_state",
    description:
      "Save work from this chat as a DDF state the person can paste into the Data Driven Football site (or open by link): league settings plus a trade, rosters or a target player, by name. Returns the pasteable block and the link.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        ...listProps,
        view: { type: "string", enum: ["compare", "targets", "finder"], description: "Which site view to open; inferred if omitted" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "find_trades",
    description:
      "Find trade packages between two rosters, scored for viability. Lists trades where you gain DDF Value and at least 3 of 4 trade charts say the other team breaks even or wins. Each trade is scored on 9 viability checks (arbitrage, fairness, lineup improvement, position protection, depth, roster space, QB, guardrails) and labelled High/Med-High/Medium when viable. Set viable_only to see only the trades most likely to be accepted.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        mine: { type: "string", description: "Comma-separated names: your full roster" },
        theirs: { type: "string", description: "Comma-separated names: their full roster" },
        max_per_side: { type: "integer", minimum: 1, maximum: 4, default: 2, description: "Maximum players each side trades (default 2-for-2)" },
        min_rival_edge: { type: "number", minimum: 0, default: 0, description: "Minimum average chart-value edge the other team needs (0 = any fair trade)" },
        limit: { type: "integer", minimum: 1, maximum: 50, default: 10, description: "Maximum trade candidates to return" },
        ...viabilityProps,
      },
      required: ["mine", "theirs"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "find_trades_league",
    description:
      "Find the best trades across an entire league. Takes your roster and a list of opponents with their rosters, scores every candidate on 9 viability checks, ranks viable offers first, and selects the best package of trades (no player sent twice, each opponent at most once). Returns per-trade viability labels, failure reasons, and the package with your projected lineup after.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        mine: { type: "string", description: "Comma-separated names: your full roster" },
        opponents: {
          type: "array",
          description: "Opposing teams: [{name, roster}] where roster is comma-separated names",
          items: {
            type: "object",
            properties: {
              name: { type: "string", description: "Team name" },
              roster: { type: "string", description: "Comma-separated player names" },
            },
            required: ["name", "roster"],
          },
          minItems: 1,
          maxItems: 15,
        },
        max_per_side: { type: "integer", minimum: 1, maximum: 4, default: 2, description: "Maximum players each side trades" },
        min_rival_edge: { type: "number", minimum: 0, default: 0, description: "Minimum market-value edge for the other team" },
        limit: { type: "integer", minimum: 1, maximum: 100, default: 25, description: "Maximum trade candidates to return" },
        ...viabilityProps,
      },
      required: ["mine", "opponents"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "explain",
    description:
      "Explain how Data Driven Football values work: methodology, sources, value scale, scoring formats, superflex, tiers, how to use values in trades.",
    inputSchema: {
      type: "object",
      properties: { topic: { type: "string", enum: EXPLAIN_TOPICS } },
      required: ["topic"],
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

export class ToolInputError extends Error {}
// A dependency is down, not the caller's input: same message to the client, logged as an outage.
export class ToolUnavailableError extends ToolInputError {}

/** Extra dependencies for tools that need the finder (find_trades). */
export interface FinderDeps {
  finder: Finder | null;
  fetchCharts: FetchValuesWithCharts | null;
}

function settings(args: Record<string, unknown>) {
  const scoring = String(args.scoring ?? "ppr");
  const teams = Number(args.teams ?? 12);
  if (!SCORINGS.includes(scoring)) {
    throw new ToolInputError(`invalid scoring: ${scoring}. Must be one of: ${SCORINGS.join(", ")}`);
  }
  if (!TEAMS.includes(teams)) {
    throw new ToolInputError(`invalid teams: ${teams}. Must be one of: ${TEAMS.join(", ")}`);
  }
  const superflex = args.superflex === true || args.superflex === 1 || args.superflex === "true" ? 1 : 0;
  // JEG-1031: the rest of a pasted league (roster shape, shares, weeks, advanced), priced by get-values.
  const league = args.league && typeof args.league === "object" ? args.league as Record<string, unknown> : undefined;
  return { scoring, teams, superflex, league };
}

function position(args: Record<string, unknown>): string {
  const pos = String(args.position ?? "all");
  if (!POSITIONS.includes(pos)) {
    throw new ToolInputError(`invalid position: ${pos}. Must be one of: ${POSITIONS.join(", ")}`);
  }
  return pos;
}

function header(data: ValuesResponse, s: { scoring: string; teams: number; superflex: number }): string[] {
  return [
    data.attribution,
    `As of: ${data.as_of || "unknown"}`,
    `Settings: ${s.scoring}, ${s.teams} teams${s.superflex ? ", superflex" : ""}`,
  ];
}

function norm(s: string): string {
  return s.toLowerCase().replace(/[.'’]/g, "").replace(/\s+/g, " ").trim();
}

// Exact name first, then unique partial match, else the best-valued partial.
export function findPlayer(players: PlayerValue[], query: string): PlayerValue | null {
  const q = norm(query);
  if (!q) return null;
  const exact = players.find((p) => norm(p.name) === q);
  if (exact) return exact;
  const partial = players.filter((p) => norm(p.name).includes(q));
  if (!partial.length) return null;
  return partial.reduce((a, b) => (b.value > a.value ? b : a));
}

function ok(text: string, structured: Record<string, unknown>): ToolResult {
  return { content: [{ type: "text", text }], structuredContent: structured };
}

export async function runTool(
  name: string,
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  if (name === "read_state") return await readState(args, fetchValues, deps);
  if (name === "make_state") return await makeState(args, fetchValues, deps);
  if (name === "find_trades") return await findTradesHandler(args, fetchValues, deps, finderDeps);
  if (name === "find_trades_league") return await findTradesLeagueHandler(args, fetchValues, deps, finderDeps);
  const prepared = prepare(args, deps);
  args = prepared.args;
  if (name === "explain") {
    const dummy = { scoring: "ppr", teams: 12, superflex: 0 };
    return finish(explain(String(args.topic ?? "")), { prepared, deps, settings: dummy, view: "targets", bare: true });
  }

  const s = settings(args);
  const entry = (input: string, p: PlayerValue | null) => p ? { key: String(p.player_key), name: p.name } : { name: input };

  if (name === "get_values") {
    const pos = position(args);
    const limit = Math.min(200, Math.max(1, Number(args.limit ?? 50) || 50));
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const players = data.players.filter((p) => pos === "all" || p.pos === pos).slice(0, limit);
    const text = [
      ...header(data, s),
      `Sources included: ${data.sources_included.join(", ")}`,
      "",
      "Rank | Player | Pos | Value | Tier",
      ...players.map((p, i) => `${i + 1} | ${p.name} | ${p.pos} | ${p.value} | ${p.tier}`),
    ].join("\n");
    return finish(
      ok(text, { as_of: data.as_of, setting: data.setting, sources_included: data.sources_included, players }),
      { prepared, deps, settings: s, view: "targets" },
    );
  }

  if (name === "get_player_value") {
    const names = String(args.names ?? "").split(",").map((n) => n.trim()).filter(Boolean);
    if (!names.length) throw new ToolInputError("names is required");
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const results = names.map((input) => ({ input, player: findPlayer(data.players, input) }));
    const text = [
      ...header(data, s),
      "",
      ...results.map((r) =>
        r.player
          ? `${r.player.name} (${r.player.pos}): value ${r.player.value}, tier ${r.player.tier}`
          : `${r.input}: NOT FOUND`
      ),
    ].join("\n");
    const first = results.find((r) => r.player);
    return finish(ok(text, { as_of: data.as_of, setting: data.setting, results }), {
      prepared, deps, settings: s, view: "targets",
      work: first ? { target: entry(first.input, first.player) } : undefined,
    });
  }

  if (name === "trade_targets") {
    const pos = position(args);
    const pct = Math.min(50, Math.max(1, Number(args.range_pct ?? 15) || 15));
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const player = findPlayer(data.players, String(args.player_name ?? ""));
    if (!player) {
      return {
        content: [{ type: "text", text: `${data.attribution}\n\nPlayer "${args.player_name}" not found. Check the spelling or try a partial name.` }],
        isError: true,
      };
    }
    const range = player.value * (pct / 100);
    const targets = data.players
      .filter((p) =>
        p.player_key !== player.player_key && Math.abs(p.value - player.value) <= range &&
        (pos === "all" || p.pos === pos)
      )
      .sort((a, b) => Math.abs(a.value - player.value) - Math.abs(b.value - player.value))
      .slice(0, 20)
      .map((p) => ({ ...p, diff: Math.round((p.value - player.value) * 10) / 10 }));
    const text = [
      ...header(data, s),
      "",
      `Trade targets for ${player.name} (${player.pos}, value ${player.value}, tier ${player.tier}):`,
      "Player | Pos | Value | Tier | Diff",
      ...targets.map((t) => `${t.name} | ${t.pos} | ${t.value} | ${t.tier} | ${t.diff >= 0 ? "+" : ""}${t.diff.toFixed(1)}`),
    ].join("\n");
    return finish(ok(text, { as_of: data.as_of, setting: data.setting, player, targets }), {
      prepared, deps, settings: s, view: "targets", work: { target: entry(String(args.player_name), player) },
    });
  }

  if (name === "compare_trade") {
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const side = (raw: unknown) =>
      String(raw ?? "").split(",").map((n) => n.trim()).filter(Boolean).map((input) => ({
        input,
        player: findPlayer(data.players, input),
      }));
    const a = side(args.side_a);
    const b = side(args.side_b);
    if (!a.length || !b.length) throw new ToolInputError("side_a and side_b each need at least one name");
    const total = (x: typeof a) => x.reduce((t, r) => t + (r.player?.value ?? 0), 0);
    const sumA = Math.round(total(a) * 10) / 10;
    const sumB = Math.round(total(b) * 10) / 10;
    const diff = Math.round((sumA - sumB) * 10) / 10;
    const notFound = [...a, ...b].filter((r) => !r.player).map((r) => r.input);
    const verdict = Math.abs(diff) < 2
      ? "roughly even"
      : diff > 0
      ? `team B comes out ahead by ${diff.toFixed(1)} (team A gives up more value)`
      : `team A comes out ahead by ${(-diff).toFixed(1)} (team B gives up more value)`;
    const fmt = (x: typeof a) =>
      x.map((r) => r.player ? `  ${r.player.name} (${r.player.pos}): ${r.player.value}` : `  ${r.input}: NOT FOUND`).join("\n");
    const text = [
      ...header(data, s),
      "",
      `Team A gives up (total ${sumA.toFixed(1)}):`,
      fmt(a),
      `Team B gives up (total ${sumB.toFixed(1)}):`,
      fmt(b),
      "",
      `Verdict (market-value sum, not lineup-aware; a gap under 2 points counts as roughly even, a rule of thumb): ${verdict}.`,
      "The site's Compare a trade shows the per-source breakdown for this trade; open the link below.",
      ...(notFound.length ? [`Warning: not found, counted as 0: ${notFound.join(", ")}`] : []),
    ].join("\n");
    // The site's Compare a trade reads "give" as what the person gives up: team A is the person.
    return finish(
      ok(text, {
        as_of: data.as_of,
        setting: data.setting,
        side_a: { total: sumA, players: a },
        side_b: { total: sumB, players: b },
        difference: diff,
        verdict,
        method: "sum_of_blended_values",
        not_found: notFound,
      }),
      {
        prepared, deps, settings: s, view: "compare",
        work: { give: a.map((r) => entry(r.input, r.player)), get: b.map((r) => entry(r.input, r.player)) },
      },
    );
  }

  throw new ToolInputError(`unknown tool: ${name}`);
}

// ---------- find_trades tool ----------

/** Convert a ChartPlayerValue into the FinderRow format finder.js expects. */
function toFinderRow(p: ChartPlayerValue): FinderRow {
  const values: Record<string, number | null> = {
    ddf_value: p.value,
    ddf_value_charts: p.ddf_value_charts,
    ddf_value_projections: p.ddf_value_projections,
  };
  for (const [k, v] of Object.entries(p.chart_values)) values[k] = v;
  return { player_key: p.player_key, name: p.name, pos: p.pos, values, ddfTier: p.tier };
}

function findChartPlayer(players: ChartPlayerValue[], query: string): ChartPlayerValue | null {
  return findPlayer(players, query) as ChartPlayerValue | null;
}

async function findTradesHandler(
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  if (!finderDeps?.finder) {
    throw new ToolUnavailableError("The trade finder is unavailable right now. Try again shortly.");
  }
  if (!finderDeps?.fetchCharts) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }

  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);

  const mineNames = String(a.mine ?? "").split(",").map((n) => n.trim()).filter(Boolean);
  const theirNames = String(a.theirs ?? "").split(",").map((n) => n.trim()).filter(Boolean);
  if (!mineNames.length) throw new ToolInputError("mine is required: comma-separated roster names");
  if (!theirNames.length) throw new ToolInputError("theirs is required: comma-separated roster names");

  const data = await finderDeps.fetchCharts(s.scoring, s.teams, s.superflex, s.league);
  const chartPlayers = data.players;

  // Resolve names to rows.
  const resolve = (names: string[]) => {
    const matched: ChartPlayerValue[] = [];
    const unmatched: string[] = [];
    for (const name of names) {
      const p = findChartPlayer(chartPlayers, name);
      if (p) matched.push(p);
      else unmatched.push(name);
    }
    return { matched, unmatched };
  };

  const mineRes = resolve(mineNames);
  const theirRes = resolve(theirNames);
  const unmatched = [...mineRes.unmatched, ...theirRes.unmatched];

  if (!mineRes.matched.length) throw new ToolInputError("No players matched on your roster. Check the spelling.");
  if (!theirRes.matched.length) throw new ToolInputError("No players matched on their roster. Check the spelling.");

  const mineRows = mineRes.matched.map(toFinderRow);
  const theirRows = theirRes.matched.map(toFinderRow);

  const maxPerSide = Number(a.max_per_side ?? 2) || 2;
  const minRivalEdge = Number(a.min_rival_edge ?? 0) || 0;
  const limit = Number(a.limit ?? 10) || 10;

  const result = findTradesForPair(finderDeps.finder, mineRows, theirRows, {
    maxSize: maxPerSide,
    minRivalEdge,
    limit: limit + 20, // fetch extra before viability filtering
  });

  // --- Viability scoring ---
  const shape = rosterShape(a, s.superflex);
  const vConfig = viabilityConfig(a);
  const viableOnly = a.viable_only === true || a.viable_only === "true";

  // Build lookup by player_key for full rows.
  const rowByKey = new Map<number, FinderRow>();
  for (const r of mineRows) rowByKey.set(r.player_key, r);
  for (const r of theirRows) rowByKey.set(r.player_key, r);

  const offers: TradeOfferInput[] = result.trades.map((t) => ({
    team: "opponent",
    userGives: t.give.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
    userGets: t.receive.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
    userRoster: mineRows,
    theirRoster: theirRows,
  }));

  let scored = scoreAndRankOffers(offers, shape, vConfig);
  if (viableOnly) scored = scored.filter((o) => o.viable);
  scored = scored.slice(0, limit);

  const entry = (input: string, p: PlayerValue | null) =>
    p ? { key: String(p.player_key), name: p.name } : { name: input };

  // Format text output.
  const lines: string[] = [
    data.attribution,
    `As of: ${data.as_of || "unknown"}`,
    `Settings: ${s.scoring}, ${s.teams} teams${s.superflex ? ", superflex" : ""}`,
    "",
    `Found ${result.total} trade${result.total === 1 ? "" : "s"} (showing ${scored.length}${viableOnly ? " viable" : ""}).`,
    `Your roster: ${mineRes.matched.length} matched, ${mineRes.unmatched.length} not found; searched ${result.mine.searched} of ${result.mine.of} priced.`,
    `Their roster: ${theirRes.matched.length} matched, ${theirRes.unmatched.length} not found; searched ${result.theirs.searched} of ${result.theirs.of} priced.`,
  ];
  if (unmatched.length) lines.push(`Not found: ${unmatched.join(", ")}`);
  lines.push("");

  for (let i = 0; i < scored.length; i++) {
    const o = scored[i];
    const giveStr = o.userGives.map((p) => `${p.name} (${p.pos}, ${p.ddfValue ?? "?"})`).join(", ");
    const getStr = o.userGets.map((p) => `${p.name} (${p.pos}, ${p.ddfValue ?? "?"})`).join(", ");
    const viabilityTag = o.viable
      ? `[${o.label}]`
      : `[NOT VIABLE: ${o.failedChecks.join("; ")}]`;
    lines.push(`${i + 1}. You give: ${giveStr}`);
    lines.push(`   You get: ${getStr}`);
    lines.push(`   Your edge: +${o.ddfEdge.toFixed(1)} DDF | Lineup: ${o.userLineupDelta >= 0 ? "+" : ""}${o.userLineupDelta.toFixed(1)} | ${viabilityTag}`);
    if (o.temporaryGap) lines.push(`   ⚠ Temporary lineup gap (injured players out)`);
    lines.push("");
  }
  if (!scored.length) lines.push(viableOnly
    ? "No viable trades found. Try without viable_only to see all candidates."
    : "No trades found where you gain DDF Value and the charts say the rival breaks even.");

  // Structured output.
  const structured = {
    as_of: data.as_of,
    setting: data.setting,
    trades: scored,
    total: result.total,
    viableCount: scored.filter((o) => o.viable).length,
    mine: { ...result.mine, unmatched: mineRes.unmatched },
    theirs: { ...result.theirs, unmatched: theirRes.unmatched },
    chart_keys: result.chartKeys,
  };

  // Work for the state: mine/theirs as entries.
  const work = {
    mine: mineNames.map((n) => entry(n, findPlayer(data.players, n))),
    theirs: theirNames.map((n) => entry(n, findPlayer(data.players, n))),
  };

  return finish(ok(lines.join("\n"), structured), {
    prepared, deps, settings: s, view: "finder", work,
  });
}

/** Minimal ViabilityRow from a trade candidate player summary. */
function toViabilityRow(p: { player_key: number; name: string; pos: string; value: number | null }): ViabilityRow {
  return { player_key: p.player_key, name: p.name, pos: p.pos, values: { ddf_value: p.value } };
}

// ---------- find_trades_league tool ----------

async function findTradesLeagueHandler(
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  if (!finderDeps?.finder) {
    throw new ToolUnavailableError("The trade finder is unavailable right now. Try again shortly.");
  }
  if (!finderDeps?.fetchCharts) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }

  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);

  const mineNames = String(a.mine ?? "").split(",").map((n: string) => n.trim()).filter(Boolean);
  if (!mineNames.length) throw new ToolInputError("mine is required: comma-separated roster names");

  const opponents = a.opponents as Array<{ name: string; roster: string }> | undefined;
  if (!opponents?.length) throw new ToolInputError("opponents is required: [{name, roster}]");
  if (opponents.length > 15) throw new ToolInputError("too many opponents (max 15)");

  const data = await finderDeps.fetchCharts(s.scoring, s.teams, s.superflex, s.league);
  const chartPlayers = data.players;

  const resolve = (names: string[]) => {
    const matched: ChartPlayerValue[] = [];
    const unmatched: string[] = [];
    for (const name of names) {
      const p = findChartPlayer(chartPlayers, name);
      if (p) matched.push(p);
      else unmatched.push(name);
    }
    return { matched, unmatched };
  };

  const mineRes = resolve(mineNames);
  if (!mineRes.matched.length) throw new ToolInputError("No players matched on your roster. Check the spelling.");
  const mineRows = mineRes.matched.map(toFinderRow);

  const shape = rosterShape(a, s.superflex);
  const vConfig = viabilityConfig(a);
  const viableOnly = a.viable_only === true || a.viable_only === "true";
  const maxPerSide = Number(a.max_per_side ?? 2) || 2;
  const minRivalEdge = Number(a.min_rival_edge ?? 0) || 0;
  const limit = Math.min(100, Math.max(1, Number(a.limit ?? 25) || 25));

  const allOffers: TradeOfferInput[] = [];
  const perOpponent: Array<{ name: string; tradesFound: number; unmatchedNames: string[] }> = [];
  const allUnmatched: string[] = [...mineRes.unmatched];

  // Run each opponent pair sequentially (edge function memory).
  for (const opp of opponents) {
    const oppNames = String(opp.roster ?? "").split(",").map((n: string) => n.trim()).filter(Boolean);
    if (!oppNames.length) {
      perOpponent.push({ name: opp.name, tradesFound: 0, unmatchedNames: [] });
      continue;
    }
    const oppRes = resolve(oppNames);
    allUnmatched.push(...oppRes.unmatched);
    if (!oppRes.matched.length) {
      perOpponent.push({ name: opp.name, tradesFound: 0, unmatchedNames: oppRes.unmatched });
      continue;
    }

    const theirRows = oppRes.matched.map(toFinderRow);
    const rowByKey = new Map<number, FinderRow>();
    for (const r of mineRows) rowByKey.set(r.player_key, r);
    for (const r of theirRows) rowByKey.set(r.player_key, r);

    const pairResult = findTradesForPair(finderDeps.finder, mineRows, theirRows, {
      maxSize: maxPerSide,
      minRivalEdge,
      limit: 50,
    });

    const pairOffers: TradeOfferInput[] = pairResult.trades.map((t) => ({
      team: opp.name,
      userGives: t.give.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
      userGets: t.receive.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
      userRoster: mineRows,
      theirRoster: theirRows,
    }));

    allOffers.push(...pairOffers);
    perOpponent.push({
      name: opp.name,
      tradesFound: pairResult.trades.length,
      unmatchedNames: oppRes.unmatched,
    });
  }

  // Score, rank, and optionally filter.
  let scored = scoreAndRankOffers(allOffers, shape, vConfig);
  if (viableOnly) scored = scored.filter((o) => o.viable);

  // Package: best viable combination.
  const pkg = selectPackage(scored, mineRows, shape, vConfig.ddfKey);

  const shownTrades = scored.slice(0, limit);
  const viableCount = scored.filter((o) => o.viable).length;

  // Text output.
  const lines: string[] = [
    data.attribution,
    `As of: ${data.as_of || "unknown"}`,
    `Settings: ${s.scoring}, ${s.teams} teams${s.superflex ? ", superflex" : ""}`,
    "",
    `League scan: ${opponents.length} opponent${opponents.length === 1 ? "" : "s"}, ${scored.length} candidate${scored.length === 1 ? "" : "s"} (${viableCount} viable), showing ${shownTrades.length}.`,
    `Your roster: ${mineRes.matched.length} matched, ${mineRes.unmatched.length} not found.`,
  ];
  if (allUnmatched.length) lines.push(`Not found: ${allUnmatched.join(", ")}`);
  lines.push("");

  if (pkg.offers.length > 0) {
    lines.push(`=== RECOMMENDED PACKAGE (${pkg.offers.length} trade${pkg.offers.length === 1 ? "" : "s"}, total edge +${pkg.totalDdfEdge.toFixed(1)}) ===`);
    for (const o of pkg.offers) {
      const giveStr = o.userGives.map((p) => `${p.name} (${p.pos})`).join(", ");
      const getStr = o.userGets.map((p) => `${p.name} (${p.pos})`).join(", ");
      lines.push(`  vs ${o.team}: give ${giveStr} → get ${getStr} [${o.label}] +${o.ddfEdge.toFixed(1)} DDF`);
    }
    lines.push("");
  }

  lines.push("=== ALL CANDIDATES ===");
  for (let i = 0; i < shownTrades.length; i++) {
    const o = shownTrades[i];
    const giveStr = o.userGives.map((p) => `${p.name} (${p.pos}, ${p.ddfValue ?? "?"})`).join(", ");
    const getStr = o.userGets.map((p) => `${p.name} (${p.pos}, ${p.ddfValue ?? "?"})`).join(", ");
    const viabilityTag = o.viable
      ? `[${o.label}]`
      : `[NOT VIABLE: ${o.failedChecks.join("; ")}]`;
    lines.push(`${i + 1}. vs ${o.team}: give ${giveStr} → get ${getStr}`);
    lines.push(`   Edge: +${o.ddfEdge.toFixed(1)} DDF | Lineup: ${o.userLineupDelta >= 0 ? "+" : ""}${o.userLineupDelta.toFixed(1)} | ${viabilityTag}`);
    if (o.temporaryGap) lines.push(`   ⚠ Temporary lineup gap`);
  }
  if (!shownTrades.length) lines.push(viableOnly
    ? "No viable trades found across the league."
    : "No trades found where you gain DDF Value and the charts say the rival breaks even.");

  const structured = {
    as_of: data.as_of,
    setting: data.setting,
    package: {
      offers: pkg.offers,
      totalDdfEdge: pkg.totalDdfEdge,
      userLineupAfter: pkg.userLineupAfter,
    },
    trades: shownTrades,
    total: scored.length,
    viableCount,
    perOpponent,
    mine: { matched: mineRes.matched.length, unmatched: mineRes.unmatched },
  };

  const entry = (input: string, p: PlayerValue | null) =>
    p ? { key: String(p.player_key), name: p.name } : { name: input };
  const work = {
    mine: mineNames.map((n: string) => entry(n, findPlayer(data.players, n))),
  };

  return finish(ok(lines.join("\n"), structured), {
    prepared, deps, settings: s, view: "finder", work,
  });
}

const EXPLANATIONS: Record<string, string> = {
  methodology:
    "Values are 'value above waivers': how much more a player is expected to produce than a freely available replacement at the same position, in the user's league (scoring, team count, superflex). The headline value (DDF Value) is the average of the four published trade charts, each adjusted to the user's league (position and bench weighting); the projection sources are an alternate version. A stale or held source is left out of the average rather than counted as zero. Full method: the site's methodology pages.",
  sources:
    "Projection sources: ESPN, CBS rest-of-season, Razzball. Published trade charts: FantasyCalc, USA Today, FantasyPros, CBS. The get_values response lists which sources are included and excluded for the current week.",
  value_scale:
    "Value is points above a replacement-level player in that league. There is no fixed maximum: read values against each other, with the top of the list setting the scale. Players the league leaves on the waiver wire are worth about 0, and a value near 0 means replacement level in that league, not worthless. Always quote the value the tool returned.",
  scoring_formats:
    "standard = no points per reception, half_ppr = 0.5, ppr = 1.0. PPR lifts high-target receivers and pass-catching backs; standard favors rushers and touchdown-dependent players.",
  superflex:
    "Superflex adds a slot that takes a QB, which sharply raises QB values and shifts replacement levels. Charts that publish their own superflex values use them.",
  tiers:
    "Tier is where a player sits in the league: starter (fills a starting lineup slot), bench (worth rostering as depth) or waiver (replacement level, freely available). It is not a quality band, so two players in the same tier can have very different values; compare values, not tiers.",
  how_to_trade:
    "1) Use compare_trade on both sides. 2) As a rough guide, a gap under about 2 points is roughly even and 5 or more is meaningful; this is a rule of thumb, not a measured threshold. 3) Use trade_targets to find similar-value partners. 4) Your own roster needs can outweigh market value. Values update weekly.",
};

function explain(topic: string): ToolResult {
  const text = EXPLANATIONS[topic];
  if (!text) throw new ToolInputError(`unknown topic: ${topic}. Must be one of: ${EXPLAIN_TOPICS.join(", ")}`);
  return ok(`Data Driven Football\n\n${text}`, { topic, text });
}

// ---------- state tools (JEG-1027) ----------

type Entry = { key?: string; name?: string };
const WORK_LISTS = ["give", "get", "mine", "theirs"];

function resolveEntry(players: PlayerValue[], e: Entry): { input: string; player: PlayerValue | null } {
  const byKey = e.key !== undefined ? players.find((p) => String(p.player_key) === e.key) ?? null : null;
  const player = byKey ?? (e.name ? findPlayer(players, e.name) : null);
  return { input: e.name ?? e.key ?? "", player };
}

function inferView(work: Record<string, unknown>): string {
  if (work.give || work.get) return "compare";
  if (work.mine || work.theirs) return "finder";
  return "targets";
}

async function readState(args: Record<string, unknown>, fetchValues: FetchValues, deps?: Deps): Promise<ToolResult> {
  if (!deps?.codec) throw new ToolUnavailableError("The shared state reader is unavailable right now. Try again shortly.");
  if (!String(args.state ?? "").trim()) throw new ToolInputError("state is required: paste a ddf-state block or a site link");
  const prepared = prepare(args, deps);
  if (!prepared.state) {
    throw new ToolInputError(`No usable DDF state found in the text. ${prepared.warnings.join(" ")}`.trim());
  }
  const s = settings(prepared.args);
  const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
  const work = (prepared.state.work ?? {}) as Record<string, unknown>;

  const lists: Record<string, Array<{ input: string; player: PlayerValue | null }>> = {};
  const resolvedWork: Record<string, unknown> = {};
  const unmatched: string[] = [];
  const lines: string[] = [...header(data, s), ""];
  for (const name of WORK_LISTS) {
    const list = work[name] as Entry[] | undefined;
    if (!list?.length) continue;
    const rows = list.map((e) => resolveEntry(data.players, e));
    lists[name] = rows;
    resolvedWork[name] = rows.map((r, i) => r.player ? { key: String(r.player.player_key), name: r.player.name } : list[i]);
    rows.filter((r) => !r.player).forEach((r) => unmatched.push(r.input));
    const total = Math.round(rows.reduce((t, r) => t + (r.player?.value ?? 0), 0) * 10) / 10;
    lines.push(`${name} (total ${total.toFixed(1)}):`);
    lines.push(...rows.map((r) => r.player ? `  ${r.player.name} (${r.player.pos}): ${r.player.value}` : `  ${r.input}: NOT FOUND`));
  }
  if (work.target) {
    const r = resolveEntry(data.players, work.target as Entry);
    lists.target = [r];
    resolvedWork.target = r.player ? { key: String(r.player.player_key), name: r.player.name } : work.target;
    if (!r.player) unmatched.push(r.input);
    lines.push(`target: ${r.player ? `${r.player.name} (${r.player.pos}): ${r.player.value}` : `${r.input}: NOT FOUND`}`);
  }
  if (!Object.keys(lists).length) lines.push("The state carries league settings only, no players.");
  if (unmatched.length) lines.push("", `Could not match: ${unmatched.join(", ")}. Ask the user to check the spelling.`);

  const view = typeof work.view === "string" ? work.view : inferView(work);
  return finish(
    ok(lines.join("\n"), { as_of: data.as_of, setting: data.setting, lists, unmatched }),
    { prepared, deps, settings: s, view, work: resolvedWork },
  );
}

async function makeState(args: Record<string, unknown>, fetchValues: FetchValues, deps?: Deps): Promise<ToolResult> {
  if (!deps?.codec) throw new ToolUnavailableError("The shared state writer is unavailable right now. Try again shortly.");
  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);
  const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
  const names = (v: unknown) => String(v ?? "").split(",").map((n) => n.trim()).filter(Boolean);
  const work: Record<string, unknown> = {};
  const unmatched: string[] = [];
  const toEntry = (input: string) => {
    const p = findPlayer(data.players, input);
    if (!p) unmatched.push(input);
    return p ? { key: String(p.player_key), name: p.name } : { name: input };
  };
  for (const name of WORK_LISTS) {
    const list = names(a[name]);
    if (list.length) work[name] = list.map(toEntry);
  }
  if (String(a.target ?? "").trim()) work.target = toEntry(String(a.target).trim());
  if (!Object.keys(work).length && !prepared.state) {
    throw new ToolInputError("Give at least one of give, get, mine, theirs or target, or a pasted state.");
  }
  const allViews = ["compare", "targets", "finder"];
  const view = allViews.includes(String(a.view)) ? String(a.view) : inferView({ ...(prepared.state?.work ?? {}), ...work });
  const text = [
    ...header(data, s),
    "",
    "Saved as a DDF state. The person can paste the block below into the site's paste box, or open the link.",
    ...(unmatched.length ? [`Could not match: ${unmatched.join(", ")} (kept by name; the site will try again).`] : []),
  ].join("\n");
  return finish(ok(text, { as_of: data.as_of, setting: data.setting, unmatched }), {
    prepared, deps, settings: s, view, work, block: true,
  });
}
