-- Migration: sleeper_season_latest_norm
-- Purpose: replace fp_season_latest_norm as the FP-fill leg of
--          v_blended_season_vorp. Full-season ECR is exiting the project
--          (owner directive 2026-10-05); the view now pulls season
--          projections from Sleeper (https://api.sleeper.app/projections/nfl/2026,
--          company "rotowire" at verification time) instead of FantasyPros.
--
-- The 7 granular stat columns, the player_norm PK, the snapshot_date, and the
-- position+team columns match the old fp_season_latest_norm shape exactly --
-- v_blended_season_vorp's per-stat COALESCE references (passing_yards,
-- passing_tds, ...) need no change. The extra columns (sleeper_player_id,
-- company, source) are audit-only.
--
-- Writer: pipeline/bin/pull_sleeper_season_projections.py writes CSV to
-- pipeline/data/sleeper_season_projections.csv; pipeline/bin/build_blended_vorp_inputs.py
-- loads that CSV into this table.
--
-- Apply via the Supabase SQL editor (Roman). This file is NOT auto-applied.

CREATE TABLE IF NOT EXISTS sleeper_season_latest_norm (
  player_norm        text PRIMARY KEY,
  sleeper_player_id  text,                 -- Sleeper player_id (string); audit-only
  snapshot_date      date NOT NULL,
  position           text,
  team               text,
  passing_yards      double precision,     -- <- Sleeper pass_yd  (NULL if not projected)
  passing_tds        double precision,     -- <- Sleeper pass_td  (NULL if not projected)
  rushing_yards      double precision,     -- <- Sleeper rush_yd  (NULL if not projected)
  rushing_tds        double precision,     -- <- Sleeper rush_td  (NULL if not projected)
  receiving_yards    double precision,     -- <- Sleeper rec_yd   (NULL if not projected)
  receiving_tds      double precision,     -- <- Sleeper rec_td   (NULL if not projected)
  receptions         double precision,     -- <- Sleeper rec      (NULL if not projected)
  company            text,                 -- expect 'rotowire'; log WARN if not
  pulled_at            timestamp        DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_sleeper_season_latest_norm_position
  ON sleeper_season_latest_norm (position);

-- Canonical identity map: replaces blended_player_map as the view's
-- player_norm -> display/position/team leg. Sourced from the Sleeper pull
-- (sleeper_player_id PK) joined through the canonical identity files.
-- Writer: pipeline/bin/build_blended_vorp_inputs.py materializes this table.
CREATE TABLE IF NOT EXISTS player_canonical_map (
  player_norm        text PRIMARY KEY,
  display_name       text,
  position           text,
  team               text,
  sleeper_player_id  text,
  has_vegas          boolean NOT NULL DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_player_canonical_map_sleeper_id
  ON player_canonical_map (sleeper_player_id);

-- Note: NULL != 0 here. The view's COALESCE(Vegas, FP-fills-elsewhere) logic
-- depends on a real NULL meaning "Sleeper did not project this stat for this
-- player". Coercing NULL to 0 would silently widen the Vegas fill range and
-- break the vegas-fp-tension flag.