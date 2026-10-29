-- JEG-1351 path B: one verified alias for a Sleeper spelling of a player the
-- table already holds under another name. (The three duplicate rows are
-- handled in the repo by data/inputs/player_key_merges.json, not by aliases:
-- an alias may not be another row's name.)
--
-- NOT APPLIED. Needs Jeremy's yes before it runs on production
-- (iskiybsimubiujwuchsl). Data only, no DDL. The same row is in the
-- jeg438_alias_table_curated.sql seed and data/inputs/player_aliases.json
-- (tests/test_player_alias_table.py pins the seed to the JSON). Until this
-- runs, lib/player_aliases.load() reads the 13 curated rows from Supabase and
-- production resolvers do not see it; reconcile_player_identity.py
-- reports the drift.
--
-- Each tie is Sleeper id -> gsis (data/inputs/sleeper_projection_idmap.csv,
-- status matched) -> the row carrying that gsis_id (read-only SQL,
-- 2026-10-29 23:30 UTC).

insert into public.player_name_aliases
    (source, source_player_name, norm_name, position, player_key, status, method,
     confidence, verified_at, verified_by, notes)
select '*', v.alias, v.norm_name, v.pos, v.player_key, 'verified', 'curated',
       1, now(), 'jeg1351-curated', v.verified
from (values
    ('Tyron Billy-Johnson', 'tyron billyjohnson', 'WR', 423, '2026-10-29 JEG-1351: Sleeper 6063 -> gsis 00-0035457 = 423 Tyron Johnson')
) as v(alias, norm_name, pos, player_key, verified)
on conflict (source, norm_name, position) do update set
    source_player_name = excluded.source_player_name,
    player_key = excluded.player_key,
    status = 'verified',
    method = 'curated',
    confidence = 1,
    candidate_keys = null,
    verified_at = excluded.verified_at,
    verified_by = excluded.verified_by,
    notes = excluded.notes,
    last_seen_at = now();
