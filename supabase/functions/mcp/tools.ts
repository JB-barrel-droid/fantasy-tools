// JEG-1012: tool logic for the remote MCP endpoint. Pure functions, no Deno
// APIs, so the same file runs under node in tests/test_mcp_remote.py.
//
// Lookups and trade math run here, so a tool call returns a small answer
// instead of the whole player list.

import { type Deps, finish, prepare } from "./state.ts";
import { type Finder, type FinderRow, findTradesForPair } from "./find-trades.ts";
import { closestNames, type NameMatch, matchName, splitNames } from "./names.ts";
import { type BenchShareReadout, type FitContext, type FitFinder, type FitRow, type FitSides, benchWeightsFromReadout, buildFitContext, fitForTrade } from "./fit.ts";
import {
  type RosterShape,
  type ViabilityConfig,
  type ViabilityRow,
  type TradeOfferInput,
  type ScoredOffer,
  DEFAULT_CONFIG,
  runViabilityChecks,
  scoreAndRankOffers,
  selectPackage,
} from "./viability.ts";
import { askedWeek, type WeekFields, weekProp, withWeek } from "./week.ts";
import {
  type AnalysisDeps,
  type AnalysisResponse,
  COMPARE_SERIES,
  fmtNet,
  inspectionOf,
  pageRows,
  priorFor,
  SERIES_LABELS,
  slimDisagreement,
  slimMover,
} from "./analyses.ts";

export interface PlayerValue {
  player_key: number;
  name: string;
  pos: string;
  value: number;
  tier: string;
}

// JEG-1179: every answer carries the week it was priced on (WeekFields: week, default_week, weeks,
// missing_sources); sources_included lists the sources priced on that week.
export interface ValuesResponse extends WeekFields {
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
  week?: number | null,
) => Promise<ValuesResponse>;

/** Extended player record with per-chart values (from get-values?include=charts). */
export interface ChartPlayerValue extends PlayerValue {
  chart_values: Record<string, number | null>;
  /** Each chart's Indexed value: the market the other team judges by (JEG-1129). */
  chart_indexed?: Record<string, number | null>;
  ddf_value_charts: number | null;
  ddf_value_projections: number | null;
}

export interface ChartValuesResponse extends ValuesResponse {
  players: ChartPlayerValue[];
  /** The engine's bench-share readout, the fit rule's bench weights (JEG-1115). */
  bench_share?: BenchShareReadout;
}

