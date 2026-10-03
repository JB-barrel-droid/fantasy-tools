-- JEG-324: Consolidation layer — Supabase table DDL
--
-- Run this in the Supabase SQL editor (PostgREST cannot run DDL).
-- Project: iskiybsimubiujwuchsl
--
-- Design decisions (Jeremy 2026-10-03, scope docs/planning/consolidation-layer-scope.md):
--   * Supabase is the system of record; JSON is the served artifact for the static site.
--   * ALL weeks retained — no aging out. Full history accumulates.
--   * Exact values, no rounding in consolidation (rounding is presentation's job).
--   * Per-row detail_locator for auditability (Goal 6: pick any number, trace it).
--   * View names use the disambiguated family: combo_reindexed / vorp_indexed /
--     vorp / adj_values (Codex recommendation — cheapest before v1).

CREATE TABLE IF NOT EXISTS public.consolidated_values (
  player       TEXT NOT NULL,   -- canonical lowercase key from the IdentityMap
  source       TEXT NOT NULL,   -- 11 source keys verbatim (fantasycalc_adjusted, cbsros, ...)
  season       INT  NOT NULL,   -- e.g. 2026
  week         INT  NOT NULL CHECK (week BETWEEN 1 AND 18),
  scoring      TEXT NOT NULL CHECK (scoring IN ('full', 'half', 'standard')),
  teams        INT  NOT NULL CHECK (teams IN (8, 10, 12, 14)),
  qb_variant   TEXT CHECK (qb_variant IN ('qb1', 'qb2')),  -- NULL except fantasycalc*
  view         TEXT NOT NULL CHECK (view IN ('combo_reindexed', 'vorp_indexed', 'vorp', 'adj_values')),
  value        NUMERIC NOT NULL,  -- exact as computed in detail; never rounded here
  detail_locator TEXT NOT NULL,   -- deterministic path in the detail fixture, e.g.
                                 -- "sources.fantasycalc_adjusted.combos.full_12_qb1.reindexed['josh allen']"
  bake_id      TEXT NOT NULL,     -- which bake produced this row
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (player, source, season, week, scoring, teams, qb_variant, view)
);

-- Week-over-week tracking: the primary query pattern.
CREATE INDEX IF NOT EXISTS consolidated_values_player_source_week_idx
  ON public.consolidated_values (player, source, season, week);

-- Per-week/per-source coverage checks (what priced this week?).
CREATE INDEX IF NOT EXISTS consolidated_values_season_week_source_idx
  ON public.consolidated_values (season, week, source);

-- Bake lineage: which bake wrote these rows.
CREATE INDEX IF NOT EXISTS consolidated_values_bake_id_idx
  ON public.consolidated_values (bake_id);

-- Lock down the function search path per the JEG-285 hardening rule.
-- (No functions in this DDL, but the rule applies to any added later:
--  always set search_path=public, pg_temp.)

-- RLS: public read (the static chart fetches the JSON export, and JEG-322
-- monitoring reads health tables the same way); writes restricted to the
-- service role, which the bake pipeline uses.
ALTER TABLE public.consolidated_values ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS consolidated_values_public_read ON public.consolidated_values;
CREATE POLICY consolidated_values_public_read
  ON public.consolidated_values FOR SELECT
  USING (true);

-- No INSERT/UPDATE/DELETE policy for anon/authenticated: only the service role
-- (which bypasses RLS) can write. This matches the hardening applied to
-- pipeline_cron_log / pipeline_cron_state / live_page_checks in JEG-285.

-- Helpful views ----------------------------------------------------------

-- Weeks available (for the JSON export's weeks_available + UI filters).
CREATE OR REPLACE VIEW public.consolidated_weeks_available AS
SELECT season, week, COUNT(DISTINCT source) AS n_sources, COUNT(*) AS n_rows,
       MIN(created_at) AS first_written, MAX(created_at) AS last_written
  FROM public.consolidated_values
 GROUP BY season, week
 ORDER BY season, week;

-- Per-week source coverage (for the JSON export's sources_available).
CREATE OR REPLACE VIEW public.consolidated_sources_available AS
SELECT season, week, source, COUNT(*) AS n_rows
  FROM public.consolidated_values
 GROUP BY season, week, source
 ORDER BY season, week, source;
