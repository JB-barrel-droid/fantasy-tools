-- Migration: schema-level per-stat provenance on projection_snapshots
-- (user-approved 2026-09-17).
--
-- Run this in the Supabase SQL editor. Idempotent: safe to re-run.
--
-- Background: the FDS labeled fallback recomputes fantasy points locally
-- from First Down Studio's vegas-attributed translated stats only.
-- Rows, signals, QA, and dashboard bundles already carry per-stat
-- provenance; these columns make it durable at the snapshot level too.
-- Local-book rows keep NULL here (their provenance is the raw odds legs
-- in odds_history / engine.vegas, never fabricated from FDS).

alter table projection_snapshots
  add column if not exists vegas_stats_used jsonb,
  add column if not exists fds_stat_sources jsonb,
  add column if not exists fds_projection_stats jsonb;

comment on column projection_snapshots.vegas_stats_used is
  'FDS-leg rows only: the vegas-attributed translated stats (stat -> value) '
  'that fed this row''s Vegas leg. Never a projection-attributed stat.';
comment on column projection_snapshots.fds_stat_sources is
  'FDS-leg rows only: per-stat attribution from the FDS payload '
  '(stat -> ''vegas'' | ''projection'').';
comment on column projection_snapshots.fds_projection_stats is
  'FDS-leg rows only: projection-attributed FDS stats (stat -> value), '
  'kept labeled and separate. Never feed a Vegas column.';
