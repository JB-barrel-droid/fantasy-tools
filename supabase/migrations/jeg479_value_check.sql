-- JEG-479 (Jeremy 2026-10-08): the math lives in two places on purpose -- the
-- browser engine and the Python reference (pipelines/value_reference.py) --
-- and every chain run diffs them (pipelines/value_check.py). This stores both
-- sides of every value the page shows, plus a diff view, and brings
-- api.player_values up to date:
--
--   public.value_check_runs    one row per chain comparison (verdict, report)
--   public.value_check_values  engine and reference value per (season, week,
--                              scoring, teams, roster, view, series, player);
--                              series include ddf_value and ddf_value_prior
--                              (the DDF Value's prior-week side)
--   api.value_check_latest     the newest run
--   api.value_check_diff       every stored value with its difference
--   api.player_values          + engine_value / reference_value / value_diff
--                              (standard roster, matching view), and the
--                              DDF Value rows (source 'ddf_value')
--   public.source_config       + razzball, ddf_value (FK targets)
--
-- Additive only: new tables, new views, two config rows, and api.player_values
-- replaced with the same columns in the same order plus three appended ones.
-- Writes come from GitHub Actions with the service-role key
-- (pipelines/load_value_check.py), non-blocking for Pages like JEG-380.

insert into public.source_config (source, max_age_hours, block_on_stale, description)
values ('razzball', 168, false, 'Razzball rest-of-season projections'),
       ('ddf_value', 168, false, 'DDF Composite Value (engine; JEG-471)')
on conflict (source) do nothing;

create table if not exists public.value_check_runs (
  run_id uuid primary key default gen_random_uuid(),
  generated_at timestamptz not null,
  season integer not null,
  week integer not null check (week between 1 and 18),
  verdict text not null check (verdict in ('agree', 'disagree')),
  tolerance numeric not null,
  values_compared bigint not null,
  disagreeing_sources text[] not null default '{}',
  composite_disagreements text[] not null default '{}',
  held_sections jsonb not null default '{}'::jsonb,
  fixture_built_at text,
  github_run_id text,
  report jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.value_check_values (
  season integer not null,
  week integer not null check (week between 1 and 18),
  scoring text not null check (scoring in ('standard', 'half', 'full')),
  teams integer not null check (teams in (8, 10, 12, 14)),
  roster text not null check (roster in ('standard', 'superflex')),
  view text not null check (view in ('indexed', 'vorp', 'adj')),
  series text not null,
  player_key bigint not null,
  player text not null,
  engine_value numeric,
  reference_value numeric,
  value_diff numeric generated always as (engine_value - reference_value) stored,
  agrees boolean not null,
  held boolean not null default false,
  run_id uuid not null references public.value_check_runs (run_id) on delete cascade,
  updated_at timestamptz not null default now(),
  primary key (season, week, scoring, teams, roster, view, series, player_key)
);

create index if not exists value_check_values_run_idx on public.value_check_values (run_id);
create index if not exists value_check_values_disagree_idx
  on public.value_check_values (season, week) where not agrees;

alter table public.value_check_runs enable row level security;
alter table public.value_check_values enable row level security;
revoke all on public.value_check_runs, public.value_check_values from anon;
grant select on public.value_check_runs, public.value_check_values to authenticated;
grant all on public.value_check_runs, public.value_check_values to service_role;

create or replace view api.value_check_latest
with (security_barrier = true) as
select run_id, generated_at, season, week, verdict, tolerance, values_compared,
       disagreeing_sources, composite_disagreements, held_sections, fixture_built_at, github_run_id
  from public.value_check_runs
 order by generated_at desc
 limit 1;

create or replace view api.value_check_diff
with (security_barrier = true) as
select v.season, v.week, v.scoring, v.teams, v.roster, v.view, v.series, v.player_key, v.player,
       v.engine_value, v.reference_value, v.value_diff, abs(v.value_diff) as abs_diff,
       v.agrees, v.held, v.run_id, v.updated_at
  from public.value_check_values v;

grant select on api.value_check_latest, api.value_check_diff to anon, authenticated, service_role;

-- api.player_values: the existing definition, unchanged, plus the engine and
-- reference values for the same cell (standard roster; combo_reindexed is the
-- Indexed view, vorp / adj_values the other two), plus the DDF Value rows.
create or replace view api.player_values
with (security_invoker = false, security_barrier = true) as
select cv.player as player_key,
       cv.source,
       cv.season,
       cv.week,
       cv.scoring,
       cv.teams,
       cv.qb_variant,
       cv.view,
       cv.value,
       case
         when cv.view = 'combo_reindexed' and (cv.source in (select unnest(po.as_published_keys)
                                                          from public.product_options po
                                                         where po.product_key = 'default')) then 'indexed'
         when cv.view = 'combo_reindexed' then 'ddf_translated'
         when cv.view = 'vorp' then 'vorp'
         when cv.view = 'vorp_indexed' then 'vorp_indexed'
         when cv.view = 'adj_values' then 'adj'
         else 'native'
       end as value_provenance,
       case when cv.source = any (array['espn', 'cbsros', 'razzball']) then 'model' else 'published' end
         as model_vs_published,
       cv.detail_locator,
       cv.bake_id,
       null::numeric as index_total,
       null::text as pie_vintage,
       tpv.tier_price_vector,
       tpv.tier_price_vintage,
       case
         when cv.view = 'combo_reindexed' then 'full'
         when cv.view = any (array['vorp', 'vorp_indexed', 'adj_values']) and cv.scoring = 'full'
              and cv.teams = 12 and cv.qb_variant = 'none'
              and cv.source = any (array['espn', 'cbsros', 'razzball', 'usatoday', 'fantasycalc', 'fantasypros',
                                         'cbs', 'fantasycalc_adjusted', 'usatoday_adjusted',
                                         'fantasypros_adjusted', 'cbs_adjusted']) then 'full'
         when cv.view = any (array['vorp', 'vorp_indexed', 'adj_values']) and cv.scoring = 'full'
              and cv.teams = 12 and cv.qb_variant = 'none' then 'view_limited_source'
         when cv.view = any (array['vorp', 'vorp_indexed', 'adj_values']) then 'view_limited_combo'
         else 'full'
       end as coverage_class,
       vc.engine_value,
       vc.reference_value,
       vc.value_diff
  from public.consolidated_values cv
  left join public.player_values_tier_prices tpv
         on tpv.player = cv.player and tpv.source = cv.source and tpv.season = cv.season
        and tpv.week = cv.week and tpv.scoring = cv.scoring and tpv.teams = cv.teams
        and tpv.qb_variant = cv.qb_variant and tpv.view = cv.view
  left join public.value_check_values vc
         on vc.player_key = cv.player_key and vc.series = cv.source and vc.season = cv.season
        and vc.week = cv.week and vc.scoring = cv.scoring and vc.teams = cv.teams
        and vc.roster = 'standard'
        and vc.view = case cv.view when 'combo_reindexed' then 'indexed' when 'vorp' then 'vorp'
                                   when 'adj_values' then 'adj' end
union all
select vc.player as player_key,
       'ddf_value' as source,
       vc.season,
       vc.week,
       vc.scoring,
       vc.teams,
       'none' as qb_variant,
       case vc.view when 'indexed' then 'combo_reindexed' when 'vorp' then 'vorp' else 'adj_values' end as view,
       vc.engine_value as value,
       'ddf_composite' as value_provenance,
       'model' as model_vs_published,
       'value_check:ddf_value' as detail_locator,
       vc.run_id::text as bake_id,
       null::numeric as index_total,
       null::text as pie_vintage,
       null::jsonb as tier_price_vector,
       null::text as tier_price_vintage,
       'full' as coverage_class,
       vc.engine_value,
       vc.reference_value,
       vc.value_diff
  from public.value_check_values vc
 where vc.series = 'ddf_value' and vc.roster = 'standard' and vc.engine_value is not null;

grant select on api.player_values to anon;
