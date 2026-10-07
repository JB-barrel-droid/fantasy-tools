-- Razzball ROS scrape to Supabase moved from Muse to CI (ops-ownership-001).
-- Replaces Muse's razzball-projections-pull (daily 06:20 CT, disabled
-- 2026-10-06). Closes GAP-024 / GAP-030. pg_cron is the only scheduler: the
-- workflow has no GitHub `schedule:` (tests/test_razzball_sync_ci.py pins that).
-- 11:20 UTC = 06:20 CDT, ahead of the 12:17 UTC rebuild-chain run.
select cron.schedule(
    'razzball-sync-live',
    '20 11 * * *',
    $$SELECT public.dispatch_gha_workflow('razzball-supabase-sync.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('razzball_projections_sync', 'http_status_and_content', 86400, 7200,
     'github_actions', 'razzball-supabase-sync.yml',
     '{"severity": "page", "what": "Razzball ROS scrape saved a new vintage to public.razzball_projections (daily 11:20 UTC via pg_cron razzball-sync-live)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
