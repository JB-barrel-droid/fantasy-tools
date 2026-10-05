-- ============================================================
-- JEG-389 (2026-10-04): loader_runs — canonical run dimension for
-- per_source_cap_audit.
--
-- DECISION: per_source_cap_audit.run_id identifies ONE EXECUTION of
-- pipelines/load_ddf_leg_to_supabase.py. It is NOT owned by
-- fidelity_runs (the JEG-375 fidelity suite's run dimension — a
-- semantically unrelated concept: fidelity runs measure
-- source-vs-live agreement, loader runs record cap-rescale factors).
-- Conflating them would corrupt both meanings.
--
-- The loader registers its run (build_run_context -> register_loader_run)
-- BEFORE inserting audit rows; the FK below enforces that every audit
-- row belongs to a registered run. per_source_cap_audit is currently
-- empty, so no backfill is needed.
--
-- Apply via the Supabase SQL editor, then:
--   NOTIFY pgrst, 'reload schema';
-- ============================================================

CREATE TABLE IF NOT EXISTS public.loader_runs (
  run_id UUID PRIMARY KEY,
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  ddf_leg_version TEXT,
  git_commit_sha TEXT,
  loader_host TEXT,
  notes TEXT
);

COMMENT ON TABLE public.loader_runs IS
  'JEG-389: one row per load_ddf_leg_to_supabase.py execution. '
  'Owns per_source_cap_audit.run_id (NOT fidelity_runs).';

-- Every audit row must belong to a registered loader run.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint WHERE conname = 'fk_per_source_cap_audit_run_id'
  ) THEN
    ALTER TABLE public.per_source_cap_audit
      ADD CONSTRAINT fk_per_source_cap_audit_run_id
      FOREIGN KEY (run_id) REFERENCES public.loader_runs(run_id);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_loader_runs_started
  ON public.loader_runs(started_at DESC);

-- NOTIFY pgrst, 'reload schema';  -- run after applying
