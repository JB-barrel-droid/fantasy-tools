-- Migration: per_source_cap_audit table for the per-source 70-cap rescale pipeline stage.
-- Applied live via Supabase SQL editor 2026-10-04 (JEG-380 / over-70 remediation).
-- The loader (pipelines/load_ddf_leg_to_supabase.py) writes audit rows here
-- transactionally with each load when PER_SOURCE_CAP_DB_AUDIT is True.

CREATE TABLE IF NOT EXISTS public.per_source_cap_audit (
  audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL,
  ddf_leg_version TEXT NOT NULL,
  git_commit_sha TEXT NOT NULL,
  source TEXT NOT NULL,
  value_column TEXT NOT NULL DEFAULT 'combo_reindexed',
  cap NUMERIC NOT NULL DEFAULT 70,
  pre_max NUMERIC NOT NULL,
  post_max NUMERIC NOT NULL,
  scale_factor NUMERIC NOT NULL,
  source_row_count BIGINT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  loader_host TEXT,
  notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_per_source_cap_audit_run
  ON public.per_source_cap_audit(ddf_leg_version, run_id);

CREATE INDEX IF NOT EXISTS idx_per_source_cap_audit_source
  ON public.per_source_cap_audit(source, applied_at DESC);
