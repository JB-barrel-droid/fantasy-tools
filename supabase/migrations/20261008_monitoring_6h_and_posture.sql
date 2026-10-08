-- 2026-10-08 monitoring tidy (monitoring lane). NOT APPLIED by the authoring
-- session: the integrator applies it with apply_migration (name:
-- monitoring_6h_and_posture_20261008), AFTER security_lockdown_20261008 and
-- after the branch fix/monitoring-tidy is merged (health-artifacts.yml must
-- call public.monitoring_refresh_summary() before this job is re-enabled,
-- otherwise the 6-hourly run snapshots a summary nothing has evaluated).
--
-- Jeremy, 2026-10-07: pre-launch, no heavy monitoring; the 5- and 15-minute
-- jobs were switched off. 2026-10-08: tidy, nothing parked. So:
--   * one producer, every 6 hours: health-artifacts.yml (pg_cron
--     health-artifacts-live) records the pg_cron run history, runs the
--     evaluator and snapshots the summary in the same call
--     (public.monitoring_refresh_summary). No 5-minute jobs.
--   * the four jobs this lane owns that stay off are retired (unscheduled) and
--     their checks deleted (same pattern as producers_schedule_tidy_20261008):
--       monitoring-evaluator-5min, monitoring-cron-observer-5min  -> folded in
--       jeg379-health-checks-15min (ops.run_health_checks -> ops.health) and
--       gate-audit-v1 (api.audit_publish_gate -> public.gate_audits): nothing
--       in the repo, the site, any view or any other function reads ops.health
--       or public.gate_audits (grep of the repo; pg_depend/pg_proc search
--       2026-10-08). The publish gate itself (api.run_publish_gate, called by
--       api.activate_snapshot) is untouched; only its 30-minute audit stops.
--   * GAP-SCHEDULER-DOWN-NOISE: the evaluator stops deriving scheduler_down.
--   * public.monitoring_security_posture(): the advisor's security findings
--     as numbers, snapshotted into monitoring-summary.json so a regression
--     (a new public table without RLS, a write grant to anon) alerts.

begin;

-- 1. Retire the jobs (cron.unschedule raises if the job is missing; guard it).
do $$
declare j text;
begin
  foreach j in array array['monitoring-evaluator-5min', 'monitoring-cron-observer-5min',
                           'jeg379-health-checks-15min', 'gate-audit-v1'] loop
    if exists (select 1 from cron.job where jobname = j) then
      perform cron.unschedule(j);
    end if;
  end loop;
end
$$;

delete from monitoring.cron_check_map
 where check_id in ('pgcron_monitoring_evaluator', 'pgcron_cron_observer', 'pgcron_ops_health_checks', 'pgcron_gate_audit');
delete from monitoring.check_heartbeats
 where check_id in ('pgcron_monitoring_evaluator', 'pgcron_cron_observer', 'pgcron_ops_health_checks', 'pgcron_gate_audit');
delete from monitoring.check_observations
 where check_id in ('pgcron_monitoring_evaluator', 'pgcron_cron_observer', 'pgcron_ops_health_checks', 'pgcron_gate_audit');
delete from monitoring.check_config
 where check_id in ('pgcron_monitoring_evaluator', 'pgcron_cron_observer', 'pgcron_ops_health_checks', 'pgcron_gate_audit');

-- 2. health-artifacts every 6 hours, 33 minutes after each rebuild-chain-live
--    dispatch (:17), so the snapshot sees that run's observation.
select cron.alter_job(
    (select jobid from cron.job where jobname = 'health-artifacts-live'),
    schedule := '50 */6 * * *',
    active   := true);

update monitoring.check_config
   set cadence_seconds = 21600, grace_override_seconds = 1800, updated_at = now(),
       alert_policy = alert_policy || jsonb_build_object(
         'what', case check_id
           when 'health_artifacts_producer' then 'CI producer built import-health + pipeline-checkpoints and refreshed the monitor (every 6h at :50 via pg_cron health-artifacts-live)'
           when 'served_import_health_fresh' then 'served modules/source-import-health.json checked_at <= 720 min old (twice the 6h cadence)'
           when 'served_pipeline_checkpoints_fresh' then 'served modules/pipeline-checkpoints.json generated_at <= 720 min old (twice the 6h cadence)'
         end)
 where check_id in ('health_artifacts_producer', 'served_import_health_fresh', 'served_pipeline_checkpoints_fresh');

