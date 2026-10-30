-- JEG-1367 fixture: a local copy of the live objects the api.* views read,
-- with the live grants, RLS state and policies, read from project
-- iskiybsimubiujwuchsl on 2026-10-30 02:15 UTC (pg_class.relacl,
-- pg_policies, pg_get_viewdef). Synthetic rows only. Used by
-- tests/test_jeg1367_api_invoker_migration.py against a throwaway Postgres (JEG-1367, JEG-1374).
-- api.v_current_weekly_signals keeps 4 of its 33 signal ->> columns: access
-- depends on the tables and filters, not on how many keys are read.

create role anon nologin;
create role authenticated nologin;
create role service_role nologin bypassrls;
create schema api;
grant usage on schema api, public to anon, authenticated, service_role;
set search_path = public;

create table public.cbs_ros_projections (id uuid, player_key integer, player_norm text, ros_standard numeric, ros_half_ppr numeric, ros_ppr numeric, per_game_standard numeric, per_game_half_ppr numeric, per_game_ppr numeric, gp numeric, receptions numeric, raw_stats jsonb, cbs_snapshot_date date, pulled_at timestamp with time zone, scoring text, season integer, week integer, source_content_date date, created_at timestamp with time zone, _run_id text, _writer_identity text, _written_at timestamp with time zone);
create table public.cbs_trade_values (id uuid, source text, variant text, player_key bigint, player_norm text, scoring text, league_teams integer, qb_slots integer, season integer, week integer, "position" text, team text, value double precision, native_value double precision, source_content_date date, pulled_at timestamp with time zone, bake_id text, created_at timestamp with time zone, _writer_identity text, _run_id text, _written_at timestamp with time zone, source_url text);
create table public.consolidated_values (player text, source text, season integer, week integer, scoring text, teams integer, qb_variant text, view text, value numeric, detail_locator text, bake_id text, created_at timestamp with time zone, player_key bigint, bake_uuid uuid, source_generated_at timestamp with time zone);
create table public.espn_season_projections (id uuid, player_key bigint, player_norm text, season integer, week integer, scoring text, r_pass_yds double precision, r_pass_tds double precision, r_rush_yds double precision, r_rush_tds double precision, r_receptions double precision, r_rec_yds double precision, r_rec_tds double precision, ros_half_ppr double precision, weeks_covered text, espn_snapshot_date date, pulled_at timestamp with time zone, created_at timestamp with time zone, _writer_identity text, _run_id text, _written_at timestamp with time zone);
create table public.player_ppg_legs (player_key bigint, bake_id text, espn_ppg jsonb, rz_ppg jsonb, cbsros_ppg jsonb, agent_ranking_ppg jsonb, blend_ppg jsonb, games_remaining integer, computed_at timestamp with time zone);
create table public.player_values_tier_prices (player text, source text, season integer, week integer, scoring text, teams integer, qb_variant text, view text, tier_price_vector jsonb, tier_price_vintage text, bake_id text, created_at timestamp with time zone);
create table public.players (id uuid, league_id uuid, team_id uuid, full_name text, "position" text, active boolean, metadata jsonb, player_key bigint);
create table public.product_options (product_key text, contract_version text, bench_share_default numeric, bench_share_min numeric, bench_share_max numeric, bench_share_user_settable boolean, default_scoring text, default_teams integer, default_roster_shape jsonb, default_lock_order text, default_view_mode text, default_reference_source text, default_position_weights jsonb, min_shared_for_pie integer, starter_markup_sane_band numeric[], peak_agreement_band numeric[], source_keys text[], adjusted_indexed_keys text[], pure_vorp_keys text[], as_published_keys text[], inserted_at timestamp with time zone, updated_at timestamp with time zone);
create table public.product_snapshot (snapshot_id uuid, contract_version text, built_at timestamp with time zone, is_active boolean, value_weeks jsonb, sources jsonb, source_validation jsonb, espn_zeroed integer[], methodology_combos jsonb, reference_freshness jsonb, health jsonb, pie_vintage_per_source jsonb, players_snapshot_at timestamp with time zone, context_meta jsonb, inserted_at timestamp with time zone, publishable boolean, generated_at timestamp with time zone, bake_ids jsonb);
create table public.razzball_projections (id uuid, player_key integer, player_norm text, pos text, team text, health text, games_reported numeric, per_game_standard numeric, per_game_half_ppr numeric, per_game_ppr numeric, raw_stats jsonb, razzball_snapshot_date date, pulled_at timestamp with time zone, scoring text, season integer, week integer, source_content_date date, created_at timestamp with time zone, _run_id text, _writer_identity text, _written_at timestamp with time zone);
create table public.source_trade_values (id uuid, source text, player_norm text, player_id uuid, "position" text, team text, scoring text, league_teams integer, qb_slots integer, season integer, week integer, variant text, value numeric, native_value numeric, source_content_date date, pulled_at timestamp with time zone, bake_id text, created_at timestamp with time zone, player_key bigint, _writer_identity text, _run_id text, _written_at timestamp with time zone, source_url text);
create table public.teams (id uuid, league_id uuid, abbreviation text, name text, city text);
create table public.value_check_runs (run_id uuid, generated_at timestamp with time zone, season integer, week integer, verdict text, tolerance numeric, values_compared bigint, disagreeing_sources text[], composite_disagreements text[], held_sections jsonb, fixture_built_at text, github_run_id text, report jsonb, created_at timestamp with time zone);
create table public.value_check_values (season integer, week integer, scoring text, teams integer, roster text, view text, series text, player_key bigint, player text, engine_value numeric, reference_value numeric, value_diff numeric, agrees boolean, held boolean, run_id uuid, updated_at timestamp with time zone);
create table public.weekly_dashboard_runs (run_id uuid, week integer, season integer, created_at timestamp with time zone, source_manifest jsonb, is_current boolean);
create table public.weekly_dashboard_signals (run_id uuid, player_key text, "position" text, team text, signal jsonb, created_at timestamp with time zone);

