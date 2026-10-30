-- JEG-1367 (2026-10-30): clear the Supabase security advisor findings that the
-- 2026-10-08 lockdown left open, where that can be done without letting any
-- role read more than it reads today. NOT APPLIED by the authoring session:
-- Jeremy approves it, then the main chat applies it with apply_migration
-- (name: jeg1367_api_views_security_invoker_20261030).
-- Rollback: supabase/rollbacks/jeg1367_api_views_security_invoker_rollback_20261030.sql
-- Dry-run report: docs/audits/jeg1367-supabase-advisor-dry-run.md
--
-- What the advisor reported on 2026-10-30 02:15 UTC and what this does:
--
--   ERROR security_definer_view (11 api.* views)
--     6 flipped to security_invoker (parts 1 and 2): product_options,
--       product_snapshot, value_check_diff, source_freshness,
--       source_inputs_weekly, source_input_weeks
--     5 kept SECURITY DEFINER (JEG-1374 correction): a table grant and row
--       policy cannot match what they show, so a direct table read would
--       reach more than the view does:
--       api.players                  reads metadata ->> 'team' (jsonb) and the
--                                    active snapshot whether or not publishable
--       api.player_values            joins on consolidated_values.player_key,
--                                    a column the view does not show
--       api.v_current_weekly_signals reads keys of signal and source_manifest
--       api.weekly_dashboard_status  reads source_manifest of the current run
--       api.value_check_latest       shows the latest run only; a policy on
--                                    value_check_runs cannot say "latest"
--                                    without reading its own table
--   WARN  function_search_path_mutable (4)          -> part 3
--   WARN  extension_in_public (pg_net)              -> not changed (see the
--                                                      2026-10-08 lockdown)
--   INFO  rls_enabled_no_policy (26 tables)         -> not changed (intended
--                                                      service-role-only tables)
--
-- Rule for part 1: each new grant is limited to the columns the view shows,
-- and each new policy is the view's own row filter, so a direct read of the
-- base table returns exactly what the view returns. Every role keeps the same
-- rows through every view. tests/test_jeg1367_api_invoker_migration.py checks
-- both against a local Postgres copy of the objects.
--
-- Who reads the api views (2026-10-30): no edge function touches the database
-- (get-values and mcp read the published site files); the static site does
-- not call Supabase; pipelines and scripts use service_role, which bypasses
-- RLS and is unchanged; pg_cron runs as postgres, the table owner, which
-- bypasses RLS (not forced). Edge logs for 2026-10-25, 10-28 and 10-29 show
-- no anon or authenticated request to any api view.
--
-- No data, no values and no view definitions change.

begin;

-- ---------------------------------------------------------------------------
-- Part 1. Base-table reads the flipped views need once they run as the
-- caller. source_freshness, source_inputs_weekly and source_input_weeks need
-- nothing: anon already reads their base tables in full.
-- ---------------------------------------------------------------------------

-- api.product_options: every column of the 'default' row except
-- inserted_at/updated_at.
grant select (product_key, contract_version, bench_share_default,
              bench_share_min, bench_share_max, bench_share_user_settable,
              default_scoring, default_teams, default_roster_shape,
              default_lock_order, default_view_mode, default_reference_source,
              default_position_weights, min_shared_for_pie,
              starter_markup_sane_band, peak_agreement_band, source_keys,
              adjusted_indexed_keys, pure_vorp_keys, as_published_keys)
  on public.product_options to anon;
create policy anon_read_api_default_20261030 on public.product_options
  for select to anon using (product_key = 'default');

-- api.product_snapshot: the active, publishable row, every column except
-- inserted_at. (api.players also reads this table but stays definer.)
grant select (snapshot_id, contract_version, built_at, generated_at, is_active,
              publishable, bake_ids, value_weeks, sources, source_validation,
              espn_zeroed, methodology_combos, reference_freshness, health,
              pie_vintage_per_source, players_snapshot_at, context_meta)
  on public.product_snapshot to anon;
create policy anon_read_api_published_20261030 on public.product_snapshot
  for select to anon using (is_active = true and publishable = true);

-- api.value_check_diff: every row and every column. The table has RLS with no
-- policy today, so these are its first read policies. authenticated already
-- holds a table-wide SELECT grant and reads api.value_check_diff today.
grant select (season, week, scoring, teams, roster, view, series, player_key,
              player, engine_value, reference_value, value_diff, agrees, held,
              run_id, updated_at)
  on public.value_check_values to anon;
create policy anon_read_api_20261030 on public.value_check_values
  for select to anon using (true);
create policy authenticated_read_api_20261030 on public.value_check_values
  for select to authenticated using (true);

-- ---------------------------------------------------------------------------
-- Part 2. The 6 views run with the caller's rights. security_barrier stays.
-- api.product_snapshot_history is not in the advisor list (no anon or
-- authenticated grant) but has the same definer default; it is flipped too so
-- a later grant cannot reopen the hole. Only postgres reads it today.
-- ---------------------------------------------------------------------------
alter view api.product_options          set (security_invoker = true);
alter view api.product_snapshot         set (security_invoker = true);
alter view api.product_snapshot_history set (security_invoker = true);
alter view api.source_freshness         set (security_invoker = true);
alter view api.source_inputs_weekly     set (security_invoker = true);
alter view api.source_input_weeks       set (security_invoker = true);
alter view api.value_check_diff         set (security_invoker = true);

-- ---------------------------------------------------------------------------
-- Part 3. Pin search_path on the 4 functions the advisor named. Bodies read on
-- 2026-10-30: the three trigger guards reference no table; value_check_prune
-- deletes from public.value_check_values (schema-qualified). Same setting as
-- the 2026-10-08 lockdown.
-- ---------------------------------------------------------------------------
alter function public.weekly_fantasypros_raw_append_only() set search_path = public, pg_temp;
alter function public.weekly_fantasypros_batches_guard()   set search_path = public, pg_temp;
alter function public.weekly_fantasypros_pages_guard()     set search_path = public, pg_temp;
alter function public.value_check_prune(interval)          set search_path = public, pg_temp;

commit;

notify pgrst, 'reload schema';