-- 3. Evaluator without the scheduler_down noise (body otherwise identical to
--    the live 2026-10-07 version; search_path pinned).
create or replace function monitoring.compute_heartbeat_state(p_check_id text, p_enabled boolean, p_cadence_seconds integer, p_cron_expr text, p_grace_override integer, p_latency_budget_ms integer, p_check_type monitoring.check_type, p_owner_type monitoring.scheduler_owner_type, p_owner_id text, p_active_ownership integer, p_now timestamp with time zone)
 returns table(state monitoring.heartbeat_state, state_reason text, expected_next_run_at timestamp with time zone, last_run_at timestamp with time zone, last_ok_at timestamp with time zone, last_error_at timestamp with time zone, ownership_status monitoring.ownership_status, scheduler_down boolean, latest_details jsonb)
 language plpgsql
 stable
 set search_path to 'monitoring', 'public', 'pg_temp'
as $function$
declare
v_grace integer;
v_latest_obs record;
v_latest_in_window record;
v_expected_next timestamptz;
v_window_start timestamptz;
v_scheduler_down boolean;
v_ownership_status monitoring.ownership_status;
v_state monitoring.heartbeat_state;
v_state_reason text;
v_latest_details jsonb;
v_created timestamptz;
begin
if not p_enabled then
return query select 'disabled'::monitoring.heartbeat_state, 'enabled=false', null::timestamptz, null::timestamptz, null::timestamptz, null::timestamptz, 'ok'::monitoring.ownership_status, false, '{}'::jsonb;
return;
end if;
if p_cadence_seconds is null and p_cron_expr is null then
return query select 'unknown'::monitoring.heartbeat_state, 'no schedule resolvable', null::timestamptz, null::timestamptz, null::timestamptz, null::timestamptz, 'ok'::monitoring.ownership_status, false, '{}'::jsonb;
return;
end if;
if p_grace_override is not null then
v_grace := greatest(120, least(1800, p_grace_override));
elsif p_cadence_seconds is not null then
v_grace := greatest(120, least(1800, ceil(1.5 * p_cadence_seconds)::int));
else
v_grace := 600;
end if;
if p_active_ownership <= 0 then
v_ownership_status := 'unknown_owner';
elsif p_active_ownership > 1 then
v_ownership_status := 'ambiguous';
else
v_ownership_status := 'ok';
end if;
-- GAP-SCHEDULER-DOWN-NOISE: scheduler_heartbeats is only touched when a
-- workflow records an observation (300 s grace), so every check slower than
-- 5 minutes read "scheduler down". A dead scheduler already shows as the
-- check going 'missed' and, for pg_cron, as a red cron_jobs row in
-- public.monitoring_summary(); the flag carried no extra signal. Always false.
v_scheduler_down := false;
select * into v_latest_obs from monitoring.v_check_observations o where o.check_id = p_check_id order by o.run_at desc limit 1;
if p_cadence_seconds is not null then
if v_latest_obs.run_at is null then
-- Never observed: wait one cadence from when the check was created, then
-- flag it missed (was: expected_next = now, i.e. 'unknown' forever).
select c.created_at into v_created from monitoring.check_config c where c.check_id = p_check_id;
v_expected_next := coalesce(v_created, p_now) + make_interval(secs => p_cadence_seconds);
else
v_expected_next := v_latest_obs.run_at + make_interval(secs => p_cadence_seconds);
end if;
else
v_expected_next := p_now;
end if;
v_window_start := v_expected_next - make_interval(secs => v_grace);
select * into v_latest_in_window from monitoring.v_check_observations o
where o.check_id = p_check_id and o.run_at >= v_window_start and o.run_at <= p_now
order by o.run_at desc limit 1;
if v_latest_in_window.run_at is not null and not v_latest_in_window.ok then
v_state := 'error';
v_state_reason := 'failed run in window';
v_latest_details := jsonb_build_object('http_status', v_latest_in_window.http_status, 'latency_ms', v_latest_in_window.latency_ms, 'error_code', v_latest_in_window.error_code);
elsif p_now > v_expected_next + make_interval(secs => v_grace) and v_latest_in_window.run_at is null then
v_state := 'missed';
v_state_reason := 'no runs in window';
v_latest_details := jsonb_build_object('grace_seconds', v_grace);
elsif v_latest_obs.run_at is not null and v_latest_obs.ok then
if p_latency_budget_ms is not null and v_latest_obs.latency_ms is not null and v_latest_obs.latency_ms > p_latency_budget_ms then
v_state := 'degraded';
else
v_state := 'healthy';
end if;
v_state_reason := 'latest ok run (' || v_state::text || ')';
v_latest_details := jsonb_build_object('http_status', v_latest_obs.http_status, 'latency_ms', v_latest_obs.latency_ms);
elsif v_latest_obs.run_at is not null and not v_latest_obs.ok then
-- JEG-414: the latest run failed but sits before the next run's window;
-- a failing check must read red ('error'), never 'unknown'.
v_state := 'error';
v_state_reason := 'latest run failed';
v_latest_details := jsonb_build_object('http_status', v_latest_obs.http_status, 'latency_ms', v_latest_obs.latency_ms, 'error_code', v_latest_obs.error_code);
else
v_state := 'unknown';
v_state_reason := 'no observations yet';
v_latest_details := jsonb_build_object('grace_seconds', v_grace);
end if;
return query select v_state, v_state_reason, v_expected_next, v_latest_obs.run_at,
(select max(run_at) from monitoring.v_check_observations where check_id = p_check_id and ok),
(select max(run_at) from monitoring.v_check_observations where check_id = p_check_id and not ok),
v_ownership_status, coalesce(v_scheduler_down, false), v_latest_details;
end;
$function$;

