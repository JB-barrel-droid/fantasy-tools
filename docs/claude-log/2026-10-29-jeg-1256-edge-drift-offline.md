## 2026-10-29 - Edge drift checker adopted offline with unavailable-result regressions (JEG-1256, part of JEG-1049)

Contract: port the #1003 checker (`cma/JEG-1049` @ `6397413bbcc898d5d159cc5c0e69442a8cf18208`) onto current main on a new branch, and correct its classification so missing, empty, non-numeric or unreadable evidence reads as "could not compare" (exit 2), never as healthy (0) or as drift (1). Offline only: no workflow, no live endpoints, no Supabase, no deploy.

This entry corrects the 2026-10-27 entry (`2026-10-27-edge-drift-check.md`, ported unchanged): its "Verified" list did not cover the cases below, and several of them were misclassified.

### What changed
- `tools/edge_drift_check.mjs`: explicit exit contract (0 in sync, 1 drift, 2 could not compare). Both sides are read with `Promise.allSettled`, so one unreadable side no longer hides the other. Any error while reading a side, expected or not, is reported as unavailable with no stack trace (before: a `null` player row crashed node with exit 1, which read as drift).
- Unavailable (exit 2): empty `players`, `players` not a list or reply not an object, a player row that is not an object, `player_key` or `value` missing or non-numeric, `chart_values` not an object of numbers or nulls, `chart_values` with no number on any player, `ddf_value_*` non-numeric, `ddf_value_*` null on every player, a chart field present on some players but not others, mcp JSON-RPC `error`, mcp listing no tools, a tool with no name, non-2xx, unreachable, unparseable or SSE without a `data:` line.
- Drift (exit 1), intent kept from #1003: tool names on main vs deployed (missing and extra), and a chart field (`chart_values`, `ddf_value_charts`, `ddf_value_projections`) absent from every player. When one side shows drift and the other is unavailable, exit is 1 and the unavailable side is listed under "Also could not compare".
- Legitimate zero stays numeric (`value: 0`, `ddf_value_*: 0`, chart value 0 pass).
- `tests/node/edge_drift_check.mjs`: 30 fake-server cases (5 in sync, 4 drift, 21 could not compare), including SSE positive, 403 on each side, unreachable, and every case above.
- `Makefile`: `tests.test_edge_drift_check` added to `test-unit-modules` (preview CI full suite, non-blocking), right after `tests.test_mcp_remote`. Not added to `test-core`.
- Not ported: `.github/workflows/edge-drift-check.yml` (the daily 12:40 UTC cron). JEG-1256 forbids enabling or dispatching it; merging it to main would enable the schedule. It stays on #1003.

### Fixture contract review (what is allowed to be null)
Read from `supabase/functions/get-values/index.ts` (`include=charts` branch) and `supabase/functions/mcp/tools.ts` on main `b863069`:
- `player_key` and `value` are always finite numbers (rows without a finite blended value are skipped), so missing or non-numeric is unreadable.
- `chart_values` is always an object; each chart entry is `number | null` (`round1`). Per-chart null is allowed.
- `ddf_value_charts` and `ddf_value_projections` are `number | null` on every row (typed `number | null` in `tools.ts`). Null on one player is allowed.
- All three chart fields are written on every row when `include=charts`, so a deploy returns them on every player or on none. Partial presence fits no deploy.

### Verified (check named)
- `python3 -m unittest tests.test_edge_drift_check`: OK (all 30 cases pass) on this branch.
- Old-vs-new proof: the same harness with `EDGE_DRIFT_SCRIPT` pointed at a copy of the #1003 checker (temporary file, not committed). Exit code was wrong on 14 cases: empty players (1, want 2); `ddf_value_*` null on every player (0); non-numeric `ddf_value_*` (0); missing `value` (0); non-numeric `value` (0); `chart_values` null (1); `chart_values` with a string entry (0); `chart_values` all null (0); partial chart field (1); a null player row (1, crash); `players` not a list (1); reply JSON `null` (1); mcp lists no tools (1); a tool with no name (1). A further 5 cases had the right exit code but message text the new harness pins (drift messages, JSON-RPC error, both unreachable).
- `python3 -m unittest tests.test_run_suite tests.test_validate_shards tests.test_no_real_clock`: OK.
- `python3 -m unittest tests.test_render_sweep_coverage`: 4 failures, identical on main `b863069` without this change (`test_interactive_trades_release_render` unwired); not caused by this branch.
- Nothing in the harness touches the network beyond 127.0.0.1.

### Claimed, not confirmed
- Behaviour against production endpoints: not run (out of scope; JEG-1248 saw `ENOTFOUND` / proxy 403 from the sandbox).
- That `test-unit-modules` runs this module in preview CI: inferred from the Makefile; confirmed only once the PR's CI runs.

### Held, not decided here (JEG-1248 items b and c)
- `serverInfo.build` vs main's last `supabase/functions/mcp` commit: not checked. Depends on deploys setting `DDF_BUILD_SHA`; build-SHA provenance is held separately.
- `bench_share`: not checked (a case pins that its absence still passes). Whether it belongs in scope is a policy call.
- Whether all-null `ddf_value_*` or all-null `chart_values` should be unavailable rather than healthy: chosen as unavailable (no numeric evidence the deploy computes the field). Logged in the picks log; reversible.
