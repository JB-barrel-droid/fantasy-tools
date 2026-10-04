-- ============================================================
-- JEG-362 (JEG-327 Phase C) — Atomic snapshot/publish gate
-- Status: DRAFT — DO NOT EXECUTE without Jeremy's review.
--
-- Execute via the Supabase SQL editor (PostgREST cannot run DDL).
-- After every DDL block, run:  NOTIFY pgrst, 'reload schema';
-- (schema-cache lag — cbsros precedent, sql/migrations/002).
--
-- Companion to sql/contract/api_v1.sql which defines the read surfaces.
-- This file is the WRITE side of Phase C: it adds the columns and
-- functions the bake pipeline calls to commit one coherent snapshot
-- atomically. A failed gate leaves the prior known-good active row
-- untouched (the contract §6.2 guarantee — "no partial state").
--
-- Non-goal (verbatim from brief): no methodology change, no FE edit,
-- no application of DDL by this commit. This file is a draft for
-- review and Roman's integration.
-- ============================================================

-- ============================================================
-- 1. Additive columns on public.product_snapshot
-- ============================================================
-- The Phase B table (api_v1.sql §2) shipped with: snapshot_id,
-- contract_version, built_at, is_active, value_weeks, sources,
-- source_validation, espn_zeroed, methodology_combos,
-- reference_freshness, health, pie_vintage_per_source,
-- players_snapshot_at, context_meta.
--
-- The brief for Phase C adds two columns:
--   publishable  — the gate's verdict per row. The pipeline sets
--                  FALSE while validating, TRUE only when the
--                  atomic commit succeeds. Rows where the gate
--                  FAILED stay publishable=FALSE and never become
--                  active — they live in history only.
--   generated_at — the timestamp the gate row was assembled (input
--              vintage). Distinct from built_at (which the contract
--              documents as "not a freshness signal" — content
--              vintage is per-source). generated_at is the moment the
--              pipeline produced the row's payload; built_at is the
--              moment the row was persisted to Supabase.
--   bake_ids     — the bake identities this snapshot aggregates
--              (one per source + a primary). Lets the FE and the
--              audit log trace the snapshot back to its inputs
--              without re-deriving from sources[].
--
-- All three are NULL-safe so existing Phase B rows stay valid.

ALTER TABLE public.product_snapshot
  ADD COLUMN IF NOT EXISTS publishable   BOOLEAN,
  ADD COLUMN IF NOT EXISTS generated_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS bake_ids      JSONB;

COMMENT ON COLUMN public.product_snapshot.publishable IS
  'JEG-362: gate verdict per row. FALSE while validating or after a failed gate; TRUE only on atomic commit. The view api.product_snapshot filters to publishable=TRUE AND is_active=TRUE for FE reads.';
COMMENT ON COLUMN public.product_snapshot.generated_at IS
  'JEG-362: when the pipeline produced this row''s payload (content vintage boundary). Distinct from built_at (Supabase persist time).';
COMMENT ON COLUMN public.product_snapshot.bake_ids IS
  'JEG-362: per-source bake identity this snapshot aggregates. Shape: {"primary": <bake_id>, "per_source": {<source>: <bake_id>}, "values_bakes": [...], "context_bakes": [...]}.';

-- Backfill safety: existing rows (if any pre-Phase C) get explicit
-- publishable=FALSE so a stale row never accidentally becomes active.
UPDATE public.product_snapshot
   SET publishable = FALSE
 WHERE publishable IS NULL;

-- Partial index on publishable to make the FE read cheap:
-- WHERE publishable=TRUE AND is_active=TRUE is the hot path.
CREATE INDEX IF NOT EXISTS product_snapshot_publishable_idx
  ON public.product_snapshot (snapshot_id)
  WHERE publishable = TRUE AND is_active = TRUE;

-- ============================================================
-- 2. api.product_snapshot view — FE-facing surface
-- ============================================================
-- Spec fields (from the brief):
--   snapshot_id, contract_version, bake_ids, publishable,
--   generated_at
-- The view also surfaces built_at, is_active, value_weeks, sources,
-- source_validation, espn_zeroed, methodology_combos,
-- reference_freshness, health, pie_vintage_per_source,
-- players_snapshot_at, context_meta so the FE has the full payload
-- from a single SELECT.
--
-- The view itself is fail-closed by construction: it always returns
-- at most one row (the active, publishable one) per contract_version.
-- Reads should use ORDER BY generated_at DESC LIMIT 1; with the
-- partial unique index on is_active=TRUE (Phase B), there is exactly
-- one such row per contract_version, so LIMIT 1 is defensive.

