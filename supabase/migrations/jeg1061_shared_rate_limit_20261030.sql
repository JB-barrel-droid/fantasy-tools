-- JEG-1061 (2026-10-30): a get-values compute limit that holds across function
-- instances. NOT APPLIED by the authoring session: Jeremy approves it, then it
-- is applied with apply_migration (name: jeg1061_shared_rate_limit_20261030).
-- Rollback: supabase/rollbacks/jeg1061_shared_rate_limit_rollback_20261030.sql
--
-- Nothing reads or writes these objects until the get-values function secret
-- DDF_SHARED_RATE_LIMIT is set to 1 (supabase/functions/get-values/rate-limit.ts).
-- Applying this alone changes no behaviour.
--
-- One row per hashed key (SHA-256 of the caller's key, so no IP is stored)
-- with a fixed window, as the in-memory limiter keeps it. edge_rate_hit counts
-- one hit atomically and says whether it is within the limit. Only the
-- service role (the edge function) may call it; nobody reads the table
-- through the API (RLS on, no policies, no grants).

create table if not exists public.edge_rate_buckets (
  bucket text primary key,
  window_start timestamptz not null default now(),
  hits integer not null default 0
);

alter table public.edge_rate_buckets enable row level security;
revoke all on table public.edge_rate_buckets from public, anon, authenticated;

create or replace function public.edge_rate_hit(p_bucket text, p_limit integer, p_window_s integer)
returns boolean
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  n integer;
begin
  if p_bucket is null or length(p_bucket) = 0 or length(p_bucket) > 128
     or p_limit is null or p_limit < 1 or p_window_s is null or p_window_s < 1 or p_window_s > 3600 then
    raise exception 'edge_rate_hit: bad arguments';
  end if;

  insert into public.edge_rate_buckets as b (bucket, window_start, hits)
  values (p_bucket, now(), 1)
  on conflict (bucket) do update
    set hits = case when b.window_start <= now() - make_interval(secs => p_window_s) then 1 else b.hits + 1 end,
        window_start = case when b.window_start <= now() - make_interval(secs => p_window_s) then now()
                            else b.window_start end
  returning hits into n;

  -- Keep the table small: now and then, drop windows that ended over an hour ago.
  if random() < 0.02 then
    delete from public.edge_rate_buckets where window_start < now() - interval '1 hour';
  end if;

  return n <= p_limit;
end;
$$;

revoke all on function public.edge_rate_hit(text, integer, integer) from public, anon, authenticated;
grant execute on function public.edge_rate_hit(text, integer, integer) to service_role;

notify pgrst, 'reload schema';
