-- v_latest_signals
-- One row per (player, game): latest Vegas-implied vs expert projections, deltas,
-- position-specific ranks, the post-worthiness flag, actuals (when played), and
-- the current post_queue status.
--
-- ASSUMPTIONS (documented, revisit when the schema grows):
-- 1. projection_snapshots did not exist as of 2026-09-10; columns assumed:
--    (batch_id, player_id, game_id, season, week, source, scoring_format,
--     projected_points, vegas_provenance, vegas_stats_used, fds_stat_sources,
--     fds_projection_stats, ecr_rank, vegas_rank, snapshot_at,
--     vintage_note). vegas_provenance is NULL on rows written before the
--    2026-09-12 completeness gate (fail-closed: NULL never counts as
--    publishable). The three per-stat columns are NULL on local rows and
--    on rows written before the 2026-09-17 FDS per-stat migration.
-- 2. No signals table exists yet. Signals are computed in-memory by
--    engine/disagreement.py; only drafts land in post_queue with signal_id NULL.
--    The queue join below parses the player name out of post_queue.note, which
--    follows the convention "v4 | <Full Name> <TEAM> <POS> | ...".
--    When a real signals table exists, rebuild this view over it and drop the
--    note-parsing CTE.
-- 3. Expert source is 'fantasypros' (the ECR feed's expert point
--    projections). 2026-09-12: ESPN rows are ignored — ESPN-sourced expert
--    points produce nothing anymore.
-- 4. Post-worthy gates encode the v4 rules on full PPR: |pts delta| >= 2.0
--    and at least one side clears the positional floor
--    (QB 10.0 / RB 7.0 / WR 7.0 / TE 5.0), AND the Vegas row's completeness
--    provenance is 'complete' or 'td-filled' (2026-09-12 user directive:
--    never publish a Vegas number whose full value can't be computed;
--    'partial' rows are informational only). The rank gap is informational
--    only (2026-09-11: rank-gap >= 8 gate eliminated by user directive).
-- 5. Actuals are recomputed from player_game_stats.stats components in all three
--    formats; the stored fantasy_points column is ignored (scoring basis unknown).

