-- JEG-432 R4: the saved 12-team inputs per source AND week, so the browser
-- can recompute both the current and the prior week with the reader's own
-- league settings (movers), instead of reading movers stored at one league.
--
-- Scope: the four published trade charts (FantasyCalc, FantasyPros, USA
-- Today, CBS) -- the only sources with more than one saved week of
-- 12-team / 1-QB inputs today (weeks 2-5, see api.source_input_weeks).
-- Projection sources are out of scope here: CBS ROS and Razzball have only
-- week-4 saves, and ESPN's table stores season stat lines with a `week`
-- column that is not a content week (GAP-R4-PROJECTION-HISTORY).
--
-- One block per (source, week, scoring): the LATEST pull of that week
-- (max pulled_at; bake_id breaks ties). Older re-pulls of the same week
-- (e.g. USA Today week 4 pulled 2026-09-29 and 2026-10-02) are not exposed.
-- Scoring is normalised to the contract spelling full/half/standard.
--
-- Additive only: two views; touches no data.

create or replace view api.source_inputs_weekly as
with raw as (
  select source, week, season, player_key::bigint as player_key, player_norm, position, team,
         case scoring when 'std' then 'standard' when 'standard' then 'standard'
                      when 'half' then 'half' when 'half_ppr' then 'half'
                      when 'full' then 'full' when 'ppr' then 'full' end as scoring,
         native_value::double precision as native_value, value::double precision as value,
         source_content_date, pulled_at, bake_id
    from public.source_trade_values
   where league_teams = 12 and qb_slots = 1 and coalesce(variant, 'as_published') = 'as_published'
     and source in ('fantasycalc', 'fantasypros', 'usatoday')
  union all
  select 'cbs', week, season, player_key, player_norm, position, team,
         case scoring when 'std' then 'standard' when 'standard' then 'standard'
                      when 'half' then 'half' when 'half_ppr' then 'half'
                      when 'full' then 'full' when 'ppr' then 'full' end,
         native_value, value, source_content_date, pulled_at, bake_id
    from public.cbs_trade_values
   where league_teams = 12 and coalesce(qb_slots, 1) = 1 and coalesce(variant, 'as_published') = 'as_published'
),
pulls as (
  select source, season, week, scoring, pulled_at, bake_id,
         row_number() over (partition by source, season, week, scoring
                            order by pulled_at desc, bake_id desc nulls last) as rn
    from (select distinct source, season, week, scoring, pulled_at, bake_id from raw) d
),
latest_week as (
  select source, season, max(week) as max_week from raw group by source, season
)
select r.source,
       r.season,
       r.week,
       lw.max_week - r.week as weeks_back_from_latest,
       public.nfl_content_week((now() at time zone 'America/New_York')::date) - r.week as weeks_back_from_content_week,
       r.scoring,
       12 as teams,
       1 as qb_slots,
       r.player_key,
       r.player_norm,
       r.position,
       r.team,
       r.native_value,
       r.value,
       r.source_content_date,
       r.pulled_at,
       r.bake_id
  from raw r
  join pulls p on p.rn = 1 and p.source = r.source and p.season = r.season and p.week = r.week
              and p.scoring = r.scoring and p.pulled_at = r.pulled_at
              and p.bake_id is not distinct from r.bake_id
  join latest_week lw on lw.source = r.source and lw.season = r.season;

comment on view api.source_inputs_weekly is
  'JEG-432 R4: latest-pull 12-team/1-QB published inputs per source x week x scoring, for browser recompute of current and prior week.';

create or replace view api.source_input_weeks as
select source, season, week, weeks_back_from_latest, weeks_back_from_content_week, scoring,
       count(*) as players,
       count(player_key) as players_keyed,
       min(pulled_at) as pulled_at,
       min(bake_id) as bake_id,
       max(source_content_date) as source_content_date
  from api.source_inputs_weekly
 group by source, season, week, weeks_back_from_latest, weeks_back_from_content_week, scoring;

comment on view api.source_input_weeks is
  'JEG-432 R4: which weeks of saved inputs exist per source (metadata for api.source_inputs_weekly).';

grant select on api.source_inputs_weekly to anon, service_role;
grant select on api.source_input_weeks to anon, service_role;
