## 2026-10-24 - JEG-1037 MCP: find_trades tool for one pair of rosters

Adds `find_trades` to the remote MCP server. Takes two rosters (comma-separated names), league settings,
and optional max_per_side/min_rival_edge/limit. Returns ranked trade candidates where the caller gains DDF
Value and at least 3 of 4 trade charts say the rival breaks even or wins.

### What changed

- `supabase/functions/mcp/find-trades.ts` (new): pure `findTradesForPair()` function exported for reuse
  by the batch tool (JEG-1036). No Deno or DOM APIs.
- `supabase/functions/get-values/index.ts`: `?include=charts` parameter adds per-chart adjusted values
  (`chart_values`), `ddf_value_charts`, `ddf_value_projections` to each player record.
- `supabase/functions/mcp/tools.ts`: `find_trades` tool definition, `findTradesHandler`, `toFinderRow`,
  `findChartPlayer` helpers, `ToolUnavailableError` class, `ChartValuesResponse`/`FetchValuesWithCharts` types.
- `supabase/functions/mcp/index.ts`: `finderCache`/`chartCache`, `loadFinder()` (evals finder.js from the
  published site, like the codec loader), `fetchCharts` (calls get-values with include=charts),
  `FinderDeps` wired into `handleRpc`.
- `supabase/functions/mcp/rpc.ts`: passes `finderDeps` through to `runTool`.
- Doc surfaces: `app/llm/llms.txt`, `server-card.json`, `SKILL.md`, `docs/values-endpoint.md`.
- Tests: `tests/node/mcp_remote_check.mjs` (chart-enriched stubs, real finder.js loaded via createRequire,
  six assertions), `tests/test_llm_surfaces.py` (tool list updated).

### Verified (check named)

- `node --experimental-strip-types tests/node/mcp_remote_check.mjs` -- ok (basic search, trade shape,
  unmatched names, empty roster error, missing finder dep error, site link target)
- `python3 -m unittest tests.test_mcp_remote` -- 2 tests ok
- `python3 -m unittest tests.test_llm_surfaces` -- 7 tests ok
- `make validate` -- running (includes build, reference data, headless browser suite)

### Not verified

- Live Supabase deploy (not attempted per brief; report only)
- `deno check` on index.ts (no Deno in the sandbox)
- Real MCP client against the deployed function
