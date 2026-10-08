-- APPLIED 2026-10-08 by the integrator (post-merge step of fix/weeks-tidy).
-- publisher_translated_values week-5 rows were written 2026-10-07 (before the
-- Week 5 promotions; CBS "week 5" rows held Week 4 content) and CBS week-4 rows
-- were stamped at the chain week (GAP-VORP-GRAIN-WEEK-LABEL). The chain keeps
-- these grains only as a record; it does not read them for chart values.
-- Copied to archive (2,044 rows: cbs w4 294, cbs w5 294, fantasycalc w5 504,
-- fantasypros w5 465, usatoday w5 487), then deleted from public.
create schema if not exists archive;
create table if not exists archive.publisher_translated_values_stale_20261008 as
  select * from public.publisher_translated_values
   where season = 2026 and (week = 5 or (week = 4 and source = 'cbs'));
revoke all on archive.publisher_translated_values_stale_20261008 from anon, authenticated;
-- guard: archived count must equal the rows deleted (2,044)
delete from public.publisher_translated_values where season = 2026 and (week = 5 or (week = 4 and source = 'cbs'));
