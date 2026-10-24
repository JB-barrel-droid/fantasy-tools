# Values endpoint (Supabase edge function `get-values`) and MCP server

Ticket JEG-616. Hosting decision: Supabase edge function (Jeremy, 2026-10-19).

- Function: `supabase/functions/get-values/index.ts`. Reads the published site
  (`value-model.js`, `lineup-parameters.json`, the comparison bundle, and the
  `players-data` island on the home page), runs `runValuePipeline`, returns
  blended values. No database access, no schema change, no service-role key.
- Public: `verify_jwt = false` in `supabase/config.toml`; per-IP rate limit
  (30/min, in memory per instance); CORS allow-list in the function.
- Parity with the page is pinned by `tests/test_endpoint_parity.py`.
- MCP server, local: `mcp-server/` (stdio), set `DDF_API_URL` to the function URL.
- MCP server, remote (JEG-1012): `supabase/functions/mcp/` (Streamable HTTP, stateless, JSON responses). See "Remote MCP" below.

## Request

`GET|POST /functions/v1/get-values` with `scoring` (standard|half_ppr|ppr),
`teams` (8|10|12|14), `superflex` (0|1). Optional `include=charts` adds
per-chart adjusted values (`chart_values`) and DDF sub-versions
(`ddf_value_charts`, `ddf_value_projections`) to each player record (used
internally by the MCP `find_trades` tool).

## Configuration

| Name | Where | Default |
|---|---|---|
| `DDF_SITE_ORIGIN` | function secret (optional) | `https://jb-barrel-droid.github.io/fantasy-tools` |
| `DDF_API_URL` | MCP server env (required) | none |
| `DDF_SITE_URL` | MCP server env (optional) | the Pages URL |

`datadrivenfootball.com` did not resolve on 2026-10-19, so the Pages URL is the
default origin. Once the domain is live, set `DDF_SITE_ORIGIN` (no redeploy of
code needed, only the secret) and add the origin to `ALLOWED_ORIGINS` if it
differs.

## Deploy

`get-values` was found deployed on 2026-10-24 (project `iskiybsimubiujwuchsl`, version 2, `verify_jwt` false). Commands for a fresh project:

    supabase login
    supabase link --project-ref <PROJECT_REF>
    supabase functions deploy get-values --project-ref <PROJECT_REF>
    # optional, only after the custom domain is live:
    supabase secrets set DDF_SITE_ORIGIN=https://datadrivenfootball.com --project-ref <PROJECT_REF>

No other secrets are needed. URL: `https://<PROJECT_REF>.supabase.co/functions/v1/get-values`.

## Known limits

- The function evals the site's own `value-model.js` at cold start (loaded
  from the published origin, so the endpoint always matches the page).
- Rate limit is per instance, not global.
- Cold start fetches about 3.7 MB; first call is slow, results cached 5 minutes.

## Remote MCP (JEG-1012)

For Claude.ai custom connectors, ChatGPT apps/developer mode and any MCP client
that needs a URL instead of a local process.

- Function: `supabase/functions/mcp/` (`index.ts` serves, `rpc.ts` is the
  JSON-RPC dispatch, `tools.ts` is the tool logic). Public (`verify_jwt = false`),
  POST only, no sessions, no SSE, 60 requests/min per IP per instance.
- It calls `get-values` (`DDF_API_URL` secret overrides the URL; default is
  `$SUPABASE_URL/functions/v1/get-values`), so tool numbers match the site.
- Tools: `get_values`, `get_player_value`, `trade_targets`, `compare_trade`,
  `read_state`, `make_state`, `find_trades`, `explain`. Name lookup and trade
  math run server-side; each result also carries `structuredContent`.
  `risers_fallers` is not offered: the endpoint has no prior-week data.
- `find_trades`: takes two rosters (comma-separated names), finds trade packages
  where you gain DDF Value and at least 3 of 4 trade charts say the other team
  breaks even or wins. Loads `finder.js` from the site (like the codec) and
  calls `get-values?include=charts` for per-chart values. Optional: `max_per_side`
  (1-4, default 2), `min_rival_edge`, `limit`. The pure function
  `findTradesForPair` is in `mcp/find-trades.ts` for reuse by the batch tool.
- Tests: `tests/test_mcp_remote.py` (node, stub values, no network) in
  `make test-unit`.

Deploy: `supabase functions deploy mcp --project-ref <PROJECT_REF>`.
Connector URL: `https://<PROJECT_REF>.supabase.co/functions/v1/mcp`.

Not yet verified (2026-10-24): the deployed function against a real client,
and `deno check` on `index.ts` (no Deno in the build sandbox).

