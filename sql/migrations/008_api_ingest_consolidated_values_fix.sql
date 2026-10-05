-- ============================================================
-- JEG-380 — Corrected api.ingest_consolidated_values(JSONB)
--
-- Status: write-only; Roman applies via Supabase SQL editor,
-- then runs  NOTIFY pgrst, 'reload schema';
-- (cbsros precedent — sql/migrations/002 §5).
--
-- Applied live 2026-10-04 (chatgpt lane result:
-- lanes/inbox/chatgpt/jeg380-ingest-rpc-fix-result.md).
-- This migration mirrors that live DDL into the versioned
-- repo so a fresh DB can be rebuilt from sql/.
--
-- Key changes vs the prior (broken) function:
--   * Fail-closed validation of required fields
--     (player, detail_locator, bake_id or bake_uuid).
--   * Derives text bake_id from bake_uuid when bake_id is absent.
--   * Hardened SECURITY DEFINER with
--     SET search_path = pg_catalog, public and schema-qualified
--     system catalogs / JSONB functions.
--   * Uses pg_catalog.jsonb_populate_recordset(NULL::public.consolidated_values, …)
--     to map JSON keys to the table rowtype so added columns with
--     defaults are picked up automatically and NOT NULLs without
--     defaults still fail-closed.
--   * UPSERT targets an explicit UNIQUE/PRIMARY constraint, either
--     supplied as payload.conflict_constraint or auto-detected as
--     a unique constraint that includes bake_id, player, detail_locator.
--   * Dynamic DO UPDATE sets all non-key, non-generated columns to
--     EXCLUDED values; falls back to DO NOTHING when none exist.
-- ============================================================

CREATE OR REPLACE FUNCTION api.ingest_consolidated_values(p_payload jsonb)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
  v_tbl            regclass := 'public.consolidated_values'::regclass;
  v_rows           jsonb;
  v_missing_cnt    integer;
  v_missing_example jsonb;

  -- UPSERT constraint selection
  v_constraint     text;
  v_key_cols_raw   text[]; -- raw (unquoted) column names of the conflict key

  -- Column lists for dynamic DO UPDATE
  v_all_cols_raw   text[];
  v_update_cols_raw text[];
  v_update_clause  text;
  v_sql            text;
BEGIN
  -- Normalize payload rows:
  -- Accept either an array as the top-level payload, or an object with key "rows": [...]
  IF (pg_catalog.jsonb_typeof(p_payload) = 'object') AND (p_payload ? 'rows') THEN
    IF pg_catalog.jsonb_typeof(p_payload->'rows') <> 'array' THEN
      RAISE EXCEPTION 'payload.rows must be a JSON array';
    END IF;
    v_rows := p_payload->'rows';
  ELSIF pg_catalog.jsonb_typeof(p_payload) = 'array' THEN
    v_rows := p_payload;
  ELSE
    RAISE EXCEPTION 'payload must be a JSON array, or an object with "rows": array';
  END IF;

  IF pg_catalog.jsonb_array_length(v_rows) = 0 THEN
    RAISE EXCEPTION 'no rows to ingest';
  END IF;

  -- Derive bake_id from bake_uuid where missing; then validate required fields.
  WITH elems AS (
    SELECT elem
    FROM pg_catalog.jsonb_array_elements(v_rows) AS elem
  ),
  norm AS (
    SELECT
      CASE
        WHEN NOT (elem ? 'bake_id') AND (elem ? 'bake_uuid')
          THEN elem || pg_catalog.jsonb_build_object('bake_id', elem->>'bake_uuid')
        ELSE elem
      END AS elem
    FROM elems
  ),
  checked AS (
    SELECT
      elem,
      (NOT (elem ? 'player'))          AS miss_player,
      (NOT (elem ? 'detail_locator'))  AS miss_detail_locator,
      (NOT (elem ? 'bake_id'))         AS miss_bake_id
    FROM norm
  )
  SELECT
    pg_catalog.jsonb_agg(elem),
    COUNT(*) FILTER (WHERE miss_player OR miss_detail_locator OR miss_bake_id),
    (SELECT elem FROM checked WHERE miss_player OR miss_detail_locator OR miss_bake_id LIMIT 1)
  INTO v_rows, v_missing_cnt, v_missing_example
  FROM checked;

  IF v_missing_cnt > 0 THEN
    RAISE EXCEPTION 'missing required fields (player, detail_locator, bake_id/bake_uuid) in % row(s); example: %',
      v_missing_cnt, v_missing_example;
  END IF;

  -- Determine UPSERT conflict target:
  -- Prefer explicit payload.conflict_constraint; else use the table's PRIMARY KEY.
  -- (The live consolidated_values PK is (player, source, season, week, scoring,
  -- teams, qb_variant, view) — the natural upsert key for idempotent loads.)
  IF (pg_catalog.jsonb_typeof(p_payload) = 'object') AND (p_payload ? 'conflict_constraint') THEN
    v_constraint := p_payload->>'conflict_constraint';
  ELSE
    SELECT conname
    INTO v_constraint
    FROM pg_catalog.pg_constraint c
    WHERE c.conrelid = v_tbl
      AND c.contype = 'p'
    LIMIT 1;

    IF v_constraint IS NULL THEN
      RAISE EXCEPTION 'could not auto-detect PRIMARY KEY on %; provide payload.conflict_constraint', v_tbl::text;
    END IF;
  END IF;

  PERFORM 1
  FROM pg_catalog.pg_constraint c
  WHERE c.conrelid = v_tbl
    AND c.conname  = v_constraint
    AND c.contype IN ('p','u');

  IF NOT FOUND THEN
    RAISE EXCEPTION 'conflict_constraint "%" is not a UNIQUE/PRIMARY constraint on %', v_constraint, v_tbl::text;
  END IF;

  -- Fetch raw (unquoted) key columns in ordinal order
  SELECT pg_catalog.array_agg(att.attname ORDER BY x.ord)::text[]
  INTO v_key_cols_raw
  FROM pg_catalog.pg_constraint c
  JOIN LATERAL pg_catalog.unnest(c.conkey) WITH ORDINALITY AS x(attnum, ord) ON true
  JOIN pg_catalog.pg_attribute att
    ON att.attrelid = c.conrelid
   AND att.attnum   = x.attnum
  WHERE c.conrelid = v_tbl
    AND c.conname  = v_constraint;

  -- All table columns (raw names) in physical order
  SELECT pg_catalog.array_agg(a.attname ORDER BY a.attnum)::text[]
  INTO v_all_cols_raw
  FROM pg_catalog.pg_attribute a
  WHERE a.attrelid = v_tbl
    AND a.attnum > 0
    AND NOT a.attisdropped;

  -- Updatable columns: exclude key columns and generated/identity columns
  SELECT pg_catalog.array_agg(col ORDER BY ord)::text[]
  INTO v_update_cols_raw
  FROM (
    SELECT col, ord
    FROM pg_catalog.unnest(v_all_cols_raw) WITH ORDINALITY AS u(col, ord)
    WHERE NOT (col = ANY (v_key_cols_raw))
      AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns ic
        WHERE ic.table_schema = 'public'
          AND ic.table_name   = 'consolidated_values'
          AND ic.column_name  = col
          AND (ic.is_generated = 'ALWAYS' OR ic.identity_generation IS NOT NULL)
      )
  ) s;

  IF v_update_cols_raw IS NULL OR pg_catalog.array_length(v_update_cols_raw, 1) = 0 THEN
    v_update_clause := NULL; -- no non-key columns to update; fall back to DO NOTHING
  ELSE
    SELECT pg_catalog.string_agg(
             pg_catalog.format('%I = EXCLUDED.%I', col, col),
             ', '
           )
    INTO v_update_clause
    FROM pg_catalog.unnest(v_update_cols_raw) AS t(col);
  END IF;

  -- Build and execute INSERT .. ON CONFLICT against the table rowtype.
  v_sql := pg_catalog.format(
    'INSERT INTO %s SELECT r.* FROM pg_catalog.jsonb_populate_recordset(NULL::%s, $1) AS r ON CONFLICT ON CONSTRAINT %I %s',
    v_tbl::text,
    v_tbl::text,
    v_constraint,
    COALESCE(pg_catalog.format('DO UPDATE SET %s', v_update_clause), 'DO NOTHING')
  );

  EXECUTE v_sql USING v_rows;

  RETURN;
