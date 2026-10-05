-- ============================================================
-- JEG-389 (2026-10-04): bake-identity cleanup for consolidated_values.
--
-- DECISION: consolidated_values.bake_uuid (uuid) is CANONICAL.
-- Verified live 2026-10-04: 20,865 rows, 0 NULL bake_uuid, 0 orphan
-- bake_uuid (every value exists in public.bakes.bake_id).
--
-- consolidated_values.bake_id (text) is LEGACY: it carries an ISO
-- timestamp string (e.g. '2026-10-04T11:00:35.444386+00:00'), not a
-- real identity. It is NOT dropped here (the ingest RPC still derives
-- it from bake_uuid for backward compatibility, and readers may still
-- use it); it is marked deprecated. A future migration may drop it
-- after the deprecation window.
--
-- This migration:
--   1. Adds FK consolidated_values.bake_uuid -> bakes.bake_id
--      (idempotent; safe: 0 orphans verified).
--   2. Sets bake_uuid NOT NULL (idempotent; safe: 0 nulls verified).
--   3. Adds column/table comments documenting canonical vs legacy.
--
-- Apply via the Supabase SQL editor, then:
--   NOTIFY pgrst, 'reload schema';
-- ============================================================

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_catalog.pg_constraint
    WHERE conname = 'fk_consolidated_values_bake_uuid'
  ) THEN
    ALTER TABLE public.consolidated_values
      ADD CONSTRAINT fk_consolidated_values_bake_uuid
      FOREIGN KEY (bake_uuid) REFERENCES public.bakes(bake_id);
  END IF;
END $$;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'consolidated_values'
      AND column_name = 'bake_uuid'
      AND is_nullable = 'YES'
  ) THEN
    ALTER TABLE public.consolidated_values
      ALTER COLUMN bake_uuid SET NOT NULL;
  END IF;
END $$;

COMMENT ON COLUMN public.consolidated_values.bake_uuid IS
  'JEG-389 CANONICAL bake identity: FK to public.bakes.bake_id. '
  'Every row must carry the bake UUID it was loaded from.';

COMMENT ON COLUMN public.consolidated_values.bake_id IS
  'JEG-389 DEPRECATED: legacy ISO-timestamp string, not a real identity. '
  'Do not use for joins; use bake_uuid. '
  'Kept for backward compatibility; may be dropped after the deprecation window.';

-- NOTIFY pgrst, 'reload schema';  -- run after applying