### Shared state with the site (JEG-1027)

Spec: `design/llm-site-state.md`. Every tool takes an optional `state` (a pasted `ddf-state` block, JSON or site link) that supplies the league; explicit arguments win. Every result ends with a link to the same view on the site (`/#compare-trade?...`, `/#trade-targets?...`, `/#find-trade?...`) and returns the state in `structuredContent.state`. `read_state` resolves a pasted state to players and prices them; `make_state` turns names from the chat into a block and link for the site.

- The function loads the codec `app/v2/ddf-state.js` from `<site>/v2/ddf-state.js` at cold start (published by the v2 build). If that fails, tools answer from their plain arguments and say the pasted state was not read.
- **Pricing limit:** `get-values` prices only scoring, teams and superflex. A pasted league with a roster shape, position shares, season weeks or advanced settings is priced with the site's default lineup, and the result says so (JEG-1029 tracks pricing the full league).
- **Site side:** compare links open today (`give`, `get`, `scoring`, `roster`...). `teams`, `mine`, `theirs` and `target` are read by the site in JEG-1026; until then those links open the right tab with the league settings the site already understands.

### Viability scoring (JEG-1038)

`mcp/viability.ts` — pure module, no I/O. Scores and ranks trade offers by
viability. Used by `find_trades` (single pair) and the batch league tool.
The site's `finder.js` can load the same logic later.

**Per-offer output (`ScoredOffer`):**

| Field | Type | Description |
|---|---|---|
| `team` | string | Opponent team name |
| `userGives` / `userGets` | `[{player_key, name, pos, ddfValue}]` | Players traded |
| `ddfEdge` | number | DDF Value gain (receive − give) for the user |
| `userLineupDelta` | number | User's starting lineup value change on DDF |
| `theirMarketNet` | number | Other team's market-value net (what they get − give) |
| `theirLineupDelta` | number | Other team's lineup change on market value |
| `theirPositionsBefore` / `After` | `{pos: {starters, value}}` | Their starters at each position, before/after |
| `userProtectedAfter` | `{pos: {starters, value}}` | User's starters at guardrail positions, after |
| `viable` | boolean | All 9 checks passed |
| `label` | `"High" \| "Med-High" \| "Medium" \| null` | Acceptance likelihood (null when non-viable) |
| `failedChecks` | `string[]` | Human-readable failure reasons |
| `temporaryGap` | boolean | Either team cannot fill a starting slot while injured players are out |
| `checks` | `CheckResult[]` | All 9 checks with name, passed, detail |

**Viability checks (all run on every offer):**

1. **Arbitrage**: user receives more DDF value than sent.
2. **Perceived fairness**: other team receives >= what it sends on market value.
3. **User lineup improves**: user's starting lineup improves on DDF value.
4. **Their lineup improves**: other team's starting lineup improves on market value.
5. **Position protection**: no position the other team gives up gets meaningfully weaker in starters.
6. **Depth**: neither team lacks healthy relevant players for starting slots plus backups at RB/WR.
7. **Roster space**: a team taking more players than it sends must have dead weight to drop.
8. **QB kept**: both teams keep a QB.
9. **User guardrails**: user-defined position protections are satisfied.

**Ordering:** viable first (by DDF edge, then user lineup improvement, then
perceived fairness). Non-viable follow (fewest failed checks, then DDF edge).
Deduplicated by received players.

**Labels:** High = a position they give up actually gets better and their lineup
clearly improves; Med-High = their lineup or perceived value clearly improves;
Medium = fair swap with small gain for them.

**Package (`selectPackage`):** across all added teams, the best combination of
viable offers that never sends the same player twice and uses each team at most
once. Output includes the user's lineup after the package.

**Configurable defaults (awaiting Jeremy's review):**

| Parameter | Default | Description |
|---|---|---|
| `minDdfEdge` | 0 | Minimum DDF value gain for the user |
| `minMarketNet` | 0 | Minimum market-value gain for the other team |
| `minUserLineupGain` | 0 | Minimum user lineup improvement |
| `minTheirLineupGain` | 0 | Minimum their lineup improvement |
| `positionWeakerThreshold` | 0.15 | Starter group drop fraction = "meaningfully weaker" |
| `depthPlayerCutoff` | 0.5 | Minimum DDF value for a player to count as depth |
| `deadWeightCutoff` | 0.5 | Maximum DDF value for a player to be considered droppable |
| `minRbBackups` | 1 | Minimum healthy RB backups beyond starters |
| `minWrBackups` | 1 | Minimum healthy WR backups beyond starters |
| `guardrails` | `[]` | User-defined position protections |
