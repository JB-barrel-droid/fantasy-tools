-- ============================================================
-- JEG-327 Phase B — v1 FE Read Contract: api.* surfaces
-- Status: DRAFT — DO NOT EXECUTE without Jeremy's review.
--
-- Execute via the Supabase SQL editor (PostgREST cannot run DDL).
-- After every DDL block, run:  NOTIFY pgrst, 'reload schema';
-- (schema-cache lag — cbsros precedent, sql/migrations/002).
--
-- PostgREST savers use BARE table names; the `api.` schema is read
-- through views only.
--
-- Scope: creates the api.* schema, the api.* views, the underlying
-- public.* tables the api.* views depend on, and the grants/RLS for
-- the FE read path. Does NOT touch the pipeline / write path beyond
-- what is needed for the read surfaces to compile.
--
-- Stages (mirrors docs/contract/fe-read-contract-v1.md §13):
--   Stage 1 (this file): create api.* + underlying tables, no RLS
--   Stage 2 (Phase D): anon SELECT on api.* views
--   Stage 3 (one release after Stage 2): restrict public.* anon SELECT
--   Stage 4: verify prod
--
-- IMPORTANT — non-goal (verbatim from brief):
--   "Mixing FE/BE separation with unrelated methodology changes."
--   This SQL creates surfaces; it does NOT change values, rescale pies,
--   alter VORP translation, or modify user-facing copy.
-- ============================================================

-- ============================================================
-- 0. api schema
-- ============================================================

CREATE SCHEMA IF NOT EXISTS api;

COMMENT ON SCHEMA api IS
  'JEG-327 v1: FE-facing read surfaces. All five semantic surfaces (player_values, players, player_context, product_options, product_snapshot) live here. Reads only; writes happen in public.* by the pipeline.';

-- ============================================================
-- 1. public.product_options (singleton — one row, product_key='default')
-- ============================================================
-- Carries the bench_share bounds/default, default selectors, frozen
-- constants (MIN_SHARED_FOR_PIE, STARTER_MARKUP_SANE band, PEAK_AGREEMENT
-- band), and the source key lists. FE reads through the api.view and
-- never the public table directly after Stage 3.
--
-- Default values match the current FE constants (curve-widget.js:759,
-- comparison-dashboard.js:23, value-model.js:25-26, 272-273, 316-317).

