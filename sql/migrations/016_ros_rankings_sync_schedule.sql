-- Migration 016: schedule the ROS rankings scrape (JEG-1198 option C)
-- DRAFT. NOT APPLIED. Apply only after 015_ros_rankings.sql, and only when Jeremy's own message
-- names this migration. Moves to supabase/migrations/ with config/monitoring_coverage.json
-- (ros-rankings-sync.yml from unmonitored to a pg_cron pipeline) in the same change.
-- The workflow must then record the check (a "Record the monitored check" step, as in
-- razzball-supabase-sync.yml).
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
