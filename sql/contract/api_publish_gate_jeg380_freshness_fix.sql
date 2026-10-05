-- ============================================================
-- JEG-380 — Rewrite gate_source_freshness to COMPUTE from
--           public.bakes + public.source_config (not trust
--           product_snapshot.source_validation)
--
-- Status: DRAFT — write-only; Roman applies via Supabase SQL editor,
-- then runs  NOTIFY pgrst, 'reload schema';
-- (cbsros precedent — sql/migrations/002 §5).
--
-- DECISION (JEG-380 task 1):
--
-- The current api.gate_source_freshness (sql/contract/api_publish_gate.sql
-- lines 545-637) reads public.product_snapshot.source_validation and only
-- checks that each declared source_key has an ENTRY whose value is
-- 'live' or 'stale'. That is a trust-by-classification gate — a snapshot
-- that was classified 'live' but is in fact hours/days past its
-- source_config SLA still passes the gate (lanes/inbox/chatgpt/
-- backend-comprehensive-review-result.md:69-72, Critical #3).
--
-- The fix computes freshness deterministically:
--   for each declared source_key in public.product_options.source_keys:
--     1. resolve its bake_uuid from the CANDIDATE snapshot's
--        product_snapshot.bake_ids.per_source[<source>], falling back
--        to public.bakes (latest by created_at for that source);
--     2. join public.bakes for source_generated_at;
--     3. join public.source_config for max_age_hours + block_on_stale;
--     4. compute age_hours = EXTRACT(EPOCH FROM (now() - source_generated_at)) / 3600;
--     5. verdict per source:
--          - missing source_config row          → FAIL (cannot compute; fail-closed)
--          - missing bake row                   → FAIL (cannot compute; fail-closed)
--          - age_hours > max_age_hours AND
--            block_on_stale = TRUE (default)    → FAIL
--          - age_hours > max_age_hours AND
--            block_on_stale = FALSE             → WARN (per-source stale;
--                                                   FE degrades per source
--                                                   per contract §6.1)
--          - otherwise                          → OK
--
-- Per-source staleness NEVER hard-fails unless source_config.block_on_stale
-- is TRUE. That preserves the v1 contract §6.1 "per-source graceful
-- degradation" — a single stale source no longer freezes the whole chart
-- when the operator has explicitly opted out via block_on_stale=false.
-- For sources with block_on_stale=TRUE (the default) staleness DOES fail —
-- the publish gate is fail-closed by default.
--
-- Gate 5a (tier_price_vintage == bake_id invariant) is preserved; that is
-- a Phase B row-level invariant on public.player_values_tier_prices, not a
-- trust of snapshot data. Gate 5b (pie_vintage forward-compat no-op) is
-- preserved; the row-level check is a tracked Phase C gap (the comment in
-- api_publish_gate.sql:573-580 documents it).
--
-- The 5c source_validation trust-check is REMOVED. The column is kept on
-- public.product_snapshot (the JEG-322 health surface feeds it; the FE
-- reads it for diagnostic rendering), but the publish gate does not gate
-- on it.
-- ============================================================

-- ============================================================
-- 1. Patch: api.gate_source_freshness — compute, don't trust
-- ============================================================

CREATE OR REPLACE FUNCTION api.gate_source_freshness(
  p_contract_version      TEXT,
  p_candidate_snapshot_id UUID DEFAULT NULL
) RETURNS JSONB
LANGUAGE plpgsql STABLE AS $$
DECLARE
  -- Gate 5a state (Phase B tier_price_vintage invariant, unchanged).
  stale_tier_count   BIGINT;

  -- Gate 5c (JEG-380) state — computed freshness per declared source.
  declared_keys      TEXT[];
  bake_ids_json      JSONB;
  per_source_bakes   JSONB;          -- {<source>: <bake_uuid>} from candidate
  source_status      JSONB := '[]'::jsonb;  -- per-source verdict
  failed_sources     TEXT[] := ARRAY[]::TEXT[];
  warned_sources     TEXT[] := ARRAY[]::TEXT[];
  src                TEXT;
  bake_uuid_text     TEXT;
  bake_row           RECORD;
  cfg_row            RECORD;
  age_hours          NUMERIC;
  per_source_entry   JSONB;
BEGIN
  -- ----------------------------------------------------------------
  -- Gate 5a (unchanged): tier_price_vintage == bake_id on every row.
  -- Phase B invariant from sql/contract/api_publish_gate.sql:556-571.
  -- ----------------------------------------------------------------
  SELECT COUNT(*) INTO stale_tier_count
    FROM public.player_values_tier_prices tpv
   WHERE tpv.tier_price_vintage IS DISTINCT FROM tpv.bake_id;

  IF stale_tier_count > 0 THEN
    RETURN jsonb_build_object(
      'passed',         FALSE,
      'gate',           'source_freshness',
      'reason',         format('%s tier_price rows have tier_price_vintage != bake_id', stale_tier_count)
    );
  END IF;

  -- ----------------------------------------------------------------
  -- Gate 5b (unchanged): pie_vintage forward-compat no-op.
  -- The Phase C row-level enforcement is a tracked gap (api_publish_gate.sql
  -- :573-580 comment block); no work to do here in Phase B/C.
  -- ----------------------------------------------------------------

  -- ----------------------------------------------------------------
  -- Gate 5c (JEG-380): COMPUTED freshness from bakes + source_config.
  --
  -- Fail-closed:
  --   * no source_config row for a declared source      → FAIL
  --   * no bake row for a declared source               → FAIL
  --   * stale AND source_config.block_on_stale IS TRUE  → FAIL
  --
  -- Warn (not fail):
  --   * stale AND source_config.block_on_stale IS FALSE → WARN
  --     (operator explicitly opted out; FE degrades per source
  --      per contract §6.1)
  --
  -- Pass:
  --   * source_generated_at within max_age_hours  → OK
  -- ----------------------------------------------------------------

  -- Pull declared keys from product_options (the same source the prior
  -- 5c trust-check used).
  SELECT po.source_keys INTO declared_keys
    FROM public.product_options po
   WHERE po.product_key = 'default';

  declared_keys := COALESCE(declared_keys, ARRAY[]::TEXT[]);

  -- Pull the candidate's bake_ids.per_source map. Prefer the explicit
  -- candidate id (W3 review S2); the newest-row ordering is a fallback
  -- heuristic for callers that do not pass one.
  IF p_candidate_snapshot_id IS NOT NULL THEN
    SELECT s.bake_ids INTO bake_ids_json
      FROM public.product_snapshot s
     WHERE s.snapshot_id = p_candidate_snapshot_id;
  ELSE
    SELECT s.bake_ids INTO bake_ids_json
      FROM public.product_snapshot s
     WHERE s.contract_version = p_contract_version
     ORDER BY s.generated_at DESC NULLS LAST, s.built_at DESC
     LIMIT 1;
  END IF;

  per_source_bakes := COALESCE(bake_ids_json -> 'per_source', '{}'::jsonb);

  -- Iterate declared sources; aggregate per-source verdicts.
  IF cardinality(declared_keys) > 0 THEN
    FOREACH src IN ARRAY declared_keys LOOP
      bake_uuid_text := per_source_bakes ->> src;

      -- Look up the bake. If bake_ids.per_source does not pin a UUID
      -- for this source, fall back to the most-recent bake for that
      -- source in public.bakes (matches the JEG-376 orchestrator's
      -- resolve_values_bake_uuids semantics in
      -- pipelines/publish_gate.py:212-216).
      IF bake_uuid_text IS NOT NULL THEN
        SELECT b.source_generated_at,
               b.contract_version
          INTO bake_row
          FROM public.bakes b
         WHERE b.bake_id = bake_uuid_text::UUID
         LIMIT 1;
      ELSE
        SELECT b.source_generated_at,
               b.contract_version
          INTO bake_row
          FROM public.bakes b
         WHERE b.source = src
         ORDER BY b.ingested_at DESC NULLS LAST, b.bake_id
         LIMIT 1;
      END IF;

      -- Look up source_config (max_age_hours + block_on_stale).
      SELECT sc.max_age_hours,
             sc.block_on_stale
        INTO cfg_row
        FROM public.source_config sc
       WHERE sc.source = src;

      -- Verdict ladder (fail-closed first).
      IF cfg_row.max_age_hours IS NULL THEN
        failed_sources := array_append(failed_sources, src);
        source_status := source_status || jsonb_build_array(jsonb_build_object(
          'source', src, 'status', 'fail',
          'reason', 'no source_config entry (cannot compute SLA)'
        ));
        CONTINUE;
      END IF;

      IF bake_row.source_generated_at IS NULL THEN
        failed_sources := array_append(failed_sources, src);
        source_status := source_status || jsonb_build_array(jsonb_build_object(
          'source', src, 'status', 'fail',
          'reason', 'no bake row found (cannot compute freshness)'
        ));
        CONTINUE;
      END IF;

      age_hours := EXTRACT(EPOCH FROM (now() - bake_row.source_generated_at)) / 3600.0;

      IF age_hours > cfg_row.max_age_hours THEN
        IF cfg_row.block_on_stale THEN
          failed_sources := array_append(failed_sources, src);
          source_status := source_status || jsonb_build_array(jsonb_build_object(
            'source', src, 'status', 'fail',
            'reason', format('stale: age=%.2fh exceeds max_age_hours=%s', age_hours, cfg_row.max_age_hours),
            'source_generated_at', bake_row.source_generated_at,
            'age_hours', age_hours,
            'max_age_hours', cfg_row.max_age_hours
          ));
        ELSE
          warned_sources := array_append(warned_sources, src);
          source_status := source_status || jsonb_build_array(jsonb_build_object(
            'source', src, 'status', 'warn',
            'reason', format('stale but block_on_stale=false: age=%.2fh exceeds max_age_hours=%s', age_hours, cfg_row.max_age_hours),
            'source_generated_at', bake_row.source_generated_at,
            'age_hours', age_hours,
            'max_age_hours', cfg_row.max_age_hours
          ));
        END IF;
      ELSE
        source_status := source_status || jsonb_build_array(jsonb_build_object(
          'source', src, 'status', 'ok',
          'source_generated_at', bake_row.source_generated_at,
          'age_hours', age_hours,
          'max_age_hours', cfg_row.max_age_hours
        ));
      END IF;
    END LOOP;
  END IF;

  -- Final verdict.
  IF cardinality(failed_sources) > 0 THEN
    RETURN jsonb_build_object(
      'passed',         FALSE,
      'gate',           'source_freshness',
      'reason',         'computed freshness failed for one or more sources',
      'failed_sources', to_jsonb(failed_sources),
      'source_status',  source_status
    );
  END IF;

  -- Build warnings[] from per-source warn entries; ride in the aggregate
  -- verdict for the audit log / health page (mirrors the run_publish_gate
  -- warnings aggregation at api_publish_gate.sql:679-684).
  DECLARE
    warnings_arr JSONB := '[]'::jsonb;
  BEGIN
    SELECT COALESCE(jsonb_agg(w), '[]'::jsonb)
      INTO warnings_arr
      FROM (
        SELECT jsonb_build_object(
          'gate', 'source_freshness',
          'source', (e ->> 'source'),
          'reason', (e ->> 'reason'),
          'age_hours', (e ->> 'age_hours')::NUMERIC,
          'max_age_hours', (e ->> 'max_age_hours')::INT
        ) AS w
          FROM jsonb_array_elements(source_status) e
         WHERE e ->> 'status' = 'warn'
      ) s;

    RETURN jsonb_build_object(
      'passed',         TRUE,
      'gate',           'source_freshness',
      'source_status',  source_status,
      'warnings',       warnings_arr
    );
  END;
END;
$$;

COMMENT ON FUNCTION api.gate_source_freshness(TEXT, UUID) IS
  'JEG-362 gate 5 (JEG-380 rewrite 2026-10-04): tier_price_vintage == bake_id on every tier_price row (Phase B invariant); per-source freshness COMPUTED from public.bakes.source_generated_at + public.source_config.max_age_hours — does NOT trust product_snapshot.source_validation. Fail-closed on missing source_config, missing bake row, and stale+block_on_stale=TRUE; warns on stale+block_on_stale=FALSE so the FE degrades per source per contract §6.1. Pass p_candidate_snapshot_id explicitly so the per_source bake map is read from the candidate row, not guessed by generated_at ordering. Pie-vintage row-level check is a tracked Phase C gap (enforced nowhere yet).';

-- ============================================================
-- 2. NOTIFY
-- ============================================================
-- After Roman applies this DDL in the Supabase SQL editor, run:
--   NOTIFY pgrst, 'reload schema';
-- (PostgREST schema-cache lag — cbsros precedent,
-- sql/migrations/002 §5).
--
-- ============================================================
-- 3. Verification (run after NOTIFY)
-- ============================================================
-- -- 3a. Function replaced:
--   SELECT proname, pg_get_functiondef(oid)
--     FROM pg_proc
--    WHERE proname = 'gate_source_freshness';
--   -- expect: body has the FOREACH src IN ARRAY declared_keys loop;
--   -- expect: source_config / bakes joins present;
--   -- expect: NO reference to product_snapshot.source_validation.
--
-- -- 3b. Required tables/columns exist (prereq for the gate to work):
--   SELECT column_name, data_type
--     FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'bakes';
--   -- expect: bake_uuid (uuid), source (text), source_generated_at
--   -- (timestamptz), created_at (timestamptz).
--
--   SELECT column_name, data_type
--     FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'source_config';
--   -- expect: source (text PK), max_age_hours (int), block_on_stale (bool).
--
-- -- 3c. Run the gate directly via psql or a service-role client:
--   SELECT api.gate_source_freshness(
--     '1.0.0',
--     '<candidate_snapshot_id>'
--   );
--   -- expect: passed=TRUE; source_status[] entries for every declared
--   -- source_keys value; status='ok' for fresh sources; warnings[] may
--   -- contain entries for stale sources with block_on_stale=FALSE.
--
-- -- 3e. Negative — simulate a stale source (block_on_stale=TRUE) and
-- -- verify the gate FAILS closed:
--   BEGIN;
--   UPDATE public.source_config
--      SET max_age_hours = 1  -- 1-hour SLA, well below any current bake
--    WHERE source = 'espn';
--   SELECT api.gate_source_freshness('1.0.0', '<candidate_snapshot_id>');
--   -- expect: passed=FALSE; failed_sources contains 'espn';
--   -- source_status entry has status='fail' with reason='stale: ...'.
--   ROLLBACK;
--
-- -- 3f. Negative — simulate a stale source with block_on_stale=FALSE
-- -- and verify the gate WARNS but still PASSES:
--   BEGIN;
--   UPDATE public.source_config
--      SET max_age_hours = 1, block_on_stale = FALSE
--    WHERE source = 'espn';
--   SELECT api.gate_source_freshness('1.0.0', '<candidate_snapshot_id>');
--   -- expect: passed=TRUE; warnings[] contains the espn entry with
--   -- reason='stale but block_on_stale=false: ...'.
--   ROLLBACK;
--
-- -- 3g. Negative — simulate a missing source_config row and verify
-- -- the gate FAILS closed:
--   BEGIN;
--   DELETE FROM public.source_config WHERE source = 'espn';
--   SELECT api.gate_source_freshness('1.0.0', '<candidate_snapshot_id>');
--   -- expect: passed=FALSE; failed_sources contains 'espn';
--   -- source_status entry has status='fail' with reason='no source_config
--   -- entry (cannot compute SLA)'.
--   ROLLBACK;