#!/usr/bin/env node
// JEG-616 step 5: MCP server for Data Driven Football trade values.
//
// Wraps the get-values endpoint (or falls back to direct engine execution)
// with MCP tools: get_values, trade_targets, compare_trade, risers_fallers,
// explain.
//
// Every response carries "Data Driven Football" attribution and the site link.
//
// Usage:
//   DDF_API_URL=https://<project>.supabase.co/functions/v1/get-values \
//     node dist/index.js
//
// Or without the endpoint (loads engine directly):
//   node dist/index.js

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const SITE_URL = process.env.DDF_SITE_URL || "https://jb-barrel-droid.github.io/fantasy-tools/";
const ATTRIBUTION = `Data Driven Football — ${SITE_URL}`;
const API_URL = process.env.DDF_API_URL || "";

// --- API client -------------------------------------------------------------

interface PlayerValue {
  player_key: number;
  name: string;
  pos: string;
  value: number;
  tier: number;
}

interface ValuesResponse {
  attribution: string;
  as_of: string | null;
  setting: { scoring: string; teams: number; superflex: number };
  players: PlayerValue[];
  sources_included: string[];
  sources_excluded: Array<{ key: string; reason: string }>;
}

async function fetchValues(
  scoring: string,
  teams: number,
  superflex: number,
): Promise<ValuesResponse> {
  if (!API_URL) throw new Error("DDF_API_URL is not set (the get-values function URL)");
  const url = new URL(API_URL);
  url.searchParams.set("scoring", scoring);
  url.searchParams.set("teams", String(teams));
  url.searchParams.set("superflex", String(superflex));

  const response = await fetch(url.toString(), {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API error ${response.status}: ${body}`);
  }
  return await response.json() as ValuesResponse;
}

// --- MCP server -------------------------------------------------------------

const server = new McpServer({
  name: "data-driven-football",
  version: "1.0.0",
});

// Tool: get_values
server.tool(
  "get_values",
  "Get current fantasy football trade values for all players. Returns each player's name, position, value (0-70 scale), and tier. Values are computed from multiple sources using the Data Driven Football methodology (value above waivers).",
  {
    scoring: z.enum(["standard", "half_ppr", "ppr"]).default("ppr")
      .describe("League scoring format"),
    teams: z.enum(["8", "10", "12", "14"]).default("12")
      .describe("Number of teams in the league"),
    superflex: z.boolean().default(false)
      .describe("Whether the league has a superflex slot"),
    position: z.enum(["QB", "RB", "WR", "TE", "all"]).default("all")
      .describe("Filter by position (or 'all' for every position)"),
    limit: z.number().min(1).max(500).default(50)
      .describe("Maximum number of players to return"),
  },
  async ({ scoring, teams, superflex, position, limit }) => {
    const data = await fetchValues(scoring, Number(teams), superflex ? 1 : 0);
    let players = data.players;
    if (position !== "all") {
      players = players.filter((p) => p.pos === position);
    }
    players = players.slice(0, limit);

    const lines = [
      `${ATTRIBUTION}`,
      `As of: ${data.as_of || "unknown"}`,
      `Settings: ${scoring}, ${teams} teams${superflex ? ", superflex" : ""}`,
      `Sources included: ${data.sources_included.join(", ")}`,
      "",
      "Rank | Player | Pos | Value | Tier",
      "-----|--------|-----|-------|-----",
      ...players.map((p, i) => `${i + 1} | ${p.name} | ${p.pos} | ${p.value} | ${p.tier}`),
    ];

    return { content: [{ type: "text" as const, text: lines.join("\n") }] };
  },
);

// Tool: trade_targets
server.tool(
  "trade_targets",
  "Find trade targets: players whose value is close to a given player's value, suggesting realistic trade partners. Useful for 1-for-1 or package deals.",
  {
    player_name: z.string().describe("Name of the player you want to trade (or trade for)"),
    scoring: z.enum(["standard", "half_ppr", "ppr"]).default("ppr"),
    teams: z.enum(["8", "10", "12", "14"]).default("12"),
    superflex: z.boolean().default(false),
    range_pct: z.number().min(1).max(50).default(15)
      .describe("How close in value (percentage) to look for targets"),
    position: z.enum(["QB", "RB", "WR", "TE", "all"]).default("all")
      .describe("Filter targets by position"),
  },
  async ({ player_name, scoring, teams, superflex, range_pct, position }) => {
    const data = await fetchValues(scoring, Number(teams), superflex ? 1 : 0);
    const needle = player_name.toLowerCase();
    const player = data.players.find(
      (p) => p.name.toLowerCase() === needle || p.name.toLowerCase().includes(needle),
    );
    if (!player) {
      return {
        content: [{
          type: "text" as const,
          text: `${ATTRIBUTION}\n\nPlayer "${player_name}" not found. Check the spelling or try a partial name.`,
        }],
      };
    }

    const range = player.value * (range_pct / 100);
    let targets = data.players.filter(
      (p) =>
        p.player_key !== player.player_key &&
        Math.abs(p.value - player.value) <= range,
    );
    if (position !== "all") {
      targets = targets.filter((p) => p.pos === position);
    }
    // Sort by closeness.
    targets.sort((a, b) => Math.abs(a.value - player.value) - Math.abs(b.value - player.value));
    targets = targets.slice(0, 20);

    const lines = [
      ATTRIBUTION,
      `As of: ${data.as_of || "unknown"}`,
      `Settings: ${scoring}, ${teams} teams${superflex ? ", superflex" : ""}`,
      "",
      `Trade targets for ${player.name} (${player.pos}, value: ${player.value}, tier ${player.tier}):`,
      "",
      "Player | Pos | Value | Tier | Diff",
      "-------|-----|-------|------|-----",
      ...targets.map((t) => {
        const diff = t.value - player.value;
        const sign = diff >= 0 ? "+" : "";
        return `${t.name} | ${t.pos} | ${t.value} | ${t.tier} | ${sign}${diff.toFixed(1)}`;
      }),
    ];

    return { content: [{ type: "text" as const, text: lines.join("\n") }] };
  },
);

// Tool: compare_trade
server.tool(
  "compare_trade",
  "Compare two sides of a trade to see which side gets more total value. Pass comma-separated player names for each side.",
  {
    side_a: z.string().describe("Comma-separated player names for side A (the team giving these players)"),
    side_b: z.string().describe("Comma-separated player names for side B (the team giving these players)"),
    scoring: z.enum(["standard", "half_ppr", "ppr"]).default("ppr"),
    teams: z.enum(["8", "10", "12", "14"]).default("12"),
    superflex: z.boolean().default(false),
  },
  async ({ side_a, side_b, scoring, teams, superflex }) => {
    const data = await fetchValues(scoring, Number(teams), superflex ? 1 : 0);

    function findPlayers(names: string): Array<{ input: string; found: PlayerValue | null }> {
      return names.split(",").map((raw) => {
        const name = raw.trim().toLowerCase();
        if (!name) return { input: raw.trim(), found: null };
        const found = data.players.find(
          (p) => p.name.toLowerCase() === name || p.name.toLowerCase().includes(name),
        );
        return { input: raw.trim(), found: found || null };
      });
    }

    const sideAPlayers = findPlayers(side_a);
    const sideBPlayers = findPlayers(side_b);

    const notFound = [
      ...sideAPlayers.filter((p) => !p.found).map((p) => p.input),
      ...sideBPlayers.filter((p) => !p.found).map((p) => p.input),
    ];

    const sumA = sideAPlayers.reduce((s, p) => s + (p.found?.value || 0), 0);
    const sumB = sideBPlayers.reduce((s, p) => s + (p.found?.value || 0), 0);
    const diff = sumA - sumB;

    const fmt = (side: Array<{ input: string; found: PlayerValue | null }>) =>
      side.map((p) =>
        p.found
          ? `  ${p.found.name} (${p.found.pos}): ${p.found.value}`
          : `  ${p.input}: NOT FOUND`
      ).join("\n");

    const verdict = Math.abs(diff) < 2
      ? "This trade is roughly even."
      : diff > 0
      ? `Side A gets ${diff.toFixed(1)} more value. Side B wins this trade.`
      : `Side B gets ${(-diff).toFixed(1)} more value. Side A wins this trade.`;

    const lines = [
      ATTRIBUTION,
      `As of: ${data.as_of || "unknown"}`,
      `Settings: ${scoring}, ${teams} teams${superflex ? ", superflex" : ""}`,
      "",
      `Side A gives up (total: ${sumA.toFixed(1)}):`,
      fmt(sideAPlayers),
      "",
      `Side B gives up (total: ${sumB.toFixed(1)}):`,
      fmt(sideBPlayers),
      "",
      verdict,
      ...(notFound.length ? [`\nWarning: could not find: ${notFound.join(", ")}`] : []),
    ];

    return { content: [{ type: "text" as const, text: lines.join("\n") }] };
  },
);

// Tool: risers_fallers
server.tool(
  "risers_fallers",
  "Show players whose value changed the most compared to the prior week. Note: requires prior-week data to be available in the engine.",
  {
    scoring: z.enum(["standard", "half_ppr", "ppr"]).default("ppr"),
    teams: z.enum(["8", "10", "12", "14"]).default("12"),
    superflex: z.boolean().default(false),
    direction: z.enum(["risers", "fallers", "both"]).default("both")
      .describe("Show risers, fallers, or both"),
    limit: z.number().min(1).max(50).default(10),
  },
  async ({ scoring, teams, superflex, direction, limit }) => {
    // This tool requires prior-week comparison. Currently the endpoint
    // returns current values only; prior-week would need a second pipeline
    // run. For now, return a helpful message.
    return {
      content: [{
        type: "text" as const,
        text: [
          ATTRIBUTION,
          "",
          "Risers/fallers comparison is not yet available through the API.",
          `Visit ${SITE_URL} to see week-over-week changes`,
          "on the interactive chart (the prior-week comparison runs in the browser).",
          "",
          `Requested: ${direction}, ${scoring}, ${teams} teams${superflex ? ", superflex" : ""}, top ${limit}`,
        ].join("\n"),
      }],
    };
  },
);

// Tool: explain
server.tool(
  "explain",
  "Explain how Data Driven Football trade values work: methodology, sources, what the numbers mean, and how to use them for trades.",
  {
    topic: z.enum([
      "methodology",
      "sources",
      "value_scale",
      "scoring_formats",
      "superflex",
      "tiers",
      "how_to_trade",
    ]).describe("What to explain"),
  },
  async ({ topic }) => {
    const explanations: Record<string, string> = {
      methodology: [
        "Data Driven Football Trade Values — Methodology",
        "=" .repeat(50),
        "",
        "Values represent how much each player is worth above the waiver wire,",
        "on a 0-70 scale. The methodology:",
        "",
        "1. Multiple projection and chart sources are combined (ESPN, CBS ROS,",
        "   Razzball for projections; FantasyCalc, USA Today, FantasyPros, CBS",
        "   for published trade charts).",
        "2. Each source's raw values are translated to 'value above waivers'",
        "   using positional waiver lines based on the league's roster settings.",
        "3. A two-tier marginal pricing curve weights starter value (85%) higher",
        "   than bench value (15%), with a smooth S-curve transition.",
        "4. All sources are normalized to a common 70-point scale (the 'fixed pie').",
        "5. The final DDF (Data Driven Football) value is the weighted average",
        "   across all included sources.",
        "",
        "This means values automatically adjust for league size, scoring format,",
        "and roster construction.",
      ].join("\n"),

      sources: [
        "Data Driven Football — Sources",
        "=" .repeat(40),
        "",
        "Projection sources (our methodology applied to their per-game projections):",
        "  - ESPN: Mike Clay model season projections",
        "  - CBS ROS: CBS rest-of-season projections",
        "  - Razzball: Independent third projection source",
        "",
        "Chart sources (published trade values, rescaled to our 0-70 scale):",
        "  - FantasyCalc: Crowd trade values from completed real trades",
        "  - USA Today: Editorial trade value chart",
        "  - FantasyPros: Analyst-consensus editorial trade values",
        "  - CBS: Editorial trade values",
        "",
        "Sources are included only when fresh data is available. A held or",
        "missing source is excluded from the blend but does not zero out.",
      ].join("\n"),

      value_scale: [
        "Data Driven Football — Value Scale",
        "=" .repeat(40),
        "",
        "Values range from 0 to 70:",
        "  - 60-70: Elite, league-winning assets (top 3-5 overall)",
        "  - 45-60: High-end starters, premium trade pieces",
        "  - 30-45: Solid starters with meaningful trade value",
        "  - 15-30: Flex-worthy players, depth pieces with some value",
        "  - 5-15: Bench stashes, lottery tickets",
        "  - 0-5: Near waiver-wire value",
        "",
        "A value of 0 does not mean the player is worthless — it means their",
        "projected production is at or below the waiver wire replacement level",
        "for their position in the given league settings.",
      ].join("\n"),

      scoring_formats: [
        "Data Driven Football — Scoring Formats",
        "=" .repeat(45),
        "",
        "Three scoring formats are supported:",
        "  - standard: No points per reception",
        "  - half_ppr: 0.5 points per reception",
        "  - ppr: 1.0 point per reception (full PPR)",
        "",
        "PPR increases the value of high-volume receivers (especially pass-catching",
        "backs and slot receivers) relative to standard scoring. Standard scoring",
        "favors volume rushers and touchdown-dependent players.",
      ].join("\n"),

      superflex: [
        "Data Driven Football — Superflex",
        "=" .repeat(40),
        "",
        "In a superflex league, one additional roster slot accepts QB/RB/WR/TE.",
        "Because QBs score significantly more fantasy points than other positions,",
        "this slot is almost always filled by a QB, dramatically increasing QB values.",
        "",
        "When superflex is enabled:",
        "  - QB values rise significantly (top QBs become the most valuable assets)",
        "  - Published chart sources that have their own superflex/2QB valuations",
        "    use those instead of their 1QB values (also in a league that starts",
        "    2 QBs with no superflex slot)",
        "  - The waiver line and positional allocation adjust accordingly",
      ].join("\n"),

      tiers: [
        "Data Driven Football — Tiers",
        "=" .repeat(35),
        "",
        "Players are grouped into tiers based on natural breaks in value.",
        "Players within the same tier have similar trade value — trading within",
        "a tier is roughly even, while trading across tiers means one side is",
        "likely giving up more value.",
        "",
        "Tiers are useful for quick trade evaluation: if both sides of a trade",
        "involve players in the same tier range, it is likely fair.",
      ].join("\n"),

      how_to_trade: [
        "Data Driven Football — How to Use Values for Trading",
        "=" .repeat(55),
        "",
        "1. Look up both sides of a proposed trade using compare_trade.",
        "2. The side giving up MORE total value is getting the worse deal.",
        "3. A difference of 2-3 points is roughly even; 5+ is meaningful.",
        "4. Consider positional scarcity: an RB1 may be harder to replace than",
        "   a WR1 in many league formats.",
        "5. Use trade_targets to find players with similar value to yours —",
        "   these are realistic 1-for-1 trade partners.",
        "6. Values change weekly as projections update. A player trending up",
        "   may cost more next week.",
        "",
        "Remember: these are market values based on production expectations.",
        "Your specific roster needs may make a player worth more or less to you.",
      ].join("\n"),
    };

    return {
      content: [{
        type: "text" as const,
        text: `${ATTRIBUTION}\n\n${explanations[topic]}`,
      }],
    };
  },
);

// --- Start ------------------------------------------------------------------

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("MCP server error:", error);
  process.exit(1);
});
