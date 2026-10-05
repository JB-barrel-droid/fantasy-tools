-- JEG-414 (ARCH-013): non-Muse producer for health/checkpoint artifacts,
-- with independent missed-run detection.
--
-- The JEG-339 monitoring schema (check_config / check_observations /
-- check_heartbeats + monitoring.run_evaluator_cycle) was deployed but never
-- configured or scheduled, so nothing could mark a missing run red.
--
-- This migration:
--   1. adds a service_role-only RPC the GitHub Actions producer
--      (.github/workflows/health-artifacts.yml) calls to record each
--      observation + its scheduler heartbeat;
--   2. registers three 30-minute checks owned by that workflow;
--   3. schedules the evaluator every 5 minutes, so a producer that stops
--      running goes 'missed' in monitoring.check_heartbeats without relying
--      on the producer (or Muse) to report its own absence.
--
-- Reversible: drop the function, delete the three check_config rows (and
-- their observations), and cron.unschedule('monitoring-evaluator-5min').

begin;

create or replace function public.monitoring_record_observation(
    p_check_id           text,
    p_ok                 boolean,
    p_content_ok         boolean default null,
    p_http_status        integer default null,
    p_latency_ms         integer default null,
    p_error_code         text    default null,
    p_scheduler_owner_id text    default null
) returns void
language plpgsql
security definer
set search_path = monitoring, public
as $$
begin
    insert into monitoring.check_observations
        (check_id, run_at, ok, latency_ms, http_status, content_ok, error_code, source)
    values
        (p_check_id, now(), p_ok, p_latency_ms, p_http_status, p_content_ok, p_error_code,
         'github_actions');
    if p_scheduler_owner_id is not null then
        insert into monitoring.scheduler_heartbeats
            (scheduler_owner_type, scheduler_owner_id, last_seen_at)
        values ('github_actions', p_scheduler_owner_id, now())
        on conflict (scheduler_owner_type, scheduler_owner_id)
        do update set last_seen_at = excluded.last_seen_at;
    end if;
end;
$$;

revoke all on function public.monitoring_record_observation(
    text, boolean, boolean, integer, integer, text, text) from public, anon, authenticated;
grant execute on function public.monitoring_record_observation(
    text, boolean, boolean, integer, integer, text, text) to service_role;

insert into monitoring.check_config
    (check_id, check_type, cadence_seconds, grace_override_seconds,
     scheduler_owner_type, scheduler_owner_id, alert_policy)
values
    ('health_artifacts_producer', 'http_status_and_content', 1800, 900,
     'github_actions', 'health-artifacts.yml',
     '{"severity": "page", "what": "CI producer built import-health + pipeline-checkpoints"}'),
    ('served_pipeline_checkpoints_fresh', 'http_status_and_content', 1800, 900,
     'github_actions', 'health-artifacts.yml',
     '{"severity": "page", "what": "served modules/pipeline-checkpoints.json generated_at <= 60 min old"}'),
    ('served_import_health_fresh', 'http_status_and_content', 1800, 900,
     'github_actions', 'health-artifacts.yml',
     '{"severity": "page", "what": "served modules/source-import-health.json checked_at <= 60 min old"}')
on conflict (check_id) do nothing;

select cron.schedule('monitoring-evaluator-5min', '*/5 * * * *',
                     'select monitoring.run_evaluator_cycle(now())');

commit;
