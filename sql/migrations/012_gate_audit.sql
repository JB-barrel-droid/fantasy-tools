-- ============================================================
-- JEG-379: gate audit monitoring — public.gate_audits
--          + api.audit_publish_gate() + v_gate_audits_latest
--
-- Status: write-only; Roman applies via Supabase SQL editor,
-- then runs  NOTIFY pgrst, 'reload schema';
-- (cbsros precedent — sql/migrations/002 §5).
--
-- What this is:
--   The publish gate (api.run_publish_gate) runs at publish time.
--   This audit re-runs the SAME gate suite against the
--   currently-active publishable snapshot on a schedule, and
--   records one row per run. It catches regressions that happen
--   BETWEEN publishes: source staleness (gate 5c is content-vintage
--   based), missing/changed source_config, broken bakes, schema
--   drift in the joined tables, or an active snapshot that was
--   flipped manually without gates.
--
--   Mirrors the public.fidelity_runs pattern (JEG-384):
--   pass | fail | blocked | error rows so downstream surfaces
--   (JEG-322 health) can distinguish "ran and passed" from
--   "never scheduled / blocked / crashed".
--
--   api.run_publish_gate is STABLE with no side effects, so the
--   audit is read-only except for its own audit row.
--
-- APPLY:
--   1. Paste this file into the Supabase SQL editor, run it.
--   2. Run: NOTIFY pgrst, 'reload schema';
--   3. Smoke test (read-only against the live active snapshot):
--        SELECT api.audit_publish_gate('1.0.0');
--      then confirm one row landed:
--        SELECT run_id, outcome, passed, failed_gates, run_at
--          FROM public.gate_audits ORDER BY run_at DESC LIMIT 1;
--      (the smoke test writes exactly one audit row; that is the
--      intended behavior — it IS the first audit.)
--   4. Schedule pg_cron ONLY with explicit approval (recurring
--      production job):
--        select cron.schedule(
--          'gate-audit-v1',
--          '*/30 * * * *',
--          $$select api.audit_publish_gate('1.0.0');$$
--        );
-- ============================================================

-- ============================================================
-- 1. Audit table: one row per scheduled gate-audit run
-- ============================================================