END;
$fn$;

-- Notes for reviewers/operators:
-- - This remains a SECURITY DEFINER function; ensure the owner has INSERT/UPDATE on public.consolidated_values.
-- - Callers can optionally pass { "conflict_constraint": "<constraint_name>", "rows": [ ... ] } to control the UPSERT key explicitly.
-- - Example minimal row: { "player": "p1", "detail_locator": "locA", "bake_uuid": "de305d54-75b4-431b-adb2-eb6b9e546014", ...other table columns... }
--   bake_id is derived from bake_uuid text; if both are present, bake_id wins as provided.
-- - The function fails-closed on missing player/detail_locator/bake_id and relies on table constraints for any further NOT NULLs.

-- ============================================================
-- 2. NOTIFY
-- ============================================================
-- After Roman applies this DDL in the Supabase SQL editor, run:
--   NOTIFY pgrst, 'reload schema';
-- (PostgREST schema-cache lag — cbsros precedent,
-- sql/migrations/002 §5).

-- ============================================================
-- 3. Verification (run after NOTIFY)
-- ============================================================
-- -- 3a. Function replaced:
--   SELECT proname, pg_get_functiondef(oid)
--     FROM pg_proc
--    WHERE proname = 'ingest_consolidated_values';
--   -- expect: body has the jsonb_populate_recordset INSERT and the
--   -- SECURITY DEFINER with SET search_path = pg_catalog, public.
--
-- -- 3b. Required columns exist (prereq):
--   SELECT column_name, is_nullable
--     FROM information_schema.columns
--    WHERE table_schema = 'public' AND table_name = 'consolidated_values'
--      AND column_name IN ('player', 'detail_locator', 'bake_id');
--   -- expect: all three present; player/detail_locator/bake_id
--   -- NOT NULL (the function fails-closed on NULLs).
--
-- -- 3c. Negative — call with a row missing player; expect RAISE EXCEPTION:
--   SELECT api.ingest_consolidated_values(
--     '[{"detail_locator":"locA","bake_uuid":"00000000-0000-0000-0000-000000000000"}]'::jsonb
--   );
--   -- expect: ERROR: missing required fields (player, detail_locator, bake_id/bake_uuid) in 1 row(s); example: ...
--
-- -- 3d. Positive — call with a valid row; expect void return and a new row:
--   SELECT api.ingest_consolidated_values(
--     '[{"player":"p_smoke","detail_locator":"locA","bake_uuid":"00000000-0000-0000-0000-000000000000","combo_reindexed":12.34}]'::jsonb
--   );
--   SELECT player, detail_locator, bake_id FROM public.consolidated_values WHERE player='p_smoke';
--   -- expect: bake_id = '00000000-0000-0000-0000-000000000000' (derived from bake_uuid).
--   -- Clean up:  DELETE FROM public.consolidated_values WHERE player='p_smoke';