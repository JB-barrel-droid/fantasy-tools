-- projection_snapshots: frozen per-week projection vintages (Vegas-implied, FantasyPros, ESPN).
-- Run this in the Supabase SQL editor (same as the v1 schema and post_queue).
-- One row per (batch, player, scoring_format). Batches are immutable; a new
-- pull writes a new batch_id, never updates in place.

create table if not exists projection_snapshots (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null,
  -- references players(id); kept constraint-free so this file runs standalone
  player_id uuid not null,
  -- references games(id); kept constraint-free so this file runs standalone
  game_id uuid not null,
  season int not null,
  week int not null,
  source text not null
    check (source in ('vegas_implied', 'fantasypros', 'espn')),
  scoring_format text not null
    check (scoring_format in ('standard', 'half_ppr', 'full_ppr')),
  projected_points numeric not null,
  ecr_rank int,
  vegas_rank int,
  snapshot_at timestamptz not null,
  vintage_note text,
  -- FDS labeled-fallback per-stat provenance (2026-09-17). NULL on local
  -- rows (their provenance is the raw odds legs) and on rows written
  -- before this migration. Only vegas-attributed stats may appear in
  -- vegas_stats_used; projection-attributed stats stay in
  -- fds_projection_stats, never in a Vegas column.
  vegas_stats_used jsonb,
  fds_stat_sources jsonb,
  fds_projection_stats jsonb,
  created_at timestamptz not null default now()
);

create index if not exists projection_snapshots_week_idx
  on projection_snapshots (season, week, source, scoring_format);

create index if not exists projection_snapshots_player_idx
  on projection_snapshots (player_id, season, week);

create index if not exists projection_snapshots_batch_idx
  on projection_snapshots (batch_id);
