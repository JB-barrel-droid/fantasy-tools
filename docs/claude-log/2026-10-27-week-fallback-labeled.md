## 2026-10-27 - JEG-1156 / JEG-1157: fall back to the latest published week, labeled

Contract: Jeremy, 2026-10-27, option A. When no trade chart has posted the content week (the Tuesday
flip), DDF Value uses the latest published week and says so ("Week 7 values, week 8 not published
yet"), on the dashboard, v2 and get-values/MCP. No value math, blend weight or charts-only change.

Changes:
- `supabase/functions/get-values/weeks.ts` (new, pure): the week rule and label, used by
  `get-values/index.ts` and `tests/_edge_pipeline_runner.cjs`. A chart is left out only when older
  than the values week (newest published chart week, capped at the content week).
- `product-data.js` `buildSourceFreshness` adds `values_week`, `values_week_fallback`,
  `values_week_label` and per-row `behind_values_week`; `curve-widget.js` `compositeKeyOlderWeek`
  uses `behind_values_week` instead of "older than the content week".
- Labels: dashboard chart context line and table note; v2 page stamp and freshness header.
- get-values response: `values_week`, `current_week`, `values_week_note`, `sources_fallback`, and
  `sources_excluded` now lists charts dropped before the pipeline with the reason.
- MCP tools (`mcp/tools.ts`): a "Values week: ..." line and `values_week` / `values_week_note` in
  every values-backed tool; get_values lists excluded sources.

### Verified (check named)
- `tests/node/week_fallback_check.mjs`: weeks.ts and product-data.js agree (values week, flag,
  label, dropped charts) on pinned days: current week published, partly published, missing, a chart
  two weeks behind, no chart at all, and the shipped bundle on 2026-10-27.
- `tests/node/get_values_week_check.mjs`: the get-values handler with `DDF_TODAY` pinned prices the
  same values on the flip day as in the charts' own week, labels it, names the fallback charts,
  drops a chart a week further behind with its reason, and returns no players with
  "No trade chart published yet" when no chart exists.
- `tests/node/mcp_week_check.mjs`: get_values, get_player_value and read_state carry the label.
- `tests.test_week_fallback.ReferenceWeekFallbackTests`: `value_reference.py` keeps the charts' week on
  the flip day and still leaves out a chart a week further behind.
- `tests/test_week_fallback_render.py`: dashboard and v2 (1440 and 390 wide) price DDF Value and
  show the label on the flip day; no label in the data's own week. Fails without the curve-widget
  change (0 players priced on all three surfaces).

### Claimed, not confirmed
- The live MCP returns players again only after `get-values` and `mcp` are deployed (not done here).
