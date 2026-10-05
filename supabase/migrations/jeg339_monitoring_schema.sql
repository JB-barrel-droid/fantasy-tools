-- JEG-339 / JEG-357: monitoring schema for heartbeat state machine.
--
-- Scope: monitoring.* only. No DDL on live_page_checks, public.*, etc.
-- Read-only consumers may map live_page_checks rows via the view at the
-- bottom of this migration; live_page_checks itself is never mutated.
--
-- Run order: this file is self-contained.

begin;

create schema if not exists monitoring;

-- Enum types --------------------------------------------------------------

do $$
begin
    if not exists (select 1 from pg_type where typname = 'heartbeat_state'
                   and typnamespace = 'monitoring'::regnamespace) then
        create type monitoring.heartbeat_state as enum (
            'healthy', 'degraded', 'missed', 'error', 'disabled', 'unknown'
        );
    end if;
end $$;

do $$
begin
    if not exists (select 1 from pg_type where typname = 'check_type'
                   and typnamespace = 'monitoring'::regnamespace) then
        create type monitoring.check_type as enum (
            'http_status', 'http_status_and_content',
            'render_js', 'redirect_ok', 'tls_ok'
        );
    end if;
end $$;

do $$
begin
    if not exists (select 1 from pg_type where typname = 'scheduler_owner_type'
                   and typnamespace = 'monitoring'::regnamespace) then
        create type monitoring.scheduler_owner_type as enum (
            'pg_cron', 'github_actions', 'vercel_cron', 'fly_cron', 'external'
        );
    end if;
end $$;

do $$
begin
    if not exists (select 1 from pg_type where typname = 'ownership_status'
                   and typnamespace = 'monitoring'::regnamespace) then
        create type monitoring.ownership_status as enum (
            'ok', 'ambiguous', 'unknown_owner'
        );
    end if;
end $$;

-- check_config: authoritative schedule + ownership per check ---------------

create table if not exists monitoring.check_config (
    check_id              text primary key,
    enabled               boolean not null default true,
    check_type            monitoring.check_type not null default 'http_status',
    cadence_seconds       integer,
    cron_expr             text,
    grace_override_seconds integer,
    latency_budget_ms     integer,
    scheduler_owner_type  monitoring.scheduler_owner_type not null,
    scheduler_owner_id    text not null,
    alert_policy          jsonb not null default '{}'::jsonb,
    active_ownership_count integer not null default 1,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now(),
    constraint check_config_schedule_xor
        check ( (cadence_seconds is not null)::int
              + (cron_expr is not null)::int = 1 ),
    constraint check_config_grace_override_positive
        check ( grace_override_seconds is null or grace_override_seconds > 0 ),
    constraint check_config_cadence_positive
        check ( cadence_seconds is null or cadence_seconds > 0 )
);

-- scheduler_heartbeats: per-owner heartbeat updated by scheduler processes -

create table if not exists monitoring.scheduler_heartbeats (
    scheduler_owner_type  monitoring.scheduler_owner_type not null,
    scheduler_owner_id    text not null,
    last_seen_at          timestamptz not null,
    down_grace_seconds    integer not null default 300,
    meta                  jsonb not null default '{}'::jsonb,
    primary key (scheduler_owner_type, scheduler_owner_id)
);

-- check_observations: fallback when no live results table exists. Used by
-- staging only; production is wired via the v_check_observations view below.

create table if not exists monitoring.check_observations (
    observation_id        bigserial primary key,
    check_id              text not null references monitoring.check_config(check_id),
    run_at                timestamptz not null,
    ok                    boolean not null,
    latency_ms            integer,
    http_status           integer,
    content_ok            boolean,
    error_code            text,
    source                text not null default 'derived'
);

create unique index if not exists check_observations_dedupe_idx
    on monitoring.check_observations (check_id, run_at);

create index if not exists check_observations_check_run_idx
    on monitoring.check_observations (check_id, run_at desc);

-- check_heartbeats: persisted state per evaluation cycle -------------------

create table if not exists monitoring.check_heartbeats (
    check_id              text primary key,
    state                 monitoring.heartbeat_state not null,
    state_since           timestamptz not null default now(),
    expected_next_run_at  timestamptz,
    last_run_at           timestamptz,
    last_ok_at            timestamptz,
    last_error_at         timestamptz,
    latest_details        jsonb not null default '{}'::jsonb,
    ownership_status      monitoring.ownership_status not null default 'ok',
    scheduler_down        boolean not null default false,
    updated_at            timestamptz not null default now()
);

create index if not exists check_heartbeats_state_idx
    on monitoring.check_heartbeats (state);

