-- chore/retire-extras (2026-10-08): drop the empty player-news context tables.
--
-- Player news was retired from the site (Jeremy 2026-10-08): player-news.json,
-- its ingester and every page read are gone (branch chore/retire-extras). The
-- database mirror was never populated: public.player_news, player_adjustments
-- and player_review held 0 rows on 2026-10-08, nothing in the repo writes them,
-- and the only reader is the view api.player_context plus the publish gate's
-- api.gate_context_valid_fresh (called by api.run_publish_gate on every bake).
--
-- NOT APPLIED. The integrator batches this for Jeremy's OK.
--
-- Order matters: the gate function reads public.player_news unconditionally,
-- so it is redefined first (same signature, same passed=TRUE verdict and output
-- keys, no table reads); dropping the tables first would make every
-- run_publish_gate call raise. Objects are dropped without CASCADE so any
-- dependent nobody knew about stops the migration instead of vanishing.
--
-- Revival: sql/contract/api_v1.sql (tables + view) and
-- supabase/migrations/jeg377_jeg380_api_mirror.sql (gate function) at aefb8f7.

BEGIN;

-- Guard: abort if any of the tables holds data.
DO $guard$
DECLARE
  t TEXT;
  n BIGINT;
BEGIN
  FOREACH t IN ARRAY ARRAY['public.player_news', 'public.player_adjustments', 'public.player_review'] LOOP
    IF to_regclass(t) IS NOT NULL THEN
      EXECUTE format('SELECT count(*) FROM %s', t) INTO n;
      IF n > 0 THEN
        RAISE EXCEPTION 'retire_player_context: % has % rows; refusing to drop', t, n;
      END IF;
    END IF;
  END LOOP;
END
$guard$;

-- The publish gate's context check: no context tables any more, so it always
-- passes and says why. Output keys kept so gate logs stay comparable.
CREATE OR REPLACE FUNCTION api.gate_context_valid_fresh(p_contract_version text, p_candidate_snapshot_id uuid, p_bake_uuid uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'api', 'public'
AS $function$
BEGIN
  RETURN jsonb_build_object(
    'passed', TRUE,
    'gate', 'context_valid_fresh',
    'warnings', '[]'::jsonb,
    'latest_news_at', NULL,
    'latest_adjustment_at', NULL,
    'note', 'player news context retired 2026-10-08 (chore/retire-extras); nothing to check');
END;
$function$;

DROP VIEW IF EXISTS api.player_context;
DROP TABLE IF EXISTS public.player_news;
DROP TABLE IF EXISTS public.player_adjustments;
DROP TABLE IF EXISTS public.player_review;

COMMIT;
