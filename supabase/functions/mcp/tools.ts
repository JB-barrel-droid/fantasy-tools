// JEG-1012: tool logic for the remote MCP endpoint. Pure functions, no Deno
// APIs, so the same file runs under node in tests/test_mcp_remote.py.
//
// Lookups and trade math run here, so a tool call returns a small answer
// instead of the whole player list.

export interface PlayerValue {
  player_key: number;
  name: string;
  pos: string;
  value: number;
  tier: number;
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
) => Promise<ValuesResponse>;

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
};

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
      "Compare two sides of a trade by total value. Pass comma-separated player names for each side. Side A is what team A gives up.",
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
  return { scoring, teams, superflex };
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
): Promise<ToolResult> {
  if (name === "explain") return explain(String(args.topic ?? ""));

  const s = settings(args);

  if (name === "get_values") {
    const pos = position(args);
    const limit = Math.min(200, Math.max(1, Number(args.limit ?? 50) || 50));
    const data = await fetchValues(s.scoring, s.teams, s.superflex);
    const players = data.players.filter((p) => pos === "all" || p.pos === pos).slice(0, limit);
    const text = [
      ...header(data, s),
      `Sources included: ${data.sources_included.join(", ")}`,
      "",
      "Rank | Player | Pos | Value | Tier",
      ...players.map((p, i) => `${i + 1} | ${p.name} | ${p.pos} | ${p.value} | ${p.tier}`),
    ].join("\n");
    return ok(text, {
      as_of: data.as_of,
      setting: data.setting,
      sources_included: data.sources_included,
      players,
    });
  }

  if (name === "get_player_value") {
    const names = String(args.names ?? "").split(",").map((n) => n.trim()).filter(Boolean);
    if (!names.length) throw new ToolInputError("names is required");
    const data = await fetchValues(s.scoring, s.teams, s.superflex);
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
    return ok(text, { as_of: data.as_of, setting: data.setting, results });
  }

  if (name === "trade_targets") {
    const pos = position(args);
    const pct = Math.min(50, Math.max(1, Number(args.range_pct ?? 15) || 15));
    const data = await fetchValues(s.scoring, s.teams, s.superflex);
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
    return ok(text, { as_of: data.as_of, setting: data.setting, player, targets });
  }

  if (name === "compare_trade") {
    const data = await fetchValues(s.scoring, s.teams, s.superflex);
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
      `Verdict: ${verdict}.`,
      ...(notFound.length ? [`Warning: not found, counted as 0: ${notFound.join(", ")}`] : []),
    ].join("\n");
    return ok(text, {
      as_of: data.as_of,
      setting: data.setting,
      side_a: { total: sumA, players: a },
      side_b: { total: sumB, players: b },
      difference: diff,
      verdict,
      not_found: notFound,
    });
  }

  throw new ToolInputError(`unknown tool: ${name}`);
}

const EXPLANATIONS: Record<string, string> = {
  methodology:
    "Values are 'value above waivers': how much more a player is expected to produce than a freely available replacement at the same position, in the user's league (scoring, team count, superflex). Several projection sources and published trade charts are blended; a stale or held source is left out of the blend rather than counted as zero. Full method: the site's methodology pages.",
  sources:
    "Projection sources: ESPN, CBS rest-of-season, Razzball. Published trade charts: FantasyCalc, USA Today, FantasyPros, CBS. The get_values response lists which sources are included and excluded for the current week.",
  value_scale:
    "Higher is more valuable and there is no fixed maximum; the best players are around 70 or a little above. Roughly: 45+ premium assets, 30-45 solid starters, 15-30 flex and depth, under 15 bench and lottery tickets. A value near 0 means replacement level in that league, not worthless.",
  scoring_formats:
    "standard = no points per reception, half_ppr = 0.5, ppr = 1.0. PPR lifts high-target receivers and pass-catching backs; standard favors rushers and touchdown-dependent players.",
  superflex:
    "Superflex adds a slot that takes a QB, which sharply raises QB values and shifts replacement levels. Charts that publish their own superflex values use them.",
  tiers:
    "Tiers group players with similar value. Trading within a tier is roughly even; across tiers one side gives up meaningfully more.",
  how_to_trade:
    "1) Use compare_trade on both sides. 2) A gap under about 2 points is roughly even; 5 or more is meaningful. 3) Use trade_targets to find similar-value partners. 4) Your own roster needs can outweigh market value. Values update weekly.",
};

function explain(topic: string): ToolResult {
  const text = EXPLANATIONS[topic];
  if (!text) throw new ToolInputError(`unknown topic: ${topic}. Must be one of: ${EXPLAIN_TOPICS.join(", ")}`);
  return ok(`Data Driven Football\n\n${text}`, { topic, text });
}
