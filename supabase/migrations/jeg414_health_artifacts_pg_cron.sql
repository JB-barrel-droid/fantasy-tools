-- JEG-414: the CI health writer (health-artifacts.yml) is scheduled from
-- Supabase, not a GitHub `schedule:` (ops-ownership-001: Supabase first).
-- Same cadence the workflow had: minutes 11 and 41 of every hour.
select cron.schedule(
    'health-artifacts-live',
    '11,41 * * * *',
    $$SELECT public.dispatch_gha_workflow('health-artifacts.yml', '{}'::jsonb)$$
);
