-- JEG-976: daily dispatch of render-sweep.yml (Jeremy, 2026-10-23, option b).
-- NOT APPLIED. Written for review; applying it is a production Supabase change
-- that needs Jeremy's go-ahead. Kept outside supabase/migrations so no migration
-- run picks it up by accident. When applied: list the job in
-- config/monitoring_coverage.json (scheduler pg_cron) and move the workflow out
-- of unmonitored_workflows.
-- Rollback: select cron.unschedule('render-sweep-daily');
select cron.schedule(
    'render-sweep-daily',
    '47 7 * * *',
    $$SELECT public.dispatch_gha_workflow('render-sweep.yml', '{}'::jsonb)$$
);