/** Fetches values with chart series included (for find_trades). */
export type FetchValuesWithCharts = (
  scoring: string,
  teams: number,
  superflex: number,
  league?: Record<string, unknown>,
  week?: number | null,
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

// JEG-1029: the series Risers & fallers offers (movers.js SERIES) and the sources Values auditing shows.
const MOVERS_SERIES = ["ddf_value", "ddf_value_charts", "ddf_value_projections", "fantasycalc", "usatoday", "fantasypros", "cbs", "cbsros", "razzball", "espn"];
const AUDIT_SOURCES = ["fantasycalc", "usatoday", "fantasypros", "cbs", "espn", "cbsros", "razzball"];

const settingsProps = {
  scoring: {
    type: "string",
    default: "ppr",
    description: "League scoring: ppr, half_ppr, or standard. Also accepts PPR, 0.5ppr, half, and non-ppr.",
  },
  teams: { type: "integer", enum: TEAMS, default: 12, description: "Number of teams in the league" },
  superflex: {
    type: "boolean",
    default: false,
    description: "Whether the league has a superflex slot. Also accepts yes/no and 1/0.",
  },
  state: {
    type: "string",
    description:
      "Optional: a DDF state pasted from the site (a ```ddf-state block, JSON, or a site link). Supplies the league settings; explicit settings above win.",
  },
  ...weekProp,
};

// JEG-1124: a one-letter name fits too many players to be useful; ask for a fuller name.
const MIN_NAME = 2;

const listProps = {
  give: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: what you give (Compare a trade)" },
  get: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: what you get (Compare a trade)" },
  mine: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: your roster (Find a trade)" },
  theirs: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: their roster (Find a trade)" },
  target: { type: "string", minLength: MIN_NAME, description: "One player name (Trade targets)" },
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
  min_wr_backups: { type: "integer", default: 0, description: "Minimum healthy WR backups beyond starters" },
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
      "Current fantasy football trade values for the user's league settings, from Data Driven Football. DDF Value is the average of the four adjusted trade charts (value above waivers). Returns name, position, value and tier, best first. Values have no fixed maximum.",
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
      "Look up one or more players by name and return their DDF Value and tier. Partial names work. A name that fits more than one player is reported as ambiguous instead of guessed. Typos and missing hyphens are matched when only one player is close.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        names: { type: "string", minLength: MIN_NAME, description: "Comma-separated player names" },
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
        player_name: { type: "string", minLength: MIN_NAME, description: "Player to trade (or trade for)" },
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
      "Compare two sides of a trade by the sum of their DDF Values. Pass comma-separated player names for each side (a comma before Jr, Sr, II, III, IV or V stays with the name). Side A is what team A gives up. This is a DDF Value sum: it is not lineup-aware. Set by_source for the site's Compare a trade breakdown: the net for DDF Value and each published trade chart (rescaled), and which charts disagree with the DDF Value verdict.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        side_a: { type: "string", minLength: MIN_NAME, description: "Comma-separated names team A gives up" },
        side_b: { type: "string", minLength: MIN_NAME, description: "Comma-separated names team B gives up" },
        by_source: { type: "boolean", default: false, description: "One row per series, as the site's Compare a trade shows it (DDF Value and the four published charts)" },
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
      properties: {
        state: { type: "string", description: "The pasted block, JSON or site link (a link's wk= picks the week)" },
        ...weekProp,
      },
      required: ["state"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "make_state",
    description:
      "Save work from this chat as a Data Driven Football site link the person opens to continue there: league settings plus a trade, rosters or a target player, by name. Returns the link (and the same state as a block).",
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
      "Find trade packages between two rosters, scored for viability. Lists trades where you gain DDF Value and at least 3 of 4 trade charts say the other team breaks even or wins. Each trade is scored on 9 viability checks (arbitrage, fairness, lineup improvement, position protection, depth, roster space, QB, guardrails) and labelled High/Med-High/Medium when viable. Each trade also carries the fit label the site's finder shows (Natural / Market supported / Force) with a one-line reason. Set viable_only to see only the trades most likely to be accepted.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        mine: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: your full roster" },
        theirs: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: their full roster" },
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
      "Find the best trades across an entire league. Takes your roster and a list of opponents with their rosters, scores every candidate on 9 viability checks, ranks viable offers first, and selects the best package of trades (no player sent twice, each opponent at most once). Returns a short line per trade (players, DDF edge, lineup change, label, failed check names, and the fit label Natural / Market supported / Force with its reason) and the package with your projected lineup after.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        mine: { type: "string", minLength: MIN_NAME, description: "Comma-separated names: your full roster" },
        opponents: {
          type: "array",
          description: "Opposing teams: [{name, roster}] where roster is comma-separated names",
          items: {
            type: "object",
            properties: {
              name: { type: "string", description: "Team name" },
              roster: { type: "string", minLength: MIN_NAME, description: "Comma-separated player names" },
            },
            required: ["name", "roster"],
          },
          minItems: 1,
          maxItems: 15,
        },
        max_per_side: { type: "integer", minimum: 1, maximum: 4, default: 2, description: "Maximum players each side trades" },
        min_rival_edge: { type: "number", minimum: 0, default: 0, description: "Minimum average chart-value edge the other team needs (0 = any fair trade)" },
        limit: { type: "integer", minimum: 1, maximum: 100, default: 10, description: "Maximum trade candidates to return" },
        ...viabilityProps,
      },
      required: ["mine", "opponents"],
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "risers_fallers",
    description:
      "Who gained and lost value since last week, as the site's Risers & fallers shows it: one series at a time (DDF Value by default), Week N-1 to the week served now, both priced for the user's league. Also lists where the market (DDF Value) and the projections (DDF Value (projections)) disagree: one moved 2.5 points or more while the other moved 1.0 or less.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        series: { type: "string", enum: MOVERS_SERIES, default: "ddf_value", description: "Which series' change to show" },
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter by position" },
        limit: { type: "integer", minimum: 1, maximum: 25, default: 10, description: "Risers and fallers to show, each" },
        disagreements: { type: "boolean", default: true, description: "Also list where the market and the projections disagree" },
      },
    },
    annotations: { readOnlyHint: true, openWorldHint: true },
  },
  {
    name: "audit_values",
    description:
      "Audit the values for the user's league, as the site's Values auditing tab shows them. view health (default): the Health check's verdicts, each check pass or flag with the reason. view source: one source's build-up (published, indexed, adjusted) with its totals and its top players in its own order.",
    inputSchema: {
      type: "object",
      properties: {
        ...settingsProps,
        view: { type: "string", enum: ["health", "source"], default: "health", description: "Health check or one source's build-up" },
        source: { type: "string", enum: AUDIT_SOURCES, default: "fantasycalc", description: "The source, for view source" },
        position: { type: "string", enum: POSITIONS, default: "all", description: "Filter the source view by position" },
        limit: { type: "integer", minimum: 1, maximum: 50, default: 15, description: "Players to show in the source view" },
      },
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
  /** JEG-1029: get-values' analysis blocks and the page modules that read them. */
  analysis?: AnalysisDeps;
}

const SCORING_ALIASES: Record<string, string> = {
  ppr: "ppr",
  fullppr: "ppr",
  full: "ppr",
  "1ppr": "ppr",
  "1.0ppr": "ppr",
  halfppr: "half_ppr",
  half: "half_ppr",
  "0.5ppr": "half_ppr",
  "0.5": "half_ppr",
  "05ppr": "half_ppr",
  point5ppr: "half_ppr",
  standard: "standard",
  std: "standard",
  nonppr: "standard",
  noppr: "standard",
  "0ppr": "standard",
};

function normalizeScoring(value: unknown): string {
  if (value === undefined || value === null || value === "") return "ppr";
  const key = String(value).trim().toLowerCase().replace(/[\s_-]+/g, "");
  const scoring = SCORING_ALIASES[key];
  if (!scoring) throw new ToolInputError(`invalid scoring: ${value}. Must be one of: ${SCORINGS.join(", ")} (also PPR, 0.5ppr, half, standard).`);
  return scoring;
}

const TRUE_WORDS = new Set(["1", "true", "yes", "y", "on"]);
const FALSE_WORDS = new Set(["0", "false", "no", "n", "off"]);

/** Missing uses the default. An unrecognised value is an error, not a silent false. */
function parseBool(value: unknown, name: string, fallback: boolean): boolean {
  if (value === undefined || value === null || value === "") return fallback;
  if (value === true || value === 1) return true;
  if (value === false || value === 0) return false;
  const word = String(value).trim().toLowerCase();
  if (TRUE_WORDS.has(word)) return true;
  if (FALSE_WORDS.has(word)) return false;
  throw new ToolInputError(`${name} must be true or false (got ${JSON.stringify(value)}).`);
}

function parseBounded(value: unknown, name: string, fallback: number, min: number, max: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const n = typeof value === "number" ? value : Number(String(value).trim());
  if (!Number.isInteger(n) || n < min || n > max) {
    throw new ToolInputError(`${name} must be an integer from ${min} to ${max}.`);
  }
  return n;
}

function parseNonNegative(value: unknown, name: string, fallback: number): number {
  if (value === undefined || value === null || value === "") return fallback;
  const n = typeof value === "number" ? value : Number(String(value).trim());
  if (!Number.isFinite(n) || n < 0) throw new ToolInputError(`${name} must be a number >= 0.`);
  return n;
}

function settings(args: Record<string, unknown>) {
  const scoring = normalizeScoring(args.scoring);
  const teams = Number(args.teams ?? 12);
  if (!TEAMS.includes(teams)) {
    throw new ToolInputError(`invalid teams: ${teams}. Must be one of: ${TEAMS.join(", ")}`);
  }
  const superflex = parseBool(args.superflex, "superflex", false) ? 1 : 0;
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

function header(data: ValuesResponse, s: { scoring: string; teams: number; superflex: number; league?: Record<string, unknown> }): string[] {
  const bits = [s.scoring, `${s.teams} teams`];
  if (s.superflex) bits.push("superflex");
  const league = s.league;
  const roster = league?.roster && typeof league.roster === "object" ? league.roster as Record<string, unknown> : null;
  if (roster) {
    const slots = ["QB", "RB", "WR", "TE", "FLEX", "BENCH"].filter((k) => roster[k] !== undefined);
    if (slots.length) bits.push(`roster ${slots.map((k) => `${k}${roster[k]}`).join(" ")}`);
  }
  const shares = league?.shares && typeof league.shares === "object" ? league.shares as Record<string, unknown> : null;
  if (shares) {
    const parts = ["QB", "RB", "WR", "TE"].filter((k) => shares[k] !== undefined)
      .map((k) => `${k} ${Number(shares[k]).toFixed(2)}`);
    if (parts.length) bits.push(`shares ${parts.join(" ")}`);
  }
  return [
    data.attribution,
    `As of: ${data.as_of || "unknown"}`,
    `Settings: ${bits.join(", ")}`,
  ];
}

// Exact or unique partial match, else a single close typo. Ambiguous queries return null
// (the caller reads matchName for the warning). Kept for callers that only need the player.
export function findPlayer(players: PlayerValue[], query: string): PlayerValue | null {
  const hit = matchName(players, query);
  return hit.match === "ambiguous" ? null : hit.player;
}

function round1(n: number): number {
  return Math.round(n * 10) / 10;
}

interface SlimPlayer { name: string; pos: string; value: number | null }

function slimOffer(o: {
  team: string;
  userGives: Array<{ name: string; pos: string; ddfValue: number | null }>;
  userGets: Array<{ name: string; pos: string; ddfValue: number | null }>;
  ddfEdge: number;
  userLineupDelta: number;
  viable: boolean;
  label: string | null;
  temporaryGap: boolean;
  checks: Array<{ name: string; passed: boolean }>;
  fit?: string | null;
  fitReason?: string | null;
  fitSides?: FitSides | null;
}, withTeam: boolean) {
  const side = (rows: Array<{ name: string; pos: string; ddfValue: number | null }>): SlimPlayer[] =>
    rows.map((p) => ({ name: p.name, pos: p.pos, value: p.ddfValue }));
  const failed = o.checks.filter((c) => !c.passed).map((c) => c.name);
  return {
    ...(withTeam ? { team: o.team } : {}),
    userGives: side(o.userGives),
    userGets: side(o.userGets),
    ddfEdge: round1(o.ddfEdge),
    lineup: round1(o.userLineupDelta),
    viable: o.viable,
    label: o.label,
    failed,
    ...(o.temporaryGap ? { temporaryGap: true } : {}),
    // JEG-1115: the fit label the finder shows (Natural / Market supported / Force) and its reason.
    ...(o.fit ? { fit: o.fit, fitReason: o.fitReason ?? null } : {}),
    // JEG-1329: the other team's side of the same tradeFit call (their Trade chart average net and
    // starters change) and roster construction for both teams. Your side's numbers are ddfEdge,
    // lineup and the fit reason; the construction issues are in the fit reason too.
    ...(o.fit && o.fitSides ? {
      theirs: { marketNet: round1(o.fitSides.theirs.net), starters: round1(o.fitSides.theirs.starters),
        constructionOk: o.fitSides.theirs.construction.ok },
      yours: { constructionOk: o.fitSides.yours.construction.ok },
    } : {}),
  };
}

function tradeLine(index: number, o: ReturnType<typeof slimOffer>, team?: string): string {
  const side = (rows: SlimPlayer[]) => rows.map((p) => `${p.name} (${p.pos} ${p.value ?? "?"})`).join(" + ");
  const tag = o.viable ? (o.label ?? "viable") : `not viable: ${o.failed.join(", ") || "checks"}`;
  const vs = team ? ` vs ${team}` : "";
  const edge = o.ddfEdge >= 0 ? `+${o.ddfEdge.toFixed(1)}` : o.ddfEdge.toFixed(1);
  const lineup = o.lineup >= 0 ? `+${o.lineup.toFixed(1)}` : o.lineup.toFixed(1);
  // JEG-1329: their starters change on the Trade chart average (their net is in the fit reason).
  const theirs = o.theirs ? ` | their starters ${o.theirs.starters >= 0 ? "+" : ""}${o.theirs.starters.toFixed(1)}` : "";
  const line = `${index + 1}.${vs} give ${side(o.userGives)} → get ${side(o.userGets)} | edge ${edge} | lineup ${lineup}${theirs} | ${tag}`;
  // JEG-1115: the finder's fit label and one-line reason (fitText opens with the label).
  return o.fit ? `${line}${o.fitReason ? `\n   ${o.fitReason}` : ` | ${o.fit}`}` : line;
}

// JEG-1123: the text lists the top rows only, so a long result is not sent twice;
// structuredContent carries every row once and the site link opens the full list.
const TEXT_ROWS = 5;

function tradeLines<T extends ReturnType<typeof slimOffer>>(rows: T[], team?: (o: T) => string): string[] {
  const lines = rows.slice(0, TEXT_ROWS).map((o, i) => tradeLine(i, o, team?.(o)));
  const more = rows.length - TEXT_ROWS;
  if (more > 0) lines.push(`${more} more in the structured result and on the site (link below).`);
  return lines;
}

// JEG-1115: fit reasons must fit inside the existing JEG-1123 reply budgets. Limits are
// upper bounds (Jeremy, Oct 26); keep a ranked prefix and the entire selected package.
const bytes = (result: ToolResult) => new TextEncoder().encode(JSON.stringify(result)).length;
// JEG-1329 (pick B, 2026-10-29): the site link does not count against the reply budget. It opens the
// full list on the site, and a league link grows with every team it carries, so counting it would cost
// trade rows. Measured as the reply with the link left out of the text and site_url.
const budgetBytes = (result: ToolResult) => {
  const url = result.structuredContent?.site_url;
  if (typeof url !== "string" || !url) return bytes(result);
  return bytes({ ...result, content: result.content.map((c) => ({ ...c, text: c.text.split(url).join("") })),
    structuredContent: { ...result.structuredContent, site_url: "" } });
};
const tradeBudget = (name: string, limit: number) => name === "find_trades"
  ? (limit <= 10 ? 6700 : 17000) : (limit <= 10 ? 8000 : 11500);
const SIZE_ERROR = "This trade reply is too large to show with complete fit reasons. Try fewer opponents or shorter roster/team names.";

function boundedTrades<T>(rows: T[], name: string, limit: number,
  render: (shown: T[], shortened: boolean) => ToolResult): ToolResult {
  // Leave room for #1024's week metadata/text. rpc.ts checks the exact final result after
  // every decorator, so an oversized envelope is an honest error, never a silent overflow.
  const budget = tradeBudget(name, limit) - 512;
  for (let count = rows.length; count >= Math.min(1, rows.length); count--) {
    const result = render(rows.slice(0, count), count < rows.length);
    if (budgetBytes(result) < budget) return result;
  }
  throw new ToolInputError(SIZE_ERROR);
}

/** Final wire guard, after state links and optional week metadata have been attached. */
export function checkTradeReplySize(name: string, result: ToolResult): void {
  if ((name === "find_trades" || name === "find_trades_league") && !result.isError &&
    budgetBytes(result) >= tradeBudget(name, Number(result.structuredContent?.limit) || 10)) {
    throw new ToolInputError(SIZE_ERROR);
  }
}

function foundLine(total: number, shown: number, limit: number, viableOnly: boolean): string {
  const noun = total === 1 ? "trade" : "trades";
  const which = viableOnly ? " viable" : "";
  if (shown === limit || total <= shown) return `Found ${total} ${noun} (showing ${shown}${which}).`;
  return `Found ${total} ${noun} (showing ${shown}${which} of limit ${limit}).`;
}

interface ResolvedNames<T extends PlayerValue> {
  matched: T[];
  unmatched: string[];
  ambiguous: Array<{ input: string; suggestions: string[] }>;
  notes: string[];
}

/** JEG-1124: one trimmed name, rejected when it is too short to pick out one player. */
function checkName(name: string, field: string): string {
  if (name.length < MIN_NAME) {
    throw new ToolInputError(
      `${field}: name too short (${JSON.stringify(name)}). Use a fuller player name, at least ${MIN_NAME} characters.`,
    );
  }
  return name;
}

/** A comma-separated name list, each name checked by checkName. */
function playerNames(raw: unknown, field: string): string[] {
  return splitNames(raw).map((n) => checkName(n, field));
}

function resolveNames<T extends PlayerValue>(players: T[], names: string[]): ResolvedNames<T> {
  const matched: T[] = [];
  const seen = new Set<number>();
  const unmatched: string[] = [];
  const ambiguous: Array<{ input: string; suggestions: string[] }> = [];
  const notes: string[] = [];
  for (const input of names) {
    const hit: NameMatch<T> = matchName(players, input);
    if (hit.match === "ambiguous") {
      ambiguous.push({ input, suggestions: hit.suggestions.map((p) => p.name) });
      notes.push(hit.note);
      continue;
    }
    if (!hit.player) {
      unmatched.push(input);
      notes.push(hit.note || `${input}: NOT FOUND`);
      continue;
    }
    if (seen.has(hit.player.player_key)) {
      notes.push(`${hit.player.name} listed more than once; counted once.`);
      continue;
    }
    seen.add(hit.player.player_key);
    matched.push(hit.player);
    if (hit.note) notes.push(hit.note);
  }
  return { matched, unmatched, ambiguous, notes };
}

/** "2 not found" plus, when any, "1 fits more than one player (left out; ask which)". */
function missed<T extends PlayerValue>(res: ResolvedNames<T>): string {
  const parts = [`${res.unmatched.length} not found`];
  if (res.ambiguous.length) parts.push(`${res.ambiguous.length} fit${res.ambiguous.length === 1 ? "s" : ""} more than one player (left out; ask which)`);
  return parts.join(", ");
}

/** Only set when a roster had an ambiguous name, so the usual reply stays the same size. */
function ambiguousOf<T extends PlayerValue>(res: ResolvedNames<T>): { ambiguous?: Array<{ input: string; suggestions: string[] }> } {
  return res.ambiguous.length ? { ambiguous: res.ambiguous } : {};
}

/**
 * JEG-1124: a name that fits several players, or (Jeremy 2026-10-30, "Letter A.") matches no
 * player, stops a compare so the model asks which one. A not-found name lists its closest names.
 */
function stopOnUnresolved<T extends PlayerValue>(players: T[], ...sides: Array<ResolvedNames<T>>): void {
  const hits = sides.flatMap((side) => side.ambiguous);
  const missing = sides.flatMap((side) => side.unmatched);
  if (!hits.length && !missing.length) return;
  const parts: string[] = [];
  if (hits.length) {
    const each = hits.map((h) => `"${h.input}" could be ${h.suggestions.join(", ")}`);
    parts.push(`More than one player fits: ${each.join("; ")}.`);
  }
  if (missing.length) {
    const each = missing.map((input) => {
      const near = closestNames(players, input, matchName(players, input)).map((p) => p.name);
      return `"${input}" matches no player${near.length ? `; closest: ${near.join(", ")}` : ""}`;
    });
    parts.push(`${each.join(". ")}.`);
  }
  throw new ToolInputError(`${parts.join(" ")} Ask the user which player they meant, then call again with the full name.`);
}

function emptyRoster<T extends PlayerValue>(side: string, res: ResolvedNames<T>): string {
  if (res.notes.length) return `No players matched on ${side}. ${res.notes.join(" ")}`;
  return `No players matched on ${side}. Check the spelling.`;
}

function parseOpponents(raw: unknown): Array<{ name: string; roster: string }> {
  if (typeof raw === "string") {
    throw new ToolInputError("opponents must be an array of {name, roster}, not a string.");
  }
  if (!Array.isArray(raw) || !raw.length) throw new ToolInputError("opponents is required: an array of {name, roster}.");
  if (raw.length > 15) throw new ToolInputError("too many opponents (max 15)");
  return raw.map((opp, i) => {
    if (!opp || typeof opp !== "object" || Array.isArray(opp)) {
      throw new ToolInputError(`opponents[${i}] must be an object with name and roster.`);
    }
    const row = opp as Record<string, unknown>;
    const name = String(row.name ?? "").trim();
    if (!name) throw new ToolInputError(`opponents[${i}].name is required.`);
    if (typeof row.roster !== "string") {
      throw new ToolInputError(`opponents[${i}].roster must be a comma-separated string of names.`);
    }
    playerNames(row.roster, `opponents[${i}].roster`);
    return { name, roster: row.roster };
  });
}

function ok(text: string, structured: Record<string, unknown>): ToolResult {
  return { content: [{ type: "text", text }], structuredContent: structured };
}

// JEG-1179: every tool prices the week get-values picks (the site's default) or the week asked for
// (`week`, or `wk=` in a pasted site link). The fetchers carry it; the result gets the week fields.
export async function runTool(
  name: string,
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  const week = askedWeek(args);
  if (Number.isNaN(week)) {
    throw new ToolInputError(`invalid week: ${args.week}. Give a whole number from 1 to 22, or leave it out for the default week.`);
  }
  let priced: ValuesResponse | null = null;
  const weekValues: FetchValues = async (scoring, teams, superflex, league) =>
    (priced = await fetchValues(scoring, teams, superflex, league, week));
  const charts = finderDeps?.fetchCharts;
  const analysis = finderDeps?.analysis?.fetchAnalysis;
  const weekDeps: FinderDeps | undefined = finderDeps && {
    ...finderDeps,
    fetchCharts: charts
      ? async (scoring, teams, superflex, league) => (priced = await charts(scoring, teams, superflex, league, week))
      : null,
    ...(finderDeps.analysis ? {
      analysis: {
        ...finderDeps.analysis,
        fetchAnalysis: analysis
          ? async (scoring, teams, superflex, league, _week, includes) =>
            (priced = await analysis(scoring, teams, superflex, league, week, includes))
          : null,
      },
    } : {}),
  };
  const result = await runPricedTool(name, args, weekValues, deps, weekDeps);
  return withWeek(result, priced, week);
}

async function runPricedTool(
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
  if (name === "risers_fallers") return await risersFallersHandler(args, deps, finderDeps?.analysis);
  if (name === "audit_values") return await auditValuesHandler(args, deps, finderDeps?.analysis);
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
    const limit = parseBounded(args.limit, "limit", 50, 1, 200);
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const players = data.players.filter((p) => pos === "all" || p.pos === pos).slice(0, limit)
      .map((p) => ({ name: p.name, pos: p.pos, value: p.value, tier: p.tier }));
    const text = [
      ...header(data, s),
      `Sources included: ${data.sources_included.join(", ")}`,
      `${players.length} players, best first.`,
      ...players.map((p) => `${p.name} | ${p.pos} | ${p.value} | ${p.tier}`),
    ].join("\n");
    return finish(
      ok(text, { as_of: data.as_of, setting: data.setting, sources_included: data.sources_included, players }),
      { prepared, deps, settings: s, view: "targets" },
    );
  }

  if (name === "get_player_value") {
    const names = playerNames(args.names, "names");
    if (!names.length) throw new ToolInputError("names is required");
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const results = names.map((input) => {
      const hit = matchName(data.players, input);
      return { input, player: hit.match === "ambiguous" ? null : hit.player, match: hit.match, suggestions: hit.suggestions.map((p) => p.name), note: hit.note };
    });
    const text = [
      ...header(data, s),
      "",
      ...results.map((r) =>
        r.player
          ? `${r.player.name} (${r.player.pos}): value ${r.player.value}, tier ${r.player.tier}${r.note ? ` — ${r.note}` : ""}`
          : r.note || `${r.input}: NOT FOUND`
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
    const pct = parseBounded(args.range_pct, "range_pct", 15, 1, 50);
    const query = String(args.player_name ?? "").trim();
    if (!query) throw new ToolInputError("player_name is required");
    checkName(query, "player_name");
    const data = await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    const hit = matchName(data.players, query);
    if (hit.match === "ambiguous" || !hit.player) {
      return {
        content: [{ type: "text", text: `${data.attribution}\n\n${hit.note || `Player "${query}" not found.`}` }],
        isError: true,
      };
    }
    const player = hit.player;
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
    const namesA = playerNames(args.side_a, "side_a");
    const namesB = playerNames(args.side_b, "side_b");
    if (!namesA.length || !namesB.length) {
      throw new ToolInputError("side_a and side_b each need at least one name");
    }
    const bySource = parseBool(args.by_source, "by_source", false);
    const data: AnalysisResponse = bySource
      ? await analysisData(finderDeps?.analysis, "trade", s, ["series"])
      : await fetchValues(s.scoring, s.teams, s.superflex, s.league);
    let a = resolveNames(data.players, namesA);
    let b = resolveNames(data.players, namesB);
    stopOnUnresolved(data.players, a, b);
    // The same player on both sides stays on team A, matching the site.
    const giveKeys = new Set(a.matched.map((p) => p.player_key));
    const shared = b.matched.filter((p) => giveKeys.has(p.player_key));
    if (shared.length) {
      b = {
        ...b,
        matched: b.matched.filter((p) => !giveKeys.has(p.player_key)),
        notes: [...b.notes, `On both sides, kept on team A only: ${shared.map((p) => p.name).join(", ")}.`],
      };
    }
    if (!a.matched.length || !b.matched.length) {
      const why = [...a.notes, ...b.notes].filter(Boolean).join(" ");
      throw new ToolInputError(why || "side_a and side_b each need at least one matched player");
    }
    // Every name matched (stopOnUnresolved), so the link carries keys only (JEG-1124).
    const work = {
      give: a.matched.map((p) => entry(p.name, p)),
      get: b.matched.map((p) => entry(p.name, p)),
    };
    if (bySource) {
      return finish(compareBySource(data, s, a, b, finderDeps!.analysis!.modules!.trade), {
        prepared, deps, settings: s, view: "compare", work,
      });
    }
    const sum = (rows: PlayerValue[]) => round1(rows.reduce((t, p) => t + p.value, 0));
    const sumA = sum(a.matched);
    const sumB = sum(b.matched);
    const diff = round1(sumA - sumB);
    const verdict = Math.abs(diff) < 2
      ? "roughly even"
      : diff > 0
      ? `team B comes out ahead by ${diff.toFixed(1)} (team A gives up more value)`
      : `team A comes out ahead by ${(-diff).toFixed(1)} (team B gives up more value)`;
    const fmt = (rows: PlayerValue[]) => rows.map((p) => `  ${p.name} (${p.pos}): ${p.value}`).join("\n");
    const notes = [...new Set([...a.notes, ...b.notes])];
    const text = [
      ...header(data, s),
      "",
      `Team A gives up (total ${sumA.toFixed(1)}):`,
      fmt(a.matched),
      `Team B gives up (total ${sumB.toFixed(1)}):`,
      fmt(b.matched),
      "",
      `Verdict (DDF Value sum, not lineup-aware; a gap under 2 points counts as roughly even, a rule of thumb): ${verdict}.`,
      "The site's Compare a trade shows the per-chart breakdown for this trade; open the link below.",
      ...(notes.length ? [notes.join("\n")] : []),
    ].join("\n");
    // Every name matched (stopOnUnresolved), so not_found stays empty; kept for the reply's shape.
    const pack = (rows: PlayerValue[]) => ({
      total: sum(rows),
      players: rows.map((p) => ({ name: p.name, pos: p.pos, value: p.value })),
      not_found: [] as string[],
    });
    // The site's Compare a trade reads "give" as what the person gives up: team A is the person.
    return finish(
      ok(text, {
        as_of: data.as_of,
        setting: data.setting,
        side_a: pack(a.matched),
        side_b: pack(b.matched),
        difference: diff,
        verdict,
        method: "sum_of_ddf_values",
        not_found: [],
      }),
      { prepared, deps, settings: s, view: "compare", work },
    );
  }

  throw new ToolInputError(`unknown tool: ${name}`);
}

// ---------- JEG-1029: risers_fallers, compare_trade by_source, audit_values ----------
// get-values prices; the page's own modules (movers.js, trade.js, audit-pie.js, audit-source.js) read
// what it returns exactly as the page reads its engine. See analyses.ts.

type Settings = ReturnType<typeof settings>;
const MODULE_FOR = { risers: "movers", trade: "trade", health: "auditPie", source: "auditSource" } as const;

async function analysisData(
  analysis: AnalysisDeps | undefined, use: keyof typeof MODULE_FOR, s: Settings, includes: string[],
): Promise<AnalysisResponse> {
  const module = analysis?.modules?.[MODULE_FOR[use]];
  if (!analysis?.fetchAnalysis || !module) {
    throw new ToolUnavailableError("This analysis is unavailable right now (the site's module could not be loaded). Open the site link instead.");
  }
  return await analysis.fetchAnalysis(s.scoring, s.teams, s.superflex, s.league, null, includes);
}

const seriesName = (key: string) => SERIES_LABELS[key] ?? key;

function compareBySource(
  data: AnalysisResponse, s: Settings, a: ResolvedNames<PlayerValue>, b: ResolvedNames<PlayerValue>,
  // deno-lint-ignore no-explicit-any
  trade: any,
): ToolResult {
  const rowsByKey = new Map(pageRows(data).map((row) => [row.player_key, row]));
  // A player get-values has no row for comes in with no values, so every series reads it as missing.
  const rowsOf = (list: PlayerValue[]) => list.map((p) => rowsByKey.get(p.player_key) ?? { player_key: p.player_key, name: p.name, pos: p.pos, values: {} });
  const giveRows = rowsOf(a.matched);
  const getRows = rowsOf(b.matched);
  const { rows } = trade.compareTrade(giveRows, getRows, COMPARE_SERIES);
  const verdict = trade.tradeVerdict(rows, "ddf_value");
  // deno-lint-ignore no-explicit-any
  const slim = rows.map((r: any) => ({
    series: r.key, label: seriesName(r.key),
    give: r.give === null ? null : round1(r.give), get: r.receive === null ? null : round1(r.receive),
    net: r.net === null ? null : round1(r.net),
    // deno-lint-ignore no-explicit-any
    missing: r.missing.map((m: any) => ({ name: m.row.name, side: m.side === "give" ? "a" : "b" })),
  }));
  const names = (keys: string[]) => keys.map(seriesName).join(", ");
  const verdictText = verdict.kind === "win"
    ? `team A comes out ahead on DDF Value by ${fmtNet(verdict.net)}`
    : verdict.kind === "lose"
    ? `team A comes out behind on DDF Value by ${fmtNet(verdict.net)}`
    : verdict.kind === "even"
    ? "even on DDF Value"
    : "DDF Value cannot be read: a player has no DDF Value";
  const against = verdict.againstKeys?.length ? `Pointing the other way: ${names(verdict.againstKeys)}.` : null;
  const agree = verdict.kind && verdict.kind !== "incomplete" && verdict.others
    ? `${verdict.agreeKeys.length} of ${verdict.others} complete chart rows agree.` : null;
  const incomplete = verdict.incompleteKeys?.length ? `Not read (a player is missing there): ${names(verdict.incompleteKeys)}.` : null;
  const notFound = [...a.unmatched, ...b.unmatched];
  const notes = [...new Set([...a.notes, ...b.notes])];
  const text = [
    ...header(data, s),
    "",
    `Team A gives up: ${a.matched.map((p) => p.name).join(", ")}`,
    `Team B gives up: ${b.matched.map((p) => p.name).join(", ")}`,
    "Series | Team A gives | Team A gets | Net for team A",
    // deno-lint-ignore no-explicit-any
    ...slim.map((r: any) => r.net === null
      ? `${r.label} | — | — | — (no value: ${r.missing.map((m: { name: string }) => m.name).join(", ")})`
      : `${r.label} | ${r.give.toFixed(1)} | ${r.get.toFixed(1)} | ${fmtNet(r.net)}`),
    "",
    `Verdict (DDF Value, one series decides; not lineup-aware): ${verdictText}.`,
    ...[agree, against, incomplete].filter(Boolean) as string[],
    ...(notes.length ? [notes.join("\n")] : []),
    ...(notFound.length ? [`Warning: not found, left out: ${notFound.join(", ")}`] : []),
  ].join("\n");
  return ok(text, {
    as_of: data.as_of, setting: data.setting, method: "compare_trade_by_series", rows: slim,
    verdict: { kind: verdict.kind, series: "ddf_value", net: verdict.net === null || verdict.net === undefined ? null : round1(verdict.net),
      agree: verdict.agreeKeys ?? [], against: verdict.againstKeys ?? [], incomplete: verdict.incompleteKeys ?? [] },
    not_found: notFound,
  });
}

async function risersFallersHandler(args: Record<string, unknown>, deps?: Deps, analysis?: AnalysisDeps): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  args = prepared.args;
  const s = settings(args);
  const series = String(args.series ?? "ddf_value");
  if (!MOVERS_SERIES.includes(series)) {
    throw new ToolInputError(`invalid series: ${series}. Must be one of: ${MOVERS_SERIES.join(", ")}`);
  }
  const pos = position(args);
  const limit = parseBounded(args.limit, "limit", 10, 1, 25);
  const withDisagreements = parseBool(args.disagreements, "disagreements", true);
  const data = await analysisData(analysis, "risers", s, ["series", "prior"]);
  const M = analysis!.modules!.movers;
  const rows = pageRows(data).filter((r) => pos === "all" || r.pos === pos);
  const v = M.buildMovers(rows, series, priorFor(data, series));
  const label = seriesName(series);
  const risers = v.risers.slice(0, limit).map(slimMover);
  const fallers = v.fallers.slice(0, limit).map(slimMover);
  const line = (m: ReturnType<typeof slimMover>) => `${m.name} (${m.pos}): ${m.before.toFixed(1)} → ${m.now.toFixed(1)} (${fmtNet(m.delta)})`;
  const text: string[] = [...header(data, s), ""];
  if (v.available) {
    text.push(`${label}: Week ${v.priorWeek} → Week ${v.currentWeek}, both priced for this league.`);
    text.push(`Risers (${v.risers.length}):`, ...(risers.length ? risers.map(line) : ["  none"]));
    text.push(`Fallers (${v.fallers.length}):`, ...(fallers.length ? fallers.map(line) : ["  none"]));
    const counts = [`${v.compared} compared`];
    if (v.unchanged) counts.push(`${v.unchanged} unchanged (0.0)`);
    if (v.noPrior) counts.push(`${v.noPrior} not priced in Week ${v.priorWeek}, so no change`);
    if (v.noCurrent) counts.push(`${v.noCurrent} without a Week ${v.currentWeek} value`);
    text.push(`Players: ${counts.join(", ")}. Missing history is no change, never a zero change.`);
  } else {
    text.push(`No change to show for ${label}: ${v.reason}.`);
  }
  // deno-lint-ignore no-explicit-any
  let disagreements: any = null;
  if (withDisagreements) {
    const d = M.buildDisagreements(rows, priorFor(data, "ddf_value_charts"), priorFor(data, "ddf_value_projections"));
    disagreements = d.available
      ? { available: true, compared: d.compared, market: d.market.slice(0, limit).map(slimDisagreement),
        projections: d.projections.slice(0, limit).map(slimDisagreement), market_total: d.market.length, projections_total: d.projections.length }
      : { available: false, reason: d.reason };
    text.push("");
    if (d.available) {
      const dl = (x: ReturnType<typeof slimDisagreement>) =>
        `${x.name} (${x.pos}): DDF Value ${fmtNet(x.market_delta)}, projections ${fmtNet(x.projections_delta)}. ${x.read}`;
      text.push(`Market vs projections, Week ${d.priorWeek} → Week ${d.currentWeek} (one moved ${M.MOVE}+ and the other ${M.QUIET.toFixed(1)} or less; ${d.compared} compared):`);
      text.push(`Market moved (${d.market.length}):`, ...(disagreements.market.length ? disagreements.market.map(dl) : ["  none"]));
      text.push(`Projections moved (${d.projections.length}):`, ...(disagreements.projections.length ? disagreements.projections.map(dl) : ["  none"]));
    } else {
      text.push(`Market vs projections: no comparison yet: ${d.reason}.`);
    }
  }
  return finish(ok(text.join("\n"), {
    as_of: data.as_of, setting: data.setting, series, position: pos, available: v.available,
    reason: v.available ? null : v.reason, current_week: v.currentWeek ?? null, prior_week: v.priorWeek ?? null,
    risers, fallers, counts: { compared: v.compared, unchanged: v.unchanged, no_prior: v.noPrior, no_current: v.noCurrent,
      risers: v.risers.length, fallers: v.fallers.length },
    disagreements,
  }), { prepared, deps, settings: s, view: "risers" });
}

async function auditValuesHandler(args: Record<string, unknown>, deps?: Deps, analysis?: AnalysisDeps): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  args = prepared.args;
  const s = settings(args);
  const viewName = String(args.view ?? "health");
  if (viewName !== "health" && viewName !== "source") throw new ToolInputError(`invalid view: ${viewName}. Must be health or source`);
  const data = await analysisData(analysis, viewName, s, ["audit"]);
  const inspection = inspectionOf(data);
  const text: string[] = [...header(data, s), ""];
  if (viewName === "health") {
    const P = analysis!.modules!.auditPie;
    const model = P.extract(inspection);
    if (!model) {
      text.push("Health check: no pipeline data available.");
      return finish(ok(text.join("\n"), { as_of: data.as_of, setting: data.setting, view: "health", available: false, checks: [] }),
        { prepared, deps, settings: s, view: "audit" });
    }
    P.computeFlags(model);
    const checks = P.computeChecks(model);
    // deno-lint-ignore no-explicit-any
    const slim = checks.map((c: any) => ({ id: c.id, label: c.name, status: c.status, detail: c.reason ?? null, sources: c.sources ?? [] }));
    // deno-lint-ignore no-explicit-any
    const flagged = slim.filter((c: any) => c.status === "flag");
    text.push(`Health check: ${flagged.length ? `${flagged.length} of ${slim.length} checks flagged` : "nothing flagged"}. Value pie ${round1(model.pie)} points, ${model.rows.length} sources.`);
    // deno-lint-ignore no-explicit-any
    text.push(...slim.map((c: any) => `${c.status.toUpperCase()} | ${c.label}${c.detail ? ` | ${c.detail}` : ""}`));
    return finish(ok(text.join("\n"), {
      as_of: data.as_of, setting: data.setting, view: "health", available: true, pie: round1(model.pie), sources: model.rows.length, checks: slim,
    }), { prepared, deps, settings: s, view: "audit" });
  }
  const source = String(args.source ?? "fantasycalc");
  if (!AUDIT_SOURCES.includes(source)) throw new ToolInputError(`invalid source: ${source}. Must be one of: ${AUDIT_SOURCES.join(", ")}`);
  const pos = position(args);
  const limit = parseBounded(args.limit, "limit", 15, 1, 50);
  const m = analysis!.modules!.auditSource.build(inspection, source, pos === "all" ? "ALL" : pos);
  const val = (v: number | null) => v === null ? "—" : v.toFixed(1);
  // A stage with no points has no total: null, never 0 (the page draws nothing for it).
  const total = (stage: string) => m.stages[stage].exists ? round1(m.totals[stage]) : null;
  const totals = { published: total("published"), indexed: total("indexed"), adjusted: total("adjusted") };
  if (!m.hasData) {
    // The page's line for a source with no values (audit-source.js render), and nothing else.
    text.push(`${m.label} has no values at these league settings${m.status ? ` (${m.status})` : ""}.`);
    return finish(ok(text.join("\n"), {
      as_of: data.as_of, setting: data.setting, view: "source", source, position: pos, available: false, status: m.status || null,
      shown: 0, estimated: 0, totals, rows: [],
    }), { prepared, deps, settings: s, view: "audit" });
  }
  // deno-lint-ignore no-explicit-any
  const rows = m.rows.slice(0, limit).map((r: any) => ({
    rank: r.rank, player_key: Number(r.key), name: r.name, pos: r.pos, role: r.role, estimated: r.estimated,
    published: r.published === null ? null : round1(r.published), indexed: r.indexed === null ? null : round1(r.indexed),
    adjusted: r.adjusted === null ? null : round1(r.adjusted),
  }));
  text.push(`${m.label} build-up (${m.family}${m.position === "ALL" ? "" : `, ${m.position}`}): ${m.shown} players, ${m.estimatedCount} filled in.` +
    (m.status ? ` Status: ${m.status}.` : ""));
  text.push(`Totals: published ${val(totals.published)} (${m.stages.published.unit}), indexed ${m.stages.indexed.exists ? val(totals.indexed) : "— (" + (m.stages.indexed.reason || "no indexed values") + ")"}, adjusted ${val(totals.adjusted)}.`);
  text.push("Rank | Player | Pos | Role | Published | Indexed | Adjusted");
  // deno-lint-ignore no-explicit-any
  text.push(...rows.map((r: any) => `${r.rank} | ${r.name}${r.estimated ? " (filled in)" : ""} | ${r.pos} | ${r.role} | ${val(r.published)} | ${val(r.indexed)} | ${val(r.adjusted)}`));
  return finish(ok(text.join("\n"), {
    as_of: data.as_of, setting: data.setting, view: "source", source, position: pos, available: m.hasData, status: m.status || null,
    shown: m.shown, estimated: m.estimatedCount,
    totals,
    rows,
  }), { prepared, deps, settings: s, view: "audit" });
}

// ---------- find_trades tool ----------

/**
 * Convert a ChartPlayerValue into the FinderRow format finder.js expects. The chart keys carry each
 * chart's Indexed value, as the site's rows do in the Indexed view, so the finder's chart checks and
 * the viability market (the mean of the chart keys) read the trade charts' Indexed values. The
 * Adjusted values (chart_values) average to DDF Value itself, so using them would judge the other
 * team on DDF Value and no trade could ever pass (JEG-1129).
 */
export function toFinderRow(p: ChartPlayerValue): FinderRow {
  const values: Record<string, number | null> = {
    ddf_value: p.value,
    ddf_value_charts: p.ddf_value_charts,
    ddf_value_projections: p.ddf_value_projections,
  };
  for (const [k, v] of Object.entries(p.chart_indexed ?? {})) values[k] = v;
  return { player_key: p.player_key, name: p.name, pos: p.pos, values, ddfTier: p.tier };
}

/** The chart players, or unavailable when get-values does not send Indexed chart values yet. */
export function chartPlayersOf(data: { players: ChartPlayerValue[] }): ChartPlayerValue[] {
  const players = data.players ?? [];
  if (players.length && !players.some((p) => p.chart_indexed)) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }
  return players;
}

