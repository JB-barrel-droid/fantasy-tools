-- ==============================================================================
-- JEG-383: Never-Blend Trigger Fix
--
-- PROBLEM (verified 2026-10-04):
--   The original trigger checked raw_source_payload for vegas_provenance/vegas_stats_used,
--   but all 3,648 live Vegas rows store attribution in dedicated COLUMNS, not payload.
--   This caused the trigger to reject every legitimate write.
--
--   Additionally, the provenance allowlist omitted real values: complete, td-filled, partial.
--
-- FIX:
--   1. Check vegas_provenance column (not payload) for valid values
--   2. Check vegas_stats_used column is not null for publishable provenance
--   3. Expand allowlist to match ALLOWED_PROVENANCE from engine/fds_fallback.py:
--      - complete, td-filled, partial (local Vegas completeness levels)
--      - fds-derived, fds-partial (FDS fallback provenance)
--
-- RUN THIS IN SUPABASE SQL EDITOR
-- ==============================================================================

BEGIN;

-- Step 1: Add vegas_provenance column if it doesn't exist (may already exist from earlier migration)
ALTER TABLE weekly_source_snapshots
  ADD COLUMN IF NOT EXISTS vegas_provenance text;

-- Step 2: Create or replace the never-blend trigger function
CREATE OR REPLACE FUNCTION check_never_blend()
RETURNS TRIGGER AS $$
DECLARE
  -- Provenance values from engine/fds_fallback.py ALLOWED_PROVENANCE
  ALLOWED_PROVENANCE text[] := ARRAY['complete', 'td-filled', 'partial', 'fds-derived', 'fds-partial'];
  -- Publishable = only these may appear in public outputs
  PUBLISHABLE_PROVENANCE text[] := ARRAY['complete', 'td-filled', 'fds-derived'];
BEGIN
  -- Skip all checks for non-Vegas sources
  IF NEW.source != 'vegas_implied' THEN
    RETURN NEW;
  END IF;

  -- Check 1: vegas_provenance must be in ALLOWED_PROVENANCE
  IF NEW.vegas_provenance IS NOT NULL
     AND NEW.vegas_provenance != ANY(ALLOWED_PROVENANCE) THEN
    RAISE EXCEPTION 'never-blend violation: vegas_provenance=% not in allowed list % (row: %)',
      NEW.vegas_provenance, ALLOWED_PROVENANCE, NEW.id;
  END IF;

  -- Check 2: Publishable provenance requires vegas_stats_used to be populated
  -- This ensures we can audit which stats fed the Vegas number
  IF NEW.vegas_provenance = ANY(PUBLISHABLE_PROVENANCE)
     AND (NEW.vegas_stats_used IS NULL OR NEW.vegas_stats_used = '{}'::jsonb) THEN
    RAISE EXCEPTION 'never-blend violation: publishable provenance % requires vegas_stats_used to be populated (row: %)',
      NEW.vegas_provenance, NEW.id;
  END IF;

  -- Check 3: If vegas_stats_used is populated, fds_stat_sources should also be present
  -- (for FDS-derived rows, these go together)
  IF NEW.vegas_stats_used IS NOT NULL
     AND NEW.vegas_stats_used != '{}'::jsonb
     AND NEW.fds_stat_sources IS NULL
     AND NEW.vegas_provenance IN ('fds-derived', 'fds-partial') THEN
    RAISE EXCEPTION 'never-blend violation: FDS provenance % requires fds_stat_sources (row: %)',
      NEW.vegas_provenance, NEW.id;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql
  SECURITY DEFINER
  SET search_path = public;

-- Step 3: Drop existing trigger if present, then create new one
DROP TRIGGER IF EXISTS trg_never_blend ON weekly_source_snapshots;

CREATE TRIGGER trg_never_blend
  BEFORE INSERT OR UPDATE ON weekly_source_snapshots
  FOR EACH ROW
  EXECUTE FUNCTION check_never_blend();

-- Step 4: Grant execute permission to lane_b_writer (the pipeline writer role)
GRANT EXECUTE ON FUNCTION check_never_blend() TO lane_b_writer;

COMMIT;

-- ==============================================================================
-- VERIFICATION STEPS (run these in Supabase SQL Editor after applying):
-- ==============================================================================

-- Test 1: Verify trigger exists
-- SELECT tgname, proname, prosrc
-- FROM pg_trigger t
-- JOIN pg_proc p ON t.tgfoid = p.oid
-- WHERE tgname = 'trg_never_blend';

-- Test 2: Check current Vegas rows - should all pass (3,648 rows)
-- SELECT
--   vegas_provenance,
--   COUNT(*) as row_count,
--   COUNT(vegas_stats_used) as with_stats_used
-- FROM weekly_source_snapshots
-- WHERE source = 'vegas_implied'
-- GROUP BY vegas_provenance;

-- Test 3: Verify allowed values match ALLOWED_PROVENANCE
-- Expected: complete, td-filled, partial, fds-derived, fds-partial
-- SELECT DISTINCT vegas_provenance FROM weekly_source_snapshots WHERE source = 'vegas_implied';

-- Test 4: Try inserting a test row that SHOULD be rejected (invalid provenance)
-- This should raise an exception:
-- INSERT INTO weekly_source_snapshots (season, week, source, scoring_format, player_id, vegas_provenance)
-- VALUES (2026, 5, 'vegas_implied', 'half_ppr', gen_random_uuid(), 'invalid-provenance');

-- Test 5: Try inserting a test row that SHOULD be rejected (publishable without stats)
-- This should raise an exception:
-- INSERT INTO weekly_source_snapshots (season, week, source, scoring_format, player_id, vegas_provenance, vegas_stats_used)
-- VALUES (2026, 5, 'vegas_implied', 'half_ppr', gen_random_uuid(), 'complete', NULL);
