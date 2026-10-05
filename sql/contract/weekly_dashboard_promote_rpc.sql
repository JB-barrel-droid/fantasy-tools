-- JEG-393: atomic weekly dashboard run promotion.
-- PRECONDITION: at most ONE row in public.weekly_dashboard_runs with is_current = true.
-- This migration fails loudly if the precondition is violated.
-- Remediation: UPDATE public.weekly_dashboard_runs SET is_current = false
--              WHERE run_id = '<stale_run_id>';
-- After this migration, the partial unique index makes >1 current row impossible.
-- Apply via the Supabase SQL editor, then: NOTIFY pgrst, 'reload schema';

BEGIN;

DO $$
DECLARE v int;
BEGIN
  SELECT count(*) INTO v FROM public.weekly_dashboard_runs WHERE is_current;
  IF v > 1 THEN
    RAISE EXCEPTION 'JEG-393 precondition violated: % current rows exist; must be <= 1', v;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.promote_weekly_dashboard_run(
  p_run_id uuid,
  p_expected_signals int
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  candidate public.weekly_dashboard_runs;
  actual_signals bigint;
  cur_season int;
  cur_week int;
BEGIN
  -- Serialize concurrent promotions. Transaction-scoped: auto-released at commit/abort.
  PERFORM pg_advisory_xact_lock(hashtext('weekly_dashboard_promotion'));

  SELECT * INTO candidate
  FROM public.weekly_dashboard_runs
  WHERE run_id = p_run_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'run % not found', p_run_id
      USING ERRCODE = 'P0002';
  END IF;

  SELECT count(*) INTO actual_signals
  FROM public.weekly_dashboard_signals
  WHERE run_id = p_run_id;

  -- Idempotent success path: already current with matching count => return true.
  -- Makes loader retries after an RPC timeout safe.
  IF candidate.is_current THEN
    IF actual_signals = p_expected_signals THEN
      RETURN true;
    END IF;
    RAISE EXCEPTION 'run % is current but has % signals, expected %',
      p_run_id, actual_signals, p_expected_signals
      USING ERRCODE = 'P0003';
  END IF;

  IF actual_signals <> p_expected_signals THEN
    RAISE EXCEPTION 'signal count mismatch for run %: got %, expected %',
      p_run_id, actual_signals, p_expected_signals
      USING ERRCODE = 'P0003';
  END IF;

  -- Tuple-safe regression guard (correct across season rollover).
  SELECT season, week INTO cur_season, cur_week
  FROM public.weekly_dashboard_runs
  WHERE is_current;

  IF FOUND AND (candidate.season, candidate.week) < (cur_season, cur_week) THEN
    RAISE EXCEPTION 'refusing regression: run % is season % week %, current is season % week %',
      p_run_id, candidate.season, candidate.week, cur_season, cur_week
      USING ERRCODE = 'P0004';
  END IF;

  -- Single transaction: clear all, set the candidate. No zero/two-current window.
  UPDATE public.weekly_dashboard_runs SET is_current = false WHERE is_current;
  UPDATE public.weekly_dashboard_runs SET is_current = true WHERE run_id = p_run_id;

  RETURN true;
END;
$$;

-- Bounded widening: only service_role may execute (SECURITY DEFINER bypasses
-- RLS on the two weekly tables for the promote path only).
REVOKE ALL ON FUNCTION public.promote_weekly_dashboard_run(uuid, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.promote_weekly_dashboard_run(uuid, int)
  TO service_role;

-- Backstop: more than one current row is impossible from here on.
CREATE UNIQUE INDEX weekly_dashboard_one_current
  ON public.weekly_dashboard_runs (is_current)
  WHERE is_current;

COMMIT;
