-- Refresh cadence, part 2 of 2: probe schedules, retired blind timers,
-- monitored checks (refresh-cadence lane, 2026-10-08). Needs part 1
-- (source_probe_tables_20261008.sql, applied 2026-10-08) and a green
-- source-probe.yml run on main.
-- Applied by the integrator, not by the lane. Pinned by
-- tests/test_source_probe.py::CadenceMigrationTest. Idempotent: re-running it
-- leaves the same state (cron.schedule upserts by name; unschedule is guarded).
--
-- Before: every ingest ran on a blind daily timer and the rebuild chain every
-- 6 h. After: cheap probes (pipelines/source_probe.py via source-probe.yml)
-- fingerprint each source several times a day and dispatch the full ingest
-- only on a change (or when the last acknowledged ingest is older than the
-- source's max age, or the probe could not read the source). A probe-driven
-- ingest that saved new content dispatches the rebuild chain itself; one daily
-- chain run (rebuild-chain-bake-live, 11:45 UTC) stays as the safety run.
--
-- Probe slots double as retry slots: a dispatched ingest that never
-- acknowledges is re-dispatched on the next slot after 50 min, up to 4 times
-- per fingerprint (source_probe.decide).


begin;

-- 2. Probe schedules (UTC). Each dispatches source-probe.yml for one group.
--    FantasyCalc: hourly (API; Cache-Control max-age=1200, no published rate
--    limit; 3 requests per probe). Changes are saved at most every 6 h
--    (POLICIES min_interval).
select cron.schedule('source-probe-fantasycalc', '5 * * * *',
  $$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "fantasycalc"}'::jsonb)$$);
--    Projections (ESPN, CBS rest of season, Razzball): every 4 h, phased so
--    the last slot of each day is 23:25 UTC: a Monday change is saved inside
--    content week N (Tuesday flip), whose snapshot is the newest one dated in it.
select cron.schedule('source-probe-projections', '25 3-23/4 * * *',
  $$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "espn,cbsros,razzball"}'::jsonb)$$);
--    Trade-value articles: every 3 h Mon-Thu (publication Mon night / Tue,
--    hand edits through Wednesday), twice a day Fri-Sun.
select cron.schedule('source-probe-trade-charts', '35 */3 * * 1-4',
  $$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "cbs,usatoday,fantasypros"}'::jsonb)$$);
select cron.schedule('source-probe-trade-charts-weekend', '35 0,12 * * 0,5,6',
  $$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "cbs,usatoday,fantasypros"}'::jsonb)$$);

-- 3. Blind timers the probes replace. The workflows stay dispatchable by hand.
select cron.unschedule(jobid) from cron.job where jobname in (
    'trade-chart-ingest-live',      -- daily 12:07
    'trigger-espn-sync-live',       -- daily 11:30
    'trigger-cbsros-sync-live',     -- Wed 11:00
    'trigger-cbsros-sync-retry',    -- Wed 17:00
    'razzball-sync-live',           -- daily 11:20
    'rebuild-chain-live'            -- 17 */6: now dispatched on change
);
-- Kept: rebuild-chain-bake-live (daily 11:45, the chain's safety run),
-- trigger-fantasycalc-weekly-save (Tue + Fri 13:07: the week-history
-- FantasyCalc cut is the first pull at or after Tue 12:00 UTC),
-- vintage-check-live (hourly; dispatches the chain when a DB vintage moves).

-- 4. Monitored checks. The probe run itself:
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('source_probe', 'http_status_and_content', 3600, 3600,
     'github_actions', 'source-probe.yml',
     '{"severity": "warn", "what": "source-probe.yml probed its sources and recorded fingerprints (hourly FantasyCalc via pg_cron source-probe-fantasycalc; projections every 4 h; trade charts every 3 h Mon-Thu, 12 h Fri-Sun)", "label": "Source change probes"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();

--    Ingests now run on change or at max age (20 h; FantasyCalc 24 h), so the
--    longest gap between runs is max age + one probe slot: projections 24 h,
--    trade charts 32 h (12 h weekend slots), FantasyCalc Tue/Fri fixed saves.
update monitoring.check_config set cadence_seconds = 86400, grace_override_seconds = 21600,
       alert_policy = alert_policy || jsonb_build_object('what',
         'ESPN projections scraped and saved (on change, at least every 20 h; dispatched by source-probe.yml)'),
       updated_at = now()
 where check_id = 'espn_supabase_sync';
update monitoring.check_config set cadence_seconds = 86400, grace_override_seconds = 21600,
       alert_policy = alert_policy || jsonb_build_object('what',
         'CBS rest-of-season projections scraped and saved (on change, at least every 20 h; dispatched by source-probe.yml)'),
       updated_at = now()
 where check_id = 'cbsros_supabase_sync';
update monitoring.check_config set cadence_seconds = 86400, grace_override_seconds = 21600,
       alert_policy = alert_policy || jsonb_build_object('what',
         'Razzball rest-of-season scrape saved (on change, at least every 20 h; dispatched by source-probe.yml)'),
       updated_at = now()
 where check_id = 'razzball_projections_sync';
update monitoring.check_config set cadence_seconds = 86400, grace_override_seconds = 43200,
       alert_policy = alert_policy || jsonb_build_object('what',
         'Trade-chart ingest ran (on change, at least every 20 h; dispatched by source-probe.yml)'),
       updated_at = now()
 where check_id in ('cbs_trade_chart_ingest', 'usatoday_trade_chart_ingest');
update monitoring.check_config set cadence_seconds = 86400, grace_override_seconds = 7200,
       alert_policy = alert_policy || jsonb_build_object('what',
         'Rebuild chain ran (dispatched after a changed ingest and by the hourly vintage check; daily safety run 11:45 UTC via rebuild-chain-bake-live)'),
       updated_at = now()
 where check_id = 'rebuild_chain';

-- Probe log retention (60 days) is done by source_probe.py itself on each
-- run, so no extra pg_cron SQL job (and no extra monitored check) is needed.

commit;

-- Verify after applying:
--   select jobname, schedule, active from cron.job
--    where jobname like 'source-probe%' or jobname in
--      ('trade-chart-ingest-live','trigger-espn-sync-live','trigger-cbsros-sync-live',
--       'trigger-cbsros-sync-retry','razzball-sync-live','rebuild-chain-live')
--    order by 1;
--   -- expect the four source-probe jobs active and the six retired jobs absent.