create function public.nfl_content_week(d date) returns integer language sql immutable set search_path to '' as $$
  select case
    when d is null then null
    when d < date '2026-09-08' then 1
    else least(greatest(((d - date '2026-09-08') / 7) + 1, 1), 18)
  end
$$;

-- The four advisor functions (bodies as live).
create function public.value_check_prune(keep interval) returns bigint language plpgsql as $$
declare n bigint;
begin
  delete from public.value_check_values where updated_at < now() - keep;
  get diagnostics n = row_count;
  return n;
end;
$$;
create function public.weekly_fantasypros_raw_append_only() returns trigger language plpgsql as $$
begin raise exception 'weekly_fantasypros_raw is append-only (%).', tg_op; end;
$$;
create function public.weekly_fantasypros_batches_guard() returns trigger language plpgsql as $$
begin if tg_op = 'DELETE' then raise exception 'append-only'; end if; return new; end;
$$;
create function public.weekly_fantasypros_pages_guard() returns trigger language plpgsql as $$
begin if tg_op = 'DELETE' then raise exception 'append-only'; end if; return new; end;
$$;

-- RLS: on everywhere, never forced (as live).
do $$ declare t record; begin
  for t in select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace
           where n.nspname = 'public' and c.relkind = 'r' loop
    execute format('alter table public.%I enable row level security', t.relname);
  end loop; end $$;

-- Table grants (relacl as live). "m" (MAINTAIN) is left out: it reads nothing.
grant select on cbs_ros_projections, cbs_trade_values, espn_season_projections, player_ppg_legs,
  player_values_tier_prices, razzball_projections, source_trade_values, teams to anon;
