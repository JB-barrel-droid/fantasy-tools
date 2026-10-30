# JEG-1367 dry run: api views to security_invoker, 4 functions pinned

Not applied. Migration: `supabase/migrations/jeg1367_api_views_security_invoker_20261030.sql`
(apply_migration name `jeg1367_api_views_security_invoker_20261030`). Rollback:
`supabase/rollbacks/jeg1367_api_views_security_invoker_rollback_20261030.sql`.
Read-only inputs: Supabase security advisor, catalog reads and edge logs on project
`iskiybsimubiujwuchsl`, 2026-10-30 02:15 to 02:40 UTC. Revised for the JEG-1374
correction: the first head (c196cd6) let anon read more rows and jsonb directly than
the views show.

## Answer

After the migration every role sees the same rows through every api view, and no role
can read any table more widely than the view it serves. The advisor's 4 WARNs clear,
and 6 of its 11 ERRORs clear. The other 5 views stay SECURITY DEFINER for now, because
no table grant or row policy can match what they show. No data, values or view
definitions change. A local Postgres copy of the live objects shows this
(`tests/test_jeg1367_api_invoker_migration.py`).

## What the advisor flagged

| Lint | Objects | This migration |
| -- | -- | -- |
| ERROR security_definer_view | 11 api views | 6 flipped to `security_invoker = true` (plus `api.product_snapshot_history`, same default, no grants); 5 kept definer |
| WARN function_search_path_mutable | `weekly_fantasypros_raw_append_only`, `weekly_fantasypros_batches_guard`, `weekly_fantasypros_pages_guard`, `value_check_prune` | `set search_path = public, pg_temp` |
| WARN extension_in_public | pg_net | unchanged (not relocatable; 2026-10-08 lockdown note) |
| INFO rls_enabled_no_policy | 26 tables | unchanged (service-role-only by design) |

## Flipped: the grant and policy match the view exactly

| View | Readers today | What anon gets on the base table |
| -- | -- | -- |
| api.product_options | anon grant; no logged use | the view's 20 columns, policy `product_key = 'default'` (the view's filter) |
| api.product_snapshot | anon grant; `ops.resolve_active_snapshot_uuid` (runs as postgres) | the view's 17 columns, policy `is_active and publishable` (the view's filter) |
| api.value_check_diff | anon, authenticated, service_role | all 16 columns and rows, which is what the view shows; policies for anon and authenticated |
| api.source_freshness | anon, service_role | nothing new; anon already reads the five source tables |
| api.source_inputs_weekly | anon, service_role | nothing new |
| api.source_input_weeks | anon, service_role | nothing new |

## Kept SECURITY DEFINER, and why

| View | Why no grant and policy can match it |
| -- | -- |
| api.players | reads `metadata ->> 'team'`; a column grant would expose the whole metadata jsonb. It also reads the active snapshot's espn_zeroed whether or not that snapshot is publishable |
| api.player_values | joins on `consolidated_values.player_key`, which the view does not show (`player` is a different value on all 124,088 live rows) |
| api.v_current_weekly_signals | reads keys of `signal` and `source_manifest` (jsonb) |
| api.weekly_dashboard_status | reads `source_manifest` of the current run (jsonb) and aggregates over every run |
| api.value_check_latest | shows only the latest run, and a policy on value_check_runs cannot say "latest" without reading its own table |

These stay as the advisor's residual ERRORs. To clear them later, either the view
reads through a narrow helper (a SECURITY DEFINER function in an unexposed schema
returning only the shown fields), or the hidden data moves into its own columns.
Both change a view's definition, so they are out of scope here.

## Who reads each view

No edge function touches the database: get-values and mcp fetch the published site
files. The static site does not call Supabase (the "api.players" names in
`app/trade-value-chart/assets/*.js` are the contract shape built from the bundle).
Edge logs for 2026-10-25, 10-28 and 10-29 show no anon or authenticated request to any
api view. Postgres-side readers run as postgres (owner, bypasses RLS). service_role
bypasses RLS and keeps its grants; it is unchanged everywhere.

## Expected effect

- Rows through each view, per role: identical. Checked on the local copy, before,
  after and after rollback (row count plus md5 of every row, 12 views x 3 roles).
- Direct base-table reads: for each newly granted table, anon's read of the granted
  columns equals the view's own filter applied by the table owner, and every other
  column is refused. The fixture has a row each filter must drop: an active
  unpublishable snapshot, an inactive one, and a non-default product. The first head's
  `is_active` policy fails this check, and the narrowed one passes.
- Tables only the definer views need (players, consolidated_values,
  weekly_dashboard_runs, weekly_dashboard_signals, value_check_runs) get no new grant
  or policy; anon is refused on each.
- Functions: behaviour unchanged; bodies reference no unqualified table.
- Rollback: puts the catalog back exactly (reloptions, table and column ACLs,
  policies, function config compared on the local copy).

## Risk

- 5 ERRORs remain on the advisor until those views are redesigned (see above).
- The local copy is Postgres 16; live is 17. security_invoker behaves the same in both.
- After applying, re-run `get_advisors` (security), then spot-check
  `api.product_snapshot` and `api.value_check_diff` with the anon key.
