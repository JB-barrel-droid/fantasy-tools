-- Refresh cadence, part 1 of 2: probe state and log tables (refresh-cadence
-- lane, 2026-10-08). APPLIED by the integrator on 2026-10-08 as migration
-- source_probe_tables_20261008. Part 2 (schedules, retired timers, monitored
-- checks) is source_probe_schedules_20261008.sql. Idempotent.

begin;

-- 1. Probe state (one row per source) and probe log (one row per probe).
create table if not exists public.source_probe_state (
    source         text primary key,
    last_probe_at  timestamptz,
    last_ok        boolean,
    last_fp        text,
    last_signals   jsonb not null default '{}'::jsonb,
    last_error     text,
    last_action    text,
    last_reason    text,
    acked_fp       text,
    acked_at       timestamptz,
    dispatched_fp  text,
    dispatched_at  timestamptz,
    attempts       integer not null default 0,
    updated_at     timestamptz not null default now()
);
alter table public.source_probe_state enable row level security;
revoke all on public.source_probe_state from anon, authenticated;

create table if not exists public.source_probe_log (
    id           bigserial primary key,
    source       text not null,
    probed_at    timestamptz not null,
    ok           boolean not null,
    fingerprint  text,
    signals      jsonb not null default '{}'::jsonb,
    error        text,
    action       text,
    reason       text
);
create index if not exists source_probe_log_source_idx
    on public.source_probe_log (source, probed_at desc);
alter table public.source_probe_log enable row level security;
revoke all on public.source_probe_log from anon, authenticated;

commit;