grant select on cbs_ros_projections, cbs_trade_values, consolidated_values, espn_season_projections,
  player_ppg_legs, player_values_tier_prices, players, product_options, product_snapshot,
  razzball_projections, source_trade_values, teams, value_check_runs, value_check_values,
  weekly_dashboard_runs, weekly_dashboard_signals to authenticated;
grant all on all tables in schema public to service_role;

-- Policies (pg_policies as live).
do $$ declare t text; begin
  foreach t in array array['cbs_ros_projections','cbs_trade_values','espn_season_projections','player_ppg_legs',
                           'player_values_tier_prices','razzball_projections','source_trade_values','teams'] loop
    execute format('create policy anon_read_20261008 on public.%I for select to anon using (true)', t);
  end loop;
  foreach t in array array['cbs_ros_projections','cbs_trade_values','espn_season_projections','player_ppg_legs',
                           'player_values_tier_prices','razzball_projections','source_trade_values','teams',
                           'players','product_options','product_snapshot'] loop
    execute format('create policy authenticated_read_20261008 on public.%I for select to authenticated using (true)', t);
  end loop; end $$;
create policy consolidated_values_public_read on public.consolidated_values for select to public using (true);
create policy weekly_dashboard_runs_service_read on public.weekly_dashboard_runs for select to service_role using (true);
create policy weekly_dashboard_signals_service_read on public.weekly_dashboard_signals for select to service_role using (true);

-- Views (pg_get_viewdef and reloptions as live).
create view api.player_values with (security_invoker = false, security_barrier = true) as
 SELECT cv.player AS player_key, cv.source, cv.season, cv.week, cv.scoring, cv.teams, cv.qb_variant, cv.view, cv.value,
        CASE
            WHEN ((cv.view = 'combo_reindexed'::text) AND (cv.source IN ( SELECT unnest(po.as_published_keys) AS unnest
               FROM product_options po
              WHERE (po.product_key = 'default'::text)))) THEN 'indexed'::text
            WHEN (cv.view = 'combo_reindexed'::text) THEN 'ddf_translated'::text
            WHEN (cv.view = 'vorp'::text) THEN 'vorp'::text
            WHEN (cv.view = 'vorp_indexed'::text) THEN 'vorp_indexed'::text
            WHEN (cv.view = 'adj_values'::text) THEN 'adj'::text
            ELSE 'native'::text
        END AS value_provenance,
        CASE
            WHEN (cv.source = ANY (ARRAY['espn'::text, 'cbsros'::text, 'razzball'::text])) THEN 'model'::text
            ELSE 'published'::text
        END AS model_vs_published,
    cv.detail_locator, cv.bake_id, NULL::numeric AS index_total, NULL::text AS pie_vintage,
    tpv.tier_price_vector, tpv.tier_price_vintage,
        CASE
            WHEN (cv.view = 'combo_reindexed'::text) THEN 'full'::text
            WHEN ((cv.view = ANY (ARRAY['vorp'::text, 'vorp_indexed'::text, 'adj_values'::text])) AND (cv.scoring = 'full'::text) AND (cv.teams = 12) AND (cv.qb_variant = 'none'::text) AND (cv.source = ANY (ARRAY['espn'::text, 'cbsros'::text, 'razzball'::text, 'usatoday'::text, 'fantasycalc'::text, 'fantasypros'::text, 'cbs'::text, 'fantasycalc_adjusted'::text, 'usatoday_adjusted'::text, 'fantasypros_adjusted'::text, 'cbs_adjusted'::text]))) THEN 'full'::text
            WHEN ((cv.view = ANY (ARRAY['vorp'::text, 'vorp_indexed'::text, 'adj_values'::text])) AND (cv.scoring = 'full'::text) AND (cv.teams = 12) AND (cv.qb_variant = 'none'::text)) THEN 'view_limited_source'::text
            WHEN (cv.view = ANY (ARRAY['vorp'::text, 'vorp_indexed'::text, 'adj_values'::text])) THEN 'view_limited_combo'::text
            ELSE 'full'::text
        END AS coverage_class,
    vc.engine_value, vc.reference_value, vc.value_diff
   FROM ((consolidated_values cv
     LEFT JOIN player_values_tier_prices tpv ON (((tpv.player = cv.player) AND (tpv.source = cv.source) AND (tpv.season = cv.season) AND (tpv.week = cv.week) AND (tpv.scoring = cv.scoring) AND (tpv.teams = cv.teams) AND (tpv.qb_variant = cv.qb_variant) AND (tpv.view = cv.view))))
     LEFT JOIN value_check_values vc ON (((vc.player_key = cv.player_key) AND (vc.series = cv.source) AND (vc.season = cv.season) AND (vc.week = cv.week) AND (vc.scoring = cv.scoring) AND (vc.teams = cv.teams) AND (vc.roster = 'standard'::text) AND (vc.view =
        CASE cv.view
            WHEN 'combo_reindexed'::text THEN 'indexed'::text
            WHEN 'vorp'::text THEN 'vorp'::text
            WHEN 'adj_values'::text THEN 'adj'::text
            ELSE NULL::text
        END))))
