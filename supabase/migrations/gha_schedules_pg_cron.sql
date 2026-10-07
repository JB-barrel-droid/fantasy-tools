-- GAP-GHA-SCHEDULES (JEG-437): move the last three GitHub `schedule:` triggers
-- to Supabase pg_cron (standing direction: schedules live in pg_cron, ops-
-- ownership-001). GitHub's own cron fires late or skips; pg_cron dispatches the
-- workflow on main through public.dispatch_gha_workflow, which also writes
-- monitoring.dispatch_log so a refused dispatch shows red.
--
-- The workflows keep `workflow_dispatch:` and lose `schedule:`
-- (tests/test_monitoring_coverage.py: one scheduler owner per workflow;
-- tests/test_gha_schedules_pg_cron.py pins the three jobs below).
--
-- Applied via the Supabase MCP on 2026-10-07. cron.schedule(name, ...) is an
-- upsert by job name, so re-running is safe. Until the PR that removes the
-- GitHub `schedule:` merges, both schedulers fire; every one of the three is
-- idempotent (rebuild + deploy, NOOP load, commit-only-on-change).
--
-- Rollback: select cron.unschedule('<job>'); and restore the `schedule:` block.

-- pages.yml: daily rebuild 11:30 UTC (also deploys on every push to main).
select cron.schedule(
    'pages-deploy-live',
    '30 11 * * *',
    $$SELECT public.dispatch_gha_workflow('pages.yml', '{}'::jsonb)$$
);

-- weekly-dashboard-load.yml: daily 16:07 UTC (11:07 CT). NOOPs, or exits 2 with
-- no staged bundle, until weekly production resumes (JEG-399).
select cron.schedule(
    'weekly-dashboard-load-live',
    '7 16 * * *',
    $$SELECT public.dispatch_gha_workflow('weekly-dashboard-load.yml', '{}'::jsonb)$$
);

-- sleeper-identity-refresh.yml: Tuesday and Thursday 09:17 UTC.
select cron.schedule(
    'sleeper-identity-refresh-live',
    '17 9 * * 2,4',
    $$SELECT public.dispatch_gha_workflow('sleeper-identity-refresh.yml', '{}'::jsonb)$$
);

-- Point the checks' descriptions at the new owner (check rows are unchanged:
-- same cadence, same recorder).
update monitoring.check_config set
    alert_policy = alert_policy || jsonb_build_object(
        'pg_cron_job', 'pages-deploy-live',
        'what', 'pages.yml deploy finished green (every push to main, plus daily 11:30 UTC via pg_cron pages-deploy-live)'),
    updated_at = now()
where check_id = 'site_deploy';

update monitoring.check_config set
    alert_policy = alert_policy || jsonb_build_object(
        'pg_cron_job', 'weekly-dashboard-load-live',
        'what', 'weekly-dashboard-load.yml finished green (daily 16:07 UTC via pg_cron weekly-dashboard-load-live)'),
    updated_at = now()
where check_id = 'weekly_dashboard_load';

update monitoring.check_config set
    alert_policy = alert_policy || jsonb_build_object(
        'pg_cron_job', 'sleeper-identity-refresh-live',
        'what', 'sleeper-identity-refresh.yml finished green (Tue + Thu 09:17 UTC via pg_cron sleeper-identity-refresh-live)'),
    updated_at = now()
where check_id = 'sleeper_identity_refresh';