-- v_check_observations: read-only mapping layer for live_page_checks.
-- Production reads from public.live_page_checks (read-only).
-- The monitoring.check_observations table is a staging fallback only.
--
-- LIVE SCHEMA (verified 2026-10-04 via PostgREST OpenAPI; table currently
-- empty, so no sample rows / verdict domain to inspect):
--   public.live_page_checks(checked_at timestamptz, url text,
--                           status_code integer, response_ms integer,
--                           verdict text)
--
-- MAPPING CONTRACT (JEG-339 repair 2026-10-04):
--   check_id   = url. The monitored URL IS the check identity: seed
--                monitoring.check_config.check_id with the exact URL strings
--                so the evaluator join matches. Deterministic, no hashing.
--   run_at     = checked_at
--   latency_ms = response_ms
--   http_status= status_code
--   ok         = TRUE only when lower(verdict) is a recognized success token:
--                ('ok','pass','passed','success','successful','healthy','up').
--                FAIL-CLOSED: any other verdict (fail tokens, typos, NULL)
--                maps to FALSE so an uninterpretable observation never reads
--                as healthy. Writers should emit 'ok' / 'fail'-style verdicts.
--   content_ok = NULL. live_page_checks carries no separate content signal;
--                the verdict text is preserved in error_code instead.
--   error_code = NULL when ok; otherwise 'verdict:<verdict>/http_status:<n>'
--                for diagnosis.

create or replace view monitoring.v_check_observations as
select
    lpc.url::text                                  as check_id,
    lpc.checked_at                                 as run_at,
    coalesce(
        lower(lpc.verdict) in
            ('ok','pass','passed','success','successful','healthy','up'),
        false
    )                                              as ok,
    lpc.response_ms::integer                       as latency_ms,
    lpc.status_code::integer                       as http_status,
    null::boolean                                  as content_ok,
    case
        when coalesce(
                 lower(lpc.verdict) in
                     ('ok','pass','passed','success','successful','healthy','up'),
                 false)
            then null
        else ('verdict:' || coalesce(lpc.verdict, 'null')
              || '/http_status:' || coalesce(lpc.status_code::text, 'null'))::text
    end                                            as error_code
from public.live_page_checks lpc
where lpc.url is not null;

-- Evaluator: called by pg_cron every 60s. Re-runnable; uses upsert so reruns
-- are idempotent. Read-only against v_check_observations; writes to
-- monitoring.check_heartbeats only.
--
-- Implementation note: this function delegates the per-row classification to
-- a PL/pgSQL mirror of the Python state machine in
-- pipelines/heartbeat_evaluator.py. Keeping the SQL function narrow (one
-- row at a time) means a future migration can swap it for an Edge Function
-- without changing the contract.

create or replace function monitoring.compute_heartbeat_state(
    p_check_id            text,
    p_enabled             boolean,
    p_cadence_seconds     integer,
    p_cron_expr           text,
    p_grace_override      integer,
    p_latency_budget_ms   integer,
    p_check_type          monitoring.check_type,
    p_owner_type          monitoring.scheduler_owner_type,
    p_owner_id            text,
    p_active_ownership    integer,
    p_now                 timestamptz
)
returns table(
    state                 monitoring.heartbeat_state,
    state_reason          text,
    expected_next_run_at  timestamptz,
    last_run_at           timestamptz,
    last_ok_at            timestamptz,
    last_error_at         timestamptz,
    ownership_status      monitoring.ownership_status,
    scheduler_down        boolean,
    latest_details        jsonb
)
language plpgsql
stable
as $$
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
    -- Global guards
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

    -- Grace policy
    if p_grace_override is not null then
        v_grace := greatest(120, least(1800, p_grace_override));
    elsif p_cadence_seconds is not null then
        v_grace := greatest(120, least(1800, ceil(1.5 * p_cadence_seconds)::int));
    else
        -- Cron grace: spec defers to runtime median; production injects the
        -- value via a wrapper. Default to 600s (10min) when called directly.
        v_grace := 600;
    end if;

    -- Ownership status
    if p_active_ownership <= 0 then
        v_ownership_status := 'unknown_owner';
    elsif p_active_ownership > 1 then
        v_ownership_status := 'ambiguous';
    else
        v_ownership_status := 'ok';
    end if;

    -- Scheduler down
    select coalesce(
        (p_now - h.last_seen_at) > make_interval(secs => h.down_grace_seconds),
        true  -- no heartbeat row → treat as down
    )
    into v_scheduler_down
    from monitoring.scheduler_heartbeats h
    where h.scheduler_owner_type = p_owner_type
      and h.scheduler_owner_id   = p_owner_id;

    -- Latest observation overall
    select * into v_latest_obs
    from monitoring.v_check_observations o
    where o.check_id = p_check_id
    order by o.run_at desc
    limit 1;

    -- Expected next run (fixed cadence only; cron path requires croniter)
    if p_cadence_seconds is not null then
        if v_latest_obs.run_at is null then
            v_expected_next := p_now;
        else
            v_expected_next :=
                v_latest_obs.run_at + make_interval(secs => p_cadence_seconds);
        end if;
    else
        v_expected_next := p_now;  -- cron handled by croniter wrapper
    end if;

    v_window_start := v_expected_next - make_interval(secs => v_grace);

    -- Latest observation inside the missed window
    select * into v_latest_in_window
    from monitoring.v_check_observations o
    where o.check_id = p_check_id
      and o.run_at >= v_window_start
      and o.run_at <= p_now
    order by o.run_at desc
    limit 1;

    -- State transitions (deterministic order)
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
            then 'no runs in window; scheduler_down=true → route to platform'
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
    else
        v_state := 'unknown';
        v_state_reason := 'no observations yet';
        v_latest_details := jsonb_build_object('grace_seconds', v_grace);
    end if;

    return query select
        v_state,
        v_state_reason,
        v_expected_next,
        v_latest_obs.run_at,
        (select max(run_at) from monitoring.v_check_observations
            where check_id = p_check_id and ok),
        (select max(run_at) from monitoring.v_check_observations
            where check_id = p_check_id and not ok),
        v_ownership_status,
        coalesce(v_scheduler_down, false),
        v_latest_details;