UNION ALL
 SELECT vc.player AS player_key, 'ddf_value'::text AS source, vc.season, vc.week, vc.scoring, vc.teams, 'none'::text AS qb_variant,
        CASE vc.view
            WHEN 'indexed'::text THEN 'combo_reindexed'::text
            WHEN 'vorp'::text THEN 'vorp'::text
            ELSE 'adj_values'::text
        END AS view,
    vc.engine_value AS value, 'ddf_composite'::text AS value_provenance, 'model'::text AS model_vs_published,
    'value_check:ddf_value'::text AS detail_locator, (vc.run_id)::text AS bake_id, NULL::numeric AS index_total,
    NULL::text AS pie_vintage, NULL::jsonb AS tier_price_vector, NULL::text AS tier_price_vintage, 'full'::text AS coverage_class,
    vc.engine_value, vc.reference_value, vc.value_diff
   FROM value_check_values vc
  WHERE ((vc.series = 'ddf_value'::text) AND (vc.roster = 'standard'::text) AND (vc.engine_value IS NOT NULL));

create view api.players with (security_invoker = false, security_barrier = true) as
 SELECT p.player_key, p.full_name AS canonical_name, p."position" AS pos,
    COALESCE((p.metadata ->> 'team'::text), t.abbreviation) AS team,
    (p.player_key IN ( SELECT unnest(s.espn_zeroed) AS unnest
           FROM product_snapshot s
          WHERE (s.is_active = true)
         LIMIT 1)) AS ir_zeroed,
    (p."position" = ANY (ARRAY['K'::text, 'DST'::text])) AS kdst_excluded_from_chart,
    ppg.espn_ppg, ppg.rz_ppg, ppg.cbsros_ppg, ppg.agent_ranking_ppg, ppg.blend_ppg, ppg.games_remaining
   FROM ((players p
     LEFT JOIN teams t ON ((t.id = p.team_id)))
     LEFT JOIN player_ppg_legs ppg ON ((ppg.player_key = p.player_key)));

create view api.product_options with (security_invoker = false, security_barrier = true) as
 SELECT product_key, contract_version,
    jsonb_build_object('default', bench_share_default, 'min', bench_share_min, 'max', bench_share_max, 'user_settable', bench_share_user_settable) AS bench_share,
    bench_share_default, bench_share_min, bench_share_max, bench_share_user_settable, default_scoring, default_teams,
    default_roster_shape, default_lock_order, default_view_mode, default_reference_source, default_position_weights,
    min_shared_for_pie, starter_markup_sane_band, peak_agreement_band, source_keys, adjusted_indexed_keys,
    pure_vorp_keys, as_published_keys
   FROM product_options
  WHERE (product_key = 'default'::text);