CREATE OR REPLACE VIEW v_latest_signals AS
WITH latest AS (
    SELECT DISTINCT ON (ps.player_id, ps.game_id, ps.source, ps.scoring_format)
           ps.player_id,
           ps.game_id,
           ps.season,
           ps.week,
           ps.source,
           ps.scoring_format,
           ps.projected_points,
           ps.vegas_provenance,
           ps.vegas_stats_used,
           ps.fds_stat_sources,
           ps.fds_projection_stats,
           ps.ecr_rank,
           ps.vegas_rank,
           ps.snapshot_at,
           ps.vintage_note
    FROM projection_snapshots ps
    ORDER BY ps.player_id, ps.game_id, ps.source, ps.scoring_format, ps.snapshot_at DESC
),
fmt AS (
    SELECT player_id, game_id, season, week, source,
           MAX(snapshot_at)  AS snapshot_at,
           MAX(vintage_note) AS vintage_note,
           MAX(vegas_provenance) AS vegas_provenance,
           -- identical across the three scoring rows of a batch (same
           -- inputs); MAX is deterministic here. jsonb has no MAX aggregate,
           -- so cast through text (2026-09-17: as applied).
           MAX(vegas_stats_used::text)::jsonb AS vegas_stats_used,
           MAX(fds_stat_sources::text)::jsonb AS fds_stat_sources,
           MAX(fds_projection_stats::text)::jsonb AS fds_projection_stats,
           MAX(projected_points) FILTER (WHERE scoring_format = 'full_ppr') AS pts_ppr,
           MAX(projected_points) FILTER (WHERE scoring_format = 'half_ppr') AS pts_half,
           MAX(projected_points) FILTER (WHERE scoring_format = 'standard') AS pts_std,
           MAX(ecr_rank)   FILTER (WHERE scoring_format = 'full_ppr') AS ecr_rank,
           MAX(vegas_rank) FILTER (WHERE scoring_format = 'full_ppr') AS vegas_rank
    FROM latest
    GROUP BY player_id, game_id, season, week, source
),
v AS (
    SELECT * FROM fmt WHERE source = 'vegas_implied'
),
e AS (
    -- the ECR feed is the expert leg; ESPN rows are excluded
    SELECT DISTINCT ON (f.player_id, f.game_id) f.*
    FROM fmt f
    WHERE f.source = 'fantasypros'
    ORDER BY f.player_id, f.game_id
),
parsed_queue AS (
    -- bridge until a signals table exists: player name parsed from the draft note
    SELECT pq.id, pq.post_type, pq.status, pq.created_at, pq.scheduled_for, pq.posted_at,
           regexp_replace(
               split_part(pq.note, ' | ', 2),
               '\s+[A-Z]{2,3}\s+(QB|RB|WR|TE|K|DST)$', ''
           ) AS note_player_name,
           ROW_NUMBER() OVER (
               PARTITION BY regexp_replace(
                   split_part(pq.note, ' | ', 2),
                   '\s+[A-Z]{2,3}\s+(QB|RB|WR|TE|K|DST)$', ''
               )
               ORDER BY pq.created_at DESC
           ) AS rn
    FROM post_queue pq
    WHERE pq.note LIKE '% | %'
)
SELECT
    v.player_id,
    p.full_name                              AS player_name,
    p.position,
    pt.abbreviation                          AS player_team,
    v.game_id,
    v.season,
    v.week,
    g.starts_at,
    g.status                                 AS game_status,
    ht.abbreviation                          AS home_team,
    at.abbreviation                          AS away_team,
    v.snapshot_at                            AS vegas_snapshot_at,
    e.snapshot_at                            AS expert_snapshot_at,
    e.source                                 AS expert_source,
    v.pts_ppr                                AS vegas_ppr,
    e.pts_ppr                                AS expert_ppr,
    v.pts_ppr - e.pts_ppr                    AS pts_delta_ppr,
    v.pts_half                               AS vegas_half,
    e.pts_half                               AS expert_half,
    v.pts_half - e.pts_half                  AS pts_delta_half,
    v.pts_std                                AS vegas_std,
    e.pts_std                                AS expert_std,
    v.pts_std - e.pts_std                    AS pts_delta_std,
    v.vegas_provenance                       AS vegas_provenance,
    v.vegas_rank,
    e.ecr_rank,
    e.ecr_rank - v.vegas_rank                AS rank_gap,        -- >0 means Vegas ranks the player higher
    ABS(e.ecr_rank - v.vegas_rank)           AS abs_rank_gap,
    CASE WHEN (v.pts_ppr - e.pts_ppr) > 0 THEN 'vegas_high'
         WHEN (v.pts_ppr - e.pts_ppr) < 0 THEN 'experts_high' END AS lean,
    COALESCE(
        ABS(v.pts_ppr - e.pts_ppr) >= 2.0
        AND GREATEST(v.pts_ppr, e.pts_ppr) >= CASE p.position
                                                 WHEN 'QB' THEN 10.0
                                                 WHEN 'RB' THEN 7.0
                                                 WHEN 'WR' THEN 7.0
                                                 WHEN 'TE' THEN 5.0
                                                 ELSE 0
                                             END
        AND COALESCE(v.vegas_provenance, '') IN ('complete', 'td-filled'),
        false
    )                                        AS post_worthy,
    -- actuals recomputed from components (all three formats)
    COALESCE((pgs.stats->>'passing_yards')::numeric, 0) / 25
      + COALESCE((pgs.stats->>'passing_tds')::numeric, 0) * 4
      - COALESCE((pgs.stats->>'interceptions')::numeric, 0) * 2
      + COALESCE((pgs.stats->>'rushing_yards')::numeric, 0) / 10
      + COALESCE((pgs.stats->>'rushing_tds')::numeric, 0) * 6
      + COALESCE((pgs.stats->>'receiving_yards')::numeric, 0) / 10
      + COALESCE((pgs.stats->>'receiving_tds')::numeric, 0) * 6
                                             AS actual_std,
    COALESCE((pgs.stats->>'passing_yards')::numeric, 0) / 25
      + COALESCE((pgs.stats->>'passing_tds')::numeric, 0) * 4
      - COALESCE((pgs.stats->>'interceptions')::numeric, 0) * 2
      + COALESCE((pgs.stats->>'rushing_yards')::numeric, 0) / 10
      + COALESCE((pgs.stats->>'rushing_tds')::numeric, 0) * 6
      + COALESCE((pgs.stats->>'receiving_yards')::numeric, 0) / 10
      + COALESCE((pgs.stats->>'receiving_tds')::numeric, 0) * 6
      + COALESCE((pgs.stats->>'receptions')::numeric, 0) * 0.5
                                             AS actual_half,
    COALESCE((pgs.stats->>'passing_yards')::numeric, 0) / 25
      + COALESCE((pgs.stats->>'passing_tds')::numeric, 0) * 4
      - COALESCE((pgs.stats->>'interceptions')::numeric, 0) * 2
      + COALESCE((pgs.stats->>'rushing_yards')::numeric, 0) / 10
      + COALESCE((pgs.stats->>'rushing_tds')::numeric, 0) * 6
      + COALESCE((pgs.stats->>'receiving_yards')::numeric, 0) / 10
      + COALESCE((pgs.stats->>'receiving_tds')::numeric, 0) * 6
      + COALESCE((pgs.stats->>'receptions')::numeric, 0)
                                             AS actual_ppr,
    pq.post_type                             AS queue_post_type,
    pq.status                                AS queue_status,
    pq.created_at                            AS queue_created_at,
    pq.scheduled_for                         AS queue_scheduled_for,
    pq.posted_at                             AS queue_posted_at,
    -- 2026-09-17 as applied: these three sit at the END of the view, not
    -- after vegas_provenance, because CREATE OR REPLACE cannot reorder
    -- existing view columns (new columns may only be appended). A mid-list
    -- position would require DROP VIEW + CREATE VIEW.
    v.vegas_stats_used,
    v.fds_stat_sources,
    v.fds_projection_stats
FROM v
JOIN e
  ON e.player_id = v.player_id AND e.game_id = v.game_id
LEFT JOIN players p  ON p.id = v.player_id
LEFT JOIN teams pt   ON pt.id = p.team_id
LEFT JOIN games g    ON g.id = v.game_id
LEFT JOIN teams ht   ON ht.id = g.home_team_id
LEFT JOIN teams at   ON at.id = g.away_team_id
LEFT JOIN player_game_stats pgs
       ON pgs.player_id = v.player_id AND pgs.game_id = v.game_id
LEFT JOIN parsed_queue pq
       ON pq.note_player_name = p.full_name AND pq.rn = 1;