async function findTradesHandler(
  args: Record<string, unknown>,
  fetchValues: FetchValues,
  deps?: Deps,
  finderDeps?: FinderDeps,
): Promise<ToolResult> {
  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);

  const mineNames = playerNames(a.mine, "mine");
  const theirNames = playerNames(a.theirs, "theirs");
  if (!mineNames.length) throw new ToolInputError("mine is required: comma-separated roster names");
  if (!theirNames.length) throw new ToolInputError("theirs is required: comma-separated roster names");
  if (!finderDeps?.finder) {
    throw new ToolUnavailableError("The trade finder is unavailable right now. Try again shortly.");
  }
  if (!finderDeps?.fetchCharts) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }

  const data = await finderDeps.fetchCharts(s.scoring, s.teams, s.superflex, s.league);
  const chartPlayers = chartPlayersOf(data);

  const mineRes = resolveNames(chartPlayers, mineNames);
  const theirRes = resolveNames(chartPlayers, theirNames);
  if (!mineRes.matched.length) throw new ToolInputError(emptyRoster("your roster", mineRes));
  // A player on both rosters stays on yours, so the search cannot trade him for himself.
  const shared = theirRes.matched.filter((p) => mineRes.matched.some((m) => m.player_key === p.player_key));
  const theirMatched = theirRes.matched.filter((p) => !shared.some((p2) => p2.player_key === p.player_key));
  if (!theirMatched.length) {
    throw new ToolInputError(shared.length
      ? `No players left on their roster. Every matched player is also on yours (${shared.map((p) => p.name).join(", ")}), so there is no one to trade for.`
      : emptyRoster("their roster", theirRes));
  }

  const mineRows = mineRes.matched.map(toFinderRow);
  const theirRows = theirMatched.map(toFinderRow);

  const maxPerSide = parseBounded(a.max_per_side, "max_per_side", 2, 1, 4);
  const minRivalEdge = parseNonNegative(a.min_rival_edge, "min_rival_edge", 0);
  const limit = parseBounded(a.limit, "limit", 10, 1, 50);
  // Pull a pool bigger than `limit` so deduping packages that receive the same players can still fill it.
  const pool = Math.min(500, Math.max(limit * 8, limit + 80));

  const result = findTradesForPair(finderDeps.finder, mineRows, theirRows, {
    maxSize: maxPerSide,
    minRivalEdge,
    limit: pool,
  });

  // --- Viability scoring ---
  const shape = rosterShape(a, s.superflex);
  const vConfig = viabilityConfig(a);
  const viableOnly = parseBool(a.viable_only, "viable_only", false);

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
  // JEG-1115: the fit label the finder shows, judged only for the trades returned.
  const finder = finderDeps.finder;
  const fitCtx = fitContextFor(finder, data, shape);
  const trades = scored.map((o) => slimOffer(withFit(o, finder, fitCtx, mineRows, theirRows, rowByKey), false));

  const entry = (input: string, p: PlayerValue | null) =>
    p ? { key: String(p.player_key), name: p.name } : { name: input };

  const nameNotes = [...mineRes.notes, ...theirRes.notes];
  if (shared.length) nameNotes.push(`On both rosters, kept on yours only: ${shared.map((p) => p.name).join(", ")}.`);

  return boundedTrades(trades, "find_trades", limit, (trades, shortened) => {
    const lines: string[] = [
      ...header(data, s),
      "",
      foundLine(result.total, trades.length, limit, viableOnly),
      `Your roster: ${mineRes.matched.length} matched, ${missed(mineRes)}; searched ${result.mine.searched} of ${result.mine.of} priced.`,
      `Their roster: ${theirMatched.length} matched, ${missed(theirRes)}; searched ${result.theirs.searched} of ${result.theirs.of} priced.`,
    ];
    if (shortened) lines.push("Fewer candidates shown to keep this reply compact; every returned trade keeps its full fit reason.");
    if (nameNotes.length) lines.push(...nameNotes);
    lines.push("");
    lines.push(...tradeLines(trades));
    if (!trades.length) lines.push(viableOnly
      ? "No viable trades found. Try without viable_only to see all candidates."
      : "No trades found where you gain DDF Value and the charts say the rival breaks even.");

    const structured = {
      as_of: data.as_of,
      setting: data.setting,
      trades,
      total: result.total,
      shown: trades.length,
      limit,
      viableCount: trades.filter((o) => o.viable).length,
      mine: { ...result.mine, unmatched: mineRes.unmatched, ...ambiguousOf(mineRes) },
      theirs: { ...result.theirs, unmatched: theirRes.unmatched, ...ambiguousOf(theirRes) },
    };

    const work = {
      mine: mineNames.map((n) => entry(n, findPlayer(data.players, n))),
      theirs: theirNames.map((n) => entry(n, findPlayer(data.players, n))),
    };

    return finish(ok(lines.join("\n"), structured), {
      prepared, deps, settings: s, view: "finder", work,
    });
  });
}