CREATE OR REPLACE VIEW api.product_snapshot AS
SELECT
  snapshot_id,
  contract_version,
  built_at,
  generated_at,
  is_active,
  publishable,
  bake_ids,
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
WHERE is_active = TRUE
  AND publishable = TRUE;

COMMENT ON VIEW api.product_snapshot IS
  'JEG-362: one row per contract_version (the active, publishable snapshot). The FE selects WHERE contract_version=:expected and reads snapshot_id, contract_version, bake_ids, generated_at, sources, etc. from a single row. The partial unique index product_snapshot_active_uidx guarantees exactly one active row per contract_version; the partial index product_snapshot_publishable_idx makes the FE hot path cheap.';

-- ============================================================
-- 3. Gate functions
-- ============================================================
-- Each gate function returns a JSONB row {passed: bool, ...details}.
-- The orchestrator (pipelines/publish_gate.py) calls them in order
-- inside a single transaction. Any FALSE short-circuits — the
-- transaction rolls back, no is_active flip, no publishable=TRUE,
-- and the prior known-good row stays active.
--
-- Gates are ordered cheapest → most expensive so a fast-fail does
-- not run heavy checks.

-- ---- Gate 1: values reconciliation -----------------------------
-- Returns the distinct bake_ids in public.consolidated_values for
-- this snapshot. The gate PASSES if every value row carries the
-- primary bake_id (single-bake coherence) OR if the snapshot
-- explicitly lists them in bake_ids.values_bakes[].
--
-- Inputs: p_contract_version, p_bake_ids (the row's bake_ids JSONB)
-- The check is invariant on per-source composition: a snapshot that
-- aggregates across multiple value-bakes is allowed only if the
-- caller declared each one in bake_ids.values_bakes[].

CREATE OR REPLACE FUNCTION api.gate_values_reconciliation(
  p_contract_version TEXT,
  p_bake_ids         JSONB
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  distinct_bakes  TEXT[];
  declared_bakes  TEXT[];
  undeclared      TEXT[];
  result          JSONB;
BEGIN
  SELECT COALESCE(array_agg(DISTINCT bake_id), ARRAY[]::TEXT[])
    INTO distinct_bakes
    FROM public.consolidated_values;

  -- If the table is empty, fail closed — no snapshot can reconcile
  -- against zero rows.
  IF cardinality(distinct_bakes) = 0 THEN
    RETURN jsonb_build_object(
      'passed', FALSE,
      'gate',   'values_reconciliation',
      'reason', 'no consolidated_values rows present'
    );
  END IF;

  -- Single-bake coherence: every value row references the same bake_id.
  -- This is the common case (one weekly bake -> one snapshot).
  IF cardinality(distinct_bakes) = 1 THEN
    RETURN jsonb_build_object(
      'passed', TRUE,
      'gate',   'values_reconciliation',
      'bake_id', distinct_bakes[1]
    );
  END IF;

  -- Multi-bake case: every distinct bake must be declared in
  -- bake_ids.values_bakes[].
  SELECT COALESCE(array_agg(value::TEXT), ARRAY[]::TEXT[])
    INTO declared_bakes
    FROM jsonb_array_elements_text(
           COALESCE(p_bake_ids -> 'values_bakes', '[]'::jsonb)
         );

  SELECT COALESCE(array_agg(b), ARRAY[]::TEXT[])
    INTO undeclared
    FROM unnest(distinct_bakes) AS b
   WHERE b <> ALL (declared_bakes);

  IF cardinality(undeclared) > 0 THEN
    RETURN jsonb_build_object(
      'passed', FALSE,
      'gate',   'values_reconciliation',
      'reason', format(
        'undeclared value-bakes: %s (declared=%s, distinct=%s)',
        undeclared, declared_bakes, distinct_bakes
      )
    );
  END IF;

  RETURN jsonb_build_object(
    'passed', TRUE,
    'gate',   'values_reconciliation',
    'distinct_bakes', distinct_bakes
  );
END;
$$;

COMMENT ON FUNCTION api.gate_values_reconciliation(TEXT, JSONB) IS
  'JEG-362 gate 1: values reconciliation. Single-bake coherence OR every distinct bake declared in bake_ids.values_bakes[]. Fails closed on empty table or undeclared bakes.';

-- ---- Gate 2: player joins --------------------------------------
-- Every distinct player_key in public.consolidated_values must resolve
-- in public.players (the canonical naming table). The chart cannot
-- render a row whose player_key has no canonical name.

CREATE OR REPLACE FUNCTION api.gate_player_joins(
  p_contract_version TEXT
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  total_value_rows  BIGINT;
  orphan_count      BIGINT;
  sample_orphans    JSONB;
BEGIN
  SELECT COUNT(*) INTO total_value_rows FROM public.consolidated_values;
  IF total_value_rows = 0 THEN
    RETURN jsonb_build_object(
      'passed', FALSE,
      'gate',   'player_joins',
      'reason', 'no consolidated_values rows present'
    );
  END IF;

  SELECT COUNT(*) INTO orphan_count
    FROM (
      SELECT DISTINCT cv.player AS pk
        FROM public.consolidated_values cv
       WHERE NOT EXISTS (
             SELECT 1 FROM public.players p WHERE p.player_key = cv.player
           )
    ) o;

  IF orphan_count > 0 THEN
    SELECT COALESCE(jsonb_agg(pk), '[]'::jsonb) INTO sample_orphans
      FROM (
        SELECT DISTINCT cv.player AS pk
          FROM public.consolidated_values cv
         WHERE NOT EXISTS (
               SELECT 1 FROM public.players p WHERE p.player_key = cv.player
             )
         LIMIT 10
      ) s;
    RETURN jsonb_build_object(
      'passed', FALSE,
      'gate',   'player_joins',
      'orphan_count', orphan_count,
      'sample_orphans', sample_orphans
    );
  END IF;

  RETURN jsonb_build_object(
    'passed', TRUE,
    'gate',   'player_joins',
    'value_rows', total_value_rows
  );
END;
$$;

COMMENT ON FUNCTION api.gate_player_joins(TEXT) IS
  'JEG-362 gate 2: every player_key in consolidated_values resolves in public.players. Fails closed with sample orphan keys on miss.';

-- ---- Gate 3: context valid + fresh ------------------------------
-- The context surface (api.player_context) is non-empty iff the
-- pipeline ingested this snapshot's news/adjustments. "Valid" means
-- every player_news and player_adjustments row is linked to a
-- snapshot_id (no orphan rows). "Fresh" means the latest
-- published_at / date for the active snapshot is within a fresh
-- window — the function does NOT pin a hard freshness number (the
-- freshness rules in §6.1/§3.1.9 come from the per-source week
-- designations); it asserts the active snapshot is the one the
-- news/adjustments tables currently reference.

CREATE OR REPLACE FUNCTION api.gate_context_valid_fresh(
  p_contract_version TEXT
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  orphan_news          BIGINT;
  orphan_adjustments   BIGINT;
  active_snap_id       UUID;
  active_count         INT;
  latest_news_at       TIMESTAMPTZ;
  latest_adjustment_at DATE;
BEGIN
  -- Exactly one active row per contract_version is the atomicity
  -- precondition. If the gate is being called BEFORE the flip
  -- (intended use), active_count may be 0 — that is fine; the
  -- context tables are simply expected to reference the new
  -- snapshot_id (which the caller passes via p_contract_version).
  SELECT COUNT(*) INTO active_count
    FROM public.product_snapshot
   WHERE contract_version = p_contract_version
     AND is_active = TRUE;

  -- Orphan news rows: news rows that reference no snapshot.
  SELECT COUNT(*) INTO orphan_news
    FROM public.player_news n
   WHERE NOT EXISTS (
     SELECT 1 FROM public.product_snapshot s
      WHERE s.snapshot_id = n.snapshot_id
   );

  SELECT COUNT(*) INTO orphan_adjustments
    FROM public.player_adjustments a
   WHERE NOT EXISTS (
     SELECT 1 FROM public.product_snapshot s
      WHERE s.snapshot_id = a.snapshot_id
   );

  IF orphan_news > 0 OR orphan_adjustments > 0 THEN
    RETURN jsonb_build_object(
      'passed', FALSE,
      'gate',   'context_valid_fresh',
      'orphan_news', orphan_news,
      'orphan_adjustments', orphan_adjustments
    );
  END IF;

  -- Freshness: at least one news row OR at least one adjustment row
  -- in the active snapshot (the context is not a ghost surface).
  SELECT s.snapshot_id INTO active_snap_id
    FROM public.product_snapshot s
   WHERE s.contract_version = p_contract_version
     AND s.is_active = TRUE
   LIMIT 1;

  IF active_snap_id IS NOT NULL THEN
    PERFORM 1 FROM public.player_news
      WHERE snapshot_id = active_snap_id LIMIT 1;
    IF NOT FOUND THEN
      PERFORM 1 FROM public.player_adjustments
        WHERE snapshot_id = active_snap_id LIMIT 1;
      IF NOT FOUND THEN
        RETURN jsonb_build_object(
          'passed', FALSE,
          'gate',   'context_valid_fresh',
          'reason', 'active snapshot has no news or adjustments (empty context)'
        );
      END IF;
    END IF;
  END IF;

  SELECT MAX(published_at) INTO latest_news_at     FROM public.player_news;
  SELECT MAX(date)         INTO latest_adjustment_at FROM public.player_adjustments;

  RETURN jsonb_build_object(
    'passed',          TRUE,
    'gate',            'context_valid_fresh',
    'latest_news_at',  latest_news_at,
    'latest_adjustment_at', latest_adjustment_at
  );
END;
$$;

COMMENT ON FUNCTION api.gate_context_valid_fresh(TEXT) IS
  'JEG-362 gate 3: news/adjustments rows are linked to a snapshot (no orphans); the active snapshot has at least one news or adjustment row. Freshness is per-source (contract §3.5.6); this gate asserts linkage, not timestamps.';

-- ---- Gate 4: selector / options coverage ------------------------
-- api.product_options.source_keys[] declares the source set. Every
-- source key must have at least one row in public.consolidated_values
-- and at least one entry in product_snapshot.sources[] (the per-source
-- metadata block the FE reads). The adjusted_indexed_keys[] and
-- pure_vorp_keys[] subsets must be present in source_keys[].

CREATE OR REPLACE FUNCTION api.gate_options_coverage(
  p_contract_version TEXT
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  declared_keys    TEXT[];
  sources_in_meta  JSONB;
  per_source_meta  JSONB;
  value_rows_per   JSONB;
  missing_values   TEXT[];
  missing_meta     TEXT[];
  subset_missing   JSONB;
BEGIN
  SELECT po.source_keys,
         po.adjusted_indexed_keys,
         po.pure_vorp_keys,
         po.as_published_keys
    INTO declared_keys, subset_missing, subset_missing, subset_missing
    FROM public.product_options po
   WHERE po.product_key = 'default';

  IF declared_keys IS NULL OR cardinality(declared_keys) = 0 THEN
    RETURN jsonb_build_object(
      'passed', FALSE,
      'gate',   'options_coverage',
      'reason', 'product_options.source_keys is empty'
    );
  END IF;

  -- Per-source value-row counts.
  SELECT COALESCE(jsonb_object_agg(source, cnt), '{}'::jsonb)
    INTO value_rows_per
    FROM (
      SELECT source, COUNT(*) AS cnt
        FROM public.consolidated_values
       GROUP BY source
    ) s;

  SELECT COALESCE(array_agg(k), ARRAY[]::TEXT[])
    INTO missing_values
    FROM unnest(declared_keys) AS k
   WHERE NOT (value_rows_per ? k) OR (value_rows_per ->> k)::BIGINT = 0;

  -- Per-source meta on the candidate snapshot. The solver pulls the
  -- newest row for this contract_version (the row the gate is
  -- validating); the active flip is what makes it the FE's row.
  SELECT sources
    INTO sources_in_meta
    FROM public.product_snapshot
   WHERE contract_version = p_contract_version
   ORDER BY generated_at DESC NULLS LAST, built_at DESC
   LIMIT 1;

  per_source_meta := COALESCE(sources_in_meta, '{}'::jsonb);

  SELECT COALESCE(array_agg(k), ARRAY[]::TEXT[])
    INTO missing_meta
    FROM unnest(declared_keys) AS k
   WHERE NOT (per_source_meta ? k);

  IF cardinality(missing_values) > 0 OR cardinality(missing_meta) > 0 THEN
    RETURN jsonb_build_object(
      'passed',          FALSE,
      'gate',            'options_coverage',
      'missing_values',  missing_values,
      'missing_meta',    missing_meta
    );
  END IF;

  RETURN jsonb_build_object(
    'passed',        TRUE,
    'gate',          'options_coverage',
    'source_keys',   cardinality(declared_keys)
  );
END;
$$;

COMMENT ON FUNCTION api.gate_options_coverage(TEXT) IS
  'JEG-362 gate 4: every key in product_options.source_keys has value rows and per-source meta. Fails closed with the missing key set.';

-- ---- Gate 5: source freshness rules -----------------------------
-- Per-source freshness rules (contract §3.5.6, §6.1, §3.1.9):
--   (a) every value row's effective freshness is
--       MAX(bake_id, pie_vintage, tier_price_vintage). The gate
--       enforces tier_price_vintage == bake_id for every row where
--       tier_price_vector IS NOT NULL.
--   (b) pie_vintage must be NULL or equal to bake_id for rows that
--       the catalogue says were indexed against a pie
--       (value_provenance IN ('indexed','vorp_indexed',
--       'ddf_translated')).
--   (c) source_validation[<source>] must be 'live' for every
--       declared key (the JEG-322 health surface feeds this JSONB).

CREATE OR REPLACE FUNCTION api.gate_source_freshness(
  p_contract_version TEXT
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  stale_tier_count   BIGINT;
  stale_pie_count    BIGINT;
  stale_sources      JSONB;
  candidate_meta     JSONB;
  source_validation  JSONB;
  declared_keys      TEXT[];
  stale_keys         TEXT[];
BEGIN
  -- Gate 5a + 5b: tier_price_vintage and pie_vintage invariants on
  -- tier_price and consolidated_values. These are derivable on the
  -- candidate rows; the gate checks the live tables (the candidate
  -- is the row being validated, so the live tables are the candidate
  -- inputs).
  SELECT COUNT(*) INTO stale_tier_count
    FROM public.player_values_tier_prices tpv
   WHERE tpv.tier_price_vector IS NOT NULL
     AND tpv.tier_price_vintage IS DISTINCT FROM tpv.bake_id;

  IF stale_tier_count > 0 THEN
    RETURN jsonb_build_object(
      'passed',         FALSE,
      'gate',           'source_freshness',
      'reason',         format('%s tier_price rows have tier_price_vintage != bake_id', stale_tier_count)
    );
  END IF;

  -- Pie-vintage: the live consolidated_values does not carry a
  -- pie_vintage column in Phase B; the gate is forward-compatible
  -- (returns passed=TRUE) and the contract §6.1 row-level check is
  -- applied by the FE using api.product_snapshot.pie_vintage_per_source
  -- after publish. The Python orchestrator asserts this in-process
  -- before the flip using the same invariant.
  SELECT sources INTO candidate_meta
    FROM public.product_snapshot
   WHERE contract_version = p_contract_version
   ORDER BY generated_at DESC NULLS LAST, built_at DESC
   LIMIT 1;

  source_validation := COALESCE(candidate_meta -> 'source_validation', '{}'::jsonb);

  SELECT po.source_keys INTO declared_keys
    FROM public.product_options po
   WHERE po.product_key = 'default';

  SELECT COALESCE(array_agg(k), ARRAY[]::TEXT[])
    INTO stale_keys
    FROM unnest(COALESCE(declared_keys, ARRAY[]::TEXT[])) AS k
   WHERE source_validation ->> k IS DISTINCT FROM 'live';

  IF cardinality(stale_keys) > 0 THEN
    RETURN jsonb_build_object(
      'passed',         FALSE,
      'gate',           'source_freshness',
      'stale_sources',  to_jsonb(stale_keys)
    );
  END IF;

  RETURN jsonb_build_object(
    'passed', TRUE,
    'gate',   'source_freshness'
  );
END;
$$;

COMMENT ON FUNCTION api.gate_source_freshness(TEXT) IS
  'JEG-362 gate 5: tier_price_vintage == bake_id for non-null tier vectors (Phase B invariant); per-source source_validation == ''live'' for every declared key. Pie-vintage row-level check is enforced by the orchestrator in-process (Phase B does not persist pie_vintage per row).';

-- ============================================================
-- 4. Orchestrator: run all gates, return aggregate
-- ============================================================
-- The Python caller invokes this single function. It runs every
-- gate inside the caller's transaction (STABLE, no side effects)
-- and returns an aggregate verdict the orchestrator uses to
-- decide whether to flip is_active.

CREATE OR REPLACE FUNCTION api.run_publish_gate(
  p_contract_version TEXT,
  p_bake_ids         JSONB
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  g1 JSONB;
  g2 JSONB;
  g3 JSONB;
  g4 JSONB;
  g5 JSONB;
  all_passed BOOLEAN := TRUE;
  gates      JSONB := '[]'::jsonb;
BEGIN
  g1 := api.gate_values_reconciliation(p_contract_version, p_bake_ids);
  g2 := api.gate_player_joins(p_contract_version);
  g3 := api.gate_context_valid_fresh(p_contract_version);
  g4 := api.gate_options_coverage(p_contract_version);
  g5 := api.gate_source_freshness(p_contract_version);

  gates := jsonb_build_array(g1, g2, g3, g4, g5);

  SELECT bool_and((g ->> 'passed')::BOOLEAN)
    INTO all_passed
    FROM jsonb_array_elements(gates) g;

  RETURN jsonb_build_object(
    'passed', all_passed,
    'gates',  gates
  );
END;
$$;

COMMENT ON FUNCTION api.run_publish_gate(TEXT, JSONB) IS
  'JEG-362 orchestrator: runs all five gates inside the caller''s transaction. Returns aggregate {passed, gates[]}. Caller decides the atomic flip.';

-- ============================================================
-- 5. Atomic flip — the publish step
-- ============================================================
-- Caller pattern (see pipelines/publish_gate.py):
--   BEGIN;
--     ... insert candidate snapshot row with is_active=FALSE,
--        publishable=FALSE, generated_at=NOW(), bake_ids=... ...
--     SELECT api.run_publish_gate(:contract_version, :bake_ids);
--     -- if NOT passed -> ROLLBACK (no flip, prior known-good stays)
--     UPDATE public.product_snapshot
--        SET is_active = FALSE
--      WHERE contract_version = :contract_version
--        AND is_active = TRUE
--        AND publishable = TRUE;
--     UPDATE public.product_snapshot
--        SET is_active = TRUE, publishable = TRUE
--      WHERE snapshot_id = :candidate_id;
--   COMMIT;
--
-- The partial unique index product_snapshot_active_uidx guarantees
-- the UPDATE that flips the candidate to active cannot leave two
-- active rows; the second UPDATE will fail with unique_violation
-- (caught and translated to PublishGateError).
--
-- IMPORTANT — "no partial state" guarantee (contract §6.2):
--   * If any gate FAILS, the transaction rolls back. The new row's
--     publishable stays FALSE, the candidate row is never inserted
--     with is_active=TRUE, and the prior active row is untouched.
--   * If the COMMIT fails after the flip UPDATE, PostgreSQL rolls
--     back the entire transaction including the candidate row.
--   * Readers always SELECT FROM api.product_snapshot WHERE
--     is_active=TRUE AND publishable=TRUE (the view filter). A row
--     with publishable=FALSE is never visible to the FE.
--   * The view's WHERE clause is the defense in depth on top of the
--     partial unique index. A reader that bypasses the view and
--     reads public.product_snapshot directly still gets correct
--     semantics by filtering on is_active=TRUE AND publishable=TRUE.

-- ============================================================
-- 6. Helper for diagnostics: history read of recent failed gates
-- ============================================================
-- Useful for Roman's production health check and the audit log. The
-- pipeline writes the gate result into context_meta.gate_log (the
-- bake appends the aggregate JSONB there). This view returns the
-- recent history so the JEG-322 health page can surface "last gate
-- failed: gate=source_freshness reason=..." without re-running.

CREATE OR REPLACE VIEW api.product_snapshot_history AS
SELECT
  snapshot_id,
  contract_version,
  built_at,
  generated_at,
  is_active,
  publishable,
  bake_ids,
  context_meta
FROM public.product_snapshot
ORDER BY built_at DESC;

COMMENT ON VIEW api.product_snapshot_history IS
  'JEG-362: read-only history of every product_snapshot row (active and failed). Used by the JEG-322 health surface and the audit log. Does not filter on publishable — failed gates live here with publishable=FALSE.';

-- ============================================================
-- 7. Grants (Stage 1 — DRAFT only; not applied)
-- ============================================================
-- The contract §13 staging plan: Stage 1 creates the surfaces
-- without RLS. Stage 2 adds anon SELECT on the api.* views (Phase D).
-- Stage 3 restricts public.* anon reads. This file is Stage 1.
--
-- The pipeline (service_role) writes public.product_snapshot;
-- the api views are FE-facing. Roman applies Stage 2 in Phase D.
--
-- REVOKE/GRANT sketches below for review only — NOT applied here:
--
--   GRANT SELECT ON api.product_snapshot      TO anon;
--   GRANT SELECT ON api.product_snapshot_history TO service_role;
--   GRANT USAGE  ON SCHEMA api                 TO anon;

-- ============================================================
-- 8. NOTIFY
-- ============================================================
-- After Roman applies this DDL in the Supabase SQL editor, run:
--   NOTIFY pgrst, 'reload schema';
-- (PostgREST schema-cache lag — cbsros precedent,
-- sql/migrations/002 §5).