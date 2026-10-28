## 2026-10-28 - JEG-1129: the other team is judged on the Indexed chart mean

Contract: finish JEG-1129 so the trade tools judge your side on DDF Value and the other team on the
market, as Jeremy defined them: "DDF is not the trade chart average, it is the average of the weight
adjusted indexed value. DDF projections is the average of the imputed values across projected sources."
(Jeremy, 2026-10-28, chat.)

Correction to the 2026-10-26 entries for this ticket (`2026-10-26-jeg1129-chart-avg-key.md`,
`2026-10-26-jeg1129-t1-review.md`): the ticket mapped "indexed trade charts" to `ddf_value_charts`.
That series is DDF Value built from the charts only (the mean of their Adjusted values), and since
JEG-1073 it equals `ddf_value` for every player. Pointing the other team at it judged them on DDF Value,
so "you gain and they break even" could never pass. Those finder/waivers/targets/trade changes are
reverted to main; the site's `chart_avg` in the default Indexed view is already the market.

The real defect was in the connector path: get-values `include=charts` sent each chart's Adjusted value
as `chart_values`, the MCP put those on the chart keys, and `viability.ts` took their mean as the
market, which is DDF Value again. Now get-values also sends `chart_indexed`, the MCP finder rows carry
the Indexed values on the chart keys (as the site's rows do), and an old get-values without
`chart_indexed` makes the finder tools say chart values are unavailable rather than price on Adjusted.

### Verified (check named)
- `ddf_value == ddf_value_charts` for 738 of 738 players, 12-team half PPR, also with a custom roster
  or shares: get-values handler run in node on the built dist, clock pinned to 2026-10-23.
- DDF Value vs the Indexed chart mean differs (median ratio RB 1.22, WR 0.90, QB 0.96, TE 0.83;
  players priced by all four charts, value > 3): same run, `r.indexed` emitted.
- `tests/node/mcp_remote_check.mjs`: new block (you +5 DDF, they +8 on Indexed, fairness passes; an
  old-shape get-values is unavailable for both finder tools) passes, and fails with the old row mapping
  ("the arbitrage trade is found: []").
- `tests/node/get_values_handler_check.mjs`: new `chart_indexed` block passes with the change and fails
  without it ("chart_indexed on Jahmyr Gibbs"), run with the clock pinned and the earlier `same()`
  asserts skipped (see Claimed).
- Jeremy's USO league (his roster vs three opponents, `find_trades_league`, limit 50, built dist,
  pinned clock): main 10 candidates, all 10 "looks lopsided to them", 0 viable. This branch 66
  candidates, 7 of the top 50 lopsided, 0 viable: 14 fail only on the WR depth guardrail (4 WRs, 3
  start, `min_wr_backups` 1). With `min_wr_backups` 0, 11 viable.

### Claimed, not confirmed
- `get_values_handler_check.mjs` already fails on main before the new block: with the real clock
  (week 8) get-values returns 0 players; with a pinned clock its `runner` subprocess is not pinned.
  Week 8 publishing is JEG-1175's lane.
- The site finder's chart keys follow the chart tab's view; on the Adjusted tab `chart_avg` would be the
  Adjusted mean (= DDF Value). Not changed here; worth its own ticket.
- Nothing deployed. get-values must deploy before mcp (the new mcp refuses an old get-values).
