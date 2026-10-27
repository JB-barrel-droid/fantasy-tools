-- JEG-976: daily dispatch of render-sweep.yml (Jeremy, 2026-10-23, option b).
-- APPLIED 2026-10-26 (jobid 47, project iskiybsimubiujwuchsl), exactly as below,
-- on Jeremy's go-ahead (2026-10-26). Kept outside supabase/migrations so no
-- migration run re-applies it. The job is listed in config/monitoring_coverage.json
-- (scheduler pg_cron, no check record: the sweep is a warning, not a pipeline).
-- Rollback: select cron.unschedule('render-sweep-daily');
select cron.schedule(
    'render-sweep-daily',
    '47 7 * * *',
    $$SELECT public.dispatch_gha_workflow('render-sweep.yml', '{}'::jsonb)$$
);
