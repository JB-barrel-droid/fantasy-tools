-- JEG-426: FantasyCalc drift detection has exactly one scheduler owner and a
-- monitored check.
--
-- The pg_cron job below already existed in production (created during the
-- JEG-285 cutover) but was never written to the repo, so the 2026-10-05 audit
-- concluded "no pg_cron replacement was created". It was dispatching
-- fantasycalc-drift.yml daily; the workflow then failed on every run.
-- cron.schedule() upserts by job name, so re-applying is idempotent.
select cron.schedule(
    'trigger-fantasycalc-drift-live',
    '45 11 * * *',
    $$SELECT public.dispatch_gha_workflow('fantasycalc-drift.yml', '{}'::jsonb)$$
);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('fantasycalc_native_drift', 'http_status_and_content', 86400, 3600,
     'github_actions', 'fantasycalc-drift.yml',
     '{"severity": "warn", "what": "live FantasyCalc top-25 (12-team half-PPR) within 5% of the Supabase natives for >= 80% of players; dispatched by pg_cron trigger-fantasycalc-drift-live"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_type = excluded.scheduler_owner_type,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();
