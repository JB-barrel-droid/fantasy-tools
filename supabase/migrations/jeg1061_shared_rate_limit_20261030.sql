-- JEG-1061 (2026-10-30): a get-values compute limit that holds across function
-- instances. NOT APPLIED by the authoring session: Jeremy approves it, then it
-- is applied with apply_migration (name: jeg1061_shared_rate_limit_20261030).
-- Rollback: supabase/rollbacks/jeg1061_shared_rate_limit_rollback_20261030.sql
--
-- Nothing reads or writes these objects until the get-values function secret
-- DDF_SHARED_RATE_LIMIT is set to 1 (supabase/functions/get-values/rate-limit.ts).
-- Applying this alone changes no behaviour.
--
-- One row per keyed hash (HMAC-SHA-256 of the caller's key under the service
-- role key, so no IP can be recovered from the table) with a fixed window, as
-- the in-memory limiter keeps it. edge_rate_hit counts one hit atomically and
-- says whether it is within the limit. It runs with the caller's rights
-- (security invoker) and an empty search_path; only service_role (the edge
-- function) may call it or touch the table. RLS is on with no policies.

create table if not exists public.edge_rate_buckets (
  bucket text primary key,
  window_start timestamptz not null default now(),
  hits integer not null default 0
);

alter table public.edge_rate_buckets enable row level security;
revoke all on table public.edge_rate_buckets from public, anon, authenticated;
grant select, insert, update, delete on table public.edge_rate_buckets to service_role;

create or replace function public.edge_rate_hit(p_bucket text, p_limit integer, p_window_s integer)
returns boolean
language plpgsql
security invoker
set search_path = ''
as $$
declare
  n integer;
  win interval;
begin
  if p_bucket is null or pg_catalog.length(p_bucket) = 0 or pg_catalog.length(p_bucket) > 128
     or p_limit is null or p_limit < 1 or p_window_s is null or p_window_s < 1 or p_window_s > 3600 then
    raise exception 'edge_rate_hit: bad arguments';
  end if;
  win := pg_catalog.make_interval(secs => p_window_s::double precision);

  insert into public.edge_rate_buckets as b (bucket, window_start, hits)
  values (p_bucket, pg_catalog.now(), 1)
  on conflict (bucket) do update
    set hits = case when b.window_start <= pg_catalog.now() - win then 1 else b.hits + 1 end,
        window_start = case when b.window_start <= pg_catalog.now() - win then pg_catalog.now()
                            else b.window_start end
  returning hits into n;

  -- Keep the table small: now and then, drop windows that ended over an hour ago.
  if pg_catalog.random() < 0.02 then
    delete from public.edge_rate_buckets where window_start < pg_catalog.now() - interval '1 hour';
  end if;

  return n <= p_limit;
end;
$$;

revoke all on function public.edge_rate_hit(text, integer, integer) from public, anon, authenticated;
grant execute on function public.edge_rate_hit(text, integer, integer) to service_role;

notify pgrst, 'reload schema';
