-- JEG-1351 path A: merge three duplicate public.players rows into the
-- original row for the same person, then delete the duplicates.
--
-- NOT APPLIED. Production write: needs Jeremy's yes before it runs on
-- production (iskiybsimubiujwuchsl). Data only, no DDL. Run
-- jeg1351_sleeper_aliases.sql in the same session, before or after this.
--
-- Why these are one person each (read-only SQL, 2026-10-29 23:30 UTC):
-- Sleeper id -> gsis in data/inputs/sleeper_projection_idmap.csv (status
-- matched) equals the original row's metadata.gsis_id. The duplicate has no
-- gsis_id; sleeper-identity-refresh (JEG-502) inserted it because Sleeper's
-- spelling didn't resolve and the original carried no sleeper_id.
--
--   duplicate                     original                     sleeper  gsis
--   4653 Nyheim Miller-Hines RB   2785 Nyheim Hines RB         5347     00-0034367
--   4655 Jody Fortson TE          437  Joseph Fortson TE       6665     00-0035547
--   4660 Mitch Tinsley WR         4363 Mitchell Tinsley WR     11068    00-0038839
--
-- What references the duplicates today (all 34 foreign keys checked):
-- 4653 none, 4655 none, 4660 player_status_history 19 rows. Those 19 move to
-- 4363 (the daily status save keys rows by sleeper_id, so no unique clash).
--
-- What this does, per pair (the migration runner wraps the file in one
-- transaction, so any raise rolls back all three):
--   1. Check the duplicate and original still look as above; raise if not.
--   2. Raise if a CASCADE or SET NULL reference (player_game_stats,
--      ranker_rankings, player_value_notes) points at the duplicate, since a
--      delete would drop or blank it silently.
--   3. Move player_status_history rows to the original.
--   4. Put the Sleeper id on the original (metadata.sleeper_id), so the
--      refresh and the status save find it by id, and carry active = true
--      from the duplicate (Sleeper lists the player as in the universe).
--   5. Delete the duplicate. Any other reference left (all NO ACTION) makes
--      the delete fail and the whole transaction roll back.
--
-- Rollback: re-insert the three rows below with their player_key
-- (OVERRIDING SYSTEM VALUE), move the 19 status rows back to 4660, remove
-- metadata.sleeper_id from 2785/437/4363 and set their active back to false.
--   4653 id 17d4f95d-4203-4f88-b5d4-aab75bc75188, active true, league/team null,
--        metadata {"team": null, "source": "sleeper-identity-refresh (JEG-502)",
--        "sleeper_id": "5347", "roster_status": "free_agent"}
--   4655 id ca815762-be95-45a6-b276-ca76c9f7ad90, active true, league/team null,
--        metadata {"team": null, "source": "sleeper-identity-refresh (JEG-502)",
--        "sleeper_id": "6665", "roster_status": "free_agent"}
--   4660 id 2e3a8c29-715a-4932-9e71-1d3247e2c2ae, active true, league null,
--        team_id 68721ad0-86e9-4fe8-a45e-61466b495f29, metadata {"team": "CIN",
--        "source": "sleeper-identity-refresh (JEG-502)", "sleeper_id": "11068",
--        "roster_status": "active_roster"}
--
-- Not in scope: 4661 Ben VanSumeren RB vs 1155 (LB). Same pattern, but the
-- duplicate carries the values there, so it needs its own decision.

do $$
declare
    pair record;
    dup_row public.players%rowtype;
    orig_row public.players%rowtype;
    n int;
begin
    for pair in
        select * from (values
            (4653, 2785, 'Nyheim Miller-Hines', '5347', '00-0034367'),
            (4655, 437, 'Jody Fortson', '6665', '00-0035547'),
            (4660, 4363, 'Mitch Tinsley', '11068', '00-0038839')
        ) as v(dup_key, orig_key, dup_name, sleeper_id, gsis)
    loop
        select * into dup_row from public.players where player_key = pair.dup_key;
        select * into orig_row from public.players where player_key = pair.orig_key;
        if dup_row.player_key is null or orig_row.player_key is null then
            raise exception 'JEG-1351: % or % is missing', pair.dup_key, pair.orig_key;
        end if;
        if dup_row.full_name <> pair.dup_name
           or dup_row.metadata->>'sleeper_id' is distinct from pair.sleeper_id
           or dup_row.metadata ? 'gsis_id' then
            raise exception 'JEG-1351: duplicate % changed since 2026-10-29', pair.dup_key;
        end if;
        if orig_row.metadata->>'gsis_id' is distinct from pair.gsis
           or orig_row.position <> dup_row.position
           or coalesce(orig_row.metadata->>'sleeper_id', pair.sleeper_id) <> pair.sleeper_id then
            raise exception 'JEG-1351: original % changed since 2026-10-29', pair.orig_key;
        end if;

        select (select count(*) from public.player_game_stats where player_id = dup_row.id)
             + (select count(*) from public.ranker_rankings where player_id = dup_row.id)
             + (select count(*) from public.player_value_notes where player_id = dup_row.id)
          into n;
        if n > 0 then
            raise exception 'JEG-1351: % has % cascade/set-null references; stop and re-check',
                pair.dup_key, n;
        end if;

        update public.player_status_history
           set player_key = pair.orig_key
         where player_key = pair.dup_key;

        update public.players
           set metadata = coalesce(metadata, '{}'::jsonb)
                          || jsonb_build_object('sleeper_id', pair.sleeper_id,
                                                'merged_from', pair.dup_key),
               active = active or dup_row.active
         where player_key = pair.orig_key;

        delete from public.players where player_key = pair.dup_key;
    end loop;
end
$$;

-- Read back: three originals carry their Sleeper id, no duplicate is left.
select player_key, full_name, active, metadata->>'sleeper_id' as sleeper_id
  from public.players
 where player_key in (2785, 437, 4363, 4653, 4655, 4660)
 order by player_key;
