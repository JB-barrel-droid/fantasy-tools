-- APPLIED 2026-10-08 by the integrator together with the fix/weeks-tidy merge.
-- fix/weeks-tidy (2026-10-08). Apply BEFORE merging the code that uses it:
-- the CBS saver's upsert names bake_id in on_conflict, and every saver writes
-- source_url, so the CI ingests fail loudly until this runs.
--
-- 1. GAP-CBS-WEEK-OVERWRITE: version CBS like USA Today. The unique grain
--    used to be the week (cbs_trade_values_grain_uidx), so a same-week CBS
--    revision overwrote that week's rows in place. bake_id joins the key
--    (same shape as source_trade_values_bake_version_uidx); readers already
--    select the latest bake (import_supabase_references._select_latest_bake,
--    verify_import_health, api.source_inputs_weekly = latest pull per week).
--    Existing rows (bake_id NULL) are labelled cbswk<week>_legacy so every
--    row names its version; NOT NULL keeps a writer from dropping it.
--
-- 2. GAP-SOURCE-URL-WEEK2: each saved row carries the article URL it was
--    priced from, so the importer can hand the promoted week's URL to the
--    fixture (sources.<key>.url) instead of a hand-set Week 2 link. Nullable:
--    FantasyCalc has no article (its URL is the site), older rows have none.
--
-- 3. Backfill source_url for the weeks whose article URL is known (below).
--    Only rows of that exact (source, week) without a URL are touched. The
--    next rebuild-chain run then carries the URL into the fixture through
--    import -> source_provenance.source_url -> promotion (sources.<key>.url).

begin;

update public.cbs_trade_values
   set bake_id = 'cbswk' || week || '_legacy'
 where bake_id is null;

drop index if exists public.cbs_trade_values_grain_uidx;
create unique index if not exists cbs_trade_values_bake_version_uidx
    on public.cbs_trade_values (source, variant, scoring, league_teams, qb_slots, season, week, player_key, bake_id);
alter table public.cbs_trade_values alter column bake_id set not null;

alter table public.cbs_trade_values add column if not exists source_url text;
alter table public.source_trade_values add column if not exists source_url text;

comment on column public.cbs_trade_values.bake_id is
  'Immutable version of a week (cbswk<week>_<date>t<HHMM>_v<n>); readers take the latest bake. GAP-CBS-WEEK-OVERWRITE.';
comment on column public.cbs_trade_values.source_url is
  'Article URL these values were priced from (GAP-SOURCE-URL-WEEK2).';
comment on column public.source_trade_values.source_url is
  'Article URL these values were priced from (GAP-SOURCE-URL-WEEK2); null when the source has no article.';

-- 3. URLs as fetched by the ingests (GitHub Actions trade-chart-ingest runs
--    37688629726 / 37689014173 / 37688456507 on 2026-10-07, and the Week 2 /
--    Week 4 links already in the repo). CBS uses the www.cbssports.com path of
--    the sportsfly mirror the puller reads.
update public.source_trade_values set source_url =
  'https://www.usatoday.com/story/sports/fantasy/football/2026/10/06/fantasy-trade-value-charts-week-5-ros-rankings/92125556007/'
 where source = 'usatoday' and season = 2026 and week = 5 and source_url is null;
update public.source_trade_values set source_url =
  'https://www.usatoday.com/story/sports/fantasy/football/2026/09/29/fantasy-trade-value-chart-week-4-ros-rankings/92008742007/'
 where source = 'usatoday' and season = 2026 and week = 4 and source_url is null;
update public.source_trade_values set source_url =
  'https://www.usatoday.com/story/sports/fantasy/football/2026/09/15/fantasy-football-trade-value-chart-week-2-ros-rankings/91770884007/'
 where source = 'usatoday' and season = 2026 and week = 2 and source_url is null;
update public.source_trade_values set source_url =
  'https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-5-2026/'
 where source = 'fantasypros' and season = 2026 and week = 5 and source_url is null;
update public.source_trade_values set source_url =
  'https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-4-2026/'
 where source = 'fantasypros' and season = 2026 and week = 4 and source_url is null;
update public.source_trade_values set source_url =
  'https://www.fantasypros.com/2026/09/fantasy-football-trade-value-chart-week-2-2026/'
 where source = 'fantasypros' and season = 2026 and week = 2 and source_url is null;
update public.cbs_trade_values set source_url =
  'https://www.cbssports.com/fantasy/football/news/dave-richards-week-' || week || '-trade-chart-and-rest-of-season-fantasy-football-rankings-help-you-win-now/'
 where season = 2026 and week in (2, 4) and source_url is null;
-- Integrator, at apply time (2026-10-08): week 3 skipped (CBS changes its slug
-- weekly; the week-3 URL differs from this pattern), week 5's real URL added.
update public.cbs_trade_values set source_url =
  'https://www.cbssports.com/fantasy/football/news/dave-richards-2026-week-5-trade-chart/'
 where season = 2026 and week = 5 and source_url is null;

commit;
