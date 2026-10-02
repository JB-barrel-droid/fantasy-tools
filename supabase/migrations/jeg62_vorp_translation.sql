-- JEG-62: VORP translation Supabase schema
-- Keeps publisher assumptions, VORP, and translated values in Supabase

-- 1. Publisher roster assumptions (per source/scoring/teams/week)
-- Stores the roster math that dictates waiver lines
CREATE TABLE IF NOT EXISTS publisher_roster_assumptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,           -- usatoday, fantasypros, fantasycalc, cbs
    scoring TEXT NOT NULL,          -- standard, half_ppr, ppr
    league_teams INT NOT NULL,      -- 10, 12, 14
    week INT NOT NULL,              -- NFL week
    season INT NOT NULL DEFAULT 2026,
    position TEXT NOT NULL,         -- QB, RB, WR, TE
    n_dedicated INT NOT NULL,       -- teams × slots
    n_flex INT NOT NULL,            -- allocated flex
    n_bench INT NOT NULL,           -- bench spots
    n_rostered INT NOT NULL,        -- dedicated + flex + bench
    waiver_line_value FLOAT NOT NULL,
    waiver_method TEXT NOT NULL,    -- roster_determined, insufficient_coverage
    bench_per_team FLOAT NOT NULL DEFAULT 6.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, scoring, league_teams, week, season, position)
);

-- 2. Publisher VORP values (per player)
-- Their values stripped of roster effects via waiver line
CREATE TABLE IF NOT EXISTS publisher_vorp (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    scoring TEXT NOT NULL,
    league_teams INT NOT NULL,
    week INT NOT NULL,
    season INT NOT NULL DEFAULT 2026,
    player_key TEXT NOT NULL,       -- canonical player key
    position TEXT NOT NULL,
    native_value FLOAT NOT NULL,    -- their published value
    vorp_value FLOAT NOT NULL,      -- native - waiver_line
    pos_rank INT NOT NULL,          -- rank within position
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, scoring, league_teams, week, season, player_key)
);

-- 3. Translated values (our framework)
-- Their VORP scaled through our positional maxes
CREATE TABLE IF NOT EXISTS publisher_translated_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    scoring TEXT NOT NULL,
    league_teams INT NOT NULL,
    week INT NOT NULL,
    season INT NOT NULL DEFAULT 2026,
    player_key TEXT NOT NULL,
    position TEXT NOT NULL,
    translated_value FLOAT NOT NULL,  -- on our 0-70 scale
    scale_factor FLOAT NOT NULL,       -- our_max / their_max_vorp
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source, scoring, league_teams, week, season, player_key)
);

-- Indexes for fast lookup by the chart pipeline
CREATE INDEX IF NOT EXISTS idx_roster_assumptions_lookup
    ON publisher_roster_assumptions(source, scoring, league_teams, week, season);
CREATE INDEX IF NOT EXISTS idx_vorp_lookup
    ON publisher_vorp(source, scoring, league_teams, week, season);
CREATE INDEX IF NOT EXISTS idx_translated_lookup
    ON publisher_translated_values(source, scoring, league_teams, week, season);
