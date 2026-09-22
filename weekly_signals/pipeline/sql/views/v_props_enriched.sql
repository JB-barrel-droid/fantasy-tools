-- v_props_enriched
-- "I can read the odds" view: every odds_history row joined to player, game, teams, sportsbook.
-- Verified columns (2026-09-10):
--   odds_history(game_id,id,line,market,metadata,odds,recorded_at,selection,sportsbook_id)
--   players(active,full_name,id,league_id,metadata,position,team_id)
--   games(away_team_id,home_team_id,id,league_id,metadata,season,starts_at,status,venue,week)
--   teams(abbreviation,city,id,league_id,name)
--   sportsbooks(code,id,name)
-- NOTE: odds_history has no player_id FK; the player link lives in
-- metadata->>'player_id' (uuid into players.id) and metadata->>'player_name'.
-- LEFT JOINs are used because some rows may reference players not yet in players.

CREATE OR REPLACE VIEW v_props_enriched AS
SELECT
    oh.id                                   AS odds_id,
    oh.recorded_at,
    oh.market,
    oh.selection,
    oh.line,
    oh.odds,
    oh.metadata->>'player_name'             AS book_player_name,
    oh.metadata->>'bookmaker'               AS bookmaker_key,
    oh.metadata->>'event_id'                AS provider_event_id,
    p.id                                    AS player_id,
    p.full_name                             AS player_name,
    p.position,
    pt.abbreviation                         AS player_team,
    g.id                                    AS game_id,
    g.season,
    g.week,
    g.starts_at,
    g.status                                AS game_status,
    ht.abbreviation                         AS home_team,
    at.abbreviation                         AS away_team,
    sb.code                                 AS sportsbook_code,
    sb.name                                 AS sportsbook_name
FROM odds_history oh
LEFT JOIN players p
       ON p.id = NULLIF(oh.metadata->>'player_id', '')::uuid
LEFT JOIN teams pt
       ON pt.id = p.team_id
LEFT JOIN games g
       ON g.id = oh.game_id
LEFT JOIN teams ht
       ON ht.id = g.home_team_id
LEFT JOIN teams at
       ON at.id = g.away_team_id
LEFT JOIN sportsbooks sb
       ON sb.id = oh.sportsbook_id;
