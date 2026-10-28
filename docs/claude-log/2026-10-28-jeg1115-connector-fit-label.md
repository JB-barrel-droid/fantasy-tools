# 2026-10-28: fit label in connector trade output (JEG-1115)

Lane: Claude Duet "Fit labels" thread. Builds on Ba-Nana's draft #966 and supersedes it (its base was too far behind main, where
tools.ts had been rewritten for compact output).

## What changed
- `supabase/functions/mcp/fit.ts` (from #966): the connector judges fit by calling the site's own
  `tradeFit` / `fitText` from finder.js (no copy of the rule), mapping the label to Natural /
  Market supported / Force.
- Bench weights, Jeremy's pick B (2026-10-26, "Yes B" on JEG-1115): `get-values` with
  `include=charts` now publishes the engine's own ES-14 readout as `bench_share`
  (QB/RB/WR/TE/overall, plus the league's bench-share `input`). `benchWeightsFromReadout`
  resolves it exactly like the page's `benchWeights()`. #966's rebuild from tiers
  (`benchWeightsFromPlayers`) is gone. With no readout (an older get-values) the fit is left
  out, never approximated.
- `tools.ts`: the fit is judged only for the trades returned (shown list and package), after
  viability ranking, so it adds no work to the search. Each trade gets `fit` and `fitReason` in
  structured output; the text adds one indented line with the finder's reason, which opens with
  the label. `find-trades.ts` and `viability.ts` are unchanged.

## Checks
- `node tests/node/connector_fit_check.mjs`: label and reason parity with finder `tradeFit` /
  `fitText` and with `fit_diagnostic.cjs` rows on the 20-team fixture; readout resolution.
- `tests/node/mcp_remote_check.mjs`: every find_trades and find_trades_league trade (and package
  offer) carries a fit label and reason, so removing the label fails it; no readout, no fit.
  Reply sizes stay under the existing caps (find default 6.7 KB, limit 50 20.9 KB, league 8.9 KB).
- `tests/node/get_values_handler_check.mjs dist`: include=charts sends `bench_share`; plain
  get-values is unchanged.
- `viability_check.mjs` 30/30, `test_edge_functions_parse`, `test_mcp_remote` pass.

## Not done here
- Live: needs both edge functions deployed (get-values first, then mcp). Not deployed; that
  needs Jeremy's yes.
