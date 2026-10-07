-- Vegas season-VORP views (pure Vegas; no expert projections anywhere).
-- Refreshes automatically: reads max(snapshot_date) from vegas_season_totals.
-- Inputs maintained by bin/build_vegas_vorp_inputs.py:
--   yahoo_rostered_snapshot (rostered set; 2026-09-11 until Yahoo re-auth)
--   season_actuals_ytd       (nflverse final-game actuals, 2026)
--   vegas_player_map         (player_norm -> position/display/team)

CREATE OR REPLACE FUNCTION f_american_prob(odds double precision)
RETURNS double precision LANGUAGE sql IMMUTABLE AS $$
  SELECT CASE WHEN odds >= 100 THEN 100.0 / (odds + 100.0)
              WHEN odds <= -100 THEN -odds / (-odds + 100.0) END
$$;

CREATE OR REPLACE VIEW v_vegas_season_vorp AS
WITH latest AS (
  SELECT max(snapshot_date) AS d FROM vegas_season_totals
),
rsnap AS (
  SELECT max(snapshot_date) AS d FROM yahoo_rostered_snapshot
),
med AS (  -- cross-book median line per (player, market); v3 convention
  SELECT player_norm, market,
         percentile_cont(0.5) WITHIN GROUP (ORDER BY line) AS med_line
  FROM vegas_season_totals, latest
  WHERE snapshot_date = latest.d
  GROUP BY 1, 2
),
picked AS (  -- odds from the book closest to the median (v3 fix)
  SELECT DISTINCT ON (v.player_norm, v.market)
         v.player_norm, v.market, v.line, v.over_odds, v.under_odds
  FROM vegas_season_totals v
  JOIN latest ON v.snapshot_date = latest.d
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
piv AS (
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
rem AS (  -- remaining implied = season line - actuals to date (NO prorating:
         -- the book's line already embeds availability expectations)
  SELECT m.display_name AS player, m.position, m.team, p.player_norm,
    p.i_pass_yds - COALESCE(a.a_pass_yds, 0)   AS r_pass_yds,
    p.i_pass_tds - COALESCE(a.a_pass_tds, 0)   AS r_pass_tds,
    p.i_rush_yds - COALESCE(a.a_rush_yds, 0)   AS r_rush_yds,
    p.i_rush_tds - COALESCE(a.a_rush_tds, 0)   AS r_rush_tds,
    p.i_rec_yds  - COALESCE(a.a_rec_yds, 0)    AS r_rec_yds,
    p.i_rec_tds  - COALESCE(a.a_rec_tds, 0)    AS r_rec_tds,
    p.i_receptions - COALESCE(a.a_receptions, 0) AS r_receptions,
    p.i_pass_yds IS NOT NULL AS has_pass_yds,
    p.i_rush_yds IS NOT NULL AS has_rush_yds,
    (p.i_rec_yds IS NOT NULL OR p.i_receptions IS NOT NULL) AS has_rec_vol
  FROM piv p
  JOIN vegas_player_map m USING (player_norm)
  LEFT JOIN act a USING (player_norm)
),
scored AS (
  SELECT player, position, team, player_norm,
    round(r_pass_yds::numeric, 1)   AS r_pass_yds,
    round(r_pass_tds::numeric, 1)   AS r_pass_tds,
    round(r_rush_yds::numeric, 1)   AS r_rush_yds,
    round(r_rush_tds::numeric, 1)   AS r_rush_tds,
    round(r_rec_yds::numeric, 1)    AS r_rec_yds,
    round(r_rec_tds::numeric, 1)    AS r_rec_tds,
    round(r_receptions::numeric, 1) AS r_receptions,
    round((0.04 * COALESCE(r_pass_yds, 0) + 4.0 * COALESCE(r_pass_tds, 0)
        + 0.10 * COALESCE(r_rush_yds, 0) + 6.0 * COALESCE(r_rush_tds, 0)
        + 0.5  * COALESCE(r_receptions, 0) + 0.10 * COALESCE(r_rec_yds, 0)
        + 6.0  * COALESCE(r_rec_tds, 0))::numeric, 2) AS ros_half_ppr,
    CASE WHEN position = 'QB' THEN has_pass_yds
         WHEN position = 'RB' THEN has_rush_yds
         WHEN position IN ('WR', 'TE') THEN has_rec_vol
         ELSE false END AS eligible,
    nullif(concat_ws(',',
      CASE WHEN r_pass_yds   < 0 THEN 'pass_yds<0' END,
      CASE WHEN r_pass_tds   < 0 THEN 'pass_tds<0' END,
      CASE WHEN r_rush_yds   < 0 THEN 'rush_yds<0' END,
      CASE WHEN r_rush_tds   < 0 THEN 'rush_tds<0' END,
      CASE WHEN r_rec_yds    < 0 THEN 'rec_yds<0' END,
      CASE WHEN r_rec_tds    < 0 THEN 'rec_tds<0' END,
      CASE WHEN r_receptions < 0 THEN 'receptions<0' END), '') AS flags
  FROM rem
),
rostered AS (
  SELECT DISTINCT player_norm FROM yahoo_rostered_snapshot, rsnap
  WHERE snapshot_date = rsnap.d
),
pool AS (  -- VORP-eligible, unrostered, priced
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
  true AS has_vegas_line,
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
         THEN 'no-priced-replacement' END), '') AS flags,
  EXISTS (SELECT 1 FROM rostered WHERE player_norm = s.player_norm)
    AS is_rostered,
  (SELECT max(snapshot_date) FROM vegas_season_totals) AS vegas_snapshot_date,
  (SELECT max(snapshot_date) FROM yahoo_rostered_snapshot) AS roster_snapshot_date
FROM scored s
LEFT JOIN repl r ON r.position = s.position
ORDER BY vorp DESC NULLS LAST, s.ros_half_ppr DESC;

-- Unpriced notables: rostered skill players with no line on the latest board.
CREATE OR REPLACE VIEW v_vegas_unpriced_watchlist AS
WITH latest AS (
  SELECT max(snapshot_date) AS d FROM vegas_season_totals
),
rsnap AS (
  SELECT max(snapshot_date) AS d FROM yahoo_rostered_snapshot
),
priced AS (
  SELECT DISTINCT player_norm FROM vegas_season_totals, latest
  WHERE snapshot_date = latest.d
)
SELECT r.player_name AS player, r.pos, r.nfl_team AS team,
       r.team_name AS yahoo_team
FROM (yahoo_rostered_snapshot r CROSS JOIN rsnap)
LEFT JOIN priced p USING (player_norm)
WHERE r.snapshot_date = rsnap.d
  AND p.player_norm IS NULL
  AND r.pos IN ('QB', 'RB', 'WR', 'TE')
ORDER BY r.pos, r.player_name;
