-- Trade-chart ingest (CBS + USA Today) moved from Muse to CI (ops-ownership-001).
-- Replaces Muse's cbs-trade-chart-ingest / usatoday-trade-chart-ingest (daily
-- 07:07 CT, disabled 2026-10-06). pg_cron is the only scheduler: the workflow
-- has no GitHub `schedule:` (tests/test_trade_chart_ingest_ci.py pins that).
-- 12:07 UTC = 07:07 CDT (06:07 CST after the November DST change).
select cron.schedule(
    'trade-chart-ingest-live',
    '7 12 * * *',
    $$SELECT public.dispatch_gha_workflow('trade-chart-ingest.yml', '{"mode": "write"}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('cbs_trade_chart_ingest', 'http_status_and_content', 86400, 7200,
     'github_actions', 'trade-chart-ingest.yml',
     '{"severity": "page", "what": "CBS trade-chart ingest ran clean: wrote the week, or found it unchanged in the DB (daily 12:07 UTC via pg_cron trade-chart-ingest-live)"}'),
    ('usatoday_trade_chart_ingest', 'http_status_and_content', 86400, 7200,
     'github_actions', 'trade-chart-ingest.yml',
     '{"severity": "warn", "what": "USA Today trade-chart ingest ran clean (daily 12:07 UTC via pg_cron trade-chart-ingest-live). Known: usatoday.com answers GitHub runners with 402 Access Restricted (error_code SOURCE_BLOCKED) as of 2026-10-06; see risk register GAP-USAT-CI-BLOCKED"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