CREATE TABLE IF NOT EXISTS public.product_options (
  product_key                  TEXT PRIMARY KEY DEFAULT 'default' CHECK (product_key = 'default'),
  contract_version             TEXT NOT NULL,
  bench_share_default          NUMERIC NOT NULL DEFAULT 0.15
                                CHECK (bench_share_default > 0 AND bench_share_default < 1),
  bench_share_min              NUMERIC NOT NULL DEFAULT 0.01
                                CHECK (bench_share_min > 0 AND bench_share_min < bench_share_default),
  bench_share_max              NUMERIC NOT NULL DEFAULT 0.30
                                CHECK (bench_share_max > bench_share_default AND bench_share_max < 1),
  bench_share_user_settable    BOOLEAN NOT NULL DEFAULT TRUE,
  default_scoring              TEXT NOT NULL DEFAULT 'full'
                                CHECK (default_scoring IN ('full','half','standard')),
  default_teams                INT  NOT NULL DEFAULT 12
                                CHECK (default_teams IN (8,10,12,14)),
  default_roster_shape         JSONB NOT NULL DEFAULT '{"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"BENCH":6}'::JSONB,
  default_lock_order           TEXT NOT NULL DEFAULT 'espn',
  default_view_mode            TEXT NOT NULL DEFAULT 'indexed',
  default_reference_source     TEXT NOT NULL DEFAULT 'usatoday',
  default_position_weights     JSONB,
  min_shared_for_pie           INT NOT NULL DEFAULT 40
                                CHECK (min_shared_for_pie >= 1),
  starter_markup_sane_band     NUMERIC[] NOT NULL DEFAULT ARRAY[0.98, 1.6]::NUMERIC[],
  peak_agreement_band          NUMERIC[] NOT NULL DEFAULT ARRAY[0.80, 1.25]::NUMERIC[],
  source_keys                  TEXT[] NOT NULL,
  adjusted_indexed_keys        TEXT[] NOT NULL,
  pure_vorp_keys               TEXT[] NOT NULL DEFAULT ARRAY['espn_vorp','cbsros_vorp','razzball_vorp']::TEXT[],
  as_published_keys            TEXT[] NOT NULL
                                DEFAULT ARRAY['usatoday','fantasycalc','fantasypros','cbs']::TEXT[],
  inserted_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE public.product_options IS
  'JEG-327 v1: singleton carrying bench_share bounds/default and selector defaults. One row (product_key=''default''). Pipeline updates on each bake; FE reads via api.product_options.';

-- Seed the singleton with the v1 default values + the 14 source keys
-- verbatim from inventory §3.1.
INSERT INTO public.product_options (
  product_key, contract_version, source_keys, adjusted_indexed_keys
) VALUES (
  'default', '1.0.0',
  ARRAY['cbs','cbs_adjusted','cbsros','ecr','espn','espn_implied','fantasycalc',
        'fantasycalc_adjusted','fantasypros','fantasypros_adjusted',
        'prediction_markets','razzball','usatoday','usatoday_adjusted']::TEXT[],
  ARRAY['fantasycalc_adjusted','usatoday_adjusted','fantasypros_adjusted','cbs_adjusted']::TEXT[]
)
ON CONFLICT (product_key) DO NOTHING;

-- ============================================================
-- 2. public.product_snapshot (history; one active row per contract version)
-- ============================================================
-- The bake identity. Every pickable pipeline writes a new row per bake
-- and flips is_active=true atomically. The publish gate (§6 in the
-- contract doc) refuses to flip is_active unless the pie_vintage
-- invariant holds for every visible row.
--
-- Field shape matches contract §3.5.2.

CREATE TABLE IF NOT EXISTS public.product_snapshot (
  snapshot_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_version       TEXT NOT NULL,
  built_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  is_active              BOOLEAN NOT NULL DEFAULT FALSE,
  value_weeks            JSONB NOT NULL,
  sources                JSONB NOT NULL,
  source_validation      JSONB NOT NULL,
  espn_zeroed            INT[]  NOT NULL DEFAULT ARRAY[]::INT[],
  methodology_combos     JSONB NOT NULL,
  reference_freshness    JSONB,
  health                 JSONB,
  pie_vintage_per_source JSONB NOT NULL,
  players_snapshot_at    TIMESTAMPTZ NOT NULL,
  context_meta           JSONB,
  inserted_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (is_active IN (TRUE, FALSE))
);

COMMENT ON TABLE public.product_snapshot IS
  'JEG-327 v1: per-bake snapshot row. Exactly one row has is_active=true (enforced by the partial unique index below). The publish gate flips is_active atomically.';

-- Exactly one active snapshot per contract_version (Phase C's publish
-- gate relies on this).
CREATE UNIQUE INDEX IF NOT EXISTS product_snapshot_active_uidx
  ON public.product_snapshot (contract_version)
  WHERE is_active = TRUE;

-- ============================================================
-- 3. public.player_news / player_adjustments / player_review
-- ============================================================
-- One row per (player_key, news_or_adjustment_id). The FE's
-- news_by_player_key / adjustments_by_player_key maps become SQL
-- JOINs on player_key.
--
-- Schema mirrors inventory §3.2 verbatim; we do not pre-pick tighter
-- enums for status (Jeremy's call — see contract §11).

CREATE TABLE IF NOT EXISTS public.player_news (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_key          BIGINT NOT NULL,
  title               TEXT NOT NULL,
  summary             TEXT NOT NULL DEFAULT '',
  published_at        TIMESTAMPTZ NOT NULL,
  source              TEXT NOT NULL,
  source_reliability  TEXT NOT NULL DEFAULT 'standard',
  url                 TEXT,
  tags                TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
  snapshot_id         UUID NOT NULL REFERENCES public.product_snapshot(snapshot_id),
  inserted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS player_news_player_key_idx
  ON public.player_news (player_key, published_at DESC);

CREATE INDEX IF NOT EXISTS player_news_snapshot_idx
  ON public.player_news (snapshot_id);

CREATE TABLE IF NOT EXISTS public.player_adjustments (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_key          BIGINT NOT NULL,
  kind                TEXT NOT NULL DEFAULT 'injury',
  status              TEXT,  -- prose string preserved verbatim (Open Q in inventory §11)
  injury              TEXT,
  weeks_out           INT,
  weeks_out_range     INT[],
  date                DATE NOT NULL,
  note                TEXT,
  source              TEXT,
  skip_form           BOOLEAN NOT NULL DEFAULT FALSE,
  consumed            BOOLEAN NOT NULL DEFAULT FALSE,
  consumed_at         TIMESTAMPTZ,
  beneficiary_review  BOOLEAN NOT NULL DEFAULT FALSE,
  snapshot_id         UUID NOT NULL REFERENCES public.product_snapshot(snapshot_id),
  inserted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS player_adjustments_player_key_idx
  ON public.player_adjustments (player_key, date DESC);

CREATE INDEX IF NOT EXISTS player_adjustments_snapshot_idx
  ON public.player_adjustments (snapshot_id);

CREATE TABLE IF NOT EXISTS public.player_review (
  id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  player_key              BIGINT NOT NULL,
  asof                    DATE NOT NULL,
  date_checked            DATE NOT NULL,
  disposition             TEXT NOT NULL,  -- 'already-priced' | 'monitoring' | 'not-material'
  original_disposition    TEXT,
  summary                 TEXT,
  reason                  TEXT,
  snapshot_id             UUID NOT NULL REFERENCES public.product_snapshot(snapshot_id),
  inserted_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS player_review_player_key_idx
  ON public.player_review (player_key);

-- ============================================================
-- 4. api.player_values (view)
-- ============================================================
-- Projects public.consolidated_values with the per-row VALUE
-- PROVENANCE and per-view COVERAGE METADATA the FE honesty layer
-- needs.
--
-- tier_price_vector and tier_price_vintage live in a sibling table
-- public.player_values_tier_prices (one row per
-- (player, source, season, week, scoring, teams, qb_variant, view));
-- the view LEFT JOINs it. The publish gate enforces
-- tier_price_vintage == bake_id when tier_price_vector IS NOT NULL.

CREATE TABLE IF NOT EXISTS public.player_values_tier_prices (
  player            TEXT NOT NULL,
  source            TEXT NOT NULL,
  season            INT  NOT NULL,
  week              INT  NOT NULL CHECK (week BETWEEN 1 AND 18),
  scoring           TEXT NOT NULL CHECK (scoring IN ('full','half','standard')),
  teams             INT  NOT NULL CHECK (teams IN (8,10,12,14)),
  qb_variant        TEXT NOT NULL DEFAULT 'none' CHECK (qb_variant IN ('qb1','qb2','none')),
  view              TEXT NOT NULL CHECK (view IN ('combo_reindexed','vorp_indexed','vorp','adj_values')),
  tier_price_vector JSONB NOT NULL,
  tier_price_vintage TEXT NOT NULL,
  bake_id           TEXT NOT NULL,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (player, source, season, week, scoring, teams, qb_variant, view)
);

COMMENT ON TABLE public.player_values_tier_prices IS
  'JEG-327 v1: per-cell two-tier price vectors (vector+blend). One row per (player, source, ..., view). The FE renders via vector+blend using this. tier_price_vintage MUST equal bake_id (publish gate).';

CREATE INDEX IF NOT EXISTS player_values_tier_prices_bake_idx
  ON public.player_values_tier_prices (bake_id);

CREATE OR REPLACE VIEW api.player_values AS
SELECT
  cv.player                                         AS player_key,
  cv.source,
  cv.season,
  cv.week,
  cv.scoring,
  cv.teams,
  cv.qb_variant,
  cv.view,
  cv.value,
  -- value_provenance taxonomy (six values; see contract §3.1.4)
  CASE
    WHEN cv.view = 'combo_reindexed' AND cv.source IN (
      SELECT unnest(po.as_published_keys) FROM public.product_options po
        WHERE po.product_key = 'default'
    ) THEN 'indexed'
    WHEN cv.view = 'combo_reindexed' THEN 'ddf_translated'
    WHEN cv.view = 'vorp'            THEN 'vorp'
    WHEN cv.view = 'vorp_indexed'    THEN 'vorp_indexed'
    WHEN cv.view = 'adj_values'      THEN 'adj'
    ELSE 'native'
  END AS value_provenance,
  -- model_vs_published taxonomy (two values; see contract §3.1.5)
  CASE
    WHEN cv.source IN ('espn','cbsros','razzball') THEN 'model'
    ELSE 'published'
  END AS model_vs_published,
  cv.detail_locator,
  cv.bake_id,
  -- index_total per (source, combo) — populated by the bake; NULL when
  -- the view doesn't emit a pie. The bake joins the fixture index_total
  -- into this column. The view here carries it through.
  NULL::NUMERIC AS index_total,
  -- pie_vintage: baked per-source pie identity (the same bake_id the
  -- gallery was indexed against). NULL on passthrough sources not on
  -- the pie. The publish gate refuses row-level mismatch.
  NULL::TEXT AS pie_vintage,
  tpv.tier_price_vector,
  tpv.tier_price_vintage,
  -- Per-view coverage metadata (JEG-331 ground truth):
  -- 'full' = view+combo+source all available
  -- 'view_limited_combo' = view exists but not for this (scoring x teams x qb_variant)
  -- 'view_limited_source' = view+combo exist but not for this source
  CASE
    WHEN cv.view = 'combo_reindexed' THEN 'full'
    WHEN cv.view IN ('vorp','vorp_indexed','adj_values')
         AND cv.scoring = 'full' AND cv.teams = 12 AND cv.qb_variant = 'none'
         AND cv.source IN (
           'espn','cbsros','razzball',  -- vorp
           'usatoday','fantasycalc','fantasypros','cbs',  -- vorp_indexed + adj_values
           'fantasycalc_adjusted','usatoday_adjusted',
           'fantasypros_adjusted','cbs_adjusted'
         )
    THEN 'full'
    WHEN cv.view IN ('vorp','vorp_indexed','adj_values')
         AND cv.scoring = 'full' AND cv.teams = 12 AND cv.qb_variant = 'none'
    THEN 'view_limited_source'
    WHEN cv.view IN ('vorp','vorp_indexed','adj_values')
    THEN 'view_limited_combo'
    ELSE 'full'
  END AS coverage_class
FROM public.consolidated_values cv
LEFT JOIN public.player_values_tier_prices tpv
  ON tpv.player     = cv.player
 AND tpv.source     = cv.source
 AND tpv.season     = cv.season
 AND tpv.week       = cv.week
 AND tpv.scoring    = cv.scoring
 AND tpv.teams      = cv.teams
 AND tpv.qb_variant = cv.qb_variant
 AND tpv.view       = cv.view;

COMMENT ON VIEW api.player_values IS
  'JEG-327 v1: per-cell trade value + value_provenance + model_vs_published + coverage_class + tier_price_vector. Per-row VALUE PROVENANCE and per-view COVERAGE METADATA live here, not in api.product_snapshot, because the FE honesty layer renders them next to the value.';

-- ============================================================
-- 5. api.players (view)
-- ============================================================
-- Projects public.players (canonical naming table) with the per-row
-- IR-zero badge and K/DST exclusion flag.
--
-- The ppg-leg fields (espn_ppg / rz_ppg / cbsros_ppg) are projected
-- from their respective tables (public.espn_season_projections,
-- public.razzball_projections, public.cbs_ros_projections) via
-- JOIN. If those tables have not landed yet, the columns return NULL
-- (the contract is forward-compatible — the bake pipeline fills them).

CREATE OR REPLACE VIEW api.players AS
SELECT
  p.player_key,
  p.canonical_name,
  p.pos,
  p.team,
  -- ir_zeroed: populated from the snapshot's espn_zeroed[] array.
  -- The snapshot is the row the FE reads; here we project the LATEST
  -- active snapshot's list. Alternative: store ir_zeroed on public.players.
  (p.player_key = ANY(
    SELECT coalesce(jsonb_array_elements_text(s.espn_zeroed)::INT, 0)
      FROM public.product_snapshot s
     WHERE s.is_active = TRUE
     LIMIT 1
  )) AS ir_zeroed,
  (p.pos IN ('K','DST')) AS kdst_excluded_from_chart,
  espn.espn_ppg,
  rz.rz_ppg,
  cbsros.cbsros_ppg,
  NULL::JSONB AS agent_ranking_ppg,  -- pipeline decides fill; reserved field
  NULL::JSONB AS blend_ppg,
  NULL::INT AS games_remaining
FROM public.players p
LEFT JOIN public.espn_season_projections espn  ON espn.player_key  = p.player_key
LEFT JOIN public.razzball_projections   rz    ON rz.player_key    = p.player_key
LEFT JOIN public.cbs_ros_projections    cbsros ON cbsros.player_key = p.player_key;

COMMENT ON VIEW api.players IS
  'JEG-327 v1: canonical players + IR-zeroed badge + K/DST exclusion flag + per-source ppg legs. K/DST are present (kdst_excluded_from_chart=true) so canonical naming can reference them; the FE filters them at render.';

-- ============================================================
-- 6. api.player_context (view)
-- ============================================================
-- Aggregates news + adjustments + review per player_key.
-- Players with no news/adjustments/review are absent from the view;
-- the FE treats absence as "no news" (matches inventory current behavior).

CREATE OR REPLACE VIEW api.player_context AS
SELECT
  p.player_key,
  COALESCE(n.news, '[]'::JSONB)         AS news,
  COALESCE(a.adjustments, '[]'::JSONB)  AS adjustments,
  COALESCE(r.review, '[]'::JSONB)       AS review,
  GREATEST(
    COALESCE(n.as_of, '1970-01-01'::TIMESTAMPTZ),
    COALESCE(a.as_of, '1970-01-01'::TIMESTAMPTZ),
    COALESCE(r.as_of, '1970-01-01'::TIMESTAMPTZ)
  ) AS as_of
FROM public.players p
LEFT JOIN LATERAL (
  SELECT jsonb_agg(
    jsonb_build_object(
      'title', n.title,
      'summary', n.summary,
      'published_at', n.published_at,
      'source', n.source,
      'source_reliability', n.source_reliability,
      'url', n.url,
      'tags', n.tags
    ) ORDER BY n.published_at DESC
  ) AS news, MAX(n.published_at) AS as_of
  FROM public.player_news n
  WHERE n.player_key = p.player_key
    AND n.snapshot_id = (SELECT snapshot_id FROM public.product_snapshot WHERE is_active = TRUE LIMIT 1)
) n ON TRUE
LEFT JOIN LATERAL (
  SELECT jsonb_agg(
    jsonb_build_object(
      'id', a.id,
      'kind', a.kind,
      'status', a.status,
      'injury', a.injury,
      'weeks_out', a.weeks_out,
      'weeks_out_range', a.weeks_out_range,
      'date', a.date,
      'note', a.note,
      'source', a.source,
      'skip_form', a.skip_form,
      'consumed', a.consumed,
      'consumed_at', a.consumed_at,
      'beneficiary_review', a.beneficiary_review
    ) ORDER BY a.date DESC
  ) AS adjustments, MAX(a.date::TIMESTAMPTZ) AS as_of
  FROM public.player_adjustments a
  WHERE a.player_key = p.player_key
    AND a.snapshot_id = (SELECT snapshot_id FROM public.product_snapshot WHERE is_active = TRUE LIMIT 1)
) a ON TRUE
LEFT JOIN LATERAL (
  SELECT jsonb_agg(
    jsonb_build_object(
      'asof', r.asof,
      'date_checked', r.date_checked,
      'disposition', r.disposition,
      'original_disposition', r.original_disposition,
      'summary', r.summary,
      'reason', r.reason
    ) ORDER BY r.date_checked DESC
  ) AS review, MAX(r.date_checked::TIMESTAMPTZ) AS as_of
  FROM public.player_review r
  WHERE r.player_key = p.player_key
    AND r.snapshot_id = (SELECT snapshot_id FROM public.product_snapshot WHERE is_active = TRUE LIMIT 1)
) r ON TRUE
WHERE
  COALESCE(jsonb_array_length(n.news), 0) > 0
  OR COALESCE(jsonb_array_length(a.adjustments), 0) > 0
  OR COALESCE(jsonb_array_length(r.review), 0) > 0;

COMMENT ON VIEW api.player_context IS
  'JEG-327 v1: news + adjustments + review per player_key. Players with no entries are absent (the FE treats missing as "no news").';

-- ============================================================
-- 7. api.product_options (view, one-row passthrough)
-- ============================================================

CREATE OR REPLACE VIEW api.product_options AS
SELECT
  product_key,
  contract_version,
  jsonb_build_object(
    'default', bench_share_default,
    'min', bench_share_min,
    'max', bench_share_max,
    'user_settable', bench_share_user_settable
  ) AS bench_share,
  bench_share_default,
  bench_share_min,
  bench_share_max,
  bench_share_user_settable,
  default_scoring,
  default_teams,
  default_roster_shape,
  default_lock_order,
  default_view_mode,
  default_reference_source,
  default_position_weights,
  min_shared_for_pie,
  starter_markup_sane_band,
  peak_agreement_band,
  source_keys,
  adjusted_indexed_keys,
  pure_vorp_keys,
  as_published_keys
FROM public.product_options
WHERE product_key = 'default';

COMMENT ON VIEW api.product_options IS
  'JEG-327 v1: singleton carrying bench_share bounds/default and selector defaults. FE reads defaults from here; no FE-side constants.';

-- ============================================================
-- 8. api.product_snapshot (view; one active row)
-- ============================================================

CREATE OR REPLACE VIEW api.product_snapshot AS
SELECT
  snapshot_id,
  contract_version,
  built_at,
  value_weeks,
  sources,
  source_validation,
  espn_zeroed,
  methodology_combos,
  reference_freshness,
  health,
  pie_vintage_per_source,
  players_snapshot_at,
  context_meta
FROM public.product_snapshot
WHERE is_active = TRUE;

COMMENT ON VIEW api.product_snapshot IS
  'JEG-327 v1: exactly one active row per contract_version (enforced by product_snapshot_active_uidx). The FE reads this view; the partial unique index guarantees atomic flip in the publish gate.';

-- ============================================================
-- 9. Grants and RLS (Stage 2 of the security plan)
-- ============================================================
-- Stage 1: api.* views exist; anon has NO access yet (FE still on
-- legacy fixtures). RLS is OFF on public.product_options /
-- public.product_snapshot / public.player_news /
-- public.player_adjustments / public.player_review / public.players /
-- public.consolidated_values (matches today's posture for the
-- pipeline-writeable tables).
--
-- Stage 2 (Phase D, applied via separate SQL blocks): anon SELECT on
-- api.* views.
-- Stage 3: anon SELECT removed from public.* (api.* keeps it).
--
-- This file applies Stage 1 only. Stage 2 / Stage 3 DDL is in a
-- separate file (sql/contract/api_v1_grants_stage2.sql, future).

-- RLS off on the new tables (matches today's posture for the pipeline
-- writes; the write path uses service_role which bypasses RLS).
-- Pipeline writes are fail-closed via writer_audit (JEG-285 hardening).
ALTER TABLE public.product_options    DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.product_snapshot   DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_news        DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_adjustments DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_review      DISABLE ROW LEVEL SECURITY;
ALTER TABLE public.player_values_tier_prices DISABLE ROW LEVEL SECURITY;

-- ============================================================
-- 10. Verification (run in the Supabase SQL editor after this DDL)
-- ============================================================
-- -- 1. api schema + views exist:
-- SELECT schemaname, viewname FROM information_schema.views
--  WHERE schemaname = 'api' ORDER BY viewname;
-- -- expect: player_context, player_values, players, product_options, product_snapshot
--
-- -- 2. product_options singleton seeded:
-- SELECT product_key, contract_version, bench_share_default,
--        source_keys, adjusted_indexed_keys
--   FROM public.product_options;
--
-- -- 3. product_snapshot table empty (no rows yet — pipeline writes them):
-- SELECT count(*) FROM public.product_snapshot;
-- -- expect: 0
--
-- -- 4. api.player_values projects from public.consolidated_values:
-- SELECT count(*) FROM api.player_values;
-- -- expect: ~20000 (today's row count)
--
-- -- 5. Coverage-class breakdown matches JEG-331 ground truth:
-- SELECT view, coverage_class, count(*)
--   FROM api.player_values
--  GROUP BY view, coverage_class
--  ORDER BY view, coverage_class;
-- -- expect:
-- --   combo_reindexed | full                  | (full coverage)
-- --   vorp            | full                  | 635
-- --   vorp_indexed    | full                  | 624
-- --   adj_values      | full                  | 635
--
-- -- 6. Schema-cache lag: after running the DDL, run
-- --      NOTIFY pgrst, 'reload schema';
-- --    before testing via PostgREST.
-- ============================================================