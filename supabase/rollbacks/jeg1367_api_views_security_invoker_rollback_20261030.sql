-- Rollback for supabase/migrations/jeg1367_api_views_security_invoker_20261030.sql
-- (JEG-1367). Puts back the state read on 2026-10-30 02:15 UTC: api views run
-- as their owner, the new read policies and column grants are gone,
-- authenticated has its table-wide SELECT on value_check_runs again, and the
-- 4 functions have no pinned search_path. Changes no data.
-- Run only on Jeremy's yes, from the main chat (apply_migration name:
-- jeg1367_rollback_20261030).

begin;

-- Part 2 back: owner rights.
alter view api.player_values            set (security_invoker = false);
alter view api.players                  set (security_invoker = false);
alter view api.product_options          set (security_invoker = false);
alter view api.product_snapshot         set (security_invoker = false);
alter view api.product_snapshot_history reset (security_invoker);
alter view api.source_freshness         reset (security_invoker);
alter view api.source_inputs_weekly     reset (security_invoker);
alter view api.source_input_weeks       reset (security_invoker);
alter view api.v_current_weekly_signals set (security_invoker = false);
alter view api.value_check_diff         reset (security_invoker);
alter view api.value_check_latest       reset (security_invoker);
alter view api.weekly_dashboard_status  set (security_invoker = false);

-- Part 1 back: policies and grants.
drop policy if exists anon_read_api_default_20261030 on public.product_options;
drop policy if exists anon_read_api_20261030 on public.value_check_values;
drop policy if exists authenticated_read_api_20261030 on public.value_check_values;
drop policy if exists anon_read_api_20261030 on public.value_check_runs;
drop policy if exists authenticated_read_api_20261030 on public.value_check_runs;
drop policy if exists anon_read_api_20261030 on public.players;
drop policy if exists anon_read_api_active_20261030 on public.product_snapshot;
drop policy if exists anon_read_api_20261030 on public.weekly_dashboard_runs;
drop policy if exists anon_read_api_current_20261030 on public.weekly_dashboard_signals;

revoke select (player, player_key, source, season, week, scoring, teams,
               qb_variant, view, value, detail_locator, bake_id)
  on public.consolidated_values from anon;
revoke select (product_key, contract_version, bench_share_default,
               bench_share_min, bench_share_max, bench_share_user_settable,
               default_scoring, default_teams, default_roster_shape,
               default_lock_order, default_view_mode, default_reference_source,
               default_position_weights, min_shared_for_pie,
               starter_markup_sane_band, peak_agreement_band, source_keys,
               adjusted_indexed_keys, pure_vorp_keys, as_published_keys)
  on public.product_options from anon;
revoke select (season, week, scoring, teams, roster, view, series, player_key,
               player, engine_value, reference_value, value_diff, agrees, held,
               run_id, updated_at)
  on public.value_check_values from anon;
revoke select (run_id, generated_at, season, week, verdict, tolerance,
               values_compared, disagreeing_sources, composite_disagreements,
               held_sections, fixture_built_at, github_run_id)
  on public.value_check_runs from anon, authenticated;
grant select on public.value_check_runs to authenticated;
revoke select (player_key, full_name, position, metadata, team_id)
  on public.players from anon;
revoke select (snapshot_id, contract_version, built_at, generated_at, is_active,
               publishable, bake_ids, value_weeks, sources, source_validation,
               espn_zeroed, methodology_combos, reference_freshness, health,
               pie_vintage_per_source, players_snapshot_at, context_meta)
  on public.product_snapshot from anon;
revoke select (run_id, season, week, created_at, source_manifest, is_current)
  on public.weekly_dashboard_runs from anon;
revoke select (run_id, player_key, position, team, signal, created_at)
  on public.weekly_dashboard_signals from anon;

-- Part 3 back.
alter function public.weekly_fantasypros_raw_append_only() reset search_path;
alter function public.weekly_fantasypros_batches_guard()   reset search_path;
alter function public.weekly_fantasypros_pages_guard()     reset search_path;
alter function public.value_check_prune(interval)          reset search_path;

commit;

notify pgrst, 'reload schema';