create view api.product_snapshot with (security_invoker = false, security_barrier = true) as
 SELECT snapshot_id, contract_version, built_at, generated_at, is_active, publishable, bake_ids, value_weeks, sources,
    source_validation, espn_zeroed, methodology_combos, reference_freshness, health, pie_vintage_per_source,
    players_snapshot_at, context_meta
   FROM product_snapshot
  WHERE ((is_active = true) AND (publishable = true));

create view api.product_snapshot_history as
 SELECT snapshot_id, contract_version, is_active, publishable, generated_at, bake_ids, source_validation, context_meta
   FROM product_snapshot
  ORDER BY generated_at DESC;

create view api.source_freshness as
 WITH saved AS (
         SELECT source_trade_values.source, source_trade_values.week, source_trade_values.source_content_date, source_trade_values.pulled_at
           FROM source_trade_values WHERE (source_trade_values.season = 2026)
        UNION ALL
         SELECT 'cbs'::text, cbs_trade_values.week, cbs_trade_values.source_content_date, cbs_trade_values.pulled_at
           FROM cbs_trade_values WHERE (cbs_trade_values.season = 2026)
        UNION ALL
         SELECT 'cbsros'::text, cbs_ros_projections.week, cbs_ros_projections.source_content_date, cbs_ros_projections.pulled_at
           FROM cbs_ros_projections WHERE (cbs_ros_projections.season = 2026)
        UNION ALL
         SELECT 'razzball'::text, razzball_projections.week, razzball_projections.source_content_date, razzball_projections.pulled_at
           FROM razzball_projections WHERE (razzball_projections.season = 2026)
        UNION ALL
         SELECT 'espn'::text, nfl_content_week(espn_season_projections.espn_snapshot_date) AS nfl_content_week,
            espn_season_projections.espn_snapshot_date, espn_season_projections.pulled_at
           FROM espn_season_projections WHERE (espn_season_projections.season = 2026)
        ), latest AS (
         SELECT saved.source, max(saved.week) AS latest_week FROM saved GROUP BY saved.source
        ), today AS (
         SELECT ((now() AT TIME ZONE 'America/New_York'::text))::date AS d
        )
 SELECT l.source, l.latest_week, max(s.source_content_date) AS latest_content_date, max(s.pulled_at) AS latest_pulled_at,
    count(*) AS latest_week_rows, nfl_content_week(t.d) AS current_content_week,
        CASE
            WHEN (l.latest_week IS NULL) THEN 'unknown'::text
            WHEN (l.latest_week >= nfl_content_week(t.d)) THEN 'current'::text
            ELSE 'older'::text
        END AS status,
    ((l.latest_week IS NOT NULL) AND (l.latest_week < nfl_content_week(t.d))) AS is_older_week,
    GREATEST((nfl_content_week(t.d) - l.latest_week), 0) AS weeks_behind,
    'content_week_tuesday_flip'::text AS calendar, 'pipelines/nfl_week.py'::text AS calendar_source
   FROM ((latest l JOIN saved s ON (((s.source = l.source) AND (s.week = l.latest_week)))) CROSS JOIN today t)
  GROUP BY l.source, l.latest_week, t.d;

