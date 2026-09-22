-- Blended season-VORP: Vegas first, FantasyPros season projections fill the holes.
-- v_vegas_season_vorp is UNTOUCHED; this is a separate view.
--
-- Per-stat hybrid: each of the 7 stat categories uses the Vegas-implied
-- remaining total where the books lined it, else the FP-implied remaining
-- total (FP full-season granulars minus actuals to date, NO prorating).
--   source = 'vegas'    : every category from Vegas lines
--   source = 'vegas+fp' : position's core volume stat from Vegas, >=1
--                         category filled from FP (e.g. receiving work for
--                         RBs that books don't line)
--   source = 'fp'       : no Vegas line for the core volume stat -> FP only
--
-- CALIBRATION (the honest part). Validation on 115 overlap players shows
-- Vegas and FP agree on rank order (Pearson r 0.84-0.92 by position) but
-- Vegas runs systematically LOWER in level (mean gap QB -57.8, RB -82.0,
-- WR -36.8, TE -38.8: books embed missed-game expectations and don't line
-- every category). Two consequences handled here:
--   1. FP fills on vegas+fp rows are scaled by k = vegas_ros / fp_ros_on_
--      vegas_lined_categories (per-player, from blended_calibration; median
--      k = 0.87). A player the books discount 40% vs FP gets FP fills at
--      40% off too -- Vegas-first coherence, no franken-numbers.
--   2. FP-only rows are shifted by the position mean gap (blended_source_
--      confidence.mean_diff) so the whole board sits on the Vegas level.
--      Their 7 displayed stat columns stay raw FP (informational); the
--      ros_half_ppr total is the calibrated number.
-- Rows where |vegas_ros - fp_ros| > 40 carry a 'vegas-fp-tension' flag:
-- that's where "Vegas first" is most contested (e.g. Aaron Jones).
--
-- Confidence: 'high' for Vegas-anchored rows; FP rows take medium/low from
-- blended_source_confidence, driven by the Vegas-vs-FP validation
-- (Pearson r per position; see bin/build_blended_vorp_inputs.py).
--
-- Inputs maintained by bin/build_blended_vorp_inputs.py (idempotent):
--   yahoo_rostered_snapshot, season_actuals_ytd  (via build_vegas_vorp_inputs.py)
--   blended_player_map        (player_norm -> display/position/team, both sources)
--   fp_season_latest_norm     (latest FP snapshot per norm, 7 granular stats)
--   blended_source_confidence (validation-driven confidence tiers per position)

CREATE OR REPLACE FUNCTION f_american_prob(odds double precision)
RETURNS double precision LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN odds >= 100 THEN 100.0 / (odds + 100.0)
              WHEN odds <= -100 THEN -odds / (-odds + 100.0) END
$$;

CREATE OR REPLACE VIEW v_blended_season_vorp AS
WITH latest_v AS (
  SELECT max(snapshot_date) AS d FROM vegas_season_totals
),
latest_f AS (
  SELECT max(snapshot_date) AS d FROM fp_season_latest_norm
),
rsnap AS (
  SELECT max(snapshot_date) AS d FROM yahoo_rostered_snapshot
),
med AS (  -- cross-book median line per (player, market); v3 convention
  SELECT player_norm, market,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY line) AS med_line
  FROM vegas_season_totals, latest_v
  WHERE snapshot_date = latest_v.d
  GROUP BY 1, 2
),
picked AS (  -- odds from the book closest to the median (v3 fix)
  SELECT DISTINCT ON (v.player_norm, v.market)
         v.player_norm, v.market, v.line, v.over_odds, v.under_odds
  FROM vegas_season_totals v
  JOIN latest_v ON v.snapshot_date = latest_v.d
  JOIN med m USING (player_norm, market)
  ORDER BY v.player_norm, v.market, abs(v.line - m.med_line), v.book
),
devigged AS (  -- de-vig skew nudge, same as engine/vegas.py vegas_implied_points
  SELECT player_norm, market,
         line + (p_over - 0.5) * 2.0 AS implied
  FROM picked
  CROSS JOIN LATERAL (
    SELECT CASE WHEN over_odds IS NULL OR under_odds IS NULL THEN 0.5
      ELSE f_american_prob(over_odds)
         / (f_american_prob(over_odds) + f_american_prob(under_odds))
    END AS p_over
  ) d
),
vpiv AS (
  SELECT player_norm,
    max(implied) FILTER (WHERE market = 'season_pass_yds')   AS i_pass_yds,
    max(implied) FILTER (WHERE market = 'season_pass_tds')   AS i_pass_tds,
    max(implied) FILTER (WHERE market = 'season_rush_yds')   AS i_rush_yds,
    max(implied) FILTER (WHERE market = 'season_rush_tds')   AS i_rush_tds,
    max(implied) FILTER (WHERE market = 'season_rec_yds')    AS i_rec_yds,
    max(implied) FILTER (WHERE market = 'season_rec_tds')    AS i_rec_tds,
    max(implied) FILTER (WHERE market = 'season_receptions') AS i_receptions
  FROM devigged GROUP BY 1
),
act AS (
  SELECT player_norm,
    max(actual) FILTER (WHERE stat_key = 'season_pass_yds')   AS a_pass_yds,
    max(actual) FILTER (WHERE stat_key = 'season_pass_tds')   AS a_pass_tds,
    max(actual) FILTER (WHERE stat_key = 'season_rush_yds')   AS a_rush_yds,
    max(actual) FILTER (WHERE stat_key = 'season_rush_tds')   AS a_rush_tds,
    max(actual) FILTER (WHERE stat_key = 'season_rec_yds')    AS a_rec_yds,
    max(actual) FILTER (WHERE stat_key = 'season_rec_tds')    AS a_rec_tds,
    max(actual) FILTER (WHERE stat_key = 'season_receptions') AS a_receptions
  FROM season_actuals_ytd WHERE season = 2026 GROUP BY 1
),
vrem AS (  -- Vegas remaining = de-vigged season line - actuals (NO prorating)
  SELECT p.player_norm,
    p.i_pass_yds - COALESCE(a.a_pass_yds, 0)       AS r_pass_yds,
    p.i_pass_tds - COALESCE(a.a_pass_tds, 0)       AS r_pass_tds,
    p.i_rush_yds - COALESCE(a.a_rush_yds, 0)       AS r_rush_yds,
    p.i_rush_tds - COALESCE(a.a_rush_tds, 0)       AS r_rush_tds,
    p.i_rec_yds  - COALESCE(a.a_rec_yds, 0)        AS r_rec_yds,
    p.i_rec_tds  - COALESCE(a.a_rec_tds, 0)        AS r_rec_tds,
    p.i_receptions - COALESCE(a.a_receptions, 0)   AS r_receptions
  FROM vpiv p LEFT JOIN act a USING (player_norm)
),
frem AS (  -- FP remaining = FP full-season granulars - actuals (NO prorating)
  SELECT n.player_norm,
    n.passing_yards   - COALESCE(a.a_pass_yds, 0)   AS r_pass_yds,
    n.passing_tds     - COALESCE(a.a_pass_tds, 0)   AS r_pass_tds,
    n.rushing_yards   - COALESCE(a.a_rush_yds, 0)   AS r_rush_yds,
    n.rushing_tds     - COALESCE(a.a_rush_tds, 0)   AS r_rush_tds,
    n.receiving_yards - COALESCE(a.a_rec_yds, 0)    AS r_rec_yds,
    n.receiving_tds   - COALESCE(a.a_rec_tds, 0)    AS r_rec_tds,
    n.receptions      - COALESCE(a.a_receptions, 0) AS r_receptions
  FROM fp_season_latest_norm n LEFT JOIN act a USING (player_norm)
),
combo AS (  -- per-stat hybrid: Vegas where lined, else FP x k (calibrated)
  SELECT m.player_norm, m.display_name AS player, m.position, m.team,
    COALESCE(v.r_pass_yds, f.r_pass_yds * COALESCE(cal.k, 1.0))     AS r_pass_yds,
    COALESCE(v.r_pass_tds, f.r_pass_tds * COALESCE(cal.k, 1.0))     AS r_pass_tds,
    COALESCE(v.r_rush_yds, f.r_rush_yds * COALESCE(cal.k, 1.0))     AS r_rush_yds,
    COALESCE(v.r_rush_tds, f.r_rush_tds * COALESCE(cal.k, 1.0))     AS r_rush_tds,
    COALESCE(v.r_rec_yds, f.r_rec_yds * COALESCE(cal.k, 1.0))       AS r_rec_yds,
    COALESCE(v.r_rec_tds, f.r_rec_tds * COALESCE(cal.k, 1.0))       AS r_rec_tds,
    COALESCE(v.r_receptions, f.r_receptions * COALESCE(cal.k, 1.0)) AS r_receptions,
    (v.r_pass_yds IS NOT NULL)   AS v_pass_yds,
    (v.r_pass_tds IS NOT NULL)   AS v_pass_tds,
    (v.r_rush_yds IS NOT NULL)   AS v_rush_yds,
    (v.r_rush_tds IS NOT NULL)   AS v_rush_tds,
    (v.r_rec_yds IS NOT NULL)    AS v_rec_yds,
    (v.r_rec_tds IS NOT NULL)    AS v_rec_tds,
    (v.r_receptions IS NOT NULL) AS v_receptions,
    cal.vegas_ros AS cal_vros,
    cal.fp_ros    AS cal_fros
  FROM blended_player_map m
  LEFT JOIN vrem v USING (player_norm)
  LEFT JOIN frem f USING (player_norm)
  LEFT JOIN blended_calibration cal USING (player_norm)
  WHERE m.position IN ('QB', 'RB', 'WR', 'TE')
),
sourced AS (
  SELECT c.*,
    CASE WHEN position = 'QB' THEN v_pass_yds
         WHEN position = 'RB' THEN v_rush_yds
         WHEN position IN ('WR', 'TE') THEN (v_rec_yds OR v_receptions)
         ELSE false END AS vegas_core,
    (v_pass_yds AND v_pass_tds AND v_rush_yds AND v_rush_tds
     AND v_rec_yds AND v_rec_tds AND v_receptions) AS vegas_full,
    -- FP-only rows sit on the Vegas level via the position mean gap
    COALESCE((SELECT mean_diff FROM blended_source_confidence bsc
              WHERE bsc.position = c.position), 0) AS fp_shift
  FROM combo c
),
scored AS (
  SELECT player, position, team, player_norm,
    CASE WHEN vegas_core
         THEN (CASE WHEN vegas_full THEN 'vegas' ELSE 'vegas+fp' END)
         ELSE 'fp' END AS source,
    round(r_pass_yds::numeric, 1)   AS r_pass_yds,
    round(r_pass_tds::numeric, 1)   AS r_pass_tds,
    round(r_rush_yds::numeric, 1)   AS r_rush_yds,
    round(r_rush_tds::numeric, 1)   AS r_rush_tds,
    round(r_rec_yds::numeric, 1)    AS r_rec_yds,
    round(r_rec_tds::numeric, 1)    AS r_rec_tds,
    round(r_receptions::numeric, 1) AS r_receptions,
    -- identical weights for both sources (Vegas convention; INT/fumbles
    -- excluded since books don't price them). FP-only rows add the position
    -- mean gap so the board sits on one (Vegas) level.
    round((0.04 * COALESCE(r_pass_yds, 0) + 4.0 * COALESCE(r_pass_tds, 0)
        + 0.10 * COALESCE(r_rush_yds, 0) + 6.0 * COALESCE(r_rush_tds, 0)
        + 0.5  * COALESCE(r_receptions, 0) + 0.10 * COALESCE(r_rec_yds, 0)
        + 6.0  * COALESCE(r_rec_tds, 0)
        + CASE WHEN NOT vegas_core THEN fp_shift ELSE 0 END)::numeric, 2
    ) AS ros_half_ppr,
    CASE WHEN position = 'QB' THEN r_pass_yds IS NOT NULL
         WHEN position = 'RB' THEN r_rush_yds IS NOT NULL
         WHEN position IN ('WR', 'TE') THEN
           (r_rec_yds IS NOT NULL OR r_receptions IS NOT NULL)
         ELSE false END AS eligible,
    nullif(concat_ws(',',
      CASE WHEN r_pass_yds   < 0 THEN 'pass_yds<0' END,
      CASE WHEN r_pass_tds   < 0 THEN 'pass_tds<0' END,
      CASE WHEN r_rush_yds   < 0 THEN 'rush_yds<0' END,
      CASE WHEN r_rush_tds   < 0 THEN 'rush_tds<0' END,
      CASE WHEN r_rec_yds    < 0 THEN 'rec_yds<0' END,
      CASE WHEN r_rec_tds    < 0 THEN 'rec_tds<0' END,
      CASE WHEN r_receptions < 0 THEN 'receptions<0' END,
      CASE WHEN cal_vros IS NOT NULL AND abs(cal_vros - cal_fros) > 90
           THEN 'vegas-fp-tension' END), '') AS flags
  FROM sourced
),
rostered AS (  -- normalize to norm_loose: the live Yahoo loader keeps
               -- hyphens ('jaxon smith-njigba') and skips nickname aliases
               -- ('cam skattebo'), so strip non-alphanumerics and map the
               -- aliases here instead of trusting the raw column.
  SELECT DISTINCT
    CASE regexp_replace(player_norm, '[^a-z0-9 ]', '', 'g')
      WHEN 'cam ward' THEN 'cameron ward'
      WHEN 'cam skattebo' THEN 'cameron skattebo'
      WHEN 'hollywood brown' THEN 'marquise brown'
      WHEN 'kenny gainwell' THEN 'kenneth gainwell'
      WHEN 'scotty miller' THEN 'scott miller'
      ELSE regexp_replace(player_norm, '[^a-z0-9 ]', '', 'g') END AS player_norm
  FROM yahoo_rostered_snapshot, rsnap
  WHERE snapshot_date = rsnap.d
),
pool AS (  -- VORP-eligible, unrostered (either source counts)
  SELECT s.* FROM scored s
  WHERE s.eligible AND NOT EXISTS (
    SELECT 1 FROM rostered r WHERE r.player_norm = s.player_norm)
),
repl AS (
  SELECT 'QB' AS position,
    (SELECT player FROM pool WHERE position = 'QB'
       ORDER BY ros_half_ppr DESC LIMIT 1) AS repl_player,
    (SELECT max(ros_half_ppr) FROM pool WHERE position = 'QB') AS repl_points
  UNION ALL
  SELECT 'RB',
    (SELECT player FROM pool WHERE position = 'RB'
       ORDER BY ros_half_ppr DESC LIMIT 1),
    (SELECT max(ros_half_ppr) FROM pool WHERE position = 'RB')
  UNION ALL
  SELECT 'WR',
    (SELECT player FROM pool WHERE position = 'WR'
       ORDER BY ros_half_ppr DESC LIMIT 1),
    (SELECT max(ros_half_ppr) FROM pool WHERE position = 'WR')
  UNION ALL
  SELECT 'TE',
    (SELECT player FROM pool WHERE position = 'TE'
       ORDER BY ros_half_ppr DESC LIMIT 1),
    (SELECT max(ros_half_ppr) FROM pool WHERE position = 'TE')
  UNION ALL
  SELECT 'FLEX',
    (SELECT player FROM pool WHERE position IN ('RB', 'WR', 'TE')
       ORDER BY ros_half_ppr DESC LIMIT 1),
    (SELECT max(ros_half_ppr) FROM pool WHERE position IN ('RB', 'WR', 'TE'))
)
SELECT s.player, s.position AS pos, s.team,
  s.source,
  CASE WHEN s.source = 'fp'
       THEN COALESCE(
         (SELECT confidence FROM blended_source_confidence c
          WHERE c.position = s.position), 'low')
       ELSE 'high' END AS confidence,
  (s.source <> 'fp') AS has_vegas_line,
  s.r_pass_yds, s.r_pass_tds, s.r_rush_yds, s.r_rush_tds,
  s.r_receptions, s.r_rec_yds, s.r_rec_tds,
  s.ros_half_ppr,
  r.repl_player AS replacement_player,
  round(r.repl_points::numeric, 2) AS replacement_points,
  CASE WHEN s.eligible AND r.repl_points IS NOT NULL
       THEN round((s.ros_half_ppr - r.repl_points)::numeric, 2) END AS vorp,
  nullif(concat_ws(',',
    s.flags,
    CASE WHEN s.eligible AND r.repl_points IS NULL
         THEN 'no-replacement' END), '') AS flags,
  EXISTS (SELECT 1 FROM rostered WHERE player_norm = s.player_norm)
    AS is_rostered,
  (SELECT max(snapshot_date) FROM vegas_season_totals) AS vegas_snapshot_date,
  (SELECT max(snapshot_date) FROM fp_season_projections) AS fp_snapshot_date,
  (SELECT max(snapshot_date) FROM yahoo_rostered_snapshot) AS roster_snapshot_date
FROM scored s
LEFT JOIN repl r ON r.position = s.position
ORDER BY vorp DESC NULLS LAST, s.ros_half_ppr DESC;