/**
 * JEG-1115: the fit context for a chart response. The compared charts are the ones get-values
 * priced (a Trade chart average needs MIN_CHARTS of them, the page's marketKeys() bar); the
 * bench weights are the engine's own readout, published by get-values as bench_share
 * (Jeremy's pick B, 2026-10-26). With no readout the fit is left unjudged rather than
 * approximated. Expected depth is not published, so it stays null: that only drops the depth
 * sentence from the reason and never moves the label.
 */
function fitContextFor(finder: Finder, data: ChartValuesResponse, shape: RosterShape): FitContext | null {
  const weights = benchWeightsFromReadout(data.bench_share);
  if (!weights) return null;
  const f = finder as unknown as FitFinder;
  const chartKeys = (f.CHART_KEYS || []).filter((k) => data.sources_included.includes(k));
  return buildFitContext(f, { shape, chartKeys, weights, expected: null, z: f.FIT_Z });
}

/** JEG-1115: one scored offer with the finder's fit label and reason (null when not judged). */
function withFit<T extends ScoredOffer>(
  o: T,
  finder: Finder,
  ctx: FitContext | null,
  mineRows: FinderRow[],
  theirRows: FinderRow[],
  rowByKey: Map<number, FinderRow>,
): T & { fit: string | null; fitReason: string | null; fitSides: FitSides | null } {
  if (!ctx) return { ...o, fit: null, fitReason: null, fitSides: null };
  const rows = (side: Array<{ player_key: number }>) =>
    side.map((p) => rowByKey.get(p.player_key)).filter((r): r is FinderRow => !!r) as unknown as FitRow[];
  const give = rows(o.userGives);
  const receive = rows(o.userGets);
  if (give.length !== o.userGives.length || receive.length !== o.userGets.length) return { ...o, fit: null, fitReason: null, fitSides: null };
  const fit = fitForTrade(finder as unknown as FitFinder, mineRows as unknown as FitRow[], theirRows as unknown as FitRow[],
    give, receive, ctx);
  return { ...o, fit: fit.fit, fitReason: fit.fit_reason, fitSides: fit.sides ?? null };
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
  const prepared = prepare(args, deps);
  const a = prepared.args;
  const s = settings(a);

  const mineNames = playerNames(a.mine, "mine");
  if (!mineNames.length) throw new ToolInputError("mine is required: comma-separated roster names");

  const opponents = parseOpponents(a.opponents);
  if (!finderDeps?.finder) {
    throw new ToolUnavailableError("The trade finder is unavailable right now. Try again shortly.");
  }
  if (!finderDeps?.fetchCharts) {
    throw new ToolUnavailableError("Chart values are unavailable right now. Try again shortly.");
  }

  const data = await finderDeps.fetchCharts(s.scoring, s.teams, s.superflex, s.league);
  const chartPlayers = chartPlayersOf(data);

  const mineRes = resolveNames(chartPlayers, mineNames);
  if (!mineRes.matched.length) throw new ToolInputError(emptyRoster("your roster", mineRes));
  const mineRows = mineRes.matched.map(toFinderRow);
  const mineKeys = new Set(mineRes.matched.map((p) => p.player_key));

  const shape = rosterShape(a, s.superflex);
  const vConfig = viabilityConfig(a);
  const viableOnly = parseBool(a.viable_only, "viable_only", false);
  const maxPerSide = parseBounded(a.max_per_side, "max_per_side", 2, 1, 4);
  const minRivalEdge = parseNonNegative(a.min_rival_edge, "min_rival_edge", 0);
  const limit = parseBounded(a.limit, "limit", 10, 1, 100);

  const allOffers: TradeOfferInput[] = [];
  const opponentsById = new Map<string, { name: string; index: number; rows: FinderRow[] }>();
  const allRowsByKey = new Map<number, FinderRow>();
  const perOpponent: Array<{
    name: string;
    opponent_index: number;
    tradesFound: number;
    unmatchedNames: string[];
    ambiguous?: Array<{ input: string; suggestions: string[] }>;
  }> = [];
  const nameNotes = [...mineRes.notes];
  // JEG-1329: every opponent's matched roster, in input order, for the site link (even teams with no trade).
  const leagueTeams: Array<{ name: string; keys: string[] }> = [];

  // Run each opponent pair sequentially (edge function memory).
  for (const [index, opp] of opponents.entries()) {
    const opponentId = String(index);
    const oppNames = splitNames(opp.roster);
    if (!oppNames.length) {
      leagueTeams.push({ name: opp.name, keys: [] });
      perOpponent.push({ name: opp.name, opponent_index: index, tradesFound: 0, unmatchedNames: [] });
      continue;
    }
    const oppRes = resolveNames(chartPlayers, oppNames);
    leagueTeams.push({ name: opp.name, keys: oppRes.matched.filter((p) => !mineKeys.has(p.player_key)).map((p) => String(p.player_key)) });
    nameNotes.push(...oppRes.notes.map((note) => `${opp.name}: ${note}`));
    const theirMatched = oppRes.matched.filter((p) => !mineKeys.has(p.player_key));
    if (!theirMatched.length) {
      perOpponent.push({ name: opp.name, opponent_index: index, tradesFound: 0, unmatchedNames: oppRes.unmatched, ...ambiguousOf(oppRes) });
      continue;
    }

    const theirRows = theirMatched.map(toFinderRow);
    const rowByKey = new Map<number, FinderRow>();
    for (const r of mineRows) rowByKey.set(r.player_key, r);
    for (const r of theirRows) rowByKey.set(r.player_key, r);
    opponentsById.set(opponentId, { name: opp.name, index, rows: theirRows });
    for (const [k, r] of rowByKey) allRowsByKey.set(k, r);

    const pairResult = findTradesForPair(finderDeps.finder, mineRows, theirRows, {
      maxSize: maxPerSide,
      minRivalEdge,
      // Never search a smaller pool than the previous per-opponent cap (50). A
      // higher limit asks for more so the shown list can still fill after dedupe.
      limit: Math.min(200, Math.max(50, limit)),
    });

    const pairOffers: TradeOfferInput[] = pairResult.trades.map((t) => ({
      team: opponentId,
      userGives: t.give.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
      userGets: t.receive.map((p) => rowByKey.get(p.player_key) ?? toViabilityRow(p)),
      userRoster: mineRows,
      theirRoster: theirRows,
    }));

    allOffers.push(...pairOffers);
    perOpponent.push({
      name: opp.name,
      opponent_index: index,
      tradesFound: pairResult.trades.length,
      unmatchedNames: oppRes.unmatched,
      ...ambiguousOf(oppRes),
    });
  }

  // Score, rank, and optionally filter.
  let scored = scoreAndRankOffers(allOffers, shape, vConfig);
  if (viableOnly) scored = scored.filter((o) => o.viable);

  // Package: best viable combination.
  const pkg = selectPackage(scored, mineRows, shape, vConfig.ddfKey);

  // JEG-1115: the fit label the finder shows, judged only for the trades returned.
  const finder = finderDeps.finder;
  const fitCtx = fitContextFor(finder, data, shape);
  const fitted = (o: ScoredOffer) => {
    const opponent = opponentsById.get(o.team)!;
    return { ...slimOffer(withFit({ ...o, team: opponent.name }, finder, fitCtx,
      mineRows, opponent.rows, allRowsByKey), true), opponent_index: opponent.index };
  };
  const shownTrades = scored.slice(0, limit).map(fitted);
  const viableCount = scored.filter((o) => o.viable).length;
  const packageOffers = pkg.offers.map(fitted);

  return boundedTrades(shownTrades, "find_trades_league", limit, (shownTrades, shortened) => {
    const lines: string[] = [
      ...header(data, s),
      "",
      `League scan: ${opponents.length} opponent${opponents.length === 1 ? "" : "s"}, ${scored.length} candidate${scored.length === 1 ? "" : "s"} (${viableCount} viable), showing ${shownTrades.length}${shownTrades.length < limit && scored.length > shownTrades.length ? ` of limit ${limit}` : ""}.`,
      `Your roster: ${mineRes.matched.length} matched, ${missed(mineRes)}.`,
    ];
    if (shortened) lines.push("Fewer candidates shown to keep this reply compact; the selected package and full fit reasons are preserved.");
    if (nameNotes.length) lines.push(...nameNotes);
    lines.push("");

    if (packageOffers.length > 0) {
      lines.push(`Package: ${packageOffers.length} trade${packageOffers.length === 1 ? "" : "s"}, total edge +${pkg.totalDdfEdge.toFixed(1)}.`);
      lines.push(...tradeLines(packageOffers, (o) => o.team as string));
      lines.push("");
    }

    lines.push(shownTrades.length ? "Candidates:" : "");
    lines.push(...tradeLines(shownTrades, (o) => o.team as string));
    if (!shownTrades.length) lines.push(viableOnly
      ? "No viable trades found across the league."
      : "No trades found where you gain DDF Value and the charts say the rival breaks even.");

    const structured = {
      as_of: data.as_of,
      setting: data.setting,
      package: {
        offers: packageOffers,
        totalDdfEdge: round1(pkg.totalDdfEdge),
        lineup: pkg.userLineupAfter.map((p) => ({ name: p.name, pos: p.pos, value: p.ddfValue })),
      },
      trades: shownTrades,
      total: scored.length,
      shown: shownTrades.length,
      limit,
      viableCount,
      perOpponent,
      mine: { matched: mineRes.matched.length, unmatched: mineRes.unmatched, ...ambiguousOf(mineRes) },
    };

    const entry = (input: string, p: PlayerValue | null) =>
      p ? { key: String(p.player_key), name: p.name } : { name: input };
    const work = {
      mine: mineNames.map((n: string) => entry(n, findPlayer(data.players, n))),
    };
    // JEG-1329: the site link opens the league finder with every team, yours first, not only yours.
    const teams = [{ name: "My team", keys: mineRes.matched.map((p) => String(p.player_key)) }]
      .concat(leagueTeams);

    return finish(ok(lines.join("\n"), structured), {
      prepared, deps, settings: s, view: "finder", work, teams,
    });
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
    "Superflex adds a slot that takes a QB, which sharply raises QB values and shifts replacement levels. Charts that publish their own superflex values use them, in a superflex league and in a league that starts 2 QBs (a pasted DDF state or site link whose roster has 2 QB slots). The 2-QB league keeps its own starter and waiver counts; only those charts' values change.",
  tiers:
    "Tier is where a player sits in the league: starter (fills a starting lineup slot), bench (worth rostering as depth) or waiver (replacement level, freely available). It is not a quality band, so two players in the same tier can have very different values; compare values, not tiers.",
  how_to_trade:
    "1) Use compare_trade on both sides. 2) As a rough guide, a gap under about 2 points is roughly even and 5 or more is meaningful; this is a rule of thumb, not a measured threshold. 3) Use trade_targets to find similar-value partners. 4) Your own roster needs can outweigh the DDF Value sum. Values update weekly.",
};

function explain(topic: string): ToolResult {
  const text = EXPLANATIONS[topic];
  if (!text) throw new ToolInputError(`unknown topic: ${topic}. Must be one of: ${EXPLAIN_TOPICS.join(", ")}`);
  return ok(`Data Driven Football\n\n${text}`, { topic, text });
}

// ---------- state tools (JEG-1027) ----------

type Entry = { key?: string; name?: string };
const WORK_LISTS = ["give", "get", "mine", "theirs"];

function resolveEntry(players: PlayerValue[], e: Entry): { input: string; player: PlayerValue | null; note: string } {
  const byKey = e.key !== undefined ? players.find((p) => String(p.player_key) === e.key) ?? null : null;
  if (byKey) return { input: e.name ?? e.key ?? "", player: byKey, note: "" };
  if (!e.name) return { input: e.key ?? "", player: null, note: `${e.key ?? ""}: NOT FOUND` };
  const hit = matchName(players, e.name);
  return { input: e.name, player: hit.match === "ambiguous" ? null : hit.player, note: hit.note };
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
    throw new ToolInputError("No usable DDF state found in the pasted text.");
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
    // JEG-1124 (Jeremy 2026-10-30, "Letter A."): a name that matches no player gives no total.
    const missing = rows.filter((r) => !r.player).length;
    const total = Math.round(rows.reduce((t, r) => t + (r.player?.value ?? 0), 0) * 10) / 10;
    lines.push(missing
      ? `${name} (no total: ${missing} name${missing === 1 ? "" : "s"} not matched):`
      : `${name} (total ${total.toFixed(1)}):`);
    lines.push(...rows.map((r) => r.player ? `  ${r.player.name} (${r.player.pos}): ${r.player.value}` : `  ${r.note || `${r.input}: NOT FOUND`}`));
  }
  if (work.target) {
    const r = resolveEntry(data.players, work.target as Entry);
    lists.target = [r];
    resolvedWork.target = r.player ? { key: String(r.player.player_key), name: r.player.name } : work.target;
    if (!r.player) unmatched.push(r.input);
    lines.push(`target: ${r.player ? `${r.player.name} (${r.player.pos}): ${r.player.value}` : (r.note || `${r.input}: NOT FOUND`)}`);
  }
  if (!Object.keys(lists).length) lines.push("The state carries league settings only, no players.");
  if (unmatched.length) lines.push("", `Could not match: ${unmatched.join(", ")}. Ask the user which player they meant (or to check the spelling).`);

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
  const names = (v: unknown, field: string) => playerNames(v, field);
  const work: Record<string, unknown> = {};
  const unmatched: string[] = [];
  const toEntry = (input: string) => {
    const hit = matchName(data.players, input);
    if (hit.match === "ambiguous" || !hit.player) {
      unmatched.push(hit.match === "ambiguous" ? `${input} (${hit.suggestions.map((p) => p.name).join(" or ")})` : input);
      return { name: input };
    }
    return { key: String(hit.player.player_key), name: hit.player.name };
  };
  for (const name of WORK_LISTS) {
    const list = names(a[name], name);
    if (list.length) work[name] = list.map(toEntry);
  }
  if (String(a.target ?? "").trim()) work.target = toEntry(checkName(String(a.target).trim(), "target"));
  if (!Object.keys(work).length && !prepared.state) {
    throw new ToolInputError("Give at least one of give, get, mine, theirs or target, or a pasted state.");
  }
  const allViews = ["compare", "targets", "finder"];
  const view = allViews.includes(String(a.view)) ? String(a.view) : inferView({ ...(prepared.state?.work ?? {}), ...work });
  const text = [
    ...header(data, s),
    "",
    "Saved as a DDF state. The person opens the link below to continue on the site.",
    ...(unmatched.length ? [`Could not match: ${unmatched.join(", ")} (kept by name; the site will try again).`] : []),
  ].join("\n");
  return finish(ok(text, { as_of: data.as_of, setting: data.setting, unmatched }), {
    prepared, deps, settings: s, view, work, block: true,
  });
}
