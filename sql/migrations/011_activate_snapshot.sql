-- ============================================================
-- JEG-377: transactional snapshot activation
-- api.activate_snapshot(p_product, p_candidate, p_contract_version)
--
-- Atomically re-runs the publish gates and flips the active
-- snapshot inside ONE database transaction. Replaces the manual
-- two-UPDATE activation in pipelines/publish_gate.py
-- (commit_active_flip), which had a TOCTOU race between the Python
-- gate check and the flip UPDATEs.
--
-- REVIEW STATUS (ChatGPT v2 review, Roman integration):
--   * Review findings 2-7 applied: NULL-arg guard, composite
--     advisory-lock key, SELECT ... FOR UPDATE on the candidate,
--     search_path = pg_catalog, api, JSON-boolean gate comparison.
--   * Review finding 1 (scope UPDATEs by product) REJECTED as
--     written: the live public.product_snapshot has NO product
--     column (verified 2026-10-04 via REST column enumeration), and
--     the live partial unique index product_snapshot_active_uidx
--     enforces one active row per contract_version. UPDATEs are
--     therefore scoped by contract_version, matching the index.
--     p_product exists only to namespace the advisory lock so a
--     future multi-product table does not collide.
--
-- APPLY: paste into the Supabase SQL editor (PostgREST cannot run
-- DDL), then run:  NOTIFY pgrst, 'reload schema';
-- ============================================================

CREATE OR REPLACE FUNCTION api.activate_snapshot(
  p_product          TEXT,
  p_candidate        UUID,
  p_contract_version TEXT
) RETURNS VOID
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, api
AS $$
DECLARE
  v_row_version TEXT;
  v_bake_ids    JSONB;
  v_gate_result JSONB;
  v_passed      BOOLEAN;
BEGIN
  -- Fail closed on NULL args before touching the lock: a NULL
  -- product would make hashtextextended return NULL and
  -- pg_advisory_xact_lock(NULL) raise a confusing error.
  IF p_product IS NULL OR p_candidate IS NULL OR p_contract_version IS NULL THEN
    RAISE EXCEPTION 'activate_snapshot: NULL arg(s) not allowed (product=% candidate=% contract_version=%)',
      p_product, p_candidate, p_contract_version;
  END IF;

  -- Serialize concurrent activations for this product+contract.
  -- Transaction-scoped: released automatically on COMMIT/ROLLBACK.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_product || ':' || p_contract_version, 0));

  -- Row-lock the candidate so no session can mutate it between the
  -- gate check and the flip below (TOCTOU fix).
  SELECT s.contract_version, s.bake_ids
    INTO v_row_version, v_bake_ids
    FROM public.product_snapshot s
   WHERE s.snapshot_id = p_candidate
   FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'activate_snapshot: candidate snapshot % not found', p_candidate;
  END IF;

  IF v_row_version IS DISTINCT FROM p_contract_version THEN
    RAISE EXCEPTION 'activate_snapshot: contract_version mismatch (candidate=%, expected=%)',
      v_row_version, p_contract_version;
  END IF;

  IF v_bake_ids IS NULL THEN
    RAISE EXCEPTION 'activate_snapshot: candidate % has NULL bake_ids; cannot scope gates', p_candidate;
  END IF;

  -- Authoritative gate check, in-transaction with the flip. The
  -- Python orchestrator (pipelines/publish_gate.py) runs the same
  -- gates first as an early, detailed pre-check; this call is the
  -- commit-time authority, so a bake that changed between the two
  -- cannot slip through.
  v_gate_result := api.run_publish_gate(p_contract_version, v_bake_ids, p_candidate);
  v_passed := COALESCE(((v_gate_result -> 'passed') = to_jsonb(TRUE)), FALSE);

  IF NOT v_passed THEN
    RAISE EXCEPTION 'activate_snapshot: publish gates failed for candidate %: %', p_candidate, v_gate_result;
  END IF;

  -- Flip. Scoped by contract_version (the live schema has no
  -- product column; the partial unique index below enforces one
  -- active row per contract_version).
  UPDATE public.product_snapshot
     SET is_active = FALSE
   WHERE contract_version = p_contract_version
     AND is_active = TRUE
     AND snapshot_id <> p_candidate;

  UPDATE public.product_snapshot
     SET is_active   = TRUE,
         publishable = TRUE
   WHERE snapshot_id    = p_candidate
     AND contract_version = p_contract_version;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'activate_snapshot: candidate % vanished during flip (contract_version=%)',
      p_candidate, p_contract_version;
  END IF;
END;
$$;

COMMENT ON FUNCTION api.activate_snapshot(TEXT, UUID, TEXT) IS
  'JEG-377 (2026-10-04): transactional snapshot activation. Advisory-locks on product:contract_version, re-runs api.run_publish_gate in-transaction, then flips is_active/publishable atomically. Replaces the manual two-UPDATE activation in pipelines/publish_gate.py. UPDATEs scope by contract_version (no product column exists on public.product_snapshot; one active row per contract_version per partial unique index product_snapshot_active_uidx).';

-- ----------------------------------------------------------------
-- Grants. The publish pipeline connects with a direct Postgres
-- connection (not PostgREST); the caller needs EXECUTE. Adjust the
-- role list if the pipeline uses a dedicated role.
-- ----------------------------------------------------------------
GRANT USAGE ON SCHEMA api TO authenticated;
GRANT USAGE ON SCHEMA api TO service_role;
GRANT EXECUTE ON FUNCTION api.activate_snapshot(TEXT, UUID, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION api.activate_snapshot(TEXT, UUID, TEXT) TO service_role;

-- ----------------------------------------------------------------
-- Hardening (NOT applied — needs Jeremy's explicit call because
-- REVOKEs can break other writers/readers on this project):
--
--   REVOKE CREATE ON SCHEMA public FROM PUBLIC;
--   REVOKE CREATE ON SCHEMA api FROM PUBLIC;
--   REVOKE ALL ON TABLE public.product_snapshot FROM PUBLIC;
--   REVOKE INSERT, UPDATE, DELETE ON TABLE public.product_snapshot FROM <app_role>;
--   GRANT SELECT ON TABLE public.product_snapshot TO <app_role>;
--
-- The one-active-per-contract_version invariant is already enforced
-- by the existing partial unique index:
--   product_snapshot_active_uidx ON public.product_snapshot (contract_version) WHERE is_active = TRUE
-- ----------------------------------------------------------------

-- NOTIFY pgrst, 'reload schema';  -- run after applying (schema-cache lag precedent)
