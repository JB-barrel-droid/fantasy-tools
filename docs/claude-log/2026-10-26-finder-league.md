## 2026-10-26 - JEG-1070 finder tools pass the pasted league

Contract: find_trades and find_trades_league priced the default lineup for a pasted custom league because fetchCharts sent only scoring, teams and superflex. Pass `league` through.

### Verified (check named)
- `node tests/node/mcp_remote_check.mjs` prints ok with the new assertions: both finder tools hand the pasted league to fetchCharts; a plain league sends none.
- Negative test: with the supabase/functions/mcp changes stashed, the same test fails at "find_trades passes the pasted league to fetchCharts".

### Claimed, not confirmed
- The chart cache key and `league` query parameter in index.ts are not exercised by the test (the stub replaces fetchCharts); they mirror fetchValues in the same file.
- docs/get-values.openapi.yaml does not describe `league` or `include=charts` at all (checked by grep); left unchanged, pre-existing gap.
- Not deployed. Order: get-values (already live, v5), then mcp.