create view api.source_inputs_weekly as
 WITH raw AS (
         SELECT source_trade_values.source, source_trade_values.week, source_trade_values.season, source_trade_values.player_key,
            source_trade_values.player_norm, source_trade_values."position", source_trade_values.team,
                CASE source_trade_values.scoring
                    WHEN 'std'::text THEN 'standard'::text WHEN 'standard'::text THEN 'standard'::text
                    WHEN 'half'::text THEN 'half'::text WHEN 'half_ppr'::text THEN 'half'::text
                    WHEN 'full'::text THEN 'full'::text WHEN 'ppr'::text THEN 'full'::text
                    ELSE NULL::text
                END AS scoring,
            (source_trade_values.native_value)::double precision AS native_value, (source_trade_values.value)::double precision AS value,
            source_trade_values.source_content_date, source_trade_values.pulled_at, source_trade_values.bake_id
           FROM source_trade_values
          WHERE ((source_trade_values.league_teams = 12) AND (source_trade_values.qb_slots = 1) AND (COALESCE(source_trade_values.variant, 'as_published'::text) = 'as_published'::text) AND (source_trade_values.source = ANY (ARRAY['fantasycalc'::text, 'fantasypros'::text, 'usatoday'::text])))
        UNION ALL
         SELECT 'cbs'::text, cbs_trade_values.week, cbs_trade_values.season, cbs_trade_values.player_key, cbs_trade_values.player_norm,
            cbs_trade_values."position", cbs_trade_values.team,
                CASE cbs_trade_values.scoring
                    WHEN 'std'::text THEN 'standard'::text WHEN 'standard'::text THEN 'standard'::text
                    WHEN 'half'::text THEN 'half'::text WHEN 'half_ppr'::text THEN 'half'::text
                    WHEN 'full'::text THEN 'full'::text WHEN 'ppr'::text THEN 'full'::text
                    ELSE NULL::text
                END AS "case",
            cbs_trade_values.native_value, cbs_trade_values.value, cbs_trade_values.source_content_date, cbs_trade_values.pulled_at, cbs_trade_values.bake_id
           FROM cbs_trade_values
          WHERE ((cbs_trade_values.league_teams = 12) AND (COALESCE(cbs_trade_values.qb_slots, 1) = 1) AND (COALESCE(cbs_trade_values.variant, 'as_published'::text) = 'as_published'::text))
        ), pulls AS (
         SELECT d.source, d.season, d.week, d.scoring, d.pulled_at, d.bake_id,
            row_number() OVER (PARTITION BY d.source, d.season, d.week, d.scoring ORDER BY d.pulled_at DESC, d.bake_id DESC NULLS LAST) AS rn
           FROM ( SELECT DISTINCT raw.source, raw.season, raw.week, raw.scoring, raw.pulled_at, raw.bake_id FROM raw) d
        ), latest_week AS (
         SELECT raw.source, raw.season, max(raw.week) AS max_week FROM raw GROUP BY raw.source, raw.season
        )
 SELECT r.source, r.season, r.week, (lw.max_week - r.week) AS weeks_back_from_latest,
    (nfl_content_week(((now() AT TIME ZONE 'America/New_York'::text))::date) - r.week) AS weeks_back_from_content_week,
    r.scoring, 12 AS teams, 1 AS qb_slots, r.player_key, r.player_norm, r."position", r.team, r.native_value, r.value,
    r.source_content_date, r.pulled_at, r.bake_id
   FROM ((raw r
     JOIN pulls p ON (((p.rn = 1) AND (p.source = r.source) AND (p.season = r.season) AND (p.week = r.week) AND (p.scoring = r.scoring) AND (p.pulled_at = r.pulled_at) AND (NOT (p.bake_id IS DISTINCT FROM r.bake_id)))))
     JOIN latest_week lw ON (((lw.source = r.source) AND (lw.season = r.season))));

create view api.source_input_weeks as
 SELECT source, season, week, weeks_back_from_latest, weeks_back_from_content_week, scoring, count(*) AS players,
    count(player_key) AS players_keyed, min(pulled_at) AS pulled_at, min(bake_id) AS bake_id, max(source_content_date) AS source_content_date
   FROM api.source_inputs_weekly
  GROUP BY source, season, week, weeks_back_from_latest, weeks_back_from_content_week, scoring;

