-- GAP-RAZZBALL-REFRESH-FOLLOWUPS (2): public.players holds Audric Estime twice.
--   4642 "Audric Estime"  RB DEN active=true   (manual add 2026-09-18; FP season
--                                               projections, projection_snapshots,
--                                               one player_name_aliases row; the
--                                               chart fixture and players.json use it)
--   1475 "Audric Estimé"  RB DEN active=false  (carries gsis_id 00-0039373 and the
--                                               18 player_game_stats rows; nothing else)
-- Accent-folding savers saw one name with two keys and sent him to review on
-- every Razzball save. The code now picks the single active row
-- (canonical_players.narrow_candidates); this merge removes the duplicate.
--
-- Checked read-only 2026-10-08: every FK table (by players.id and by
-- player_key) has 0 rows for 1475 except player_game_stats (18). 4642 has 0
-- player_game_stats rows, so moving them cannot collide.
--
-- Apply once, as one transaction. Each statement asserts the state it expects.

BEGIN;

DO $$
BEGIN
  IF (SELECT count(*) FROM public.players WHERE player_key IN (1475, 4642)) <> 2 THEN
    RAISE EXCEPTION 'expected both Estime rows (1475, 4642)';
  END IF;
  IF EXISTS (SELECT 1 FROM public.player_game_stats
             WHERE player_id = (SELECT id FROM public.players WHERE player_key = 4642)) THEN
    RAISE EXCEPTION '4642 already has player_game_stats rows; review before merging';
  END IF;
END $$;

-- Keep the survivor's identity data: gsis_id from 1475.
UPDATE public.players
   SET metadata = coalesce(metadata, '{}'::jsonb)
                  || jsonb_build_object('gsis_id', '00-0039373',
                                        'merged_from_player_key', 1475,
                                        'merged_at', '2026-10-08')
 WHERE player_key = 4642;

UPDATE public.player_game_stats
   SET player_id = (SELECT id FROM public.players WHERE player_key = 4642)
 WHERE player_id = (SELECT id FROM public.players WHERE player_key = 1475);

DELETE FROM public.players WHERE player_key = 1475;

COMMIT;

-- Verify:
--   SELECT player_key, full_name, active, metadata->>'gsis_id' FROM public.players
--    WHERE full_name ILIKE 'audric%';                      -- one row, 4642
--   SELECT count(*) FROM public.player_game_stats
--    WHERE player_id = (SELECT id FROM public.players WHERE player_key = 4642);  -- 18
-- Caveat: if a roster sync re-inserts players by gsis_id without reading
-- metadata.gsis_id, 1475 can come back; the savers still resolve 4642 (active).
