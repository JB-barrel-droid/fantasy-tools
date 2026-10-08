-- Producers lane schedule tidy (2026-10-08). Applied by the integrator, not by
-- the lane. Pinned by tests/test_producers_schedule_tidy.py. Every statement is
-- idempotent: re-running it leaves the same state.
--
-- 1. Retire two paused jobs whose output nothing on the site or chain reads.
-- 2. Re-enable the player trace (served monitor page reads it) at a daily cadence.
-- (Retry slots / per-source cadence belong to the refresh-cadence lane.)

begin;

-- 1a. FantasyCalc drift monitor: retired. The weekly save (Tue + Fri 13:07)
--     re-saves before drift ages; drift is a warn-level signal, not wrong
--     numbers. Workflow stays as a manual tool.
select cron.unschedule(jobid) from cron.job where jobname = 'trigger-fantasycalc-drift-live';

-- 1b. Weekly dashboard load: retired until weekly production resumes (JEG-399).
--     No site/chain reader of weekly_dashboard_*; the job failed daily (exit 2).
select cron.unschedule(jobid) from cron.job where jobname = 'weekly-dashboard-load-live';

-- Their monitored checks go with them (the coverage manifest no longer lists
-- them; a leftover row would be flagged by audit_monitoring_coverage.py).
delete from monitoring.cron_check_map
 where check_id in ('fantasycalc_native_drift', 'weekly_dashboard_load');
delete from monitoring.check_observations
 where check_id in ('fantasycalc_native_drift', 'weekly_dashboard_load');
delete from monitoring.check_config
 where check_id in ('fantasycalc_native_drift', 'weekly_dashboard_load');

-- 2. Player trace: daily 12:47 UTC, after rebuild-chain-bake-live (11:45).
select cron.alter_job(jobid, schedule := '47 12 * * *', active := true)
  from cron.job where jobname = 'trigger-player-trace-live';
update monitoring.check_config
   set cadence_seconds = 86400,
       grace_override_seconds = 7200,
       alert_policy = alert_policy || jsonb_build_object(
         'what', 'player-trace-rebuild.yml finished green on main (daily 12:47 UTC via pg_cron trigger-player-trace-live)'),
       updated_at = now()
 where check_id = 'player_trace_rebuild';

commit;

-- Verify after applying:
--   select jobname, schedule, active from cron.job
--    where jobname in
--      ('trigger-player-trace-live','trigger-fantasycalc-drift-live','weekly-dashboard-load-live')
--    order by 1;
--   -- expect player trace '47 12 * * *' active, the two retired jobs absent.