create view api.v_current_weekly_signals with (security_invoker = false, security_barrier = true) as
 SELECT r.season, r.week, r.run_id, r.created_at AS run_created_at,
    (COALESCE((r.source_manifest ->> 'bundle_built_at'::text), (r.source_manifest ->> 'built_at'::text)))::timestamp with time zone AS bundle_built_at,
    s.player_key, s."position", s.team, (s.signal ->> 'name'::text) AS name, (s.signal ->> 'direction'::text) AS direction,
    (s.signal ->> 'delta'::text) AS delta, (s.signal ->> 'injury_note'::text) AS injury_note, s.created_at AS signal_created_at
   FROM (weekly_dashboard_runs r JOIN weekly_dashboard_signals s ON ((s.run_id = r.run_id)))
  WHERE r.is_current;

create view api.value_check_diff with (security_barrier = true) as
 SELECT season, week, scoring, teams, roster, view, series, player_key, player, engine_value, reference_value, value_diff,
    abs(value_diff) AS abs_diff, agrees, held, run_id, updated_at
   FROM value_check_values v;

create view api.value_check_latest with (security_barrier = true) as
 SELECT run_id, generated_at, season, week, verdict, tolerance, values_compared, disagreeing_sources, composite_disagreements,
    held_sections, fixture_built_at, github_run_id
   FROM value_check_runs
  ORDER BY generated_at DESC
 LIMIT 1;

create view api.weekly_dashboard_status with (security_invoker = false, security_barrier = true) as
 SELECT max(created_at) FILTER (WHERE is_current) AS run_created_at,
    (COALESCE(max((source_manifest ->> 'bundle_built_at'::text)) FILTER (WHERE is_current), max((source_manifest ->> 'built_at'::text)) FILTER (WHERE is_current)))::timestamp with time zone AS bundle_built_at,
    (max(created_at) FILTER (WHERE is_current) IS NOT NULL) AS has_current,
    max(season) FILTER (WHERE is_current) AS season,
    max(week) FILTER (WHERE is_current) AS week,
    COALESCE(sum(( SELECT count(*) AS count FROM weekly_dashboard_signals s WHERE (s.run_id = r.run_id))) FILTER (WHERE is_current), (0)::numeric) AS signal_count,
    ( SELECT count(*) AS count FROM weekly_dashboard_runs r2 WHERE r2.is_current) AS current_run_count,
    max(created_at) AS latest_run_created_at
   FROM weekly_dashboard_runs r;

-- View grants (relacl as live).
grant select on api.player_values, api.players, api.product_options, api.product_snapshot,
  api.source_freshness, api.source_input_weeks, api.source_inputs_weekly, api.v_current_weekly_signals,
  api.value_check_diff, api.value_check_latest, api.weekly_dashboard_status to anon;
grant select on api.value_check_diff, api.value_check_latest to authenticated;
grant select on api.source_freshness, api.source_input_weeks, api.source_inputs_weekly, api.v_current_weekly_signals,
  api.value_check_diff, api.value_check_latest, api.weekly_dashboard_status to service_role;

-- Synthetic rows: enough that every filter in every view keeps some rows and
-- drops others (an inactive snapshot, a non-default product, an old run).
insert into teams values ('00000000-0000-0000-0000-0000000000a1', null, 'SEA', 'Seahawks', 'Seattle');
insert into players values
  (gen_random_uuid(), null, '00000000-0000-0000-0000-0000000000a1', 'Jaxon Smith-Njigba', 'WR', true, '{"sleeper_id":"9488"}', 101),
  (gen_random_uuid(), null, null, 'Kicker Guy', 'K', true, '{"team":"DAL"}', 102),
  (gen_random_uuid(), null, null, 'Hurt Back', 'RB', true, '{}', 103);
insert into player_ppg_legs values (101, 'b1', '{"ppg":15.1}', null, null, null, null, 9, now());
insert into product_snapshot (snapshot_id, contract_version, is_active, publishable, espn_zeroed, generated_at, health) values
  (gen_random_uuid(), 'v1', true, true, '{103}', now(), '{"ok":true}'),
  (gen_random_uuid(), 'v0', false, false, '{101}', now() - interval '1 day', '{"ok":false}'),
  -- active but not publishable: api.product_snapshot hides it; same
  -- espn_zeroed as the live row so api.players' LIMIT 1 pick is stable.
  (gen_random_uuid(), 'v2', true, false, '{103}', now() - interval '1 hour', '{"ok":"draft"}');
