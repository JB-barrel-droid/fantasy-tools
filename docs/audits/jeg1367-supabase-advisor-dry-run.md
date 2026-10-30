# JEG-1367 dry run: api views to security_invoker, 4 functions pinned

Not applied. Migration: `supabase/migrations/jeg1367_api_views_security_invoker_20261030.sql`
(apply_migration name `jeg1367_api_views_security_invoker_20261030`). Rollback:
`supabase/rollbacks/jeg1367_api_views_security_invoker_rollback_20261030.sql`.
Read-only inputs: Supabase security advisor, catalog reads and edge logs on project
`iskiybsimubiujwuchsl`, 2026-10-30 02:15 to 02:40 UTC.

## Answer

After the migration every role sees the same rows through every api view, and the
advisor's 11 ERRORs and 4 WARNs for these objects should clear. No data, values or
view definitions change. A local Postgres copy of the live objects shows this
(`tests/test_jeg1367_api_invoker_migration.py`). The trade-off: anon gets new direct
SELECT on 8 base tables, limited to the columns and rows the views already show, with
three jsonb columns exposed whole (see Risk).

## What the advisor flagged

| Lint | Objects | This migration |
| -- | -- | -- |
| ERROR security_definer_view | 11 api views | flipped to `security_invoker = true` (plus `api.product_snapshot_history`, same default, no grants) |
| WARN function_search_path_mutable | `weekly_fantasypros_raw_append_only`, `weekly_fantasypros_batches_guard`, `weekly_fantasypros_pages_guard`, `value_check_prune` | `set search_path = public, pg_temp` |
| WARN extension_in_public | pg_net | unchanged (not relocatable; 2026-10-08 lockdown note) |
| INFO rls_enabled_no_policy | 26 tables | unchanged (service-role-only by design) |

## Who reads each view

No edge function touches the database: get-values and mcp fetch the published site
files. The static site does not call Supabase (the "api.players" names in
`app/trade-value-chart/assets/*.js` are the contract shape built from the bundle).
Edge logs for 2026-10-25, 10-28 and 10-29 show no anon or authenticated request to any
api view. Postgres-side readers run as postgres (owner, bypasses RLS).

| View | Readers today | Base tables | What anon needed (added) |
| -- | -- | -- | -- |
| api.player_values | anon grant; no logged use | consolidated_values, product_options, player_values_tier_prices, value_check_values | column grants on consolidated_values, product_options, value_check_values; policies on product_options (`product_key = 'default'`) and value_check_values |
| api.players | anon grant; no logged use | players, teams, player_ppg_legs, product_snapshot | column grants on players, product_snapshot; policies `true` on players, `is_active` on product_snapshot |
| api.product_options | anon grant | product_options | covered above |
| api.product_snapshot | anon grant; `ops.resolve_active_snapshot_uuid` (runs as postgres) | product_snapshot | covered above |
| api.source_freshness | anon, service_role | five source tables | nothing; anon already reads them |
| api.source_inputs_weekly | anon, service_role | source_trade_values, cbs_trade_values | nothing |
| api.source_input_weeks | anon, service_role | api.source_inputs_weekly | nothing |
| api.v_current_weekly_signals | anon, service_role | weekly_dashboard_runs, weekly_dashboard_signals | column grants on both; policies `true` on runs, current runs only on signals |
| api.weekly_dashboard_status | anon, service_role (`scripts/check_weekly_freshness.py`) | same two | covered above |
| api.value_check_latest | anon, authenticated, service_role | value_check_runs | column grants (no `report`, `created_at`); policies for anon and authenticated; authenticated's table-wide grant narrowed to the same columns |
| api.value_check_diff | anon, authenticated, service_role | value_check_values | policies for anon and authenticated |

service_role bypasses RLS and keeps the grants it has; it is unchanged everywhere,
including the four views it cannot read today (players, player_values,
product_options, product_snapshot).

## Expected effect

- Rows through each view, per role: identical. Checked on the local copy, before,
  after and after rollback (row count plus md5 of every row, 12 views x 3 roles).
- Direct base-table reads by anon: new, but only the view columns. On the local copy
  anon is refused `players.id`, `consolidated_values.bake_uuid`,
  `value_check_runs.report` and `product_snapshot.inserted_at`, sees 1 of 2 snapshots,
  1 of 2 product rows and 1 of 2 signals. No write grant or write policy is added.
- authenticated: `value_check_runs.report` was never readable (RLS, no policy) and
  stays unreadable; the grant is narrowed before the policy is added.
- Functions: behaviour unchanged; bodies reference no unqualified table.
- Rollback: puts the catalog back exactly (reloptions, table and column ACLs,
  policies, function config compared on the local copy).
- Flipping the views without the grants (the comparison's own check): anon loses 8
  views and authenticated loses the value_check rows. So part 1 is what keeps access.

## Risk

- jsonb columns are granted whole, since a column grant cannot reach inside jsonb:
  `players.metadata` (team, gsis_id, sleeper ids, roster_status, merge notes),
  `weekly_dashboard_runs.source_manifest` (bundle path, loader, counts) and
  `weekly_dashboard_signals.signal` (about 12 keys beyond the 33 the view shows,
  such as game_id, kickoff, fds_projection_stats). All public football data, no user
  data. If that is not acceptable, the smaller option is to flip the views and add no
  grants: nobody reads these views with anon today, but anon would lose 8 views.
- Policy `is_active` on product_snapshot is wider than api.product_snapshot's
  `is_active and publishable` because api.players reads the active row's espn_zeroed.
  Live today: 1 snapshot, active and publishable.
- The local copy is Postgres 16; live is 17. security_invoker behaves the same in both.
- After applying, re-run `get_advisors` (security) and spot-check `api.players` and
  `api.weekly_dashboard_status` with the anon key.
