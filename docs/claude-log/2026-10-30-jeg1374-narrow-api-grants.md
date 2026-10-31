## 2026-10-30 - JEG-1374 correction to JEG-1367: narrow the api view grants

Contract: the independent review of PR #1197 at c196cd6 found row policies and
jsonb grants wider than their views. Narrow them so anon reads exactly what
each view shows, and keep a view definer where that can't be done.

### Verified (check named)
- Findings 1 to 4 fixed: value_check_runs, weekly_dashboard_runs,
  weekly_dashboard_signals and players get no grant or policy (their views stay
  definer); the product_snapshot policy is now `is_active and publishable`.
  Check: `python3 -m unittest tests.test_jeg1367_api_invoker_migration`.
  The new direct-read check passes on this head. It fails on c196cd6, and on
  this head with the product_snapshot policy put back to `is_active`.
- Found while narrowing: api.player_values joins on
  consolidated_values.player_key, a column the view doesn't show. `player`
  differs from `player_key` on all 124,088 live rows (read-only SQL), so
  player_values stays definer too.
- Same rows per role through all 12 views before, after and after rollback;
  rollback restores the catalog exactly: same test, local Postgres 16 copy.

### Claimed, not confirmed
- Behaviour on the live Postgres 17 database: not applied; needs Jeremy's yes.
- The advisor clearing 6 ERRORs and 4 WARNs after apply (5 ERRORs remain).