CREATE TABLE IF NOT EXISTS public.gate_audits (
  run_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
  run_at           TIMESTAMPTZ  NOT NULL DEFAULT now(),
  contract_version TEXT         NOT NULL,
  snapshot_id      UUID,                 -- active snapshot audited;
                                        -- NULL when outcome='blocked'/'error'
  passed           BOOLEAN      NOT NULL,
  gate_results     JSONB        NOT NULL DEFAULT '[]'::jsonb,
  warnings         JSONB        NOT NULL DEFAULT '[]'::jsonb,
  failed_gates     TEXT[]       NOT NULL DEFAULT '{}',
  outcome          TEXT         NOT NULL
                   CHECK (outcome IN ('pass','fail','blocked','error')),
  blocked_reason   TEXT,                 -- set for 'blocked' and 'error'
  metadata         JSONB        NOT NULL DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gate_audits_contract_run
  ON public.gate_audits (contract_version, run_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_gate_audits_outcome
  ON public.gate_audits (outcome, run_at DESC NULLS LAST);

COMMENT ON TABLE public.gate_audits IS
  'JEG-379 (2026-10-04): one row per scheduled re-run of api.run_publish_gate against the active publishable snapshot. outcome: pass | fail | blocked (no active snapshot) | error (gate call raised). Fail-closed: a missing active snapshot is blocked, never pass.';

-- ============================================================
-- 2. Audit function
-- ============================================================

CREATE OR REPLACE FUNCTION api.audit_publish_gate(
  p_contract_version TEXT DEFAULT '1.0.0'
) RETURNS JSONB
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, api
AS $$
DECLARE
  v_snapshot_id UUID;
  v_bake_ids    JSONB;
  v_verdict     JSONB;
  v_passed      BOOLEAN;
  v_gates       JSONB;
  v_warnings    JSONB;
  v_failed      TEXT[];
  v_outcome     TEXT;
  v_run_id      UUID;
  v_run_at      TIMESTAMPTZ;
BEGIN
  -- NULL contract_version is a caller bug: fail closed before touching data.
  IF p_contract_version IS NULL THEN
    RAISE EXCEPTION 'audit_publish_gate: NULL contract_version not allowed';
  END IF;

  -- Resolve the currently-active publishable snapshot for this contract
  -- version. Newest wins on ties; the partial unique index
  -- product_snapshot_active_uidx normally guarantees at most one.
  SELECT s.snapshot_id, s.bake_ids
    INTO v_snapshot_id, v_bake_ids
    FROM public.product_snapshot s
   WHERE s.contract_version = p_contract_version
     AND s.is_active = TRUE
     AND s.publishable = TRUE
   ORDER BY s.built_at DESC NULLS LAST,
            s.generated_at DESC NULLS LAST
   LIMIT 1;

  -- Fail closed: no active snapshot is a BLOCKED audit, never a pass.
  IF v_snapshot_id IS NULL THEN
    INSERT INTO public.gate_audits(
      contract_version, snapshot_id, passed, gate_results, warnings,
      failed_gates, outcome, blocked_reason
    )
    VALUES (
      p_contract_version, NULL, FALSE, '[]'::jsonb, '[]'::jsonb, '{}',
      'blocked',
      'no active publishable snapshot for contract_version=' || p_contract_version
    )
    RETURNING gate_audits.run_id, gate_audits.run_at
    INTO v_run_id, v_run_at;

    RETURN jsonb_build_object(
      'run_id',           v_run_id,
      'run_at',           v_run_at,
      'contract_version', p_contract_version,
      'snapshot_id',      NULL,
      'passed',           FALSE,
      'outcome',          'blocked',
      'blocked_reason',   'no active publishable snapshot'
    );
  END IF;

  -- Run the full gate suite against the active snapshot's bake_ids.
  -- run_publish_gate is STABLE / side-effect free; the audit's only
  -- write is its own gate_audits row below.
  BEGIN
    v_verdict := api.run_publish_gate(p_contract_version, v_bake_ids, v_snapshot_id);
  EXCEPTION WHEN OTHERS THEN
    INSERT INTO public.gate_audits(
      contract_version, snapshot_id, passed, gate_results, warnings,
      failed_gates, outcome, blocked_reason
    )
    VALUES (
      p_contract_version, v_snapshot_id, FALSE, '[]'::jsonb, '[]'::jsonb, '{}',
      'error', 'run_publish_gate raised: ' || SQLERRM
    )
    RETURNING gate_audits.run_id, gate_audits.run_at
    INTO v_run_id, v_run_at;

    RETURN jsonb_build_object(
      'run_id',           v_run_id,
      'run_at',           v_run_at,
      'contract_version', p_contract_version,
      'snapshot_id',      v_snapshot_id,
      'passed',           FALSE,
      'outcome',          'error',
      'blocked_reason',   'run_publish_gate raised: ' || SQLERRM
    );
  END;

  -- Extract the verdict into the audit row.
  v_passed   := COALESCE((v_verdict ->> 'passed')::BOOLEAN, FALSE);
  v_gates    := COALESCE(v_verdict -> 'gates', '[]'::jsonb);
  v_warnings := COALESCE(v_verdict -> 'warnings', '[]'::jsonb);

  SELECT COALESCE(array_agg(g ->> 'gate' ORDER BY g ->> 'gate'), '{}')
    INTO v_failed
    FROM jsonb_array_elements(v_gates) AS g
   WHERE (g ->> 'passed')::BOOLEAN IS DISTINCT FROM TRUE;

  v_outcome := CASE WHEN v_passed THEN 'pass' ELSE 'fail' END;

  INSERT INTO public.gate_audits(
    contract_version, snapshot_id, passed, gate_results, warnings,
    failed_gates, outcome
  )
  VALUES (
    p_contract_version, v_snapshot_id, v_passed, v_gates, v_warnings,
    v_failed, v_outcome
  )
  RETURNING gate_audits.run_id, gate_audits.run_at
  INTO v_run_id, v_run_at;

  RETURN jsonb_build_object(
    'run_id',           v_run_id,
    'run_at',           v_run_at,
    'contract_version', p_contract_version,
    'snapshot_id',      v_snapshot_id,
    'passed',           v_passed,
    'outcome',          v_outcome,
    'failed_gates',     to_jsonb(v_failed),
    'warnings',         v_warnings
  );
END;
$$;

COMMENT ON FUNCTION api.audit_publish_gate(TEXT) IS
  'JEG-379 (2026-10-04): scheduled gate-audit entry point. Re-runs api.run_publish_gate against the active publishable snapshot for the given contract_version and records one row in public.gate_audits (pass|fail|blocked|error). Fail-closed: missing active snapshot -> blocked, never pass. Idempotent per run (each call inserts exactly one row).';

-- ============================================================
-- 3. Grants
--    pg_cron on Supabase schedules as the postgres role; the
--    pipeline and health surfaces connect as service_role.
--    SECURITY DEFINER means callers only need EXECUTE.
-- ============================================================

GRANT USAGE ON SCHEMA api TO service_role;
GRANT EXECUTE ON FUNCTION api.audit_publish_gate(TEXT) TO service_role;
GRANT EXECUTE ON FUNCTION api.audit_publish_gate(TEXT) TO postgres;
GRANT SELECT ON public.gate_audits TO service_role;

-- ============================================================
-- 4. Latest-run view for the JEG-322 health surface
-- ============================================================

CREATE OR REPLACE VIEW public.v_gate_audits_latest AS
SELECT DISTINCT ON (contract_version)
  run_id,
  run_at,
  contract_version,
  snapshot_id,
  passed,
  gate_results,
  warnings,
  failed_gates,
  outcome,
  blocked_reason,
  metadata,
  created_at
FROM public.gate_audits
ORDER BY contract_version, run_at DESC NULLS LAST;

COMMENT ON VIEW public.v_gate_audits_latest IS
  'JEG-379 (2026-10-04): most recent gate-audit run per contract_version. Read by the JEG-322 health surface: outcome=pass (green), fail (red — failed_gates names the gates), blocked/error (amber — blocked_reason explains).';

GRANT SELECT ON public.v_gate_audits_latest TO service_role;

-- ============================================================
-- 5. pg_cron schedule — NOT APPLIED HERE.
--    Creates a recurring production job: needs explicit approval.
--    Suggested cadence: every 30 minutes (the gate suite is
--    heavier than the 60s heartbeat evaluator; gate 5c freshness
--    SLAs are 24h-168h, so 30m gives ample detection margin).
--
--    select cron.schedule(
--      'gate-audit-v1',
--      '*/30 * * * *',
--      $$select api.audit_publish_gate('1.0.0');$$
--    );
--
--    Verify:  select jobname, schedule, active from cron.job;
--    Remove:  select cron.unschedule('gate-audit-v1');
-- ============================================================

-- ============================================================
-- 6. NOTIFY
-- ============================================================
-- After Roman applies this DDL in the Supabase SQL editor, run:
--   NOTIFY pgrst, 'reload schema';
-- (PostgREST schema-cache lag — cbsros precedent,
-- sql/migrations/002 §5).
