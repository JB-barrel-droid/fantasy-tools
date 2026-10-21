-- JEG-792 (Jeremy, 2026-10-21: "Self-host on the Mac mini"): retention for the
-- value-check log. NOT APPLIED. Nothing in this repo applies it; Jeremy (or his
-- Mac session) runs it by hand against the database that holds the table.
--
-- Since JEG-792 pipelines/load_value_check.py no longer writes one row per
-- compared value. A run writes ONE gzip CSV (output/value-check-values.csv.gz,
-- uploaded by rebuild-chain.yml in the `value-check` artifact), one summary row
-- in public.value_check_runs (counts, top mismatches in `report`), and at most
-- 500 mismatch rows in public.value_check_values. Nothing on the site reads the
-- table; the api views api.value_check_diff / api.player_values only expose
-- engine/reference values for mismatched cells from now on.
--
-- (The number 011 is the one Jeremy's ticket asked for; sql/migrations already
-- holds 011_rotoballer_trade_values.sql, and these files are applied by hand,
-- not in number order.)

-- 1. ONE-TIME: drop the existing log (about 498 MB, 1.25M rows). The data is
--    reproducible from any chain run and is not migrated to the self-hosted
--    database. run_id cascades from value_check_runs, so truncate the child
--    table only; keep value_check_runs (small).
--    Run once, by hand, in the cloud project before its export:
--
--      truncate table public.value_check_values;
--      vacuum full public.value_check_values;   -- returns the disk space
--
--    On the self-hosted database the table starts empty: skip this step.

-- 2. Recurring retention: per-value rows older than 14 days.
create or replace function public.value_check_prune(keep interval default interval '14 days')
returns bigint
language plpgsql
security invoker
as $$
declare
  n bigint;
begin
  delete from public.value_check_values where updated_at < now() - keep;
  get diagnostics n = row_count;
  return n;
end;
$$;

revoke all on function public.value_check_prune(interval) from public, anon, authenticated;
grant execute on function public.value_check_prune(interval) to service_role;

-- Plain form of the same rule (what the function runs):
--   delete from public.value_check_values where updated_at < now() - interval '14 days';

-- 3. pg_cron snippet (run once where pg_cron is installed; daily 04:17 UTC):
--
--   select cron.schedule(
--     'value-check-retention',
--     '17 4 * * *',
--     $$select public.value_check_prune(interval '14 days')$$
--   );
--
--   -- remove: select cron.unschedule('value-check-retention');