-- 4. One call for the 6-hourly producer: record pg_cron history, evaluate,
--    return the summary. service_role only.
grant execute on function monitoring.record_cron_observations() to service_role;

create or replace function public.monitoring_refresh_summary()
 returns jsonb
 language plpgsql
 volatile
 security definer
 set search_path to 'monitoring', 'public', 'cron', 'pg_temp'
as $function$
begin
  perform monitoring.record_cron_observations();
  perform monitoring.run_evaluator_cycle(now());
  return public.monitoring_summary();
end;
$function$;
revoke execute on function public.monitoring_refresh_summary() from public, anon, authenticated;
grant execute on function public.monitoring_refresh_summary() to service_role;

-- record_cron_observations looks back only 1 hour when a check has no pg_cron
-- observation yet; with a 6-hour caller that misses the daily retention run.
-- Look back one day instead (the remaining mapped job, cron-retention-30d, is daily).
create or replace function monitoring.record_cron_observations()
 returns integer
 language plpgsql
 security definer
 set search_path to 'monitoring', 'cron', 'public', 'pg_temp'
as $function$
declare v_n integer;
begin
  insert into monitoring.check_observations (check_id, run_at, ok, error_code, source)
  select m.check_id, d.start_time, d.status = 'succeeded',
         case when d.status = 'succeeded' then null else 'cron_' || d.status end,
         'pg_cron'
  from monitoring.cron_check_map m
  join cron.job j on j.jobname = m.jobname
  join cron.job_run_details d on d.jobid = j.jobid
  where d.status in ('succeeded', 'failed')
    and d.start_time > coalesce(
          (select max(o.run_at) from monitoring.check_observations o
            where o.check_id = m.check_id and o.source = 'pg_cron'),
          now() - interval '1 day');
  get diagnostics v_n = row_count;
  return v_n;
end;
$function$;
revoke execute on function monitoring.record_cron_observations() from public, anon, authenticated;
grant execute on function monitoring.record_cron_observations() to service_role;

