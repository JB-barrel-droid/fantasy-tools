-- JEG-539 item 3, GAP-POSITION-CONFLICT-NAMES: six public.players rows carry
-- a position that ESPN, Razzball and Sleeper's depth charts all contradict.
-- The canonical resolver refuses a publisher's name at a position the table
-- does not hold (position_conflict), so ESPN stored none of them (Russell
-- 8.0, Heyward 9.6, Yankoff 4.9 half-PPR rest of season lost), and the pulse
-- listed them amber.
--
-- Checked 2026-10-10 (Sleeper /players/nfl, data/inputs/sleeper_identity_base.json,
-- each row's own metadata.sleeper.depth_chart_position, ESPN and Razzball pages):
--   key   name               table  Sleeper pos / depth chart     ESPN  Razzball
--   2724  Brady Russell      TE     RB / SEA RB 3                 RB    RB
--    914  Connor Heyward     TE     RB / LV RB 3                  RB    RB
--   3963  Riley Nowakowski   TE     RB / PIT RB 5                 RB    RB
--   3889  Colson Yankoff     RB     TE / WAS TE 4                 TE    TE
--   4000  Jackson Meeks      WR     TE / DET TE 4                 TE    TE
--   3087  Ty Pezza           WR     TE / BAL (no depth slot)      -     TE
-- These five depth-chart rows are every skill row whose
-- metadata.sleeper.depth_chart_position disagrees with position (query below).
-- Max Hurleman (2100, RB) is left alone: Razzball lists WR, Sleeper CB.
--
-- Data only (no schema change). Apply once, as one transaction; each
-- statement asserts the state it expects. tests/test_position_conflict_names.py
-- pins this file to the Sleeper identity base.

BEGIN;

DO $$
BEGIN
  IF (SELECT count(*) FROM public.players
       WHERE (player_key, full_name, position) IN
             ((2724, 'Brady Russell', 'TE'), (914, 'Connor Heyward', 'TE'),
              (3963, 'Riley Nowakowski', 'TE'), (3889, 'Colson Yankoff', 'RB'),
              (4000, 'Jackson Meeks', 'WR'), (3087, 'Ty Pezza', 'WR'))) <> 6 THEN
    RAISE EXCEPTION 'expected the six rows at their old positions; review before applying';
  END IF;
END $$;

UPDATE public.players AS p
   SET position = v.new_position,
       metadata = coalesce(p.metadata, '{}'::jsonb)
                  || jsonb_build_object('position_corrected', jsonb_build_object(
                       'from', p.position, 'to', v.new_position, 'on', '2026-10-10',
                       'ticket', 'JEG-539', 'evidence', 'Sleeper depth chart + ESPN + Razzball'))
  FROM (VALUES (2724, 'RB'), (914, 'RB'), (3963, 'RB'),
               (3889, 'TE'), (4000, 'TE'), (3087, 'TE')) AS v(player_key, new_position)
 WHERE p.player_key = v.player_key;

COMMIT;

-- Verify (expect no rows):
--   SELECT player_key, full_name, position, metadata->'sleeper'->>'depth_chart_position'
--     FROM public.players
--    WHERE position IN ('QB','RB','WR','TE')
--      AND metadata->'sleeper'->>'depth_chart_position' IN ('QB','RB','WR','TE')
--      AND metadata->'sleeper'->>'depth_chart_position' <> position;
