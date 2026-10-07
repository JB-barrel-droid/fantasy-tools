-- JEG-432 R5: server-side freshness for each source's SAVED inputs.
--
-- public.nfl_content_week(date) is the content calendar of
-- pipelines/nfl_week.py (flips on TUESDAY, after Monday night; content week 1
-- starts Tue 2026-09-08; preseason -> 1; capped at 18). It is NOT the
-- watchdog calendar (ops/watchdog/_common.nfl_week flips Thursday; see
-- GAP-WEEK-CALENDARS). tests/test_source_freshness.py pins the browser port
-- (product-data.js contentWeekForDay) to nfl_week.py; the SQL copy was
-- checked against nfl_week.py over the same 200 days when applied (log).
--
-- api.source_freshness: one row per source with the newest week saved in its
-- Supabase source table, against the current content week (today in
-- America/New_York). Read-only metadata (weeks, dates, row counts) -- no
-- player values. This describes what is SAVED; the published chart's own
-- vintage is product-data.js getSourceFreshness() over the shipped snapshot,
-- which can lag the saved week until the next bake.
--
-- Additive only: creates one function and one view; touches no data.

create or replace function public.nfl_content_week(d date)
returns integer
language sql
immutable
set search_path = ''
as $$
  select case
    when d is null then null
    when d < date '2026-09-08' then 1
    else least(greatest(((d - date '2026-09-08') / 7) + 1, 1), 18)
  end
$$;

comment on function public.nfl_content_week(date) is
  'JEG-432: content week (Tuesday flip) -- SQL copy of pipelines/nfl_week.py current_nfl_week().';

create or replace view api.source_freshness as
with saved as (
  select source, week, source_content_date, pulled_at
    from public.source_trade_values where season = 2026
  union all
  select 'cbs', week, source_content_date, pulled_at
    from public.cbs_trade_values where season = 2026
  union all
  select 'cbsros', week, source_content_date, pulled_at
    from public.cbs_ros_projections where season = 2026
  union all
  select 'razzball', week, source_content_date, pulled_at
    from public.razzball_projections where season = 2026
  union all
  -- ESPN's `week` column is not a content week (week-2 rows were pulled on
  -- 2026-10-06), so ESPN is dated by its snapshot date on the content calendar.
  select 'espn', public.nfl_content_week(espn_snapshot_date), espn_snapshot_date, pulled_at
    from public.espn_season_projections where season = 2026
),
latest as (
  select source,
         max(week) as latest_week
    from saved
   group by source
),
today as (
  select (now() at time zone 'America/New_York')::date as d
)
select l.source,
       l.latest_week,
       max(s.source_content_date) as latest_content_date,
       max(s.pulled_at) as latest_pulled_at,
       count(*) as latest_week_rows,
       public.nfl_content_week(t.d) as current_content_week,
       case when l.latest_week is null then 'unknown'
            when l.latest_week >= public.nfl_content_week(t.d) then 'current'
            else 'older' end as status,
       (l.latest_week is not null and l.latest_week < public.nfl_content_week(t.d)) as is_older_week,
       greatest(public.nfl_content_week(t.d) - l.latest_week, 0) as weeks_behind,
       'content_week_tuesday_flip'::text as calendar,
       'pipelines/nfl_week.py'::text as calendar_source
  from latest l
  join saved s on s.source = l.source and s.week = l.latest_week
  cross join today t
 group by l.source, l.latest_week, t.d;

comment on view api.source_freshness is
  'JEG-432 R5: newest saved week per source vs the current content week (Tuesday flip). Metadata only.';

grant select on api.source_freshness to anon;
grant select on api.source_freshness to service_role;
-- anon needs EXECUTE: Postgres checks a function called inside a view against
-- the querying role, not the view owner. jeg377_jeg380_api_lockdown revoked
-- EXECUTE from anon to stop anon WRITES (ingest RPCs); this function is
-- IMMUTABLE date arithmetic with no table access, so granting it is safe.
revoke execute on function public.nfl_content_week(date) from public;
grant execute on function public.nfl_content_week(date) to anon, service_role;
