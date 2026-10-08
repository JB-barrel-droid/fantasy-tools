-- APPLIED 2026-10-08 by the integrator (name archive_fp_kdst_20261008).
-- K/DST removed from the product (JEG-211, reconfirmed 2026-10-08). The FantasyPros
-- K/DST projections table (66 rows) and its view had no reader in the repo or the
-- database; archived (moved to schema archive), not deleted.
-- public.player_name_aliases was kept: public.player_identity_unresolved_v depends
-- on it and pipelines/build_ops_status.py reads that view (identity review queue).
create schema if not exists archive;
revoke all on schema archive from anon, authenticated;
alter view public.v_fp_season_kdst_latest set schema archive;
alter table public.fp_season_kdst_projections set schema archive;
revoke all on all tables in schema archive from anon, authenticated;
notify pgrst, 'reload schema';
