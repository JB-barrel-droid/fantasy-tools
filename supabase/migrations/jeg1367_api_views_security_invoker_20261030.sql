-- JEG-1367 (2026-10-30): clear the Supabase security advisor's ERROR and WARN
-- findings that the 2026-10-08 lockdown left open. NOT APPLIED by the
-- authoring session: Jeremy approves it, then the main chat applies it with
-- apply_migration (name: jeg1367_api_views_security_invoker_20261030).
-- Rollback: supabase/rollbacks/jeg1367_api_views_security_invoker_rollback_20261030.sql
-- Dry-run report: docs/audits/jeg1367-supabase-advisor-dry-run.md
--
-- What the advisor reported on 2026-10-30 02:15 UTC and what this does:
--
--   ERROR security_definer_view (11 api.* views)  -> parts 1 and 2
--   WARN  function_search_path_mutable (4)         -> part 3
--   WARN  extension_in_public (pg_net)             -> not changed (see the
--                                                     2026-10-08 lockdown)
--   INFO  rls_enabled_no_policy (26 tables)        -> not changed (intended
--                                                     service-role-only tables)
--
-- The 2026-10-08 lockdown kept the api.* views SECURITY DEFINER because
-- flipping them alone turns the curated surface off for anon: anon has no
-- grant or no policy on several base tables. Part 1 gives anon (and
-- authenticated, where it reads an api view today) exactly the base-table
-- reads the views need: column grants limited to the columns the views use,
-- and row policies that match the views' own filters. Part 2 then flips the
-- views to security_invoker. Every role keeps the same rows through every
-- view; tests/test_jeg1367_api_invoker_migration.py checks that against a
-- local Postgres copy of the objects.
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
-- Part 1. Base-table reads the api views need once they run as the caller.
-- Tables the views read that anon can already read in full keep their grants
-- and policies as they are (player_values_tier_prices, teams, player_ppg_legs,
-- source_trade_values, cbs_trade_values, cbs_ros_projections,
-- razzball_projections, espn_season_projections).
-- ---------------------------------------------------------------------------

-- api.player_values reads consolidated_values. Its existing policy
-- consolidated_values_public_read (to public, using true) already covers anon;
-- anon only lacks the grant.
grant select (player, player_key, source, season, week, scoring, teams,
              qb_variant, view, value, detail_locator, bake_id)
  on public.consolidated_values to anon;

-- api.product_options (and api.player_values' as_published_keys lookup) read
-- the 'default' row only.
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

-- api.player_values and api.value_check_diff read every value_check_values
-- row (all columns). The table has RLS with no policy today, so these are the
-- first read policies. authenticated already holds a table-wide SELECT grant
-- and reads api.value_check_diff today.
grant select (season, week, scoring, teams, roster, view, series, player_key,
              player, engine_value, reference_value, value_diff, agrees, held,
              run_id, updated_at)
  on public.value_check_values to anon;
create policy anon_read_api_20261030 on public.value_check_values
  for select to anon using (true);
create policy authenticated_read_api_20261030 on public.value_check_values
  for select to authenticated using (true);

-- api.value_check_latest reads value_check_runs without report/created_at.
-- authenticated reads that view today; its table-wide grant is narrowed to the
-- view's columns first, so the new policy opens no column the view hides
-- (today the grant reaches no rows at all: RLS on, no policy).
revoke select on public.value_check_runs from authenticated;
grant select (run_id, generated_at, season, week, verdict, tolerance,
              values_compared, disagreeing_sources, composite_disagreements,
              held_sections, fixture_built_at, github_run_id)
  on public.value_check_runs to anon, authenticated;
create policy anon_read_api_20261030 on public.value_check_runs
  for select to anon using (true);
create policy authenticated_read_api_20261030 on public.value_check_runs
  for select to authenticated using (true);

-- api.players reads every players row. metadata is granted whole because the
-- view reads metadata ->> 'team' (column grants cannot reach inside jsonb).
grant select (player_key, full_name, position, metadata, team_id)
  on public.players to anon;
create policy anon_read_api_20261030 on public.players
  for select to anon using (true);

-- api.product_snapshot shows the active, publishable row; api.players reads
-- espn_zeroed from the active row (publishable or not), so the policy is the
-- wider of the two filters: is_active.
grant select (snapshot_id, contract_version, built_at, generated_at, is_active,
              publishable, bake_ids, value_weeks, sources, source_validation,
              espn_zeroed, methodology_combos, reference_freshness, health,
              pie_vintage_per_source, players_snapshot_at, context_meta)
  on public.product_snapshot to anon;
create policy anon_read_api_active_20261030 on public.product_snapshot
  for select to anon using (is_active = true);

-- api.weekly_dashboard_status aggregates over every run; api.v_current_weekly_
-- signals and the status signal count read signals of current runs only.
grant select (run_id, season, week, created_at, source_manifest, is_current)
  on public.weekly_dashboard_runs to anon;
create policy anon_read_api_20261030 on public.weekly_dashboard_runs
  for select to anon using (true);
grant select (run_id, player_key, position, team, signal, created_at)
  on public.weekly_dashboard_signals to anon;
create policy anon_read_api_current_20261030 on public.weekly_dashboard_signals
  for select to anon using (
    exists (select 1 from public.weekly_dashboard_runs r
            where r.run_id = weekly_dashboard_signals.run_id and r.is_current));

-- ---------------------------------------------------------------------------
-- Part 2. The api views run with the caller's rights. security_barrier stays.
-- api.product_snapshot_history is not in the advisor list (no anon or
-- authenticated grant) but has the same definer default; it is flipped too so
-- a later grant cannot reopen the hole. Only postgres reads it today.
-- ---------------------------------------------------------------------------
alter view api.player_values            set (security_invoker = true);
alter view api.players                  set (security_invoker = true);
alter view api.product_options          set (security_invoker = true);
alter view api.product_snapshot         set (security_invoker = true);
alter view api.product_snapshot_history set (security_invoker = true);
alter view api.source_freshness         set (security_invoker = true);
alter view api.source_inputs_weekly     set (security_invoker = true);
alter view api.source_input_weeks       set (security_invoker = true);
alter view api.v_current_weekly_signals set (security_invoker = true);
alter view api.value_check_diff         set (security_invoker = true);
alter view api.value_check_latest       set (security_invoker = true);
alter view api.weekly_dashboard_status  set (security_invoker = true);

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
