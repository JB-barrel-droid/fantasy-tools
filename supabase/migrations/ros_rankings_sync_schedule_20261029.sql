-- Schedule the ROS rankings scrape (JEG-1198 option C). Was sql/migrations/016.
-- APPLIED 2026-10-29 on Jeremy's approval ("Approve 015 and 016"), after the table migration
-- (sql/migrations/015_ros_rankings.sql). config/monitoring_coverage.json lists
-- ros-rankings-sync.yml as a pg_cron pipeline; the workflow records the check in its
-- "Record the monitored check" step.
-- dispatch_gha_workflow dispatches on main, so scheduled runs need the workflow on main.
--
-- 13:40 UTC daily: after the expert consensus' overnight update; Yahoo tiers articles post
-- mid-week, so a daily read picks each up within a day.
--
-- Rollback:
--   select cron.unschedule('ros-rankings-sync-live');
--   delete from monitoring.check_config where check_id = 'ros_rankings_sync';
select cron.schedule(
    'ros-rankings-sync-live',
    '40 13 * * *',
    $$SELECT public.dispatch_gha_workflow('ros-rankings-sync.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('ros_rankings_sync', 'http_status_and_content', 86400, 7200,
     'github_actions', 'ros-rankings-sync.yml',
     '{"severity": "warn", "what": "ROS rankings scrape saved to public.ros_rankings (daily 13:40 UTC via pg_cron ros-rankings-sync-live); research data, no published value depends on it"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
