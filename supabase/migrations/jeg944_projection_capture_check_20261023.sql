-- JEG-944: monitoring check for the Sunday projection capture workflow
-- (tests/test_monitoring_coverage.py requires a check_config insert per recorded check).
-- Weekly cadence; the workflow records on success and failure. Not yet applied.
insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('projection_capture_sunday', 'http_status_and_content', 604800, 14400,
     'github_actions', 'projection-capture-sunday.yml',
     '{"severity": "warn", "what": "Sunday pre-kickoff capture of CBS and Razzball projections into public.source_projection_captures (15:30 UTC Sunday via pg_cron projection-capture-sunday; JEG-944)"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
