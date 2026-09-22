-- Lottery ticket model v0 schema (Phase 1 heuristic MVP).
-- Public schema, no RLS (matches existing project convention).
-- Point-in-time discipline: every row carries as_of / season / week.

-- ---------------------------------------------------------------- league profiles
CREATE TABLE IF NOT EXISTS public.lottery_league_profiles (
    league_profile_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name                text NOT NULL,
    platform            text NOT NULL DEFAULT 'generic',
    season              int  NOT NULL,
    teams               int  NOT NULL,
    scoring             text NOT NULL DEFAULT 'ppr',   -- ppr | half_ppr | standard
    lineup_json         jsonb NOT NULL,                -- {"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1}
    bench_slots         int  NOT NULL DEFAULT 6,
    waiver_type         text NOT NULL DEFAULT 'faab',
    faab_budget         int  NOT NULL DEFAULT 100,
    transaction_limit   int,                            -- NULL = unlimited
    effective_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (name, season)
);
COMMENT ON TABLE public.lottery_league_profiles IS
    'Versioned league contexts for the lottery-ticket model. Replacement level and VORP are computed per profile.';

-- ------------------------------------------------------- point-in-time features
CREATE TABLE IF NOT EXISTS public.lottery_player_features (
    feature_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_id           uuid REFERENCES public.players(id),
    player_key          text NOT NULL,                  -- normalized name fallback
    season              int  NOT NULL,
    week                int  NOT NULL,                  -- feature cutoff week
    as_of               timestamptz NOT NULL DEFAULT now(),
    position            text NOT NULL,
    team                text,
    feature_version     text NOT NULL DEFAULT 'v0',
    -- typed hot columns (role level)
    snap_share          numeric,
    route_share         numeric,                        -- routes / team dropbacks
    target_share        numeric,
    targets_per_route   numeric,
    rush_share          numeric,
    goal_line_share     numeric,
    off_field_opp_share numeric,                        -- next-man-up share: player's share of backfield opps on plays with the incumbent off field
    off_field_snaps     int,
    backfield_hhi       numeric,                        -- backfield concentration
    depth_chart_rank    int,
    air_yard_share      numeric,
    yards_per_route     numeric,
    production_lag      numeric,                        -- role-implied PPR - actual PPR (positive = mispriced)
    role_slope          numeric,                        -- 3-week role trajectory slope (standardized)
    starter_status      text,                           -- healthy | questionable | out | ir
    draft_pick          int,                            -- overall draft pick number
    exp_years           int,
    add_velocity        numeric,                        -- Sleeper trending adds (24h)
    source_freshness_hours numeric,
    is_stale            boolean NOT NULL DEFAULT false,
    feature_json        jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (player_key, season, week, feature_version)
);
CREATE INDEX IF NOT EXISTS ix_lpf_season_week ON public.lottery_player_features (season, week);
CREATE INDEX IF NOT EXISTS ix_lpf_player ON public.lottery_player_features (player_id);

-- ------------------------------------------------------- mechanism predictions
CREATE TABLE IF NOT EXISTS public.lottery_model_runs (
    model_run_id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name      text NOT NULL DEFAULT 'lottery_v0_heuristic',
    model_version   text NOT NULL,
    training_cutoff text,
    feature_version text NOT NULL,
    label_version   text,
    parameters_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    metrics_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.lottery_predictions (
    prediction_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_run_id        uuid REFERENCES public.lottery_model_runs(model_run_id),
    player_id           uuid REFERENCES public.players(id),
    player_key          text NOT NULL,
    league_profile_id   uuid REFERENCES public.lottery_league_profiles(league_profile_id),
    as_of               timestamptz NOT NULL DEFAULT now(),
    mechanism           text NOT NULL,                  -- contingent | emergent | ambiguous | signing
    horizon_weeks       int  NOT NULL,                   -- 1 | 2 | 4 | 6
    breakout_probability numeric NOT NULL,
    lower_80            numeric,
    upper_80            numeric,
    UNIQUE (player_key, league_profile_id, as_of, mechanism, horizon_weeks)
);
CREATE INDEX IF NOT EXISTS ix_lpred_lookup
    ON public.lottery_predictions (league_profile_id, as_of, horizon_weeks, breakout_probability DESC);

-- ------------------------------------------------------- breakout labels (training, v1)
CREATE TABLE IF NOT EXISTS public.lottery_breakout_labels (
    label_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    player_key      text NOT NULL,
    season          int  NOT NULL,
    as_of_week      int  NOT NULL,
    breakout_week   int,                                -- NULL = no breakout within horizon
    weeks_to_breakout int,
    mechanism       text,                               -- contingent | emergent | ambiguous | signing
    sustained_vorp  numeric,
    duration_games  int,
    censored        boolean NOT NULL DEFAULT false,
    label_version   text NOT NULL DEFAULT 'v0',
    UNIQUE (player_key, season, as_of_week, label_version)
);

-- ------------------------------------------------------- final valuations
CREATE TABLE IF NOT EXISTS public.lottery_valuations (
    valuation_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_run_id        uuid REFERENCES public.lottery_model_runs(model_run_id),
    player_id           uuid REFERENCES public.players(id),
    player_key          text NOT NULL,
    league_profile_id   uuid REFERENCES public.lottery_league_profiles(league_profile_id),
    as_of               timestamptz NOT NULL DEFAULT now(),
    position            text NOT NULL,
    team                text,
    current_use_vorp    numeric NOT NULL DEFAULT 0,     -- C_i
    owned_option_ev     numeric NOT NULL DEFAULT 0,     -- sum p*U
    wait_ev             numeric NOT NULL DEFAULT 0,     -- sum p*U*(1-q)
    now_wait_premium    numeric NOT NULL DEFAULT 0,     -- sum p*U*q
    bench_cost          numeric NOT NULL DEFAULT 0,     -- B_i
    option_adjusted_vorp numeric NOT NULL DEFAULT 0,    -- OAV
    lottery_score       numeric NOT NULL DEFAULT 0,     -- 0-10 display
    primary_mechanism   text,
    secondary_mechanism text,
    role_trend          text,                           -- rising | stable | declining
    confidence          text,                           -- High | Medium | Low
    p1                  numeric, p2 numeric, p4 numeric, p6 numeric,
    cond_vorp_pg        numeric,                        -- conditional VORP per game
    cond_vorp_total     numeric,                        -- cumulative conditional VORP
    duration_games      numeric,                        -- expected valuable duration
    acquisition_risk    numeric,                        -- q blended
    ci_low              numeric, ci_high               numeric,  -- 80% OAV interval
    bad_variance_flag   boolean NOT NULL DEFAULT false,
    bad_variance_note   text,
    starter_name        text,                           -- v0.3: named starter whose injury creates the contingent role
    explanation_json    jsonb NOT NULL DEFAULT '{}'::jsonb,
    component_json      jsonb NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (player_key, league_profile_id, as_of)
);
CREATE INDEX IF NOT EXISTS ix_lval_board
    ON public.lottery_valuations (league_profile_id, as_of, option_adjusted_vorp DESC);

-- ------------------------------------------------------- serving view
CREATE OR REPLACE VIEW public.v_lottery_board AS
SELECT
    v.valuation_id, v.as_of, v.player_key,
    COALESCE(p.full_name, v.player_key) AS player_name,
    v.position, v.team,
    v.lottery_score, v.option_adjusted_vorp,
    v.current_use_vorp, v.owned_option_ev, v.wait_ev, v.now_wait_premium,
    v.bench_cost,
    v.p1, v.p2, v.p4, v.p6,
    v.cond_vorp_pg, v.cond_vorp_total, v.duration_games,
    v.acquisition_risk, v.ci_low, v.ci_high,
    v.primary_mechanism, v.secondary_mechanism, v.role_trend,
    v.confidence, v.bad_variance_flag, v.bad_variance_note,
    v.explanation_json, v.component_json,
    lp.name AS league_profile, lp.season, lp.teams, lp.scoring
FROM public.lottery_valuations v
LEFT JOIN public.players p ON p.id = v.player_id
JOIN public.lottery_league_profiles lp ON lp.league_profile_id = v.league_profile_id;
COMMENT ON VIEW public.v_lottery_board IS
    'Latest lottery-ticket valuations joined to canonical player names. Filter as_of = (SELECT MAX(as_of) ...) per league profile.';