insert into product_options (product_key, contract_version, bench_share_default, as_published_keys, source_keys) values
  ('default', 'v1', 0.2, '{fantasycalc}', '{fantasycalc,cbs}'),
  ('experiment', 'v1', 0.5, '{cbs}', '{cbs}');
insert into consolidated_values (player, source, season, week, scoring, teams, qb_variant, view, value, player_key, bake_id) values
  ('101', 'fantasycalc', 2026, 9, 'full', 12, 'none', 'combo_reindexed', 71.4, 101, 'b1'),
  ('101', 'cbs', 2026, 9, 'full', 12, 'none', 'combo_reindexed', 69.0, 101, 'b1'),
  ('103', 'espn', 2026, 9, 'full', 12, 'none', 'vorp', 5.4, 103, 'b1');
insert into player_values_tier_prices values ('101', 'fantasycalc', 2026, 9, 'full', 12, 'none', 'combo_reindexed', '[1,2]', 'w9', 'b1', now());
insert into value_check_values values
  (2026, 9, 'full', 12, 'standard', 'indexed', 'fantasycalc', 101, '101', 71.4, 71.4, 0, true, false, '00000000-0000-0000-0000-0000000000c1', now()),
  (2026, 9, 'full', 12, 'standard', 'indexed', 'ddf_value', 101, '101', 70.2, 70.2, 0, true, false, '00000000-0000-0000-0000-0000000000c1', now());
insert into value_check_runs values
  ('00000000-0000-0000-0000-0000000000c1', now(), 2026, 9, 'pass', 0.05, 2, '{}', '{}', '{}', 'x', '1', '{"secret_detail":1}', now()),
  ('00000000-0000-0000-0000-0000000000c0', now() - interval '1 day', 2026, 8, 'pass', 0.05, 2, '{}', '{}', '{}', 'x', '0', null, now());
insert into weekly_dashboard_runs values
  ('00000000-0000-0000-0000-0000000000d1', 9, 2026, now(), '{"bundle_built_at":"2026-10-29T12:00:00Z"}', true),
  ('00000000-0000-0000-0000-0000000000d0', 8, 2026, now() - interval '7 days', '{"built_at":"2026-10-22T12:00:00Z"}', false);
insert into weekly_dashboard_signals values
  ('00000000-0000-0000-0000-0000000000d1', '101', 'WR', 'SEA', '{"name":"JSN","direction":"up","delta":"2"}', now()),
  ('00000000-0000-0000-0000-0000000000d0', '103', 'RB', 'SEA', '{"name":"old","direction":"down","delta":"-1"}', now());
insert into source_trade_values (source, season, week, scoring, league_teams, qb_slots, value, native_value, player_key, pulled_at, source_content_date, bake_id) values
  ('fantasycalc', 2026, 9, 'ppr', 12, 1, 71.4, 7140, 101, now(), current_date, 'b1');
insert into cbs_trade_values (source, season, week, scoring, league_teams, qb_slots, value, native_value, player_key, pulled_at, source_content_date, bake_id) values
  ('cbs', 2026, 9, 'ppr', 12, 1, 22, 22, 101, now(), current_date, 'b1');
insert into cbs_ros_projections (season, week, player_key, pulled_at, source_content_date) values (2026, 9, 101, now(), current_date);
insert into razzball_projections (season, week, player_key, pulled_at, source_content_date) values (2026, 9, 101, now(), current_date);
insert into espn_season_projections (season, player_key, espn_snapshot_date, pulled_at) values (2026, 101, current_date, now());
