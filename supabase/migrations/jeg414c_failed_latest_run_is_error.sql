-- JEG-414: a check whose latest run FAILED but sits before the next run's
-- window evaluated as 'unknown' ('no observations yet'). A failing check must
-- read red. Applied 2026-10-05 as migration jeg414_failed_latest_run_is_error.

CREATE OR REPLACE FUNCTION monitoring.compute_heartbeat_state(p_check_id text, p_enabled boolean, p_cadence_seconds integer, p_cron_expr text, p_grace_override integer, p_latency_budget_ms integer, p_check_type monitoring.check_type, p_owner_type monitoring.scheduler_owner_type, p_owner_id text, p_active_ownership integer, p_now timestamp with time zone)
RETURNS TABLE(state monitoring.heartbeat_state, state_reason text, expected_next_run_at timestamp with time zone, last_run_at timestamp with time zone, last_ok_at timestamp with time zone, last_error_at timestamp with time zone, ownership_status monitoring.ownership_status, scheduler_down boolean, latest_details jsonb)
LANGUAGE plpgsql
STABLE
AS $function$
declare
v_grace               integer;
v_latest_obs           record;
v_latest_in_window     record;
v_expected_next        timestamptz;
v_window_start         timestamptz;
v_scheduler_down       boolean;
v_ownership_status     monitoring.ownership_status;
v_state                monitoring.heartbeat_state;
v_state_reason         text;
v_latest_details       jsonb;
begin
if not p_enabled then
return query select 'disabled'::monitoring.heartbeat_state,
'enabled=false', null::timestamptz, null::timestamptz,
null::timestamptz, null::timestamptz,
'ok'::monitoring.ownership_status, false, '{}'::jsonb;
return;
end if;
if p_cadence_seconds is null and p_cron_expr is null then
return query select 'unknown'::monitoring.heartbeat_state,
'no schedule resolvable', null::timestamptz, null::timestamptz,
null::timestamptz, null::timestamptz,
'ok'::monitoring.ownership_status, false, '{}'::jsonb;
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
select coalesce(
(p_now - h.last_seen_at) > make_interval(secs => h.down_grace_seconds),
true
)
into v_scheduler_down
from monitoring.scheduler_heartbeats h
where h.scheduler_owner_type = p_owner_type
and h.scheduler_owner_id   = p_owner_id;
select * into v_latest_obs
from monitoring.v_check_observations o
where o.check_id = p_check_id
order by o.run_at desc
limit 1;
if p_cadence_seconds is not null then
if v_latest_obs.run_at is null then
v_expected_next := p_now;
else
v_expected_next :=
v_latest_obs.run_at + make_interval(secs => p_cadence_seconds);
end if;
else
v_expected_next := p_now;
end if;
v_window_start := v_expected_next - make_interval(secs => v_grace);
select * into v_latest_in_window
from monitoring.v_check_observations o
where o.check_id = p_check_id
and o.run_at >= v_window_start
and o.run_at <= p_now
order by o.run_at desc
limit 1;
if v_latest_in_window.run_at is not null and not v_latest_in_window.ok then
v_state := 'error';
v_state_reason := 'failed run in window';
v_latest_details := jsonb_build_object(
'http_status', v_latest_in_window.http_status,
'latency_ms',  v_latest_in_window.latency_ms,
'error_code',  v_latest_in_window.error_code
);
elsif p_now > v_expected_next + make_interval(secs => v_grace)
and v_latest_in_window.run_at is null then
v_state := 'missed';
v_state_reason := case when v_scheduler_down
then 'no runs in window; scheduler_down=true'
else 'no runs in window' end;
v_latest_details := jsonb_build_object('grace_seconds', v_grace);
elsif v_latest_obs.run_at is not null and v_latest_obs.ok then
if p_latency_budget_ms is not null
and v_latest_obs.latency_ms is not null
and v_latest_obs.latency_ms > p_latency_budget_ms then
v_state := 'degraded';
else
v_state := 'healthy';
end if;
v_state_reason := 'latest ok run (' || v_state::text || ')';
v_latest_details := jsonb_build_object(
'http_status', v_latest_obs.http_status,
'latency_ms',  v_latest_obs.latency_ms
);
elsif v_latest_obs.run_at is not null and not v_latest_obs.ok then
-- JEG-414: the latest run failed but sits before the next run's window;
-- a failing check must read red ('error'), never 'unknown'.
v_state := 'error';
v_state_reason := 'latest run failed';
v_latest_details := jsonb_build_object(
'http_status', v_latest_obs.http_status,
'latency_ms',  v_latest_obs.latency_ms,
'error_code',  v_latest_obs.error_code
);
else
v_state := 'unknown';
v_state_reason := 'no observations yet';
v_latest_details := jsonb_build_object('grace_seconds', v_grace);
end if;
return query select
v_state, v_state_reason, v_expected_next, v_latest_obs.run_at,
(select max(run_at) from monitoring.v_check_observations
where check_id = p_check_id and ok),
(select max(run_at) from monitoring.v_check_observations
where check_id = p_check_id and not ok),
v_ownership_status, coalesce(v_scheduler_down, false), v_latest_details;
end;
$function$
;
