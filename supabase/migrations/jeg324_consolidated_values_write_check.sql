-- JEG-324 / decision consol-nonblocking-001 (Jeremy 2026-10-07): the
-- consolidated_values write in rebuild-chain.yml is non-blocking for Pages and
-- is monitored on its own. rebuild-chain.yml's "Record consolidated_values
-- check" step records each run (red on failure) via record_monitor_check.py.
-- NOT YET APPLIED: apply after the PR that adds the record step merges.
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('consolidated_values_write', 'http_status_and_content', 21600, 1800,
     'github_actions', 'rebuild-chain.yml',
     '{"severity": "page", "label": "Consolidation write (Supabase)", "pg_cron_job": "rebuild-chain-live", "workflow": "rebuild-chain.yml", "what": "build_consolidated_values.py --write-supabase succeeded in the rebuild chain (core sources; *_adjusted excluded by decision consol-adjusted-001). Non-blocking for Pages: a red here means public.consolidated_values lags the published fixture."}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