end;
$$;

-- Bulk evaluator: iterates every enabled check_config row and upserts the
-- resulting state into monitoring.check_heartbeats. Idempotent.

create or replace function monitoring.run_evaluator_cycle(p_now timestamptz)
returns integer
language plpgsql
as $$
declare
    v_count integer := 0;
    c_check_id text;  -- FOR-loop target below; declared explicitly so the
                      -- per-iteration check identity is unambiguous
    v_state monitoring.heartbeat_state;
    v_reason text;
    v_expected_next timestamptz;
    v_last_run timestamptz;
    v_last_ok timestamptz;
    v_last_err timestamptz;
    v_own monitoring.ownership_status;
    v_down boolean;
    v_details jsonb;
begin
    for c_check_id, v_state, v_reason, v_expected_next, v_last_run, v_last_ok,
        v_last_err, v_own, v_down, v_details in
        select c.check_id, s.state, s.state_reason, s.expected_next_run_at, s.last_run_at,
               s.last_ok_at, s.last_error_at, s.ownership_status,
               s.scheduler_down, s.latest_details
        from monitoring.check_config c
        cross join lateral monitoring.compute_heartbeat_state(
            c.check_id, c.enabled, c.cadence_seconds, c.cron_expr,
            c.grace_override_seconds, c.latency_budget_ms, c.check_type,
            c.scheduler_owner_type, c.scheduler_owner_id,
            c.active_ownership_count, p_now
        ) s
    loop
        insert into monitoring.check_heartbeats(
            check_id, state, state_since, expected_next_run_at,
            last_run_at, last_ok_at, last_error_at,
            latest_details, ownership_status, scheduler_down, updated_at
        )
        values (
            c_check_id,
            v_state, p_now, v_expected_next,
            v_last_run, v_last_ok, v_last_err,
            v_details, v_own, v_down, p_now
        )
        on conflict (check_id) do update set
            state = excluded.state,
            state_since = case
                when monitoring.check_heartbeats.state = excluded.state
                then monitoring.check_heartbeats.state_since
                else p_now
            end,
            expected_next_run_at = excluded.expected_next_run_at,
            last_run_at = excluded.last_run_at,
            last_ok_at = excluded.last_ok_at,
            last_error_at = excluded.last_error_at,
            latest_details = excluded.latest_details,
            ownership_status = excluded.ownership_status,
            scheduler_down = excluded.scheduler_down,
            updated_at = p_now;

        v_count := v_count + 1;
    end loop;

    return v_count;
end;
$$;

-- pg_cron schedule (UNAPPLIED here; LEFT to the approver to schedule).
-- Spec: evaluator should run every 60 seconds.
-- Example (uncommented intentionally — Roman applies the schedule):
--
--   select cron.schedule(
--       'heartbeat-evaluator-v1',
--       '* * * * *',
--       $$select monitoring.run_evaluator_cycle(now());$$
--   );

-- Service-role grants (the cron job runs as postgres; consumers via the
-- PostgREST API need select on the view only).

grant usage on schema monitoring to service_role;
grant select on monitoring.v_check_observations to service_role;
grant select, insert, update on monitoring.check_observations to service_role;
grant select, insert, update on monitoring.check_config to service_role;
grant select, insert, update on monitoring.check_heartbeats to service_role;
grant select, update on monitoring.scheduler_heartbeats to service_role;
grant execute on function monitoring.compute_heartbeat_state(
    text, boolean, integer, text, integer, integer,
    monitoring.check_type, monitoring.scheduler_owner_type, text, integer, timestamptz
) to service_role;
grant execute on function monitoring.run_evaluator_cycle(timestamptz)
    to service_role;

commit;