-- 5. Security posture as numbers (the Supabase advisor's security lints that
--    matter here). ok=false on any regression; api.* definer views are the
--    accepted, read-only front-end surface and are reported, not failed.
create or replace function public.monitoring_security_posture()
 returns jsonb
 language sql
 stable
 security definer
 set search_path to 'pg_catalog', 'pg_temp'
as $function$
with
no_rls as (
  select n.nspname || '.' || c.relname as obj
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname in ('public', 'monitoring') and c.relkind in ('r', 'p') and not c.relrowsecurity
),
writes as (
  select distinct n.nspname || '.' || c.relname || ' (' || r.rolname || ')' as obj
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  cross join (values ('anon'), ('authenticated')) as r(rolname)
  where n.nspname in ('public', 'api', 'monitoring') and c.relkind in ('r', 'p', 'v', 'm')
    and (has_table_privilege(r.rolname, c.oid, 'INSERT') or has_table_privilege(r.rolname, c.oid, 'UPDATE')
         or has_table_privilege(r.rolname, c.oid, 'DELETE') or has_table_privilege(r.rolname, c.oid, 'TRUNCATE'))
),
definer_views as (
  select n.nspname as nsp, n.nspname || '.' || c.relname as obj
  from pg_class c join pg_namespace n on n.oid = c.relnamespace
  where n.nspname in ('public', 'api') and c.relkind = 'v'
    and not coalesce(c.reloptions && array['security_invoker=true', 'security_invoker=on', 'security_invoker=1'], false)
),
mutable_path as (
  select n.nspname || '.' || p.proname as obj
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  where n.nspname in ('public', 'api', 'monitoring')
    and not exists (select 1 from pg_depend d where d.objid = p.oid and d.deptype = 'e')
    and not exists (select 1 from unnest(coalesce(p.proconfig, '{}')) cfg where cfg like 'search_path=%')
),
anon_secdef as (
  select n.nspname || '.' || p.proname as obj
  from pg_proc p join pg_namespace n on n.oid = p.pronamespace
  where n.nspname in ('public', 'api', 'monitoring') and p.prosecdef
    and (has_function_privilege('anon', p.oid, 'EXECUTE') or has_function_privilege('authenticated', p.oid, 'EXECUTE'))
)
select jsonb_build_object(
  'schema', 'ddf-security-posture-v1',
  'checked_at', now(),
  'tables_without_rls', (select count(*) from no_rls),
  'anon_or_auth_write_grants', (select count(*) from writes),
  'public_definer_views', (select count(*) from definer_views where nsp = 'public'),
  'mutable_search_path_functions', (select count(*) from mutable_path),
  'anon_executable_definer_functions', (select count(*) from anon_secdef),
  'api_definer_views_accepted', (select count(*) from definer_views where nsp = 'api'),
  'ok', (select count(*) from no_rls) = 0 and (select count(*) from writes) = 0
        and (select count(*) from definer_views where nsp = 'public') = 0
        and (select count(*) from mutable_path) = 0 and (select count(*) from anon_secdef) = 0,
  'details', jsonb_build_object(
    'tables_without_rls', (select coalesce(jsonb_agg(obj order by obj), '[]') from (select obj from no_rls limit 25) x),
    'anon_or_auth_write_grants', (select coalesce(jsonb_agg(obj order by obj), '[]') from (select obj from writes limit 25) x),
    'public_definer_views', (select coalesce(jsonb_agg(obj order by obj), '[]') from (select obj from definer_views where nsp = 'public' limit 25) x),
    'mutable_search_path_functions', (select coalesce(jsonb_agg(obj order by obj), '[]') from (select obj from mutable_path limit 25) x),
    'anon_executable_definer_functions', (select coalesce(jsonb_agg(obj order by obj), '[]') from (select obj from anon_secdef limit 25) x)))
$function$;
revoke execute on function public.monitoring_security_posture() from public, anon, authenticated;
grant execute on function public.monitoring_security_posture() to service_role;

commit;
