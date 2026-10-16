-- JEG-620 / JEG-621: Draft Sharks and Fantasy Sharks save workflows, scheduled by
-- the change probes (pipelines/source_probe.py sources draftsharks, fantasysharks).
-- Applied by the integrator after the workflows are on main and a dry
-- source-probe.yml run (sources=draftsharks,fantasysharks, dry=true) is green.
-- Idempotent. Pinned by tests/test_source_probe.py::SharksScheduleTest.
-- Probes at 04:45 and 16:45 UTC; a changed chart (or max age 20 h) dispatches
-- draftsharks-supabase-sync.yml / fantasysharks-supabase-sync.yml with mode=write.
begin;

select cron.schedule('source-probe-sharks', '45 4,16 * * *',
  $$SELECT public.dispatch_gha_workflow('source-probe.yml', '{"sources": "draftsharks,fantasysharks"}'::jsonb)$$);

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('draftsharks_trade_chart_sync', 'http_status_and_content', 86400, 43200,
     'github_actions', 'draftsharks-supabase-sync.yml',
     '{"severity": "warn", "what": "Draft Sharks trade value chart saved to public.draftsharks_trade_values (on change, at least every 20 h; dispatched by source-probe.yml)", "label": "Draft Sharks chart sync"}'),
    ('fantasysharks_projections_sync', 'http_status_and_content', 86400, 43200,
     'github_actions', 'fantasysharks-supabase-sync.yml',
     '{"severity": "warn", "what": "Fantasy Sharks rest-of-year projections saved to public.fantasysharks_projections (on change, at least every 20 h; dispatched by source-probe.yml)", "label": "Fantasy Sharks projections sync"}')
on conflict (check_id) do update set
    cadence_seconds = excluded.cadence_seconds,
    grace_override_seconds = excluded.grace_override_seconds,
    scheduler_owner_id = excluded.scheduler_owner_id,
    alert_policy = excluded.alert_policy,
    updated_at = now();

commit;
