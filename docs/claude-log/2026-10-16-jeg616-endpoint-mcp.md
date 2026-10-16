# JEG-616: Agent-callable values endpoint + MCP server

**Date:** 2026-10-16
**PR:** (pending)
**Branch:** `jeg-616-endpoint-mcp`

## What changed

1. **Supabase edge function** (`supabase/functions/get-values/index.ts`): loads
   published value-model.js + bundle from the live site, runs
   `ValueModel.runValuePipeline()`, returns DDF blended values. Includes source
   eligibility (freshness/staleness, holds, validation status), lineup
   parameters for bench share, and ESPN zero-player handling.

2. **MCP server** (`mcp-server/`): wraps the endpoint with tools: get_values,
   trade_targets, compare_trade, risers_fallers, explain. All responses carry
   attribution.

3. **Parity test** (`tests/test_endpoint_parity.py` +
   `tests/_edge_pipeline_runner.cjs`): headless Node.js runner replicates the
   edge function pipeline; Playwright drives the engine page; compares all
   players across 4 settings. Negative-tested with wrong bench_per_team=99.

## Key bugs found and fixed

- `espnProjectsZero` is a derived property from `product-data.js`, not present
  on raw player records. Raw data uses `espn_status === "ineligible"` and
  `espn_zeroed: true`. Without this, players ESPN marks ineligible (e.g. Tank
  Dell on IR) were missing from ESPN's native set, causing single-source DDF
  blends (2x values) instead of two-source blends.

- Source eligibility was missing from both edge function and test runner: chart
  sources at week 5 were included when current week is 6, and held sources
  weren't marked hidden.

- Bench share was hardcoded at 0.15 instead of using lineup-parameters.json
  (expected-starts model gives ~0.087).

## Verified

- `pytest tests/test_endpoint_parity.py` — 5/5 pass (4 parity + 1 negative)
- MCP server compiles (`npx tsc --noEmit` clean)

## Not verified

- Edge function not deployed (needs Supabase project/account decision from Jeremy)
- MCP server not integration-tested against live endpoint
