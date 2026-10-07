-- v_player_week_projections
-- Latest projection snapshot per (player, game, source, scoring_format).
--
-- ASSUMED (table did not exist as of 2026-09-10; written against the documented design):
--   projection_snapshots(batch_id, player_id, game_id, season, week, source,
--                        scoring_format, projected_points, ecr_rank, vegas_rank,
--                        snapshot_at, vintage_note)
--   source values: 'vegas_implied' | 'fantasypros' | 'pinnacle_implied' |
--                  'dfs_implied'  ('espn' rows are legacy; nothing new writes them)
--   scoring_format values: 'standard' | 'half_ppr' | 'full_ppr'
-- If the real table differs, adjust the column list below; the DISTINCT ON pattern stays.
--
-- Verified columns used from other tables:
--   players(id,full_name,position,team_id), teams(id,abbreviation),
--   games(id,season,week,starts_at,status,home_team_id,away_team_id)

CREATE OR REPLACE VIEW v_player_week_projections AS
WITH latest AS (
    SELECT DISTINCT ON (ps.player_id, ps.game_id, ps.source, ps.scoring_format)
           ps.player_id,
           ps.game_id,
           ps.season,
           ps.week,
           ps.source,
           ps.scoring_format,
           ps.projected_points,
           ps.ecr_rank,
           ps.vegas_rank,
           ps.batch_id,
           ps.snapshot_at,
           ps.vintage_note
    FROM projection_snapshots ps
    ORDER BY ps.player_id, ps.game_id, ps.source, ps.scoring_format, ps.snapshot_at DESC
)
SELECT
    l.player_id,
    p.full_name                              AS player_name,
    p.position,
    pt.abbreviation                          AS player_team,
    l.game_id,
    l.season,
    l.week,
    g.starts_at,
    g.status                                 AS game_status,
    ht.abbreviation                          AS home_team,
    at.abbreviation                          AS away_team,
    l.source,
    l.scoring_format,
    l.projected_points,
    l.ecr_rank,
    l.vegas_rank,
    l.batch_id,
    l.snapshot_at,
    l.vintage_note
FROM latest l
LEFT JOIN players p  ON p.id = l.player_id
LEFT JOIN teams pt    ON pt.id = p.team_id
LEFT JOIN games g     ON g.id = l.game_id
LEFT JOIN teams ht    ON ht.id = g.home_team_id
LEFT JOIN teams at    ON at.id = g.away_team_id;
